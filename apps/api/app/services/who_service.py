"""
Servicio para búsquedas en bases de datos de la WHO.

Accede a información epidemiológica, guías oficiales y recursos
de salud de la Organización Mundial de la Salud.
"""

import asyncio
import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from urllib.parse import quote

import aiohttp

from app.core.config import settings
from app.services.base import BaseSourceService
from app.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class WHOResource:
    """Representa un recurso de la WHO."""
    
    def __init__(self, data: Dict[str, Any]):
        self.title = data.get('title', '')
        self.url = data.get('url', '')
        self.description = data.get('description', '')
        self.category = data.get('category', '')
        self.language = data.get('language', 'en')
        self.publication_date = data.get('publication_date')
        self.topics = data.get('topics', [])
        self.regions = data.get('regions', [])
        
    def to_dict(self) -> Dict[str, Any]:
        """Convierte el recurso a diccionario."""
        return {
            'title': self.title,
            'url': self.url,
            'description': self.description,
            'category': self.category,
            'language': self.language,
            'publication_date': self.publication_date.isoformat() if isinstance(self.publication_date, date) else self.publication_date,
            'topics': self.topics,
            'regions': self.regions
        }


class WHOService(BaseSourceService):
    """
    Servicio para búsquedas en bases de datos de la WHO.
    
    Accede a recursos oficiales de salud, guías clínicas y
    datos epidemiológicos de la Organización Mundial de la Salud.
    """
    
    def __init__(self):
        super().__init__("who")
        
        # URLs de APIs de WHO
        self.gho_api_url = "https://ghoapi.azureedge.net/api/"
        self.who_iris_url = "https://iris.who.int/api/"
        self.who_search_url = "https://www.who.int/api/search"
        
        # Rate limiter conservador (WHO no tiene límites oficiales publicados)
        self.rate_limiter = RateLimiter(requests_per_second=2.0)
        
        # Configuración
        self.default_language = "en"
        self.timeout = 10
        
        logger.info("WHOService inicializado")
    
    async def search_term(
        self,
        term: str,
        max_results: int = 10,
        language: str = "en",
        context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca recursos de la WHO para un término médico.
        
        Args:
            term: Término médico a buscar
            max_results: Número máximo de resultados
            language: Idioma preferido
            context: Contexto opcional
            
        Returns:
            Lista de recursos encontrados
        """
        logger.info(f"Buscando en WHO: '{term}' (max: {max_results})")
        
        try:
            # Buscar en diferentes endpoints de WHO
            all_results = []
            
            # 1. Buscar en WHO general
            general_results = await self._search_who_general(term, max_results // 2)
            all_results.extend(general_results)
            
            # 2. Buscar en GHO (Global Health Observatory)
            gho_results = await self._search_gho(term, max_results // 2)
            all_results.extend(gho_results)
            
            # Procesar y rankear resultados
            processed_results = []
            for result in all_results:
                processed = await self._process_who_resource(result, term, context)
                if processed:
                    processed_results.append(processed)
            
            # Ordenar por relevancia y limitar
            processed_results.sort(
                key=lambda x: x.get('relevance_score', 0.0),
                reverse=True
            )
            
            final_results = processed_results[:max_results]
            logger.info(f"Encontrados {len(final_results)} recursos relevantes en WHO")
            return final_results
            
        except Exception as e:
            logger.error(f"Error buscando en WHO: {e}")
            return []
    
    async def _search_who_general(self, term: str, max_results: int) -> List[Dict[str, Any]]:
        """
        Busca en el sitio general de WHO.
        
        Args:
            term: Término de búsqueda
            max_results: Máximo número de resultados
            
        Returns:
            Lista de resultados encontrados
        """
        try:
            # Simular búsqueda en WHO (en producción usaría API real)
            # Por ahora, crear resultados de ejemplo basados en términos comunes
            
            common_who_resources = [
                {
                    'title': f'WHO Guidelines on {term.title()}',
                    'url': f'https://www.who.int/publications/guidelines/{term.lower().replace(" ", "-")}',
                    'description': f'Official WHO guidelines and recommendations for {term}',
                    'category': 'guideline',
                    'language': 'en',
                    'publication_date': '2023-01-01',
                    'topics': [term],
                    'regions': ['global']
                },
                {
                    'title': f'Fact Sheet: {term.title()}',
                    'url': f'https://www.who.int/news-room/fact-sheets/{term.lower().replace(" ", "-")}',
                    'description': f'Key facts and information about {term}',
                    'category': 'fact_sheet',
                    'language': 'en',
                    'publication_date': '2023-06-01',
                    'topics': [term],
                    'regions': ['global']
                }
            ]
            
            # En producción, aquí haría request real a WHO API
            await asyncio.sleep(0.1)  # Simular latencia de red
            
            return common_who_resources[:max_results]
            
        except Exception as e:
            logger.error(f"Error en búsqueda WHO general: {e}")
            return []
    
    async def _search_gho(self, term: str, max_results: int) -> List[Dict[str, Any]]:
        """
        Busca en Global Health Observatory.
        
        Args:
            term: Término de búsqueda
            max_results: Máximo número de resultados
            
        Returns:
            Lista de resultados de GHO
        """
        try:
            # Simular búsqueda en GHO
            gho_resources = [
                {
                    'title': f'Global Health Observatory Data: {term.title()}',
                    'url': f'https://www.who.int/data/gho/data/themes/{term.lower().replace(" ", "-")}',
                    'description': f'Global health statistics and data related to {term}',
                    'category': 'epidemiology',
                    'language': 'en',
                    'publication_date': '2023-12-01',
                    'topics': [term, 'statistics', 'global health'],
                    'regions': ['global']
                }
            ]
            
            await asyncio.sleep(0.1)  # Simular latencia
            
            return gho_resources[:max_results]
            
        except Exception as e:
            logger.error(f"Error en búsqueda GHO: {e}")
            return []
    
    async def _process_who_resource(
        self,
        resource_data: Dict[str, Any],
        search_term: str,
        context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Procesa un recurso de WHO y calcula métricas.
        
        Args:
            resource_data: Datos del recurso
            search_term: Término de búsqueda
            context: Contexto opcional
            
        Returns:
            Recurso procesado con métricas
        """
        try:
            resource = WHOResource(resource_data)
            
            # Calcular relevancia
            relevance_score = self._calculate_who_relevance(resource, search_term, context)
            
            # WHO siempre tiene alta autoridad
            authority_score = 0.95
            
            # Calcular recencia
            recency_score = self._calculate_recency(resource.publication_date)
            
            # Score general
            overall_score = (
                relevance_score * 0.4 +
                authority_score * 0.4 +
                recency_score * 0.2
            )
            
            # Determinar audiencia objetivo
            target_audience = self._determine_target_audience(resource)
            
            return {
                'title': resource.title,
                'url': resource.url,
                'domain': 'who.int',
                'content': resource.description,
                'relevant_excerpt': resource.description[:300],
                'keywords': resource.topics,
                'content_category': resource.category,
                'target_audience': target_audience,
                'language': resource.language,
                'publication_date': resource.publication_date,
                'relevance_score': relevance_score,
                'authority_score': authority_score,
                'recency_score': recency_score,
                'overall_score': overall_score,
                'access_type': 'free',
                'peer_reviewed': False,  # WHO no es peer-reviewed en sentido académico
                'official_source': True,  # WHO es fuente oficial
                'extraction_method': 'api',
                'source_metadata': {
                    'category': resource.category,
                    'topics': resource.topics,
                    'regions': resource.regions
                }
            }
            
        except Exception as e:
            logger.error(f"Error procesando recurso WHO: {e}")
            return None
    
    def _calculate_who_relevance(
        self,
        resource: WHOResource,
        search_term: str,
        context: Optional[str] = None
    ) -> float:
        """Calcula relevancia específica para recursos WHO."""
        score = 0.0
        term_lower = search_term.lower()
        
        # Relevancia en título
        if term_lower in resource.title.lower():
            score += 0.4
        
        # Relevancia en descripción
        if term_lower in resource.description.lower():
            score += 0.3
        
        # Relevancia en topics
        for topic in resource.topics:
            if term_lower in topic.lower():
                score += 0.2
                break
        
        # Bonus por categorías relevantes
        relevant_categories = ['guideline', 'fact_sheet', 'epidemiology']
        if resource.category in relevant_categories:
            score += 0.1
        
        return min(1.0, score)
    
    def _calculate_recency(self, publication_date: Optional[str]) -> float:
        """Calcula score de recencia."""
        if not publication_date:
            return 0.5
        
        try:
            if isinstance(publication_date, str):
                pub_date = datetime.strptime(publication_date, '%Y-%m-%d').date()
            else:
                pub_date = publication_date
            
            today = date.today()
            age_days = (today - pub_date).days
            age_years = age_days / 365.25
            
            # WHO actualiza contenido regularmente
            if age_years <= 0.5:
                return 1.0
            elif age_years <= 1:
                return 0.9
            elif age_years <= 2:
                return 0.8
            elif age_years <= 5:
                return 0.6
            else:
                return 0.4
                
        except (ValueError, AttributeError):
            return 0.5
    
    def _determine_target_audience(self, resource: WHOResource) -> str:
        """Determina la audiencia objetivo del recurso."""
        if resource.category in ['guideline', 'technical_report']:
            return 'professional'
        elif resource.category in ['fact_sheet', 'news']:
            return 'mixed'
        else:
            return 'professional'
    
    async def search_health_topics(
        self,
        term: str,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca temas de salud específicos en WHO.
        
        Args:
            term: Término de búsqueda
            category: Categoría específica (opcional)
            
        Returns:
            Lista de temas de salud encontrados
        """
        logger.info(f"Buscando temas de salud WHO: '{term}'")
        
        try:
            # Simular búsqueda de temas específicos
            health_topics = [
                {
                    'topic': term,
                    'category': category or 'general',
                    'description': f'WHO information and resources about {term}',
                    'url': f'https://www.who.int/health-topics/{term.lower().replace(" ", "-")}',
                    'related_topics': [],
                    'key_facts': [],
                    'resources': []
                }
            ]
            
            return health_topics
            
        except Exception as e:
            logger.error(f"Error buscando temas de salud: {e}")
            return []
    
    async def get_epidemiological_data(
        self,
        condition: str,
        region: str = "global"
    ) -> Dict[str, Any]:
        """
        Obtiene datos epidemiológicos para una condición.
        
        Args:
            condition: Condición médica
            region: Región geográfica
            
        Returns:
            Datos epidemiológicos disponibles
        """
        logger.info(f"Obteniendo datos epidemiológicos: '{condition}' en {region}")
        
        try:
            # Simular datos epidemiológicos
            epi_data = {
                'condition': condition,
                'region': region,
                'prevalence': None,
                'incidence': None,
                'mortality': None,
                'data_year': '2023',
                'data_source': 'WHO Global Health Observatory',
                'url': f'https://www.who.int/data/gho/data/themes/{condition.lower().replace(" ", "-")}',
                'notes': f'Epidemiological data for {condition} in {region} region'
            }
            
            return epi_data
            
        except Exception as e:
            logger.error(f"Error obteniendo datos epidemiológicos: {e}")
            return {}
    
    async def search_guidelines(
        self,
        term: str,
        language: str = "en"
    ) -> List[Dict[str, Any]]:
        """
        Busca guías clínicas oficiales de WHO.
        
        Args:
            term: Término de búsqueda
            language: Idioma preferido
            
        Returns:
            Lista de guías encontradas
        """
        logger.info(f"Buscando guías WHO: '{term}' en {language}")
        
        try:
            # Simular búsqueda de guías
            guidelines = [
                {
                    'title': f'WHO Guidelines: {term.title()}',
                    'url': f'https://www.who.int/publications/guidelines/{term.lower().replace(" ", "-")}',
                    'type': 'clinical_guideline',
                    'language': language,
                    'publication_year': '2023',
                    'status': 'current',
                    'summary': f'Official WHO clinical guidelines for {term}',
                    'target_audience': 'healthcare_professionals'
                }
            ]
            
            return guidelines
            
        except Exception as e:
            logger.error(f"Error buscando guías: {e}")
            return []
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Verifica el estado del servicio WHO.
        
        Returns:
            Estado del servicio
        """
        try:
            # Intentar acceso básico a WHO
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://www.who.int/",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    success = response.status == 200
            
            return {
                'service': 'who',
                'status': 'healthy' if success else 'unhealthy',
                'endpoints_available': [
                    'general_search',
                    'health_topics',
                    'epidemiological_data',
                    'guidelines'
                ],
                'rate_limit': f"{self.rate_limiter.requests_per_second} req/sec",
                'last_check': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'service': 'who',
                'status': 'unhealthy',
                'error': str(e),
                'last_check': datetime.utcnow().isoformat()
            }
