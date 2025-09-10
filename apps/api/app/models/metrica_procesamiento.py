# -*- coding: utf-8 -*-
"""
Modelo para métricas de procesamiento del pipeline de transcripción.
"""

from sqlalchemy import Column, String, DateTime, Integer, Float, Text, JSON, BigInteger, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone

from app.models.base import BaseModel


class MetricaProcesamiento(BaseModel):
    """
    Métricas específicas del pipeline de procesamiento de audio y transcripción.
    
    Captura información detallada sobre rendimiento, calidad y recursos 
    utilizados en cada etapa del procesamiento.
    """
    __tablename__ = "metricas_procesamiento"

    # Identificación
    metrica_id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="ID único de la métrica de procesamiento"
    )
    
    id_sesion_metrica = Column(
        UUID(as_uuid=True), 
        ForeignKey("sesiones_metricas.session_id"),
        nullable=False,
        comment="ID de la sesión de métricas asociada"
    )
    
    # Tipo de métrica
    tipo_metrica = Column(
        String(50), 
        nullable=False,
        comment="Tipo de procesamiento: asr, diarizacion, llm, ocr, tts"
    )
    
    nombre_componente = Column(
        String(100), 
        nullable=False,
        comment="Nombre específico del componente: whisper_large_v3, pyannote_audio, qwen2.5"
    )
    
    # Temporal
    tiempo_inicio = Column(
        DateTime(timezone=True), 
        nullable=False,
        comment="Momento de inicio del procesamiento"
    )
    
    tiempo_fin = Column(
        DateTime(timezone=True), 
        nullable=False,
        comment="Momento de finalización del procesamiento"
    )
    
    duracion_ms = Column(
        Integer, 
        nullable=False,
        comment="Duración del procesamiento en milisegundos"
    )
    
    # Datos de Entrada/Salida
    tamano_entrada_bytes = Column(
        BigInteger,
        nullable=True,
        comment="Tamaño de los datos de entrada en bytes"
    )
    
    tamano_salida_bytes = Column(
        BigInteger,
        nullable=True,
        comment="Tamaño de los datos de salida en bytes"
    )
    
    # Métricas de Calidad
    puntuacion_calidad = Column(
        Float, 
        nullable=True,
        comment="Puntuación de calidad general (0.0 - 1.0)"
    )
    
    puntuacion_confianza = Column(
        Float, 
        nullable=True,
        comment="Puntuación de confianza del procesamiento (0.0 - 1.0)"
    )
    
    # Recursos Utilizados
    uso_cpu_porcentaje = Column(
        Float,
        nullable=True,
        comment="Porcentaje de uso de CPU durante el procesamiento"
    )
    
    uso_memoria_mb = Column(
        Float,
        nullable=True,
        comment="Memoria RAM utilizada en megabytes"
    )
    
    uso_gpu_porcentaje = Column(
        Float,
        nullable=True,
        comment="Porcentaje de uso de GPU durante el procesamiento"
    )
    
    memoria_gpu_mb = Column(
        Float,
        nullable=True,
        comment="Memoria GPU utilizada en megabytes"
    )
    
    # Metadatos Específicos
    metadatos = Column(
        JSON,
        nullable=True,
        comment="Metadatos específicos del tipo de procesamiento"
    )
    
    detalles_error = Column(
        Text,
        nullable=True,
        comment="Detalles del error si el procesamiento falló"
    )
    
    # Relaciones
    sesion_metrica = relationship(
        "SesionMetrica", 
        back_populates="metricas_procesamiento"
    )
    
    def __repr__(self):
        return f"<MetricaProcesamiento(id={self.metrica_id}, tipo='{self.tipo_metrica}', componente='{self.nombre_componente}')>"
    
    @property
    def fue_exitoso(self) -> bool:
        """Indica si el procesamiento fue exitoso (sin errores)."""
        return self.detalles_error is None
    
    @property
    def throughput_bytes_por_segundo(self) -> float:
        """Calcula el throughput en bytes por segundo."""
        if self.duracion_ms and self.tamano_entrada_bytes:
            segundos = self.duracion_ms / 1000.0
            return self.tamano_entrada_bytes / segundos if segundos > 0 else 0.0
        return 0.0
    
    def obtener_resumen_rendimiento(self) -> dict:
        """Retorna un resumen del rendimiento para dashboard."""
        return {
            "metrica_id": str(self.metrica_id),
            "tipo": self.tipo_metrica,
            "componente": self.nombre_componente,
            "duracion_ms": self.duracion_ms,
            "calidad": self.puntuacion_calidad,
            "confianza": self.puntuacion_confianza,
            "uso_cpu": self.uso_cpu_porcentaje,
            "uso_gpu": self.uso_gpu_porcentaje,
            "memoria_mb": self.uso_memoria_mb,
            "throughput": self.throughput_bytes_por_segundo,
            "exitoso": self.fue_exitoso,
            "timestamp": self.tiempo_inicio.isoformat()
        }
    
    def anadir_metadato(self, clave: str, valor) -> None:
        """Añade un metadato específico."""
        if self.metadatos is None:
            self.metadatos = {}
        self.metadatos[clave] = valor
    
    def obtener_metadato(self, clave: str, default=None):
        """Obtiene un metadato específico."""
        if self.metadatos:
            return self.metadatos.get(clave, default)
        return default
