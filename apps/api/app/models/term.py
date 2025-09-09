"""
Modelo Term - Términos médicos del glosario.
Representa términos médicos extraídos y definidos de las clases.
"""

from typing import List, Optional
from sqlalchemy import Column, String, Text, ForeignKey, Index, JSON, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Term(BaseModel):
    """
    Término médico del glosario.
    
    Almacena términos médicos identificados en las transcripciones
    con sus traducciones, definiciones y ejemplos de uso.
    """
    
    __tablename__ = "terms"
    
    # ==============================================
    # RELACIÓN CON CLASE
    # ==============================================
    
    class_id = Column(
        UUID(as_uuid=True),
        ForeignKey("class_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # ==============================================
    # INFORMACIÓN DEL TÉRMINO
    # ==============================================
    
    # Término en idioma original (italiano/inglés)
    termino_original = Column(String(200), nullable=False, index=True)
    
    # Traducción al español
    traduccion_es = Column(String(200), nullable=False, index=True)
    
    # Definición médica en español
    definicion_es = Column(Text, nullable=False)
    
    # Ejemplo de uso en idioma original
    ejemplo_original = Column(Text, nullable=True)
    
    # Ejemplo de uso en español
    ejemplo_es = Column(Text, nullable=True)
    
    # ==============================================
    # METADATOS LINGÜÍSTICOS
    # ==============================================
    
    # Idioma del término original
    idioma = Column(String(5), nullable=False, index=True)  # 'it', 'en', etc.
    
    # Categoría médica (anatomía, farmacología, patología, etc.)
    categoria = Column(String(50), nullable=True, index=True)
    
    # Nivel de dificultad (básico, intermedio, avanzado)
    dificultad = Column(String(20), nullable=True, index=True)
    
    # ==============================================
    # VARIACIONES Y SINÓNIMOS
    # ==============================================
    
    # Sinónimos en idioma original (JSON array)
    sinonimos_original = Column(JSON, nullable=True)
    
    # Sinónimos en español (JSON array)
    sinonimos_es = Column(JSON, nullable=True)
    
    # Abreviaciones o acrónimos
    abreviaciones = Column(JSON, nullable=True)
    
    # ==============================================
    # CONTEXTO DE USO
    # ==============================================
    
    # Fragmento de la transcripción donde aparece
    contexto_transcripcion = Column(Text, nullable=True)
    
    # Timestamp en la grabación donde se menciona (segundos)
    timestamp_mencion = Column(Integer, nullable=True)
    
    # Frecuencia de aparición en la clase
    frecuencia = Column(Integer, nullable=False, default=1)
    
    # ==============================================
    # INFORMACIÓN ADICIONAL
    # ==============================================
    
    # Etimología del término (opcional)
    etimologia = Column(Text, nullable=True)
    
    # Enlaces a recursos adicionales
    recursos_adicionales = Column(JSON, nullable=True)
    
    # Confianza en la traducción/definición (0-1)
    confianza = Column(Float, nullable=True, default=1.0)
    
    # ==============================================
    # RELACIONES
    # ==============================================
    
    class_session = relationship("ClassSession", back_populates="terms")
    
    def __repr__(self) -> str:
        return (
            f"<Term("
            f"id={self.id}, "
            f"original='{self.termino_original}', "
            f"español='{self.traduccion_es}', "
            f"idioma='{self.idioma}'"
            f")>"
        )
    
    @property
    def sinonimos_original_list(self) -> List[str]:
        """Lista de sinónimos en idioma original."""
        return self.sinonimos_original or []
    
    @property
    def sinonimos_es_list(self) -> List[str]:
        """Lista de sinónimos en español."""
        return self.sinonimos_es or []
    
    @property
    def abreviaciones_list(self) -> List[str]:
        """Lista de abreviaciones."""
        return self.abreviaciones or []
    
    def add_sinonimo_original(self, sinonimo: str) -> None:
        """Añadir sinónimo en idioma original."""
        sinonimos = self.sinonimos_original_list
        if sinonimo not in sinonimos:
            sinonimos.append(sinonimo)
            self.sinonimos_original = sinonimos
    
    def add_sinonimo_es(self, sinonimo: str) -> None:
        """Añadir sinónimo en español."""
        sinonimos = self.sinonimos_es_list
        if sinonimo not in sinonimos:
            sinonimos.append(sinonimo)
            self.sinonimos_es = sinonimos
    
    def add_abreviacion(self, abreviacion: str) -> None:
        """Añadir abreviación."""
        abrevs = self.abreviaciones_list
        if abreviacion not in abrevs:
            abrevs.append(abreviacion)
            self.abreviaciones = abrevs
    
    @property
    def timestamp_formatted(self) -> Optional[str]:
        """Timestamp formateado como MM:SS."""
        if not self.timestamp_mencion:
            return None
        
        minutes = self.timestamp_mencion // 60
        seconds = self.timestamp_mencion % 60
        return f"{minutes:02d}:{seconds:02d}"
    
    def matches_term(self, busqueda: str) -> bool:
        """
        Verificar si un término de búsqueda coincide.
        Busca en término original, traducción y sinónimos.
        """
        busqueda_lower = busqueda.lower().strip()
        
        # Buscar en término original y traducción
        if (busqueda_lower in self.termino_original.lower() or
            busqueda_lower in self.traduccion_es.lower()):
            return True
        
        # Buscar en sinónimos
        for sinonimo in self.sinonimos_original_list + self.sinonimos_es_list:
            if busqueda_lower in sinonimo.lower():
                return True
        
        # Buscar en abreviaciones
        for abrev in self.abreviaciones_list:
            if busqueda_lower == abrev.lower():
                return True
        
        return False
    
    @classmethod
    def get_categorias_disponibles(cls) -> List[str]:
        """Obtener lista de categorías médicas disponibles."""
        return [
            "anatomía",
            "fisiología", 
            "patología",
            "farmacología",
            "diagnóstico",
            "tratamiento",
            "procedimientos",
            "especialidades",
            "síntomas",
            "signos"
        ]
    
    @classmethod
    def get_niveles_dificultad(cls) -> List[str]:
        """Obtener niveles de dificultad disponibles."""
        return ["básico", "intermedio", "avanzado"]


# Índices para optimizar consultas frecuentes
Index('idx_term_class_original', Term.class_id, Term.termino_original)
Index('idx_term_traduccion', Term.traduccion_es)
Index('idx_term_categoria_dificultad', Term.categoria, Term.dificultad)
Index('idx_term_idioma_categoria', Term.idioma, Term.categoria)
Index('idx_term_frecuencia', Term.frecuencia)  # Para términos más usados
