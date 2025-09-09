"""Esquemas Pydantic para Term."""

from typing import Optional, List
from uuid import UUID
from pydantic import Field
from app.schemas.base import BaseSchema, BaseResponseSchema


class TermCreate(BaseSchema):
    termino_original: str = Field(..., max_length=200)
    traduccion_es: str = Field(..., max_length=200)
    definicion_es: str = Field(...)
    ejemplo_original: Optional[str] = None
    ejemplo_es: Optional[str] = None
    idioma: str = Field(..., max_length=5)
    categoria: Optional[str] = Field(None, max_length=50)
    dificultad: Optional[str] = Field(None, max_length=20)


class TermResponse(BaseResponseSchema):
    class_id: UUID
    termino_original: str
    traduccion_es: str
    definicion_es: str
    ejemplo_original: Optional[str] = None
    ejemplo_es: Optional[str] = None
    idioma: str
    categoria: Optional[str] = None
    dificultad: Optional[str] = None
    sinonimos_original: Optional[List[str]] = None
    sinonimos_es: Optional[List[str]] = None
    abreviaciones: Optional[List[str]] = None
    frecuencia: int = 1
    confianza: Optional[float] = None
