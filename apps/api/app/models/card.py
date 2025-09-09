"""
Modelo Card - Tarjetas de estudio (Flashcards).
Representa tarjetas de estudio generadas automáticamente para repaso.
"""

from datetime import date, datetime, timedelta
from typing import Optional
from sqlalchemy import Column, String, Text, Date, ForeignKey, Index, Enum, Integer, Float, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.models.base import BaseModel


class TipoCard(str, enum.Enum):
    """Tipos de tarjetas de estudio."""
    DEFINICION = "definicion"           # Término -> Definición
    TRADUCCION = "traduccion"           # Término IT -> Español
    PREGUNTA_RESPUESTA = "pregunta"     # Pregunta -> Respuesta
    CLOZE = "cloze"                     # Texto con hueco a rellenar
    IMAGEN = "imagen"                   # Imagen -> Descripción
    CASO_CLINICO = "caso"               # Caso -> Diagnóstico/Tratamiento


class DificultadCard(str, enum.Enum):
    """Niveles de dificultad de las tarjetas."""
    MUY_FACIL = "muy_facil"
    FACIL = "facil"
    NORMAL = "normal"
    DIFICIL = "dificil"
    MUY_DIFICIL = "muy_dificil"


class Card(BaseModel):
    """
    Tarjeta de estudio (Flashcard).
    
    Representa una tarjeta de estudio generada automáticamente
    a partir del contenido de la clase para facilitar el repaso.
    """
    
    __tablename__ = "cards"
    
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
    # CONTENIDO DE LA TARJETA
    # ==============================================
    
    # Frente de la tarjeta (pregunta/estímulo)
    front = Column(Text, nullable=False)
    
    # Reverso de la tarjeta (respuesta/definición)
    back = Column(Text, nullable=False)
    
    # Tipo de tarjeta
    tipo = Column(Enum(TipoCard), nullable=False, index=True)
    
    # ==============================================
    # SISTEMA DE REPASO ESPACIADO
    # ==============================================
    
    # Dificultad actual de la tarjeta
    dificultad = Column(
        Enum(DificultadCard), 
        nullable=False, 
        default=DificultadCard.NORMAL,
        index=True
    )
    
    # Próxima fecha de repaso
    proximo_repaso = Column(Date, nullable=False, index=True)
    
    # Intervalo actual (días hasta próximo repaso)
    intervalo_dias = Column(Integer, nullable=False, default=1)
    
    # Factor de facilidad (algoritmo SM-2)
    factor_facilidad = Column(Float, nullable=False, default=2.5)
    
    # Número de repeticiones consecutivas correctas
    repeticiones_correctas = Column(Integer, nullable=False, default=0)
    
    # ==============================================
    # ESTADÍSTICAS DE USO
    # ==============================================
    
    # Total de veces mostrada
    veces_mostrada = Column(Integer, nullable=False, default=0)
    
    # Total de respuestas correctas
    respuestas_correctas = Column(Integer, nullable=False, default=0)
    
    # Última fecha de repaso
    ultimo_repaso = Column(Date, nullable=True)
    
    # Tiempo promedio de respuesta (segundos)
    tiempo_respuesta_promedio = Column(Float, nullable=True)
    
    # ==============================================
    # METADATOS
    # ==============================================
    
    # Contexto original (de dónde se extrajo)
    contexto_origen = Column(Text, nullable=True)
    
    # Timestamp en la grabación si es relevante
    timestamp_origen = Column(Integer, nullable=True)
    
    # Etiquetas para categorización
    etiquetas = Column(JSON, nullable=True)
    
    # Confianza en la generación automática (0-1)
    confianza_generacion = Column(Float, nullable=True, default=1.0)
    
    # ==============================================
    # RELACIONES
    # ==============================================
    
    class_session = relationship("ClassSession", back_populates="cards")
    
    def __repr__(self) -> str:
        return (
            f"<Card("
            f"id={self.id}, "
            f"tipo='{self.tipo}', "
            f"dificultad='{self.dificultad}', "
            f"proximo_repaso={self.proximo_repaso}"
            f")>"
        )
    
    @property
    def tasa_acierto(self) -> float:
        """Tasa de acierto (0-1)."""
        if self.veces_mostrada == 0:
            return 0.0
        return self.respuestas_correctas / self.veces_mostrada
    
    @property
    def es_due_para_repaso(self) -> bool:
        """True si la tarjeta debe ser repasada hoy."""
        return self.proximo_repaso <= date.today()
    
    @property
    def dias_hasta_repaso(self) -> int:
        """Días hasta el próximo repaso."""
        delta = self.proximo_repaso - date.today()
        return delta.days
    
    def responder(self, calidad: int, tiempo_respuesta: float) -> None:
        """
        Registrar respuesta y actualizar algoritmo de repaso espaciado.
        
        Args:
            calidad: Calidad de la respuesta (0=muy mal, 5=muy bien)
            tiempo_respuesta: Tiempo de respuesta en segundos
        """
        self.veces_mostrada += 1
        self.ultimo_repaso = date.today()
        
        # Actualizar tiempo promedio de respuesta
        if self.tiempo_respuesta_promedio is None:
            self.tiempo_respuesta_promedio = tiempo_respuesta
        else:
            # Promedio móvil simple
            self.tiempo_respuesta_promedio = (
                (self.tiempo_respuesta_promedio * (self.veces_mostrada - 1) + tiempo_respuesta) 
                / self.veces_mostrada
            )
        
        # Algoritmo SM-2 simplificado
        if calidad >= 3:  # Respuesta correcta
            self.respuestas_correctas += 1
            self.repeticiones_correctas += 1
            
            if self.repeticiones_correctas == 1:
                self.intervalo_dias = 1
            elif self.repeticiones_correctas == 2:
                self.intervalo_dias = 6
            else:
                self.intervalo_dias = round(self.intervalo_dias * self.factor_facilidad)
            
            # Actualizar factor de facilidad
            self.factor_facilidad = max(1.3, 
                self.factor_facilidad + (0.1 - (5 - calidad) * (0.08 + (5 - calidad) * 0.02))
            )
            
        else:  # Respuesta incorrecta
            self.repeticiones_correctas = 0
            self.intervalo_dias = 1
        
        # Actualizar dificultad basada en rendimiento
        if self.tasa_acierto >= 0.9:
            self.dificultad = DificultadCard.MUY_FACIL
        elif self.tasa_acierto >= 0.8:
            self.dificultad = DificultadCard.FACIL
        elif self.tasa_acierto >= 0.6:
            self.dificultad = DificultadCard.NORMAL
        elif self.tasa_acierto >= 0.4:
            self.dificultad = DificultadCard.DIFICIL
        else:
            self.dificultad = DificultadCard.MUY_DIFICIL
        
        # Calcular próximo repaso
        self.proximo_repaso = date.today() + timedelta(days=self.intervalo_dias)
    
    @property
    def front_preview(self) -> str:
        """Preview del frente de la tarjeta (primeros 100 caracteres)."""
        return self.front[:100] + "..." if len(self.front) > 100 else self.front
    
    @property
    def back_preview(self) -> str:
        """Preview del reverso de la tarjeta (primeros 100 caracteres)."""
        return self.back[:100] + "..." if len(self.back) > 100 else self.back
    
    @classmethod
    def get_cards_for_today(cls, class_id: Optional[str] = None) -> list:
        """
        Obtener tarjetas que deben ser repasadas hoy.
        
        Args:
            class_id: Filtrar por clase específica (opcional)
        
        Returns:
            Lista de tarjetas para repasar
        """
        # TODO: Implementar query real cuando tengamos session
        # Por ahora retornamos lista vacía
        return []
    
    @classmethod
    def create_from_term(cls, term, class_session) -> 'Card':
        """Crear tarjeta de definición a partir de un término."""
        return cls(
            class_id=class_session.id,
            front=term.termino_original,
            back=f"{term.traduccion_es}\n\n{term.definicion_es}",
            tipo=TipoCard.DEFINICION,
            contexto_origen=f"Término: {term.termino_original}",
            proximo_repaso=date.today() + timedelta(days=1)
        )
    
    @classmethod 
    def create_translation_card(cls, term, class_session) -> 'Card':
        """Crear tarjeta de traducción a partir de un término."""
        return cls(
            class_id=class_session.id,
            front=f"Traducir: {term.termino_original}",
            back=term.traduccion_es,
            tipo=TipoCard.TRADUCCION,
            contexto_origen=f"Término: {term.termino_original}",
            proximo_repaso=date.today() + timedelta(days=1)
        )


# Índices para optimizar consultas frecuentes
Index('idx_card_class_tipo', Card.class_id, Card.tipo)
Index('idx_card_proximo_repaso', Card.proximo_repaso)
Index('idx_card_dificultad_repaso', Card.dificultad, Card.proximo_repaso)
Index('idx_card_ultimo_repaso', Card.ultimo_repaso)
Index('idx_card_tasa_acierto', Card.respuestas_correctas, Card.veces_mostrada)
