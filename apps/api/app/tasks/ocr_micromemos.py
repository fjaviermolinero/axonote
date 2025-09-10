"""
Tareas Celery para procesamiento OCR y generación de micro-memos.
Pipeline: OCR → Análisis médico → Generación micro-memos → Sincronización Notion.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import current_task
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import api_logger, get_async_db
from app.models import (
    ClassSession, OCRResult, MicroMemo, MicroMemoCollection,
    LLMAnalysisResult, ResearchResult
)
from app.services.ocr_service import OCRService, ConfiguracionOCR
from app.services.micro_memo_service import MicroMemoService, ConfiguracionMicroMemo
from app.services.notion_service import NotionService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="process_ocr_document")
def process_ocr_document_task(
    self,
    file_key: str,
    class_session_id: str,
    ocr_config: Optional[Dict[str, Any]] = None,
    auto_generate_memos: bool = True
) -> Dict[str, Any]:
    """
    Tarea principal de procesamiento OCR completo.
    
    Args:
        file_key: Clave del archivo en MinIO
        class_session_id: ID de la sesión de clase
        ocr_config: Configuración opcional del OCR
        auto_generate_memos: Si generar micro-memos automáticamente
        
    Returns:
        Resultado del procesamiento con métricas
    """
    session_uuid = UUID(class_session_id)
    
    try:
        # Actualizar estado inicial
        self.update_state(
            state="PROCESSING",
            meta={
                "step": "initializing",
                "progress": 0,
                "message": "Inicializando procesamiento OCR",
                "file_key": file_key
            }
        )
        
        api_logger.info(
            "Iniciando procesamiento OCR",
            file_key=file_key,
            class_session_id=class_session_id,
            task_id=current_task.request.id
        )
        
        # Ejecutar pipeline asíncrono
        resultado = asyncio.run(_execute_ocr_pipeline(
            self,
            file_key,
            session_uuid,
            ocr_config,
            auto_generate_memos
        ))
        
        # Estado final exitoso
        self.update_state(
            state="SUCCESS",
            meta={
                "step": "completed",
                "progress": 100,
                "message": "Procesamiento OCR completado exitosamente",
                "result": resultado
            }
        )
        
        api_logger.info(
            "Procesamiento OCR finalizado",
            file_key=file_key,
            task_id=current_task.request.id,
            ocr_result_id=resultado.get("ocr_result_id"),
            memos_generated=resultado.get("memos_generated", 0),
            processing_time=resultado.get("processing_time")
        )
        
        return resultado
        
    except Exception as e:
        error_msg = f"Error en procesamiento OCR: {str(e)}"
        
        self.update_state(
            state="FAILURE",
            meta={
                "step": "error",
                "progress": 0,
                "message": error_msg,
                "error": str(e)
            }
        )
        
        api_logger.error(
            "Error en procesamiento OCR",
            file_key=file_key,
            task_id=current_task.request.id,
            error=str(e),
            exc_info=True
        )
        
        raise


async def _execute_ocr_pipeline(
    task,
    file_key: str,
    class_session_id: UUID,
    ocr_config: Optional[Dict[str, Any]],
    auto_generate_memos: bool
) -> Dict[str, Any]:
    """Ejecuta el pipeline completo de OCR."""
    start_time = time.time()
    
    async with get_async_db() as db:
        try:
            # Paso 1: Verificar sesión de clase
            task.update_state(
                state="PROCESSING",
                meta={
                    "step": "validating_session",
                    "progress": 5,
                    "message": "Validando sesión de clase"
                }
            )
            
            class_session = await db.get(ClassSession, class_session_id)
            if not class_session:
                raise ValueError(f"Sesión de clase no encontrada: {class_session_id}")
            
            # Paso 2: Configurar servicio OCR
            task.update_state(
                state="PROCESSING",
                meta={
                    "step": "initializing_ocr",
                    "progress": 10,
                    "message": "Inicializando servicio OCR"
                }
            )
            
            ocr_service = OCRService()
            await ocr_service._setup()
            
            # Preparar configuración
            config = ConfiguracionOCR()
            if ocr_config:
                config.engine = ocr_config.get("engine", "tesseract")
                config.languages = ocr_config.get("languages", "ita+eng")
                config.confidence_threshold = ocr_config.get("confidence_threshold", 0.7)
                config.dpi = ocr_config.get("dpi", 300)
                config.medical_mode = ocr_config.get("medical_mode", True)
            
            # Paso 3: Procesamiento OCR
            task.update_state(
                state="PROCESSING",
                meta={
                    "step": "ocr_extraction",
                    "progress": 20,
                    "message": "Extrayendo texto con OCR"
                }
            )
            
            ocr_result = await ocr_service.process_document(
                file_key=file_key,
                class_session_id=class_session_id,
                config=config
            )
            
            # Guardar resultado OCR en BD
            db.add(ocr_result)
            await db.commit()
            await db.refresh(ocr_result)
            
            # Paso 4: Post-procesamiento médico
            task.update_state(
                state="PROCESSING",
                meta={
                    "step": "medical_analysis",
                    "progress": 50,
                    "message": "Analizando contenido médico"
                }
            )
            
            # El análisis médico ya se hizo en el servicio OCR
            medical_terms_count = len(ocr_result.medical_terms_detected or [])
            
            memos_generated = 0
            collection_id = None
            
            # Paso 5: Generación de micro-memos (si está habilitado)
            if auto_generate_memos and ocr_result.is_medical_content:
                task.update_state(
                    state="PROCESSING",
                    meta={
                        "step": "generating_memos",
                        "progress": 70,
                        "message": "Generando micro-memos automáticamente"
                    }
                )
                
                memo_service = MicroMemoService()
                await memo_service._setup()
                
                memo_config = ConfiguracionMicroMemo(
                    max_memos_per_concept=2,
                    min_confidence_threshold=0.6,
                    balance_difficulty=True,
                    auto_validate_high_confidence=True
                )
                
                memos = await memo_service.generate_from_ocr(ocr_result, memo_config)
                
                # Guardar micro-memos en BD
                for memo in memos:
                    db.add(memo)
                
                await db.commit()
                memos_generated = len(memos)
                
                # Crear colección automática si hay suficientes memos
                if memos_generated >= 5:
                    collection = await _create_auto_collection(
                        db, class_session, memos, "ocr_based"
                    )
                    if collection:
                        collection_id = str(collection.id)
            
            # Paso 6: Sincronización con Notion (si está habilitado)
            task.update_state(
                state="PROCESSING",
                meta={
                    "step": "notion_sync",
                    "progress": 90,
                    "message": "Sincronizando con Notion"
                }
            )
            
            notion_synced = False
            try:
                if hasattr(class_session, 'notion_page_id') and class_session.notion_page_id:
                    notion_service = NotionService()
                    await notion_service._setup()
                    
                    # Sincronizar contenido OCR
                    await notion_service.sync_ocr_content(ocr_result)
                    notion_synced = True
            except Exception as e:
                logger.warning(f"Error sincronizando con Notion: {str(e)}")
            
            # Resultado final
            processing_time = time.time() - start_time
            
            return {
                "success": True,
                "ocr_result_id": str(ocr_result.id),
                "text_extracted_length": len(ocr_result.extracted_text or ""),
                "confidence_score": ocr_result.confidence_score,
                "quality_score": ocr_result.quality_score,
                "is_medical_content": ocr_result.is_medical_content,
                "medical_terms_detected": medical_terms_count,
                "pages_processed": ocr_result.pages_processed,
                "processing_time": processing_time,
                "memos_generated": memos_generated,
                "collection_id": collection_id,
                "notion_synced": notion_synced,
                "requires_review": ocr_result.requires_review
            }
            
        except Exception as e:
            await db.rollback()
            raise


@celery_app.task(bind=True, name="generate_micromemos_from_source")
def generate_micromemos_from_source_task(
    self,
    source_id: str,
    source_type: str,  # "ocr", "llm_analysis", "research"
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Genera micro-memos desde una fuente específica.
    
    Args:
        source_id: ID de la fuente (OCRResult, LLMAnalysisResult, etc.)
        source_type: Tipo de fuente
        config: Configuración de generación
        
    Returns:
        Resultado de la generación
    """
    source_uuid = UUID(source_id)
    
    try:
        self.update_state(
            state="PROCESSING",
            meta={
                "step": "initializing",
                "progress": 0,
                "message": f"Inicializando generación desde {source_type}",
                "source_id": source_id
            }
        )
        
        api_logger.info(
            "Iniciando generación de micro-memos",
            source_id=source_id,
            source_type=source_type,
            task_id=current_task.request.id
        )
        
        # Ejecutar generación
        resultado = asyncio.run(_execute_memo_generation(
            self, source_uuid, source_type, config
        ))
        
        self.update_state(
            state="SUCCESS",
            meta={
                "step": "completed",
                "progress": 100,
                "message": "Generación de micro-memos completada",
                "result": resultado
            }
        )
        
        api_logger.info(
            "Generación de micro-memos finalizada",
            source_id=source_id,
            task_id=current_task.request.id,
            memos_generated=resultado.get("memos_generated", 0)
        )
        
        return resultado
        
    except Exception as e:
        error_msg = f"Error generando micro-memos: {str(e)}"
        
        self.update_state(
            state="FAILURE",
            meta={
                "step": "error",
                "progress": 0,
                "message": error_msg,
                "error": str(e)
            }
        )
        
        api_logger.error(
            "Error en generación de micro-memos",
            source_id=source_id,
            task_id=current_task.request.id,
            error=str(e),
            exc_info=True
        )
        
        raise


async def _execute_memo_generation(
    task,
    source_id: UUID,
    source_type: str,
    config: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Ejecuta la generación de micro-memos desde una fuente."""
    start_time = time.time()
    
    async with get_async_db() as db:
        try:
            # Configurar servicio de micro-memos
            task.update_state(
                state="PROCESSING",
                meta={
                    "step": "initializing_service",
                    "progress": 10,
                    "message": "Inicializando servicio de micro-memos"
                }
            )
            
            memo_service = MicroMemoService()
            await memo_service._setup()
            
            # Preparar configuración
            memo_config = ConfiguracionMicroMemo()
            if config:
                memo_config.max_memos_per_concept = config.get("max_memos_per_concept", 3)
                memo_config.min_confidence_threshold = config.get("min_confidence_threshold", 0.6)
                memo_config.balance_difficulty = config.get("balance_difficulty", True)
                memo_config.specialty_focus = config.get("specialty_focus")
            
            # Obtener fuente según tipo
            task.update_state(
                state="PROCESSING",
                meta={
                    "step": "loading_source",
                    "progress": 20,
                    "message": f"Cargando fuente {source_type}"
                }
            )
            
            source = None
            if source_type == "ocr":
                source = await db.get(OCRResult, source_id)
            elif source_type == "llm_analysis":
                source = await db.get(LLMAnalysisResult, source_id)
            elif source_type == "research":
                source = await db.get(ResearchResult, source_id)
            
            if not source:
                raise ValueError(f"Fuente no encontrada: {source_id}")
            
            # Generar micro-memos
            task.update_state(
                state="PROCESSING",
                meta={
                    "step": "generating_memos",
                    "progress": 40,
                    "message": "Generando micro-memos"
                }
            )
            
            memos = []
            if source_type == "ocr":
                memos = await memo_service.generate_from_ocr(source, memo_config)
            elif source_type == "llm_analysis":
                memos = await memo_service.generate_from_llm_analysis(source, memo_config)
            elif source_type == "research":
                memos = await memo_service.generate_from_research(source, memo_config)
            
            # Guardar en BD
            task.update_state(
                state="PROCESSING",
                meta={
                    "step": "saving_memos",
                    "progress": 80,
                    "message": "Guardando micro-memos en base de datos"
                }
            )
            
            for memo in memos:
                db.add(memo)
            
            await db.commit()
            
            # Resultado
            processing_time = time.time() - start_time
            
            return {
                "success": True,
                "source_id": str(source_id),
                "source_type": source_type,
                "memos_generated": len(memos),
                "memo_ids": [str(memo.id) for memo in memos],
                "processing_time": processing_time,
                "avg_confidence": sum(memo.confidence_score or 0 for memo in memos) / len(memos) if memos else 0,
                "difficulty_distribution": _get_difficulty_distribution(memos)
            }
            
        except Exception as e:
            await db.rollback()
            raise


@celery_app.task(bind=True, name="generate_micromemo_collection")
def generate_micromemo_collection_task(
    self,
    class_session_id: str,
    collection_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Genera colección completa de micro-memos para una clase.
    
    Args:
        class_session_id: ID de la sesión de clase
        collection_config: Configuración de la colección
        
    Returns:
        Resultado de la generación de colección
    """
    session_uuid = UUID(class_session_id)
    
    try:
        self.update_state(
            state="PROCESSING",
            meta={
                "step": "initializing",
                "progress": 0,
                "message": "Inicializando generación de colección",
                "class_session_id": class_session_id
            }
        )
        
        api_logger.info(
            "Iniciando generación de colección de micro-memos",
            class_session_id=class_session_id,
            task_id=current_task.request.id
        )
        
        # Ejecutar generación
        resultado = asyncio.run(_execute_collection_generation(
            self, session_uuid, collection_config
        ))
        
        self.update_state(
            state="SUCCESS",
            meta={
                "step": "completed",
                "progress": 100,
                "message": "Colección de micro-memos generada",
                "result": resultado
            }
        )
        
        api_logger.info(
            "Generación de colección finalizada",
            class_session_id=class_session_id,
            task_id=current_task.request.id,
            collection_id=resultado.get("collection_id"),
            total_memos=resultado.get("total_memos")
        )
        
        return resultado
        
    except Exception as e:
        error_msg = f"Error generando colección: {str(e)}"
        
        self.update_state(
            state="FAILURE",
            meta={
                "step": "error",
                "progress": 0,
                "message": error_msg,
                "error": str(e)
            }
        )
        
        api_logger.error(
            "Error en generación de colección",
            class_session_id=class_session_id,
            task_id=current_task.request.id,
            error=str(e),
            exc_info=True
        )
        
        raise


async def _execute_collection_generation(
    task,
    class_session_id: UUID,
    collection_config: Dict[str, Any]
) -> Dict[str, Any]:
    """Ejecuta la generación de colección de micro-memos."""
    start_time = time.time()
    
    async with get_async_db() as db:
        try:
            # Obtener sesión de clase
            task.update_state(
                state="PROCESSING",
                meta={
                    "step": "loading_session",
                    "progress": 10,
                    "message": "Cargando sesión de clase"
                }
            )
            
            class_session = await db.get(ClassSession, class_session_id)
            if not class_session:
                raise ValueError(f"Sesión de clase no encontrada: {class_session_id}")
            
            # Configurar servicio
            task.update_state(
                state="PROCESSING",
                meta={
                    "step": "initializing_service",
                    "progress": 20,
                    "message": "Inicializando servicio de micro-memos"
                }
            )
            
            memo_service = MicroMemoService()
            await memo_service._setup()
            
            # Generar colección
            task.update_state(
                state="PROCESSING",
                meta={
                    "step": "generating_collection",
                    "progress": 40,
                    "message": "Generando colección de micro-memos"
                }
            )
            
            collection = await memo_service.generate_collection(
                class_session, collection_config
            )
            
            # Guardar en BD
            task.update_state(
                state="PROCESSING",
                meta={
                    "step": "saving_collection",
                    "progress": 80,
                    "message": "Guardando colección en base de datos"
                }
            )
            
            db.add(collection)
            await db.commit()
            await db.refresh(collection)
            
            # Actualizar estadísticas
            collection.update_statistics()
            await db.commit()
            
            # Resultado
            processing_time = time.time() - start_time
            
            return {
                "success": True,
                "collection_id": str(collection.id),
                "collection_name": collection.name,
                "total_memos": collection.total_memos,
                "completion_rate": collection.completion_rate,
                "avg_accuracy": collection.avg_accuracy,
                "difficulty_distribution": collection.difficulty_distribution,
                "processing_time": processing_time
            }
            
        except Exception as e:
            await db.rollback()
            raise


@celery_app.task(bind=True, name="update_micromemo_statistics")
def update_micromemo_statistics_task(
    self,
    collection_ids: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Actualiza estadísticas de colecciones de micro-memos.
    
    Args:
        collection_ids: IDs específicos de colecciones, o None para todas
        
    Returns:
        Resultado de la actualización
    """
    try:
        self.update_state(
            state="PROCESSING",
            meta={
                "step": "initializing",
                "progress": 0,
                "message": "Inicializando actualización de estadísticas"
            }
        )
        
        # Ejecutar actualización
        resultado = asyncio.run(_execute_statistics_update(self, collection_ids))
        
        self.update_state(
            state="SUCCESS",
            meta={
                "step": "completed",
                "progress": 100,
                "message": "Estadísticas actualizadas",
                "result": resultado
            }
        )
        
        return resultado
        
    except Exception as e:
        error_msg = f"Error actualizando estadísticas: {str(e)}"
        
        self.update_state(
            state="FAILURE",
            meta={
                "step": "error",
                "progress": 0,
                "message": error_msg,
                "error": str(e)
            }
        )
        
        raise


async def _execute_statistics_update(
    task,
    collection_ids: Optional[List[str]]
) -> Dict[str, Any]:
    """Ejecuta la actualización de estadísticas."""
    async with get_async_db() as db:
        try:
            # Obtener colecciones a actualizar
            collections = []
            if collection_ids:
                for collection_id in collection_ids:
                    collection = await db.get(MicroMemoCollection, UUID(collection_id))
                    if collection:
                        collections.append(collection)
            else:
                # Obtener todas las colecciones activas
                from sqlalchemy import select
                result = await db.execute(
                    select(MicroMemoCollection).where(
                        MicroMemoCollection.status == "active"
                    )
                )
                collections = result.scalars().all()
            
            # Actualizar cada colección
            updated_count = 0
            for i, collection in enumerate(collections):
                task.update_state(
                    state="PROCESSING",
                    meta={
                        "step": "updating_statistics",
                        "progress": int((i / len(collections)) * 100),
                        "message": f"Actualizando colección {collection.name}"
                    }
                )
                
                collection.update_statistics()
                updated_count += 1
            
            await db.commit()
            
            return {
                "success": True,
                "collections_updated": updated_count,
                "total_collections": len(collections)
            }
            
        except Exception as e:
            await db.rollback()
            raise


# Funciones auxiliares

async def _create_auto_collection(
    db: AsyncSession,
    class_session: ClassSession,
    memos: List[MicroMemo],
    collection_type: str
) -> Optional[MicroMemoCollection]:
    """Crea una colección automática de micro-memos."""
    try:
        collection = MicroMemoCollection(
            name=f"Auto: {class_session.asignatura} - {class_session.tema[:50]}",
            description=f"Colección automática generada desde {collection_type}",
            collection_type="auto",
            status="active",
            study_mode="spaced_repetition",
            max_memos_per_session=20,
            enable_spaced_repetition=True,
            total_memos=len(memos),
            auto_include_new_memos=True
        )
        
        # Añadir memos a la colección
        collection.memos = memos
        
        # Actualizar estadísticas
        collection.update_statistics()
        
        db.add(collection)
        return collection
        
    except Exception as e:
        logger.error(f"Error creando colección automática: {str(e)}")
        return None


def _get_difficulty_distribution(memos: List[MicroMemo]) -> Dict[str, int]:
    """Calcula la distribución de dificultad de los memos."""
    distribution = {}
    for memo in memos:
        level = memo.difficulty_level
        distribution[level] = distribution.get(level, 0) + 1
    return distribution
