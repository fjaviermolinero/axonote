"""Esquemas Pydantic para Source."""

from datetime import date
from typing import Optional
from uuid import UUID
from pydantic import Field, HttpUrl
from app.schemas.base import BaseSchema, BaseResponseSchema


class SourceCreate(BaseSchema):
    titulo: str = Field(..., max_length=500)
    url: HttpUrl
    editor: str = Field(..., max_length=200)
    tipo: str = Field(..., max_length=50)
    anio: Optional[int] = Field(None, ge=1900, le=2030)
    doi_pmid: Optional[str] = Field(None, max_length=200)
    anchor_id: str = Field(..., max_length=10)


class SourceResponse(BaseResponseSchema):
    class_id: UUID
    titulo: str
    url: str
    editor: str
    tipo: str
    anio: Optional[int] = None
    doi_pmid: Optional[str] = None
    anchor_id: str
    confianza: Optional[float] = None
    url_verificada: bool = False
    contenido_relevante: bool = True
    fuente_aprobada: bool = False
