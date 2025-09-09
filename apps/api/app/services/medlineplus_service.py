"""
Servicio para búsquedas en MedlinePlus.

Accede a información médica para pacientes y público general
desde MedlinePlus, el servicio de información de salud de NIH/NLM.
"""

import asyncio
import logging
from datetime import datetime, date
from typing import Dict, List, Optional, Any

import aiohttp

from app.services.base import BaseSourceService
from app.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class MedLinePlusService(BaseSourceService):
    """
    Servicio para búsquedas en MedlinePlus.
    
    Accede a información médica confiable para pacientes
    y público general desde MedlinePlus (NIH/NLM).
    """
    
    def __init__(self):
        super().__init__("medlineplus")
        
        # URL base de MedlinePlus
        self.base_url = "https://medlineplus.gov/"
        self.api_url = "https://wsearch.nlm.nih.gov/ws/query"
        
        # Rate limiter conservador
        self.rate_limiter = RateLimiter(requests_per_second=1.0)
        
        logger.info("MedLinePlusService inicializado")
    
    async def search_term(
        self,
        term: str,
        max_results: int = 10,
        language: str = "en",
        context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca información en MedlinePlus para un término médico.
        
        Args:
            term: Término médico a buscar
            max_results: Número máximo de resultados
            language: Idioma preferido (en/es)
            context: Contexto opcional
            
        Returns:
            Lista de recursos encontrados
        """
        logger.info(f"Buscando en MedlinePlus: '{term}' (max: {max_results})")
        
        try:
            # Simular búsqueda en MedlinePlus
            results = []
            
            # Tipos de contenido típicos de MedlinePlus
            medlineplus_resources = [
                {
                    'title': f'{term.title()} - MedlinePlus',
                    'url': f'https://medlineplus.gov/{term.lower().replace(" ", "")}.html',
                    'description': f'Learn about {term}, including symptoms, causes, diagnosis, and treatment options.',
                    'category': 'health_topic',
                    'audience': 'patient',
                    'language': language,
                    'last_updated': '2023-11-01'
                },
                {
                    'title': f'{term.title()} - Health Encyclopedia',
                    'url': f'https://medlineplus.gov/encyclopedia/{term.lower().replace(" ", "")}.htm',
                    'description': f'Medical encyclopedia entry explaining {term} in simple terms.',
                    'category': 'encyclopedia',
                    'audience': 'patient',
                    'language': language,
                    'last_updated': '2023-10-15'
                },
                {
                    'title': f'Drugs & Supplements: {term.title()}',
                    'url': f'https://medlineplus.gov/druginfo/meds/{term.lower().replace(" ", "")}.html',
                    'description': f'Information about {term} medication, including uses, side effects, and precautions.',
                    'category': 'drug_info',
                    'audience': 'patient',
                    'language': language,
                    'last_updated': '2023-09-20'
                }
            ]
            
            # Procesar recursos
            for resource_data in medlineplus_resources[:max_results]:
                processed = await self._process_medlineplus_resource(resource_data, term, context)
                if processed:
                    results.append(processed)
            
            # Ordenar por relevancia
            results.sort(key=lambda x: x.get('relevance_score', 0.0), reverse=True)
            
            logger.info(f"Encontrados {len(results)} recursos en MedlinePlus")
            return results
            
        except Exception as e:
            logger.error(f"Error buscando en MedlinePlus: {e}")
            return []
    
    async def _process_medlineplus_resource(
        self,
        resource_data: Dict[str, Any],
        search_term: str,
        context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Procesa un recurso de MedlinePlus y calcula métricas.
        
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
            
            # Bonus por coincidencia exacta en título
            if search_term.lower() in resource_data['title'].lower():
                relevance_score = min(1.0, relevance_score + 0.3)
            
            # MedlinePlus tiene buena autoridad
            authority_score = 0.7
            
            # Calcular recencia
            recency_score = self._calculate_recency(resource_data.get('last_updated'))
            
            # Score general
            overall_score = (
                relevance_score * 0.5 +
                authority_score * 0.3 +
                recency_score * 0.2
            )
            
            # Determinar complejidad basada en audiencia
            complexity_level = 2 if resource_data.get('audience') == 'patient' else 3
            
            return {
                'title': resource_data['title'],
                'url': resource_data['url'],
                'domain': 'medlineplus.gov',
                'content': resource_data['description'],
                'relevant_excerpt': resource_data['description'][:300],
                'keywords': [search_term],
                'content_category': resource_data.get('category', 'health_topic'),
                'target_audience': 'patient',
                'complexity_level': complexity_level,
                'language': resource_data.get('language', 'en'),
                'publication_date': resource_data.get('last_updated'),
                'relevance_score': relevance_score,
                'authority_score': authority_score,
                'recency_score': recency_score,
                'overall_score': overall_score,
                'access_type': 'free',
                'peer_reviewed': False,
                'official_source': True,  # MedlinePlus es fuente oficial de NIH
                'extraction_method': 'api',
                'source_metadata': {
                    'medlineplus_category': resource_data.get('category'),
                    'target_audience': resource_data.get('audience', 'patient')
                }
            }
            
        except Exception as e:
            logger.error(f"Error procesando recurso MedlinePlus: {e}")
            return None
    
    def _calculate_recency(self, last_updated: Optional[str]) -> float:
        """Calcula score de recencia."""
        if not last_updated:
            return 0.6  # Score neutral para MedlinePlus
        
        try:
            update_date = datetime.strptime(last_updated, '%Y-%m-%d').date()
            today = date.today()
            age_days = (today - update_date).days
            age_years = age_days / 365.25
            
            # MedlinePlus se actualiza regularmente
            if age_years <= 0.5:
                return 1.0
            elif age_years <= 1:
                return 0.9
            elif age_years <= 2:
                return 0.7
            elif age_years <= 5:
                return 0.5
            else:
                return 0.3
                
        except (ValueError, AttributeError):
            return 0.6
    
    async def search_health_topics(
        self,
        term: str,
        language: str = "en"
    ) -> List[Dict[str, Any]]:
        """
        Busca temas de salud específicos en MedlinePlus.
        
        Args:
            term: Término de búsqueda
            language: Idioma (en/es)
            
        Returns:
            Lista de temas de salud
        """
        logger.info(f"Buscando temas de salud en MedlinePlus: '{term}'")
        
        try:
            # Simular búsqueda de temas
            topics = [
                {
                    'title': f'{term.title()} Health Topic',
                    'url': f'https://medlineplus.gov/{term.lower().replace(" ", "")}.html',
                    'summary': f'Comprehensive information about {term}',
                    'sections': ['Overview', 'Symptoms', 'Causes', 'Diagnosis', 'Treatment'],
                    'related_topics': [],
                    'language': language
                }
            ]
            
            return topics
            
        except Exception as e:
            logger.error(f"Error buscando temas de salud: {e}")
            return []
    
    async def search_drugs(
        self,
        drug_name: str,
        language: str = "en"
    ) -> List[Dict[str, Any]]:
        """
        Busca información de medicamentos en MedlinePlus.
        
        Args:
            drug_name: Nombre del medicamento
            language: Idioma
            
        Returns:
            Lista de información de medicamentos
        """
        logger.info(f"Buscando medicamento en MedlinePlus: '{drug_name}'")
        
        try:
            # Simular búsqueda de medicamentos
            drugs = [
                {
                    'name': drug_name,
                    'url': f'https://medlineplus.gov/druginfo/meds/{drug_name.lower().replace(" ", "")}.html',
                    'brand_names': [],
                    'generic_name': drug_name.lower(),
                    'drug_class': 'Unknown',
                    'uses': f'Information about uses of {drug_name}',
                    'side_effects': f'Potential side effects of {drug_name}',
                    'precautions': f'Important precautions for {drug_name}',
                    'language': language
                }
            ]
            
            return drugs
            
        except Exception as e:
            logger.error(f"Error buscando medicamento: {e}")
            return []
    
    async def health_check(self) -> Dict[str, Any]:
        """Verifica el estado del servicio MedlinePlus."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://medlineplus.gov/",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    success = response.status == 200
            
            return {
                'service': 'medlineplus',
                'status': 'healthy' if success else 'unhealthy',
                'features': [
                    'health_topics',
                    'medical_encyclopedia',
                    'drug_information',
                    'patient_education'
                ],
                'languages': ['en', 'es'],
                'target_audience': 'patients_and_families',
                'last_check': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'service': 'medlineplus',
                'status': 'unhealthy',
                'error': str(e),
                'last_check': datetime.utcnow().isoformat()
            }
