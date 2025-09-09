"""
Endpoints para gestión de grabaciones de audio.
Maneja subida, procesamiento y gestión de grabaciones de clases.
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import uuid
from datetime import datetime

from app.core import settings, api_logger, validate_upload_file, sanitize_filename
from app.core.database import get_db
from app.models import ClassSession, UploadSession, EstadoUpload
from app.services.chunk_service import chunk_service

router = APIRouter()


class RecordingCreate(BaseModel):
    """Datos para crear una nueva grabación."""
    asignatura: str
    tema: str
    profesor_text: str
    fecha: Optional[datetime] = None
    filename: str
    content_type: str
    file_size_total: Optional[int] = None
    file_checksum: Optional[str] = None


class RecordingResponse(BaseModel):
    """Respuesta de creación de grabación."""
    recording_id: str
    upload_session_id: str
    upload_urls: Optional[Dict[str, str]] = None
    chunk_config: Optional[Dict[str, Any]] = None
    message: str


class RecordingStatus(BaseModel):
    """Estado de una grabación."""
    recording_id: str
    estado_pipeline: str
    created_at: datetime
    updated_at: datetime
    asignatura: str
    tema: str
    profesor_text: str
    duracion_sec: Optional[int] = None
    confianza_asr: Optional[float] = None
    confianza_llm: Optional[float] = None
    notion_page_id: Optional[str] = None


@router.post("/", response_model=RecordingResponse)
async def create_recording(
    recording_data: RecordingCreate,
    db: AsyncSession = Depends(get_db)
) -> RecordingResponse:
    """
    Iniciar una nueva sesión de grabación.
    Crea el registro en base de datos y prepara para subida de audio por chunks.
    """
    try:
        # Crear registro de ClassSession en base de datos
        class_session = ClassSession(
            fecha=recording_data.fecha or datetime.now().date(),
            asignatura=recording_data.asignatura,
            tema=recording_data.tema,
            profesor_text=recording_data.profesor_text,
            estado_pipeline="uploaded"
        )
        
        db.add(class_session)
        await db.commit()
        await db.refresh(class_session)
        
        recording_id = str(class_session.id)
        
        api_logger.info(
            "ClassSession creada",
            recording_id=recording_id,
            asignatura=recording_data.asignatura,
            tema=recording_data.tema,
            profesor=recording_data.profesor_text
        )
        
        # Crear sesión de upload por chunks
        upload_session = await chunk_service.create_upload_session(
            db=db,
            class_session_id=recording_id,
            filename=recording_data.filename,
            content_type=recording_data.content_type,
            file_size_total=recording_data.file_size_total,
            file_checksum=recording_data.file_checksum
        )
        
        # Configuración de upload
        upload_info = {
            "chunk_upload_url": f"/api/v1/recordings/{recording_id}/chunk",
            "complete_url": f"/api/v1/recordings/{recording_id}/complete",
            "status_url": f"/api/v1/recordings/{recording_id}/upload-status",
            "recovery_url": f"/api/v1/recordings/{recording_id}/recovery"
        }
        
        chunk_config = {
            "max_chunk_size_mb": settings.MAX_CHUNK_SIZE_MB,
            "recommended_chunk_size_mb": 5,
            "supported_formats": settings.ALLOWED_AUDIO_FORMATS,
            "upload_session_id": str(upload_session.id),
            "total_chunks_expected": upload_session.total_chunks_expected,
            "expires_at": upload_session.expires_at.isoformat(),
            "validation_enabled": True
        }
        
        api_logger.info(
            "Sesión de grabación creada exitosamente",
            recording_id=recording_id,
            upload_session_id=str(upload_session.id),
            chunk_size_mb=settings.MAX_CHUNK_SIZE_MB
        )
        
        return RecordingResponse(
            recording_id=recording_id,
            upload_session_id=str(upload_session.id),
            upload_urls=upload_info,
            chunk_config=chunk_config,
            message="Grabación iniciada. Sistema de chunks configurado."
        )
        
    except Exception as e:
        api_logger.error(
            "Error creando grabación",
            asignatura=recording_data.asignatura,
            filename=recording_data.filename,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error creando grabación: {str(e)}"
        )


@router.post("/{recording_id}/chunk")
async def upload_audio_chunk(
    recording_id: str,
    upload_session_id: str = Form(...),
    chunk_number: int = Form(...),
    total_chunks: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Subir un chunk de audio de la grabación.
    Sistema robusto con validación, recovery y progress tracking.
    """
    try:
        api_logger.info(
            "Recibiendo chunk de audio",
            recording_id=recording_id,
            upload_session_id=upload_session_id,
            chunk_number=chunk_number,
            total_chunks=total_chunks,
            filename=file.filename,
            content_type=file.content_type
        )
        
        # Validar archivo
        if not file.filename:
            raise HTTPException(status_code=400, detail="Nombre de archivo requerido")
        
        # Leer contenido del chunk
        content = await file.read()
        file_size = len(content)
        
        # Validar tamaño del chunk
        max_chunk_size = settings.MAX_CHUNK_SIZE_MB * 1024 * 1024
        if file_size > max_chunk_size:
            raise HTTPException(
                status_code=413,
                detail=f"Chunk demasiado grande. Máximo: {settings.MAX_CHUNK_SIZE_MB}MB"
            )
        
        # Subir chunk usando el servicio
        result = await chunk_service.upload_chunk(
            db=db,
            upload_session_id=upload_session_id,
            chunk_number=chunk_number,
            chunk_data=content,
            total_chunks=total_chunks
        )
        
        api_logger.info(
            "Chunk procesado exitosamente",
            recording_id=recording_id,
            upload_session_id=upload_session_id,
            chunk_number=chunk_number,
            status=result["status"],
            progress=f"{result['chunks_received']}/{result['total_chunks'] or '?'}"
        )
        
        # Agregar información adicional para el cliente
        result.update({
            "recording_id": recording_id,
            "upload_session_id": upload_session_id,
            "file_size_bytes": file_size,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return result
        
    except ValueError as e:
        api_logger.error(
            "Error de validación en chunk",
            recording_id=recording_id,
            upload_session_id=upload_session_id,
            chunk_number=chunk_number,
            error=str(e)
        )
        raise HTTPException(status_code=400, detail=str(e))
        
    except Exception as e:
        api_logger.error(
            "Error interno procesando chunk",
            recording_id=recording_id,
            upload_session_id=upload_session_id,
            chunk_number=chunk_number,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error procesando chunk: {str(e)}"
        )


@router.post("/{recording_id}/complete")
async def complete_recording_upload(
    recording_id: str,
    upload_session_id: str = Form(...),
    validate_checksum: bool = Form(True),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Completar la subida de grabación y ensamblar archivo final.
    Une todos los chunks, valida integridad e inicia procesamiento.
    """
    try:
        api_logger.info(
            "Completando subida de grabación",
            recording_id=recording_id,
            upload_session_id=upload_session_id,
            validate_checksum=validate_checksum
        )
        
        # Ensamblar archivo final usando el servicio de chunks
        final_url = await chunk_service.assemble_file(
            db=db,
            upload_session_id=upload_session_id,
            validate_checksum=validate_checksum
        )
        
        # Actualizar ClassSession con la URL del archivo
        result = await db.execute(
            select(ClassSession).where(ClassSession.id == recording_id)
        )
        class_session = result.scalar_one_or_none()
        
        if class_session:
            class_session.audio_url = final_url
            class_session.estado_pipeline = "asr"  # Listo para procesamiento ASR
            await db.commit()
        
        # Obtener información final de la sesión de upload
        upload_status = await chunk_service.get_upload_status(db, upload_session_id)
        
        # TODO: Encolar tareas de procesamiento (Celery tasks)
        processing_tasks = [
            "asr_transcribe", 
            "diarize_speakers",
            "postprocess_transcription",
            "nlp_summarize",
            "generate_content"
        ]
        
        api_logger.info(
            "Grabación completada exitosamente",
            recording_id=recording_id,
            upload_session_id=upload_session_id,
            final_url=final_url,
            file_size_mb=round(upload_status["bytes_uploaded"] / (1024 * 1024), 2)
        )
        
        return {
            "message": "Grabación completada exitosamente. Archivo ensamblado.",
            "recording_id": recording_id,
            "upload_session_id": upload_session_id,
            "status": "completed",
            "final_file_url": final_url,
            "file_info": {
                "filename": upload_status["filename"],
                "content_type": upload_status["content_type"],
                "file_size_bytes": upload_status["bytes_uploaded"],
                "file_size_mb": round(upload_status["bytes_uploaded"] / (1024 * 1024), 2),
                "total_chunks": upload_status["chunks_received"],
                "upload_time_seconds": upload_status.get("total_upload_time_sec"),
                "upload_speed_mbps": upload_status.get("upload_speed_mbps")
            },
            "processing_pipeline": processing_tasks,
            "next_step": "asr_processing",
            "estimated_processing_minutes": max(5, upload_status["bytes_uploaded"] // (1024 * 1024 * 2))  # ~2MB/min
        }
        
    except ValueError as e:
        api_logger.error(
            "Error de validación completando upload",
            recording_id=recording_id,
            upload_session_id=upload_session_id,
            error=str(e)
        )
        raise HTTPException(status_code=400, detail=str(e))
        
    except Exception as e:
        api_logger.error(
            "Error interno completando upload",
            recording_id=recording_id,
            upload_session_id=upload_session_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error completando upload: {str(e)}"
        )


@router.get("/{recording_id}/upload-status")
async def get_upload_status(
    recording_id: str,
    upload_session_id: str,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Obtener estado detallado del upload por chunks.
    Incluye progreso, chunks faltantes y métricas de rendimiento.
    """
    try:
        # Obtener estado del upload
        upload_status = await chunk_service.get_upload_status(db, upload_session_id)
        
        # Agregar información del recording
        upload_status.update({
            "recording_id": recording_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        api_logger.info(
            "Estado de upload consultado",
            recording_id=recording_id,
            upload_session_id=upload_session_id,
            estado=upload_status["estado"],
            progress=upload_status["progress_percentage"]
        )
        
        return upload_status
        
    except Exception as e:
        api_logger.error(
            "Error consultando estado de upload",
            recording_id=recording_id,
            upload_session_id=upload_session_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error consultando estado: {str(e)}"
        )


@router.post("/{recording_id}/recovery")
async def recover_upload_session(
    recording_id: str,
    upload_session_id: str,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Recuperar información para reanudar upload interrumpido.
    Proporciona lista de chunks faltantes y configuración.
    """
    try:
        # Obtener estado detallado
        upload_status = await chunk_service.get_upload_status(db, upload_session_id)
        
        # Verificar si la sesión puede ser recuperada
        if upload_status["estado"] in ["completado", "cancelado"]:
            return {
                "recovery_possible": False,
                "message": f"Sesión {upload_status['estado']}, no requiere recovery",
                "current_status": upload_status["estado"]
            }
        
        if upload_status["is_expired"]:
            return {
                "recovery_possible": False,
                "message": "Sesión expirada, crear nueva sesión",
                "expired_at": upload_status["expires_at"]
            }
        
        # Información para recovery
        recovery_info = {
            "recovery_possible": True,
            "recording_id": recording_id,
            "upload_session_id": upload_session_id,
            "chunks_missing": upload_status["missing_chunks"],
            "chunks_received": upload_status["chunks_received"],
            "total_chunks_expected": upload_status["total_chunks_expected"],
            "progress_percentage": upload_status["progress_percentage"],
            "bytes_uploaded": upload_status["bytes_uploaded"],
            "file_size_total": upload_status["file_size_total"],
            "chunk_upload_url": f"/api/v1/recordings/{recording_id}/chunk",
            "complete_url": f"/api/v1/recordings/{recording_id}/complete",
            "expires_at": upload_status["expires_at"],
            "recommendations": []
        }
        
        # Generar recomendaciones para recovery
        if len(upload_status["missing_chunks"]) > 0:
            recovery_info["recommendations"].append({
                "type": "upload_missing_chunks",
                "message": f"Subir {len(upload_status['missing_chunks'])} chunks faltantes",
                "missing_chunks": upload_status["missing_chunks"][:10]  # Primeros 10 para no saturar
            })
        
        if upload_status["progress_percentage"] > 90:
            recovery_info["recommendations"].append({
                "type": "nearly_complete",
                "message": "Upload casi completo, verificar últimos chunks",
                "progress": upload_status["progress_percentage"]
            })
        
        api_logger.info(
            "Recovery info generada",
            recording_id=recording_id,
            upload_session_id=upload_session_id,
            missing_chunks_count=len(upload_status["missing_chunks"]),
            progress=upload_status["progress_percentage"]
        )
        
        return recovery_info
        
    except Exception as e:
        api_logger.error(
            "Error en recovery de upload",
            recording_id=recording_id,
            upload_session_id=upload_session_id,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Error en recovery: {str(e)}"
        )


@router.get("/{recording_id}/status", response_model=RecordingStatus)
async def get_recording_status(
    recording_id: str,
    db: AsyncSession = Depends(get_db)
) -> RecordingStatus:
    """
    Obtener estado actual de una grabación.
    Incluye progreso del pipeline de procesamiento.
    """
    api_logger.info(
        "Consultando estado de grabación",
        recording_id=recording_id
    )
    
    # TODO: Consultar base de datos para obtener estado real
    # Por ahora, devolvemos datos simulados
    
    return RecordingStatus(
        recording_id=recording_id,
        estado_pipeline="asr",  # uploaded, asr, nlp, notion, done, error
        created_at=datetime.now(),
        updated_at=datetime.now(),
        asignatura="Medicina Interna",
        tema="Cardiología - Arritmias",
        profesor_text="Dr. Francesco Rossi",
        duracion_sec=3600,  # 1 hora
        confianza_asr=0.92,
        confianza_llm=None,
        notion_page_id=None
    )


@router.get("/")
async def list_recordings(
    skip: int = 0,
    limit: int = 20,
    asignatura: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Listar grabaciones con filtros opcionales.
    Soporta paginación y filtrado por asignatura.
    """
    api_logger.info(
        "Listando grabaciones",
        skip=skip,
        limit=limit,
        asignatura_filter=asignatura
    )
    
    # TODO: Consultar base de datos con filtros y paginación
    # Por ahora, devolvemos datos simulados
    
    sample_recordings = [
        {
            "recording_id": str(uuid.uuid4()),
            "asignatura": "Medicina Interna",
            "tema": "Cardiología - Arritmias",
            "profesor_text": "Dr. Francesco Rossi", 
            "estado_pipeline": "done",
            "created_at": datetime.now(),
            "duracion_sec": 3600,
            "confianza_asr": 0.92,
            "notion_page_id": "abc123"
        },
        {
            "recording_id": str(uuid.uuid4()),
            "asignatura": "Anatomía",
            "tema": "Sistema Nervioso Central",
            "profesor_text": "Dra. Maria Bianchi",
            "estado_pipeline": "nlp", 
            "created_at": datetime.now(),
            "duracion_sec": 2700,
            "confianza_asr": 0.89,
            "notion_page_id": None
        }
    ]
    
    # Filtrar por asignatura si se especifica
    if asignatura:
        sample_recordings = [
            r for r in sample_recordings 
            if r["asignatura"].lower() == asignatura.lower()
        ]
    
    # Aplicar paginación
    total = len(sample_recordings)
    recordings = sample_recordings[skip:skip + limit]
    
    return {
        "recordings": recordings,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": skip + limit < total
    }


@router.delete("/{recording_id}")
async def delete_recording(
    recording_id: str,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, str]:
    """
    Eliminar una grabación y todos sus datos asociados.
    CUIDADO: Esta operación es irreversible.
    """
    api_logger.info(
        "Eliminando grabación",
        recording_id=recording_id
    )
    
    # TODO:
    # 1. Verificar que la grabación existe
    # 2. Eliminar archivos de audio de MinIO
    # 3. Eliminar registros de base de datos
    # 4. Cancelar tareas de Celery pendientes
    # 5. Opcionalmente eliminar página de Notion
    
    api_logger.warning(
        "Grabación eliminada",
        recording_id=recording_id
    )
    
    return {
        "message": f"Grabación {recording_id} eliminada exitosamente",
        "recording_id": recording_id
    }
