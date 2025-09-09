"""
Esquemas Pydantic para Professor.
Validación de datos de profesores.
"""

from datetime import date
from typing import Optional, List
from uuid import UUID

from pydantic import Field, validator

from app.schemas.base import BaseSchema, BaseResponseSchema


class ProfessorCreate(BaseSchema):
    """Esquema para crear nuevo profesor."""
    
    nombre: str = Field(..., min_length=1, max_length=200, description="Nombre completo del profesor")
    titulo: Optional[str] = Field(None, max_length=100, description="Título académico (Dr., Prof., etc.)")
    departamento: Optional[str] = Field(None, max_length=200, description="Departamento")
    email: Optional[str] = Field(None, max_length=300, description="Email del profesor")
    
    @validator('nombre')
    def validate_nombre(cls, v):
        if not v or not v.strip():
            raise ValueError('El nombre no puede estar vacío')
        return v.strip()
    
    @validator('email')
    def validate_email(cls, v):
        if v and '@' not in v:
            raise ValueError('Email inválido')
        return v


class ProfessorUpdate(BaseSchema):
    """Esquema para actualizar profesor."""
    
    nombre: Optional[str] = Field(None, min_length=1, max_length=200)
    titulo: Optional[str] = Field(None, max_length=100)
    departamento: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = Field(None, max_length=300)
    
    @validator('nombre')
    def validate_nombre(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('El nombre no puede estar vacío')
        return v.strip() if v else v
    
    @validator('email')
    def validate_email(cls, v):
        if v and '@' not in v:
            raise ValueError('Email inválido')
        return v


class ProfessorResponse(BaseResponseSchema):
    """Esquema de respuesta para profesor."""
    
    nombre: str
    slug: str
    titulo: Optional[str] = None
    departamento: Optional[str] = None
    email: Optional[str] = None
    
    # Metadatos
    total_clases: int = Field(0, description="Total de clases del profesor")
    ultima_clase: Optional[date] = Field(None, description="Fecha de la última clase")
    
    # Alias
    alias_json: Optional[List[str]] = Field(None, description="Lista de alias del profesor")
    
    @property
    def nombre_completo(self) -> str:
        """Nombre completo con título."""
        if self.titulo:
            return f"{self.titulo} {self.nombre}"
        return self.nombre
    
    @property
    def alias_list(self) -> List[str]:
        """Lista de alias."""
        return self.alias_json or [self.nombre]


class ProfessorSummary(BaseSchema):
    """Resumen de profesor para listas."""
    
    id: UUID
    nombre: str
    slug: str
    titulo: Optional[str] = None
    departamento: Optional[str] = None
    total_clases: int = 0
    ultima_clase: Optional[date] = None
    
    @property
    def nombre_completo(self) -> str:
        """Nombre completo con título."""
        if self.titulo:
            return f"{self.titulo} {self.nombre}"
        return self.nombre
