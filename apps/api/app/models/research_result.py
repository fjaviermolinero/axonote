"""
Modelo ResearchResult para resultados de investigación médica.

Este modelo almacena los resultados de investigación para un término médico
específico, incluyendo todas las fuentes encontradas, definiciones y
métricas de calidad del research automático.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey, Date
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import BaseModel


class ResearchResult(BaseModel):
    """
    Resultado de investigación para un término médico específico.
    
    Contiene todas las fuentes encontradas y validadas para un término
    médico detectado durante el análisis LLM, con definiciones,
    traducciones y métricas de calidad.
    """
    
    __tablename__ = "research_results"
    
    # ==============================================
    # RELACIÓN CON TRABAJO DE RESEARCH
    # ==============================================
    
    research_job_id = Column(
        PostgresUUID(as_uuid=True), 
        ForeignKey("research_jobs.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    
    # ==============================================
    # TÉRMINO INVESTIGADO
    # ==============================================
    
    # Término médico original
    medical_term = Column(String(200), nullable=False, index=True)
    
    # Término normalizado para búsquedas
    normalized_term = Column(String(200), nullable=False, index=True)
    
    # Categoría médica del término
    term_category = Column(String(100), nullable=True, index=True)  # anatomia, patologia, farmacologia, etc.
    
    # Subcategoría específica
    term_subcategory = Column(String(100), nullable=True)
    
    # Contexto original donde apareció el término
    original_context = Column(Text, nullable=True)
    
    # Posición en el texto original (para referencia)
    context_position = Column(Integer, nullable=True)
    
    # ==============================================
    # DEFINICIONES Y CONTENIDO
    # ==============================================
    
    # Definición principal (mejor fuente)
    primary_definition = Column(Text, nullable=True)
    
    # Fuente de la definición principal
    primary_source_type = Column(String(50), nullable=True)
    
    # Definiciones alternativas de otras fuentes
    alternative_definitions = Column(JSON, nullable=True)  # [{"source": "who", "definition": "...", "score": 0.9}]
    
    # Resumen consolidado de todas las definiciones
    consolidated_summary = Column(Text, nullable=True)
    
    # ==============================================
    # TRADUCCIONES
    # ==============================================
    
    # Definición en italiano (idioma principal)
    italian_definition = Column(Text, nullable=True)
    
    # Definición en español (para estudiantes)
    spanish_definition = Column(Text, nullable=True)
    
    # Definición en inglés (fuentes académicas)
    english_definition = Column(Text, nullable=True)
    
    # Términos equivalentes en otros idiomas
    multilingual_terms = Column(JSON, nullable=True)  # {"en": "term", "es": "término", "it": "termine"}
    
    # ==============================================
    # INFORMACIÓN CONTEXTUAL
    # ==============================================
    
    # Sinónimos encontrados
    synonyms = Column(JSON, nullable=True)  # ["sinonimo1", "sinonimo2"]
    
    # Términos relacionados
    related_terms = Column(JSON, nullable=True)  # ["término relacionado1", "término relacionado2"]
    
    # Abreviaciones y acrónimos
    abbreviations = Column(JSON, nullable=True)  # ["ABC", "DEF"]
    
    # Significancia clínica
    clinical_significance = Column(Text, nullable=True)
    
    # Información epidemiológica (si disponible)
    epidemiological_data = Column(JSON, nullable=True)
    
    # Información sobre tratamientos
    treatment_info = Column(Text, nullable=True)
    
    # Información sobre diagnóstico
    diagnostic_info = Column(Text, nullable=True)
    
    # ==============================================
    # MÉTRICAS DE CALIDAD
    # ==============================================
    
    # Score de confianza general (0-1)
    confidence_score = Column(Float, nullable=False, default=0.0, index=True)
    
    # Score de confiabilidad de las fuentes (0-1)
    source_reliability = Column(Float, nullable=False, default=0.0)
    
    # Score de frescura del contenido (0-1, basado en fechas)
    content_freshness = Column(Float, nullable=False, default=0.0)
    
    # Score de relevancia para el contexto original (0-1)
    context_relevance = Column(Float, nullable=False, default=0.0)
    
    # Score de completitud de la información (0-1)
    completeness_score = Column(Float, nullable=False, default=0.0)
    
    # Score de consenso entre fuentes (0-1)
    consensus_score = Column(Float, nullable=False, default=0.0)
    
    # ==============================================
    # METADATOS DE BÚSQUEDA
    # ==============================================
    
    # Queries de búsqueda que encontraron resultados
    search_queries_used = Column(JSON, nullable=True)  # ["query1", "query2"]
    
    # Queries que no encontraron resultados
    failed_queries = Column(JSON, nullable=True)
    
    # Tiempo total de búsqueda en milisegundos
    search_duration_ms = Column(Integer, nullable=True)
    
    # Número de fuentes consultadas
    sources_consulted = Column(Integer, nullable=False, default=0)
    
    # Número de fuentes que devolvieron resultados
    sources_with_results = Column(Integer, nullable=False, default=0)
    
    # Resultado obtenido del cache
    cache_hit = Column(Boolean, nullable=False, default=False)
    
    # Clave de cache utilizada
    cache_key = Column(String(128), nullable=True)
    
    # ==============================================
    # VALIDACIÓN Y REVISIÓN
    # ==============================================
    
    # Validación automática completada
    auto_validated = Column(Boolean, nullable=False, default=False)
    
    # Resultado de la validación automática
    auto_validation_score = Column(Float, nullable=True)
    
    # Notas de la validación automática
    auto_validation_notes = Column(Text, nullable=True)
    
    # Validación humana completada
    human_validated = Column(Boolean, nullable=False, default=False)
    
    # Notas de la validación humana
    validation_notes = Column(Text, nullable=True)
    
    # Usuario que validó
    validated_by = Column(String(100), nullable=True)
    
    # Fecha de validación humana
    validated_at = Column(DateTime, nullable=True)
    
    # Score asignado por el validador humano
    human_validation_score = Column(Float, nullable=True)
    
    # ==============================================
    # INFORMACIÓN DE ACTUALIZACIÓN
    # ==============================================
    
    # Última vez que se actualizó el contenido
    content_last_updated = Column(DateTime, nullable=False, default=func.now())
    
    # Versión del algoritmo de research utilizado
    research_algorithm_version = Column(String(20), nullable=False, default="1.0")
    
    # Hash del contenido para detectar cambios
    content_hash = Column(String(64), nullable=True)
    
    # Indica si necesita actualización
    needs_update = Column(Boolean, nullable=False, default=False)
    
    # Razón por la que necesita actualización
    update_reason = Column(String(200), nullable=True)
    
    # ==============================================
    # METADATOS ADICIONALES
    # ==============================================
    
    # Configuración específica utilizada para este término
    research_config = Column(JSON, nullable=True)
    
    # Estadísticas detalladas del proceso
    detailed_stats = Column(JSON, nullable=True)
    
    # Flags de características especiales
    is_rare_term = Column(Boolean, nullable=False, default=False)
    is_controversial = Column(Boolean, nullable=False, default=False)
    requires_expert_review = Column(Boolean, nullable=False, default=False)
    has_recent_updates = Column(Boolean, nullable=False, default=False)
    
    # ==============================================
    # RELACIONES
    # ==============================================
    
    # Relación con el trabajo de research
    research_job = relationship(
        "ResearchJob", 
        back_populates="research_results"
    )
    
    # Relación con las fuentes médicas encontradas
    medical_sources = relationship(
        "MedicalSource", 
        back_populates="research_result", 
        cascade="all, delete-orphan",
        order_by="MedicalSource.relevance_score.desc()"
    )
    
    # ==============================================
    # PROPIEDADES CALCULADAS
    # ==============================================
    
    @property
    def sources_count(self) -> int:
        """Número total de fuentes encontradas."""
        return len(self.medical_sources) if self.medical_sources else 0
    
    @property
    def validated_sources_count(self) -> int:
        """Número de fuentes validadas."""
        if not self.medical_sources:
            return 0
        return sum(1 for source in self.medical_sources if source.fact_checked)
    
    @property
    def peer_reviewed_sources_count(self) -> int:
        """Número de fuentes peer-reviewed."""
        if not self.medical_sources:
            return 0
        return sum(1 for source in self.medical_sources if source.peer_reviewed)
    
    @property
    def official_sources_count(self) -> int:
        """Número de fuentes oficiales."""
        if not self.medical_sources:
            return 0
        return sum(1 for source in self.medical_sources if source.official_source)
    
    @property
    def average_source_relevance(self) -> float:
        """Relevancia promedio de las fuentes."""
        if not self.medical_sources:
            return 0.0
        
        total_relevance = sum(source.relevance_score for source in self.medical_sources)
        return total_relevance / len(self.medical_sources)
    
    @property
    def best_source(self) -> Optional['MedicalSource']:
        """Obtiene la mejor fuente basada en scores combinados."""
        if not self.medical_sources:
            return None
        
        return max(
            self.medical_sources,
            key=lambda s: (s.relevance_score * 0.4 + s.authority_score * 0.4 + s.recency_score * 0.2)
        )
    
    @property
    def has_high_quality_sources(self) -> bool:
        """Indica si tiene fuentes de alta calidad."""
        return (
            self.official_sources_count > 0 or 
            self.peer_reviewed_sources_count > 0 or
            self.average_source_relevance > 0.8
        )
    
    @property
    def quality_grade(self) -> str:
        """Califica la calidad general del research (A-F)."""
        score = (
            self.confidence_score * 0.3 +
            self.source_reliability * 0.3 +
            self.completeness_score * 0.2 +
            self.consensus_score * 0.2
        )
        
        if score >= 0.9:
            return "A"
        elif score >= 0.8:
            return "B"
        elif score >= 0.7:
            return "C"
        elif score >= 0.6:
            return "D"
        else:
            return "F"
    
    def get_best_definition(self, language: str = "it") -> Optional[str]:
        """
        Obtiene la mejor definición en el idioma especificado.
        
        Args:
            language: Código de idioma (it, es, en)
            
        Returns:
            La mejor definición disponible en el idioma solicitado
        """
        if language == "it" and self.italian_definition:
            return self.italian_definition
        elif language == "es" and self.spanish_definition:
            return self.spanish_definition
        elif language == "en" and self.english_definition:
            return self.english_definition
        
        # Fallback a definición principal
        return self.primary_definition
    
    def get_sources_by_type(self, source_type: str) -> List['MedicalSource']:
        """
        Obtiene fuentes filtradas por tipo.
        
        Args:
            source_type: Tipo de fuente (pubmed, who, nih, etc.)
            
        Returns:
            Lista de fuentes del tipo especificado
        """
        if not self.medical_sources:
            return []
        
        return [source for source in self.medical_sources if source.source_type == source_type]
    
    def calculate_overall_quality_score(self) -> float:
        """
        Calcula un score de calidad general combinando todas las métricas.
        
        Returns:
            Score de calidad general (0-1)
        """
        # Pesos para diferentes aspectos de calidad
        weights = {
            'confidence': 0.25,
            'reliability': 0.25,
            'completeness': 0.20,
            'consensus': 0.15,
            'freshness': 0.10,
            'relevance': 0.05
        }
        
        score = (
            self.confidence_score * weights['confidence'] +
            self.source_reliability * weights['reliability'] +
            self.completeness_score * weights['completeness'] +
            self.consensus_score * weights['consensus'] +
            self.content_freshness * weights['freshness'] +
            self.context_relevance * weights['relevance']
        )
        
        return min(1.0, max(0.0, score))
    
    def needs_human_review(self) -> bool:
        """
        Determina si el resultado necesita revisión humana.
        
        Returns:
            True si necesita revisión humana
        """
        return (
            self.requires_expert_review or
            self.is_controversial or
            self.confidence_score < 0.7 or
            self.consensus_score < 0.6 or
            self.sources_count < 2
        )
    
    def get_summary_for_export(self) -> Dict[str, Any]:
        """
        Obtiene un resumen del resultado para export/visualización.
        
        Returns:
            Diccionario con información resumida
        """
        return {
            "term": self.medical_term,
            "category": self.term_category,
            "definition": self.get_best_definition("it"),
            "sources_count": self.sources_count,
            "quality_grade": self.quality_grade,
            "confidence_score": self.confidence_score,
            "has_official_sources": self.official_sources_count > 0,
            "peer_reviewed_count": self.peer_reviewed_sources_count,
            "synonyms": self.synonyms,
            "related_terms": self.related_terms,
            "clinical_significance": self.clinical_significance,
            "needs_review": self.needs_human_review()
        }
    
    def update_quality_metrics(self) -> None:
        """
        Actualiza las métricas de calidad basadas en las fuentes actuales.
        """
        if not self.medical_sources:
            return
        
        # Actualizar reliability basada en fuentes
        source_reliabilities = [source.authority_score for source in self.medical_sources]
        self.source_reliability = sum(source_reliabilities) / len(source_reliabilities)
        
        # Actualizar freshness basada en fechas de fuentes
        source_freshness = [source.recency_score for source in self.medical_sources]
        self.content_freshness = sum(source_freshness) / len(source_freshness)
        
        # Actualizar completeness basada en cantidad y variedad de fuentes
        unique_source_types = set(source.source_type for source in self.medical_sources)
        self.completeness_score = min(1.0, len(unique_source_types) / 3.0)  # Máximo con 3 tipos diferentes
        
        # Actualizar consensus basada en consistencia de definiciones
        # (Implementación simplificada - en producción sería más sofisticada)
        if len(self.medical_sources) > 1:
            self.consensus_score = 0.8  # Placeholder - requiere análisis de texto más avanzado
        else:
            self.consensus_score = 0.5
        
        # Actualizar confidence general
        self.confidence_score = self.calculate_overall_quality_score()
    
    def mark_for_update(self, reason: str) -> None:
        """
        Marca el resultado para actualización futura.
        
        Args:
            reason: Razón por la que necesita actualización
        """
        self.needs_update = True
        self.update_reason = reason
    
    def __repr__(self) -> str:
        return (
            f"<ResearchResult(id={self.id}, "
            f"term='{self.medical_term}', "
            f"category={self.term_category}, "
            f"sources={self.sources_count}, "
            f"quality={self.quality_grade}, "
            f"confidence={self.confidence_score:.2f})>"
        )
