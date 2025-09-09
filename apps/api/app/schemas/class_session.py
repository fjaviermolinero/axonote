"""
Esquemas Pydantic para ClassSession.
Validación de datos de sesiones de clase.
"""

from datetime import date, datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import Field, validator

from app.schemas.base import BaseSchema, BaseResponseSchema, PaginationResponse
from app.models.class_session import EstadoPipeline


class ClassSessionCreate(BaseSchema):
    """Esquema para crear nueva sesión de clase."""
    
    fecha: date = Field(..., description="Fecha de la clase")
    asignatura: str = Field(..., min_length=1, max_length=200, description="Nombre de la asignatura")
    tema: str = Field(..., min_length=1, max_length=500, description="Tema de la clase")
    profesor_text: str = Field(..., min_length=1, max_length=200, description="Nombre del profesor")
    
    @validator('asignatura', 'tema', 'profesor_text')
    def validate_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('El campo no puede estar vacío')
        return v.strip()


class ClassSessionUpdate(BaseSchema):
    """Esquema para actualizar sesión de clase."""
    
    asignatura: Optional[str] = Field(None, min_length=1, max_length=200)
    tema: Optional[str] = Field(None, min_length=1, max_length=500)
    profesor_text: Optional[str] = Field(None, min_length=1, max_length=200)
    estado_pipeline: Optional[EstadoPipeline] = Field(None, description="Estado del pipeline")
    
    @validator('asignatura', 'tema', 'profesor_text')
    def validate_not_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('El campo no puede estar vacío')
        return v.strip() if v else v


class ClassSessionResponse(BaseResponseSchema):
    """Esquema de respuesta para sesión de clase."""
    
    fecha: date
    asignatura: str
    tema: str
    profesor_text: str
    profesor_id: Optional[UUID] = None
    
    # Información del audio
    audio_url: Optional[str] = None
    duracion_sec: Optional[int] = None
    
    # Resultados de procesamiento
    transcripcion_md: Optional[str] = None
    resumen_md: Optional[str] = None
    ampliacion_md: Optional[str] = None
    glosario_json: Optional[Dict[str, Any]] = None
    preguntas_json: Optional[Dict[str, Any]] = None
    tarjetas_json: Optional[Dict[str, Any]] = None
    
    # Métricas
    confianza_asr: Optional[float] = Field(None, ge=0, le=1)
    confianza_llm: Optional[float] = Field(None, ge=0, le=1)
    
    # Estado
    estado_pipeline: EstadoPipeline
    error_message: Optional[str] = None
    
    # Integración Notion
    notion_page_id: Optional[str] = None
    notion_synced_at: Optional[datetime] = None
    
    # Metadatos
    idioma_detectado: Optional[str] = None
    palabra_count: Optional[int] = None
    tiempo_procesamiento_sec: Optional[int] = None
    costo_openai_eur: Optional[float] = None
    tokens_utilizados: Optional[int] = None
    
    @property
    def duracion_minutos(self) -> Optional[int]:
        """Duración en minutos."""
        return round(self.duracion_sec / 60) if self.duracion_sec else None
    
    @property
    def is_completed(self) -> bool:
        """True si el procesamiento está completado."""
        return self.estado_pipeline == EstadoPipeline.DONE
    
    @property
    def has_error(self) -> bool:
        """True si hay error en el procesamiento."""
        return self.estado_pipeline == EstadoPipeline.ERROR


class ClassSessionSummary(BaseSchema):
    """Esquema resumido para listas de clases."""
    
    id: UUID
    fecha: date
    asignatura: str
    tema: str
    profesor_text: str
    estado_pipeline: EstadoPipeline
    duracion_sec: Optional[int] = None
    confianza_asr: Optional[float] = None
    notion_page_id: Optional[str] = None
    created_at: datetime
    
    @property
    def duracion_minutos(self) -> Optional[int]:
        """Duración en minutos."""
        return round(self.duracion_sec / 60) if self.duracion_sec else None


class ClassSessionList(PaginationResponse):
    """Lista paginada de sesiones de clase."""
    
    items: List[ClassSessionSummary] = Field(..., description="Lista de clases")


class ClassSessionStats(BaseSchema):
    """Estadísticas de sesiones de clase."""
    
    total_clases: int = Field(..., description="Total de clases")
    total_horas: float = Field(..., description="Total de horas grabadas")
    clases_completadas: int = Field(..., description="Clases procesadas completamente")
    clases_en_proceso: int = Field(..., description="Clases en procesamiento")
    clases_con_error: int = Field(..., description="Clases con errores")
    
    # Estadísticas por asignatura
    asignaturas: Dict[str, int] = Field(..., description="Clases por asignatura")
    
    # Métricas de calidad promedio
    confianza_asr_promedio: Optional[float] = Field(None, description="Confianza ASR promedio")
    confianza_llm_promedio: Optional[float] = Field(None, description="Confianza LLM promedio")
    
    # Costos
    costo_total_openai: Optional[float] = Field(None, description="Costo total OpenAI (EUR)")
    tokens_total_utilizados: Optional[int] = Field(None, description="Tokens totales utilizados")


class ProcessingStatus(BaseSchema):
    """Estado detallado del procesamiento."""
    
    class_id: UUID
    estado_pipeline: EstadoPipeline
    progreso_porcentaje: int = Field(..., ge=0, le=100, description="Progreso en porcentaje")
    
    # Tiempos de procesamiento por etapa
    tiempo_asr: Optional[int] = Field(None, description="Tiempo ASR en segundos")
    tiempo_diarizacion: Optional[int] = Field(None, description="Tiempo diarización en segundos")
    tiempo_nlp: Optional[int] = Field(None, description="Tiempo NLP en segundos")
    tiempo_total: Optional[int] = Field(None, description="Tiempo total en segundos")
    
    # Información de error si existe
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    
    # Última actualización
    updated_at: datetime
