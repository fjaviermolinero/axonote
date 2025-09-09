"""
Modelo para diccionario de terminología médica italiana.
Incluye términos, definiciones, correcciones ASR y contexto médico.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.models.base import BaseModel


class MedicalTerminology(BaseModel):
    """
    Diccionario de terminología médica italiana para corrección ASR y NER.
    
    Almacena términos médicos con sus definiciones, traducciones, variantes
    de transcripción ASR y contexto especializado para mejorar la precisión
    del procesamiento de clases médicas.
    """
    
    __tablename__ = "medical_terminology"
    
    # Término principal
    termino_original: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        comment="Término médico en italiano (forma canónica)"
    )
    termino_normalizado: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        comment="Versión normalizada para búsqueda (lowercase, sin acentos)"
    )
    categoria: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Categoría médica: anatomia, patologia, farmacologia, etc."
    )
    
    # Definiciones y traducciones
    definicion_italiana: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="Definición del término en italiano"
    )
    definicion_espanola: Mapped[Optional[str]] = mapped_column(
        Text,
        comment="Definición/traducción en español"
    )
    sinonimos: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Lista de sinónimos en italiano"
    )
    acronimos: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Acrónimos relacionados (ej: ECG, RMN, etc.)"
    )
    
    # Contexto médico especializado
    especialidad_medica: Mapped[Optional[str]] = mapped_column(
        String(100),
        index=True,
        comment="Especialidad médica principal (cardiologia, neurologia, etc.)"
    )
    subespecialidad: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="Subespecialidad o área específica"
    )
    nivel_complejidad: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="Nivel de complejidad del término (1=básico, 5=avanzado)"
    )
    frecuencia_uso: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Frecuencia de uso en clases (incrementa automáticamente)"
    )
    
    # Corrección ASR específica
    variantes_asr: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Variantes comunes de transcripción ASR errónea"
    )
    patron_correccion: Mapped[Optional[str]] = mapped_column(
        String(500),
        comment="Patrón regex para corrección automática"
    )
    confianza_correccion: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.9,
        comment="Confianza en la corrección automática (0.0-1.0)"
    )
    
    # Contexto pedagógico
    nivel_educativo: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="universitario",
        comment="Nivel educativo: pregrado, postgrado, especialización"
    )
    curso_recomendado: Mapped[Optional[str]] = mapped_column(
        String(100),
        comment="Curso o materia donde se usa típicamente"
    )
    prerequisitos: Mapped[List[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Términos prerequisito para entender este concepto"
    )
    
    # Flags de validación
    validado_por_experto: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Indica si ha sido validado por un experto médico"
    )
    activo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Indica si el término está activo para uso"
    )
    
    # Metadatos de fuente
    fuente_definicion: Mapped[Optional[str]] = mapped_column(
        String(200),
        comment="Fuente de la definición (diccionario, paper, etc.)"
    )
    url_referencia: Mapped[Optional[str]] = mapped_column(
        String(500),
        comment="URL de referencia para más información"
    )
    
    def __repr__(self) -> str:
        return (
            f"<MedicalTerminology("
            f"termino='{self.termino_original}', "
            f"categoria='{self.categoria}', "
            f"especialidad='{self.especialidad_medica}', "
            f"frecuencia={self.frecuencia_uso}"
            f")>"
        )
    
    @property
    def all_variants(self) -> List[str]:
        """Todas las variantes del término (original + sinónimos + variantes ASR)."""
        variants = [self.termino_original, self.termino_normalizado]
        variants.extend(self.sinonimos)
        variants.extend(self.variantes_asr)
        variants.extend(self.acronimos)
        return list(set(filter(None, variants)))  # Eliminar duplicados y valores None
    
    @property
    def is_high_frequency(self) -> bool:
        """Determina si es un término de alta frecuencia."""
        return self.frecuencia_uso >= 10
    
    @property
    def complexity_level_text(self) -> str:
        """Descripción textual del nivel de complejidad."""
        levels = {
            1: "Básico",
            2: "Intermedio",
            3: "Avanzado", 
            4: "Especializado",
            5: "Experto"
        }
        return levels.get(self.nivel_complejidad, "Desconocido")
    
    def increment_usage(self) -> None:
        """Incrementar contador de frecuencia de uso."""
        self.frecuencia_uso += 1
    
    def add_asr_variant(self, variant: str) -> None:
        """Agregar nueva variante ASR si no existe."""
        if variant and variant not in self.variantes_asr:
            if self.variantes_asr is None:
                self.variantes_asr = []
            self.variantes_asr.append(variant)
    
    def get_definition_summary(self) -> dict:
        """Resumen de definiciones disponibles."""
        return {
            "termino": self.termino_original,
            "categoria": self.categoria,
            "especialidad": self.especialidad_medica,
            "definicion_italiana": self.definicion_italiana,
            "definicion_espanola": self.definicion_espanola,
            "sinonimos": self.sinonimos,
            "nivel_complejidad": self.complexity_level_text,
            "frecuencia_uso": self.frecuencia_uso,
            "validado": self.validado_por_experto
        }
