"""
Modelo TTSResult - Resultado de síntesis de voz (TTS).
Representa el audio generado desde micro-memos y otro contenido textual.
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


class TipoTTS(str, Enum):
    """Tipos de síntesis TTS disponibles."""
    INDIVIDUAL = "individual"         # TTS de micro-memo individual
    COLLECTION = "collection"         # TTS de colección completa
    STUDY_SESSION = "study_session"   # TTS para sesión de estudio
    BATCH = "batch"                  # TTS masivo/batch
    CUSTOM = "custom"                # TTS personalizado


class EstadoTTS(str, Enum):
    """Estados de procesamiento TTS."""
    PENDING = "pending"              # Pendiente de síntesis
    PROCESSING = "processing"        # En procesamiento
    COMPLETED = "completed"          # Completado exitosamente
    FAILED = "failed"               # Falló la síntesis
    CANCELLED = "cancelled"          # Cancelado por usuario


class CalidadAudio(str, Enum):
    """Niveles de calidad de audio."""
    LOW = "low"                     # 16kHz, 64kbps - para previews
    MEDIUM = "medium"               # 22kHz, 128kbps - estándar
    HIGH = "high"                   # 44kHz, 192kbps - alta calidad
    STUDIO = "studio"               # 48kHz, 320kbps - calidad estudio


class ModoEstudio(str, Enum):
    """Modos de estudio para TTS."""
    SEQUENTIAL = "sequential"        # Secuencial simple
    QUESTION_PAUSE = "question_pause" # Pregunta + pausa + respuesta
    SPACED_REPETITION = "spaced_repetition" # Con algoritmo de repetición
    ADAPTIVE = "adaptive"            # Adaptativo según performance
    REVIEW_ONLY = "review_only"      # Solo revisión rápida


class TTSResult(BaseModel):
    """
    Resultado de síntesis de voz (TTS).
    Almacena el audio generado desde contenido textual médico.
    """
    
    __tablename__ = "tts_results"
    
    # Relaciones opcionales (puede estar asociado a diferentes fuentes)
    export_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("export_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Export session asociada (si aplica)"
    )
    
    micro_memo_id = Column(
        UUID(as_uuid=True),
        ForeignKey("micro_memos.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Micro-memo fuente (para TTS individual)"
    )
    
    collection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("micro_memo_collections.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Colección fuente (para TTS de colección)"
    )
    
    class_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("class_sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Clase asociada para organización"
    )
    
    # Configuración TTS
    tts_type = Column(
        String(50),
        nullable=False,
        default="individual",
        index=True,
        comment="Tipo de síntesis realizada"
    )
    
    voice_model = Column(
        String(100),
        nullable=False,
        default="it_riccardo_quality",
        comment="Modelo de voz utilizado"
    )
    
    language = Column(
        String(10),
        nullable=False,
        default="ita",
        comment="Idioma del contenido sintetizado"
    )
    
    speed_factor = Column(
        Float,
        nullable=False,
        default=1.0,
        comment="Factor de velocidad aplicado (0.5-2.0)"
    )
    
    # Contenido textual
    original_text = Column(
        Text,
        nullable=False,
        comment="Texto original antes de normalización"
    )
    
    normalized_text = Column(
        Text,
        nullable=False,
        comment="Texto normalizado para TTS (con SSML si aplica)"
    )
    
    # Estado y progreso
    status = Column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
        comment="Estado actual del procesamiento TTS"
    )
    
    progress_percentage = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Porcentaje de progreso (0.0-100.0)"
    )
    
    error_message = Column(
        Text,
        nullable=True,
        comment="Mensaje de error si falló la síntesis"
    )
    
    # Resultado de audio
    audio_file_path = Column(
        String(500),
        nullable=True,
        comment="Path del archivo de audio generado"
    )
    
    audio_format = Column(
        String(10),
        nullable=False,
        default="mp3",
        comment="Formato del archivo de audio"
    )
    
    audio_quality = Column(
        String(20),
        nullable=False,
        default="medium",
        comment="Calidad del audio generado"
    )
    
    duration_seconds = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Duración del audio en segundos"
    )
    
    file_size_bytes = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Tamaño del archivo de audio en bytes"
    )
    
    # Métricas de calidad y performance
    synthesis_quality = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Score de calidad de síntesis (0.0-1.0)"
    )
    
    processing_time_seconds = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Tiempo de procesamiento en segundos"
    )
    
    confidence_score = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Confianza en la pronunciación médica (0.0-1.0)"
    )
    
    words_per_minute = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Velocidad de habla en palabras por minuto"
    )
    
    # Configuración avanzada TTS
    ssml_applied = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Si se aplicó SSML para énfasis y pausas"
    )
    
    medical_pronunciation = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Si se aplicó normalización médica"
    )
    
    # Estructura de contenido (para colecciones/sesiones)
    has_chapters = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Si el audio tiene marcadores de capítulos"
    )
    
    chapter_markers = Column(
        JSON,
        nullable=True,
        comment="Marcadores de capítulos con timestamps"
    )
    
    content_structure = Column(
        JSON,
        nullable=True,
        comment="Estructura del contenido (memos, pausas, etc.)"
    )
    
    # Configuración para estudio
    study_mode = Column(
        String(50),
        nullable=True,
        comment="Modo de estudio aplicado (si aplica)"
    )
    
    pause_duration_ms = Column(
        Integer,
        nullable=False,
        default=1000,
        comment="Duración de pausas en milisegundos"
    )
    
    question_pause_ms = Column(
        Integer,
        nullable=False,
        default=3000,
        comment="Pausa después de preguntas en milisegundos"
    )
    
    # Metadata adicional
    medical_terms_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Número de términos médicos procesados"
    )
    
    abbreviations_expanded = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Número de abreviaciones expandidas"
    )
    
    custom_pronunciations = Column(
        JSON,
        nullable=True,
        comment="Pronunciaciones personalizadas aplicadas"
    )
    
    # Configuración de compresión y calidad
    bitrate_kbps = Column(
        Integer,
        nullable=False,
        default=128,
        comment="Bitrate del audio en kbps"
    )
    
    sample_rate_hz = Column(
        Integer,
        nullable=False,
        default=22050,
        comment="Frecuencia de muestreo en Hz"
    )
    
    channels = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Número de canales (1=mono, 2=stereo)"
    )
    
    # Timestamps específicos
    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Momento de inicio de la síntesis"
    )
    
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Momento de finalización de la síntesis"
    )
    
    # Relationships
    export_session = relationship(
        "ExportSession",
        back_populates="tts_results",
        lazy="select"
    )
    
    micro_memo = relationship(
        "MicroMemo",
        lazy="select"
    )
    
    collection = relationship(
        "MicroMemoCollection",
        lazy="select"
    )
    
    class_session = relationship(
        "ClassSession",
        lazy="select"
    )
    
    # Propiedades computadas
    @property
    def is_completed(self) -> bool:
        """Indica si la síntesis está completada."""
        return self.status == EstadoTTS.COMPLETED
    
    @property
    def is_processing(self) -> bool:
        """Indica si la síntesis está en procesamiento."""
        return self.status == EstadoTTS.PROCESSING
    
    @property
    def has_failed(self) -> bool:
        """Indica si la síntesis falló."""
        return self.status == EstadoTTS.FAILED
    
    @property
    def duration_formatted(self) -> str:
        """Duración formateada como MM:SS."""
        if self.duration_seconds <= 0:
            return "00:00"
        
        minutes = int(self.duration_seconds // 60)
        seconds = int(self.duration_seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    @property
    def file_size_mb(self) -> float:
        """Tamaño del archivo en MB."""
        return self.file_size_bytes / (1024 * 1024) if self.file_size_bytes > 0 else 0.0
    
    @property
    def processing_speed_ratio(self) -> float:
        """Ratio de velocidad de procesamiento (duration/processing_time)."""
        if self.processing_time_seconds <= 0:
            return 0.0
        return self.duration_seconds / self.processing_time_seconds
    
    @property
    def audio_quality_display(self) -> str:
        """Descripción legible de la calidad de audio."""
        quality_descriptions = {
            CalidadAudio.LOW: "Baja (16kHz, 64kbps)",
            CalidadAudio.MEDIUM: "Media (22kHz, 128kbps)",
            CalidadAudio.HIGH: "Alta (44kHz, 192kbps)",
            CalidadAudio.STUDIO: "Estudio (48kHz, 320kbps)"
        }
        return quality_descriptions.get(self.audio_quality, f"Personalizada ({self.sample_rate_hz}Hz, {self.bitrate_kbps}kbps)")
    
    @property
    def content_type_display(self) -> str:
        """Descripción del tipo de contenido."""
        if self.micro_memo_id:
            return "Micro-memo Individual"
        elif self.collection_id:
            return "Colección de Micro-memos"
        elif self.tts_type == TipoTTS.STUDY_SESSION:
            return "Sesión de Estudio"
        elif self.tts_type == TipoTTS.BATCH:
            return "Procesamiento Masivo"
        else:
            return "Contenido Personalizado"
    
    def __repr__(self) -> str:
        return (
            f"<TTSResult("
            f"id={self.id}, "
            f"type={self.tts_type}, "
            f"status={self.status}, "
            f"duration={self.duration_formatted}"
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
            "duration_formatted": self.duration_formatted,
            "file_size_mb": self.file_size_mb,
            "processing_speed_ratio": self.processing_speed_ratio,
            "audio_quality_display": self.audio_quality_display,
            "content_type_display": self.content_type_display
        })
        
        return base_dict
