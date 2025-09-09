"""
Endpoints REST API para procesamiento de IA (ASR y Diarización).
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core import api_logger, get_async_db
from app.models import ProcessingJob, TranscriptionResult, DiarizationResult, ClassSession
from app.models.processing_job import TipoProcesamiento, PrioridadProcesamiento, EstadoProcesamiento
from app.schemas.base import ResponseModel
from app.tasks.processing import process_audio_complete_task, transcribe_audio_task, diarize_audio_task


router = APIRouter(prefix="/processing", tags=["processing"])


@router.post("/start/{class_session_id}")
async def start_processing(
    class_session_id: UUID,
    tipo_procesamiento: TipoProcesamiento = TipoProcesamiento.FULL_PIPELINE,
    prioridad: PrioridadProcesamiento = PrioridadProcesamiento.NORMAL,
    preset_whisper: str = "MEDICAL_HIGH_PRECISION",
    preset_diarizacion: str = "MEDICAL_CLASS_STANDARD",
    usar_vad: bool = True,
    usar_alineacion_temporal: bool = True,
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """
    Iniciar procesamiento de IA para una clase.
    
    Crea un ProcessingJob y lo envía a la cola de Celery.
    """
    try:
        # Verificar que existe la ClassSession y tiene audio
        stmt = select(ClassSession).where(ClassSession.id == class_session_id)
        result = await db.execute(stmt)
        class_session = result.scalar_one_or_none()
        
        if not class_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ClassSession {class_session_id} no encontrada"
            )
        
        if not class_session.ruta_archivo_final:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ClassSession no tiene archivo de audio procesado"
            )
        
        # Verificar si ya existe un job en progreso
        stmt = select(ProcessingJob).where(
            ProcessingJob.class_session_id == class_session_id,
            ProcessingJob.estado.in_([EstadoProcesamiento.PENDIENTE, EstadoProcesamiento.PROCESANDO])
        )
        result = await db.execute(stmt)
        existing_job = result.scalar_one_or_none()
        
        if existing_job:
            return ResponseModel(
                success=False,
                message=f"Ya existe un job de procesamiento en progreso: {existing_job.id}",
                data={
                    "existing_job_id": str(existing_job.id),
                    "estado": existing_job.estado.value,
                    "progreso": existing_job.progreso_porcentaje
                }
            )
        
        # Crear nuevo ProcessingJob
        processing_job = ProcessingJob(
            class_session_id=class_session_id,
            tipo_procesamiento=tipo_procesamiento,
            prioridad=prioridad,
            estado=EstadoProcesamiento.PENDIENTE,
            progreso_porcentaje=0.0,
            config_whisper={"preset": preset_whisper},
            config_diarizacion={"preset": preset_diarizacion},
            usar_vad=usar_vad,
            usar_alineacion_temporal=usar_alineacion_temporal,
            ruta_audio_original=class_session.ruta_archivo_final,
            max_reintentos=3,
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        
        db.add(processing_job)
        await db.commit()
        await db.refresh(processing_job)
        
        # Enviar a cola de Celery según tipo
        if tipo_procesamiento == TipoProcesamiento.FULL_PIPELINE:
            task = process_audio_complete_task.delay(str(processing_job.id))
        elif tipo_procesamiento == TipoProcesamiento.ASR_ONLY:
            task = transcribe_audio_task.delay(str(processing_job.id))
        elif tipo_procesamiento == TipoProcesamiento.DIARIZATION_ONLY:
            task = diarize_audio_task.delay(str(processing_job.id))
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tipo de procesamiento no soportado: {tipo_procesamiento}"
            )
        
        # Actualizar job con task ID
        processing_job.celery_task_id = task.id
        await db.commit()
        
        api_logger.info(
            "Procesamiento iniciado",
            processing_job_id=str(processing_job.id),
            class_session_id=str(class_session_id),
            tipo=tipo_procesamiento.value,
            celery_task_id=task.id
        )
        
        return ResponseModel(
            success=True,
            message="Procesamiento iniciado exitosamente",
            data={
                "processing_job_id": str(processing_job.id),
                "celery_task_id": task.id,
                "tipo_procesamiento": tipo_procesamiento.value,
                "estado": processing_job.estado.value,
                "estimated_time_minutes": _estimate_processing_time(tipo_procesamiento)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(
            "Error iniciando procesamiento",
            class_session_id=str(class_session_id),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno: {str(e)}"
        )


@router.get("/status/{processing_job_id}")
async def get_processing_status(
    processing_job_id: UUID,
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """
    Obtener estado detallado de un job de procesamiento.
    """
    try:
        # Obtener ProcessingJob
        processing_job = await db.get(ProcessingJob, processing_job_id)
        if not processing_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ProcessingJob {processing_job_id} no encontrado"
            )
        
        # Estado básico
        estado_data = processing_job.to_dict()
        
        # Agregar información adicional según estado
        if processing_job.estado == EstadoProcesamiento.COMPLETADO:
            # Obtener resultados si están disponibles
            if processing_job.tipo_procesamiento in [TipoProcesamiento.FULL_PIPELINE, TipoProcesamiento.ASR_ONLY]:
                stmt = select(TranscriptionResult).where(TranscriptionResult.processing_job_id == processing_job_id)
                result = await db.execute(stmt)
                transcription = result.scalar_one_or_none()
                if transcription:
                    estado_data["transcription_result"] = transcription.to_dict()
            
            if processing_job.tipo_procesamiento in [TipoProcesamiento.FULL_PIPELINE, TipoProcesamiento.DIARIZATION_ONLY]:
                stmt = select(DiarizationResult).where(DiarizationResult.processing_job_id == processing_job_id)
                result = await db.execute(stmt)
                diarization = result.scalar_one_or_none()
                if diarization:
                    estado_data["diarization_result"] = diarization.to_dict()
        
        return ResponseModel(
            success=True,
            message="Estado obtenido exitosamente",
            data=estado_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(
            "Error obteniendo estado de procesamiento",
            processing_job_id=str(processing_job_id),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno: {str(e)}"
        )


@router.get("/list")
async def list_processing_jobs(
    estado: Optional[EstadoProcesamiento] = None,
    tipo: Optional[TipoProcesamiento] = None,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """
    Listar jobs de procesamiento con filtros.
    """
    try:
        # Construir query
        stmt = select(ProcessingJob).order_by(ProcessingJob.created_at.desc())
        
        # Aplicar filtros
        if estado:
            stmt = stmt.where(ProcessingJob.estado == estado)
        if tipo:
            stmt = stmt.where(ProcessingJob.tipo_procesamiento == tipo)
        
        # Paginación
        stmt = stmt.offset(offset).limit(limit)
        
        # Ejecutar query
        result = await db.execute(stmt)
        jobs = result.scalars().all()
        
        # Query para total count (sin paginación)
        count_stmt = select(ProcessingJob)
        if estado:
            count_stmt = count_stmt.where(ProcessingJob.estado == estado)
        if tipo:
            count_stmt = count_stmt.where(ProcessingJob.tipo_procesamiento == tipo)
        
        total_result = await db.execute(count_stmt)
        total_count = len(total_result.scalars().all())
        
        return ResponseModel(
            success=True,
            message=f"Encontrados {len(jobs)} jobs de procesamiento",
            data={
                "jobs": [job.to_dict() for job in jobs],
                "pagination": {
                    "total": total_count,
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + len(jobs) < total_count
                }
            }
        )
        
    except Exception as e:
        api_logger.error("Error listando jobs de procesamiento", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno: {str(e)}"
        )


@router.post("/cancel/{processing_job_id}")
async def cancel_processing(
    processing_job_id: UUID,
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """
    Cancelar un job de procesamiento en progreso.
    """
    try:
        # Obtener ProcessingJob
        processing_job = await db.get(ProcessingJob, processing_job_id)
        if not processing_job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ProcessingJob {processing_job_id} no encontrado"
            )
        
        # Verificar que se puede cancelar
        if processing_job.estado not in [EstadoProcesamiento.PENDIENTE, EstadoProcesamiento.PROCESANDO]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se puede cancelar job en estado: {processing_job.estado.value}"
            )
        
        # Cancelar tarea de Celery si existe
        if processing_job.celery_task_id:
            from app.workers.celery_app import celery_app
            celery_app.control.revoke(processing_job.celery_task_id, terminate=True)
        
        # Actualizar estado del job
        processing_job.estado = EstadoProcesamiento.CANCELADO
        processing_job.updated_at = datetime.utcnow()
        processing_job.error_actual = "Cancelado por usuario"
        
        await db.commit()
        
        api_logger.info(
            "Procesamiento cancelado",
            processing_job_id=str(processing_job_id),
            celery_task_id=processing_job.celery_task_id
        )
        
        return ResponseModel(
            success=True,
            message="Procesamiento cancelado exitosamente",
            data={"processing_job_id": str(processing_job_id)}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(
            "Error cancelando procesamiento",
            processing_job_id=str(processing_job_id),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno: {str(e)}"
        )


@router.get("/results/transcription/{transcription_id}")
async def get_transcription_result(
    transcription_id: UUID,
    include_details: bool = Query(default=False),
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """
    Obtener resultado detallado de transcripción.
    """
    try:
        transcription = await db.get(TranscriptionResult, transcription_id)
        if not transcription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"TranscriptionResult {transcription_id} no encontrado"
            )
        
        if include_details:
            data = transcription.to_dict_detailed()
        else:
            data = transcription.to_dict()
        
        return ResponseModel(
            success=True,
            message="Resultado de transcripción obtenido",
            data=data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(
            "Error obteniendo resultado de transcripción",
            transcription_id=str(transcription_id),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno: {str(e)}"
        )


@router.get("/results/diarization/{diarization_id}")
async def get_diarization_result(
    diarization_id: UUID,
    include_details: bool = Query(default=False),
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """
    Obtener resultado detallado de diarización.
    """
    try:
        diarization = await db.get(DiarizationResult, diarization_id)
        if not diarization:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"DiarizationResult {diarization_id} no encontrado"
            )
        
        if include_details:
            data = diarization.to_dict_detailed()
        else:
            data = diarization.to_dict()
        
        return ResponseModel(
            success=True,
            message="Resultado de diarización obtenido",
            data=data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(
            "Error obteniendo resultado de diarización",
            diarization_id=str(diarization_id),
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno: {str(e)}"
        )


@router.get("/health")
async def processing_health_check() -> ResponseModel[Dict[str, Any]]:
    """
    Health check de servicios de procesamiento.
    """
    try:
        from app.services import whisper_service, diarization_service
        
        # Health check de servicios
        whisper_health = await whisper_service.health_check()
        diarization_health = await diarization_service.health_check()
        
        # Estado general
        all_healthy = (
            whisper_health.get("status") == "healthy" and
            diarization_health.get("status") == "healthy"
        )
        
        return ResponseModel(
            success=all_healthy,
            message="Health check de procesamiento completado",
            data={
                "overall_status": "healthy" if all_healthy else "degraded",
                "whisper_service": whisper_health,
                "diarization_service": diarization_health,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        api_logger.error("Error en health check de procesamiento", error=str(e))
        return ResponseModel(
            success=False,
            message="Error en health check",
            data={"error": str(e)}
        )


# ============================================================================
# FUNCIONES DE UTILIDAD
# ============================================================================

def _estimate_processing_time(tipo_procesamiento: TipoProcesamiento) -> int:
    """Estimar tiempo de procesamiento en minutos."""
    if tipo_procesamiento == TipoProcesamiento.FULL_PIPELINE:
        return 15  # ASR + Diarización + Post-procesamiento
    elif tipo_procesamiento == TipoProcesamiento.ASR_ONLY:
        return 8   # Solo ASR
    elif tipo_procesamiento == TipoProcesamiento.DIARIZATION_ONLY:
        return 10  # Solo diarización
    else:
        return 5   # Otros casos
