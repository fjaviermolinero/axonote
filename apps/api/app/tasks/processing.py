"""
Tareas de procesamiento de audio y transcripción con IA.
Pipeline completo: Normalización → ASR → Diarización → Fusión → Post-procesamiento.
"""

import asyncio
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import current_task
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import api_logger, get_async_db
from app.models import ProcessingJob, TranscriptionResult, DiarizationResult
from app.models.processing_job import EstadoProcesamiento, EtapaProcesamiento
from app.services.whisper_service import whisper_service
from app.services.diarization_service import diarization_service
from app.services.minio_service import minio_service
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, name="process_audio_complete")
def process_audio_complete_task(self, processing_job_id: str) -> Dict[str, Any]:
    """
    Tarea principal de procesamiento completo de audio.
    Coordina todo el pipeline: ASR + Diarización + Fusión + Post-procesamiento.
    """
    job_uuid = UUID(processing_job_id)
    
    try:
        api_logger.info(
            "Iniciando procesamiento completo de audio",
            processing_job_id=processing_job_id,
            task_id=current_task.request.id
        )
        
        # Ejecutar pipeline asíncrono
        resultado = asyncio.run(_execute_complete_pipeline(job_uuid))
        
        api_logger.info(
            "Procesamiento completo finalizado",
            processing_job_id=processing_job_id,
            task_id=current_task.request.id,
            estado_final=resultado.get("estado"),
            tiempo_total=resultado.get("tiempo_total_sec")
        )
        
        return resultado
        
    except Exception as e:
        api_logger.error(
            "Error en procesamiento completo",
            processing_job_id=processing_job_id,
            task_id=current_task.request.id,
            error=str(e)
        )
        
        # Actualizar estado de error
        asyncio.run(_update_job_error(job_uuid, str(e)))
        
        # Retry con backoff exponencial
        self.retry(countdown=60 * (2 ** self.request.retries), max_retries=3)


@celery_app.task(bind=True, name="transcribe_audio")
def transcribe_audio_task(self, processing_job_id: str) -> Dict[str, Any]:
    """
    Tarea específica de transcripción con Whisper.
    Ejecuta solo ASR sin diarización.
    """
    job_uuid = UUID(processing_job_id)
    
    try:
        api_logger.info(
            "Iniciando transcripción ASR",
            processing_job_id=processing_job_id,
            task_id=current_task.request.id
        )
        
        resultado = asyncio.run(_execute_asr_pipeline(job_uuid))
        
        api_logger.info(
            "Transcripción ASR completada",
            processing_job_id=processing_job_id,
            resultado=resultado
        )
        
        return resultado
        
    except Exception as e:
        api_logger.error(
            "Error en transcripción ASR",
            processing_job_id=processing_job_id,
            error=str(e)
        )
        
        asyncio.run(_update_job_error(job_uuid, str(e)))
        self.retry(countdown=60 * (2 ** self.request.retries), max_retries=3)


@celery_app.task(bind=True, name="diarize_audio")
def diarize_audio_task(self, processing_job_id: str) -> Dict[str, Any]:
    """
    Tarea específica de diarización de speakers.
    Ejecuta solo diarización sin ASR.
    """
    job_uuid = UUID(processing_job_id)
    
    try:
        api_logger.info(
            "Iniciando diarización",
            processing_job_id=processing_job_id,
            task_id=current_task.request.id
        )
        
        resultado = asyncio.run(_execute_diarization_pipeline(job_uuid))
        
        api_logger.info(
            "Diarización completada",
            processing_job_id=processing_job_id,
            resultado=resultado
        )
        
        return resultado
        
    except Exception as e:
        api_logger.error(
            "Error en diarización",
            processing_job_id=processing_job_id,
            error=str(e)
        )
        
        asyncio.run(_update_job_error(job_uuid, str(e)))
        self.retry(countdown=60 * (2 ** self.request.retries), max_retries=3)


# ============================================================================
# FUNCIONES AUXILIARES ASÍNCRONAS
# ============================================================================

async def _execute_complete_pipeline(job_id: UUID) -> Dict[str, Any]:
    """Ejecutar pipeline completo de procesamiento."""
    inicio_tiempo = time.time()
    
    async for db in get_async_db():
        try:
            # Cargar job
            job = await _get_processing_job(db, job_id)
            if not job:
                raise ValueError(f"ProcessingJob {job_id} no encontrado")
            
            # Actualizar estado inicial
            await _update_job_state(
                db, job, 
                EstadoProcesamiento.PROCESANDO, 
                EtapaProcesamiento.VALIDACION,
                0.0
            )
            
            # 1. Validación y normalización de audio
            audio_normalizado = await _normalize_audio_pipeline(db, job)
            await _update_job_progress(db, job, EtapaProcesamiento.NORMALIZACION, 15.0)
            
            # 2. ASR con Whisper
            resultado_asr = await _execute_whisper_asr(db, job, audio_normalizado)
            await _update_job_progress(db, job, EtapaProcesamiento.ASR, 50.0)
            
            # 3. Diarización con pyannote
            resultado_diarizacion = await _execute_pyannote_diarization(db, job, audio_normalizado)
            await _update_job_progress(db, job, EtapaProcesamiento.DIARIZACION, 80.0)
            
            # 4. Fusión de resultados
            resultado_fusion = await _fuse_asr_diarization(db, job, resultado_asr, resultado_diarizacion)
            await _update_job_progress(db, job, EtapaProcesamiento.FUSION, 90.0)
            
            # 5. Post-procesamiento y finalización
            resultado_final = await _post_process_results(db, job, resultado_fusion)
            await _update_job_progress(db, job, EtapaProcesamiento.FINALIZACION, 100.0)
            
            # Finalizar job
            tiempo_total = time.time() - inicio_tiempo
            await _finalize_job(db, job, tiempo_total, resultado_final)
            
            return {
                "estado": "completado",
                "processing_job_id": str(job_id),
                "tiempo_total_sec": tiempo_total,
                "transcripcion_id": str(resultado_asr.id) if resultado_asr else None,
                "diarizacion_id": str(resultado_diarizacion.id) if resultado_diarizacion else None,
                "resultado_fusion": resultado_fusion
            }
            
        except Exception as e:
            await _update_job_error(job_id, str(e))
            raise
        finally:
            await db.close()


async def _execute_asr_pipeline(job_id: UUID) -> Dict[str, Any]:
    """Ejecutar solo pipeline de ASR."""
    async for db in get_async_db():
        try:
            job = await _get_processing_job(db, job_id)
            if not job:
                raise ValueError(f"ProcessingJob {job_id} no encontrado")
            
            await _update_job_state(db, job, EstadoProcesamiento.PROCESANDO, EtapaProcesamiento.ASR, 0.0)
            
            # Normalizar audio
            audio_normalizado = await _normalize_audio_pipeline(db, job)
            await _update_job_progress(db, job, EtapaProcesamiento.ASR, 20.0)
            
            # ASR
            resultado_asr = await _execute_whisper_asr(db, job, audio_normalizado)
            await _update_job_progress(db, job, EtapaProcesamiento.FINALIZACION, 100.0)
            
            await _finalize_job(db, job, 0, {"asr_only": True})
            
            return {
                "estado": "completado",
                "processing_job_id": str(job_id),
                "transcripcion_id": str(resultado_asr.id) if resultado_asr else None
            }
            
        finally:
            await db.close()


async def _execute_diarization_pipeline(job_id: UUID) -> Dict[str, Any]:
    """Ejecutar solo pipeline de diarización."""
    async for db in get_async_db():
        try:
            job = await _get_processing_job(db, job_id)
            if not job:
                raise ValueError(f"ProcessingJob {job_id} no encontrado")
            
            await _update_job_state(db, job, EstadoProcesamiento.PROCESANDO, EtapaProcesamiento.DIARIZACION, 0.0)
            
            # Normalizar audio
            audio_normalizado = await _normalize_audio_pipeline(db, job)
            await _update_job_progress(db, job, EtapaProcesamiento.DIARIZACION, 20.0)
            
            # Diarización
            resultado_diarizacion = await _execute_pyannote_diarization(db, job, audio_normalizado)
            await _update_job_progress(db, job, EtapaProcesamiento.FINALIZACION, 100.0)
            
            await _finalize_job(db, job, 0, {"diarization_only": True})
            
            return {
                "estado": "completado",
                "processing_job_id": str(job_id),
                "diarizacion_id": str(resultado_diarizacion.id) if resultado_diarizacion else None
            }
            
        finally:
            await db.close()


async def _normalize_audio_pipeline(db: AsyncSession, job: ProcessingJob) -> str:
    """Normalizar audio para procesamiento óptimo."""
    try:
        api_logger.info("Iniciando normalización de audio", job_id=str(job.id))
        
        # TODO: Implementar normalización con ffmpeg
        # Por ahora, usar el audio original
        ruta_normalizada = job.ruta_audio_original
        
        # Actualizar job con ruta normalizada
        job.ruta_audio_normalizado = ruta_normalizada
        await db.commit()
        
        api_logger.info("Normalización completada", ruta_normalizada=ruta_normalizada)
        return ruta_normalizada
        
    except Exception as e:
        api_logger.error("Error en normalización", error=str(e))
        raise


async def _execute_whisper_asr(db: AsyncSession, job: ProcessingJob, ruta_audio: str) -> TranscriptionResult:
    """Ejecutar transcripción con Whisper."""
    try:
        api_logger.info("Iniciando ASR con Whisper", job_id=str(job.id))
        
        # TODO: Implementar callback de progreso real
        # Ejecutar transcripción
        configuracion = job.config_whisper.get("preset", "MEDICAL_HIGH_PRECISION")
        resultado_whisper = await whisper_service.transcribir_audio(
            ruta_audio=ruta_audio,
            configuracion=configuracion,
            idioma="it"
        )
        
        # Crear registro en base de datos
        transcription_result = TranscriptionResult(
            processing_job_id=job.id,
            texto_completo=resultado_whisper.texto_completo,
            texto_raw=resultado_whisper.texto_completo,
            idioma_detectado=resultado_whisper.idioma_detectado,
            confianza_global=resultado_whisper.confianza_global,
            segmentos=[s.dict() for s in resultado_whisper.segmentos],
            num_palabras=resultado_whisper.num_palabras,
            num_segmentos=len(resultado_whisper.segmentos),
            duracion_audio_sec=resultado_whisper.duracion_audio_sec,
            palabras_por_minuto=resultado_whisper.palabras_por_minuto,
            modelo_whisper_usado=resultado_whisper.modelo_usado,
            compute_type_usado="float16",
            configuracion_whisper=resultado_whisper.configuracion_usada,
            vad_aplicado=True,
            alineacion_temporal_aplicada=True,
            tiempo_procesamiento_sec=resultado_whisper.tiempo_procesamiento_sec
        )
        
        db.add(transcription_result)
        await db.commit()
        await db.refresh(transcription_result)
        
        api_logger.info("ASR completado exitosamente", transcription_id=str(transcription_result.id))
        return transcription_result
        
    except Exception as e:
        api_logger.error("Error en ASR", error=str(e))
        raise


async def _execute_pyannote_diarization(db: AsyncSession, job: ProcessingJob, ruta_audio: str) -> DiarizationResult:
    """Ejecutar diarización con pyannote."""
    try:
        api_logger.info("Iniciando diarización con pyannote", job_id=str(job.id))
        
        # Ejecutar diarización
        configuracion = job.config_diarizacion.get("preset", "MEDICAL_CLASS_STANDARD")
        resultado_diarizacion = await diarization_service.diarizar_audio(
            ruta_audio=ruta_audio,
            configuracion=configuracion
        )
        
        # Crear registro en base de datos
        diarization_result = DiarizationResult(
            processing_job_id=job.id,
            num_speakers_detectados=resultado_diarizacion.num_speakers_detectados,
            speakers_clasificados=[s.dict() for s in resultado_diarizacion.speakers_info],
            segmentos_diarizacion=[s.dict() for s in resultado_diarizacion.segmentos_diarizacion],
            embeddings_speakers=resultado_diarizacion.embeddings_speakers,
            speaker_profesor=next(
                (s.speaker_id for s in resultado_diarizacion.speakers_info if s.tipo_speaker == "profesor"), 
                None
            ),
            speakers_alumnos=[
                s.speaker_id for s in resultado_diarizacion.speakers_info 
                if s.tipo_speaker.startswith("alumno")
            ],
            calidad_separacion=resultado_diarizacion.calidad_separacion,
            modelo_diarizacion_usado="pyannote/speaker-diarization-3.1",
            configuracion_diarizacion=resultado_diarizacion.configuracion_usada,
            tiempo_procesamiento_sec=resultado_diarizacion.tiempo_procesamiento_sec
        )
        
        db.add(diarization_result)
        await db.commit()
        await db.refresh(diarization_result)
        
        api_logger.info("Diarización completada exitosamente", diarization_id=str(diarization_result.id))
        return diarization_result
        
    except Exception as e:
        api_logger.error("Error en diarización", error=str(e))
        raise


async def _fuse_asr_diarization(
    db: AsyncSession, 
    job: ProcessingJob, 
    asr_result: TranscriptionResult, 
    diarization_result: DiarizationResult
) -> Dict[str, Any]:
    """Fusionar resultados de ASR y diarización."""
    try:
        api_logger.info("Iniciando fusión ASR + Diarización", job_id=str(job.id))
        
        fusion_resultado = {
            "transcripcion_id": str(asr_result.id),
            "diarizacion_id": str(diarization_result.id),
            "texto_completo": asr_result.texto_completo,
            "speakers_detectados": diarization_result.num_speakers_detectados,
            "speaker_profesor": diarization_result.speaker_profesor,
            "calidad_fusion": (asr_result.confianza_global + diarization_result.calidad_separacion) / 2
        }
        
        # Actualizar job con resultado de fusión
        job.resultado_fusion = fusion_resultado
        await db.commit()
        
        api_logger.info("Fusión completada")
        return fusion_resultado
        
    except Exception as e:
        api_logger.error("Error en fusión", error=str(e))
        raise


async def _post_process_results(db: AsyncSession, job: ProcessingJob, fusion_result: Dict[str, Any]) -> Dict[str, Any]:
    """Post-procesamiento final de resultados."""
    try:
        api_logger.info("Iniciando post-procesamiento", job_id=str(job.id))
        
        resultado_final = fusion_result.copy()
        resultado_final.update({
            "post_procesado": True,
            "terminologia_medica_extraida": [],
            "estructura_clase_detectada": "lecture"
        })
        
        # Actualizar métricas de calidad
        metricas_calidad = {
            "confianza_global": fusion_result.get("calidad_fusion", 0.8),
            "procesamiento_exitoso": True
        }
        
        job.metricas_calidad = metricas_calidad
        job.confianza_global = fusion_result.get("calidad_fusion", 0.8)
        await db.commit()
        
        api_logger.info("Post-procesamiento completado")
        return resultado_final
        
    except Exception as e:
        api_logger.error("Error en post-procesamiento", error=str(e))
        raise


# ============================================================================
# FUNCIONES DE UTILIDAD
# ============================================================================

async def _get_processing_job(db: AsyncSession, job_id: UUID) -> Optional[ProcessingJob]:
    """Obtener ProcessingJob por ID."""
    result = await db.get(ProcessingJob, job_id)
    return result


async def _update_job_state(
    db: AsyncSession, 
    job: ProcessingJob, 
    estado: EstadoProcesamiento, 
    etapa: EtapaProcesamiento, 
    progreso: float
) -> None:
    """Actualizar estado del job."""
    job.estado = estado
    job.etapa_actual = etapa
    job.progreso_porcentaje = progreso
    job.updated_at = datetime.utcnow()
    
    if estado == EstadoProcesamiento.PROCESANDO and not job.tiempo_inicio:
        job.tiempo_inicio = datetime.utcnow()
    
    await db.commit()


async def _update_job_progress(
    db: AsyncSession, 
    job: ProcessingJob, 
    etapa: EtapaProcesamiento, 
    progreso: float
) -> None:
    """Actualizar progreso del job."""
    job.etapa_actual = etapa
    job.progreso_porcentaje = progreso
    job.updated_at = datetime.utcnow()
    await db.commit()


async def _update_job_error(job_id: UUID, error_message: str) -> None:
    """Actualizar job con error."""
    async for db in get_async_db():
        try:
            job = await _get_processing_job(db, job_id)
            if job:
                job.estado = EstadoProcesamiento.ERROR
                job.error_actual = error_message
                job.reintentos += 1
                job.updated_at = datetime.utcnow()
                await db.commit()
        finally:
            await db.close()


async def _finalize_job(db: AsyncSession, job: ProcessingJob, tiempo_total: float, resultado: Dict[str, Any]) -> None:
    """Finalizar job exitosamente."""
    job.estado = EstadoProcesamiento.COMPLETADO
    job.progreso_porcentaje = 100.0
    job.tiempo_fin = datetime.utcnow()
    job.tiempo_procesamiento_total_sec = tiempo_total
    job.updated_at = datetime.utcnow()
    
    await db.commit()
    
    api_logger.info("ProcessingJob finalizado exitosamente", job_id=str(job.id))
