"""
Modelo ClassSession - Sesión de clase grabada.
Entidad principal que representa una clase universitaria grabada y procesada.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Column, String, Text, Integer, Float, Date, 
    Enum, ForeignKey, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.models.base import BaseModel


class EstadoPipeline(str, enum.Enum):
    """Estados del pipeline de procesamiento."""
    UPLOADED = "uploaded"           # Audio subido, esperando procesamiento
    ASR = "asr"                    # Transcripción en proceso
    DIARIZATION = "diarization"    # Diarización en proceso  
    POSTPROCESS = "postprocess"    # Post-procesamiento léxico
    NLP = "nlp"                    # Procesamiento LLM en curso
    RESEARCH = "research"          # Ampliación con investigación
    NOTION = "notion"              # Sincronización con Notion
    EXPORT = "export"              # Generación de exports
    DONE = "done"                  # Completado exitosamente
    ERROR = "error"                # Error en el procesamiento


class ClassSession(BaseModel):
    """
    Sesión de clase universitaria grabada.
    
    Representa una clase completa con toda la información
    desde la grabación original hasta el contenido procesado.
    """
    
    __tablename__ = "class_sessions"
    
    # ==============================================
    # INFORMACIÓN BÁSICA DE LA CLASE
    # ==============================================
    
    fecha = Column(Date, nullable=False, index=True)
    asignatura = Column(String(200), nullable=False, index=True)
    tema = Column(String(500), nullable=False)
    profesor_text = Column(String(200), nullable=False)
    
    # Relación opcional con entidad Professor (si FEATURE_PROFESSOR_ENTITY=true)
    profesor_id = Column(UUID(as_uuid=True), ForeignKey("professors.id"), nullable=True)
    
    # ==============================================
    # INFORMACIÓN DEL AUDIO
    # ==============================================
    
    audio_url = Column(String(1000), nullable=True)  # URL en MinIO/storage
    duracion_sec = Column(Integer, nullable=True)    # Duración en segundos
    
    # ==============================================
    # RESULTADOS DE PROCESAMIENTO
    # ==============================================
    
    # Diarización (JSON con segments y speakers)
    diarizacion_json = Column(JSON, nullable=True)
    
    # Transcripción cruda con timestamps
    transcripcion_md = Column(Text, nullable=True)
    
    # Resumen en español con citas en idioma original
    resumen_md = Column(Text, nullable=True)
    
    # Ampliación con investigación médica
    ampliacion_md = Column(Text, nullable=True)
    
    # Glosario de términos médicos (JSON)
    glosario_json = Column(JSON, nullable=True)
    
    # Preguntas de autoevaluación (JSON)
    preguntas_json = Column(JSON, nullable=True)
    
    # Tarjetas de estudio/flashcards (JSON)
    tarjetas_json = Column(JSON, nullable=True)
    
    # ==============================================
    # MÉTRICAS DE CALIDAD
    # ==============================================
    
    confianza_asr = Column(Float, nullable=True)      # Confianza Whisper (0-1)
    confianza_llm = Column(Float, nullable=True)      # Confianza LLM (0-1)
    
    # ==============================================
    # ESTADO Y CONTROL
    # ==============================================
    
    estado_pipeline = Column(
        Enum(EstadoPipeline),
        nullable=False,
        default=EstadoPipeline.UPLOADED,
        index=True
    )
    
    # Información de errores (si estado=ERROR)
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    
    # ==============================================
    # INTEGRACIÓN NOTION
    # ==============================================
    
    notion_page_id = Column(String(100), nullable=True, index=True)
    notion_synced_at = Column(DateTime, nullable=True)
    
    # ==============================================
    # METADATOS ADICIONALES
    # ==============================================
    
    # Idioma detectado de la transcripción
    idioma_detectado = Column(String(10), nullable=True)
    
    # Número de palabras en la transcripción
    palabra_count = Column(Integer, nullable=True)
    
    # Tiempo total de procesamiento (segundos)
    tiempo_procesamiento_sec = Column(Integer, nullable=True)
    
    # Información de costes (si se usa OpenAI)
    costo_openai_eur = Column(Float, nullable=True)
    tokens_utilizados = Column(Integer, nullable=True)
    
    # ==============================================
    # RELACIONES
    # ==============================================
    
    # Relación con Professor (opcional)
    profesor = relationship("Professor", back_populates="class_sessions")
    
    # Relaciones con entidades relacionadas
    sources = relationship("Source", back_populates="class_session", cascade="all, delete-orphan")
    terms = relationship("Term", back_populates="class_session", cascade="all, delete-orphan")
    cards = relationship("Card", back_populates="class_session", cascade="all, delete-orphan")
    upload_sessions = relationship("UploadSession", back_populates="class_session", cascade="all, delete-orphan")
    
    # Nuevas relaciones Fase 9
    ocr_results = relationship("OCRResult", back_populates="class_session", cascade="all, delete-orphan")
    micro_memos = relationship("MicroMemo", back_populates="class_session", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return (
            f"<ClassSession("
            f"id={self.id}, "
            f"fecha={self.fecha}, "
            f"asignatura='{self.asignatura}', "
            f"tema='{self.tema[:50]}...', "
            f"estado='{self.estado_pipeline}'"
            f")>"
        )
    
    @property
    def duracion_minutos(self) -> Optional[int]:
        """Duración en minutos (calculada)."""
        return round(self.duracion_sec / 60) if self.duracion_sec else None
    
    @property
    def is_completed(self) -> bool:
        """True si el procesamiento está completado."""
        return self.estado_pipeline == EstadoPipeline.DONE
    
    @property
    def has_error(self) -> bool:
        """True si hay error en el procesamiento."""
        return self.estado_pipeline == EstadoPipeline.ERROR
    
    @property
    def progress_percentage(self) -> int:
        """Porcentaje de progreso del pipeline (0-100)."""
        pipeline_steps = list(EstadoPipeline)
        if self.estado_pipeline == EstadoPipeline.ERROR:
            return 0
        
        try:
            current_index = pipeline_steps.index(self.estado_pipeline)
            # ERROR no cuenta, DONE es 100%
            total_steps = len(pipeline_steps) - 2  # Restar ERROR y contar DONE como 100%
            if self.estado_pipeline == EstadoPipeline.DONE:
                return 100
            return int((current_index / total_steps) * 100)
        except ValueError:
            return 0
