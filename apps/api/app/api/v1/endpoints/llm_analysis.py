"""
Endpoints REST para análisis LLM y post-procesamiento de transcripciones médicas.
Incluye gestión completa del pipeline de análisis inteligente.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import (
    ProcessingJob, LLMAnalysisResult, PostProcessingResult, 
    MedicalTerminology, TranscriptionResult, DiarizationResult
)
from app.services import LLMService, PostProcessingService
from app.tasks.llm_analysis import full_post_processing_pipeline
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


# Schemas de request/response
class PostProcessingConfig(BaseModel):
    """Configuración para post-procesamiento."""
    
    # Configuración de corrección ASR
    asr_correction_enabled: bool = Field(True, description="Habilitar corrección ASR")
    confidence_threshold: float = Field(0.8, ge=0.0, le=1.0, description="Umbral de confianza para correcciones")
    
    # Configuración de NER médico
    ner_enabled: bool = Field(True, description="Habilitar NER médico")
    include_definitions: bool = Field(True, description="Incluir definiciones de términos")
    
    # Configuración de análisis de estructura
    structure_analysis_enabled: bool = Field(True, description="Habilitar análisis de estructura")
    
    # Configuración de LLM
    llm_preset: str = Field("MEDICAL_COMPREHENSIVE", description="Preset de análisis LLM")
    force_local_llm: bool = Field(False, description="Forzar uso de LLM local")
    
    # Configuración general
    priority: str = Field("normal", description="Prioridad del procesamiento")


class LLMAnalysisResponse(BaseModel):
    """Respuesta de análisis LLM."""
    
    id: UUID
    processing_job_id: UUID
    transcription_result_id: UUID
    llm_provider: str
    model_name: str
    analysis_preset: str
    resumen_principal: Optional[str]
    conceptos_clave: Optional[Dict]
    estructura_clase: Optional[Dict]
    terminologia_medica: Optional[Dict]
    momentos_clave: Optional[List[Dict]]
    confianza_llm: float
    coherencia_score: float
    completitud_score: float
    relevancia_medica: float
    needs_review: bool
    validated_by_human: bool
    tiempo_procesamiento: float
    tokens_utilizados: int
    costo_estimado: float
    created_at: str


class PostProcessingResponse(BaseModel):
    """Respuesta de post-procesamiento."""
    
    id: UUID
    processing_job_id: UUID
    transcription_result_id: UUID
    texto_original: str
    texto_corregido: str
    correcciones_aplicadas: Dict
    confianza_correccion: float
    entidades_medicas: Dict
    terminologia_detectada: List[str]
    glosario_clase: Dict
    precision_ner: float
    segmentos_identificados: Dict
    participacion_speakers: Dict
    momentos_clave: List[Dict]
    flujo_clase: Dict
    mejora_legibilidad: float
    precision_terminologia: float
    cobertura_conceptos: float
    num_correcciones: int
    num_entidades: int
    tiempo_procesamiento: float
    created_at: str


# Endpoints principales
@router.post("/start/{processing_job_id}")
async def start_post_processing(
    processing_job_id: UUID,
    config: Optional[PostProcessingConfig] = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Iniciar post-procesamiento completo de una transcripción.
    
    Ejecuta el pipeline completo: corrección ASR, NER médico, análisis de estructura
    y análisis LLM para generar contenido estructurado listo para Notion.
    """
    try:
        # Validar que existe el job y tiene transcripción completada
        job = db.query(ProcessingJob).filter(ProcessingJob.id == processing_job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job de procesamiento no encontrado")
        
        if job.estado not in ["completado", "transcription_completed"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Job debe estar completado para post-procesamiento. Estado actual: {job.estado}"
            )
        
        # Buscar resultado de transcripción
        transcription = db.query(TranscriptionResult).filter(
            TranscriptionResult.processing_job_id == processing_job_id
        ).first()
        
        if not transcription:
            raise HTTPException(
                status_code=404, 
                detail="No se encontró resultado de transcripción para este job"
            )
        
        # Buscar resultado de diarización (opcional)
        diarization = db.query(DiarizationResult).filter(
            DiarizationResult.processing_job_id == processing_job_id
        ).first()
        
        # Verificar si ya existe post-procesamiento
        existing_post_processing = db.query(PostProcessingResult).filter(
            PostProcessingResult.processing_job_id == processing_job_id
        ).first()
        
        if existing_post_processing:
            logger.warning(f"Post-procesamiento ya existe para job {processing_job_id}")
        
        # Preparar configuración
        config_dict = {}
        if config:
            config_dict = {
                "correction_config": {
                    "enabled": config.asr_correction_enabled,
                    "confidence_threshold": config.confidence_threshold
                },
                "ner_config": {
                    "enabled": config.ner_enabled,
                    "include_definitions": config.include_definitions
                },
                "structure_config": {
                    "enabled": config.structure_analysis_enabled
                },
                "llm_config": {
                    "preset": config.llm_preset,
                    "force_local": config.force_local_llm
                }
            }
        
        # Iniciar pipeline de post-procesamiento
        task = full_post_processing_pipeline.delay(
            str(processing_job_id),
            str(transcription.id),
            str(diarization.id) if diarization else None,
            config_dict
        )
        
        # Actualizar job
        job.estado = "post_processing"
        job.celery_task_id = task.id
        db.commit()
        
        logger.info(f"Post-procesamiento iniciado para job {processing_job_id}, task {task.id}")
        
        return {
            "success": True,
            "message": "Post-procesamiento iniciado exitosamente",
            "processing_job_id": str(processing_job_id),
            "task_id": task.id,
            "transcription_id": str(transcription.id),
            "diarization_id": str(diarization.id) if diarization else None,
            "config": config_dict
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error iniciando post-procesamiento: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/status/{processing_job_id}")
async def get_post_processing_status(
    processing_job_id: UUID,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Obtener estado del post-procesamiento."""
    try:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == processing_job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job no encontrado")
        
        # Verificar si existe resultado de post-procesamiento
        post_processing = db.query(PostProcessingResult).filter(
            PostProcessingResult.processing_job_id == processing_job_id
        ).first()
        
        llm_analysis = db.query(LLMAnalysisResult).filter(
            LLMAnalysisResult.processing_job_id == processing_job_id
        ).first()
        
        status_info = {
            "processing_job_id": str(processing_job_id),
            "estado": job.estado,
            "progreso_porcentaje": job.progreso_porcentaje,
            "etapa_actual": job.etapa_actual,
            "error_actual": job.error_actual,
            "celery_task_id": job.celery_task_id,
            "post_processing_completed": post_processing is not None,
            "llm_analysis_completed": llm_analysis is not None,
            "tiempo_inicio": job.tiempo_inicio.isoformat() if job.tiempo_inicio else None,
            "tiempo_fin": job.tiempo_fin.isoformat() if job.tiempo_fin else None
        }
        
        if post_processing:
            status_info["post_processing_id"] = str(post_processing.id)
            status_info["num_correcciones"] = post_processing.num_correcciones
            status_info["num_entidades"] = post_processing.num_entidades
            status_info["mejora_legibilidad"] = post_processing.mejora_legibilidad
        
        if llm_analysis:
            status_info["llm_analysis_id"] = str(llm_analysis.id)
            status_info["llm_provider"] = llm_analysis.llm_provider
            status_info["confianza_llm"] = llm_analysis.confianza_llm
            status_info["needs_review"] = llm_analysis.needs_review
            status_info["tokens_utilizados"] = llm_analysis.tokens_utilizados
            status_info["costo_estimado"] = llm_analysis.costo_estimado
        
        return {
            "success": True,
            "data": status_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo estado: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/results/llm/{llm_analysis_id}")
async def get_llm_analysis_result(
    llm_analysis_id: UUID,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Obtener resultado completo de análisis LLM."""
    try:
        result = db.query(LLMAnalysisResult).filter(
            LLMAnalysisResult.id == llm_analysis_id
        ).first()
        
        if not result:
            raise HTTPException(status_code=404, detail="Resultado de análisis LLM no encontrado")
        
        return {
            "success": True,
            "data": LLMAnalysisResponse(
                id=result.id,
                processing_job_id=result.processing_job_id,
                transcription_result_id=result.transcription_result_id,
                llm_provider=result.llm_provider,
                model_name=result.model_name,
                analysis_preset=result.analysis_preset,
                resumen_principal=result.resumen_principal,
                conceptos_clave=result.conceptos_clave,
                estructura_clase=result.estructura_clase,
                terminologia_medica=result.terminologia_medica,
                momentos_clave=result.momentos_clave,
                confianza_llm=result.confianza_llm,
                coherencia_score=result.coherencia_score,
                completitud_score=result.completitud_score,
                relevancia_medica=result.relevancia_medica,
                needs_review=result.needs_review,
                validated_by_human=result.validated_by_human,
                tiempo_procesamiento=result.tiempo_procesamiento,
                tokens_utilizados=result.tokens_utilizados,
                costo_estimado=result.costo_estimado,
                created_at=result.created_at.isoformat()
            )
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo resultado LLM: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/results/post-processing/{post_processing_id}")
async def get_post_processing_result(
    post_processing_id: UUID,
    include_full_text: bool = Query(False, description="Incluir texto completo"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Obtener resultado completo de post-procesamiento."""
    try:
        result = db.query(PostProcessingResult).filter(
            PostProcessingResult.id == post_processing_id
        ).first()
        
        if not result:
            raise HTTPException(status_code=404, detail="Resultado de post-procesamiento no encontrado")
        
        response_data = PostProcessingResponse(
            id=result.id,
            processing_job_id=result.processing_job_id,
            transcription_result_id=result.transcription_result_id,
            texto_original=result.texto_original if include_full_text else result.texto_original[:200] + "...",
            texto_corregido=result.texto_corregido if include_full_text else result.texto_corregido[:200] + "...",
            correcciones_aplicadas=result.correcciones_aplicadas,
            confianza_correccion=result.confianza_correccion,
            entidades_medicas=result.entidades_medicas,
            terminologia_detectada=result.terminologia_detectada,
            glosario_clase=result.glosario_clase,
            precision_ner=result.precision_ner,
            segmentos_identificados=result.segmentos_identificados,
            participacion_speakers=result.participacion_speakers,
            momentos_clave=result.momentos_clave,
            flujo_clase=result.flujo_clase,
            mejora_legibilidad=result.mejora_legibilidad,
            precision_terminologia=result.precision_terminologia,
            cobertura_conceptos=result.cobertura_conceptos,
            num_correcciones=result.num_correcciones,
            num_entidades=result.num_entidades,
            tiempo_procesamiento=result.tiempo_procesamiento,
            created_at=result.created_at.isoformat()
        )
        
        return {
            "success": True,
            "data": response_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo resultado post-procesamiento: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/results/by-job/{processing_job_id}")
async def get_results_by_job(
    processing_job_id: UUID,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Obtener todos los resultados de post-procesamiento para un job."""
    try:
        # Buscar resultados
        post_processing = db.query(PostProcessingResult).filter(
            PostProcessingResult.processing_job_id == processing_job_id
        ).first()
        
        llm_analysis = db.query(LLMAnalysisResult).filter(
            LLMAnalysisResult.processing_job_id == processing_job_id
        ).first()
        
        if not post_processing and not llm_analysis:
            raise HTTPException(
                status_code=404, 
                detail="No se encontraron resultados de post-procesamiento para este job"
            )
        
        results = {
            "processing_job_id": str(processing_job_id),
            "post_processing": None,
            "llm_analysis": None
        }
        
        if post_processing:
            results["post_processing"] = {
                "id": str(post_processing.id),
                "num_correcciones": post_processing.num_correcciones,
                "num_entidades": post_processing.num_entidades,
                "mejora_legibilidad": post_processing.mejora_legibilidad,
                "precision_terminologia": post_processing.precision_terminologia,
                "cobertura_conceptos": post_processing.cobertura_conceptos,
                "tiempo_procesamiento": post_processing.tiempo_procesamiento,
                "created_at": post_processing.created_at.isoformat()
            }
        
        if llm_analysis:
            results["llm_analysis"] = {
                "id": str(llm_analysis.id),
                "llm_provider": llm_analysis.llm_provider,
                "model_name": llm_analysis.model_name,
                "confianza_llm": llm_analysis.confianza_llm,
                "coherencia_score": llm_analysis.coherencia_score,
                "completitud_score": llm_analysis.completitud_score,
                "needs_review": llm_analysis.needs_review,
                "tokens_utilizados": llm_analysis.tokens_utilizados,
                "costo_estimado": llm_analysis.costo_estimado,
                "tiempo_procesamiento": llm_analysis.tiempo_procesamiento,
                "created_at": llm_analysis.created_at.isoformat()
            }
        
        return {
            "success": True,
            "data": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo resultados por job: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/health")
async def llm_health_check() -> Dict[str, Any]:
    """Health check de servicios LLM y post-procesamiento."""
    try:
        # Verificar LLM Service
        llm_service = LLMService()
        await llm_service._setup()
        llm_health = await llm_service.health_check()
        
        # Verificar Post Processing Service
        post_processing_service = PostProcessingService()
        await post_processing_service._setup()
        
        post_processing_health = {
            "medical_dict_loaded": len(post_processing_service.medical_dict) > 0,
            "aho_corasick_ready": post_processing_service.aho_corasick is not None,
            "correction_patterns_loaded": len(post_processing_service.correction_patterns) > 0,
            "is_initialized": post_processing_service.is_initialized
        }
        
        overall_status = "healthy" if (
            llm_health["status"] == "healthy" and 
            post_processing_health["is_initialized"]
        ) else "degraded"
        
        return {
            "success": True,
            "data": {
                "overall_status": overall_status,
                "llm_service": llm_health,
                "post_processing_service": post_processing_health,
                "timestamp": "2024-01-01T00:00:00Z"  # Se actualizará automáticamente
            }
        }
        
    except Exception as e:
        logger.error(f"Error en health check: {e}")
        return {
            "success": False,
            "error": str(e),
            "data": {
                "overall_status": "error",
                "timestamp": "2024-01-01T00:00:00Z"
            }
        }


@router.get("/terminology/search")
async def search_medical_terminology(
    query: str = Query(..., min_length=2, description="Término a buscar"),
    category: Optional[str] = Query(None, description="Filtrar por categoría médica"),
    limit: int = Query(20, ge=1, le=100, description="Límite de resultados"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Buscar terminología médica en el diccionario."""
    try:
        # Construir query base
        query_db = db.query(MedicalTerminology).filter(
            MedicalTerminology.activo == True
        )
        
        # Filtrar por término (búsqueda parcial)
        query_db = query_db.filter(
            MedicalTerminology.termino_original.ilike(f"%{query}%") |
            MedicalTerminology.termino_normalizado.ilike(f"%{query}%")
        )
        
        # Filtrar por categoría si se especifica
        if category:
            query_db = query_db.filter(MedicalTerminology.categoria == category)
        
        # Ordenar por frecuencia de uso y limitar resultados
        terms = query_db.order_by(
            MedicalTerminology.frecuencia_uso.desc(),
            MedicalTerminology.termino_original
        ).limit(limit).all()
        
        results = []
        for term in terms:
            results.append({
                "id": str(term.id),
                "termino_original": term.termino_original,
                "categoria": term.categoria,
                "especialidad_medica": term.especialidad_medica,
                "definicion_italiana": term.definicion_italiana,
                "definicion_espanola": term.definicion_espanola,
                "sinonimos": term.sinonimos,
                "nivel_complejidad": term.nivel_complejidad,
                "frecuencia_uso": term.frecuencia_uso,
                "validado_por_experto": term.validado_por_experto
            })
        
        return {
            "success": True,
            "data": {
                "query": query,
                "category": category,
                "total_results": len(results),
                "results": results
            }
        }
        
    except Exception as e:
        logger.error(f"Error buscando terminología: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.put("/llm-analysis/{llm_analysis_id}/validate")
async def validate_llm_analysis(
    llm_analysis_id: UUID,
    validated: bool = Query(..., description="Marcar como validado por humano"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Marcar análisis LLM como validado por humano."""
    try:
        result = db.query(LLMAnalysisResult).filter(
            LLMAnalysisResult.id == llm_analysis_id
        ).first()
        
        if not result:
            raise HTTPException(status_code=404, detail="Resultado de análisis LLM no encontrado")
        
        result.validated_by_human = validated
        if validated:
            result.needs_review = False
        
        db.commit()
        
        logger.info(f"Análisis LLM {llm_analysis_id} marcado como validado: {validated}")
        
        return {
            "success": True,
            "message": f"Análisis LLM {'validado' if validated else 'marcado como no validado'}",
            "data": {
                "llm_analysis_id": str(llm_analysis_id),
                "validated_by_human": validated,
                "needs_review": result.needs_review
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validando análisis LLM: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
