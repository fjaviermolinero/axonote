"""
Endpoints API para síntesis de voz (TTS).
Permite generar audio desde micro-memos y contenido textual médico.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import MicroMemo, MicroMemoCollection, TTSResult
from app.services.tts_service import TTSService, ConfiguracionTTS, tts_service
from app.tasks.export_tts import synthesize_collection_tts_task, batch_tts_synthesis_task

logger = logging.getLogger(__name__)

router = APIRouter()


# Schemas de request/response
class TTSConfigRequest(BaseModel):
    """Configuración para síntesis TTS."""
    
    # Configuración básica
    voice_model: str = Field("it_riccardo_quality", description="Modelo de voz a utilizar")
    language: str = Field("ita", description="Idioma del contenido")
    speed_factor: float = Field(1.0, ge=0.5, le=2.0, description="Factor de velocidad (0.5x - 2.0x)")
    audio_quality: str = Field("medium", description="Calidad del audio (low, medium, high, studio)")
    
    # Configuración de audio
    audio_format: str = Field("mp3", description="Formato del archivo de audio")
    bitrate_kbps: int = Field(128, ge=64, le=320, description="Bitrate en kbps")
    sample_rate_hz: int = Field(22050, description="Frecuencia de muestreo en Hz")
    channels: int = Field(1, ge=1, le=2, description="Número de canales")
    
    # Procesamiento médico
    apply_medical_normalization: bool = Field(True, description="Aplicar normalización médica")
    expand_abbreviations: bool = Field(True, description="Expandir abreviaciones médicas")
    use_ssml: bool = Field(True, description="Usar SSML para énfasis")
    emphasize_keywords: bool = Field(True, description="Enfatizar palabras clave")
    
    # Configuración para estudio
    study_mode: Optional[str] = Field(None, description="Modo de estudio (sequential, question_pause, spaced_repetition)")
    pause_duration_ms: int = Field(1000, ge=100, le=5000, description="Duración de pausas en ms")
    question_pause_ms: int = Field(3000, ge=500, le=10000, description="Pausa después de preguntas en ms")
    add_intro_outro: bool = Field(False, description="Añadir introducción y conclusión")
    
    # Configuración avanzada
    min_confidence_threshold: float = Field(0.7, ge=0.0, le=1.0, description="Umbral mínimo de confianza")
    validate_pronunciation: bool = Field(True, description="Validar pronunciación médica")
    custom_pronunciations: Optional[Dict[str, str]] = Field(None, description="Pronunciaciones personalizadas")


class SynthesizeMemoRequest(BaseModel):
    """Request para sintetizar micro-memo individual."""
    config: TTSConfigRequest = Field(..., description="Configuración TTS")


class SynthesizeCollectionRequest(BaseModel):
    """Request para sintetizar colección completa."""
    config: TTSConfigRequest = Field(..., description="Configuración TTS")


class BatchTTSRequest(BaseModel):
    """Request para síntesis TTS en batch."""
    micro_memo_ids: List[UUID] = Field(..., description="Lista de IDs de micro-memos")
    config: TTSConfigRequest = Field(..., description="Configuración TTS")
    batch_size: int = Field(5, ge=1, le=20, description="Tamaño del batch")
    parallel_processing: bool = Field(False, description="Procesamiento en paralelo")


class TTSResultResponse(BaseModel):
    """Response con resultado de síntesis TTS."""
    id: UUID
    tts_type: str
    voice_model: str
    language: str
    speed_factor: float
    status: str
    progress_percentage: float
    audio_file_path: Optional[str]
    audio_format: str
    duration_seconds: float
    file_size_bytes: int
    synthesis_quality: float
    confidence_score: float
    has_chapters: bool
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str] = None
    
    # Propiedades computadas
    is_completed: bool
    duration_formatted: str
    file_size_mb: float
    audio_quality_display: str
    content_type_display: str
    
    class Config:
        from_attributes = True


class TTSCollectionResultsResponse(BaseModel):
    """Response con resultados TTS de una colección."""
    collection_id: UUID
    collection_name: str
    tts_results: List[TTSResultResponse]
    total_duration_seconds: float
    total_size_mb: float
    avg_quality_score: float


class TTSMetricsResponse(BaseModel):
    """Response con métricas de TTS."""
    total_synthesis: int
    synthesis_by_type: Dict[str, int]
    synthesis_by_status: Dict[str, int]
    avg_synthesis_time: float
    avg_quality_score: float
    total_audio_duration_hours: float
    total_audio_size_gb: float
    synthesis_last_24h: int
    most_used_voice_model: str


# Endpoints
@router.post("/memo/{memo_id}/synthesize", response_model=TTSResultResponse, status_code=status.HTTP_201_CREATED)
async def synthesize_memo_tts(
    memo_id: UUID,
    request: SynthesizeMemoRequest,
    db: Session = Depends(get_db)
):
    """
    Sintetiza TTS de un micro-memo individual.
    
    Args:
        memo_id: ID del micro-memo
        request: Configuración TTS
        db: Sesión de base de datos
        
    Returns:
        Resultado de la síntesis TTS
    """
    try:
        # Verificar que el memo existe
        memo = db.query(MicroMemo).filter(MicroMemo.id == memo_id).first()
        
        if not memo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Micro-memo not found: {memo_id}"
            )
        
        # Crear configuración TTS
        config_dict = request.config.model_dump()
        config = ConfiguracionTTS(**config_dict)
        
        # Sintetizar TTS
        tts_result = await tts_service.synthesize_micro_memo(memo, config, db)
        
        logger.info(f"TTS synthesis completed for memo {memo_id}: {tts_result.id}")
        
        # Construir response con propiedades computadas
        response_data = TTSResultResponse.model_validate(tts_result)
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to synthesize TTS for memo {memo_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to synthesize TTS: {str(e)}"
        )


@router.post("/collection/{collection_id}/synthesize", response_model=TTSResultResponse, status_code=status.HTTP_202_ACCEPTED)
async def synthesize_collection_tts(
    collection_id: UUID,
    request: SynthesizeCollectionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Sintetiza TTS de una colección completa (procesamiento asíncrono).
    
    Args:
        collection_id: ID de la colección
        request: Configuración TTS
        background_tasks: Tareas en background
        db: Sesión de base de datos
        
    Returns:
        Información inicial del procesamiento TTS
    """
    try:
        # Verificar que la colección existe
        collection = db.query(MicroMemoCollection).filter(
            MicroMemoCollection.id == collection_id
        ).first()
        
        if not collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Collection not found: {collection_id}"
            )
        
        # Verificar que tiene micro-memos
        memos_count = db.query(MicroMemo).filter(
            MicroMemo.collection_id == collection_id
        ).count()
        
        if memos_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Collection has no micro-memos to synthesize"
            )
        
        # Crear configuración TTS
        config_dict = request.config.model_dump()
        
        # Lanzar procesamiento en background
        background_tasks.add_task(
            synthesize_collection_tts_task.delay,
            str(collection_id),
            config_dict
        )
        
        # Crear registro TTS inicial
        tts_result = TTSResult(
            collection_id=collection_id,
            class_session_id=collection.class_session_id,
            tts_type="collection",
            voice_model=config_dict.get("voice_model", "it_riccardo_quality"),
            language=config_dict.get("language", "ita"),
            speed_factor=config_dict.get("speed_factor", 1.0),
            original_text=f"Collection: {collection.name} ({memos_count} memos)",
            status="processing",
            has_chapters=True
        )
        
        db.add(tts_result)
        db.commit()
        db.refresh(tts_result)
        
        logger.info(f"Started TTS synthesis for collection {collection_id}: {tts_result.id}")
        
        return TTSResultResponse.model_validate(tts_result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start TTS synthesis for collection {collection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start TTS synthesis: {str(e)}"
        )


@router.get("/result/{result_id}", response_model=TTSResultResponse)
async def get_tts_result(
    result_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Obtiene información detallada de un resultado TTS.
    
    Args:
        result_id: ID del resultado TTS
        db: Sesión de base de datos
        
    Returns:
        Información completa del resultado TTS
    """
    try:
        tts_result = db.query(TTSResult).filter(TTSResult.id == result_id).first()
        
        if not tts_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"TTS result not found: {result_id}"
            )
        
        return TTSResultResponse.model_validate(tts_result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get TTS result {result_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get TTS result: {str(e)}"
        )


@router.get("/result/{result_id}/audio")
async def stream_tts_audio(
    result_id: UUID,
    download: bool = Query(False, description="Forzar descarga del archivo"),
    db: Session = Depends(get_db)
):
    """
    Transmite o descarga el audio de un resultado TTS.
    
    Args:
        result_id: ID del resultado TTS
        download: Si forzar descarga en lugar de streaming
        db: Sesión de base de datos
        
    Returns:
        Stream de audio o archivo para descarga
    """
    try:
        tts_result = db.query(TTSResult).filter(TTSResult.id == result_id).first()
        
        if not tts_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"TTS result not found: {result_id}"
            )
        
        if tts_result.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"TTS not completed yet. Current status: {tts_result.status}"
            )
        
        if not tts_result.audio_file_path or not Path(tts_result.audio_file_path).exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Audio file not found"
            )
        
        # Determinar media type
        media_type_map = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "ogg": "audio/ogg"
        }
        media_type = media_type_map.get(tts_result.audio_format, "audio/mpeg")
        
        # Nombre del archivo
        filename = f"tts_{result_id}_{tts_result.tts_type}.{tts_result.audio_format}"
        
        if download:
            # Descarga directa
            return FileResponse(
                path=tts_result.audio_file_path,
                filename=filename,
                media_type=media_type
            )
        else:
            # Streaming
            def iter_file():
                with open(tts_result.audio_file_path, "rb") as f:
                    while chunk := f.read(8192):
                        yield chunk
            
            return StreamingResponse(
                iter_file(),
                media_type=media_type,
                headers={
                    "Content-Disposition": f"inline; filename={filename}",
                    "Content-Length": str(tts_result.file_size_bytes)
                }
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stream TTS audio {result_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stream audio: {str(e)}"
        )


@router.get("/collection/{collection_id}/results", response_model=TTSCollectionResultsResponse)
async def get_collection_tts_results(
    collection_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Obtiene todos los resultados TTS de una colección.
    
    Args:
        collection_id: ID de la colección
        db: Sesión de base de datos
        
    Returns:
        Resultados TTS de la colección con estadísticas
    """
    try:
        # Verificar que la colección existe
        collection = db.query(MicroMemoCollection).filter(
            MicroMemoCollection.id == collection_id
        ).first()
        
        if not collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Collection not found: {collection_id}"
            )
        
        # Obtener resultados TTS
        tts_results = db.query(TTSResult).filter(
            TTSResult.collection_id == collection_id
        ).order_by(TTSResult.created_at.desc()).all()
        
        # Calcular estadísticas
        total_duration = sum(result.duration_seconds for result in tts_results)
        total_size_mb = sum(result.file_size_bytes for result in tts_results) / (1024 * 1024)
        
        completed_results = [r for r in tts_results if r.status == "completed"]
        avg_quality = sum(r.synthesis_quality for r in completed_results) / len(completed_results) if completed_results else 0.0
        
        return TTSCollectionResultsResponse(
            collection_id=collection_id,
            collection_name=collection.name,
            tts_results=[TTSResultResponse.model_validate(result) for result in tts_results],
            total_duration_seconds=total_duration,
            total_size_mb=total_size_mb,
            avg_quality_score=avg_quality
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get collection TTS results {collection_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get collection TTS results: {str(e)}"
        )


@router.post("/batch", response_model=Dict[str, Any], status_code=status.HTTP_202_ACCEPTED)
async def create_batch_tts(
    request: BatchTTSRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Crea síntesis TTS en batch para múltiples micro-memos.
    
    Args:
        request: Configuración del batch TTS
        background_tasks: Tareas en background
        db: Sesión de base de datos
        
    Returns:
        Información del batch TTS iniciado
    """
    try:
        # Verificar que todos los memos existen
        existing_memos = db.query(MicroMemo).filter(
            MicroMemo.id.in_(request.micro_memo_ids)
        ).all()
        
        existing_ids = {memo.id for memo in existing_memos}
        missing_ids = set(request.micro_memo_ids) - existing_ids
        
        if missing_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Micro-memos not found: {list(missing_ids)}"
            )
        
        # Preparar configuración para batch
        config_dict = request.config.model_dump()
        config_dict.update({
            "batch_size": request.batch_size,
            "parallel_processing": request.parallel_processing
        })
        
        # Lanzar procesamiento en background
        background_tasks.add_task(
            batch_tts_synthesis_task.delay,
            [str(memo_id) for memo_id in request.micro_memo_ids],
            config_dict
        )
        
        logger.info(f"Started batch TTS synthesis for {len(request.micro_memo_ids)} memos")
        
        return {
            "batch_id": f"batch_tts_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            "total_memos": len(request.micro_memo_ids),
            "batch_size": request.batch_size,
            "parallel_processing": request.parallel_processing,
            "voice_model": request.config.voice_model,
            "started_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create batch TTS: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create batch TTS: {str(e)}"
        )


@router.get("/metrics", response_model=TTSMetricsResponse)
async def get_tts_metrics(
    days_back: int = Query(30, ge=1, le=365, description="Días hacia atrás para métricas"),
    db: Session = Depends(get_db)
):
    """
    Obtiene métricas globales de TTS.
    
    Args:
        days_back: Días hacia atrás para calcular métricas
        db: Sesión de base de datos
        
    Returns:
        Métricas detalladas de TTS
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        # Query base para el período
        period_tts = db.query(TTSResult).filter(
            TTSResult.created_at >= cutoff_date
        )
        
        # Métricas básicas
        total_synthesis = period_tts.count()
        
        # Síntesis por tipo
        synthesis_by_type = {}
        for result in period_tts.all():
            type_name = result.tts_type
            synthesis_by_type[type_name] = synthesis_by_type.get(type_name, 0) + 1
        
        # Síntesis por estado
        synthesis_by_status = {}
        for result in period_tts.all():
            status_name = result.status
            synthesis_by_status[status_name] = synthesis_by_status.get(status_name, 0) + 1
        
        # Métricas de performance
        completed_synthesis = period_tts.filter(
            TTSResult.status == "completed"
        ).all()
        
        avg_synthesis_time = 0.0
        avg_quality_score = 0.0
        total_audio_duration_hours = 0.0
        total_audio_size_gb = 0.0
        
        if completed_synthesis:
            avg_synthesis_time = sum(s.processing_time_seconds for s in completed_synthesis) / len(completed_synthesis)
            avg_quality_score = sum(s.synthesis_quality for s in completed_synthesis) / len(completed_synthesis)
            total_audio_duration_hours = sum(s.duration_seconds for s in completed_synthesis) / 3600
            total_audio_size_gb = sum(s.file_size_bytes for s in completed_synthesis) / (1024 * 1024 * 1024)
        
        # Síntesis últimas 24h
        yesterday = datetime.utcnow() - timedelta(days=1)
        synthesis_last_24h = period_tts.filter(
            TTSResult.created_at >= yesterday
        ).count()
        
        # Modelo de voz más usado
        voice_model_count = {}
        for result in period_tts.all():
            model = result.voice_model
            voice_model_count[model] = voice_model_count.get(model, 0) + 1
        
        most_used_voice_model = max(voice_model_count.items(), key=lambda x: x[1])[0] if voice_model_count else "none"
        
        return TTSMetricsResponse(
            total_synthesis=total_synthesis,
            synthesis_by_type=synthesis_by_type,
            synthesis_by_status=synthesis_by_status,
            avg_synthesis_time=avg_synthesis_time,
            avg_quality_score=avg_quality_score,
            total_audio_duration_hours=total_audio_duration_hours,
            total_audio_size_gb=total_audio_size_gb,
            synthesis_last_24h=synthesis_last_24h,
            most_used_voice_model=most_used_voice_model
        )
        
    except Exception as e:
        logger.error(f"Failed to get TTS metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get TTS metrics: {str(e)}"
        )


@router.get("/health", response_model=Dict[str, Any])
async def tts_health_check():
    """
    Verifica el estado de salud del servicio TTS.
    
    Returns:
        Estado de salud del servicio
    """
    try:
        health_info = await tts_service.health_check()
        return health_info
        
    except Exception as e:
        logger.error(f"TTS health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TTS health check failed: {str(e)}"
        )
