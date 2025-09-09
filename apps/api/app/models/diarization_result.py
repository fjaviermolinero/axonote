"""
Modelo de base de datos para resultados de diarización.
Almacena separación de speakers y clasificación en roles médicos.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import BaseModel


class DiarizationResult(BaseModel):
    """
    Modelo para almacenar resultados de diarización con pyannote-audio.
    Incluye separación de speakers y clasificación en roles médicos.
    """
    __tablename__ = "diarization_results"

    # Identificación
    id: UUID = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    processing_job_id: UUID = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="CASCADE"),
        nullable=False,
        comment="Relación con ProcessingJob"
    )
    
    # Información básica de speakers
    num_speakers_detectados: Integer = Column(
        Integer,
        nullable=False,
        comment="Número de speakers únicos detectados"
    )
    speakers_clasificados: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Lista de speakers con clasificación de roles"
    )
    
    # Segmentos de diarización
    segmentos_diarizacion: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Segmentos con [start, end, speaker_id, confidence]"
    )
    embeddings_speakers: Dict[str, List[float]] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Embeddings de cada speaker para re-identificación"
    )
    
    # Clasificación en roles médicos
    speaker_profesor: Optional[String] = Column(
        String(50),
        nullable=True,
        comment="ID del speaker identificado como profesor"
    )
    speakers_alumnos: List[String] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Lista de IDs de speakers identificados como alumnos"
    )
    confianza_clasificacion: Float = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Confianza en la clasificación de roles (0.0-1.0)"
    )
    
    # Análisis de participación
    tiempo_habla_por_speaker: Dict[str, float] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Tiempo total de habla por cada speaker en segundos"
    )
    porcentaje_participacion: Dict[str, float] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Porcentaje de participación de cada speaker"
    )
    turnos_de_palabra: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Análisis de turnos de conversación"
    )
    
    # Análisis de interacciones
    overlaps_detectados: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Solapamientos de speech entre speakers"
    )
    interrupciones: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Interrupciones detectadas con contexto"
    )
    pausas_significativas: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Pausas largas que pueden indicar cambios de tema"
    )
    
    # Métricas de calidad de diarización
    calidad_separacion: Float = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Métrica de calidad de separación de speakers (0.0-1.0)"
    )
    segmentos_ambiguos: Integer = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Número de segmentos con speaker incierto"
    )
    consistency_score: Float = Column(
        Float,
        nullable=True,
        comment="Score de consistencia temporal de speakers"
    )
    
    # Análisis específico de clases médicas
    patron_profesor_alumno_detectado: Boolean = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Si se detectó patrón típico profesor-alumno"
    )
    momenos_pregunta_respuesta: List[Dict[str, Any]] = Column(
        JSON,
        nullable=False,
        default=list,
        comment="Momentos identificados como pregunta-respuesta"
    )
    dinamica_clase_estimada: String = Column(
        String(50),
        nullable=True,
        comment="Tipo de dinámica: lecture, discussion, interview, etc."
    )
    
    # Configuración técnica utilizada
    modelo_diarizacion_usado: String = Column(
        String(100),
        nullable=False,
        comment="Modelo de diarización utilizado"
    )
    parametros_clustering: Dict[str, Any] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Parámetros de clustering utilizados"
    )
    configuracion_diarizacion: Dict[str, Any] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Configuración completa de diarización"
    )
    
    # Timing y rendimiento
    tiempo_procesamiento_sec: Float = Column(
        Float,
        nullable=False,
        comment="Tiempo total de procesamiento en segundos"
    )
    memoria_gpu_usada_mb: Optional[Integer] = Column(
        Integer,
        nullable=True,
        comment="Memoria GPU utilizada durante el procesamiento"
    )
    velocidad_procesamiento: Float = Column(
        Float,
        nullable=True,
        comment="Velocidad de procesamiento (ratio tiempo_real/tiempo_audio)"
    )
    
    # Métricas avanzadas
    matriz_confusion_speakers: Dict[str, Any] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Matriz de confusión entre speakers si hay ground truth"
    )
    distribucion_duracion_segmentos: Dict[str, Any] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Estadísticas de duración de segmentos por speaker"
    )
    patrones_temporales: Dict[str, Any] = Column(
        JSON,
        nullable=False,
        default=dict,
        comment="Patrones temporales de participación detectados"
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
    # processing_job = relationship("ProcessingJob", back_populates="diarization_result")
    
    def __repr__(self) -> str:
        return (
            f"<DiarizationResult(id={self.id}, "
            f"job_id={self.processing_job_id}, "
            f"speakers={self.num_speakers_detectados}, "
            f"calidad={self.calidad_separacion:.3f})>"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario para APIs."""
        return {
            "id": str(self.id),
            "processing_job_id": str(self.processing_job_id),
            "num_speakers_detectados": self.num_speakers_detectados,
            "speaker_profesor": self.speaker_profesor,
            "speakers_alumnos": self.speakers_alumnos,
            "confianza_clasificacion": self.confianza_clasificacion,
            "tiempo_habla_por_speaker": self.tiempo_habla_por_speaker,
            "porcentaje_participacion": self.porcentaje_participacion,
            "calidad_separacion": self.calidad_separacion,
            "segmentos_ambiguos": self.segmentos_ambiguos,
            "consistency_score": self.consistency_score,
            "patron_profesor_alumno_detectado": self.patron_profesor_alumno_detectado,
            "dinamica_clase_estimada": self.dinamica_clase_estimada,
            "modelo_diarizacion_usado": self.modelo_diarizacion_usado,
            "tiempo_procesamiento_sec": self.tiempo_procesamiento_sec,
            "memoria_gpu_usada_mb": self.memoria_gpu_usada_mb,
            "velocidad_procesamiento": self.velocidad_procesamiento,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    def to_dict_detailed(self) -> Dict[str, Any]:
        """Convertir a diccionario con detalles completos para análisis."""
        base_dict = self.to_dict()
        base_dict.update({
            "speakers_clasificados": self.speakers_clasificados,
            "segmentos_diarizacion": self.segmentos_diarizacion,
            "embeddings_speakers": self.embeddings_speakers,
            "turnos_de_palabra": self.turnos_de_palabra,
            "overlaps_detectados": self.overlaps_detectados,
            "interrupciones": self.interrupciones,
            "pausas_significativas": self.pausas_significativas,
            "momenos_pregunta_respuesta": self.momenos_pregunta_respuesta,
            "parametros_clustering": self.parametros_clustering,
            "configuracion_diarizacion": self.configuracion_diarizacion,
            "matriz_confusion_speakers": self.matriz_confusion_speakers,
            "distribucion_duracion_segmentos": self.distribucion_duracion_segmentos,
            "patrones_temporales": self.patrones_temporales
        })
        return base_dict
    
    @property
    def es_alta_calidad(self) -> bool:
        """Verificar si la diarización es de alta calidad."""
        return (
            self.calidad_separacion >= 0.7 and
            self.num_speakers_detectados >= 1 and
            self.segmentos_ambiguos / max(1, len(self.segmentos_diarizacion)) <= 0.1
        )
    
    @property
    def tiene_profesor_identificado(self) -> bool:
        """Verificar si se identificó un profesor."""
        return bool(self.speaker_profesor)
    
    @property
    def ratio_profesor_alumnos(self) -> Optional[float]:
        """Ratio de tiempo de habla profesor vs alumnos."""
        if not self.speaker_profesor or not self.tiempo_habla_por_speaker:
            return None
        
        tiempo_profesor = self.tiempo_habla_por_speaker.get(self.speaker_profesor, 0)
        tiempo_alumnos = sum(
            tiempo for speaker_id, tiempo in self.tiempo_habla_por_speaker.items()
            if speaker_id != self.speaker_profesor
        )
        
        if tiempo_alumnos == 0:
            return float('inf')
        
        return tiempo_profesor / tiempo_alumnos
    
    @property
    def participacion_equilibrada(self) -> bool:
        """Verificar si hay participación equilibrada entre alumnos."""
        if len(self.speakers_alumnos) < 2:
            return True
        
        participaciones_alumnos = [
            self.porcentaje_participacion.get(speaker_id, 0)
            for speaker_id in self.speakers_alumnos
        ]
        
        if not participaciones_alumnos:
            return True
        
        # Considerar equilibrada si ningún alumno tiene más del 60% de la participación estudiantil
        max_participacion = max(participaciones_alumnos)
        total_participacion_alumnos = sum(participaciones_alumnos)
        
        if total_participacion_alumnos == 0:
            return True
        
        return (max_participacion / total_participacion_alumnos) <= 0.6
    
    @property
    def resumen_participacion(self) -> Dict[str, Any]:
        """Resumen de participación para dashboard."""
        return {
            "num_speakers": self.num_speakers_detectados,
            "tiene_profesor": self.tiene_profesor_identificado,
            "num_alumnos": len(self.speakers_alumnos),
            "ratio_profesor_alumnos": self.ratio_profesor_alumnos,
            "participacion_equilibrada": self.participacion_equilibrada,
            "turnos_totales": len(self.turnos_de_palabra),
            "interrupciones_count": len(self.interrupciones),
            "overlaps_count": len(self.overlaps_detectados),
            "dinamica_clase": self.dinamica_clase_estimada,
            "calidad_separacion": self.calidad_separacion,
            "es_alta_calidad": self.es_alta_calidad
        }
