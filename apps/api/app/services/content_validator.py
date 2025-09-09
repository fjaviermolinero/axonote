"""
Validador de contenido médico para verificar calidad y confiabilidad.

Valida contenido médico encontrado durante el research automático,
calculando scores de relevancia, autoridad y precisión médica.
"""

import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, date
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ValidationResult:
    """Resultado de validación de contenido médico."""
    
    def __init__(
        self,
        is_valid: bool,
        relevance_score: float,
        authority_score: float,
        quality_score: float,
        issues: List[str] = None,
        recommendations: List[str] = None
    ):
        self.is_valid = is_valid
        self.relevance_score = relevance_score
        self.authority_score = authority_score
        self.quality_score = quality_score
        self.issues = issues or []
        self.recommendations = recommendations or []
        
        # Score combinado
        self.overall_score = (
            relevance_score * 0.4 +
            authority_score * 0.35 +
            quality_score * 0.25
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte el resultado a diccionario."""
        return {
            'is_valid': self.is_valid,
            'relevance_score': self.relevance_score,
            'authority_score': self.authority_score,
            'quality_score': self.quality_score,
            'overall_score': self.overall_score,
            'issues': self.issues,
            'recommendations': self.recommendations
        }


class ContentValidator:
    """
    Validador de contenido médico que verifica calidad,
    relevancia y confiabilidad de las fuentes encontradas.
    """
    
    def __init__(self):
        # Dominios de alta autoridad médica
        self.high_authority_domains = {
            'pubmed.ncbi.nlm.nih.gov': 0.95,
            'www.who.int': 0.95,
            'www.nih.gov': 0.9,
            'medlineplus.gov': 0.8,
            'www.iss.it': 0.9,
            'www.aifa.gov.it': 0.85,
            'www.salute.gov.it': 0.8,
            'www.mayoclinic.org': 0.8,
            'my.clevelandclinic.org': 0.75,
            'www.cochrane.org': 0.9,
            'www.uptodate.com': 0.85
        }
        
        # Dominios de autoridad media
        self.medium_authority_domains = {
            'www.webmd.com': 0.6,
            'www.healthline.com': 0.6,
            'www.medicalnewstoday.com': 0.55,
            'www.drugs.com': 0.65
        }
        
        # Patrones de contenido médico válido
        self.medical_patterns = [
            r'\b(diagnosis|treatment|symptom|disease|condition|medication|therapy)\b',
            r'\b(clinical|medical|therapeutic|pharmaceutical|pathological)\b',
            r'\b(patient|healthcare|medicine|health)\b'
        ]
        
        # Patrones de contenido de baja calidad
        self.low_quality_patterns = [
            r'\b(click here|buy now|limited time|miracle cure|guaranteed)\b',
            r'\b(secret|amazing|shocking|unbelievable)\b',
            r'[!]{3,}',  # Múltiples signos de exclamación
            r'[A-Z]{10,}'  # Texto en mayúsculas excesivo
        ]
        
        logger.info("ContentValidator inicializado")
    
    async def validate_source(
        self,
        source: Dict[str, Any],
        search_term: str
    ) -> ValidationResult:
        """
        Valida una fuente médica individual.
        
        Args:
            source: Datos de la fuente médica
            search_term: Término de búsqueda original
            
        Returns:
            Resultado de validación
        """
        try:
            issues = []
            recommendations = []
            
            # 1. Validar relevancia
            relevance_score = self._validate_relevance(source, search_term)
            if relevance_score < 0.3:
                issues.append("Baja relevancia para el término de búsqueda")
                recommendations.append("Verificar que el contenido sea específico al término")
            
            # 2. Validar autoridad
            authority_score = self._validate_authority(source)
            if authority_score < 0.5:
                issues.append("Fuente de autoridad cuestionable")
                recommendations.append("Priorizar fuentes oficiales o peer-reviewed")
            
            # 3. Validar calidad del contenido
            quality_score = self._validate_content_quality(source)
            if quality_score < 0.6:
                issues.append("Calidad de contenido por debajo del estándar")
                recommendations.append("Revisar contenido para asegurar rigor médico")
            
            # 4. Validaciones específicas
            self._validate_medical_accuracy(source, issues, recommendations)
            self._validate_completeness(source, issues, recommendations)
            self._validate_currency(source, issues, recommendations)
            
            # Determinar si es válida
            is_valid = (
                relevance_score >= 0.3 and
                authority_score >= 0.4 and
                quality_score >= 0.5 and
                len(issues) <= 2
            )
            
            return ValidationResult(
                is_valid=is_valid,
                relevance_score=relevance_score,
                authority_score=authority_score,
                quality_score=quality_score,
                issues=issues,
                recommendations=recommendations
            )
            
        except Exception as e:
            logger.error(f"Error validando fuente: {e}")
            return ValidationResult(
                is_valid=False,
                relevance_score=0.0,
                authority_score=0.0,
                quality_score=0.0,
                issues=[f"Error en validación: {str(e)}"]
            )
    
    async def validate_sources(
        self,
        sources: List[Dict[str, Any]],
        search_term: str,
        context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Valida múltiples fuentes y las rankea por calidad.
        
        Args:
            sources: Lista de fuentes a validar
            search_term: Término de búsqueda
            context: Contexto opcional
            
        Returns:
            Lista de fuentes validadas y rankeadas
        """
        logger.info(f"Validando {len(sources)} fuentes para término '{search_term}'")
        
        validated_sources = []
        
        for source in sources:
            try:
                # Validar fuente individual
                validation = await self.validate_source(source, search_term)
                
                # Añadir métricas de validación a la fuente
                source.update({
                    'validation_result': validation.to_dict(),
                    'relevance_score': validation.relevance_score,
                    'authority_score': validation.authority_score,
                    'content_quality_score': validation.quality_score,
                    'overall_score': validation.overall_score,
                    'is_validated': validation.is_valid
                })
                
                # Solo incluir fuentes válidas o con score mínimo
                if validation.is_valid or validation.overall_score >= 0.4:
                    validated_sources.append(source)
                else:
                    logger.debug(f"Fuente rechazada: {source.get('title', 'Sin título')} (score: {validation.overall_score:.2f})")
                
            except Exception as e:
                logger.error(f"Error validando fuente individual: {e}")
                continue
        
        logger.info(f"Validadas {len(validated_sources)} fuentes de {len(sources)} originales")
        return validated_sources
    
    def _validate_relevance(
        self,
        source: Dict[str, Any],
        search_term: str
    ) -> float:
        """Valida la relevancia de la fuente para el término de búsqueda."""
        score = 0.0
        term_lower = search_term.lower()
        
        # Contenido a evaluar
        title = source.get('title', '').lower()
        content = source.get('content', '').lower()
        abstract = source.get('abstract', '').lower()
        keywords = [k.lower() for k in source.get('keywords', [])]
        
        # Relevancia en título (peso alto)
        if term_lower in title:
            score += 0.4
        
        # Relevancia en abstract/contenido principal
        if term_lower in abstract or term_lower in content:
            score += 0.3
        
        # Relevancia en keywords
        if any(term_lower in keyword for keyword in keywords):
            score += 0.2
        
        # Densidad del término en el contenido
        all_content = f"{title} {content} {abstract}".lower()
        if all_content:
            term_count = all_content.count(term_lower)
            word_count = len(all_content.split())
            if word_count > 0:
                density = (term_count / word_count) * 100
                if 0.5 <= density <= 3:  # Densidad óptima
                    score += 0.1
        
        return min(1.0, score)
    
    def _validate_authority(self, source: Dict[str, Any]) -> float:
        """Valida la autoridad de la fuente."""
        # Score base por dominio
        domain = source.get('domain', '').lower()
        authority_score = self._get_domain_authority_score(domain)
        
        # Bonificaciones por características de autoridad
        if source.get('peer_reviewed', False):
            authority_score += 0.1
        
        if source.get('official_source', False):
            authority_score += 0.1
        
        # Bonificación por journal de alto impacto
        impact_factor = source.get('journal_impact_factor')
        if impact_factor:
            if impact_factor > 10:
                authority_score += 0.1
            elif impact_factor > 5:
                authority_score += 0.05
        
        # Bonificación por autores con afiliación
        authors = source.get('authors', [])
        if authors and isinstance(authors, list):
            has_affiliation = any(
                author.get('affiliation') for author in authors
                if isinstance(author, dict)
            )
            if has_affiliation:
                authority_score += 0.05
        
        return min(1.0, authority_score)
    
    def _validate_content_quality(self, source: Dict[str, Any]) -> float:
        """Valida la calidad del contenido."""
        content = source.get('content', '') or source.get('abstract', '')
        if not content:
            return 0.0
        
        score = 0.5  # Score base
        
        # Longitud apropiada
        content_length = len(content)
        if 100 <= content_length <= 2000:
            score += 0.2
        elif content_length > 50:
            score += 0.1
        
        # Presencia de patrones médicos válidos
        medical_pattern_count = sum(
            1 for pattern in self.medical_patterns
            if re.search(pattern, content, re.IGNORECASE)
        )
        if medical_pattern_count >= 2:
            score += 0.2
        elif medical_pattern_count >= 1:
            score += 0.1
        
        # Penalización por patrones de baja calidad
        low_quality_count = sum(
            1 for pattern in self.low_quality_patterns
            if re.search(pattern, content, re.IGNORECASE)
        )
        score -= low_quality_count * 0.1
        
        # Estructura del contenido
        sentences = re.split(r'[.!?]+', content)
        if len(sentences) >= 3:  # Contenido estructurado
            score += 0.1
        
        # Presencia de referencias o citas
        if re.search(r'\b(doi|pmid|reference|citation)\b', content, re.IGNORECASE):
            score += 0.1
        
        return max(0.0, min(1.0, score))
    
    def _validate_medical_accuracy(
        self,
        source: Dict[str, Any],
        issues: List[str],
        recommendations: List[str]
    ) -> None:
        """Valida la precisión médica del contenido."""
        content = source.get('content', '') or source.get('abstract', '')
        
        # Verificar presencia de disclaimers médicos apropiados
        if source.get('target_audience') == 'patient':
            disclaimer_patterns = [
                r'consult.*doctor',
                r'medical.*advice',
                r'healthcare.*professional'
            ]
            has_disclaimer = any(
                re.search(pattern, content, re.IGNORECASE)
                for pattern in disclaimer_patterns
            )
            if not has_disclaimer and len(content) > 200:
                issues.append("Falta disclaimer médico apropiado para contenido dirigido a pacientes")
                recommendations.append("Incluir advertencia sobre consultar profesionales médicos")
        
        # Verificar afirmaciones médicas extremas
        extreme_patterns = [
            r'\b(cure|heal|miracle|guarantee)\b',
            r'\b(always|never|100%|completely)\b.*\b(effective|safe|works)\b'
        ]
        for pattern in extreme_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                issues.append("Contiene afirmaciones médicas absolutas o extremas")
                recommendations.append("Usar lenguaje médico más preciso y matizado")
                break
    
    def _validate_completeness(
        self,
        source: Dict[str, Any],
        issues: List[str],
        recommendations: List[str]
    ) -> None:
        """Valida la completitud de la información."""
        # Verificar metadatos esenciales
        essential_fields = ['title', 'url', 'content']
        missing_fields = [field for field in essential_fields if not source.get(field)]
        
        if missing_fields:
            issues.append(f"Faltan campos esenciales: {', '.join(missing_fields)}")
            recommendations.append("Completar metadatos básicos de la fuente")
        
        # Verificar información de autoría para contenido académico
        if source.get('source_type') == 'pubmed' and not source.get('authors'):
            issues.append("Falta información de autoría para fuente académica")
            recommendations.append("Incluir información de autores cuando esté disponible")
        
        # Verificar fecha para contenido médico
        if not source.get('publication_date') and source.get('content_category') in ['clinical_trial', 'guideline']:
            issues.append("Falta fecha de publicación para contenido médico crítico")
            recommendations.append("Incluir fecha de publicación para evaluar vigencia")
    
    def _validate_currency(
        self,
        source: Dict[str, Any],
        issues: List[str],
        recommendations: List[str]
    ) -> None:
        """Valida la vigencia del contenido."""
        pub_date = source.get('publication_date')
        if not pub_date:
            return
        
        try:
            if isinstance(pub_date, str):
                pub_date = datetime.strptime(pub_date, '%Y-%m-%d').date()
            
            today = date.today()
            age_years = (today - pub_date).days / 365.25
            
            # Alertas por contenido desactualizado según categoría
            category = source.get('content_category', '')
            
            if category in ['drug_info', 'clinical_trial'] and age_years > 5:
                issues.append("Información de medicamentos/ensayos clínicos potencialmente desactualizada")
                recommendations.append("Verificar vigencia de información farmacológica")
            
            elif category == 'guideline' and age_years > 3:
                issues.append("Guías clínicas potencialmente desactualizadas")
                recommendations.append("Buscar versiones más recientes de las guías")
            
            elif age_years > 10:
                issues.append("Contenido médico muy desactualizado")
                recommendations.append("Priorizar fuentes más recientes")
                
        except (ValueError, AttributeError):
            issues.append("Formato de fecha inválido")
            recommendations.append("Verificar y corregir formato de fecha")
    
    def _get_domain_authority_score(self, domain: str) -> float:
        """Obtiene el score de autoridad para un dominio."""
        domain = domain.lower()
        
        # Buscar en dominios de alta autoridad
        if domain in self.high_authority_domains:
            return self.high_authority_domains[domain]
        
        # Buscar en dominios de autoridad media
        if domain in self.medium_authority_domains:
            return self.medium_authority_domains[domain]
        
        # Verificar patrones de dominios conocidos
        if any(pattern in domain for pattern in ['nih.gov', 'who.int', 'gov.it']):
            return 0.8
        
        if any(pattern in domain for pattern in ['.edu', '.org']):
            return 0.6
        
        if any(pattern in domain for pattern in ['.gov', '.mil']):
            return 0.7
        
        # Score por defecto para dominios desconocidos
        return 0.4
    
    async def calculate_relevance_score(
        self,
        content: str,
        search_term: str,
        context: Optional[str] = None
    ) -> float:
        """
        Calcula score de relevancia para contenido específico.
        
        Args:
            content: Contenido a evaluar
            search_term: Término de búsqueda
            context: Contexto opcional
            
        Returns:
            Score de relevancia (0-1)
        """
        if not content or not search_term:
            return 0.0
        
        content_lower = content.lower()
        term_lower = search_term.lower()
        
        # Relevancia básica por presencia del término
        base_score = 0.3 if term_lower in content_lower else 0.0
        
        # Relevancia por densidad del término
        term_count = content_lower.count(term_lower)
        word_count = len(content.split())
        if word_count > 0:
            density = (term_count / word_count) * 100
            if 0.5 <= density <= 2:
                base_score += 0.4
            elif density > 0:
                base_score += 0.2
        
        # Relevancia por contexto
        if context:
            context_words = re.findall(r'\b\w{4,}\b', context.lower())
            context_matches = sum(
                1 for word in context_words
                if word in content_lower
            )
            if context_words:
                context_score = (context_matches / len(context_words)) * 0.3
                base_score += context_score
        
        return min(1.0, base_score)
    
    async def verify_medical_accuracy(
        self,
        content: str,
        source_type: str
    ) -> Dict[str, Any]:
        """
        Verifica precisión médica del contenido.
        
        Args:
            content: Contenido a verificar
            source_type: Tipo de fuente
            
        Returns:
            Resultado de verificación
        """
        accuracy_score = 0.7  # Score base
        warnings = []
        
        # Verificaciones específicas por tipo de fuente
        if source_type in ['pubmed', 'who', 'nih']:
            accuracy_score = 0.9  # Fuentes de alta confianza
        elif source_type in ['webmd', 'healthline']:
            accuracy_score = 0.6  # Fuentes comerciales
        
        # Detectar contenido problemático
        if re.search(r'\b(miracle|cure|guaranteed)\b', content, re.IGNORECASE):
            accuracy_score -= 0.2
            warnings.append("Contiene afirmaciones médicas no verificables")
        
        # Verificar presencia de evidencia
        if re.search(r'\b(study|research|clinical trial|evidence)\b', content, re.IGNORECASE):
            accuracy_score += 0.1
        
        return {
            'accuracy_score': max(0.0, min(1.0, accuracy_score)),
            'warnings': warnings,
            'verified': accuracy_score >= 0.7
        }
