"""
Modelo de base de datos para resultados de transcripción (ASR).
Almacena resultados detallados de Whisper con metadatos de calidad.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import BaseModel


class TranscriptionResult(BaseModel):
    """
    Modelo para almacenar resultados detallados de transcripción con Whisper.
    Incluye texto, segmentos, timestamps y métricas de calidad.
    """
    __tablename__ = "transcription_results"

    # Identificación
    id: UUID = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    processing_job_id: UUID = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="CASCADE"),
        nullable=False,
        comment="Relación con ProcessingJob"
    )
    
    # Transcripción principal
    texto_completo: String = Column(
        Text,
        nullable=False,
        comment="Transcripción completa final limpia"
    )
    texto_raw: String = Column(
        Text,
        nullable=True,
        comment="Transcripción sin procesar directa de Whisper"
    )
    idioma_detectado: String = Column(
        String(10),
        nullable=False,
        comment="Código de idioma detectado (it, en, es, etc.)"
    )
    confianza_global: Float = Column(
        Float,
        nullable=False,
        comment="Confianza promedio global (0.0-1.0)"
    )
    
    # Segmentos estructurados
    segmentos: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Lista de segmentos con timestamps y texto"
    )
    palabras_con_timestamps: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Alineación temporal a nivel de palabra"
    )
    
    # Métricas básicas
    num_palabras: Integer = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Número total de palabras transcribidas"
    )
    num_segmentos: Integer = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Número de segmentos de audio procesados"
    )
    duracion_audio_sec: Float = Column(
        Float,
        nullable=False,
        comment="Duración total del audio en segundos"
    )
    palabras_por_minuto: Float = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Velocidad de habla calculada (WPM)"
    )
    
    # Análisis de calidad
    nivel_ruido_estimado: Float = Column(
        Float,
        nullable=True,
        comment="Nivel de ruido estimado en el audio (0.0-1.0)"
    )
    calidad_audio_estimada: String = Column(
        String(20),
        nullable=True,
        comment="Calidad estimada: high, medium, low"
    )
    segmentos_con_baja_confianza: Integer = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Número de segmentos con confianza < 0.7"
    )
    
    # Análisis de contenido médico
    terminologia_medica_detectada: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Términos médicos identificados con confianza"
    )
    probabilidad_contenido_medico: Float = Column(
        Float,
        nullable=True,
        comment="Probabilidad de que sea contenido médico (0.0-1.0)"
    )
    entidades_medicas: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Entidades médicas extraídas (medicamentos, síntomas, etc.)"
    )
    
    # Detección de estructura de clase
    segmentos_pregunta: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Segmentos identificados como preguntas"
    )
    segmentos_respuesta: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Segmentos identificados como respuestas"
    )
    momentos_clave_detectados: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Momentos importantes identificados automáticamente"
    )
    
    # Configuración técnica utilizada
    modelo_whisper_usado: String = Column(
        String(50),
        nullable=False,
        comment="Modelo Whisper utilizado (large-v3, medium, etc.)"
    )
    compute_type_usado: String = Column(
        String(20),
        nullable=False,
        comment="Tipo de cómputo usado (float16, int8, etc.)"
    )
    configuracion_whisper: Dict[str, Any] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Configuración completa de Whisper utilizada"
    )
    
    # Flags de procesamiento
    vad_aplicado: Boolean = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Si se aplicó Voice Activity Detection"
    )
    alineacion_temporal_aplicada: Boolean = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Si se aplicó alineación temporal a nivel de palabra"
    )
    post_procesamiento_aplicado: Boolean = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Si se aplicó post-procesamiento del texto"
    )
    
    # Timing y rendimiento
    tiempo_procesamiento_sec: Float = Column(
        Float,
        nullable=False,
        comment="Tiempo total de procesamiento en segundos"
    )
    velocidad_procesamiento: Float = Column(
        Float,
        nullable=True,
        comment="Velocidad de procesamiento (ratio tiempo_real/tiempo_audio)"
    )
    memoria_gpu_usada_mb: Optional[Integer] = Column(
        Integer,
        nullable=True,
        comment="Memoria GPU utilizada durante el procesamiento"
    )
    
    # Métricas avanzadas
    distribucion_confianza: Dict[str, Any] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Distribución estadística de confianza por segmentos"
    )
    metricas_vad: Dict[str, Any] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Métricas de Voice Activity Detection si se aplicó"
    )
    estadisticas_linguisticas: Dict[str, Any] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Estadísticas lingüísticas del texto transcrito"
    )
    
    # Timestamps
    created_at: DateTime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        comment="Timestamp de creación del resultado"
    )
    updated_at: DateTime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        onupdate=func.now(),
        comment="Timestamp de última actualización"
    )
    
    # Relaciones
    # processing_job = relationship("ProcessingJob", back_populates="transcription_result")
    
    def __repr__(self) -> str:
        return (
            f"<TranscriptionResult(id={self.id}, "
            f"job_id={self.processing_job_id}, "
            f"idioma={self.idioma_detectado}, "
            f"palabras={self.num_palabras}, "
            f"confianza={self.confianza_global:.3f})>"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para APIs."""
        return {
            "id": str(self.id),
            "processing_job_id": str(self.processing_job_id),
            "texto_completo": self.texto_completo,
            "idioma_detectado": self.idioma_detectado,
            "confianza_global": self.confianza_global,
            "num_palabras": self.num_palabras,
            "num_segmentos": self.num_segmentos,
            "duracion_audio_sec": self.duracion_audio_sec,
            "palabras_por_minuto": self.palabras_por_minuto,
            "nivel_ruido_estimado": self.nivel_ruido_estimado,
            "calidad_audio_estimada": self.calidad_audio_estimada,
            "terminologia_medica_detectada": self.terminologia_medica_detectada,
            "probabilidad_contenido_medico": self.probabilidad_contenido_medico,
            "modelo_whisper_usado": self.modelo_whisper_usado,
            "compute_type_usado": self.compute_type_usado,
            "vad_aplicado": self.vad_aplicado,
            "alineacion_temporal_aplicada": self.alineacion_temporal_aplicada,
            "post_procesamiento_aplicado": self.post_procesamiento_aplicado,
            "tiempo_procesamiento_sec": self.tiempo_procesamiento_sec,
            "velocidad_procesamiento": self.velocidad_procesamiento,
            "memoria_gpu_usada_mb": self.memoria_gpu_usada_mb,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    def to_dict_detailed(self) -> Dict[str, Any]:
        """Convertir a diccionario con detalles completos para análisis."""
        base_dict = self.to_dict()
        base_dict.update({
            "segmentos": self.segmentos,
            "palabras_con_timestamps": self.palabras_con_timestamps,
            "entidades_medicas": self.entidades_medicas,
            "segmentos_pregunta": self.segmentos_pregunta,
            "segmentos_respuesta": self.segmentos_respuesta,
            "momentos_clave_detectados": self.momentos_clave_detectados,
            "configuracion_whisper": self.configuracion_whisper,
            "distribucion_confianza": self.distribucion_confianza,
            "metricas_vad": self.metricas_vad,
            "estadisticas_linguisticas": self.estadisticas_linguisticas
        })
        return base_dict
    
    @property
    def es_alta_calidad(self) -> bool:
        """Verificar si la transcripción es de alta calidad."""
        return (
            self.confianza_global >= 0.8 and
            self.segmentos_con_baja_confianza / max(1, self.num_segmentos) <= 0.1 and
            self.calidad_audio_estimada in ["high", "medium"]
        )
    
    @property
    def velocidad_procesamiento_real_time_factor(self) -> Optional[float]:
        """Factor de velocidad respecto a tiempo real."""
        if self.duracion_audio_sec and self.tiempo_procesamiento_sec:
            return self.duracion_audio_sec / self.tiempo_procesamiento_sec
        return None
    
    @property
    def resumen_calidad(self) -> Dict[str, Any]:
        """Resumen de métricas de calidad para dashboard."""
        return {
            "confianza_global": self.confianza_global,
            "calidad_audio": self.calidad_audio_estimada,
            "es_alta_calidad": self.es_alta_calidad,
            "porcentaje_segmentos_baja_confianza": (
                self.segmentos_con_baja_confianza / max(1, self.num_segmentos) * 100
            ),
            "velocidad_procesamiento_rtf": self.velocidad_procesamiento_real_time_factor,
            "contenido_medico_probable": self.probabilidad_contenido_medico or 0.0,
            "terminos_medicos_count": len(self.terminologia_medica_detectada)
        }
