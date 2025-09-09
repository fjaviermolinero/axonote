"""
Modelo para resultados de post-procesamiento de transcripciones.
Incluye corrección ASR, NER médico y análisis de estructura.
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import BaseModel


class PostProcessingResult(BaseModel):
    """
    Resultado del post-procesamiento de una transcripción médica.
    
    Almacena las correcciones aplicadas al texto ASR, entidades médicas
    extraídas, análisis de estructura pedagógica y métricas de mejora
    de calidad del contenido.
    """
    
    __tablename__ = "post_processing_results"
    
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
    
    # Corrección ASR
    texto_original: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Texto original de la transcripción ASR"
    )
    texto_corregido: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Texto corregido con terminología médica"
    )
    correcciones_aplicadas: Mapped[Dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Lista de correcciones aplicadas con contexto"
    )
    confianza_correccion: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Confianza en las correcciones aplicadas (0.0-1.0)"
    )
    
    # NER Médico (Named Entity Recognition)
    entidades_medicas: Mapped[Dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Entidades médicas extraídas por categoría"
    )
    terminologia_detectada: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Lista de términos médicos detectados"
    )
    glosario_clase: Mapped[Dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Glosario de términos específicos de esta clase"
    )
    precision_ner: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Precisión estimada del NER médico"
    )
    
    # Análisis de estructura pedagógica
    segmentos_identificados: Mapped[Dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Segmentos temporales y tipos de actividad"
    )
    participacion_speakers: Mapped[Dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Análisis de participación por speaker"
    )
    momentos_clave: Mapped[List[Dict]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Momentos pedagógicos importantes identificados"
    )
    flujo_clase: Mapped[Dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Flujo general de la clase (introducción, desarrollo, cierre)"
    )
    
    # Métricas de mejora de calidad
    mejora_legibilidad: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Mejora en legibilidad del texto (0.0-1.0)"
    )
    precision_terminologia: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Precisión en identificación de terminología médica"
    )
    cobertura_conceptos: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Cobertura de conceptos médicos identificados"
    )
    
    # Estadísticas de procesamiento
    num_correcciones: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Número total de correcciones aplicadas"
    )
    num_entidades: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Número total de entidades médicas detectadas"
    )
    tiempo_procesamiento: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Tiempo total de post-procesamiento en segundos"
    )
    
    # Configuración utilizada
    config_correccion: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="Configuración utilizada para corrección ASR"
    )
    config_ner: Mapped[Optional[Dict]] = mapped_column(
        JSON,
        comment="Configuración utilizada para NER médico"
    )
    
    # Relaciones
    processing_job = relationship("ProcessingJob", back_populates="post_processing_results")
    transcription_result = relationship("TranscriptionResult", back_populates="post_processing_results")
    
    def __repr__(self) -> str:
        return (
            f"<PostProcessingResult("
            f"id={self.id}, "
            f"correcciones={self.num_correcciones}, "
            f"entidades={self.num_entidades}, "
            f"mejora={self.mejora_legibilidad:.2f}"
            f")>"
        )
    
    @property
    def improvement_summary(self) -> Dict[str, any]:
        """Resumen de mejoras aplicadas."""
        return {
            "mejora_legibilidad": self.mejora_legibilidad,
            "precision_terminologia": self.precision_terminologia,
            "cobertura_conceptos": self.cobertura_conceptos,
            "num_correcciones": self.num_correcciones,
            "num_entidades": self.num_entidades,
            "confianza_correccion": self.confianza_correccion,
            "precision_ner": self.precision_ner
        }
    
    @property
    def entities_by_category(self) -> Dict[str, int]:
        """Conteo de entidades por categoría médica."""
        if not self.entidades_medicas:
            return {}
        
        return {
            categoria: len(entidades)
            for categoria, entidades in self.entidades_medicas.items()
            if isinstance(entidades, list)
        }
    
    def get_terminology_stats(self) -> Dict[str, any]:
        """Estadísticas de terminología médica detectada."""
        return {
            "total_terminos": len(self.terminologia_detectada),
            "terminos_glosario": len(self.glosario_clase),
            "categorias_detectadas": list(self.entities_by_category.keys()),
            "precision_ner": self.precision_ner,
            "cobertura_conceptos": self.cobertura_conceptos
        }
