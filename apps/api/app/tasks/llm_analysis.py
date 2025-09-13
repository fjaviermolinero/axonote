"""
Tareas Celery para análisis LLM y post-procesamiento de transcripciones médicas.
Pipeline completo desde corrección ASR hasta análisis estructural.
"""

import time
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from celery import current_task
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import (
    ProcessingJob, TranscriptionResult, DiarizationResult,
    LLMAnalysisResult, PostProcessingResult, MedicalTerminology
)
from app.services import LLMService, PostProcessingService
from app.workers.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


def update_processing_progress(job_id: str, progress: float, message: str) -> None:
    """Actualizar progreso del procesamiento."""
    try:
        db: Session = next(get_db())
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if job:
            job.progreso_porcentaje = progress
            job.error_actual = None if progress >= 0 else message
            db.commit()
        
        # Actualizar estado de tarea Celery
        if current_task:
            current_task.update_state(
                state='PROGRESS',
                meta={'progress': progress, 'message': message}
            )
    except Exception as e:
        logger.error(f"Error actualizando progreso: {e}")


@celery_app.task(bind=True, name="llm_analysis.full_post_processing_pipeline")
def full_post_processing_pipeline(
    self,
    processing_job_id: str,
    transcription_result_id: str,
    diarization_result_id: Optional[str] = None,
    config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Pipeline completo de post-procesamiento LLM.
    
    Ejecuta todas las etapas: corrección ASR, NER médico, análisis de estructura,
    análisis LLM y métricas de calidad.
    
    Args:
        processing_job_id: ID del job de procesamiento
        transcription_result_id: ID del resultado de transcripción
        diarization_result_id: ID del resultado de diarización (opcional)
        config: Configuración del pipeline
        
    Returns:
        Resultado completo del post-procesamiento
    """
    start_time = time.time()
    config = config or {}
    
    try:
        logger.info(f"Iniciando post-procesamiento completo para job {processing_job_id}")
        update_processing_progress(processing_job_id, 60, "Iniciando post-procesamiento LLM")
        
        # Obtener datos de entrada
        db: Session = next(get_db())
        
        transcription = db.query(TranscriptionResult).filter(
            TranscriptionResult.id == transcription_result_id
        ).first()
        
        if not transcription:
            raise ValueError(f"Transcripción no encontrada: {transcription_result_id}")
        
        diarization = None
        if diarization_result_id:
            diarization = db.query(DiarizationResult).filter(
                DiarizationResult.id == diarization_result_id
            ).first()
        
        # 1. Corrección ASR (60-70%)
        logger.info("Ejecutando corrección ASR")
        correction_result = asr_correction_task.apply_async(
            args=[transcription.texto_completo, config.get("correction_config", {})],
            queue="post_processing"
        ).get()
        update_processing_progress(processing_job_id, 70, "Corrección ASR completada")
        
        # 2. NER Médico (70-75%)
        logger.info("Ejecutando NER médico")
        ner_result = medical_ner_task.apply_async(
            args=[correction_result["corrected_text"], config.get("ner_config", {})],
            queue="post_processing"
        ).get()
        update_processing_progress(processing_job_id, 75, "Extracción de terminología completada")
        
        # 3. Análisis de estructura (75-80%)
        logger.info("Ejecutando análisis de estructura")
        diarization_data = diarization.resultado_completo if diarization else {}
        structure_result = structure_analysis_task.apply_async(
            args=[correction_result["corrected_text"], diarization_data, config.get("structure_config", {})],
            queue="post_processing"
        ).get()
        update_processing_progress(processing_job_id, 80, "Análisis de estructura completado")
        
        # 4. Análisis LLM (80-90%)
        logger.info("Ejecutando análisis LLM")
        llm_result = llm_analysis_task.apply_async(
            args=[
                correction_result["corrected_text"],
                diarization_data,
                config.get("llm_config", {})
            ],
            queue="llm_analysis"
        ).get()
        update_processing_progress(processing_job_id, 90, "Análisis LLM completado")
        
        # 5. Guardar resultados en base de datos (90-95%)
        logger.info("Guardando resultados en base de datos")
        
        # Guardar resultado de post-procesamiento
        post_processing_result = PostProcessingResult(
            processing_job_id=UUID(processing_job_id),
            transcription_result_id=UUID(transcription_result_id),
            texto_original=transcription.texto_completo,
            texto_corregido=correction_result["corrected_text"],
            correcciones_aplicadas=correction_result["corrections"],
            confianza_correccion=correction_result["confidence_avg"],
            entidades_medicas=ner_result["entities"],
            terminologia_detectada=ner_result["detected_terms"],
            glosario_clase=ner_result["glossary"],
            precision_ner=ner_result["precision_estimate"],
            segmentos_identificados=structure_result["segments"],
            participacion_speakers=structure_result["participation"],
            momentos_clave=structure_result["key_moments"],
            flujo_clase=structure_result["class_flow"],
            mejora_legibilidad=correction_result["improvement_score"],
            precision_terminologia=ner_result["precision_estimate"],
            cobertura_conceptos=len(ner_result["detected_terms"]) / max(len(transcription.texto_completo.split()), 1),
            num_correcciones=correction_result["num_corrections"],
            num_entidades=ner_result["total_entities"],
            tiempo_procesamiento=time.time() - start_time,
            config_correccion=config.get("correction_config", {}),
            config_ner=config.get("ner_config", {})
        )
        
        db.add(post_processing_result)
        db.flush()
        
        # Guardar resultado de análisis LLM
        llm_analysis_result = LLMAnalysisResult(
            processing_job_id=UUID(processing_job_id),
            transcription_result_id=UUID(transcription_result_id),
            llm_provider=llm_result["provider"],
            model_name=llm_result["model_name"],
            analysis_preset=llm_result["preset"],
            resumen_principal=llm_result["resumen_principal"],
            conceptos_clave=llm_result["conceptos_clave"],
            estructura_clase=llm_result["estructura_clase"],
            terminologia_medica=llm_result["terminologia_medica"],
            momentos_clave=llm_result["momentos_clave"],
            confianza_llm=llm_result["confianza_analisis"],
            coherencia_score=llm_result["coherencia_score"],
            completitud_score=llm_result["completitud_score"],
            relevancia_medica=llm_result.get("relevancia_medica", 0.8),
            needs_review=llm_result["needs_review"],
            tiempo_procesamiento=llm_result["processing_time"],
            tokens_utilizados=llm_result["tokens_used"],
            costo_estimado=llm_result["cost_eur"],
            llm_config=config.get("llm_config", {})
        )
        
        db.add(llm_analysis_result)
        db.commit()
        
        update_processing_progress(processing_job_id, 95, "Resultados guardados en base de datos")
        
        # 6. Métricas de calidad final (95-100%)
        logger.info("Calculando métricas de calidad")
        quality_metrics = calculate_quality_metrics(
            correction_result, ner_result, structure_result, llm_result
        )
        
        # Actualizar job como completado
        job = db.query(ProcessingJob).filter(ProcessingJob.id == processing_job_id).first()
        if job:
            job.estado = "post_processing_completed"
            job.progreso_porcentaje = 100.0
            job.tiempo_fin = time.time()
            job.metricas_calidad = quality_metrics
            db.commit()
        
        update_processing_progress(processing_job_id, 100, "Post-procesamiento completado exitosamente")
        
        total_time = time.time() - start_time
        logger.info(f"Post-procesamiento completado en {total_time:.2f}s para job {processing_job_id}")
        
        return {
            "success": True,
            "processing_job_id": processing_job_id,
            "post_processing_result_id": str(post_processing_result.id),
            "llm_analysis_result_id": str(llm_analysis_result.id),
            "correction_result": correction_result,
            "ner_result": ner_result,
            "structure_result": structure_result,
            "llm_result": llm_result,
            "quality_metrics": quality_metrics,
            "total_processing_time": total_time
        }
        
    except Exception as e:
        logger.error(f"Error en pipeline post-procesamiento: {e}")
        update_processing_progress(processing_job_id, -1, f"Error: {str(e)}")
        
        # Actualizar job con error
        try:
            db: Session = next(get_db())
            job = db.query(ProcessingJob).filter(ProcessingJob.id == processing_job_id).first()
            if job:
                job.estado = "error"
                job.error_actual = str(e)
                db.commit()
        except Exception as db_error:
            logger.error(f"Error actualizando job con error: {db_error}")
        
        return {
            "success": False,
            "error": str(e),
            "processing_job_id": processing_job_id,
            "total_processing_time": time.time() - start_time
        }


@celery_app.task(bind=True, name="llm_analysis.asr_correction")
async def asr_correction_task(
    self,
    transcription_text: str,
    config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Tarea de corrección ASR para terminología médica italiana.
    
    Args:
        transcription_text: Texto de la transcripción a corregir
        config: Configuración de corrección
        
    Returns:
        Resultado de corrección con texto mejorado
    """
    try:
        logger.info("Iniciando corrección ASR")
        
        post_processing_service = PostProcessingService()
        await post_processing_service._setup()
        
        config = config or {}
        confidence_threshold = config.get("confidence_threshold", 0.8)
        
        result = await post_processing_service.correct_asr_errors(
            transcription_text,
            confidence_threshold
        )
        
        logger.info(f"Corrección ASR completada: {result['num_corrections']} correcciones aplicadas")
        return result
        
    except Exception as e:
        logger.error(f"Error en corrección ASR: {e}")
        return {
            "success": False,
            "error": str(e),
            "original_text": transcription_text,
            "corrected_text": transcription_text,
            "corrections": []
        }


@celery_app.task(bind=True, name="llm_analysis.medical_ner")
async def medical_ner_task(
    self,
    text: str,
    config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Tarea de NER médico para extracción de terminología.
    
    Args:
        text: Texto para análisis NER
        config: Configuración de NER
        
    Returns:
        Entidades médicas extraídas
    """
    try:
        logger.info("Iniciando NER médico")
        
        post_processing_service = PostProcessingService()
        await post_processing_service._setup()
        
        config = config or {}
        include_definitions = config.get("include_definitions", True)
        
        result = await post_processing_service.extract_medical_entities(
            text,
            include_definitions
        )
        
        logger.info(f"NER médico completado: {result['total_entities']} entidades detectadas")
        return result
        
    except Exception as e:
        logger.error(f"Error en NER médico: {e}")
        return {
            "success": False,
            "error": str(e),
            "entities": {},
            "detected_terms": [],
            "total_entities": 0
        }


@celery_app.task(bind=True, name="llm_analysis.structure_analysis")
async def structure_analysis_task(
    self,
    transcription_text: str,
    diarization_data: Dict,
    config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Tarea de análisis de estructura pedagógica.
    
    Args:
        transcription_text: Texto de la transcripción
        diarization_data: Datos de diarización
        config: Configuración de análisis
        
    Returns:
        Análisis de estructura de la clase
    """
    try:
        logger.info("Iniciando análisis de estructura")
        
        post_processing_service = PostProcessingService()
        await post_processing_service._setup()
        
        result = await post_processing_service.analyze_class_structure(
            transcription_text,
            diarization_data
        )
        
        logger.info(f"Análisis de estructura completado: {result['total_segments']} segmentos analizados")
        return result
        
    except Exception as e:
        logger.error(f"Error en análisis de estructura: {e}")
        return {
            "success": False,
            "error": str(e),
            "segments": [],
            "activities": [],
            "participation": {},
            "key_moments": []
        }


@celery_app.task(bind=True, name="llm_analysis.llm_analysis")
async def llm_analysis_task(
    self,
    transcription_text: str,
    diarization_data: Dict,
    config: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Tarea de análisis LLM completo.
    
    Args:
        transcription_text: Texto de la transcripción
        diarization_data: Datos de diarización
        config: Configuración de análisis LLM
        
    Returns:
        Resultado completo del análisis LLM
    """
    try:
        logger.info("Iniciando análisis LLM")
        
        llm_service = LLMService()
        await llm_service._setup()
        
        config = config or {}
        preset = config.get("preset", "MEDICAL_COMPREHENSIVE")
        
        result = await llm_service.analyze_medical_transcription(
            transcription_text,
            diarization_data,
            preset
        )
        
        logger.info(f"Análisis LLM completado con {result['provider']} - {result['model_name']}")
        return result
        
    except Exception as e:
        logger.error(f"Error en análisis LLM: {e}")
        return {
            "success": False,
            "error": str(e),
            "provider": "error",
            "model_name": "error",
            "resumen_principal": "",
            "conceptos_clave": [],
            "needs_review": True
        }


def calculate_quality_metrics(
    correction_result: Dict,
    ner_result: Dict,
    structure_result: Dict,
    llm_result: Dict
) -> Dict[str, Any]:
    """Calcular métricas de calidad del post-procesamiento."""
    try:
        # Métricas de corrección ASR
        asr_quality = {
            "corrections_applied": correction_result.get("num_corrections", 0),
            "improvement_score": correction_result.get("improvement_score", 0.0),
            "confidence_avg": correction_result.get("confidence_avg", 0.0)
        }
        
        # Métricas de NER
        ner_quality = {
            "entities_detected": ner_result.get("total_entities", 0),
            "precision_estimate": ner_result.get("precision_estimate", 0.0),
            "categories_found": len(ner_result.get("entities_by_category", {}))
        }
        
        # Métricas de estructura
        structure_quality = {
            "segments_analyzed": structure_result.get("total_segments", 0),
            "key_moments_found": len(structure_result.get("key_moments", [])),
            "speakers_detected": structure_result.get("participation", {}).get("total_speakers", 0)
        }
        
        # Métricas de LLM
        llm_quality = {
            "confidence": llm_result.get("confianza_analisis", 0.0),
            "coherence": llm_result.get("coherencia_score", 0.0),
            "completeness": llm_result.get("completitud_score", 0.0),
            "quality_score": llm_result.get("quality_score", 0.0),
            "needs_review": llm_result.get("needs_review", True)
        }
        
        # Puntuación global
        global_score = (
            asr_quality["improvement_score"] * 0.2 +
            ner_quality["precision_estimate"] * 0.3 +
            llm_quality["quality_score"] * 0.5
        )
        
        return {
            "global_score": global_score,
            "asr_quality": asr_quality,
            "ner_quality": ner_quality,
            "structure_quality": structure_quality,
            "llm_quality": llm_quality,
            "ready_for_notion": global_score >= 0.7 and not llm_quality["needs_review"]
        }
        
    except Exception as e:
        logger.error(f"Error calculando métricas de calidad: {e}")
        return {
            "global_score": 0.0,
            "error": str(e),
            "ready_for_notion": False
        }
