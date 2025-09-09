"""
Endpoints para gestión de grabaciones de audio.
Maneja subida, procesamiento y gestión de grabaciones de clases.
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import uuid
from datetime import datetime

from app.core import settings, api_logger, validate_upload_file, sanitize_filename
from app.core.database import get_db

router = APIRouter()


class RecordingCreate(BaseModel):
    """Datos para crear una nueva grabación."""
    asignatura: str
    tema: str
    profesor_text: str
    fecha: Optional[datetime] = None


class RecordingResponse(BaseModel):
    """Respuesta de creación de grabación."""
    recording_id: str
    upload_urls: Optional[Dict[str, str]] = None
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
    Crea el registro en base de datos y prepara para subida de audio.
    """
    # Generar ID único para la grabación
    recording_id = str(uuid.uuid4())
    
    api_logger.info(
        "Creando nueva grabación",
        recording_id=recording_id,
        asignatura=recording_data.asignatura,
        tema=recording_data.tema,
        profesor=recording_data.profesor_text
    )
    
    # TODO: Crear registro en base de datos (ClassSession)
    # Por ahora, solo simulamos la creación
    
    # En el futuro, aquí se crearían URLs pre-firmadas para MinIO
    # o se configuraría el endpoint de subida por chunks
    
    upload_info = {
        "chunk_upload_url": f"/api/v1/recordings/{recording_id}/chunk",
        "complete_url": f"/api/v1/recordings/{recording_id}/complete",
        "max_chunk_size_mb": 10,
        "supported_formats": settings.ALLOWED_AUDIO_FORMATS
    }
    
    api_logger.info(
        "Grabación creada exitosamente",
        recording_id=recording_id
    )
    
    return RecordingResponse(
        recording_id=recording_id,
        upload_urls=upload_info,
        message="Grabación iniciada. Procede a subir el audio por chunks."
    )


@router.post("/{recording_id}/chunk")
async def upload_audio_chunk(
    recording_id: str,
    chunk_number: int = Form(...),
    total_chunks: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Subir un chunk de audio de la grabación.
    Permite subida resiliente por partes.
    """
    api_logger.info(
        "Recibiendo chunk de audio",
        recording_id=recording_id,
        chunk_number=chunk_number,
        total_chunks=total_chunks,
        filename=file.filename,
        content_type=file.content_type
    )
    
    # Validar archivo
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo requerido")
    
    # Leer contenido para validación de tamaño
    content = await file.read()
    file_size = len(content)
    
    # Validar el archivo
    is_valid, error_msg = validate_upload_file(
        file.filename,
        file.content_type or "application/octet-stream",
        file_size,
        settings.ALLOWED_AUDIO_FORMATS
    )
    
    if not is_valid:
        api_logger.error(
            "Archivo inválido",
            recording_id=recording_id,
            error=error_msg,
            filename=file.filename
        )
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Sanitizar nombre de archivo
    safe_filename = sanitize_filename(file.filename)
    
    # TODO: Guardar chunk en MinIO o sistema de archivos
    # Por ahora, solo simulamos el guardado
    
    api_logger.info(
        "Chunk guardado exitosamente",
        recording_id=recording_id,
        chunk_number=chunk_number,
        file_size_bytes=file_size,
        safe_filename=safe_filename
    )
    
    return {
        "message": f"Chunk {chunk_number}/{total_chunks} recibido exitosamente",
        "recording_id": recording_id,
        "chunk_number": chunk_number,
        "total_chunks": total_chunks,
        "file_size_bytes": file_size,
        "status": "received"
    }


@router.post("/{recording_id}/complete")
async def complete_recording_upload(
    recording_id: str,
    total_chunks: int = Form(...),
    final_filename: str = Form(...),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Completar la subida de grabación y iniciar procesamiento.
    Une todos los chunks y encola las tareas de procesamiento.
    """
    api_logger.info(
        "Completando subida de grabación",
        recording_id=recording_id,
        total_chunks=total_chunks,
        final_filename=final_filename
    )
    
    # TODO: 
    # 1. Verificar que todos los chunks estén presentes
    # 2. Unir chunks en archivo final
    # 3. Actualizar registro en base de datos
    # 4. Encolar tareas de procesamiento (ASR, diarización, etc.)
    
    # Simular encolado de tareas de procesamiento
    processing_tasks = [
        "ingest_audio",
        "asr_transcribe", 
        "diarize",
        "postprocess",
        "nlp_summarize"
    ]
    
    api_logger.info(
        "Procesamiento encolado",
        recording_id=recording_id,
        tasks=processing_tasks
    )
    
    return {
        "message": "Grabación completada. Procesamiento iniciado.",
        "recording_id": recording_id,
        "status": "processing",
        "total_chunks_processed": total_chunks,
        "final_filename": sanitize_filename(final_filename),
        "processing_pipeline": processing_tasks,
        "estimated_time_minutes": 5  # Estimación basada en duración
    }


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
