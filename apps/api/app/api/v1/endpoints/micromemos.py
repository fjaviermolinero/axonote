"""
Endpoints REST API para gestión de micro-memos y flashcards.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from pydantic import BaseModel, Field

from app.core import api_logger, get_async_db
from app.models import (
    ClassSession, MicroMemo, MicroMemoCollection, OCRResult, 
    LLMAnalysisResult, ResearchResult
)
from app.models.micro_memo import (
    TipoMicroMemo, NivelDificultad, EstadoMicroMemo, EspecialidadMedica
)
from app.models.micro_memo_collection import TipoColeccion, EstadoColeccion, ModoEstudio
from app.schemas.base import ResponseModel
from app.services.micro_memo_service import MicroMemoService, ConfiguracionMicroMemo
from app.tasks.ocr_micromemos import (
    generate_micromemos_from_source_task, 
    generate_micromemo_collection_task,
    update_micromemo_statistics_task
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/micromemos", tags=["micromemos"])


# Esquemas Pydantic

class MicroMemoConfigSchema(BaseModel):
    """Configuración para generación de micro-memos."""
    max_memos_per_concept: int = Field(default=3, description="Máximo memos por concepto")
    min_confidence_threshold: float = Field(default=0.6, description="Umbral mínimo de confianza")
    balance_difficulty: bool = Field(default=True, description="Balancear niveles de dificultad")
    auto_validate_high_confidence: bool = Field(default=True, description="Auto-validar alta confianza")
    enable_spaced_repetition: bool = Field(default=True, description="Habilitar repetición espaciada")
    target_language: str = Field(default="ita", description="Idioma objetivo")
    specialty_focus: Optional[str] = Field(None, description="Especialidad médica enfoque")


class CollectionConfigSchema(BaseModel):
    """Configuración para colección de micro-memos."""
    name: str = Field(..., description="Nombre de la colección")
    description: Optional[str] = Field(None, description="Descripción de la colección")
    collection_type: str = Field(default="custom", description="Tipo de colección")
    study_mode: str = Field(default="spaced_repetition", description="Modo de estudio")
    max_memos_per_session: int = Field(default=20, description="Máximo memos por sesión")
    max_session_time: int = Field(default=30, description="Tiempo máximo por sesión (minutos)")
    difficulty_range: Optional[Dict[str, str]] = Field(None, description="Rango de dificultad")
    specialty_filter: Optional[str] = Field(None, description="Filtro por especialidad")
    auto_include_new_memos: bool = Field(default=False, description="Incluir nuevos memos automáticamente")


class StudySessionRequest(BaseModel):
    """Request para sesión de estudio."""
    max_memos: Optional[int] = Field(None, description="Máximo memos en la sesión")
    focus_weaknesses: bool = Field(default=False, description="Enfocarse en debilidades")
    custom_filter: Optional[Dict[str, Any]] = Field(None, description="Filtros personalizados")


class StudyResultRequest(BaseModel):
    """Request para registrar resultado de estudio."""
    memo_id: UUID = Field(..., description="ID del micro-memo")
    correct: bool = Field(..., description="Si la respuesta fue correcta")
    response_time: Optional[float] = Field(None, description="Tiempo de respuesta en segundos")
    difficulty_rating: Optional[int] = Field(None, description="Calificación de dificultad (1-5)")


@router.get("/health")
async def health_check() -> ResponseModel[Dict[str, Any]]:
    """Health check del servicio de micro-memos."""
    try:
        memo_service = MicroMemoService()
        health = await memo_service.health_check()
        
        return ResponseModel(
            success=True,
            message="Micro-memos service health check",
            data=health
        )
        
    except Exception as e:
        logger.error(f"Error en health check micro-memos: {str(e)}")
        return ResponseModel(
            success=False,
            message=f"Error en health check: {str(e)}",
            data={"status": "error", "error": str(e)}
        )


@router.post("/generate/from-source")
async def generate_from_source(
    source_id: UUID,
    source_type: str = Query(..., description="Tipo de fuente: ocr, llm_analysis, research"),
    config: Optional[MicroMemoConfigSchema] = None,
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Genera micro-memos desde una fuente específica."""
    try:
        # Validar tipo de fuente
        valid_sources = ["ocr", "llm_analysis", "research"]
        if source_type not in valid_sources:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tipo de fuente inválido. Válidos: {valid_sources}"
            )
        
        # Verificar que la fuente existe
        source = None
        if source_type == "ocr":
            source = await db.get(OCRResult, source_id)
        elif source_type == "llm_analysis":
            source = await db.get(LLMAnalysisResult, source_id)
        elif source_type == "research":
            source = await db.get(ResearchResult, source_id)
        
        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Fuente {source_type} {source_id} no encontrada"
            )
        
        # Preparar configuración
        config_dict = config.dict() if config else {}
        
        # Enviar a procesamiento asíncrono
        task = generate_micromemos_from_source_task.delay(
            source_id=str(source_id),
            source_type=source_type,
            config=config_dict
        )
        
        api_logger.info(
            "Generación de micro-memos iniciada",
            source_id=str(source_id),
            source_type=source_type,
            task_id=task.id
        )
        
        return ResponseModel(
            success=True,
            message="Generación de micro-memos iniciada",
            data={
                "task_id": task.id,
                "source_id": str(source_id),
                "source_type": source_type,
                "estimated_time": "60-180 segundos"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error iniciando generación: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error iniciando generación: {str(e)}"
        )


@router.get("/class/{class_session_id}")
async def get_class_micromemos(
    class_session_id: UUID,
    skip: int = Query(0, description="Número de memos a omitir"),
    limit: int = Query(50, description="Número máximo de memos"),
    memo_type: Optional[str] = Query(None, description="Filtrar por tipo de memo"),
    difficulty: Optional[str] = Query(None, description="Filtrar por dificultad"),
    status_filter: Optional[str] = Query(None, description="Filtrar por estado"),
    only_needs_review: bool = Query(False, description="Solo memos que necesitan revisión"),
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Obtiene micro-memos de una clase específica."""
    try:
        # Construir query
        stmt = select(MicroMemo).where(MicroMemo.class_session_id == class_session_id)
        
        # Aplicar filtros
        if memo_type:
            stmt = stmt.where(MicroMemo.memo_type == memo_type)
        
        if difficulty:
            stmt = stmt.where(MicroMemo.difficulty_level == difficulty)
        
        if status_filter:
            stmt = stmt.where(MicroMemo.status == status_filter)
        
        if only_needs_review:
            stmt = stmt.where(
                or_(
                    MicroMemo.requires_review == True,
                    MicroMemo.next_review <= datetime.utcnow()
                )
            )
        
        # Ordenar por prioridad y fecha
        stmt = stmt.order_by(
            desc(MicroMemo.study_priority),
            desc(MicroMemo.created_at)
        ).offset(skip).limit(limit)
        
        # Ejecutar query
        result = await db.execute(stmt)
        memos = result.scalars().all()
        
        # Convertir a respuesta
        memos_data = [memo.to_dict() for memo in memos]
        
        # Contar total
        count_stmt = select(func.count(MicroMemo.id)).where(MicroMemo.class_session_id == class_session_id)
        if memo_type:
            count_stmt = count_stmt.where(MicroMemo.memo_type == memo_type)
        if difficulty:
            count_stmt = count_stmt.where(MicroMemo.difficulty_level == difficulty)
        if status_filter:
            count_stmt = count_stmt.where(MicroMemo.status == status_filter)
        
        count_result = await db.execute(count_stmt)
        total_count = count_result.scalar() or 0
        
        return ResponseModel(
            success=True,
            message="Micro-memos de clase obtenidos",
            data={
                "memos": memos_data,
                "pagination": {
                    "total": total_count,
                    "skip": skip,
                    "limit": limit,
                    "returned": len(memos_data)
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Error obteniendo micro-memos de clase: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo micro-memos: {str(e)}"
        )


@router.get("/memo/{memo_id}")
async def get_micromemo_detail(
    memo_id: UUID,
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Obtiene detalles completos de un micro-memo."""
    try:
        memo = await db.get(MicroMemo, memo_id)
        
        if not memo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Micro-memo {memo_id} no encontrado"
            )
        
        return ResponseModel(
            success=True,
            message="Detalles de micro-memo",
            data=memo.to_dict()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo detalle micro-memo: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo detalle: {str(e)}"
        )


@router.post("/collections/create")
async def create_collection(
    class_session_id: UUID,
    config: CollectionConfigSchema,
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Crea una nueva colección de micro-memos."""
    try:
        # Verificar que existe la clase
        class_session = await db.get(ClassSession, class_session_id)
        if not class_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sesión de clase {class_session_id} no encontrada"
            )
        
        # Enviar a generación asíncrona
        task = generate_micromemo_collection_task.delay(
            class_session_id=str(class_session_id),
            collection_config=config.dict()
        )
        
        api_logger.info(
            "Creación de colección iniciada",
            class_session_id=str(class_session_id),
            collection_name=config.name,
            task_id=task.id
        )
        
        return ResponseModel(
            success=True,
            message="Creación de colección iniciada",
            data={
                "task_id": task.id,
                "class_session_id": str(class_session_id),
                "collection_name": config.name,
                "estimated_time": "180-600 segundos"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creando colección: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creando colección: {str(e)}"
        )


@router.get("/collections")
async def get_collections(
    skip: int = Query(0, description="Número de colecciones a omitir"),
    limit: int = Query(20, description="Número máximo de colecciones"),
    status_filter: Optional[str] = Query(None, description="Filtrar por estado"),
    collection_type: Optional[str] = Query(None, description="Filtrar por tipo"),
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Obtiene lista de colecciones de micro-memos."""
    try:
        # Construir query
        stmt = select(MicroMemoCollection)
        
        if status_filter:
            stmt = stmt.where(MicroMemoCollection.status == status_filter)
        
        if collection_type:
            stmt = stmt.where(MicroMemoCollection.collection_type == collection_type)
        
        stmt = stmt.order_by(desc(MicroMemoCollection.created_at)).offset(skip).limit(limit)
        
        # Ejecutar query
        result = await db.execute(stmt)
        collections = result.scalars().all()
        
        # Convertir a respuesta
        collections_data = [collection.to_summary() for collection in collections]
        
        # Contar total
        count_stmt = select(func.count(MicroMemoCollection.id))
        if status_filter:
            count_stmt = count_stmt.where(MicroMemoCollection.status == status_filter)
        if collection_type:
            count_stmt = count_stmt.where(MicroMemoCollection.collection_type == collection_type)
        
        count_result = await db.execute(count_stmt)
        total_count = count_result.scalar() or 0
        
        return ResponseModel(
            success=True,
            message="Colecciones obtenidas",
            data={
                "collections": collections_data,
                "pagination": {
                    "total": total_count,
                    "skip": skip,
                    "limit": limit,
                    "returned": len(collections_data)
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Error obteniendo colecciones: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo colecciones: {str(e)}"
        )


@router.get("/collection/{collection_id}")
async def get_collection_detail(
    collection_id: UUID,
    include_memos: bool = Query(False, description="Incluir micro-memos de la colección"),
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Obtiene detalles completos de una colección."""
    try:
        collection = await db.get(MicroMemoCollection, collection_id)
        
        if not collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Colección {collection_id} no encontrada"
            )
        
        collection_data = collection.to_dict()
        
        # Incluir micro-memos si se solicita
        if include_memos:
            memos_data = [memo.to_study_card() for memo in collection.memos]
            collection_data["memos"] = memos_data
        
        return ResponseModel(
            success=True,
            message="Detalles de colección",
            data=collection_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo detalle colección: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo detalle: {str(e)}"
        )


@router.post("/collection/{collection_id}/study-session")
async def get_study_session(
    collection_id: UUID,
    request: StudySessionRequest,
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Obtiene una sesión de estudio de la colección."""
    try:
        collection = await db.get(MicroMemoCollection, collection_id)
        
        if not collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Colección {collection_id} no encontrada"
            )
        
        # Obtener memos para la sesión
        study_memos = collection.get_study_session(request.max_memos)
        
        # Actualizar fecha de último estudio
        collection.last_studied = datetime.utcnow()
        collection.total_sessions += 1
        await db.commit()
        
        return ResponseModel(
            success=True,
            message="Sesión de estudio preparada",
            data={
                "collection_id": str(collection_id),
                "collection_name": collection.name,
                "session_memos": study_memos,
                "total_memos": len(study_memos),
                "estimated_time": sum(memo.get("estimated_time", 5) for memo in study_memos),
                "study_mode": collection.study_mode
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error preparando sesión de estudio: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error preparando sesión: {str(e)}"
        )


@router.post("/study/record-result")
async def record_study_result(
    result: StudyResultRequest,
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Registra el resultado de estudiar un micro-memo."""
    try:
        memo = await db.get(MicroMemo, result.memo_id)
        
        if not memo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Micro-memo {result.memo_id} no encontrado"
            )
        
        # Registrar sesión de estudio
        memo.record_study_session(result.correct, result.response_time)
        
        # Actualizar dificultad si se proporciona rating
        if result.difficulty_rating:
            # Ajustar dificultad basado en el rating del usuario
            if result.difficulty_rating <= 2 and memo.difficulty_level in ["hard", "very_hard", "expert"]:
                # Si el usuario dice que es fácil pero está marcado como difícil, ajustar
                memo.difficulty_level = "medium"
            elif result.difficulty_rating >= 4 and memo.difficulty_level in ["very_easy", "easy"]:
                # Si el usuario dice que es difícil pero está marcado como fácil, ajustar
                memo.difficulty_level = "hard"
        
        await db.commit()
        
        api_logger.info(
            "Resultado de estudio registrado",
            memo_id=str(result.memo_id),
            correct=result.correct,
            response_time=result.response_time,
            new_success_rate=memo.success_rate
        )
        
        return ResponseModel(
            success=True,
            message="Resultado de estudio registrado",
            data={
                "memo_id": str(result.memo_id),
                "times_studied": memo.times_studied,
                "success_rate": memo.success_rate,
                "next_review": memo.next_review.isoformat() if memo.next_review else None,
                "current_interval": memo.current_interval,
                "performance_rating": memo.performance_rating
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registrando resultado de estudio: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error registrando resultado: {str(e)}"
        )


@router.get("/review/upcoming")
async def get_upcoming_reviews(
    days_ahead: int = Query(7, description="Días hacia adelante para buscar"),
    limit: int = Query(100, description="Máximo memos a retornar"),
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Obtiene micro-memos que necesitan revisión próximamente."""
    try:
        # Fecha límite
        end_date = datetime.utcnow() + timedelta(days=days_ahead)
        
        # Query para memos que necesitan revisión
        stmt = select(MicroMemo).where(
            and_(
                MicroMemo.next_review <= end_date,
                MicroMemo.enable_spaced_repetition == True,
                MicroMemo.status.in_(["approved", "draft"])
            )
        ).order_by(MicroMemo.next_review).limit(limit)
        
        result = await db.execute(stmt)
        memos = result.scalars().all()
        
        # Agrupar por fecha
        reviews_by_date = {}
        for memo in memos:
            if memo.next_review:
                date_key = memo.next_review.date().isoformat()
                if date_key not in reviews_by_date:
                    reviews_by_date[date_key] = []
                reviews_by_date[date_key].append(memo.to_study_card())
        
        return ResponseModel(
            success=True,
            message="Revisiones próximas obtenidas",
            data={
                "reviews_by_date": reviews_by_date,
                "total_memos": len(memos),
                "date_range": {
                    "start": datetime.utcnow().date().isoformat(),
                    "end": end_date.date().isoformat()
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Error obteniendo revisiones próximas: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo revisiones: {str(e)}"
        )


@router.get("/metrics")
async def get_micromemos_metrics(
    days_back: int = Query(7, description="Días hacia atrás para métricas"),
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Obtiene métricas generales de micro-memos."""
    try:
        since_date = datetime.utcnow() - timedelta(days=days_back)
        
        # Total de micro-memos
        total_stmt = select(func.count(MicroMemo.id)).where(
            MicroMemo.created_at >= since_date
        )
        total_result = await db.execute(total_stmt)
        total_memos = total_result.scalar() or 0
        
        # Distribución por tipo
        type_stmt = select(
            MicroMemo.memo_type,
            func.count(MicroMemo.id)
        ).where(
            MicroMemo.created_at >= since_date
        ).group_by(MicroMemo.memo_type)
        
        type_result = await db.execute(type_stmt)
        type_distribution = dict(type_result.all())
        
        # Distribución por dificultad
        difficulty_stmt = select(
            MicroMemo.difficulty_level,
            func.count(MicroMemo.id)
        ).where(
            MicroMemo.created_at >= since_date
        ).group_by(MicroMemo.difficulty_level)
        
        difficulty_result = await db.execute(difficulty_stmt)
        difficulty_distribution = dict(difficulty_result.all())
        
        # Métricas de estudio
        study_stmt = select(
            func.avg(MicroMemo.success_rate),
            func.avg(MicroMemo.times_studied),
            func.count(MicroMemo.id).filter(MicroMemo.times_studied > 0)
        ).where(
            MicroMemo.created_at >= since_date
        )
        
        study_result = await db.execute(study_stmt)
        avg_success_rate, avg_times_studied, studied_count = study_result.first() or (None, None, 0)
        
        # Métricas de colecciones
        collections_stmt = select(func.count(MicroMemoCollection.id)).where(
            MicroMemoCollection.created_at >= since_date
        )
        collections_result = await db.execute(collections_stmt)
        total_collections = collections_result.scalar() or 0
        
        return ResponseModel(
            success=True,
            message="Métricas de micro-memos obtenidas",
            data={
                "period_days": days_back,
                "total_memos": total_memos,
                "total_collections": total_collections,
                "studied_memos": studied_count,
                "study_rate": round(studied_count / total_memos * 100, 2) if total_memos > 0 else 0,
                "avg_success_rate": round(avg_success_rate, 3) if avg_success_rate else None,
                "avg_times_studied": round(avg_times_studied, 1) if avg_times_studied else None,
                "type_distribution": type_distribution,
                "difficulty_distribution": difficulty_distribution
            }
        )
        
    except Exception as e:
        logger.error(f"Error obteniendo métricas micro-memos: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error obteniendo métricas: {str(e)}"
        )


@router.post("/statistics/update")
async def update_statistics(
    collection_ids: Optional[List[UUID]] = Query(None, description="IDs específicos de colecciones"),
    background_tasks: BackgroundTasks = BackgroundTasks()
) -> ResponseModel[Dict[str, Any]]:
    """Actualiza estadísticas de colecciones."""
    try:
        # Convertir UUIDs a strings
        collection_ids_str = [str(id) for id in collection_ids] if collection_ids else None
        
        # Enviar a procesamiento en background
        task = update_micromemo_statistics_task.delay(collection_ids_str)
        
        api_logger.info(
            "Actualización de estadísticas iniciada",
            collection_ids=collection_ids_str,
            task_id=task.id
        )
        
        return ResponseModel(
            success=True,
            message="Actualización de estadísticas iniciada",
            data={
                "task_id": task.id,
                "collections_to_update": len(collection_ids_str) if collection_ids_str else "all"
            }
        )
        
    except Exception as e:
        logger.error(f"Error actualizando estadísticas: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error actualizando estadísticas: {str(e)}"
        )


@router.delete("/memo/{memo_id}")
async def delete_micromemo(
    memo_id: UUID,
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Elimina un micro-memo."""
    try:
        memo = await db.get(MicroMemo, memo_id)
        
        if not memo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Micro-memo {memo_id} no encontrado"
            )
        
        memo_title = memo.title
        await db.delete(memo)
        await db.commit()
        
        api_logger.info(
            "Micro-memo eliminado",
            memo_id=str(memo_id),
            title=memo_title
        )
        
        return ResponseModel(
            success=True,
            message="Micro-memo eliminado correctamente",
            data={
                "deleted_memo_id": str(memo_id),
                "title": memo_title
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando micro-memo: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error eliminando micro-memo: {str(e)}"
        )


@router.delete("/collection/{collection_id}")
async def delete_collection(
    collection_id: UUID,
    delete_memos: bool = Query(False, description="Eliminar también los micro-memos"),
    db: AsyncSession = Depends(get_async_db)
) -> ResponseModel[Dict[str, Any]]:
    """Elimina una colección de micro-memos."""
    try:
        collection = await db.get(MicroMemoCollection, collection_id)
        
        if not collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Colección {collection_id} no encontrada"
            )
        
        collection_name = collection.name
        memos_count = len(collection.memos)
        
        # Eliminar micro-memos si se solicita
        if delete_memos:
            for memo in collection.memos:
                await db.delete(memo)
        
        # Eliminar colección
        await db.delete(collection)
        await db.commit()
        
        api_logger.info(
            "Colección eliminada",
            collection_id=str(collection_id),
            name=collection_name,
            memos_deleted=memos_count if delete_memos else 0
        )
        
        return ResponseModel(
            success=True,
            message="Colección eliminada correctamente",
            data={
                "deleted_collection_id": str(collection_id),
                "name": collection_name,
                "memos_count": memos_count,
                "memos_deleted": delete_memos
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error eliminando colección: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error eliminando colección: {str(e)}"
        )
