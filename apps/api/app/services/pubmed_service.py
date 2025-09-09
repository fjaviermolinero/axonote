"""
Servicio especializado para búsquedas en PubMed/NCBI.

Utiliza las APIs oficiales de NCBI para búsquedas académicas
de artículos médicos peer-reviewed con extracción automática
de contenido relevante.
"""

import asyncio
import logging
import re
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from urllib.parse import quote

import aiohttp
from xml.etree import ElementTree as ET

from app.core.config import settings
from app.services.base import BaseSourceService
from app.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class PubMedArticle:
    """Representa un artículo de PubMed con metadatos completos."""
    
    def __init__(self, data: Dict[str, Any]):
        self.pmid = data.get('pmid')
        self.title = data.get('title', '')
        self.abstract = data.get('abstract', '')
        self.authors = data.get('authors', [])
        self.journal = data.get('journal', '')
        self.publication_date = data.get('publication_date')
        self.doi = data.get('doi')
        self.pmcid = data.get('pmcid')
        self.keywords = data.get('keywords', [])
        self.mesh_terms = data.get('mesh_terms', [])
        self.publication_types = data.get('publication_types', [])
        self.language = data.get('language', 'eng')
        self.journal_impact_factor = data.get('impact_factor')
        
    def to_dict(self) -> Dict[str, Any]:
        """Convierte el artículo a diccionario."""
        return {
            'pmid': self.pmid,
            'title': self.title,
            'abstract': self.abstract,
            'authors': self.authors,
            'journal': self.journal,
            'publication_date': self.publication_date.isoformat() if isinstance(self.publication_date, date) else self.publication_date,
            'doi': self.doi,
            'pmcid': self.pmcid,
            'keywords': self.keywords,
            'mesh_terms': self.mesh_terms,
            'publication_types': self.publication_types,
            'language': self.language,
            'impact_factor': self.journal_impact_factor
        }


class PubMedService(BaseSourceService):
    """
    Servicio especializado para búsquedas en PubMed/NCBI.
    
    Utiliza las APIs oficiales de NCBI (E-utilities) para realizar
    búsquedas académicas y extraer contenido médico relevante.
    """
    
    def __init__(self):
        super().__init__("pubmed")
        
        # URLs de las APIs de NCBI
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
        self.esearch_url = f"{self.base_url}esearch.fcgi"
        self.efetch_url = f"{self.base_url}efetch.fcgi"
        self.esummary_url = f"{self.base_url}esummary.fcgi"
        
        # Configuración de API
        self.api_key = getattr(settings, 'NCBI_API_KEY', None)
        self.email = getattr(settings, 'NCBI_EMAIL', 'research@axonote.com')
        
        # Rate limiter (NCBI permite 3 req/sec con API key, 1 req/sec sin ella)
        requests_per_second = 3 if self.api_key else 1
        self.rate_limiter = RateLimiter(requests_per_second=requests_per_second)
        
        # Configuración de búsqueda
        self.default_retmax = 20
        self.max_retries = 3
        
        logger.info(f"PubMedService inicializado con API key: {'Sí' if self.api_key else 'No'}")
    
    async def search_term(
        self,
        term: str,
        max_results: int = 10,
        language: str = "en",
        context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca artículos en PubMed para un término médico.
        
        Args:
            term: Término médico a buscar
            max_results: Número máximo de resultados
            language: Idioma preferido (no afecta PubMed directamente)
            context: Contexto opcional para refinar búsqueda
            
        Returns:
            Lista de artículos encontrados
        """
        logger.info(f"Buscando en PubMed: '{term}' (max: {max_results})")
        
        try:
            # Construir query de búsqueda
            search_query = self._build_search_query(term, context)
            
            # Realizar búsqueda
            pmids = await self._search_articles(search_query, max_results)
            
            if not pmids:
                logger.info(f"No se encontraron artículos para '{term}'")
                return []
            
            # Obtener detalles de artículos
            articles = await self._fetch_article_details(pmids)
            
            # Procesar y rankear resultados
            processed_articles = []
            for article in articles:
                processed = await self._process_article(article, term, context)
                if processed:
                    processed_articles.append(processed)
            
            # Ordenar por relevancia
            processed_articles.sort(
                key=lambda x: x.get('relevance_score', 0.0),
                reverse=True
            )
            
            logger.info(f"Encontrados {len(processed_articles)} artículos relevantes en PubMed")
            return processed_articles[:max_results]
            
        except Exception as e:
            logger.error(f"Error buscando en PubMed: {e}")
            return []
    
    def _build_search_query(self, term: str, context: Optional[str] = None) -> str:
        """
        Construye una query optimizada para PubMed.
        
        Args:
            term: Término principal
            context: Contexto opcional
            
        Returns:
            Query de búsqueda optimizada
        """
        # Limpiar término
        clean_term = re.sub(r'[^\w\s-]', '', term).strip()
        
        # Query base con el término
        query_parts = [f'"{clean_term}"[Title/Abstract]']
        
        # Añadir contexto si está disponible
        if context:
            context_words = re.findall(r'\b\w{4,}\b', context.lower())
            if context_words:
                # Tomar las 2-3 palabras más relevantes del contexto
                context_query = ' OR '.join([f'"{word}"[Title/Abstract]' for word in context_words[:3]])
                query_parts.append(f'({context_query})')
        
        # Filtros adicionales para mejorar relevancia
        filters = [
            'hasabstract',  # Solo artículos con abstract
            'humans[MeSH Terms]',  # Solo estudios en humanos
            'english[Language] OR italian[Language]'  # Idiomas relevantes
        ]
        
        # Combinar query
        main_query = ' AND '.join(query_parts)
        filter_query = ' AND '.join(filters)
        
        final_query = f'({main_query}) AND ({filter_query})'
        
        logger.debug(f"Query PubMed construida: {final_query}")
        return final_query
    
    async def _search_articles(self, query: str, max_results: int) -> List[str]:
        """
        Realiza búsqueda en PubMed y obtiene PMIDs.
        
        Args:
            query: Query de búsqueda
            max_results: Número máximo de resultados
            
        Returns:
            Lista de PMIDs encontrados
        """
        params = {
            'db': 'pubmed',
            'term': query,
            'retmax': min(max_results * 2, 50),  # Margen extra para filtrado
            'retmode': 'xml',
            'sort': 'relevance',
            'tool': 'axonote',
            'email': self.email
        }
        
        if self.api_key:
            params['api_key'] = self.api_key
        
        async with self.rate_limiter:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.esearch_url, params=params) as response:
                    if response.status != 200:
                        raise Exception(f"Error en búsqueda PubMed: HTTP {response.status}")
                    
                    xml_content = await response.text()
                    
        # Parsear XML response
        try:
            root = ET.fromstring(xml_content)
            pmids = [id_elem.text for id_elem in root.findall('.//Id')]
            
            logger.debug(f"Encontrados {len(pmids)} PMIDs en búsqueda")
            return pmids
            
        except ET.ParseError as e:
            logger.error(f"Error parseando respuesta XML de PubMed: {e}")
            return []
    
    async def _fetch_article_details(self, pmids: List[str]) -> List[PubMedArticle]:
        """
        Obtiene detalles completos de artículos por PMID.
        
        Args:
            pmids: Lista de PMIDs
            
        Returns:
            Lista de artículos con detalles completos
        """
        if not pmids:
            return []
        
        # Procesar en lotes para evitar URLs muy largas
        batch_size = 20
        all_articles = []
        
        for i in range(0, len(pmids), batch_size):
            batch_pmids = pmids[i:i + batch_size]
            batch_articles = await self._fetch_batch_details(batch_pmids)
            all_articles.extend(batch_articles)
        
        return all_articles
    
    async def _fetch_batch_details(self, pmids: List[str]) -> List[PubMedArticle]:
        """
        Obtiene detalles de un lote de artículos.
        
        Args:
            pmids: Lista de PMIDs del lote
            
        Returns:
            Lista de artículos del lote
        """
        params = {
            'db': 'pubmed',
            'id': ','.join(pmids),
            'retmode': 'xml',
            'rettype': 'abstract',
            'tool': 'axonote',
            'email': self.email
        }
        
        if self.api_key:
            params['api_key'] = self.api_key
        
        async with self.rate_limiter:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.efetch_url, params=params) as response:
                    if response.status != 200:
                        logger.warning(f"Error obteniendo detalles: HTTP {response.status}")
                        return []
                    
                    xml_content = await response.text()
        
        # Parsear respuesta XML
        try:
            return self._parse_articles_xml(xml_content)
        except Exception as e:
            logger.error(f"Error parseando detalles de artículos: {e}")
            return []
    
    def _parse_articles_xml(self, xml_content: str) -> List[PubMedArticle]:
        """
        Parsea XML de detalles de artículos de PubMed.
        
        Args:
            xml_content: Contenido XML de la respuesta
            
        Returns:
            Lista de artículos parseados
        """
        articles = []
        
        try:
            root = ET.fromstring(xml_content)
            
            for article_elem in root.findall('.//PubmedArticle'):
                try:
                    article_data = self._extract_article_data(article_elem)
                    if article_data:
                        articles.append(PubMedArticle(article_data))
                except Exception as e:
                    logger.warning(f"Error parseando artículo individual: {e}")
                    continue
            
        except ET.ParseError as e:
            logger.error(f"Error parseando XML de artículos: {e}")
        
        return articles
    
    def _extract_article_data(self, article_elem: ET.Element) -> Optional[Dict[str, Any]]:
        """
        Extrae datos de un elemento XML de artículo.
        
        Args:
            article_elem: Elemento XML del artículo
            
        Returns:
            Diccionario con datos del artículo
        """
        try:
            # PMID
            pmid_elem = article_elem.find('.//PMID')
            pmid = pmid_elem.text if pmid_elem is not None else None
            
            if not pmid:
                return None
            
            # Título
            title_elem = article_elem.find('.//ArticleTitle')
            title = title_elem.text if title_elem is not None else ''
            
            # Abstract
            abstract_parts = []
            for abstract_elem in article_elem.findall('.//AbstractText'):
                text = abstract_elem.text or ''
                label = abstract_elem.get('Label', '')
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
            
            abstract = ' '.join(abstract_parts).strip()
            
            # Autores
            authors = []
            for author_elem in article_elem.findall('.//Author'):
                last_name = author_elem.find('LastName')
                first_name = author_elem.find('ForeName')
                
                if last_name is not None:
                    name = last_name.text or ''
                    if first_name is not None:
                        name = f"{first_name.text} {name}"
                    
                    affiliation_elem = author_elem.find('AffiliationInfo/Affiliation')
                    affiliation = affiliation_elem.text if affiliation_elem is not None else ''
                    
                    authors.append({
                        'name': name.strip(),
                        'affiliation': affiliation
                    })
            
            # Journal
            journal_elem = article_elem.find('.//Journal/Title')
            journal = journal_elem.text if journal_elem is not None else ''
            
            # Fecha de publicación
            pub_date = self._extract_publication_date(article_elem)
            
            # DOI
            doi = None
            for id_elem in article_elem.findall('.//ArticleId'):
                if id_elem.get('IdType') == 'doi':
                    doi = id_elem.text
                    break
            
            # PMC ID
            pmcid = None
            for id_elem in article_elem.findall('.//ArticleId'):
                if id_elem.get('IdType') == 'pmc':
                    pmcid = id_elem.text
                    break
            
            # Keywords/MeSH terms
            mesh_terms = []
            for mesh_elem in article_elem.findall('.//MeshHeading/DescriptorName'):
                if mesh_elem.text:
                    mesh_terms.append(mesh_elem.text)
            
            # Tipos de publicación
            pub_types = []
            for type_elem in article_elem.findall('.//PublicationType'):
                if type_elem.text:
                    pub_types.append(type_elem.text)
            
            # Idioma
            lang_elem = article_elem.find('.//Language')
            language = lang_elem.text if lang_elem is not None else 'eng'
            
            return {
                'pmid': pmid,
                'title': title,
                'abstract': abstract,
                'authors': authors,
                'journal': journal,
                'publication_date': pub_date,
                'doi': doi,
                'pmcid': pmcid,
                'keywords': [],  # Keywords separadas no siempre disponibles
                'mesh_terms': mesh_terms,
                'publication_types': pub_types,
                'language': language
            }
            
        except Exception as e:
            logger.warning(f"Error extrayendo datos de artículo: {e}")
            return None
    
    def _extract_publication_date(self, article_elem: ET.Element) -> Optional[date]:
        """
        Extrae fecha de publicación del XML.
        
        Args:
            article_elem: Elemento XML del artículo
            
        Returns:
            Fecha de publicación o None
        """
        try:
            # Buscar fecha en diferentes ubicaciones
            date_elem = article_elem.find('.//PubDate')
            if date_elem is None:
                return None
            
            year_elem = date_elem.find('Year')
            month_elem = date_elem.find('Month')
            day_elem = date_elem.find('Day')
            
            if year_elem is None:
                return None
            
            year = int(year_elem.text)
            month = 1
            day = 1
            
            if month_elem is not None:
                month_text = month_elem.text
                if month_text.isdigit():
                    month = int(month_text)
                else:
                    # Convertir nombre de mes
                    month_names = {
                        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
                        'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
                        'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                    }
                    month = month_names.get(month_text, 1)
            
            if day_elem is not None and day_elem.text.isdigit():
                day = int(day_elem.text)
            
            return date(year, month, day)
            
        except (ValueError, AttributeError):
            return None
    
    async def _process_article(
        self,
        article: PubMedArticle,
        search_term: str,
        context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Procesa un artículo y calcula métricas de relevancia.
        
        Args:
            article: Artículo de PubMed
            search_term: Término de búsqueda original
            context: Contexto opcional
            
        Returns:
            Artículo procesado con métricas
        """
        try:
            # Calcular relevancia
            relevance_score = self._calculate_relevance(article, search_term, context)
            
            # Calcular autoridad
            authority_score = self._calculate_authority(article)
            
            # Calcular recencia
            recency_score = self._calculate_recency(article)
            
            # Score general
            overall_score = (
                relevance_score * 0.5 +
                authority_score * 0.3 +
                recency_score * 0.2
            )
            
            # Extraer extracto relevante
            relevant_excerpt = self._extract_relevant_excerpt(article, search_term)
            
            # Determinar categoría de contenido
            content_category = self._determine_content_category(article)
            
            # Construir URL
            url = f"https://pubmed.ncbi.nlm.nih.gov/{article.pmid}/"
            
            return {
                'title': article.title,
                'url': url,
                'domain': 'pubmed.ncbi.nlm.nih.gov',
                'authors': article.authors,
                'journal_name': article.journal,
                'publication_date': article.publication_date,
                'doi': article.doi,
                'pmid': article.pmid,
                'pmcid': article.pmcid,
                'abstract': article.abstract,
                'relevant_excerpt': relevant_excerpt,
                'keywords': article.mesh_terms,  # Usar MeSH terms como keywords
                'content_category': content_category,
                'target_audience': 'professional',
                'language': 'en' if article.language == 'eng' else article.language,
                'relevance_score': relevance_score,
                'authority_score': authority_score,
                'recency_score': recency_score,
                'overall_score': overall_score,
                'access_type': 'free',
                'peer_reviewed': True,  # PubMed es peer-reviewed por defecto
                'official_source': True,  # NCBI es fuente oficial
                'extraction_method': 'api',
                'source_metadata': {
                    'publication_types': article.publication_types,
                    'mesh_terms': article.mesh_terms,
                    'impact_factor': article.journal_impact_factor
                }
            }
            
        except Exception as e:
            logger.error(f"Error procesando artículo {article.pmid}: {e}")
            return None
    
    def _calculate_relevance(
        self,
        article: PubMedArticle,
        search_term: str,
        context: Optional[str] = None
    ) -> float:
        """Calcula relevancia del artículo para el término de búsqueda."""
        score = 0.0
        term_lower = search_term.lower()
        
        # Relevancia en título (peso alto)
        if term_lower in article.title.lower():
            score += 0.4
        
        # Relevancia en abstract (peso medio)
        if term_lower in article.abstract.lower():
            score += 0.3
        
        # Relevancia en MeSH terms (peso medio)
        for mesh_term in article.mesh_terms:
            if term_lower in mesh_term.lower():
                score += 0.2
                break
        
        # Relevancia por contexto
        if context:
            context_words = re.findall(r'\b\w{4,}\b', context.lower())
            context_matches = sum(
                1 for word in context_words
                if word in article.abstract.lower() or word in article.title.lower()
            )
            if context_words:
                score += (context_matches / len(context_words)) * 0.1
        
        return min(1.0, score)
    
    def _calculate_authority(self, article: PubMedArticle) -> float:
        """Calcula score de autoridad basado en journal y metadatos."""
        score = 0.7  # Base score para PubMed
        
        # Bonus por journal de alto impacto
        if article.journal_impact_factor:
            if article.journal_impact_factor > 10:
                score += 0.2
            elif article.journal_impact_factor > 5:
                score += 0.1
        
        # Bonus por tipos de publicación relevantes
        high_quality_types = [
            'Randomized Controlled Trial',
            'Meta-Analysis',
            'Systematic Review',
            'Clinical Trial'
        ]
        
        for pub_type in article.publication_types:
            if any(hq_type in pub_type for hq_type in high_quality_types):
                score += 0.1
                break
        
        return min(1.0, score)
    
    def _calculate_recency(self, article: PubMedArticle) -> float:
        """Calcula score de recencia basado en fecha de publicación."""
        if not article.publication_date:
            return 0.5  # Score neutral si no hay fecha
        
        if isinstance(article.publication_date, str):
            try:
                pub_date = datetime.strptime(article.publication_date, '%Y-%m-%d').date()
            except ValueError:
                return 0.5
        else:
            pub_date = article.publication_date
        
        today = date.today()
        age_days = (today - pub_date).days
        age_years = age_days / 365.25
        
        # Score decae con la edad
        if age_years <= 1:
            return 1.0
        elif age_years <= 2:
            return 0.8
        elif age_years <= 5:
            return 0.6
        elif age_years <= 10:
            return 0.4
        else:
            return 0.2
    
    def _extract_relevant_excerpt(self, article: PubMedArticle, search_term: str) -> str:
        """Extrae el extracto más relevante del abstract."""
        if not article.abstract:
            return ""
        
        # Buscar oraciones que contengan el término
        sentences = re.split(r'[.!?]+', article.abstract)
        relevant_sentences = [
            s.strip() for s in sentences
            if search_term.lower() in s.lower() and len(s.strip()) > 20
        ]
        
        if relevant_sentences:
            # Tomar la primera oración relevante
            return relevant_sentences[0][:300] + "..." if len(relevant_sentences[0]) > 300 else relevant_sentences[0]
        
        # Fallback: primeras líneas del abstract
        return article.abstract[:300] + "..." if len(article.abstract) > 300 else article.abstract
    
    def _determine_content_category(self, article: PubMedArticle) -> str:
        """Determina la categoría de contenido basada en tipos de publicación."""
        pub_types_lower = [pt.lower() for pt in article.publication_types]
        
        if any('review' in pt for pt in pub_types_lower):
            return 'review'
        elif any('trial' in pt for pt in pub_types_lower):
            return 'clinical_trial'
        elif any('meta-analysis' in pt for pt in pub_types_lower):
            return 'meta_analysis'
        elif any('case' in pt for pt in pub_types_lower):
            return 'case_study'
        else:
            return 'definition'
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Verifica el estado del servicio PubMed.
        
        Returns:
            Estado del servicio
        """
        try:
            # Realizar búsqueda simple de prueba
            test_query = "medicine[Title]"
            params = {
                'db': 'pubmed',
                'term': test_query,
                'retmax': 1,
                'retmode': 'xml',
                'tool': 'axonote',
                'email': self.email
            }
            
            if self.api_key:
                params['api_key'] = self.api_key
            
            async with self.rate_limiter:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.esearch_url, params=params, timeout=10) as response:
                        success = response.status == 200
            
            return {
                'service': 'pubmed',
                'status': 'healthy' if success else 'unhealthy',
                'api_key_configured': bool(self.api_key),
                'rate_limit': f"{self.rate_limiter.requests_per_second} req/sec",
                'last_check': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'service': 'pubmed',
                'status': 'unhealthy',
                'error': str(e),
                'last_check': datetime.utcnow().isoformat()
            }
