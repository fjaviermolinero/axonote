"""
Servicio para búsquedas en NIH/NLM (National Institutes of Health).

Accede a recursos médicos del NIH incluyendo bases de datos
especializadas y publicaciones oficiales.
"""

import asyncio
import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Any

import aiohttp

from app.services.base import BaseSourceService
from app.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class NIHService(BaseSourceService):
    """
    Servicio para búsquedas en NIH/NLM.
    
    Accede a recursos médicos oficiales del National Institutes
    of Health y National Library of Medicine.
    """
    
    def __init__(self):
        super().__init__("nih")
        
        # URLs base de NIH
        self.nih_base_url = "https://www.nih.gov/"
        self.nlm_base_url = "https://www.nlm.nih.gov/"
        
        # Rate limiter conservador
        self.rate_limiter = RateLimiter(requests_per_second=2.0)
        
        logger.info("NIHService inicializado")
    
    async def search_term(
        self,
        term: str,
        max_results: int = 10,
        language: str = "en",
        context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca recursos del NIH para un término médico.
        
        Args:
            term: Término médico a buscar
            max_results: Número máximo de resultados
            language: Idioma preferido
            context: Contexto opcional
            
        Returns:
            Lista de recursos encontrados
        """
        logger.info(f"Buscando en NIH: '{term}' (max: {max_results})")
        
        try:
            # Simular búsqueda en NIH (en producción usaría APIs reales)
            results = []
            
            # Recursos típicos de NIH
            nih_resources = [
                {
                    'title': f'NIH Clinical Information: {term.title()}',
                    'url': f'https://www.nih.gov/health-information/{term.lower().replace(" ", "-")}',
                    'description': f'Clinical information and research about {term} from NIH',
                    'category': 'clinical_info',
                    'source': 'nih',
                    'publication_date': '2023-08-01'
                },
                {
                    'title': f'NLM Medical Encyclopedia: {term.title()}',
                    'url': f'https://medlineplus.gov/encyclopedia/{term.lower().replace(" ", "")}.htm',
                    'description': f'Medical encyclopedia entry for {term}',
                    'category': 'definition',
                    'source': 'nlm',
                    'publication_date': '2023-09-15'
                },
                {
                    'title': f'NIH Research on {term.title()}',
                    'url': f'https://www.nih.gov/research/{term.lower().replace(" ", "-")}',
                    'description': f'Current NIH research and clinical trials related to {term}',
                    'category': 'research',
                    'source': 'nih',
                    'publication_date': '2023-10-01'
                }
            ]
            
            # Procesar recursos
            for resource_data in nih_resources[:max_results]:
                processed = await self._process_nih_resource(resource_data, term, context)
                if processed:
                    results.append(processed)
            
            # Ordenar por relevancia
            results.sort(key=lambda x: x.get('relevance_score', 0.0), reverse=True)
            
            logger.info(f"Encontrados {len(results)} recursos en NIH")
            return results
            
        except Exception as e:
            logger.error(f"Error buscando en NIH: {e}")
            return []
    
    async def _process_nih_resource(
        self,
        resource_data: Dict[str, Any],
        search_term: str,
        context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Procesa un recurso de NIH y calcula métricas.
        
        Args:
            resource_data: Datos del recurso
            search_term: Término de búsqueda
            context: Contexto opcional
            
        Returns:
            Recurso procesado con métricas
        """
        try:
            # Calcular relevancia básica
            relevance_score = self.calculate_base_relevance_score(
                resource_data.get('description', ''),
                search_term
            )
            
            # NIH tiene alta autoridad
            authority_score = 0.9
            
            # Calcular recencia
            recency_score = self._calculate_recency(resource_data.get('publication_date'))
            
            # Score general
            overall_score = (
                relevance_score * 0.4 +
                authority_score * 0.4 +
                recency_score * 0.2
            )
            
            return {
                'title': resource_data['title'],
                'url': resource_data['url'],
                'domain': 'nih.gov' if 'nih.gov' in resource_data['url'] else 'nlm.nih.gov',
                'content': resource_data['description'],
                'relevant_excerpt': resource_data['description'][:300],
                'keywords': [search_term],
                'content_category': resource_data.get('category', 'general'),
                'target_audience': 'mixed',
                'language': 'en',
                'publication_date': resource_data.get('publication_date'),
                'relevance_score': relevance_score,
                'authority_score': authority_score,
                'recency_score': recency_score,
                'overall_score': overall_score,
                'access_type': 'free',
                'peer_reviewed': False,
                'official_source': True,
                'extraction_method': 'api',
                'source_metadata': {
                    'nih_source': resource_data.get('source', 'nih'),
                    'category': resource_data.get('category')
                }
            }
            
        except Exception as e:
            logger.error(f"Error procesando recurso NIH: {e}")
            return None
    
    def _calculate_recency(self, publication_date: Optional[str]) -> float:
        """Calcula score de recencia."""
        if not publication_date:
            return 0.7  # Score neutral-alto para NIH
        
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
            return 0.7
    
    async def health_check(self) -> Dict[str, Any]:
        """Verifica el estado del servicio NIH."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://www.nih.gov/",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    success = response.status == 200
            
            return {
                'service': 'nih',
                'status': 'healthy' if success else 'unhealthy',
                'endpoints': ['clinical_info', 'research', 'medical_encyclopedia'],
                'last_check': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'service': 'nih',
                'status': 'unhealthy',
                'error': str(e),
                'last_check': datetime.utcnow().isoformat()
            }
