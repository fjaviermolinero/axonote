"""
Servicio principal de investigación médica automática.

Coordina la búsqueda en múltiples fuentes médicas verificadas,
valida resultados y gestiona el cache inteligente para optimizar
las búsquedas repetidas.
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.core.config import settings
from app.models import (
    ResearchJob, ResearchResult, MedicalSource, SourceCache,
    LLMAnalysisResult, PostProcessingResult
)
from app.services.pubmed_service import PubMedService
from app.services.who_service import WHOService
from app.services.nih_service import NIHService
from app.services.medlineplus_service import MedLinePlusService
from app.services.italian_sources_service import ItalianSourcesService
from app.services.content_validator import ContentValidator
from app.services.source_cache_service import SourceCacheService

logger = logging.getLogger(__name__)


class ResearchConfig:
    """Configuración para trabajos de investigación médica."""
    
    def __init__(
        self,
        preset: str = "COMPREHENSIVE",
        language: str = "it",
        max_sources_per_term: int = 3,
        enabled_sources: Optional[List[str]] = None,
        include_related_terms: bool = True,
        enable_translation: bool = True,
        priority_score_threshold: float = 0.6,
        **kwargs
    ):
        self.preset = preset
        self.language = language
        self.max_sources_per_term = max_sources_per_term
        self.enabled_sources = enabled_sources or self._get_default_sources(preset)
        self.include_related_terms = include_related_terms
        self.enable_translation = enable_translation
        self.priority_score_threshold = priority_score_threshold
        
        # Configuraciones específicas por preset
        preset_configs = self._get_preset_configs()
        if preset in preset_configs:
            config = preset_configs[preset]
            for key, value in config.items():
                if not hasattr(self, key):
                    setattr(self, key, value)
        
        # Aplicar configuraciones adicionales
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def _get_default_sources(self, preset: str) -> List[str]:
        """Obtiene fuentes por defecto según el preset."""
        source_configs = {
            "COMPREHENSIVE": ["pubmed", "who", "nih", "medlineplus", "italian_official"],
            "QUICK": ["pubmed", "who", "italian_official"],
            "ACADEMIC": ["pubmed", "nih"],
            "CLINICAL": ["who", "nih", "medlineplus", "italian_official"],
            "ITALIAN_FOCUSED": ["italian_official", "pubmed", "who"]
        }
        return source_configs.get(preset, source_configs["COMPREHENSIVE"])
    
    def _get_preset_configs(self) -> Dict[str, Dict[str, Any]]:
        """Configuraciones detalladas por preset."""
        return {
            "COMPREHENSIVE": {
                "max_sources_per_term": 5,
                "include_related_terms": True,
                "enable_translation": True,
                "priority_score_threshold": 0.6,
                "peer_review_only": False,
                "clinical_guidelines_priority": False,
                "italian_priority": False
            },
            "QUICK": {
                "max_sources_per_term": 3,
                "include_related_terms": False,
                "enable_translation": False,
                "priority_score_threshold": 0.7,
                "peer_review_only": False,
                "clinical_guidelines_priority": False,
                "italian_priority": False
            },
            "ACADEMIC": {
                "max_sources_per_term": 4,
                "include_related_terms": True,
                "enable_translation": True,
                "priority_score_threshold": 0.8,
                "peer_review_only": True,
                "clinical_guidelines_priority": False,
                "italian_priority": False
            },
            "CLINICAL": {
                "max_sources_per_term": 4,
                "include_related_terms": False,
                "enable_translation": True,
                "priority_score_threshold": 0.7,
                "peer_review_only": False,
                "clinical_guidelines_priority": True,
                "italian_priority": False
            },
            "ITALIAN_FOCUSED": {
                "max_sources_per_term": 4,
                "include_related_terms": True,
                "enable_translation": False,
                "priority_score_threshold": 0.6,
                "peer_review_only": False,
                "clinical_guidelines_priority": False,
                "italian_priority": True
            }
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte la configuración a diccionario."""
        return {
            "preset": self.preset,
            "language": self.language,
            "max_sources_per_term": self.max_sources_per_term,
            "enabled_sources": self.enabled_sources,
            "include_related_terms": self.include_related_terms,
            "enable_translation": self.enable_translation,
            "priority_score_threshold": self.priority_score_threshold
        }
    
    def get_cache_key_data(self) -> str:
        """Genera datos para clave de cache."""
        return f"{self.preset}|{self.language}|{self.max_sources_per_term}|{'|'.join(sorted(self.enabled_sources))}"


class ResearchService:
    """
    Servicio principal de investigación médica automática.
    
    Coordina la búsqueda en múltiples fuentes médicas verificadas,
    valida resultados y gestiona el cache inteligente.
    """
    
    def __init__(self, db: Session):
        self.db = db
        
        # Inicializar servicios de fuentes
        self.pubmed_service = PubMedService()
        self.who_service = WHOService()
        self.nih_service = NIHService()
        self.medlineplus_service = MedLinePlusService()
        self.italian_sources_service = ItalianSourcesService()
        
        # Servicios auxiliares
        self.cache_service = SourceCacheService(db)
        self.content_validator = ContentValidator()
        
        # Mapeo de servicios
        self.source_services = {
            "pubmed": self.pubmed_service,
            "who": self.who_service,
            "nih": self.nih_service,
            "medlineplus": self.medlineplus_service,
            "italian_official": self.italian_sources_service
        }
    
    async def start_research_job(
        self,
        llm_analysis_id: UUID,
        config: ResearchConfig,
        priority: str = "normal"
    ) -> ResearchJob:
        """
        Inicia un trabajo de investigación médica completo.
        
        Args:
            llm_analysis_id: ID del análisis LLM completado
            config: Configuración de investigación
            priority: Prioridad del trabajo
            
        Returns:
            Trabajo de investigación creado
        """
        logger.info(f"Iniciando research job para LLM analysis {llm_analysis_id}")
        
        # Verificar que el análisis LLM existe
        llm_analysis = self.db.query(LLMAnalysisResult).filter(
            LLMAnalysisResult.id == llm_analysis_id
        ).first()
        
        if not llm_analysis:
            raise ValueError(f"LLM analysis {llm_analysis_id} no encontrado")
        
        # Crear trabajo de investigación
        research_job = ResearchJob(
            llm_analysis_id=llm_analysis_id,
            research_preset=config.preset,
            priority=priority,
            language_preference=config.language,
            enabled_sources=config.enabled_sources,
            max_sources_per_term=config.max_sources_per_term,
            include_related_terms=config.include_related_terms,
            enable_translation=config.enable_translation,
            peer_review_only=getattr(config, 'peer_review_only', False),
            clinical_guidelines_priority=getattr(config, 'clinical_guidelines_priority', False),
            italian_priority=getattr(config, 'italian_priority', False),
            research_config=config.to_dict()
        )
        
        self.db.add(research_job)
        self.db.commit()
        self.db.refresh(research_job)
        
        logger.info(f"Research job {research_job.id} creado exitosamente")
        return research_job
    
    async def extract_medical_terms(self, llm_analysis_id: UUID) -> List[str]:
        """
        Extrae términos médicos del análisis LLM para investigación.
        
        Args:
            llm_analysis_id: ID del análisis LLM
            
        Returns:
            Lista de términos médicos únicos
        """
        logger.info(f"Extrayendo términos médicos de LLM analysis {llm_analysis_id}")
        
        # Obtener análisis LLM
        llm_analysis = self.db.query(LLMAnalysisResult).filter(
            LLMAnalysisResult.id == llm_analysis_id
        ).first()
        
        if not llm_analysis:
            raise ValueError(f"LLM analysis {llm_analysis_id} no encontrado")
        
        terms = set()
        
        # Extraer de conceptos clave
        if llm_analysis.conceptos_clave:
            for concepto in llm_analysis.conceptos_clave:
                if isinstance(concepto, dict) and 'termino' in concepto:
                    terms.add(concepto['termino'].lower().strip())
                elif isinstance(concepto, str):
                    terms.add(concepto.lower().strip())
        
        # Extraer de terminología médica
        if llm_analysis.terminologia_medica:
            for termino in llm_analysis.terminologia_medica:
                if isinstance(termino, dict):
                    if 'termino' in termino:
                        terms.add(termino['termino'].lower().strip())
                    if 'termino_it' in termino:
                        terms.add(termino['termino_it'].lower().strip())
                elif isinstance(termino, str):
                    terms.add(termino.lower().strip())
        
        # Obtener también del post-processing si existe
        post_processing = self.db.query(PostProcessingResult).filter(
            PostProcessingResult.processing_job_id == llm_analysis.processing_job_id
        ).first()
        
        if post_processing and post_processing.medical_entities:
            for entity in post_processing.medical_entities:
                if isinstance(entity, dict) and 'text' in entity:
                    terms.add(entity['text'].lower().strip())
        
        # Filtrar términos muy cortos o comunes
        filtered_terms = [
            term for term in terms 
            if len(term) > 3 and not self._is_common_word(term)
        ]
        
        logger.info(f"Extraídos {len(filtered_terms)} términos médicos únicos")
        return sorted(filtered_terms)
    
    async def check_cache(
        self, 
        terms: List[str], 
        config: ResearchConfig
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Verifica qué términos están en cache y cuáles necesitan investigación.
        
        Args:
            terms: Lista de términos médicos
            config: Configuración de investigación
            
        Returns:
            Tupla con (resultados_cache, términos_nuevos)
        """
        logger.info(f"Verificando cache para {len(terms)} términos")
        
        cached_results = []
        new_terms = []
        
        config_key_data = config.get_cache_key_data()
        
        for term in terms:
            # Generar clave de cache
            cache_key = SourceCache.generate_cache_key(term, {"config": config_key_data})
            
            # Buscar en cache
            cached = self.db.query(SourceCache).filter(
                SourceCache.cache_key == cache_key,
                SourceCache.is_valid == True,
                SourceCache.expires_at > datetime.utcnow()
            ).first()
            
            if cached:
                # Registrar acceso al cache
                try:
                    results = cached.access_cache()
                    cached_results.append({
                        "term": term,
                        "results": results,
                        "from_cache": True,
                        "cache_age_hours": cached.age_in_hours
                    })
                    logger.debug(f"Cache hit para término '{term}'")
                except ValueError:
                    # Cache expirado o inválido
                    new_terms.append(term)
                    logger.debug(f"Cache inválido para término '{term}'")
            else:
                new_terms.append(term)
                logger.debug(f"Cache miss para término '{term}'")
        
        logger.info(f"Cache: {len(cached_results)} hits, {len(new_terms)} misses")
        return cached_results, new_terms
    
    async def research_term(
        self, 
        term: str, 
        config: ResearchConfig,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Investiga un término médico específico en todas las fuentes configuradas.
        
        Args:
            term: Término médico a investigar
            config: Configuración de investigación
            context: Contexto opcional del término
            
        Returns:
            Resultado de investigación completo
        """
        logger.info(f"Investigando término médico: '{term}'")
        
        start_time = datetime.utcnow()
        all_sources = []
        search_errors = []
        
        # Buscar en cada fuente habilitada
        for source_type in config.enabled_sources:
            if source_type not in self.source_services:
                logger.warning(f"Servicio de fuente '{source_type}' no disponible")
                continue
            
            try:
                service = self.source_services[source_type]
                sources = await service.search_term(
                    term=term,
                    max_results=config.max_sources_per_term,
                    language=config.language,
                    context=context
                )
                
                # Añadir metadatos de fuente
                for source in sources:
                    source['source_type'] = source_type
                    source['search_term'] = term
                    source['search_timestamp'] = datetime.utcnow().isoformat()
                
                all_sources.extend(sources)
                logger.debug(f"Encontradas {len(sources)} fuentes en {source_type}")
                
            except Exception as e:
                error_msg = f"Error buscando en {source_type}: {str(e)}"
                logger.error(error_msg)
                search_errors.append({
                    "source_type": source_type,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        # Validar y rankear fuentes
        if all_sources:
            validated_sources = await self.content_validator.validate_sources(
                all_sources, term, context
            )
            
            # Ordenar por score combinado
            validated_sources.sort(
                key=lambda s: s.get('overall_score', 0.0), 
                reverse=True
            )
            
            # Limitar al número máximo configurado
            final_sources = validated_sources[:config.max_sources_per_term * 2]  # Margen extra
        else:
            final_sources = []
        
        # Calcular métricas
        search_duration = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        result = {
            "term": term,
            "normalized_term": term.lower().strip(),
            "sources": final_sources,
            "sources_count": len(final_sources),
            "search_duration_ms": int(search_duration),
            "sources_consulted": len(config.enabled_sources),
            "sources_with_results": len([s for s in config.enabled_sources if s not in [e['source_type'] for e in search_errors]]),
            "search_errors": search_errors,
            "config_used": config.to_dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Guardar en cache si hay resultados válidos
        if final_sources and len(search_errors) < len(config.enabled_sources):
            await self._save_to_cache(term, config, result)
        
        logger.info(f"Research completado para '{term}': {len(final_sources)} fuentes en {search_duration:.0f}ms")
        return result
    
    async def research_multiple_terms(
        self,
        terms: List[str],
        config: ResearchConfig,
        progress_callback: Optional[callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Investiga múltiples términos médicos de forma concurrente.
        
        Args:
            terms: Lista de términos médicos
            config: Configuración de investigación
            progress_callback: Callback opcional para reportar progreso
            
        Returns:
            Lista de resultados de investigación
        """
        logger.info(f"Iniciando research de {len(terms)} términos")
        
        results = []
        
        # Procesar términos en lotes para evitar sobrecarga
        batch_size = 5
        for i in range(0, len(terms), batch_size):
            batch = terms[i:i + batch_size]
            
            # Procesar lote concurrentemente
            batch_tasks = [
                self.research_term(term, config) 
                for term in batch
            ]
            
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            # Procesar resultados del lote
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Error investigando término '{batch[j]}': {result}")
                    # Crear resultado de error
                    error_result = {
                        "term": batch[j],
                        "sources": [],
                        "sources_count": 0,
                        "error": str(result),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    results.append(error_result)
                else:
                    results.append(result)
            
            # Reportar progreso
            if progress_callback:
                progress = ((i + len(batch)) / len(terms)) * 100
                progress_callback(progress, f"Procesados {i + len(batch)}/{len(terms)} términos")
        
        logger.info(f"Research completado para {len(terms)} términos")
        return results
    
    async def save_research_results(
        self,
        research_job_id: UUID,
        research_results: List[Dict[str, Any]]
    ) -> List[ResearchResult]:
        """
        Guarda los resultados de investigación en la base de datos.
        
        Args:
            research_job_id: ID del trabajo de investigación
            research_results: Lista de resultados de investigación
            
        Returns:
            Lista de objetos ResearchResult creados
        """
        logger.info(f"Guardando {len(research_results)} resultados de research")
        
        saved_results = []
        
        for result_data in research_results:
            try:
                # Crear resultado de investigación
                research_result = ResearchResult(
                    research_job_id=research_job_id,
                    medical_term=result_data['term'],
                    normalized_term=result_data.get('normalized_term', result_data['term'].lower()),
                    sources_consulted=result_data.get('sources_consulted', 0),
                    sources_with_results=result_data.get('sources_with_results', 0),
                    search_duration_ms=result_data.get('search_duration_ms', 0),
                    cache_hit=result_data.get('from_cache', False),
                    research_config=result_data.get('config_used', {})
                )
                
                # Extraer mejor definición si hay fuentes
                sources = result_data.get('sources', [])
                if sources:
                    best_source = max(sources, key=lambda s: s.get('overall_score', 0.0))
                    research_result.primary_definition = best_source.get('abstract') or best_source.get('relevant_excerpt')
                    research_result.primary_source_type = best_source.get('source_type')
                
                self.db.add(research_result)
                self.db.flush()  # Para obtener el ID
                
                # Crear fuentes médicas
                for source_data in sources:
                    medical_source = MedicalSource(
                        research_result_id=research_result.id,
                        title=source_data.get('title', ''),
                        url=source_data.get('url', ''),
                        source_type=source_data.get('source_type', 'unknown'),
                        domain=source_data.get('domain'),
                        language=source_data.get('language', 'en'),
                        authors=source_data.get('authors'),
                        publication_date=source_data.get('publication_date'),
                        journal_name=source_data.get('journal_name'),
                        doi=source_data.get('doi'),
                        pmid=source_data.get('pmid'),
                        abstract=source_data.get('abstract'),
                        relevant_excerpt=source_data.get('relevant_excerpt'),
                        keywords=source_data.get('keywords'),
                        content_category=source_data.get('content_category'),
                        target_audience=source_data.get('target_audience', 'professional'),
                        relevance_score=source_data.get('relevance_score', 0.0),
                        authority_score=source_data.get('authority_score', 0.0),
                        recency_score=source_data.get('recency_score', 0.0),
                        overall_score=source_data.get('overall_score', 0.0),
                        access_type=source_data.get('access_type', 'free'),
                        peer_reviewed=source_data.get('peer_reviewed', False),
                        official_source=source_data.get('official_source', False),
                        extraction_method=source_data.get('extraction_method', 'api')
                    )
                    
                    self.db.add(medical_source)
                
                # Actualizar métricas del resultado
                research_result.update_quality_metrics()
                saved_results.append(research_result)
                
            except Exception as e:
                logger.error(f"Error guardando resultado para término '{result_data.get('term', 'unknown')}': {e}")
                continue
        
        self.db.commit()
        logger.info(f"Guardados {len(saved_results)} resultados exitosamente")
        return saved_results
    
    async def _save_to_cache(
        self, 
        term: str, 
        config: ResearchConfig, 
        result: Dict[str, Any]
    ) -> None:
        """
        Guarda un resultado de investigación en el cache.
        
        Args:
            term: Término médico
            config: Configuración utilizada
            result: Resultado de investigación
        """
        try:
            config_key_data = config.get_cache_key_data()
            cache_key = SourceCache.generate_cache_key(term, {"config": config_key_data})
            
            # Determinar TTL basado en tipos de fuentes
            source_types = [s.get('source_type') for s in result.get('sources', [])]
            ttl_hours = SourceCache.calculate_ttl_hours('general', source_types)
            
            # Crear entrada de cache
            cache_entry = SourceCache(
                cache_key=cache_key,
                medical_term=term,
                normalized_term=result.get('normalized_term', term.lower()),
                search_config_hash=hashlib.md5(config_key_data.encode()).hexdigest(),
                cached_results=result,
                sources_count=result.get('sources_count', 0),
                language=config.language,
                source_types=config.enabled_sources,
                research_preset=config.preset,
                search_configuration=config.to_dict(),
                expires_at=datetime.utcnow() + timedelta(hours=ttl_hours),
                original_ttl_hours=ttl_hours,
                generation_time_ms=result.get('search_duration_ms', 0),
                sources_consulted=result.get('sources_consulted', 0)
            )
            
            # Actualizar métricas de calidad
            if result.get('sources'):
                cache_entry.update_quality_metrics(result['sources'])
            
            self.db.add(cache_entry)
            self.db.commit()
            
            logger.debug(f"Resultado cacheado para término '{term}' con TTL de {ttl_hours}h")
            
        except Exception as e:
            logger.error(f"Error guardando en cache término '{term}': {e}")
    
    def _is_common_word(self, word: str) -> bool:
        """
        Determina si una palabra es demasiado común para investigar.
        
        Args:
            word: Palabra a evaluar
            
        Returns:
            True si es una palabra común
        """
        common_words = {
            # Palabras comunes en italiano
            'che', 'con', 'per', 'una', 'del', 'della', 'delle', 'dei', 'degli',
            'nel', 'nella', 'nelle', 'nei', 'negli', 'sul', 'sulla', 'sulle',
            'sui', 'sugli', 'dal', 'dalla', 'dalle', 'dai', 'dagli',
            'questo', 'questa', 'questi', 'queste', 'quello', 'quella',
            'molto', 'più', 'anche', 'come', 'quando', 'dove', 'perché',
            
            # Palabras comunes en español
            'que', 'con', 'por', 'para', 'una', 'del', 'de', 'la', 'las',
            'el', 'los', 'en', 'al', 'del', 'este', 'esta', 'estos', 'estas',
            'ese', 'esa', 'esos', 'esas', 'muy', 'más', 'también', 'como',
            'cuando', 'donde', 'porque',
            
            # Palabras comunes en inglés
            'the', 'and', 'for', 'with', 'that', 'this', 'these', 'those',
            'very', 'more', 'also', 'how', 'when', 'where', 'why', 'what'
        }
        
        return word.lower() in common_words
    
    async def get_research_statistics(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas generales del sistema de investigación.
        
        Returns:
            Diccionario con estadísticas del sistema
        """
        # Estadísticas de trabajos
        total_jobs = self.db.query(ResearchJob).count()
        completed_jobs = self.db.query(ResearchJob).filter(
            ResearchJob.status == "completed"
        ).count()
        
        # Estadísticas de resultados
        total_results = self.db.query(ResearchResult).count()
        total_sources = self.db.query(MedicalSource).count()
        
        # Estadísticas de cache
        cache_stats = SourceCache.get_cache_statistics(self.db)
        
        # Métricas de calidad promedio
        avg_confidence = self.db.query(
            self.db.func.avg(ResearchResult.confidence_score)
        ).scalar() or 0.0
        
        avg_relevance = self.db.query(
            self.db.func.avg(MedicalSource.relevance_score)
        ).scalar() or 0.0
        
        return {
            "research_jobs": {
                "total": total_jobs,
                "completed": completed_jobs,
                "success_rate": completed_jobs / max(1, total_jobs)
            },
            "research_results": {
                "total_terms_researched": total_results,
                "total_sources_found": total_sources,
                "average_sources_per_term": total_sources / max(1, total_results),
                "average_confidence_score": avg_confidence,
                "average_relevance_score": avg_relevance
            },
            "cache_performance": cache_stats,
            "system_health": {
                "services_available": len(self.source_services),
                "cache_enabled": settings.RESEARCH_CACHE_ENABLED,
                "last_updated": datetime.utcnow().isoformat()
            }
        }
