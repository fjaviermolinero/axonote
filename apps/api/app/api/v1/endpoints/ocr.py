"""
Endpoints REST API para procesamiento OCR y gestión de documentos.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import (
    APIRouter, Depends, HTTPException, Query, File, UploadFile, 
    Form, status, BackgroundTasks
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc
from pydantic import BaseModel, Field

from app.core import api_logger, get_async_db
from app.models import ClassSession, OCRResult, MicroMemo
from app.models.ocr_result import EstadoOCR, TipoContenidoOCR, MotorOCR
from app.schemas.base import ResponseModel
from app.services.ocr_service import OCRService, ConfiguracionOCR
from app.services.minio_service import minio_service
from app.tasks.ocr_micromemos import process_ocr_document_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ocr", tags=["ocr"])


# Esquemas Pydantic

class OCRConfigSchema(BaseModel):
    """Configuración para procesamiento OCR."""
    engine: str = Field(default="tesseract", description="Motor OCR a utilizar")
    languages: str = Field(default="ita+eng", description="Idiomas para OCR")
    confidence_threshold: float = Field(default=0.7, description="Umbral mínimo de confianza")
    dpi: int = Field(default=300, description="DPI para procesamiento")
    enhance_image: bool = Field(default=True, description="Mejorar imagen antes de OCR")
    medical_mode: bool = Field(default=True, description="Modo optimizado para contenido médico")


class OCRResultResponse(BaseModel):
    """Respuesta con resultado OCR."""
    id: str
    class_session_id: str
    source_filename: str
    content_type: Optional[str]
    confidence_score: Optional[float]
    quality_score: Optional[float]
    is_medical_content: bool
    status: str
    extracted_text_preview: str  # Primeros 500 caracteres
    medical_terms_count: int
    pages_processed: int
    processing_time: Optional[float]
    created_at: str


class OCRProcessRequest(BaseModel):
    """Request para procesamiento OCR."""
    auto_generate_memos: bool = Field(default=True, description="Generar micro-memos automáticamente")
    config: Optional[OCRConfigSchema] = Field(None, description="Configuración OCR")


@router.get("/health")
async def health_check() -> ResponseModel[Dict[str, Any]]:
    """Health check del servicio OCR."""
    try:
        ocr_service = OCRService()
        health = await ocr_service.health_check()
        
        return ResponseModel(
            success=True,
            message="OCR service health check",
            data=health
        )
        
    except Exception as e:
        logger.error(f"Error en health check OCR: {str(e)}")
        return ResponseModel(
            success=False,
            message=f"Error en health check: {str(e)}",
            data={"status": "error", "error": str(e)}
        )


@router.post("/process")
async def process_document(
    file: UploadFile = File(..., description="Documento a procesar con OCR"),
    class_session_id: UUID = Form(..., description="ID de la sesión de clase"),
    auto_generate_memos: bool = Form(default=True, description="Generar micro-memos automáticamente"),
    config: Optional[str] = Form(None, description="Configuración OCR en JSON"),
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """
    Procesa un documento con OCR y opcionalmente genera micro-memos.
    
    Sube el archivo a MinIO y envía a procesamiento asíncrono.
    """
    try:
        # Validar sesión de clase
        stmt = select(ClassSession).where(ClassSession.id == class_session_id)
        result = await db.execute(stmt)
        class_session = result.scalar_one_or_none()
        
        if not class_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sesión de clase {class_session_id} no encontrada"
            )
        
        # Validar archivo
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nombre de archivo requerido"
            )
        
        # Verificar formato soportado
        supported_formats = ["pdf", "png", "jpg", "jpeg", "tiff", "bmp"]
        file_ext = file.filename.lower().split('.')[-1]
        if file_ext not in supported_formats:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Formato no soportado: {file_ext}. Soportados: {supported_formats}"
            )
        
        # Verificar tamaño de archivo
        file_content = await file.read()
        if len(file_content) > 50 * 1024 * 1024:  # 50MB
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Archivo demasiado grande. Máximo 50MB."
            )
        
        # Subir archivo a MinIO
        file_key = f"ocr_documents/{class_session_id}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
        
        await minio_service.upload_file(
            file_key=file_key,
            file_data=file_content,
            content_type=file.content_type or "application/octet-stream"
        )
        
        # Preparar configuración OCR
        ocr_config_dict = None
        if config:
            try:
                import json
                ocr_config_dict = json.loads(config)
            except Exception as e:
                logger.warning(f"Error parseando configuración OCR: {str(e)}")
        
        # Enviar a procesamiento asíncrono
        task = process_ocr_document_task.delay(
            file_key=file_key,
            class_session_id=str(class_session_id),
            ocr_config=ocr_config_dict,
            auto_generate_memos=auto_generate_memos
        )
        
        api_logger.info(
            "Documento enviado a procesamiento OCR",
            file_key=file_key,
            class_session_id=str(class_session_id),
            task_id=task.id,
            filename=file.filename,
            file_size=len(file_content)
        )
        
        return ResponseModel(
            success=True,
            message="Documento enviado a procesamiento OCR",
            data={
                "task_id": task.id,
                "file_key": file_key,
                "filename": file.filename,
                "file_size": len(file_content),
                "class_session_id": str(class_session_id),
                "auto_generate_memos": auto_generate_memos,
                "estimated_processing_time": "60-300 segundos"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error procesando documento OCR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error procesando documento: {str(e)}"
        )


@router.get("/status/{task_id}")
async def get_processing_status(task_id: str) -> ResponseModel[Dict[str, Any]]:
    """Obtiene el estado de una tarea de procesamiento OCR."""
    try:
        # Obtener estado de Celery
        from app.workers.celery_app import celery_app
        
        task_result = celery_app.AsyncResult(task_id)
        
        response_data = {
            "task_id": task_id,
            "status": task_result.status,
            "ready": task_result.ready()
        }
        
        if task_result.info:
            if isinstance(task_result.info, dict):
                response_data.update(task_result.info)
            else:
                response_data["info"] = str(task_result.info)
        
        # Si está completado, incluir resultado
        if task_result.ready() and task_result.successful():
            response_data["result"] = task_result.result
        
        return ResponseModel(
            success=True,
            message="Estado de procesamiento OCR",
            data=response_data
        )
        
    except Exception as e:
        logger.error(f"Error obteniendo estado OCR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo estado: {str(e)}"
        )


@router.get("/results/class/{class_session_id}")
async def get_class_ocr_results(
    class_session_id: UUID,
    skip: int = Query(0, description="Número de resultados a omitir"),
    limit: int = Query(50, description="Número máximo de resultados"),
    status_filter: Optional[str] = Query(None, description="Filtrar por estado"),
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Obtiene los resultados OCR de una clase específica."""
    try:
        # Construir query
        stmt = select(OCRResult).where(OCRResult.class_session_id == class_session_id)
        
        if status_filter:
            stmt = stmt.where(OCRResult.status == status_filter)
        
        stmt = stmt.order_by(desc(OCRResult.created_at)).offset(skip).limit(limit)
        
        # Ejecutar query
        result = await db.execute(stmt)
        ocr_results = result.scalars().all()
        
        # Convertir a respuesta
        results_data = []
        for ocr_result in ocr_results:
            result_data = OCRResultResponse(
                id=str(ocr_result.id),
                class_session_id=str(ocr_result.class_session_id),
                source_filename=ocr_result.source_filename,
                content_type=ocr_result.content_type,
                confidence_score=ocr_result.confidence_score,
                quality_score=ocr_result.quality_score,
                is_medical_content=ocr_result.is_medical_content,
                status=ocr_result.status,
                extracted_text_preview=(ocr_result.extracted_text or "")[:500],
                medical_terms_count=len(ocr_result.medical_terms_detected or []),
                pages_processed=ocr_result.pages_processed,
                processing_time=ocr_result.processing_time,
                created_at=ocr_result.created_at.isoformat() if ocr_result.created_at else ""
            )
            results_data.append(result_data.dict())
        
        # Estadísticas generales
        total_stmt = select(func.count(OCRResult.id)).where(OCRResult.class_session_id == class_session_id)
        total_result = await db.execute(total_stmt)
        total_count = total_result.scalar()
        
        return ResponseModel(
            success=True,
            message="Resultados OCR obtenidos",
            data={
                "results": results_data,
                "pagination": {
                    "total": total_count,
                    "skip": skip,
                    "limit": limit,
                    "returned": len(results_data)
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Error obteniendo resultados OCR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo resultados: {str(e)}"
        )


@router.get("/result/{ocr_result_id}")
async def get_ocr_result_detail(
    ocr_result_id: UUID,
    include_raw_data: bool = Query(False, description="Incluir datos RAW del OCR"),
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Obtiene detalles completos de un resultado OCR."""
    try:
        ocr_result = await db.get(OCRResult, ocr_result_id)
        
        if not ocr_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resultado OCR {ocr_result_id} no encontrado"
            )
        
        result_data = ocr_result.to_dict()
        
        # Incluir texto completo
        result_data["extracted_text_full"] = ocr_result.extracted_text
        result_data["corrected_text_full"] = ocr_result.corrected_text
        
        # Incluir datos RAW si se solicita
        if include_raw_data:
            result_data["raw_ocr_data"] = ocr_result.raw_ocr_data
        
        # Incluir información de micro-memos relacionados
        memos_stmt = select(MicroMemo).where(MicroMemo.source_ocr_id == ocr_result_id)
        memos_result = await db.execute(memos_stmt)
        related_memos = memos_result.scalars().all()
        
        result_data["related_memos"] = [
            {
                "id": str(memo.id),
                "title": memo.title,
                "memo_type": memo.memo_type,
                "difficulty_level": memo.difficulty_level,
                "status": memo.status
            }
            for memo in related_memos
        ]
        
        return ResponseModel(
            success=True,
            message="Detalles de resultado OCR",
            data=result_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo detalle OCR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo detalle: {str(e)}"
        )


@router.post("/reprocess/{ocr_result_id}")
async def reprocess_ocr(
    ocr_result_id: UUID,
    config: Optional[OCRConfigSchema] = None,
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Reprocesa un resultado OCR con nueva configuración."""
    try:
        # Obtener resultado OCR existente
        ocr_result = await db.get(OCRResult, ocr_result_id)
        
        if not ocr_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resultado OCR {ocr_result_id} no encontrado"
            )
        
        # Preparar configuración
        ocr_config_dict = None
        if config:
            ocr_config_dict = config.dict()
        
        # Enviar a reprocesamiento
        task = process_ocr_document_task.delay(
            file_key=ocr_result.source_file_id,
            class_session_id=str(ocr_result.class_session_id),
            ocr_config=ocr_config_dict,
            auto_generate_memos=True
        )
        
        api_logger.info(
            "Documento enviado a reprocesamiento OCR",
            ocr_result_id=str(ocr_result_id),
            task_id=task.id,
            filename=ocr_result.source_filename
        )
        
        return ResponseModel(
            success=True,
            message="Documento enviado a reprocesamiento OCR",
            data={
                "task_id": task.id,
                "original_result_id": str(ocr_result_id),
                "filename": ocr_result.source_filename
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reprocesando OCR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reprocesando: {str(e)}"
        )


@router.get("/metrics")
async def get_ocr_metrics(
    days_back: int = Query(7, description="Días hacia atrás para métricas"),
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Obtiene métricas generales del servicio OCR."""
    try:
        # Fecha límite
        since_date = datetime.utcnow() - timedelta(days=days_back)
        
        # Métricas básicas
        from sqlalchemy import func
        
        # Total de documentos procesados
        total_stmt = select(func.count(OCRResult.id)).where(
            OCRResult.created_at >= since_date
        )
        total_result = await db.execute(total_stmt)
        total_documents = total_result.scalar() or 0
        
        # Documentos por estado
        status_stmt = select(
            OCRResult.status,
            func.count(OCRResult.id)
        ).where(
            OCRResult.created_at >= since_date
        ).group_by(OCRResult.status)
        
        status_result = await db.execute(status_stmt)
        status_distribution = dict(status_result.all())
        
        # Documentos médicos vs no médicos
        medical_stmt = select(
            OCRResult.is_medical_content,
            func.count(OCRResult.id)
        ).where(
            OCRResult.created_at >= since_date
        ).group_by(OCRResult.is_medical_content)
        
        medical_result = await db.execute(medical_stmt)
        medical_distribution = dict(medical_result.all())
        
        # Métricas de calidad promedio
        quality_stmt = select(
            func.avg(OCRResult.confidence_score),
            func.avg(OCRResult.quality_score),
            func.avg(OCRResult.processing_time)
        ).where(
            and_(
                OCRResult.created_at >= since_date,
                OCRResult.status == EstadoOCR.COMPLETED
            )
        )
        
        quality_result = await db.execute(quality_stmt)
        avg_confidence, avg_quality, avg_processing_time = quality_result.first() or (None, None, None)
        
        # Distribución por tipo de contenido
        content_type_stmt = select(
            OCRResult.content_type,
            func.count(OCRResult.id)
        ).where(
            OCRResult.created_at >= since_date
        ).group_by(OCRResult.content_type)
        
        content_type_result = await db.execute(content_type_stmt)
        content_type_distribution = dict(content_type_result.all())
        
        return ResponseModel(
            success=True,
            message="Métricas de OCR obtenidas",
            data={
                "period_days": days_back,
                "total_documents": total_documents,
                "status_distribution": status_distribution,
                "medical_content_distribution": {
                    "medical": medical_distribution.get(True, 0),
                    "non_medical": medical_distribution.get(False, 0)
                },
                "content_type_distribution": content_type_distribution,
                "quality_metrics": {
                    "avg_confidence": round(avg_confidence, 3) if avg_confidence else None,
                    "avg_quality_score": round(avg_quality, 3) if avg_quality else None,
                    "avg_processing_time": round(avg_processing_time, 2) if avg_processing_time else None
                },
                "success_rate": round(
                    status_distribution.get("completed", 0) / total_documents * 100, 2
                ) if total_documents > 0 else 0
            }
        )
        
    except Exception as e:
        logger.error(f"Error obteniendo métricas OCR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo métricas: {str(e)}"
        )


@router.delete("/result/{ocr_result_id}")
async def delete_ocr_result(
    ocr_result_id: UUID,
    delete_memos: bool = Query(False, description="Eliminar micro-memos relacionados"),
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Elimina un resultado OCR y opcionalmente sus micro-memos."""
    try:
        ocr_result = await db.get(OCRResult, ocr_result_id)
        
        if not ocr_result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Resultado OCR {ocr_result_id} no encontrado"
            )
        
        # Contar micro-memos relacionados
        memos_stmt = select(func.count(MicroMemo.id)).where(MicroMemo.source_ocr_id == ocr_result_id)
        memos_result = await db.execute(memos_stmt)
        memos_count = memos_result.scalar() or 0
        
        # Eliminar micro-memos si se solicita
        deleted_memos = 0
        if delete_memos and memos_count > 0:
            delete_memos_stmt = select(MicroMemo).where(MicroMemo.source_ocr_id == ocr_result_id)
            memos_to_delete = await db.execute(delete_memos_stmt)
            for memo in memos_to_delete.scalars():
                await db.delete(memo)
            deleted_memos = memos_count
        
        # Eliminar resultado OCR
        await db.delete(ocr_result)
        await db.commit()
        
        api_logger.info(
            "Resultado OCR eliminado",
            ocr_result_id=str(ocr_result_id),
            filename=ocr_result.source_filename,
            deleted_memos=deleted_memos
        )
        
        return ResponseModel(
            success=True,
            message="Resultado OCR eliminado correctamente",
            data={
                "deleted_result_id": str(ocr_result_id),
                "filename": ocr_result.source_filename,
                "related_memos_count": memos_count,
                "deleted_memos": deleted_memos
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando resultado OCR: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error eliminando resultado: {str(e)}"
        )
