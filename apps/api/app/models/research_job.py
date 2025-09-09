"""
Modelo ResearchJob para trabajos de investigación médica automática.

Este modelo coordina la investigación de fuentes médicas para términos
detectados en el análisis LLM, gestionando el progreso y configuración
del proceso de research automático.
"""

import enum
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import BaseModel


class EstadoResearch(str, enum.Enum):
    """Estados posibles de un trabajo de investigación."""
    PENDING = "pending"           # Pendiente de iniciar
    EXTRACTING = "extracting"     # Extrayendo términos médicos
    CONFIGURING = "configuring"   # Configurando fuentes y parámetros
    CACHING = "caching"          # Verificando cache existente
    RESEARCHING = "researching"   # Investigando términos nuevos
    VALIDATING = "validating"     # Validando y rankeando fuentes
    SAVING = "saving"            # Guardando resultados en BD
    COMPLETED = "completed"       # Completado exitosamente
    FAILED = "failed"            # Error en el procesamiento
    CANCELLED = "cancelled"       # Cancelado por usuario


class PresetResearch(str, enum.Enum):
    """Presets de configuración para investigación médica."""
    COMPREHENSIVE = "COMPREHENSIVE"     # Búsqueda exhaustiva en todas las fuentes
    QUICK = "QUICK"                    # Búsqueda rápida en fuentes principales
    ACADEMIC = "ACADEMIC"              # Enfoque en artículos peer-reviewed
    CLINICAL = "CLINICAL"              # Enfoque en guías clínicas y tratamientos
    ITALIAN_FOCUSED = "ITALIAN_FOCUSED" # Prioridad a fuentes italianas


class ResearchJob(BaseModel):
    """
    Trabajo de investigación médica automática.
    
    Coordina la búsqueda de fuentes médicas verificadas para todos los
    términos detectados en un análisis LLM, gestionando progreso,
    configuración y métricas del proceso.
    """
    
    __tablename__ = "research_jobs"
    
    # ==============================================
    # RELACIÓN CON ANÁLISIS LLM
    # ==============================================
    
    llm_analysis_id = Column(
        PostgresUUID(as_uuid=True), 
        ForeignKey("llm_analysis_results.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    
    # ==============================================
    # CONFIGURACIÓN DEL RESEARCH
    # ==============================================
    
    # Preset de investigación utilizado
    research_preset = Column(String(50), nullable=False, default=PresetResearch.COMPREHENSIVE)
    
    # Prioridad del trabajo (normal, high, urgent)
    priority = Column(String(20), nullable=False, default="normal")
    
    # Idioma preferido para búsquedas
    language_preference = Column(String(10), nullable=False, default="it")
    
    # Fuentes habilitadas para este trabajo
    enabled_sources = Column(JSON, nullable=True)  # ["pubmed", "who", "nih", "italian_official"]
    
    # Límites de búsqueda
    max_sources_per_term = Column(Integer, nullable=False, default=3)
    max_search_results = Column(Integer, nullable=False, default=20)
    
    # ==============================================
    # ESTADO Y PROGRESO
    # ==============================================
    
    # Estado actual del trabajo
    status = Column(String(50), nullable=False, default=EstadoResearch.PENDING, index=True)
    
    # Progreso en porcentaje (0-100)
    progress_percentage = Column(Float, nullable=False, default=0.0)
    
    # Descripción del paso actual
    current_step = Column(String(200), nullable=True)
    
    # Término actualmente siendo investigado
    current_term = Column(String(200), nullable=True)
    
    # ==============================================
    # MÉTRICAS DE RESEARCH
    # ==============================================
    
    # Contadores de términos
    total_terms = Column(Integer, nullable=True)
    terms_researched = Column(Integer, nullable=False, default=0)
    terms_from_cache = Column(Integer, nullable=False, default=0)
    
    # Contadores de fuentes
    sources_found = Column(Integer, nullable=False, default=0)
    sources_validated = Column(Integer, nullable=False, default=0)
    
    # Métricas de cache
    cache_hits = Column(Integer, nullable=False, default=0)
    cache_misses = Column(Integer, nullable=False, default=0)
    
    # Métricas de calidad
    average_relevance_score = Column(Float, nullable=True)
    average_authority_score = Column(Float, nullable=True)
    
    # ==============================================
    # TIEMPOS DE EJECUCIÓN
    # ==============================================
    
    # Timestamps del proceso
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Duración total en segundos
    duration_seconds = Column(Float, nullable=True)
    
    # Tiempo estimado restante (calculado dinámicamente)
    estimated_remaining_seconds = Column(Float, nullable=True)
    
    # ==============================================
    # RESULTADOS Y ERRORES
    # ==============================================
    
    # Mensaje de error si el trabajo falló
    error_message = Column(Text, nullable=True)
    
    # Warnings y mensajes informativos
    warnings = Column(JSON, nullable=True)
    
    # Configuración detallada utilizada
    research_config = Column(JSON, nullable=True)
    
    # Estadísticas detalladas del proceso
    detailed_stats = Column(JSON, nullable=True)
    
    # ==============================================
    # METADATOS ADICIONALES
    # ==============================================
    
    # ID del worker Celery que procesó el trabajo
    celery_task_id = Column(String(100), nullable=True, index=True)
    
    # Versión del algoritmo de research utilizado
    algorithm_version = Column(String(20), nullable=False, default="1.0")
    
    # Flags de configuración específica
    include_related_terms = Column(Boolean, nullable=False, default=True)
    enable_translation = Column(Boolean, nullable=False, default=True)
    peer_review_only = Column(Boolean, nullable=False, default=False)
    clinical_guidelines_priority = Column(Boolean, nullable=False, default=False)
    italian_priority = Column(Boolean, nullable=False, default=False)
    
    # ==============================================
    # RELACIONES
    # ==============================================
    
    # Relación con el análisis LLM origen
    llm_analysis = relationship(
        "LLMAnalysisResult", 
        back_populates="research_jobs"
    )
    
    # Relación con los resultados de investigación
    research_results = relationship(
        "ResearchResult", 
        back_populates="research_job", 
        cascade="all, delete-orphan",
        order_by="ResearchResult.confidence_score.desc()"
    )
    
    # ==============================================
    # PROPIEDADES CALCULADAS
    # ==============================================
    
    @property
    def cache_hit_rate(self) -> float:
        """Calcula la tasa de aciertos del cache (0-1)."""
        total_requests = self.cache_hits + self.cache_misses
        if total_requests == 0:
            return 0.0
        return self.cache_hits / total_requests
    
    @property
    def terms_completion_rate(self) -> float:
        """Calcula el porcentaje de términos completados (0-1)."""
        if not self.total_terms or self.total_terms == 0:
            return 0.0
        return self.terms_researched / self.total_terms
    
    @property
    def sources_per_term_average(self) -> float:
        """Calcula el promedio de fuentes por término."""
        if self.terms_researched == 0:
            return 0.0
        return self.sources_found / self.terms_researched
    
    @property
    def is_active(self) -> bool:
        """Indica si el trabajo está actualmente en progreso."""
        return self.status in [
            EstadoResearch.EXTRACTING,
            EstadoResearch.CONFIGURING,
            EstadoResearch.CACHING,
            EstadoResearch.RESEARCHING,
            EstadoResearch.VALIDATING,
            EstadoResearch.SAVING
        ]
    
    @property
    def is_completed(self) -> bool:
        """Indica si el trabajo ha terminado (exitoso o fallido)."""
        return self.status in [
            EstadoResearch.COMPLETED,
            EstadoResearch.FAILED,
            EstadoResearch.CANCELLED
        ]
    
    @property
    def duration_minutes(self) -> Optional[float]:
        """Duración del trabajo en minutos."""
        if self.duration_seconds is None:
            return None
        return self.duration_seconds / 60.0
    
    def calculate_estimated_remaining(self) -> Optional[float]:
        """
        Calcula el tiempo estimado restante basado en progreso actual.
        
        Returns:
            Tiempo estimado restante en segundos, o None si no se puede calcular
        """
        if not self.started_at or self.progress_percentage <= 0:
            return None
            
        elapsed = (datetime.utcnow() - self.started_at).total_seconds()
        if self.progress_percentage >= 100:
            return 0.0
            
        # Estimación basada en progreso lineal
        total_estimated = elapsed / (self.progress_percentage / 100.0)
        remaining = total_estimated - elapsed
        
        return max(0.0, remaining)
    
    def get_preset_config(self) -> Dict[str, Any]:
        """
        Obtiene la configuración del preset utilizado.
        
        Returns:
            Diccionario con la configuración del preset
        """
        preset_configs = {
            PresetResearch.COMPREHENSIVE: {
                "description": "Búsqueda exhaustiva en todas las fuentes disponibles",
                "sources": ["pubmed", "who", "nih", "medlineplus", "italian_official"],
                "max_sources_per_term": 5,
                "include_related_terms": True,
                "enable_translation": True,
                "priority_score_threshold": 0.6,
                "estimated_duration_multiplier": 1.5
            },
            PresetResearch.QUICK: {
                "description": "Búsqueda rápida en fuentes principales",
                "sources": ["pubmed", "who", "italian_official"],
                "max_sources_per_term": 3,
                "include_related_terms": False,
                "enable_translation": False,
                "priority_score_threshold": 0.7,
                "estimated_duration_multiplier": 0.8
            },
            PresetResearch.ACADEMIC: {
                "description": "Enfoque en artículos académicos peer-reviewed",
                "sources": ["pubmed", "nih"],
                "max_sources_per_term": 4,
                "include_related_terms": True,
                "enable_translation": True,
                "priority_score_threshold": 0.8,
                "peer_review_only": True,
                "estimated_duration_multiplier": 1.2
            },
            PresetResearch.CLINICAL: {
                "description": "Enfoque en guías clínicas y tratamientos",
                "sources": ["who", "nih", "medlineplus", "italian_official"],
                "max_sources_per_term": 4,
                "include_related_terms": False,
                "enable_translation": True,
                "priority_score_threshold": 0.7,
                "clinical_guidelines_priority": True,
                "estimated_duration_multiplier": 1.0
            },
            PresetResearch.ITALIAN_FOCUSED: {
                "description": "Prioridad a fuentes médicas italianas oficiales",
                "sources": ["italian_official", "pubmed", "who"],
                "max_sources_per_term": 4,
                "include_related_terms": True,
                "enable_translation": False,
                "priority_score_threshold": 0.6,
                "italian_priority": True,
                "estimated_duration_multiplier": 0.9
            }
        }
        
        return preset_configs.get(self.research_preset, preset_configs[PresetResearch.COMPREHENSIVE])
    
    def update_progress(self, percentage: float, step: str, term: str = None) -> None:
        """
        Actualiza el progreso del trabajo de investigación.
        
        Args:
            percentage: Porcentaje de progreso (0-100)
            step: Descripción del paso actual
            term: Término actualmente siendo procesado (opcional)
        """
        self.progress_percentage = min(100.0, max(0.0, percentage))
        self.current_step = step
        if term:
            self.current_term = term
        
        # Actualizar tiempo estimado restante
        self.estimated_remaining_seconds = self.calculate_estimated_remaining()
    
    def mark_completed(self, success: bool = True, error_message: str = None) -> None:
        """
        Marca el trabajo como completado.
        
        Args:
            success: Si el trabajo se completó exitosamente
            error_message: Mensaje de error si falló
        """
        self.completed_at = func.now()
        
        if self.started_at:
            elapsed = (datetime.utcnow() - self.started_at).total_seconds()
            self.duration_seconds = elapsed
        
        if success:
            self.status = EstadoResearch.COMPLETED
            self.progress_percentage = 100.0
            self.current_step = "Research completado exitosamente"
        else:
            self.status = EstadoResearch.FAILED
            self.error_message = error_message
            self.current_step = f"Error: {error_message}" if error_message else "Error en procesamiento"
        
        self.estimated_remaining_seconds = 0.0
    
    def add_warning(self, warning_message: str, warning_type: str = "general") -> None:
        """
        Añade un warning al trabajo de investigación.
        
        Args:
            warning_message: Mensaje del warning
            warning_type: Tipo de warning (general, source, validation, etc.)
        """
        if self.warnings is None:
            self.warnings = []
        
        warning = {
            "type": warning_type,
            "message": warning_message,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.warnings.append(warning)
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas resumidas del trabajo de investigación.
        
        Returns:
            Diccionario con estadísticas clave
        """
        return {
            "research_job_id": str(self.id),
            "status": self.status,
            "progress_percentage": self.progress_percentage,
            "preset": self.research_preset,
            "total_terms": self.total_terms,
            "terms_researched": self.terms_researched,
            "sources_found": self.sources_found,
            "cache_hit_rate": self.cache_hit_rate,
            "average_relevance": self.average_relevance_score,
            "duration_minutes": self.duration_minutes,
            "estimated_remaining_seconds": self.estimated_remaining_seconds,
            "warnings_count": len(self.warnings) if self.warnings else 0
        }
    
    def __repr__(self) -> str:
        return (
            f"<ResearchJob(id={self.id}, "
            f"status={self.status}, "
            f"preset={self.research_preset}, "
            f"progress={self.progress_percentage}%, "
            f"terms={self.terms_researched}/{self.total_terms})>"
        )
