"""
Tareas Celery para investigación médica automática.

Implementa el pipeline completo de research automático incluyendo
extracción de términos, búsqueda en fuentes, validación y
almacenamiento de resultados.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import UUID

from celery import current_task
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import ResearchJob, LLMAnalysisResult
from app.services.research_service import ResearchService, ResearchConfig
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="research.start_medical_research")
def start_medical_research_task(
    self,
    llm_analysis_id: str,
    research_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Tarea principal de investigación médica automática.
    
    Etapas del pipeline:
    1. Extraer términos médicos del análisis LLM (10%)
    2. Configurar fuentes y parámetros (15%)
    3. Verificar cache existente (25%)
    4. Investigar términos nuevos (70%)
    5. Validar y rankear resultados (85%)
    6. Guardar en base de datos (95%)
    7. Generar métricas finales (100%)
    
    Args:
        llm_analysis_id: ID del análisis LLM completado
        research_config: Configuración de investigación
        
    Returns:
        Resultado del proceso de investigación
    """
    try:
        logger.info(f"Iniciando research médico para LLM analysis {llm_analysis_id}")
        
        # Obtener sesión de BD
        db = next(get_db())
        
        # Crear servicio de research
        research_service = ResearchService(db)
        config = ResearchConfig(**research_config)
        
        # 1. Extraer términos médicos (10%)
        self.update_state(
            state="PROGRESS",
            meta={
                "current_step": "Extrayendo términos médicos del análisis LLM",
                "progress": 10,
                "stage": "term_extraction",
                "llm_analysis_id": llm_analysis_id
            }
        )
        
        # Ejecutar extracción de términos de forma asíncrona
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            terms = loop.run_until_complete(
                research_service.extract_medical_terms(UUID(llm_analysis_id))
            )
        finally:
            loop.close()
        
        if not terms:
            return {
                "status": "completed",
                "message": "No se encontraron términos médicos para investigar",
                "terms_found": 0
            }
        
        # 2. Configurar búsqueda (15%)
        self.update_state(
            state="PROGRESS",
            meta={
                "current_step": "Configurando fuentes de búsqueda",
                "progress": 15,
                "stage": "configuration",
                "total_terms": len(terms),
                "terms_preview": terms[:5]  # Primeros 5 términos
            }
        )
        
        # Crear trabajo de investigación
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            research_job = loop.run_until_complete(
                research_service.start_research_job(
                    llm_analysis_id=UUID(llm_analysis_id),
                    config=config,
                    priority=research_config.get('priority', 'normal')
                )
            )
            
            # Actualizar job con ID de tarea Celery
            research_job.celery_task_id = self.request.id
            research_job.started_at = datetime.utcnow()
            research_job.total_terms = len(terms)
            research_job.status = "researching"
            db.commit()
            
        finally:
            loop.close()
        
        # 3. Verificar cache (25%)
        self.update_state(
            state="PROGRESS",
            meta={
                "current_step": "Verificando cache de búsquedas anteriores",
                "progress": 25,
                "stage": "cache_check",
                "research_job_id": str(research_job.id)
            }
        )
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            cached_results, new_terms = loop.run_until_complete(
                research_service.check_cache(terms, config)
            )
        finally:
            loop.close()
        
        # Actualizar estadísticas de cache
        research_job.cache_hits = len(cached_results)
        research_job.cache_misses = len(new_terms)
        research_job.terms_from_cache = len(cached_results)
        db.commit()
        
        # 4. Investigar términos nuevos (25% - 70%)
        all_research_results = cached_results.copy()
        
        if new_terms:
            for i, term in enumerate(new_terms):
                # Calcular progreso (25% a 70%)
                progress = 25 + (45 * (i + 1) / len(new_terms))
                
                self.update_state(
                    state="PROGRESS",
                    meta={
                        "current_step": f"Investigando término: {term}",
                        "progress": progress,
                        "stage": "research",
                        "current_term": term,
                        "terms_completed": i,
                        "terms_total": len(new_terms),
                        "cache_hits": len(cached_results)
                    }
                )
                
                # Investigar término individual
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    result = loop.run_until_complete(
                        research_service.research_term(term, config)
                    )
                    all_research_results.append(result)
                    
                    # Actualizar progreso en BD
                    research_job.terms_researched = i + 1
                    research_job.sources_found += result.get('sources_count', 0)
                    research_job.current_term = term
                    research_job.progress_percentage = progress
                    db.commit()
                    
                except Exception as e:
                    logger.error(f"Error investigando término '{term}': {e}")
                    # Crear resultado de error
                    error_result = {
                        "term": term,
                        "sources": [],
                        "sources_count": 0,
                        "error": str(e),
                        "from_cache": False
                    }
                    all_research_results.append(error_result)
                    
                finally:
                    loop.close()
        
        # 5. Validar y rankear resultados (85%)
        self.update_state(
            state="PROGRESS",
            meta={
                "current_step": "Validando y rankeando fuentes encontradas",
                "progress": 85,
                "stage": "validation",
                "total_results": len(all_research_results),
                "total_sources": sum(r.get('sources_count', 0) for r in all_research_results)
            }
        )
        
        # Calcular métricas de calidad
        total_sources = sum(r.get('sources_count', 0) for r in all_research_results)
        successful_terms = len([r for r in all_research_results if r.get('sources_count', 0) > 0])
        
        # 6. Guardar en base de datos (95%)
        self.update_state(
            state="PROGRESS",
            meta={
                "current_step": "Guardando resultados en base de datos",
                "progress": 95,
                "stage": "saving",
                "successful_terms": successful_terms,
                "total_sources_found": total_sources
            }
        )
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            saved_results = loop.run_until_complete(
                research_service.save_research_results(
                    research_job.id,
                    all_research_results
                )
            )
        finally:
            loop.close()
        
        # 7. Métricas finales y completion (100%)
        research_job.mark_completed(success=True)
        research_job.sources_found = total_sources
        research_job.sources_validated = len(saved_results)
        research_job.terms_researched = len(terms)
        
        # Calcular métricas de calidad promedio
        if saved_results:
            avg_relevance = sum(r.confidence_score for r in saved_results) / len(saved_results)
            research_job.average_relevance_score = avg_relevance
        
        db.commit()
        
        # Resultado final
        final_result = {
            "status": "completed",
            "research_job_id": str(research_job.id),
            "total_terms": len(terms),
            "terms_researched": len(all_research_results),
            "sources_found": total_sources,
            "cache_hits": len(cached_results),
            "cache_hit_rate": len(cached_results) / len(terms) if terms else 0,
            "duration_seconds": research_job.duration_seconds,
            "average_relevance": research_job.average_relevance_score,
            "successful_terms": successful_terms,
            "success_rate": successful_terms / len(terms) if terms else 0
        }
        
        logger.info(f"Research completado exitosamente: {final_result}")
        return final_result
        
    except Exception as e:
        logger.error(f"Error en research task: {str(e)}", exc_info=True)
        
        # Marcar job como fallido si existe
        try:
            db = next(get_db())
            if 'research_job' in locals():
                research_job.mark_completed(success=False, error_message=str(e))
                db.commit()
        except:
            pass
        
        # Actualizar estado de Celery
        self.update_state(
            state="FAILURE",
            meta={
                "error": str(e),
                "current_step": "Error en procesamiento de research",
                "stage": "error"
            }
        )
        
        raise


@celery_app.task(bind=True, name="research.research_single_term")
def research_single_term_task(
    self,
    term: str,
    config: Dict[str, Any],
    context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Tarea para investigar un término médico individual.
    
    Args:
        term: Término médico a investigar
        config: Configuración de investigación
        context: Contexto opcional
        
    Returns:
        Resultado de investigación del término
    """
    try:
        logger.info(f"Investigando término individual: '{term}'")
        
        # Obtener sesión de BD
        db = next(get_db())
        
        # Crear servicio y configuración
        research_service = ResearchService(db)
        research_config = ResearchConfig(**config)
        
        # Ejecutar investigación
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                research_service.research_term(term, research_config, context)
            )
        finally:
            loop.close()
        
        logger.info(f"Investigación individual completada para '{term}': {result.get('sources_count', 0)} fuentes")
        return result
        
    except Exception as e:
        logger.error(f"Error en investigación individual de '{term}': {e}")
        self.update_state(
            state="FAILURE",
            meta={
                "error": str(e),
                "term": term
            }
        )
        raise


@celery_app.task(bind=True, name="research.validate_sources")
def validate_sources_task(
    self,
    sources: List[Dict[str, Any]],
    search_term: str
) -> List[Dict[str, Any]]:
    """
    Tarea para validar un conjunto de fuentes médicas.
    
    Args:
        sources: Lista de fuentes a validar
        search_term: Término de búsqueda original
        
    Returns:
        Lista de fuentes validadas
    """
    try:
        logger.info(f"Validando {len(sources)} fuentes para término '{search_term}'")
        
        # Obtener sesión de BD
        db = next(get_db())
        
        # Crear validador
        from app.services.content_validator import ContentValidator
        validator = ContentValidator()
        
        # Ejecutar validación
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            validated_sources = loop.run_until_complete(
                validator.validate_sources(sources, search_term)
            )
        finally:
            loop.close()
        
        logger.info(f"Validación completada: {len(validated_sources)} fuentes válidas de {len(sources)} originales")
        return validated_sources
        
    except Exception as e:
        logger.error(f"Error validando fuentes: {e}")
        self.update_state(
            state="FAILURE",
            meta={
                "error": str(e),
                "sources_count": len(sources)
            }
        )
        raise


@celery_app.task(bind=True, name="research.cleanup_cache")
def cleanup_cache_task(self) -> Dict[str, Any]:
    """
    Tarea de mantenimiento para limpiar cache expirado.
    
    Returns:
        Estadísticas de limpieza
    """
    try:
        logger.info("Iniciando limpieza de cache de research")
        
        # Obtener sesión de BD
        db = next(get_db())
        
        # Crear servicio de cache
        from app.services.source_cache_service import SourceCacheService
        cache_service = SourceCacheService(db)
        
        # Ejecutar limpieza
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            cleanup_stats = loop.run_until_complete(
                cache_service.cleanup_expired_cache()
            )
        finally:
            loop.close()
        
        logger.info(f"Limpieza de cache completada: {cleanup_stats}")
        return cleanup_stats
        
    except Exception as e:
        logger.error(f"Error en limpieza de cache: {e}")
        self.update_state(
            state="FAILURE",
            meta={"error": str(e)}
        )
        raise


@celery_app.task(bind=True, name="research.optimize_cache")
def optimize_cache_task(self) -> Dict[str, Any]:
    """
    Tarea de optimización del cache de research.
    
    Returns:
        Resultados de optimización
    """
    try:
        logger.info("Iniciando optimización de cache de research")
        
        # Obtener sesión de BD
        db = next(get_db())
        
        # Crear servicio de cache
        from app.services.source_cache_service import SourceCacheService
        cache_service = SourceCacheService(db)
        
        # Ejecutar optimización
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            optimization_results = loop.run_until_complete(
                cache_service.optimize_cache()
            )
        finally:
            loop.close()
        
        logger.info(f"Optimización de cache completada: {optimization_results}")
        return optimization_results
        
    except Exception as e:
        logger.error(f"Error en optimización de cache: {e}")
        self.update_state(
            state="FAILURE",
            meta={"error": str(e)}
        )
        raise


@celery_app.task(bind=True, name="research.health_check_sources")
def health_check_sources_task(self) -> Dict[str, Any]:
    """
    Tarea para verificar el estado de todas las fuentes médicas.
    
    Returns:
        Estado de todas las fuentes
    """
    try:
        logger.info("Verificando estado de fuentes médicas")
        
        # Obtener sesión de BD
        db = next(get_db())
        
        # Crear servicios de fuentes
        from app.services.pubmed_service import PubMedService
        from app.services.who_service import WHOService
        from app.services.nih_service import NIHService
        from app.services.medlineplus_service import MedLinePlusService
        from app.services.italian_sources_service import ItalianSourcesService
        
        services = {
            'pubmed': PubMedService(),
            'who': WHOService(),
            'nih': NIHService(),
            'medlineplus': MedLinePlusService(),
            'italian_sources': ItalianSourcesService()
        }
        
        # Verificar cada servicio
        health_status = {}
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            for service_name, service in services.items():
                try:
                    status = loop.run_until_complete(service.health_check())
                    health_status[service_name] = status
                except Exception as e:
                    health_status[service_name] = {
                        'service': service_name,
                        'status': 'unhealthy',
                        'error': str(e)
                    }
        finally:
            loop.close()
        
        # Calcular estado general
        healthy_services = sum(
            1 for status in health_status.values() 
            if status.get('status') == 'healthy'
        )
        total_services = len(health_status)
        
        overall_result = {
            'overall_status': 'healthy' if healthy_services >= total_services * 0.8 else 'degraded',
            'healthy_services': healthy_services,
            'total_services': total_services,
            'health_percentage': (healthy_services / total_services) * 100,
            'services': health_status,
            'check_timestamp': datetime.utcnow().isoformat()
        }
        
        logger.info(f"Health check completado: {healthy_services}/{total_services} servicios saludables")
        return overall_result
        
    except Exception as e:
        logger.error(f"Error en health check de fuentes: {e}")
        self.update_state(
            state="FAILURE",
            meta={"error": str(e)}
        )
        raise


@celery_app.task(bind=True, name="research.update_research_job_status")
def update_research_job_status_task(
    self,
    research_job_id: str,
    status: str,
    progress: float = None,
    current_step: str = None
) -> bool:
    """
    Tarea auxiliar para actualizar el estado de un trabajo de investigación.
    
    Args:
        research_job_id: ID del trabajo de investigación
        status: Nuevo estado
        progress: Progreso en porcentaje (0-100)
        current_step: Descripción del paso actual
        
    Returns:
        True si se actualizó exitosamente
    """
    try:
        # Obtener sesión de BD
        db = next(get_db())
        
        # Buscar trabajo de investigación
        research_job = db.query(ResearchJob).filter(
            ResearchJob.id == UUID(research_job_id)
        ).first()
        
        if not research_job:
            logger.error(f"Research job {research_job_id} no encontrado")
            return False
        
        # Actualizar estado
        research_job.status = status
        if progress is not None:
            research_job.progress_percentage = progress
        if current_step is not None:
            research_job.current_step = current_step
        
        db.commit()
        
        logger.debug(f"Estado de research job {research_job_id} actualizado: {status}")
        return True
        
    except Exception as e:
        logger.error(f"Error actualizando estado de research job: {e}")
        return False
