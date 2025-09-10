"""
Modelo ExportSession - Sesión de exportación multi-modal.
Representa una sesión de exportación de contenido en múltiples formatos.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, 
    ForeignKey, JSON, DateTime
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class ExportFormat(str, Enum):
    """Formatos de exportación disponibles."""
    PDF = "pdf"                    # PDF médico académico
    DOCX = "docx"                 # Word profesional  
    JSON = "json"                 # JSON API completo
    ANKI = "anki"                 # Package Anki (.apkg)
    CSV = "csv"                   # Dataset CSV para análisis
    HTML = "html"                 # Reporte HTML interactivo


class EstadoExport(str, Enum):
    """Estados de procesamiento de export."""
    PENDING = "pending"           # Pendiente de procesamiento
    PROCESSING = "processing"     # En procesamiento
    COMPLETED = "completed"       # Completado exitosamente
    FAILED = "failed"            # Falló el procesamiento
    CANCELLED = "cancelled"       # Cancelado por usuario
    EXPIRED = "expired"          # Expirado (limpieza automática)


class TipoTemplate(str, Enum):
    """Tipos de templates disponibles."""
    MEDICAL_ACADEMIC = "medical_academic"      # Template académico médico
    CLINICAL_REPORT = "clinical_report"       # Reporte clínico profesional
    STUDY_CARDS = "study_cards"              # Tarjetas de estudio
    RESEARCH_PAPER = "research_paper"        # Paper de investigación
    PRESENTATION = "presentation"            # Template presentación
    CUSTOM = "custom"                       # Template personalizado


class ExportSession(BaseModel):
    """
    Sesión de exportación multi-modal.
    Gestiona la exportación de contenido de una clase en diferentes formatos.
    """
    
    __tablename__ = "export_sessions"
    
    # Relación con clase
    class_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("class_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Configuración de export
    export_format = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Formato de exportación (pdf, docx, json, anki, csv, html)"
    )
    
    template_name = Column(
        String(100),
        nullable=False,
        default="medical_academic",
        comment="Nombre del template usado"
    )
    
    template_type = Column(
        String(50),
        nullable=False,
        default="medical_academic",
        index=True,
        comment="Tipo de template aplicado"
    )
    
    # Configuración y filtros aplicados
    filters_applied = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Filtros y configuración aplicados en el export"
    )
    
    export_config = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Configuración específica del formato de export"
    )
    
    # Estado y progreso
    status = Column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        comment="Estado actual del procesamiento"
    )
    
    progress_percentage = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Porcentaje de progreso (0.0-100.0)"
    )
    
    estimated_completion = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Tiempo estimado de finalización"
    )
    
    error_message = Column(
        Text,
        nullable=True,
        comment="Mensaje de error si falló el procesamiento"
    )
    
    # Resultado del export
    output_files = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Lista de archivos generados con metadata"
    )
    
    total_size_bytes = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Tamaño total en bytes de todos los archivos"
    )
    
    storage_path = Column(
        String(500),
        nullable=True,
        comment="Path base donde se almacenan los archivos"
    )
    
    # Métricas de procesamiento
    processing_time_seconds = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Tiempo total de procesamiento en segundos"
    )
    
    elements_exported = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Número total de elementos exportados"
    )
    
    quality_score = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Score de calidad del export (0.0-1.0)"
    )
    
    # Contadores específicos por tipo de contenido
    transcriptions_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Número de transcripciones incluidas"
    )
    
    ocr_results_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Número de resultados OCR incluidos"
    )
    
    micro_memos_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Número de micro-memos incluidos"
    )
    
    research_results_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Número de resultados de research incluidos"
    )
    
    # Metadata de export
    export_title = Column(
        String(200),
        nullable=True,
        comment="Título personalizado del export"
    )
    
    export_description = Column(
        Text,
        nullable=True,
        comment="Descripción del contenido exportado"
    )
    
    language = Column(
        String(10),
        nullable=False,
        default="ita",
        comment="Idioma del contenido exportado"
    )
    
    # Configuración de TTS (si incluye audio)
    include_tts = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Si incluye síntesis de voz"
    )
    
    tts_config = Column(
        JSON,
        nullable=True,
        comment="Configuración específica para TTS"
    )
    
    # Timestamps específicos
    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Momento de inicio del procesamiento"
    )
    
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Momento de finalización del procesamiento"
    )
    
    expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Momento de expiración para limpieza automática"
    )
    
    # Información de usuario/institución
    user_metadata = Column(
        JSON,
        nullable=True,
        comment="Metadata del usuario que solicitó el export"
    )
    
    institutional_config = Column(
        JSON,
        nullable=True,
        comment="Configuración institucional (logos, headers, etc.)"
    )
    
    # Relationships
    class_session = relationship(
        "ClassSession",
        back_populates="export_sessions",
        lazy="select"
    )
    
    tts_results = relationship(
        "TTSResult",
        back_populates="export_session",
        cascade="all, delete-orphan",
        lazy="select"
    )
    
    # Propiedades computadas
    @property
    def is_completed(self) -> bool:
        """Indica si el export está completado."""
        return self.status == EstadoExport.COMPLETED
    
    @property
    def is_processing(self) -> bool:
        """Indica si el export está en procesamiento."""
        return self.status == EstadoExport.PROCESSING
    
    @property
    def has_failed(self) -> bool:
        """Indica si el export falló."""
        return self.status == EstadoExport.FAILED
    
    @property
    def is_expired(self) -> bool:
        """Indica si el export ha expirado."""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    @property
    def total_content_elements(self) -> int:
        """Número total de elementos de contenido."""
        return (
            self.transcriptions_count +
            self.ocr_results_count +
            self.micro_memos_count +
            self.research_results_count
        )
    
    @property
    def format_display_name(self) -> str:
        """Nombre legible del formato."""
        format_names = {
            ExportFormat.PDF: "PDF Académico",
            ExportFormat.DOCX: "Word Profesional",
            ExportFormat.JSON: "JSON Completo",
            ExportFormat.ANKI: "Package Anki",
            ExportFormat.CSV: "Dataset CSV",
            ExportFormat.HTML: "Reporte HTML"
        }
        return format_names.get(self.export_format, self.export_format.upper())
    
    def __repr__(self) -> str:
        return (
            f"<ExportSession("
            f"id={self.id}, "
            f"format={self.export_format}, "
            f"status={self.status}, "
            f"elements={self.total_content_elements}"
            f")>"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte el modelo a diccionario con información completa."""
        base_dict = super().to_dict()
        
        # Añadir propiedades computadas
        base_dict.update({
            "is_completed": self.is_completed,
            "is_processing": self.is_processing,
            "has_failed": self.has_failed,
            "is_expired": self.is_expired,
            "total_content_elements": self.total_content_elements,
            "format_display_name": self.format_display_name
        })
        
        return base_dict
