# -*- coding: utf-8 -*-
"""
Modelo para métricas de calidad del procesamiento académico.
"""

from sqlalchemy import Column, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.models.base import BaseModel


class MetricaCalidad(BaseModel):
    """
    Métricas específicas de calidad del procesamiento académico y médico.
    
    Captura información sobre la precisión y calidad del procesamiento
    en términos académicos y de contenido médico.
    """
    __tablename__ = "metricas_calidad"

    # Identificación
    metrica_id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="ID único de la métrica de calidad"
    )
    
    id_sesion_metrica = Column(
        UUID(as_uuid=True), 
        ForeignKey("sesiones_metricas.session_id"),
        nullable=False,
        comment="ID de la sesión de métricas asociada"
    )
    
    # Métricas de Calidad ASR
    puntuacion_wer = Column(
        Float,
        nullable=True,
        comment="Word Error Rate - Tasa de error de palabras (0.0 = perfecto, 1.0 = total error)"
    )
    
    confianza_promedio = Column(
        Float,
        nullable=True,
        comment="Confianza promedio del ASR (0.0 - 1.0)"
    )
    
    palabras_por_minuto = Column(
        Float,
        nullable=True,
        comment="Velocidad de habla detectada en palabras por minuto"
    )
    
    # Métricas de Calidad Diarización
    puntuacion_der = Column(
        Float,
        nullable=True,
        comment="Diarization Error Rate - Tasa de error de diarización (0.0 = perfecto)"
    )
    
    precision_separacion_hablantes = Column(
        Float,
        nullable=True,
        comment="Precisión en la separación de hablantes (0.0 - 1.0)"
    )
    
    # Métricas de Calidad LLM
    tasa_validez_json = Column(
        Float,
        nullable=True,
        comment="Porcentaje de respuestas JSON válidas del LLM (0.0 - 1.0)"
    )
    
    precision_terminos_medicos = Column(
        Float,
        nullable=True,
        comment="Precisión en identificación de términos médicos (0.0 - 1.0)"
    )
    
    puntuacion_relevancia_investigacion = Column(
        Float,
        nullable=True,
        comment="Relevancia de la investigación automática generada (0.0 - 1.0)"
    )
    
    # Métricas de Calidad de Contenido
    completitud_contenido = Column(
        Float,
        nullable=True,
        comment="Qué tan completo está el contenido procesado (0.0 - 1.0)"
    )
    
    consistencia_idioma = Column(
        Float,
        nullable=True,
        comment="Consistencia en el idioma detectado y procesado (0.0 - 1.0)"
    )
    
    nivel_academico_puntuacion = Column(
        Float,
        nullable=True,
        comment="Puntuación del nivel académico del contenido (0.0 - 1.0)"
    )
    
    # Métricas de Glosario y Términos
    cantidad_terminos_extraidos = Column(
        Float,
        nullable=True,
        comment="Número de términos médicos extraídos exitosamente"
    )
    
    precision_definiciones = Column(
        Float,
        nullable=True,
        comment="Precisión de las definiciones generadas automáticamente (0.0 - 1.0)"
    )
    
    cobertura_glosario = Column(
        Float,
        nullable=True,
        comment="Cobertura del glosario respecto al contenido médico (0.0 - 1.0)"
    )
    
    # Relaciones
    sesion_metrica = relationship(
        "SesionMetrica", 
        back_populates="metricas_calidad"
    )
    
    def __repr__(self):
        return f"<MetricaCalidad(id={self.metrica_id}, wer={self.puntuacion_wer}, confianza={self.confianza_promedio})>"
    
    @property
    def calidad_general(self) -> float:
        """Calcula una puntuación general de calidad combinando múltiples métricas."""
        metricas_positivas = []
        
        # Métricas donde mayor es mejor
        if self.confianza_promedio is not None:
            metricas_positivas.append(self.confianza_promedio)
        if self.precision_separacion_hablantes is not None:
            metricas_positivas.append(self.precision_separacion_hablantes)
        if self.tasa_validez_json is not None:
            metricas_positivas.append(self.tasa_validez_json)
        if self.precision_terminos_medicos is not None:
            metricas_positivas.append(self.precision_terminos_medicos)
        if self.completitud_contenido is not None:
            metricas_positivas.append(self.completitud_contenido)
        if self.consistencia_idioma is not None:
            metricas_positivas.append(self.consistencia_idioma)
        if self.precision_definiciones is not None:
            metricas_positivas.append(self.precision_definiciones)
        
        # Métricas donde menor es mejor (invertir)
        if self.puntuacion_wer is not None:
            metricas_positivas.append(1.0 - self.puntuacion_wer)
        if self.puntuacion_der is not None:
            metricas_positivas.append(1.0 - self.puntuacion_der)
        
        if metricas_positivas:
            return sum(metricas_positivas) / len(metricas_positivas)
        return 0.0
    
    @property
    def esta_dentro_umbrales_aceptables(self) -> bool:
        """Verifica si las métricas están dentro de umbrales aceptables."""
        # WER menor a 15%
        if self.puntuacion_wer is not None and self.puntuacion_wer > 0.15:
            return False
        
        # Confianza mayor a 70%
        if self.confianza_promedio is not None and self.confianza_promedio < 0.7:
            return False
        
        # DER menor a 20%
        if self.puntuacion_der is not None and self.puntuacion_der > 0.20:
            return False
        
        # Validez JSON mayor a 90%
        if self.tasa_validez_json is not None and self.tasa_validez_json < 0.9:
            return False
        
        return True
    
    def obtener_resumen_calidad(self) -> dict:
        """Retorna un resumen de calidad para dashboard."""
        return {
            "metrica_id": str(self.metrica_id),
            "calidad_general": round(self.calidad_general, 3),
            "wer": self.puntuacion_wer,
            "confianza_asr": self.confianza_promedio,
            "der": self.puntuacion_der,
            "precision_hablantes": self.precision_separacion_hablantes,
            "validez_json": self.tasa_validez_json,
            "precision_terminos": self.precision_terminos_medicos,
            "completitud": self.completitud_contenido,
            "terminos_extraidos": self.cantidad_terminos_extraidos,
            "umbral_aceptable": self.esta_dentro_umbrales_aceptables,
            "timestamp": self.created_at.isoformat() if self.created_at else None
        }
    
    def detectar_alertas_calidad(self) -> list:
        """Detecta problemas de calidad que requieren alertas."""
        alertas = []
        
        if self.puntuacion_wer is not None and self.puntuacion_wer > 0.20:
            alertas.append({
                "tipo": "wer_alto",
                "severidad": "critica",
                "mensaje": f"WER muy alto: {self.puntuacion_wer:.3f}",
                "valor": self.puntuacion_wer,
                "umbral": 0.20
            })
        
        if self.confianza_promedio is not None and self.confianza_promedio < 0.6:
            alertas.append({
                "tipo": "confianza_baja",
                "severidad": "warning",
                "mensaje": f"Confianza baja del ASR: {self.confianza_promedio:.3f}",
                "valor": self.confianza_promedio,
                "umbral": 0.6
            })
        
        if self.tasa_validez_json is not None and self.tasa_validez_json < 0.8:
            alertas.append({
                "tipo": "json_invalido",
                "severidad": "warning",
                "mensaje": f"Baja validez JSON del LLM: {self.tasa_validez_json:.3f}",
                "valor": self.tasa_validez_json,
                "umbral": 0.8
            })
        
        return alertas
