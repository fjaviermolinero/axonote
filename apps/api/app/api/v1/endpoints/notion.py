"""
Endpoints REST para gestión completa de integración Notion.
Incluye sincronización, templates, configuración y monitoreo.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.models import (
    ClassSession, NotionSyncRecord, NotionWorkspace, NotionTemplate,
    NotionTemplateInstance, LLMAnalysisResult
)
from app.services.notion_service import notion_service
from app.tasks.notion import (
    full_sync_class_task, bidirectional_sync_task, workspace_maintenance_task
)

router = APIRouter()


# ============================================================
# MODELOS PYDANTIC PARA REQUEST/RESPONSE
# ============================================================

class NotionSyncRequest(BaseModel):
    """Request para sincronización con Notion."""
    include_attachments: bool = True
    template_detection: bool = True
    bidirectional_sync: bool = True
    force_update: bool = False
    template_preference: Optional[str] = None


class NotionSyncResponse(BaseModel):
    """Response de sincronización."""
    status: str
    task_id: Optional[str] = None
    notion_page_id: Optional[str] = None
    sync_record_id: Optional[str] = None
    message: str


class NotionHealthResponse(BaseModel):
    """Response del health check."""
    status: str
    token_configured: bool
    api_accessible: bool
    databases_configured: bool
    rate_limiter_active: bool
    workspace_id: Optional[str] = None
    error: Optional[str] = None


class NotionConfigResponse(BaseModel):
    """Response de configuración Notion."""
    workspace_id: Optional[str]
    databases: Dict[str, Optional[str]]
    sync_settings: Dict[str, Any]
    templates_available: List[str]
    auto_sync_enabled: bool


class NotionSyncStatusResponse(BaseModel):
    """Response del estado de sincronización."""
    total_records: int
    synced: int
    pending: int
    errors: int
    last_sync: Optional[datetime]
    sync_health: str


class NotionTemplateResponse(BaseModel):
    """Response de template."""
    id: str
    name: str
    type: str
    description: Optional[str]
    is_active: bool
    usage_count: int
    last_used: Optional[datetime]


class NotionMetricsResponse(BaseModel):
    """Response de métricas."""
    total_pages_created: int
    total_syncs_performed: int
    avg_sync_success_rate: float
    avg_sync_duration: float
    attachments_uploaded: int
    api_calls_today: int
    cache_hit_rate: float


# ============================================================
# ENDPOINTS DE SINCRONIZACIÓN
# ============================================================

@router.post("/sync/class/{class_session_id}", response_model=NotionSyncResponse)
async def sync_class_to_notion(
    class_session_id: UUID,
    sync_request: NotionSyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Sincronizar una clase específica con Notion.
    
    Crea o actualiza una página Notion con toda la información
    de la clase incluyendo transcripción, análisis y research.
    """
    
    # Verificar que la clase existe
    class_session = db.get(ClassSession, class_session_id)
    if not class_session:
        raise HTTPException(status_code=404, detail="Clase no encontrada")
    
    # Verificar configuración de Notion
    health_check = await notion_service.health_check()
    if health_check.get("status") != "healthy":
        raise HTTPException(
            status_code=503, 
            detail=f"Servicio Notion no disponible: {health_check.get('error', 'Unknown error')}"
        )
    
    # Iniciar tarea de sincronización
    sync_options = sync_request.dict()
    task = full_sync_class_task.apply_async(
        args=[str(class_session_id), sync_options]
    )
    
    return NotionSyncResponse(
        status="queued",
        task_id=task.id,
        message=f"Sincronización iniciada para clase '{class_session.class_name}'"
    )


@router.get("/sync/status/{task_id}")
async def get_sync_status(task_id: str):
    """
    Obtener estado de una tarea de sincronización.
    
    Permite monitorear el progreso en tiempo real de la sincronización.
    """
    from celery.result import AsyncResult
    
    task_result = AsyncResult(task_id)
    
    if task_result.state == 'PENDING':
        return {
            "status": "pending",
            "message": "Tarea en cola de procesamiento"
        }
    elif task_result.state == 'PROGRESS':
        return {
            "status": "processing",
            "progress": task_result.info.get('progress', 0),
            "stage": task_result.info.get('stage', 'unknown'),
            "message": task_result.info.get('message', 'Procesando...')
        }
    elif task_result.state == 'SUCCESS':
        return {
            "status": "completed",
            "result": task_result.info
        }
    elif task_result.state == 'FAILURE':
        return {
            "status": "failed",
            "error": str(task_result.info)
        }
    else:
        return {
            "status": task_result.state.lower(),
            "info": task_result.info
        }


@router.post("/sync/bulk")
async def bulk_sync_classes(
    class_ids: List[UUID],
    sync_request: NotionSyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Sincronizar múltiples clases en lote.
    
    Útil para sincronización inicial o actualizaciones masivas.
    """
    
    # Validar que todas las clases existen
    existing_classes = db.execute(
        select(ClassSession).where(ClassSession.id.in_(class_ids))
    ).scalars().all()
    
    if len(existing_classes) != len(class_ids):
        raise HTTPException(
            status_code=400, 
            detail="Algunas clases especificadas no existen"
        )
    
    # Importar y ejecutar tarea de bulk sync
    from app.tasks.notion import bulk_sync_task
    
    sync_options = sync_request.dict()
    task = bulk_sync_task.apply_async(
        args=[[str(cid) for cid in class_ids], sync_options]
    )
    
    return {
        "status": "queued",
        "task_id": task.id,
        "classes_count": len(class_ids),
        "message": f"Sincronización en lote iniciada para {len(class_ids)} clases"
    }


@router.post("/sync/bidirectional/{notion_page_id}")
async def trigger_bidirectional_sync(
    notion_page_id: str,
    background_tasks: BackgroundTasks
):
    """
    Activar sincronización bidireccional para una página específica.
    
    Detecta cambios en Notion y los sincroniza de vuelta al sistema.
    """
    
    task = bidirectional_sync_task.apply_async(args=[notion_page_id])
    
    return {
        "status": "queued",
        "task_id": task.id,
        "message": f"Sincronización bidireccional iniciada para página {notion_page_id}"
    }


# ============================================================
# ENDPOINTS DE CONFIGURACIÓN Y SALUD
# ============================================================

@router.get("/health", response_model=NotionHealthResponse)
async def notion_health_check():
    """
    Verificar salud completa del servicio Notion.
    
    Incluye conectividad, configuración y estado de databases.
    """
    health_data = await notion_service.health_check()
    
    return NotionHealthResponse(**health_data)


@router.get("/config", response_model=NotionConfigResponse)
async def get_notion_config(db: Session = Depends(get_db)):
    """
    Obtener configuración actual de Notion.
    
    Incluye databases configuradas, templates disponibles y settings.
    """
    from app.core import settings
    
    # Obtener templates disponibles
    templates = db.execute(
        select(NotionTemplate).where(NotionTemplate.is_active == True)
    ).scalars().all()
    
    return NotionConfigResponse(
        workspace_id=settings.NOTION_WORKSPACE_ID,
        databases={
            "classes": settings.NOTION_DB_CLASSES,
            "sources": settings.NOTION_DB_SOURCES,
            "terms": settings.NOTION_DB_TERMS,
            "cards": settings.NOTION_DB_CARDS,
            "professors": settings.NOTION_DB_PROFESSORS,
            "research": settings.NOTION_DB_RESEARCH
        },
        sync_settings={
            "auto_sync_enabled": settings.NOTION_AUTO_SYNC_ENABLED,
            "sync_on_completion": settings.NOTION_SYNC_ON_COMPLETION,
            "sync_interval_minutes": settings.NOTION_SYNC_INTERVAL_MINUTES,
            "bidirectional_sync": settings.NOTION_BIDIRECTIONAL_SYNC,
            "include_attachments": settings.NOTION_UPLOAD_ATTACHMENTS
        },
        templates_available=[t.template_name for t in templates],
        auto_sync_enabled=settings.NOTION_AUTO_SYNC_ENABLED
    )


@router.get("/sync-status", response_model=NotionSyncStatusResponse)
async def get_sync_overview(db: Session = Depends(get_db)):
    """
    Obtener resumen del estado de sincronización.
    
    Estadísticas generales de todos los registros de sync.
    """
    
    # Contar registros por estado
    total_records = db.execute(select(NotionSyncRecord)).scalars().all()
    
    synced = len([r for r in total_records if r.sync_status.value == "sincronizado"])
    pending = len([r for r in total_records if r.sync_status.value == "pendiente"])
    errors = len([r for r in total_records if r.sync_status.value == "error"])
    
    # Última sincronización
    last_sync = None
    if total_records:
        last_synced = max(
            [r for r in total_records if r.last_sync_at], 
            key=lambda x: x.last_sync_at,
            default=None
        )
        if last_synced:
            last_sync = last_synced.last_sync_at
    
    # Determinar salud general
    if errors > len(total_records) * 0.1:  # Más del 10% con errores
        sync_health = "unhealthy"
    elif pending > len(total_records) * 0.3:  # Más del 30% pendientes
        sync_health = "degraded"
    else:
        sync_health = "healthy"
    
    return NotionSyncStatusResponse(
        total_records=len(total_records),
        synced=synced,
        pending=pending,
        errors=errors,
        last_sync=last_sync,
        sync_health=sync_health
    )


# ============================================================
# ENDPOINTS DE TEMPLATES
# ============================================================

@router.get("/templates", response_model=List[NotionTemplateResponse])
async def list_notion_templates(
    active_only: bool = Query(True, description="Solo templates activos"),
    db: Session = Depends(get_db)
):
    """
    Listar templates de Notion disponibles.
    
    Incluye información de uso y estado de cada template.
    """
    
    query = select(NotionTemplate)
    if active_only:
        query = query.where(NotionTemplate.is_active == True)
    
    templates = db.execute(query).scalars().all()
    
    return [
        NotionTemplateResponse(
            id=str(t.id),
            name=t.template_name,
            type=t.template_type.value,
            description=t.description,
            is_active=t.is_active,
            usage_count=t.usage_stats.get("total_uses", 0) if t.usage_stats else 0,
            last_used=t.last_used_at
        )
        for t in templates
    ]


@router.get("/templates/{template_id}")
async def get_template_details(
    template_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Obtener detalles completos de un template.
    
    Incluye configuración, estadísticas de uso y estructura.
    """
    
    template = db.get(NotionTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template no encontrado")
    
    return {
        "id": str(template.id),
        "name": template.template_name,
        "type": template.template_type.value,
        "description": template.description,
        "version": template.version,
        "is_active": template.is_active,
        "template_config": template.template_config,
        "content_mapping": template.content_mapping,
        "style_config": template.style_config,
        "auto_detection_rules": template.auto_detection_rules,
        "usage_stats": template.usage_stats,
        "created_at": template.created_at,
        "last_used_at": template.last_used_at
    }


# ============================================================
# ENDPOINTS DE GESTIÓN Y MANTENIMIENTO
# ============================================================

@router.post("/maintenance")
async def run_workspace_maintenance(
    background_tasks: BackgroundTasks,
    workspace_id: Optional[str] = None
):
    """
    Ejecutar mantenimiento del workspace Notion.
    
    Incluye limpieza de cache, verificación de salud y optimización.
    """
    
    task = workspace_maintenance_task.apply_async(args=[workspace_id])
    
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "Mantenimiento de workspace iniciado"
    }


@router.post("/attachments/manage/{class_session_id}")
async def manage_class_attachments(
    class_session_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Gestionar attachments específicos de una clase.
    
    Procesa y sube archivos de audio, imágenes y documentos.
    """
    
    # Verificar que la clase existe
    class_session = db.get(ClassSession, class_session_id)
    if not class_session:
        raise HTTPException(status_code=404, detail="Clase no encontrada")
    
    # TODO: Implementar manage_attachments_task
    # task = manage_attachments_task.apply_async(args=[str(class_session_id)])
    task = None
    
    return {
        "status": "queued",
        "task_id": None,  # task.id if task else None,
        "message": f"Gestión de attachments iniciada para clase '{class_session.class_name}'"
    }


@router.get("/metrics", response_model=NotionMetricsResponse)
async def get_notion_metrics(db: Session = Depends(get_db)):
    """
    Obtener métricas completas de Notion.
    
    Estadísticas de uso, performance y calidad del servicio.
    """
    
    # Obtener registros de sync
    sync_records = db.execute(select(NotionSyncRecord)).scalars().all()
    
    # Calcular métricas básicas
    total_syncs = len(sync_records)
    successful_syncs = len([r for r in sync_records if r.sync_status.value == "sincronizado"])
    success_rate = successful_syncs / total_syncs if total_syncs > 0 else 0
    
    # Duración promedio de sync
    durations = []
    for record in sync_records:
        if record.performance_metrics and "avg_sync_time" in record.performance_metrics:
            durations.append(record.performance_metrics["avg_sync_time"])
    
    avg_duration = sum(durations) / len(durations) if durations else 0
    
    # Attachments procesados
    total_attachments = 0
    for record in sync_records:
        if record.sync_metadata and "attachments_processed" in record.sync_metadata:
            total_attachments += record.sync_metadata["attachments_processed"]
    
    # Cache hit rate (simulado)
    cache_hit_rate = 0.85  # TODO: Obtener de servicio real
    
    return NotionMetricsResponse(
        total_pages_created=successful_syncs,
        total_syncs_performed=total_syncs,
        avg_sync_success_rate=success_rate,
        avg_sync_duration=avg_duration,
        attachments_uploaded=total_attachments,
        api_calls_today=0,  # TODO: Implementar tracking
        cache_hit_rate=cache_hit_rate
    )


@router.get("/records/{class_session_id}")
async def get_sync_record(
    class_session_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Obtener registro de sincronización de una clase específica.
    
    Incluye historial, métricas y estado actual.
    """
    
    sync_record = db.execute(
        select(NotionSyncRecord).where(
            and_(
                NotionSyncRecord.entity_type == "class_session",
                NotionSyncRecord.entity_id == class_session_id
            )
        )
    ).scalar_one_or_none()
    
    if not sync_record:
        raise HTTPException(status_code=404, detail="Registro de sincronización no encontrado")
    
    return {
        "id": str(sync_record.id),
        "entity_type": sync_record.entity_type,
        "entity_id": str(sync_record.entity_id),
        "notion_page_id": sync_record.notion_page_id,
        "sync_status": sync_record.sync_status.value,
        "created_at": sync_record.created_at,
        "last_sync_at": sync_record.last_sync_at,
        "last_notion_update": sync_record.last_notion_update,
        "sync_metadata": sync_record.sync_metadata,
        "error_count": sync_record.error_count,
        "error_details": sync_record.error_details,
        "performance_metrics": sync_record.performance_metrics,
        "is_active": sync_record.is_active,
        "is_healthy": sync_record.is_healthy
    }


@router.delete("/records/{class_session_id}")
async def delete_sync_record(
    class_session_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Eliminar registro de sincronización de una clase.
    
    Útil para resetear estado de sync o limpiar registros antiguos.
    """
    
    sync_record = db.execute(
        select(NotionSyncRecord).where(
            and_(
                NotionSyncRecord.entity_type == "class_session",
                NotionSyncRecord.entity_id == class_session_id
            )
        )
    ).scalar_one_or_none()
    
    if not sync_record:
        raise HTTPException(status_code=404, detail="Registro de sincronización no encontrado")
    
    db.delete(sync_record)
    db.commit()
    
    return {
        "status": "success",
        "message": "Registro de sincronización eliminado"
    }
