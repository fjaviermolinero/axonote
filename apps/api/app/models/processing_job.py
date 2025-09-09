"""
Modelo de base de datos para trabajos de procesamiento de IA.
Gestiona el pipeline completo de ASR y diarización.
"""

import enum
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Enum, Float, Integer, JSON, String, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import BaseModel


class TipoProcesamiento(str, enum.Enum):
    """Tipos de procesamiento disponibles."""
    ASR_ONLY = "asr_only"
    DIARIZATION_ONLY = "diarization_only"
    FULL_PIPELINE = "full_pipeline"
    REPROCESS_ASR = "reprocess_asr"
    REPROCESS_DIARIZATION = "reprocess_diarization"


class PrioridadProcesamiento(str, enum.Enum):
    """Prioridades de procesamiento."""
    URGENT = "urgent"      # Procesamiento inmediato
    HIGH = "high"          # Alta prioridad
    NORMAL = "normal"      # Prioridad normal
    LOW = "low"           # Baja prioridad
    BATCH = "batch"       # Procesamiento en lote


class EstadoProcesamiento(str, enum.Enum):
    """Estados del procesamiento."""
    PENDIENTE = "pendiente"
    PROCESANDO = "procesando"
    COMPLETADO = "completado"
    ERROR = "error"
    CANCELADO = "cancelado"
    PAUSADO = "pausado"


class EtapaProcesamiento(str, enum.Enum):
    """Etapas del pipeline de procesamiento."""
    VALIDACION = "validacion"
    NORMALIZACION = "normalizacion"
    VAD = "vad"
    ASR = "asr"
    DIARIZACION = "diarizacion"
    FUSION = "fusion"
    POST_PROCESSING = "post_processing"
    FINALIZACION = "finalizacion"


class ProcessingJob(BaseModel):
    """
    Modelo para gestión completa de trabajos de procesamiento de IA.
    Controla todo el pipeline desde upload hasta resultados finales.
    """
    __tablename__ = "processing_jobs"

    # Información básica
    id: UUID = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    class_session_id: UUID = Column(
        PostgresUUID(as_uuid=True), 
        nullable=False,
        comment="Relación con ClassSession"
    )
    
    # Configuración del job
    tipo_procesamiento: TipoProcesamiento = Column(
        Enum(TipoProcesamiento),
        nullable=False,
        default=TipoProcesamiento.FULL_PIPELINE,
        comment="Tipo de procesamiento a realizar"
    )
    prioridad: PrioridadProcesamiento = Column(
        Enum(PrioridadProcesamiento),
        nullable=False,
        default=PrioridadProcesamiento.NORMAL,
        comment="Prioridad en la cola de procesamiento"
    )
    
    # Estado del procesamiento
    estado: EstadoProcesamiento = Column(
        Enum(EstadoProcesamiento),
        nullable=False,
        default=EstadoProcesamiento.PENDIENTE,
        comment="Estado actual del procesamiento"
    )
    progreso_porcentaje: Float = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Progreso del procesamiento (0.0-100.0)"
    )
    etapa_actual: Optional[EtapaProcesamiento] = Column(
        Enum(EtapaProcesamiento),
        nullable=True,
        comment="Etapa actual del pipeline"
    )
    
    # Configuraciones de IA
    config_whisper: Dict[str, Any] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Configuración específica para Whisper ASR"
    )
    config_diarizacion: Dict[str, Any] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Configuración para diarización de speakers"
    )
    usar_vad: Boolean = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Usar Voice Activity Detection"
    )
    usar_alineacion_temporal: Boolean = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Generar timestamps a nivel de palabra"
    )
    
    # Archivos y rutas
    ruta_audio_original: String = Column(
        String(512),
        nullable=False,
        comment="Ruta del audio original subido"
    )
    ruta_audio_normalizado: Optional[String] = Column(
        String(512),
        nullable=True,
        comment="Ruta del audio normalizado para procesamiento"
    )
    chunks_audio: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Lista de chunks de audio para procesamiento"
    )
    
    # Metadatos del audio
    duracion_audio_sec: Optional[Float] = Column(
        Float,
        nullable=True,
        comment="Duración del audio en segundos"
    )
    sample_rate: Optional[Integer] = Column(
        Integer,
        nullable=True,
        comment="Sample rate del audio"
    )
    canales: Optional[Integer] = Column(
        Integer,
        nullable=True,
        comment="Número de canales del audio"
    )
    
    # Resultados de procesamiento
    transcripcion_completa: Optional[Dict[str, Any]] = Column(
        JSON,
        nullable=True,
        comment="Resultado completo de ASR con metadatos"
    )
    diarizacion_completa: Optional[Dict[str, Any]] = Column(
        JSON,
        nullable=True,
        comment="Resultado completo de diarización"
    )
    resultado_fusion: Optional[Dict[str, Any]] = Column(
        JSON,
        nullable=True,
        comment="Resultado de fusión ASR + diarización"
    )
    
    # Métricas de calidad
    metricas_calidad: Dict[str, Any] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Métricas de confianza y calidad del procesamiento"
    )
    confianza_global: Optional[Float] = Column(
        Float,
        nullable=True,
        comment="Confianza global del procesamiento (0.0-1.0)"
    )
    
    # Timing y rendimiento
    tiempo_inicio: Optional[DateTime] = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp de inicio del procesamiento"
    )
    tiempo_fin: Optional[DateTime] = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp de finalización"
    )
    tiempo_estimado_sec: Optional[Integer] = Column(
        Integer,
        nullable=True,
        comment="Tiempo estimado de procesamiento en segundos"
    )
    tiempo_procesamiento_total_sec: Optional[Float] = Column(
        Float,
        nullable=True,
        comment="Tiempo real de procesamiento total"
    )
    
    # Gestión de errores
    errores: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Log estructurado de errores encontrados"
    )
    error_actual: Optional[String] = Column(
        Text,
        nullable=True,
        comment="Descripción del error actual si existe"
    )
    reintentos: Integer = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Número de reintentos realizados"
    )
    max_reintentos: Integer = Column(
        Integer,
        nullable=False,
        default=3,
        comment="Máximo número de reintentos permitidos"
    )
    
    # Hardware y optimización
    device_usado: Optional[String] = Column(
        String(50),
        nullable=True,
        comment="Device usado para procesamiento (cuda/cpu)"
    )
    memoria_gpu_usada_mb: Optional[Integer] = Column(
        Integer,
        nullable=True,
        comment="Memoria GPU utilizada en MB"
    )
    tiempo_gpu_sec: Optional[Float] = Column(
        Float,
        nullable=True,
        comment="Tiempo de GPU utilizado en segundos"
    )
    
    # Worker y task management
    celery_task_id: Optional[String] = Column(
        String(255),
        nullable=True,
        comment="ID de la tarea Celery asociada"
    )
    worker_node: Optional[String] = Column(
        String(255),
        nullable=True,
        comment="Nodo worker que procesó el job"
    )
    
    # Timestamps automáticos
    created_at: DateTime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        comment="Timestamp de creación del job"
    )
    updated_at: DateTime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Timestamp de última actualización"
    )
    
    # Expiración y cleanup
    expires_at: Optional[DateTime] = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp de expiración del job"
    )
    
    def __repr__(self) -> str:
        return (
            f"<ProcessingJob(id={self.id}, "
            f"class_session_id={self.class_session_id}, "
            f"estado={self.estado}, "
            f"progreso={self.progreso_porcentaje}%)>"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para APIs."""
        return {
            "id": str(self.id),
            "class_session_id": str(self.class_session_id),
            "tipo_procesamiento": self.tipo_procesamiento.value,
            "prioridad": self.prioridad.value,
            "estado": self.estado.value,
            "progreso_porcentaje": self.progreso_porcentaje,
            "etapa_actual": self.etapa_actual.value if self.etapa_actual else None,
            "duracion_audio_sec": self.duracion_audio_sec,
            "confianza_global": self.confianza_global,
            "tiempo_inicio": self.tiempo_inicio.isoformat() if self.tiempo_inicio else None,
            "tiempo_fin": self.tiempo_fin.isoformat() if self.tiempo_fin else None,
            "tiempo_procesamiento_total_sec": self.tiempo_procesamiento_total_sec,
            "reintentos": self.reintentos,
            "max_reintentos": self.max_reintentos,
            "error_actual": self.error_actual,
            "device_usado": self.device_usado,
            "memoria_gpu_usada_mb": self.memoria_gpu_usada_mb,
            "celery_task_id": self.celery_task_id,
            "worker_node": self.worker_node,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }
    
    @property
    def es_completado(self) -> bool:
        """Verificar si el procesamiento está completado."""
        return self.estado == EstadoProcesamiento.COMPLETADO
    
    @property
    def tiene_error(self) -> bool:
        """Verificar si hay errores."""
        return self.estado == EstadoProcesamiento.ERROR or bool(self.error_actual)
    
    @property
    def puede_reintentar(self) -> bool:
        """Verificar si puede reintentarse."""
        return self.reintentos < self.max_reintentos and self.tiene_error
    
    @property
    def tiempo_transcurrido_sec(self) -> Optional[float]:
        """Calcular tiempo transcurrido desde inicio."""
        if not self.tiempo_inicio:
            return None
        
        tiempo_fin = self.tiempo_fin or datetime.utcnow()
        return (tiempo_fin - self.tiempo_inicio).total_seconds()
    
    @property
    def tiempo_restante_estimado_sec(self) -> Optional[int]:
        """Estimar tiempo restante basado en progreso."""
        if not self.tiempo_estimado_sec or self.progreso_porcentaje <= 0:
            return None
        
        tiempo_transcurrido = self.tiempo_transcurrido_sec
        if not tiempo_transcurrido:
            return self.tiempo_estimado_sec
        
        # Calcular tiempo restante basado en progreso actual
        tiempo_total_estimado = tiempo_transcurrido / (self.progreso_porcentaje / 100)
        tiempo_restante = max(0, tiempo_total_estimado - tiempo_transcurrido)
        
        return int(tiempo_restante)
    
    # Relaciones con otros modelos
    transcription_results = relationship("TranscriptionResult", back_populates="processing_job")
    diarization_results = relationship("DiarizationResult", back_populates="processing_job") 
    llm_analysis_results = relationship("LLMAnalysisResult", back_populates="processing_job")
    post_processing_results = relationship("PostProcessingResult", back_populates="processing_job")