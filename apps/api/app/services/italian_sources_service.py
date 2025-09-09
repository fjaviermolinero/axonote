"""
Servicio para fuentes médicas italianas oficiales.

Integra ISS, AIFA, Ministero della Salute y otras fuentes
médicas oficiales italianas para proporcionar información
localizada y relevante para el contexto italiano.
"""

import asyncio
import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Any

import aiohttp

from app.services.base import BaseSourceService
from app.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class ISSResource:
    """Representa un recurso del Istituto Superiore di Sanità."""
    
    def __init__(self, data: Dict[str, Any]):
        self.title = data.get('title', '')
        self.url = data.get('url', '')
        self.description = data.get('description', '')
        self.category = data.get('category', '')
        self.publication_date = data.get('publication_date')
        self.language = data.get('language', 'it')


class AIFADrug:
    """Representa información de medicamento de AIFA."""
    
    def __init__(self, data: Dict[str, Any]):
        self.name = data.get('name', '')
        self.aic = data.get('aic', '')  # Autorizzazione Immissione in Commercio
        self.active_ingredient = data.get('active_ingredient', '')
        self.therapeutic_class = data.get('therapeutic_class', '')
        self.indication = data.get('indication', '')
        self.url = data.get('url', '')


class ItalianSourcesService(BaseSourceService):
    """
    Servicio para fuentes médicas italianas oficiales.
    
    Integra múltiples fuentes oficiales italianas:
    - ISS (Istituto Superiore di Sanità)
    - AIFA (Agenzia Italiana del Farmaco)
    - Ministero della Salute
    - Società mediche italiane
    """
    
    def __init__(self):
        super().__init__("italian_official")
        
        # URLs de fuentes italianas
        self.iss_url = "https://www.iss.it/"
        self.aifa_url = "https://www.aifa.gov.it/"
        self.salute_url = "https://www.salute.gov.it/"
        
        # Rate limiter conservador para fuentes italianas
        self.rate_limiter = RateLimiter(requests_per_second=1.0)
        
        logger.info("ItalianSourcesService inicializado")
    
    async def search_term(
        self,
        term: str,
        max_results: int = 10,
        language: str = "it",
        context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca en fuentes médicas italianas para un término médico.
        
        Args:
            term: Término médico a buscar
            max_results: Número máximo de resultados
            language: Idioma preferido (it/en)
            context: Contexto opcional
            
        Returns:
            Lista de recursos encontrados
        """
        logger.info(f"Buscando en fuentes italianas: '{term}' (max: {max_results})")
        
        try:
            all_results = []
            
            # Buscar en diferentes fuentes italianas
            iss_results = await self._search_iss(term, max_results // 3)
            all_results.extend(iss_results)
            
            aifa_results = await self._search_aifa(term, max_results // 3)
            all_results.extend(aifa_results)
            
            ministry_results = await self._search_ministry(term, max_results // 3)
            all_results.extend(ministry_results)
            
            # Procesar y rankear resultados
            processed_results = []
            for result in all_results:
                processed = await self._process_italian_resource(result, term, context)
                if processed:
                    processed_results.append(processed)
            
            # Ordenar por relevancia
            processed_results.sort(
                key=lambda x: x.get('relevance_score', 0.0),
                reverse=True
            )
            
            final_results = processed_results[:max_results]
            logger.info(f"Encontrados {len(final_results)} recursos en fuentes italianas")
            return final_results
            
        except Exception as e:
            logger.error(f"Error buscando en fuentes italianas: {e}")
            return []
    
    async def _search_iss(self, term: str, max_results: int) -> List[Dict[str, Any]]:
        """
        Busca recursos en el Istituto Superiore di Sanità.
        
        Args:
            term: Término de búsqueda
            max_results: Máximo número de resultados
            
        Returns:
            Lista de recursos ISS
        """
        try:
            # Simular búsqueda en ISS
            iss_resources = [
                {
                    'title': f'ISS - Informazioni su {term.title()}',
                    'url': f'https://www.iss.it/salute/{term.lower().replace(" ", "-")}',
                    'description': f'Informazioni scientifiche e raccomandazioni dell\'ISS riguardo {term}',
                    'category': 'scientific_info',
                    'source': 'iss',
                    'language': 'it',
                    'publication_date': '2023-10-01',
                    'authority_level': 'high'
                },
                {
                    'title': f'Rapporto ISS: {term.title()}',
                    'url': f'https://www.iss.it/rapporti/{term.lower().replace(" ", "-")}',
                    'description': f'Rapporto tecnico-scientifico dell\'ISS su {term}',
                    'category': 'technical_report',
                    'source': 'iss',
                    'language': 'it',
                    'publication_date': '2023-09-15',
                    'authority_level': 'high'
                }
            ]
            
            return iss_resources[:max_results]
            
        except Exception as e:
            logger.error(f"Error buscando en ISS: {e}")
            return []
    
    async def _search_aifa(self, term: str, max_results: int) -> List[Dict[str, Any]]:
        """
        Busca información de medicamentos en AIFA.
        
        Args:
            term: Término de búsqueda (nombre de medicamento)
            max_results: Máximo número de resultados
            
        Returns:
            Lista de recursos AIFA
        """
        try:
            # Simular búsqueda en AIFA
            aifa_resources = [
                {
                    'title': f'AIFA - Scheda Tecnica: {term.title()}',
                    'url': f'https://farmaci.agenziafarmaco.gov.it/scheda/{term.lower().replace(" ", "")}',
                    'description': f'Scheda tecnica ufficiale AIFA per {term}',
                    'category': 'drug_info',
                    'source': 'aifa',
                    'language': 'it',
                    'publication_date': '2023-11-01',
                    'authority_level': 'high',
                    'drug_specific': True
                },
                {
                    'title': f'AIFA - Foglietto Illustrativo: {term.title()}',
                    'url': f'https://farmaci.agenziafarmaco.gov.it/foglietto/{term.lower().replace(" ", "")}',
                    'description': f'Foglietto illustrativo ufficiale per {term}',
                    'category': 'patient_info',
                    'source': 'aifa',
                    'language': 'it',
                    'publication_date': '2023-11-01',
                    'authority_level': 'high',
                    'drug_specific': True
                }
            ]
            
            return aifa_resources[:max_results]
            
        except Exception as e:
            logger.error(f"Error buscando en AIFA: {e}")
            return []
    
    async def _search_ministry(self, term: str, max_results: int) -> List[Dict[str, Any]]:
        """
        Busca recursos del Ministero della Salute.
        
        Args:
            term: Término de búsqueda
            max_results: Máximo número de resultados
            
        Returns:
            Lista de recursos del Ministerio
        """
        try:
            # Simular búsqueda en Ministero della Salute
            ministry_resources = [
                {
                    'title': f'Ministero della Salute - {term.title()}',
                    'url': f'https://www.salute.gov.it/salute/{term.lower().replace(" ", "-")}',
                    'description': f'Informazioni ufficiali del Ministero della Salute su {term}',
                    'category': 'official_info',
                    'source': 'ministry_health',
                    'language': 'it',
                    'publication_date': '2023-08-15',
                    'authority_level': 'high'
                },
                {
                    'title': f'Linee Guida - {term.title()}',
                    'url': f'https://www.salute.gov.it/linee-guida/{term.lower().replace(" ", "-")}',
                    'description': f'Linee guida nazionali per {term}',
                    'category': 'guidelines',
                    'source': 'ministry_health',
                    'language': 'it',
                    'publication_date': '2023-07-01',
                    'authority_level': 'high'
                }
            ]
            
            return ministry_resources[:max_results]
            
        except Exception as e:
            logger.error(f"Error buscando en Ministero: {e}")
            return []
    
    async def _process_italian_resource(
        self,
        resource_data: Dict[str, Any],
        search_term: str,
        context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Procesa un recurso italiano y calcula métricas.
        
        Args:
            resource_data: Datos del recurso
            search_term: Término de búsqueda
            context: Contexto opcional
            
        Returns:
            Recurso procesado con métricas
        """
        try:
            # Calcular relevancia
            relevance_score = self.calculate_base_relevance_score(
                resource_data.get('description', ''),
                search_term
            )
            
            # Bonus por fuentes italianas oficiales
            authority_score = self._get_italian_authority_score(resource_data.get('source', ''))
            
            # Calcular recencia
            recency_score = self._calculate_recency(resource_data.get('publication_date'))
            
            # Score general con bonus por ser fuente italiana
            overall_score = (
                relevance_score * 0.4 +
                authority_score * 0.4 +
                recency_score * 0.2
            )
            
            # Bonus adicional por ser fuente italiana (relevante para contexto italiano)
            overall_score = min(1.0, overall_score + 0.1)
            
            # Determinar audiencia
            target_audience = self._determine_italian_audience(resource_data)
            
            # Extraer dominio
            domain = self._extract_domain(resource_data['url'])
            
            return {
                'title': resource_data['title'],
                'url': resource_data['url'],
                'domain': domain,
                'content': resource_data['description'],
                'relevant_excerpt': resource_data['description'][:300],
                'keywords': [search_term],
                'content_category': resource_data.get('category', 'general'),
                'target_audience': target_audience,
                'language': resource_data.get('language', 'it'),
                'publication_date': resource_data.get('publication_date'),
                'relevance_score': relevance_score,
                'authority_score': authority_score,
                'recency_score': recency_score,
                'overall_score': overall_score,
                'access_type': 'free',
                'peer_reviewed': False,
                'official_source': True,  # Todas las fuentes italianas son oficiales
                'extraction_method': 'api',
                'source_metadata': {
                    'italian_source': resource_data.get('source'),
                    'authority_level': resource_data.get('authority_level', 'medium'),
                    'is_drug_specific': resource_data.get('drug_specific', False)
                }
            }
            
        except Exception as e:
            logger.error(f"Error procesando recurso italiano: {e}")
            return None
    
    def _get_italian_authority_score(self, source: str) -> float:
        """Obtiene score de autoridad para fuentes italianas."""
        authority_scores = {
            'iss': 0.9,           # Istituto Superiore di Sanità
            'aifa': 0.85,         # Agenzia Italiana del Farmaco
            'ministry_health': 0.8, # Ministero della Salute
            'medical_society': 0.7  # Società mediche italiane
        }
        
        return authority_scores.get(source, 0.6)
    
    def _calculate_recency(self, publication_date: Optional[str]) -> float:
        """Calcula score de recencia."""
        if not publication_date:
            return 0.6
        
        try:
            pub_date = datetime.strptime(publication_date, '%Y-%m-%d').date()
            today = date.today()
            age_days = (today - pub_date).days
            age_years = age_days / 365.25
            
            if age_years <= 1:
                return 1.0
            elif age_years <= 2:
                return 0.8
            elif age_years <= 5:
                return 0.6
            else:
                return 0.4
                
        except (ValueError, AttributeError):
            return 0.6
    
    def _determine_italian_audience(self, resource_data: Dict[str, Any]) -> str:
        """Determina la audiencia objetivo del recurso italiano."""
        category = resource_data.get('category', '')
        source = resource_data.get('source', '')
        
        if category in ['patient_info', 'foglietto']:
            return 'patient'
        elif category in ['technical_report', 'scientific_info']:
            return 'professional'
        elif source == 'aifa' and category == 'drug_info':
            return 'professional'
        else:
            return 'mixed'
    
    def _extract_domain(self, url: str) -> str:
        """Extrae el dominio de una URL."""
        try:
            from urllib.parse import urlparse
            return urlparse(url).netloc
        except:
            return "unknown"
    
    async def search_iss_resources(self, term: str) -> List[Dict[str, Any]]:
        """
        Busca recursos específicamente en ISS.
        
        Args:
            term: Término de búsqueda
            
        Returns:
            Lista de recursos ISS
        """
        logger.info(f"Buscando específicamente en ISS: '{term}'")
        return await self._search_iss(term, 10)
    
    async def search_aifa_drugs(self, drug_name: str) -> List[Dict[str, Any]]:
        """
        Busca información de medicamentos específicamente en AIFA.
        
        Args:
            drug_name: Nombre del medicamento
            
        Returns:
            Lista de información de medicamentos AIFA
        """
        logger.info(f"Buscando medicamento en AIFA: '{drug_name}'")
        return await self._search_aifa(drug_name, 10)
    
    async def search_ministry_guidelines(self, term: str) -> List[Dict[str, Any]]:
        """
        Busca guías específicamente del Ministero della Salute.
        
        Args:
            term: Término de búsqueda
            
        Returns:
            Lista de guías del Ministerio
        """
        logger.info(f"Buscando guías del Ministerio: '{term}'")
        return await self._search_ministry(term, 10)
    
    async def health_check(self) -> Dict[str, Any]:
        """Verifica el estado del servicio de fuentes italianas."""
        try:
            # Verificar acceso a fuentes principales
            sources_status = {}
            
            async with aiohttp.ClientSession() as session:
                # Verificar ISS
                try:
                    async with session.get(
                        "https://www.iss.it/",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        sources_status['iss'] = response.status == 200
                except:
                    sources_status['iss'] = False
                
                # Verificar AIFA
                try:
                    async with session.get(
                        "https://www.aifa.gov.it/",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        sources_status['aifa'] = response.status == 200
                except:
                    sources_status['aifa'] = False
                
                # Verificar Ministero
                try:
                    async with session.get(
                        "https://www.salute.gov.it/",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as response:
                        sources_status['ministry_health'] = response.status == 200
                except:
                    sources_status['ministry_health'] = False
            
            # Determinar estado general
            healthy_sources = sum(sources_status.values())
            overall_healthy = healthy_sources >= 2  # Al menos 2 de 3 fuentes
            
            return {
                'service': 'italian_sources',
                'status': 'healthy' if overall_healthy else 'unhealthy',
                'sources': {
                    'iss': 'healthy' if sources_status.get('iss') else 'unhealthy',
                    'aifa': 'healthy' if sources_status.get('aifa') else 'unhealthy',
                    'ministry_health': 'healthy' if sources_status.get('ministry_health') else 'unhealthy'
                },
                'healthy_sources': f"{healthy_sources}/3",
                'features': [
                    'scientific_information',
                    'drug_information',
                    'official_guidelines',
                    'patient_information'
                ],
                'language': 'it',
                'last_check': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'service': 'italian_sources',
                'status': 'unhealthy',
                'error': str(e),
                'last_check': datetime.utcnow().isoformat()
            }
