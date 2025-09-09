"""Esquemas Pydantic para Card."""

from datetime import date
from typing import Optional, List
from uuid import UUID
from pydantic import Field
from app.schemas.base import BaseSchema, BaseResponseSchema
from app.models.card import TipoCard, DificultadCard


class CardCreate(BaseSchema):
    front: str = Field(...)
    back: str = Field(...)
    tipo: TipoCard
    contexto_origen: Optional[str] = None


class CardResponse(BaseResponseSchema):
    class_id: UUID
    front: str
    back: str
    tipo: TipoCard
    dificultad: DificultadCard
    proximo_repaso: date
    veces_mostrada: int = 0
    respuestas_correctas: int = 0
    ultimo_repaso: Optional[date] = None
    
    @property
    def tasa_acierto(self) -> float:
        if self.veces_mostrada == 0:
            return 0.0
        return self.respuestas_correctas / self.veces_mostrada


class CardStudySession(BaseSchema):
    card_id: UUID
    calidad_respuesta: int = Field(..., ge=0, le=5)
    tiempo_respuesta: float = Field(..., gt=0)
