"""
Tareas Celery para procesamiento de exports y síntesis TTS.
Pipeline: Export processing → TTS synthesis → Notion sync → Cleanup
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import current_task
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import api_logger, get_async_db
from app.models import (
    ClassSession, ExportSession, TTSResult, MicroMemo, MicroMemoCollection,
    NotionSyncRecord
)
from app.services.export_service import ExportService, ConfiguracionExport, export_service
from app.services.tts_service import TTSService, ConfiguracionTTS, tts_service
from app.services.notion_service import NotionService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="process_export_session")
async def process_export_session_task(
    self,
    export_session_id: str,
    notify_completion: bool = True
):
    """
    Procesa una sesión de export completa.
    
    Args:
        export_session_id: ID de la sesión de export
        notify_completion: Si notificar completación vía Notion
    """
    start_time = time.time()
    task_id = self.request.id
    
    logger.info(f"Starting export processing task {task_id} for session {export_session_id}")
    
    # Actualizar progreso inicial
    current_task.update_state(
        state="PROCESSING",
        meta={
            "stage": "initializing",
            "progress": 0,
            "message": "Iniciando procesamiento de export...",
            "started_at": datetime.utcnow().isoformat()
        }
    )
    
    try:
        async with get_async_db() as db:
            # Obtener sesión de export
            export_session = await db.get(ExportSession, UUID(export_session_id))
            if not export_session:
                raise ValueError(f"Export session not found: {export_session_id}")
            
            # Actualizar estado en BD
            export_session.status = "processing"
            export_session.started_at = datetime.utcnow()
            export_session.progress_percentage = 5.0
            await db.commit()
            
            # Fase 1: Recopilar contenido (10-30%)
            current_task.update_state(
                state="PROCESSING",
                meta={
                    "stage": "gathering_content",
                    "progress": 10,
                    "message": "Recopilando contenido para export..."
                }
            )
            
            contenido = await export_service.gather_content_for_export(export_session, db)
            
            export_session.progress_percentage = 30.0
            export_session.elements_exported = contenido.total_elementos
            export_session.transcriptions_count = len(contenido.transcripciones)
            export_session.ocr_results_count = len(contenido.ocr_results)
            export_session.micro_memos_count = len(contenido.micro_memos)
            export_session.research_results_count = len(contenido.research_results)
            await db.commit()
            
            # Fase 2: Generar export según formato (30-80%)
            current_task.update_state(
                state="PROCESSING",
                meta={
                    "stage": "generating_export",
                    "progress": 30,
                    "message": f"Generando export en formato {export_session.export_format.upper()}..."
                }
            )
            
            output_file = None
            if export_session.export_format == "pdf":
                output_file = await export_service.export_to_pdf(export_session, contenido)
            elif export_session.export_format == "docx":
                output_file = await export_service.export_to_docx(export_session, contenido)
            elif export_session.export_format == "json":
                output_file = await export_service.export_to_json(export_session, contenido)
            elif export_session.export_format == "anki":
                output_file = await export_service.export_to_anki(export_session, contenido)
            elif export_session.export_format == "csv":
                output_file = await export_service.export_to_csv(export_session, contenido)
            elif export_session.export_format == "html":
                output_file = await export_service.export_to_html(export_session, contenido)
            else:
                raise ValueError(f"Unsupported export format: {export_session.export_format}")
            
            # Actualizar información del archivo
            if output_file:
                import os
                file_size = os.path.getsize(output_file)
                export_session.output_files = [{
                    "path": output_file,
                    "size": file_size,
                    "format": export_session.export_format,
                    "created_at": datetime.utcnow().isoformat()
                }]
                export_session.total_size_bytes = file_size
            
            export_session.progress_percentage = 80.0
            await db.commit()
            
            # Fase 3: TTS si está habilitado (80-90%)
            tts_result = None
            if export_session.include_tts and contenido.micro_memos:
                current_task.update_state(
                    state="PROCESSING",
                    meta={
                        "stage": "generating_tts",
                        "progress": 80,
                        "message": "Generando audio TTS para micro-memos..."
                    }
                )
                
                # Generar TTS para micro-memos si el formato lo permite (principalmente Anki)
                if export_session.export_format == "anki":
                    tts_config = ConfiguracionTTS(
                        study_mode="question_pause",
                        audio_quality="medium"
                    )
                    
                    # Crear una colección temporal para TTS
                    temp_collection = MicroMemoCollection(
                        name=f"Export TTS - {export_session.id}",
                        class_session_id=export_session.class_session_id,
                        collection_type="custom",
                        auto_include_new=False
                    )
                    
                    db.add(temp_collection)
                    await db.commit()
                    
                    # Generar TTS de la colección
                    tts_result = await tts_service.synthesize_collection(
                        temp_collection, tts_config, db
                    )
                    
                    # Asociar TTS con export session
                    tts_result.export_session_id = export_session.id
                    await db.commit()
            
            export_session.progress_percentage = 90.0
            await db.commit()
            
            # Fase 4: Sincronización Notion si está habilitada (90-95%)
            if notify_completion:
                current_task.update_state(
                    state="PROCESSING",
                    meta={
                        "stage": "notion_sync",
                        "progress": 90,
                        "message": "Sincronizando con Notion..."
                    }
                )
                
                try:
                    notion_service = NotionService()
                    await notion_service.sync_export_session(export_session)
                except Exception as e:
                    logger.warning(f"Notion sync failed: {e}")
                    # No fallar el export por errores de Notion
            
            # Finalización
            export_session.status = "completed"
            export_session.completed_at = datetime.utcnow()
            export_session.progress_percentage = 100.0
            export_session.processing_time_seconds = time.time() - start_time
            
            # Calcular score de calidad
            quality_factors = []
            if contenido.total_elementos > 0:
                quality_factors.append(0.9)  # Base quality
            if output_file and os.path.exists(output_file):
                quality_factors.append(0.95)  # File generated successfully
            if tts_result and tts_result.status == "completed":
                quality_factors.append(0.9)  # TTS successful
            
            export_session.quality_score = sum(quality_factors) / len(quality_factors) if quality_factors else 0.7
            
            await db.commit()
            
            logger.info(f"Export processing completed successfully: {export_session_id}")
            
            return {
                "status": "completed",
                "export_session_id": export_session_id,
                "output_file": output_file,
                "tts_result_id": str(tts_result.id) if tts_result else None,
                "elements_exported": contenido.total_elementos,
                "processing_time": time.time() - start_time,
                "quality_score": export_session.quality_score
            }
    
    except Exception as e:
        logger.error(f"Export processing failed for session {export_session_id}: {e}")
        
        # Actualizar estado de error
        try:
            async with get_async_db() as db:
                export_session = await db.get(ExportSession, UUID(export_session_id))
                if export_session:
                    export_session.status = "failed"
                    export_session.error_message = str(e)
                    export_session.processing_time_seconds = time.time() - start_time
                    await db.commit()
        except Exception as update_error:
            logger.error(f"Failed to update error state: {update_error}")
        
        # Actualizar estado de la tarea
        current_task.update_state(
            state="FAILURE",
            meta={
                "stage": "error",
                "progress": 0,
                "message": f"Error en procesamiento: {str(e)}",
                "error": str(e),
                "completed_at": datetime.utcnow().isoformat()
            }
        )
        
        raise


@celery_app.task(bind=True, name="synthesize_collection_tts")
async def synthesize_collection_tts_task(
    self,
    collection_id: str,
    tts_config_dict: Optional[Dict[str, Any]] = None
):
    """
    Sintetiza TTS de una colección de micro-memos.
    
    Args:
        collection_id: ID de la colección
        tts_config_dict: Configuración TTS serializada
    """
    start_time = time.time()
    task_id = self.request.id
    
    logger.info(f"Starting TTS synthesis task {task_id} for collection {collection_id}")
    
    current_task.update_state(
        state="PROCESSING",
        meta={
            "stage": "initializing",
            "progress": 0,
            "message": "Iniciando síntesis TTS...",
            "started_at": datetime.utcnow().isoformat()
        }
    )
    
    try:
        async with get_async_db() as db:
            # Obtener colección
            collection = await db.get(MicroMemoCollection, UUID(collection_id))
            if not collection:
                raise ValueError(f"Collection not found: {collection_id}")
            
            # Configuración TTS
            config = ConfiguracionTTS(**(tts_config_dict or {}))
            
            # Fase 1: Validación y preparación (0-20%)
            current_task.update_state(
                state="PROCESSING",
                meta={
                    "stage": "preparation",
                    "progress": 10,
                    "message": "Preparando contenido para síntesis..."
                }
            )
            
            # Obtener micro-memos
            memos = db.query(MicroMemo).filter(
                MicroMemo.collection_id == collection.id
            ).all()
            
            if not memos:
                raise ValueError(f"No memos found in collection {collection_id}")
            
            # Fase 2: Síntesis TTS (20-90%)
            current_task.update_state(
                state="PROCESSING",
                meta={
                    "stage": "synthesis",
                    "progress": 20,
                    "message": f"Sintetizando audio para {len(memos)} micro-memos..."
                }
            )
            
            tts_result = await tts_service.synthesize_collection(collection, config, db)
            
            # Fase 3: Post-procesamiento (90-100%)
            current_task.update_state(
                state="PROCESSING",
                meta={
                    "stage": "finalization",
                    "progress": 90,
                    "message": "Finalizando síntesis TTS..."
                }
            )
            
            # Actualizar métricas finales
            tts_result.processing_time_seconds = time.time() - start_time
            await db.commit()
            
            logger.info(f"TTS synthesis completed: {tts_result.id}")
            
            return {
                "status": "completed",
                "tts_result_id": str(tts_result.id),
                "collection_id": collection_id,
                "memos_count": len(memos),
                "duration_seconds": tts_result.duration_seconds,
                "processing_time": time.time() - start_time,
                "audio_file": tts_result.audio_file_path
            }
    
    except Exception as e:
        logger.error(f"TTS synthesis failed for collection {collection_id}: {e}")
        
        current_task.update_state(
            state="FAILURE",
            meta={
                "stage": "error",
                "progress": 0,
                "message": f"Error en síntesis TTS: {str(e)}",
                "error": str(e),
                "completed_at": datetime.utcnow().isoformat()
            }
        )
        
        raise


@celery_app.task(bind=True, name="create_anki_package_with_tts")
async def create_anki_package_with_tts_task(
    self,
    export_session_id: str,
    include_individual_audio: bool = True
):
    """
    Crea un package Anki con audio TTS integrado.
    
    Args:
        export_session_id: ID de la sesión de export
        include_individual_audio: Si incluir audio individual por memo
    """
    start_time = time.time()
    task_id = self.request.id
    
    logger.info(f"Starting Anki package creation task {task_id} for export {export_session_id}")
    
    current_task.update_state(
        state="PROCESSING",
        meta={
            "stage": "initializing",
            "progress": 0,
            "message": "Creando package Anki con audio...",
            "started_at": datetime.utcnow().isoformat()
        }
    )
    
    try:
        async with get_async_db() as db:
            # Obtener sesión de export
            export_session = await db.get(ExportSession, UUID(export_session_id))
            if not export_session:
                raise ValueError(f"Export session not found: {export_session_id}")
            
            # Fase 1: Recopilar contenido (0-30%)
            current_task.update_state(
                state="PROCESSING",
                meta={
                    "stage": "gathering_content",
                    "progress": 10,
                    "message": "Recopilando micro-memos..."
                }
            )
            
            contenido = await export_service.gather_content_for_export(export_session, db)
            
            if not contenido.micro_memos:
                raise ValueError("No micro-memos found for Anki package")
            
            # Fase 2: Generar audio TTS individual si se solicita (30-70%)
            tts_results = []
            if include_individual_audio:
                current_task.update_state(
                    state="PROCESSING",
                    meta={
                        "stage": "generating_individual_tts",
                        "progress": 30,
                        "message": "Generando audio individual para cada memo..."
                    }
                )
                
                tts_config = ConfiguracionTTS(
                    study_mode="question_pause",
                    audio_quality="medium",
                    audio_format="mp3"
                )
                
                for i, memo_data in enumerate(contenido.micro_memos):
                    memo = await db.get(MicroMemo, UUID(memo_data["id"]))
                    if memo:
                        tts_result = await tts_service.synthesize_micro_memo(
                            memo, tts_config, db
                        )
                        tts_results.append(tts_result)
                    
                    # Actualizar progreso
                    progress = 30 + (40 * (i + 1) / len(contenido.micro_memos))
                    current_task.update_state(
                        state="PROCESSING",
                        meta={
                            "stage": "generating_individual_tts",
                            "progress": int(progress),
                            "message": f"Audio generado para memo {i+1}/{len(contenido.micro_memos)}"
                        }
                    )
            
            # Fase 3: Crear package Anki con media (70-90%)
            current_task.update_state(
                state="PROCESSING",
                meta={
                    "stage": "creating_anki_package",
                    "progress": 70,
                    "message": "Creando package Anki..."
                }
            )
            
            # Generar package Anki básico
            anki_file = await export_service.export_to_anki(export_session, contenido)
            
            # TODO: Integrar archivos de audio en el package
            # Esto requeriría modificar el método export_to_anki para incluir media
            
            # Fase 4: Finalización (90-100%)
            current_task.update_state(
                state="PROCESSING",
                meta={
                    "stage": "finalization",
                    "progress": 90,
                    "message": "Finalizando package Anki..."
                }
            )
            
            # Actualizar export session con información TTS
            if tts_results:
                export_session.include_tts = True
                export_session.tts_config = {
                    "individual_audio": include_individual_audio,
                    "tts_results_count": len(tts_results)
                }
                await db.commit()
            
            logger.info(f"Anki package with TTS created: {anki_file}")
            
            return {
                "status": "completed",
                "export_session_id": export_session_id,
                "anki_file": anki_file,
                "tts_results_count": len(tts_results),
                "processing_time": time.time() - start_time
            }
    
    except Exception as e:
        logger.error(f"Anki package creation failed: {e}")
        
        current_task.update_state(
            state="FAILURE",
            meta={
                "stage": "error",
                "progress": 0,
                "message": f"Error creando package Anki: {str(e)}",
                "error": str(e),
                "completed_at": datetime.utcnow().isoformat()
            }
        )
        
        raise


@celery_app.task(bind=True, name="batch_tts_synthesis")
async def batch_tts_synthesis_task(
    self,
    micro_memo_ids: List[str],
    batch_config_dict: Optional[Dict[str, Any]] = None
):
    """
    Síntesis TTS masiva de micro-memos con optimización.
    
    Args:
        micro_memo_ids: Lista de IDs de micro-memos
        batch_config_dict: Configuración para el batch
    """
    start_time = time.time()
    task_id = self.request.id
    
    logger.info(f"Starting batch TTS synthesis task {task_id} for {len(micro_memo_ids)} memos")
    
    current_task.update_state(
        state="PROCESSING",
        meta={
            "stage": "initializing",
            "progress": 0,
            "message": f"Iniciando síntesis masiva de {len(micro_memo_ids)} memos...",
            "started_at": datetime.utcnow().isoformat()
        }
    )
    
    try:
        batch_config = batch_config_dict or {}
        config = ConfiguracionTTS(
            batch_size=batch_config.get("batch_size", 5),
            parallel_processing=batch_config.get("parallel_processing", False),
            **{k: v for k, v in batch_config.items() if k not in ["batch_size", "parallel_processing"]}
        )
        
        tts_results = []
        failed_memos = []
        
        async with get_async_db() as db:
            # Procesar en batches
            batch_size = config.batch_size
            total_batches = len(micro_memo_ids) // batch_size + (1 if len(micro_memo_ids) % batch_size else 0)
            
            for batch_idx in range(total_batches):
                start_idx = batch_idx * batch_size
                end_idx = min(start_idx + batch_size, len(micro_memo_ids))
                batch_ids = micro_memo_ids[start_idx:end_idx]
                
                current_task.update_state(
                    state="PROCESSING",
                    meta={
                        "stage": "batch_synthesis",
                        "progress": int((batch_idx / total_batches) * 90),
                        "message": f"Procesando batch {batch_idx + 1}/{total_batches}..."
                    }
                )
                
                # Procesar batch actual
                for memo_id in batch_ids:
                    try:
                        memo = await db.get(MicroMemo, UUID(memo_id))
                        if memo:
                            tts_result = await tts_service.synthesize_micro_memo(
                                memo, config, db
                            )
                            tts_results.append(tts_result)
                        else:
                            failed_memos.append({"id": memo_id, "reason": "Memo not found"})
                    
                    except Exception as e:
                        logger.error(f"Failed to synthesize memo {memo_id}: {e}")
                        failed_memos.append({"id": memo_id, "reason": str(e)})
                
                # Pequeña pausa entre batches para no sobrecargar
                await asyncio.sleep(0.5)
            
            logger.info(f"Batch TTS synthesis completed: {len(tts_results)} successful, {len(failed_memos)} failed")
            
            return {
                "status": "completed",
                "successful_count": len(tts_results),
                "failed_count": len(failed_memos),
                "tts_result_ids": [str(r.id) for r in tts_results],
                "failed_memos": failed_memos,
                "processing_time": time.time() - start_time
            }
    
    except Exception as e:
        logger.error(f"Batch TTS synthesis failed: {e}")
        
        current_task.update_state(
            state="FAILURE",
            meta={
                "stage": "error",
                "progress": 0,
                "message": f"Error en síntesis masiva: {str(e)}",
                "error": str(e),
                "completed_at": datetime.utcnow().isoformat()
            }
        )
        
        raise


@celery_app.task(bind=True, name="cleanup_expired_exports")
async def cleanup_expired_exports_task(self, days_old: int = 30):
    """
    Limpia exports expirados y archivos asociados.
    
    Args:
        days_old: Días de antigüedad para considerar expirado
    """
    start_time = time.time()
    task_id = self.request.id
    
    logger.info(f"Starting export cleanup task {task_id} for exports older than {days_old} days")
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        async with get_async_db() as db:
            # Buscar exports expirados
            expired_exports = db.query(ExportSession).filter(
                or_(
                    ExportSession.expires_at < datetime.utcnow(),
                    and_(
                        ExportSession.created_at < cutoff_date,
                        ExportSession.status.in_(["completed", "failed"])
                    )
                )
            ).all()
            
            cleaned_count = 0
            for export_session in expired_exports:
                try:
                    # Eliminar archivos del sistema de archivos
                    if export_session.output_files:
                        for file_info in export_session.output_files:
                            file_path = Path(file_info.get("path", ""))
                            if file_path.exists():
                                file_path.unlink()
                    
                    # Eliminar archivos TTS asociados
                    tts_results = db.query(TTSResult).filter(
                        TTSResult.export_session_id == export_session.id
                    ).all()
                    
                    for tts_result in tts_results:
                        if tts_result.audio_file_path:
                            audio_path = Path(tts_result.audio_file_path)
                            if audio_path.exists():
                                audio_path.unlink()
                    
                    # Marcar como expirado en lugar de eliminar
                    export_session.status = "expired"
                    cleaned_count += 1
                
                except Exception as e:
                    logger.error(f"Failed to cleanup export {export_session.id}: {e}")
            
            await db.commit()
            
            logger.info(f"Export cleanup completed: {cleaned_count} exports cleaned")
            
            return {
                "status": "completed",
                "cleaned_count": cleaned_count,
                "cutoff_date": cutoff_date.isoformat(),
                "processing_time": time.time() - start_time
            }
    
    except Exception as e:
        logger.error(f"Export cleanup failed: {e}")
        raise
