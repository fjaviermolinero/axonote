"""
Esquemas base para modelos Pydantic.
Incluye configuraciones comunes y utilidades.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class BaseSchema(BaseModel):
    """Esquema base con configuración común."""
    
    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        str_strip_whitespace=True
    )


class BaseResponseSchema(BaseSchema):
    """Esquema base para respuestas que incluyen metadatos comunes."""
    
    id: UUID = Field(..., description="ID único del registro")
    created_at: datetime = Field(..., description="Fecha de creación")
    updated_at: datetime = Field(..., description="Fecha de última actualización")


class PaginationParams(BaseSchema):
    """Parámetros de paginación para listas."""
    
    skip: int = Field(0, ge=0, description="Número de registros a omitir")
    limit: int = Field(20, ge=1, le=100, description="Número máximo de registros")


class PaginationResponse(BaseSchema):
    """Respuesta con metadatos de paginación."""
    
    total: int = Field(..., description="Total de registros disponibles")
    skip: int = Field(..., description="Registros omitidos")
    limit: int = Field(..., description="Límite aplicado")
    has_more: bool = Field(..., description="Hay más registros disponibles")


class SuccessResponse(BaseSchema):
    """Respuesta de éxito genérica."""
    
    message: str = Field(..., description="Mensaje de éxito")
    success: bool = Field(True, description="Indica operación exitosa")


class ErrorResponse(BaseSchema):
    """Respuesta de error estándar."""
    
    error: str = Field(..., description="Tipo de error")
    message: str = Field(..., description="Descripción del error")
    details: Optional[dict] = Field(None, description="Detalles adicionales del error")
    success: bool = Field(False, description="Indica operación fallida")
