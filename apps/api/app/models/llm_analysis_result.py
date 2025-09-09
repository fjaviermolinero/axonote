"""
Modelo para resultados de análisis LLM de transcripciones médicas.
Almacena resúmenes, conceptos clave y métricas de calidad.
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import BaseModel


class LLMAnalysisResult(BaseModel):
    """
    Resultado del análisis LLM de una transcripción médica.
    
    Almacena el análisis completo realizado por el LLM local o remoto,
    incluyendo resúmenes, conceptos clave, estructura de clase y métricas
    de calidad para validación automática.
    """
    
    __tablename__ = "llm_analysis_results"
    
    # Relaciones con otros modelos
    processing_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    transcription_result_id: Mapped[UUID] = mapped_column(
        ForeignKey("transcription_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Configuración del análisis LLM
    llm_provider: Mapped[str] = mapped_column(
        String(50), 
        nullable=False,
        comment="Proveedor LLM utilizado: 'local', 'openai'"
    )
    model_name: Mapped[str] = mapped_column(
        String(100), 
        nullable=False,
        comment="Nombre del modelo LLM específico"
    )
    analysis_preset: Mapped[str] = mapped_column(
        String(50), 
        nullable=False,
        default="MEDICAL_COMPREHENSIVE",
        comment="Preset de configuración utilizado"
    )
    
    # Resultados estructurados del análisis
    resumen_principal: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="Resumen principal de la clase en español"
    )
    conceptos_clave: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="Conceptos médicos clave identificados con definiciones"
    )
    estructura_clase: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="Estructura pedagógica identificada (intro, desarrollo, cierre)"
    )
    terminologia_medica: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="Terminología médica extraída con traducciones"
    )
    momentos_clave: Mapped[Optional[List[Dict]]] = mapped_column(
        JSON,
        default=list,
        comment="Momentos importantes de la clase con timestamps"
    )
    
    # Métricas de calidad del análisis
    confianza_llm: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Confianza general del análisis LLM (0.0-1.0)"
    )
    coherencia_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Puntuación de coherencia del contenido generado"
    )
    completitud_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Puntuación de completitud del análisis"
    )
    relevancia_medica: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Relevancia del contenido médico identificado"
    )
    
    # Flags de validación y revisión
    needs_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Indica si requiere revisión manual"
    )
    validated_by_human: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Indica si ha sido validado por un humano"
    )
    
    # Metadatos de procesamiento
    tiempo_procesamiento: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Tiempo de procesamiento en segundos"
    )
    tokens_utilizados: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Número de tokens utilizados en el análisis"
    )
    costo_estimado: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Costo estimado del análisis en EUR"
    )
    
    # Configuración utilizada (para reproducibilidad)
    llm_config: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="Configuración completa utilizada para el análisis"
    )
    
    # Relaciones
    processing_job = relationship("ProcessingJob", back_populates="llm_analysis_results")
    transcription_result = relationship("TranscriptionResult", back_populates="llm_analysis_results")
    research_jobs = relationship("ResearchJob", back_populates="llm_analysis", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return (
            f"<LLMAnalysisResult("
            f"id={self.id}, "
            f"provider={self.llm_provider}, "
            f"model={self.model_name}, "
            f"confianza={self.confianza_llm:.2f}"
            f")>"
        )
    
    @property
    def is_high_quality(self) -> bool:
        """Determina si el análisis es de alta calidad."""
        return (
            self.confianza_llm >= 0.8 and
            self.coherencia_score >= 0.7 and
            self.completitud_score >= 0.6
        )
    
    @property
    def quality_summary(self) -> Dict[str, any]:
        """Resumen de métricas de calidad."""
        return {
            "confianza_llm": self.confianza_llm,
            "coherencia_score": self.coherencia_score,
            "completitud_score": self.completitud_score,
            "relevancia_medica": self.relevancia_medica,
            "is_high_quality": self.is_high_quality,
            "needs_review": self.needs_review,
            "validated_by_human": self.validated_by_human
        }
