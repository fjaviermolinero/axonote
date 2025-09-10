"""
Endpoints API para export multi-modal.
Permite exportar contenido en múltiples formatos académicos y profesionales.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import ClassSession, ExportSession
from app.services.export_service import ExportService, ConfiguracionExport, export_service
from app.tasks.export_tts import process_export_session_task

logger = logging.getLogger(__name__)

router = APIRouter()


# Schemas de request/response
class ExportConfigRequest(BaseModel):
    """Configuración para exportación."""
    
    # Filtros de contenido
    incluir_transcripciones: bool = Field(True, description="Incluir transcripciones en el export")
    incluir_ocr: bool = Field(True, description="Incluir resultados OCR")
    incluir_micromemos: bool = Field(True, description="Incluir micro-memos")
    incluir_research: bool = Field(True, description="Incluir resultados de research")
    incluir_analytics: bool = Field(False, description="Incluir analytics y métricas")
    
    # Filtros de calidad
    confianza_minima: float = Field(0.7, ge=0.0, le=1.0, description="Confianza mínima para incluir contenido")
    solo_validados: bool = Field(False, description="Solo incluir contenido validado")
    
    # Filtros temporales
    fecha_inicio: Optional[datetime] = Field(None, description="Fecha de inicio para filtrar contenido")
    fecha_fin: Optional[datetime] = Field(None, description="Fecha fin para filtrar contenido")
    
    # Filtros especializados
    especialidades: List[str] = Field(default_factory=list, description="Especialidades médicas a incluir")
    niveles_dificultad: List[str] = Field(default_factory=list, description="Niveles de dificultad a incluir")
    tipos_contenido: List[str] = Field(default_factory=list, description="Tipos de contenido a incluir")
    
    # Opciones de formato
    incluir_metadatos: bool = Field(True, description="Incluir metadatos en el export")
    incluir_imagenes: bool = Field(True, description="Incluir imágenes si están disponibles")
    incluir_audio: bool = Field(False, description="Incluir síntesis TTS")
    comprimir_salida: bool = Field(True, description="Comprimir archivos de salida")
    
    # Template y personalización
    template_personalizado: Optional[str] = Field(None, description="Template personalizado a usar")
    logo_institucional: Optional[str] = Field(None, description="URL del logo institucional")
    header_personalizado: Optional[str] = Field(None, description="Header personalizado")
    footer_personalizado: Optional[str] = Field(None, description="Footer personalizado")
    
    # Formato específico
    formato_referencias: str = Field("apa", description="Formato de referencias (apa, vancouver, harvard)")
    estilo_medico: str = Field("academico", description="Estilo médico (clinico, academico, investigacion)")
    incluir_disclaimer: bool = Field(True, description="Incluir disclaimer médico")
    confidencialidad: str = Field("medical", description="Nivel de confidencialidad")


class CreateExportRequest(BaseModel):
    """Request para crear nueva exportación."""
    export_format: str = Field(..., description="Formato de exportación (pdf, docx, json, anki, csv, html)")
    config: ExportConfigRequest = Field(..., description="Configuración del export")


class ExportSessionResponse(BaseModel):
    """Response con información de sesión de export."""
    id: UUID
    class_session_id: UUID
    export_format: str
    status: str
    progress_percentage: float
    estimated_completion: Optional[datetime]
    output_files: List[Dict[str, Any]]
    total_size_bytes: int
    elements_exported: int
    quality_score: float
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str] = None
    
    class Config:
        from_attributes = True


class ExportStatusResponse(BaseModel):
    """Response con estado detallado del export."""
    id: UUID
    status: str
    progress_percentage: float
    estimated_completion: Optional[datetime]
    current_stage: Optional[str] = None
    message: Optional[str] = None
    elements_exported: int
    processing_time_seconds: float
    is_completed: bool
    has_failed: bool
    
    class Config:
        from_attributes = True


class ExportHistoryResponse(BaseModel):
    """Response con historial de exports."""
    exports: List[ExportSessionResponse]
    total_count: int
    page: int
    page_size: int


class ExportMetricsResponse(BaseModel):
    """Response con métricas de export."""
    total_exports: int
    exports_by_format: Dict[str, int]
    exports_by_status: Dict[str, int]
    avg_processing_time: float
    avg_quality_score: float
    total_size_exported_mb: float
    exports_last_24h: int
    most_exported_format: str


# Endpoints
@router.post("/create", response_model=ExportSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_export_session(
    class_session_id: UUID,
    request: CreateExportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Crea una nueva sesión de export.
    
    Args:
        class_session_id: ID de la sesión de clase
        request: Configuración del export
        background_tasks: Tareas en background
        db: Sesión de base de datos
        
    Returns:
        Información de la sesión de export creada
    """
    try:
        # Verificar que la clase existe
        class_session = db.query(ClassSession).filter(
            ClassSession.id == class_session_id
        ).first()
        
        if not class_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Class session not found: {class_session_id}"
            )
        
        # Validar formato de export
        valid_formats = ["pdf", "docx", "json", "anki", "csv", "html"]
        if request.export_format not in valid_formats:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid export format. Must be one of: {', '.join(valid_formats)}"
            )
        
        # Crear configuración
        config_dict = request.config.model_dump()
        config = ConfiguracionExport(**config_dict)
        
        # Crear sesión de export
        export_session = await export_service.create_export_session(
            class_session_id=class_session_id,
            export_format=request.export_format,
            config=config,
            db=db
        )
        
        # Lanzar procesamiento en background
        background_tasks.add_task(
            process_export_session_task.delay,
            str(export_session.id),
            True  # notify_completion
        )
        
        logger.info(f"Created export session {export_session.id} for class {class_session_id}")
        
        return ExportSessionResponse.model_validate(export_session)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create export session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create export session: {str(e)}"
        )


@router.get("/session/{session_id}", response_model=ExportSessionResponse)
async def get_export_session(
    session_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Obtiene información detallada de una sesión de export.
    
    Args:
        session_id: ID de la sesión de export
        db: Sesión de base de datos
        
    Returns:
        Información completa de la sesión de export
    """
    try:
        export_session = db.query(ExportSession).filter(
            ExportSession.id == session_id
        ).first()
        
        if not export_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Export session not found: {session_id}"
            )
        
        return ExportSessionResponse.model_validate(export_session)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get export session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get export session: {str(e)}"
        )


@router.get("/session/{session_id}/status", response_model=ExportStatusResponse)
async def get_export_status(
    session_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Obtiene el estado actual de procesamiento de un export.
    
    Args:
        session_id: ID de la sesión de export
        db: Sesión de base de datos
        
    Returns:
        Estado detallado del procesamiento
    """
    try:
        export_session = db.query(ExportSession).filter(
            ExportSession.id == session_id
        ).first()
        
        if not export_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Export session not found: {session_id}"
            )
        
        # Calcular tiempo de procesamiento
        processing_time = 0.0
        if export_session.started_at:
            end_time = export_session.completed_at or datetime.utcnow()
            processing_time = (end_time - export_session.started_at).total_seconds()
        
        return ExportStatusResponse(
            id=export_session.id,
            status=export_session.status,
            progress_percentage=export_session.progress_percentage,
            estimated_completion=export_session.estimated_completion,
            elements_exported=export_session.elements_exported,
            processing_time_seconds=processing_time,
            is_completed=export_session.is_completed,
            has_failed=export_session.has_failed
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get export status {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get export status: {str(e)}"
        )


@router.get("/session/{session_id}/download/{file_name}")
async def download_export_file(
    session_id: UUID,
    file_name: str,
    db: Session = Depends(get_db)
):
    """
    Descarga un archivo de export generado.
    
    Args:
        session_id: ID de la sesión de export
        file_name: Nombre del archivo a descargar
        db: Sesión de base de datos
        
    Returns:
        Archivo para descarga
    """
    try:
        export_session = db.query(ExportSession).filter(
            ExportSession.id == session_id
        ).first()
        
        if not export_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Export session not found: {session_id}"
            )
        
        if export_session.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Export not completed yet. Current status: {export_session.status}"
            )
        
        # Buscar archivo en output_files
        file_path = None
        for file_info in export_session.output_files or []:
            if Path(file_info.get("path", "")).name == file_name:
                file_path = file_info["path"]
                break
        
        if not file_path or not Path(file_path).exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File not found: {file_name}"
            )
        
        # Determinar media type según extensión
        media_type_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".json": "application/json",
            ".csv": "text/csv",
            ".html": "text/html",
            ".apkg": "application/octet-stream"
        }
        
        file_extension = Path(file_path).suffix.lower()
        media_type = media_type_map.get(file_extension, "application/octet-stream")
        
        return FileResponse(
            path=file_path,
            filename=file_name,
            media_type=media_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download export file {file_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download file: {str(e)}"
        )


@router.get("/class/{class_id}/history", response_model=ExportHistoryResponse)
async def get_export_history(
    class_id: UUID,
    page: int = Query(1, ge=1, description="Número de página"),
    page_size: int = Query(20, ge=1, le=100, description="Tamaño de página"),
    format_filter: Optional[str] = Query(None, description="Filtrar por formato"),
    status_filter: Optional[str] = Query(None, description="Filtrar por estado"),
    db: Session = Depends(get_db)
):
    """
    Obtiene historial de exports de una clase.
    
    Args:
        class_id: ID de la clase
        page: Número de página
        page_size: Tamaño de página
        format_filter: Filtro por formato
        status_filter: Filtro por estado
        db: Sesión de base de datos
        
    Returns:
        Historial paginado de exports
    """
    try:
        # Verificar que la clase existe
        class_session = db.query(ClassSession).filter(
            ClassSession.id == class_id
        ).first()
        
        if not class_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Class session not found: {class_id}"
            )
        
        # Construir query
        query = db.query(ExportSession).filter(
            ExportSession.class_session_id == class_id
        )
        
        if format_filter:
            query = query.filter(ExportSession.export_format == format_filter)
        
        if status_filter:
            query = query.filter(ExportSession.status == status_filter)
        
        # Obtener total count
        total_count = query.count()
        
        # Paginación
        offset = (page - 1) * page_size
        exports = query.order_by(ExportSession.created_at.desc()).offset(offset).limit(page_size).all()
        
        return ExportHistoryResponse(
            exports=[ExportSessionResponse.model_validate(exp) for exp in exports],
            total_count=total_count,
            page=page,
            page_size=page_size
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get export history for class {class_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get export history: {str(e)}"
        )


@router.post("/batch", response_model=Dict[str, Any])
async def create_batch_export(
    class_session_ids: List[UUID],
    export_format: str = Query(..., description="Formato de exportación"),
    config: ExportConfigRequest = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """
    Crea exports en batch para múltiples clases.
    
    Args:
        class_session_ids: Lista de IDs de clases
        export_format: Formato de exportación
        config: Configuración del export
        background_tasks: Tareas en background
        db: Sesión de base de datos
        
    Returns:
        Información del batch de exports creado
    """
    try:
        # Validar formato
        valid_formats = ["pdf", "docx", "json", "anki", "csv", "html"]
        if export_format not in valid_formats:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid export format. Must be one of: {', '.join(valid_formats)}"
            )
        
        # Verificar que todas las clases existen
        existing_classes = db.query(ClassSession).filter(
            ClassSession.id.in_(class_session_ids)
        ).all()
        
        existing_ids = {cls.id for cls in existing_classes}
        missing_ids = set(class_session_ids) - existing_ids
        
        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Class sessions not found: {list(missing_ids)}"
            )
        
        # Crear configuración
        config_obj = ConfiguracionExport(**(config.model_dump() if config else {}))
        
        # Crear sessions de export para cada clase
        created_sessions = []
        for class_id in class_session_ids:
            try:
                export_session = await export_service.create_export_session(
                    class_session_id=class_id,
                    export_format=export_format,
                    config=config_obj,
                    db=db
                )
                created_sessions.append(export_session)
                
                # Lanzar procesamiento en background
                if background_tasks:
                    background_tasks.add_task(
                        process_export_session_task.delay,
                        str(export_session.id),
                        False  # No notificar individualmente en batch
                    )
                    
            except Exception as e:
                logger.error(f"Failed to create export for class {class_id}: {e}")
                # Continuar con las demás clases
        
        logger.info(f"Created batch export: {len(created_sessions)} sessions")
        
        return {
            "batch_id": f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            "total_requested": len(class_session_ids),
            "total_created": len(created_sessions),
            "export_format": export_format,
            "session_ids": [str(session.id) for session in created_sessions],
            "created_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create batch export: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create batch export: {str(e)}"
        )


@router.delete("/session/{session_id}", response_model=Dict[str, Any])
async def delete_export_session(
    session_id: UUID,
    delete_files: bool = Query(True, description="Eliminar archivos del sistema"),
    db: Session = Depends(get_db)
):
    """
    Elimina una sesión de export y sus archivos.
    
    Args:
        session_id: ID de la sesión de export
        delete_files: Si eliminar archivos del sistema
        db: Sesión de base de datos
        
    Returns:
        Confirmación de eliminación
    """
    try:
        export_session = db.query(ExportSession).filter(
            ExportSession.id == session_id
        ).first()
        
        if not export_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Export session not found: {session_id}"
            )
        
        # Eliminar archivos del sistema si se solicita
        files_deleted = 0
        if delete_files and export_session.output_files:
            for file_info in export_session.output_files:
                file_path = Path(file_info.get("path", ""))
                if file_path.exists():
                    try:
                        file_path.unlink()
                        files_deleted += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete file {file_path}: {e}")
        
        # Eliminar registro de BD
        db.delete(export_session)
        db.commit()
        
        logger.info(f"Deleted export session {session_id}")
        
        return {
            "session_id": str(session_id),
            "deleted": True,
            "files_deleted": files_deleted,
            "deleted_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete export session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete export session: {str(e)}"
        )


@router.get("/metrics", response_model=ExportMetricsResponse)
async def get_export_metrics(
    days_back: int = Query(30, ge=1, le=365, description="Días hacia atrás para métricas"),
    db: Session = Depends(get_db)
):
    """
    Obtiene métricas globales de exports.
    
    Args:
        days_back: Días hacia atrás para calcular métricas
        db: Sesión de base de datos
        
    Returns:
        Métricas detalladas de exports
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        # Query base para el período
        period_exports = db.query(ExportSession).filter(
            ExportSession.created_at >= cutoff_date
        )
        
        # Métricas básicas
        total_exports = period_exports.count()
        
        # Exports por formato
        exports_by_format = {}
        for exp in period_exports.all():
            format_name = exp.export_format
            exports_by_format[format_name] = exports_by_format.get(format_name, 0) + 1
        
        # Exports por estado
        exports_by_status = {}
        for exp in period_exports.all():
            status_name = exp.status
            exports_by_status[status_name] = exports_by_status.get(status_name, 0) + 1
        
        # Métricas de performance
        completed_exports = period_exports.filter(
            ExportSession.status == "completed"
        ).all()
        
        avg_processing_time = 0.0
        avg_quality_score = 0.0
        total_size_mb = 0.0
        
        if completed_exports:
            avg_processing_time = sum(exp.processing_time_seconds for exp in completed_exports) / len(completed_exports)
            avg_quality_score = sum(exp.quality_score for exp in completed_exports) / len(completed_exports)
            total_size_mb = sum(exp.total_size_bytes for exp in completed_exports) / (1024 * 1024)
        
        # Exports últimas 24h
        yesterday = datetime.utcnow() - timedelta(days=1)
        exports_last_24h = period_exports.filter(
            ExportSession.created_at >= yesterday
        ).count()
        
        # Formato más exportado
        most_exported_format = max(exports_by_format.items(), key=lambda x: x[1])[0] if exports_by_format else "none"
        
        return ExportMetricsResponse(
            total_exports=total_exports,
            exports_by_format=exports_by_format,
            exports_by_status=exports_by_status,
            avg_processing_time=avg_processing_time,
            avg_quality_score=avg_quality_score,
            total_size_exported_mb=total_size_mb,
            exports_last_24h=exports_last_24h,
            most_exported_format=most_exported_format
        )
        
    except Exception as e:
        logger.error(f"Failed to get export metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get export metrics: {str(e)}"
        )


@router.get("/health", response_model=Dict[str, Any])
async def export_health_check():
    """
    Verifica el estado de salud del servicio de export.
    
    Returns:
        Estado de salud del servicio
    """
    try:
        health_info = await export_service.health_check()
        return health_info
        
    except Exception as e:
        logger.error(f"Export health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export health check failed: {str(e)}"
        )
