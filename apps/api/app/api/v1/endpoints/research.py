"""
Endpoints REST para gestión de investigación médica automática.

Proporciona APIs para iniciar, monitorear y gestionar trabajos
de research automático de fuentes médicas verificadas.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from celery.result import AsyncResult

from app.core.database import get_db
from app.models import (
    ResearchJob, ResearchResult, MedicalSource, SourceCache,
    LLMAnalysisResult
)
from app.services.research_service import ResearchService, ResearchConfig
from app.services.source_cache_service import SourceCacheService
from app.tasks.research import (
    start_medical_research_task,
    research_single_term_task,
    cleanup_cache_task,
    health_check_sources_task
)
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter()


# Schemas de request/response
class ResearchConfigRequest:
    """Schema para configuración de research."""
    
    def __init__(
        self,
        preset: str = "COMPREHENSIVE",
        language: str = "it",
        max_sources_per_term: int = 3,
        enabled_sources: Optional[List[str]] = None,
        priority: str = "normal",
        include_related_terms: bool = True,
        enable_translation: bool = True
    ):
        self.preset = preset
        self.language = language
        self.max_sources_per_term = max_sources_per_term
        self.enabled_sources = enabled_sources
        self.priority = priority
        self.include_related_terms = include_related_terms
        self.enable_translation = enable_translation


class ResearchJobResponse:
    """Schema para respuesta de trabajo de research."""
    
    def __init__(self, research_job: ResearchJob, task_id: str = None):
        self.research_job_id = str(research_job.id)
        self.status = research_job.status
        self.progress_percentage = research_job.progress_percentage
        self.current_step = research_job.current_step
        self.preset = research_job.research_preset
        self.priority = research_job.priority
        self.total_terms = research_job.total_terms
        self.terms_researched = research_job.terms_researched
        self.sources_found = research_job.sources_found
        self.cache_hits = research_job.cache_hits
        self.estimated_remaining_seconds = research_job.estimated_remaining_seconds
        self.created_at = research_job.created_at.isoformat()
        self.task_id = task_id or research_job.celery_task_id


# Endpoints principales
@router.post("/research/start/{llm_analysis_id}")
async def start_research(
    llm_analysis_id: UUID,
    config: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Inicia investigación automática para un análisis LLM.
    
    Args:
        llm_analysis_id: ID del análisis LLM completado
        config: Configuración de research
        
    Returns:
        Información del trabajo de research iniciado
    """
    try:
        logger.info(f"Iniciando research para LLM analysis {llm_analysis_id}")
        
        # Verificar que el análisis LLM existe
        llm_analysis = db.query(LLMAnalysisResult).filter(
            LLMAnalysisResult.id == llm_analysis_id
        ).first()
        
        if not llm_analysis:
            raise HTTPException(
                status_code=404,
                detail=f"Análisis LLM {llm_analysis_id} no encontrado"
            )
        
        # Verificar si ya existe un research job para este análisis
        existing_job = db.query(ResearchJob).filter(
            ResearchJob.llm_analysis_id == llm_analysis_id,
            ResearchJob.status.in_(["pending", "researching", "validating", "saving"])
        ).first()
        
        if existing_job:
            return {
                "message": "Ya existe un trabajo de research en progreso",
                "research_job_id": str(existing_job.id),
                "status": existing_job.status,
                "progress": existing_job.progress_percentage
            }
        
        # Validar configuración
        try:
            research_config = ResearchConfig(**config)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Configuración de research inválida: {str(e)}"
            )
        
        # Iniciar tarea asíncrona
        task = start_medical_research_task.delay(
            str(llm_analysis_id),
            config
        )
        
        # Crear entrada inicial en BD (se completará en la tarea)
        research_service = ResearchService(db)
        research_job = await research_service.start_research_job(
            llm_analysis_id,
            research_config,
            config.get('priority', 'normal')
        )
        
        # Actualizar con ID de tarea
        research_job.celery_task_id = task.id
        db.commit()
        
        # Estimar duración
        preset_multipliers = {
            "COMPREHENSIVE": 1.5,
            "QUICK": 0.8,
            "ACADEMIC": 1.2,
            "CLINICAL": 1.0,
            "ITALIAN_FOCUSED": 0.9
        }
        
        base_duration = 300  # 5 minutos base
        multiplier = preset_multipliers.get(research_config.preset, 1.0)
        estimated_duration = int(base_duration * multiplier)
        
        response = {
            "message": "Research iniciado exitosamente",
            "research_job_id": str(research_job.id),
            "task_id": task.id,
            "status": "pending",
            "preset": research_config.preset,
            "priority": config.get('priority', 'normal'),
            "estimated_duration_seconds": estimated_duration,
            "progress_url": f"/api/v1/research/status/{research_job.id}",
            "results_url": f"/api/v1/research/results/{research_job.id}"
        }
        
        logger.info(f"Research job {research_job.id} iniciado con tarea {task.id}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error iniciando research: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )


@router.get("/research/status/{research_job_id}")
async def get_research_status(
    research_job_id: UUID,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Obtiene el estado actual de un trabajo de investigación.
    
    Args:
        research_job_id: ID del trabajo de investigación
        
    Returns:
        Estado detallado del research
    """
    try:
        # Buscar trabajo de research
        research_job = db.query(ResearchJob).filter(
            ResearchJob.id == research_job_id
        ).first()
        
        if not research_job:
            raise HTTPException(
                status_code=404,
                detail=f"Trabajo de research {research_job_id} no encontrado"
            )
        
        # Obtener estado de tarea Celery si existe
        celery_status = None
        celery_info = {}
        
        if research_job.celery_task_id:
            celery_result = AsyncResult(research_job.celery_task_id, app=celery_app)
            celery_status = celery_result.status
            
            if celery_result.info:
                celery_info = celery_result.info if isinstance(celery_result.info, dict) else {}
        
        # Preparar respuesta
        response = {
            "research_job_id": str(research_job.id),
            "status": research_job.status,
            "progress_percentage": research_job.progress_percentage,
            "current_step": research_job.current_step,
            "current_term": research_job.current_term,
            
            # Información de configuración
            "preset": research_job.research_preset,
            "priority": research_job.priority,
            "language": research_job.language_preference,
            "enabled_sources": research_job.enabled_sources,
            
            # Progreso detallado
            "total_terms": research_job.total_terms,
            "terms_researched": research_job.terms_researched,
            "terms_from_cache": research_job.terms_from_cache,
            "sources_found": research_job.sources_found,
            "sources_validated": research_job.sources_validated,
            
            # Métricas de cache
            "cache_hits": research_job.cache_hits,
            "cache_misses": research_job.cache_misses,
            "cache_hit_rate": research_job.cache_hit_rate,
            
            # Tiempos
            "started_at": research_job.started_at.isoformat() if research_job.started_at else None,
            "completed_at": research_job.completed_at.isoformat() if research_job.completed_at else None,
            "duration_seconds": research_job.duration_seconds,
            "estimated_remaining_seconds": research_job.estimated_remaining_seconds,
            
            # Estado de Celery
            "celery_status": celery_status,
            "celery_info": celery_info,
            
            # Errores y warnings
            "error_message": research_job.error_message,
            "warnings": research_job.warnings,
            
            # Estado general
            "is_active": research_job.is_active,
            "is_completed": research_job.is_completed
        }
        
        # Añadir información específica según estado
        if research_job.is_completed and research_job.status == "completed":
            response["summary"] = {
                "success": True,
                "terms_completion_rate": research_job.terms_completion_rate,
                "sources_per_term_average": research_job.sources_per_term_average,
                "average_relevance_score": research_job.average_relevance_score,
                "total_duration_minutes": research_job.duration_minutes
            }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo estado de research: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )


@router.get("/research/results/{research_job_id}")
async def get_research_results(
    research_job_id: UUID,
    include_sources: bool = Query(True, description="Incluir fuentes detalladas"),
    limit: Optional[int] = Query(None, description="Límite de resultados"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Obtiene los resultados completos de investigación.
    
    Args:
        research_job_id: ID del trabajo de investigación
        include_sources: Si incluir fuentes detalladas
        limit: Límite de resultados
        
    Returns:
        Resultados completos del research
    """
    try:
        # Buscar trabajo de research
        research_job = db.query(ResearchJob).filter(
            ResearchJob.id == research_job_id
        ).first()
        
        if not research_job:
            raise HTTPException(
                status_code=404,
                detail=f"Trabajo de research {research_job_id} no encontrado"
            )
        
        # Obtener resultados de investigación
        results_query = db.query(ResearchResult).filter(
            ResearchResult.research_job_id == research_job_id
        ).order_by(ResearchResult.confidence_score.desc())
        
        if limit:
            results_query = results_query.limit(limit)
        
        research_results = results_query.all()
        
        # Preparar respuesta
        response = {
            "research_job_id": str(research_job.id),
            "status": research_job.status,
            "total_results": len(research_results),
            "job_summary": research_job.get_summary_stats(),
            "results": []
        }
        
        # Procesar cada resultado
        for result in research_results:
            result_data = {
                "result_id": str(result.id),
                "medical_term": result.medical_term,
                "term_category": result.term_category,
                "primary_definition": result.primary_definition,
                "sources_count": result.sources_count,
                "quality_grade": result.quality_grade,
                "confidence_score": result.confidence_score,
                "source_reliability": result.source_reliability,
                "has_high_quality_sources": result.has_high_quality_sources,
                "needs_human_review": result.needs_human_review(),
                "search_duration_ms": result.search_duration_ms,
                "cache_hit": result.cache_hit
            }
            
            # Incluir fuentes si se solicita
            if include_sources and result.medical_sources:
                result_data["sources"] = []
                
                for source in result.medical_sources:
                    source_data = {
                        "source_id": str(source.id),
                        "title": source.title,
                        "url": source.url,
                        "domain": source.domain,
                        "source_type": source.source_type,
                        "relevance_score": source.relevance_score,
                        "authority_score": source.authority_score,
                        "overall_score": source.overall_score,
                        "publication_date": source.publication_date.isoformat() if source.publication_date else None,
                        "language": source.language,
                        "access_type": source.access_type,
                        "peer_reviewed": source.peer_reviewed,
                        "official_source": source.official_source,
                        "quality_indicators": source.quality_indicators,
                        "relevant_excerpt": source.relevant_excerpt[:300] if source.relevant_excerpt else None
                    }
                    result_data["sources"].append(source_data)
            else:
                # Solo incluir conteo de fuentes por tipo
                result_data["sources_summary"] = {
                    "total": result.sources_count,
                    "peer_reviewed": result.peer_reviewed_sources_count,
                    "official": result.official_sources_count,
                    "average_relevance": result.average_source_relevance
                }
            
            response["results"].append(result_data)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo resultados de research: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )


@router.get("/research/results/summary/{research_job_id}")
async def get_research_summary(
    research_job_id: UUID,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Obtiene un resumen ejecutivo de los resultados de investigación.
    
    Args:
        research_job_id: ID del trabajo de investigación
        
    Returns:
        Resumen ejecutivo del research
    """
    try:
        # Buscar trabajo de research
        research_job = db.query(ResearchJob).filter(
            ResearchJob.id == research_job_id
        ).first()
        
        if not research_job:
            raise HTTPException(
                status_code=404,
                detail=f"Trabajo de research {research_job_id} no encontrado"
            )
        
        # Obtener estadísticas de resultados
        results = db.query(ResearchResult).filter(
            ResearchResult.research_job_id == research_job_id
        ).all()
        
        if not results:
            return {
                "research_job_id": str(research_job.id),
                "status": research_job.status,
                "message": "No hay resultados disponibles aún"
            }
        
        # Calcular estadísticas
        total_results = len(results)
        high_quality_results = sum(1 for r in results if r.has_high_quality_sources)
        needs_review = sum(1 for r in results if r.needs_human_review())
        
        # Distribución por categorías
        categories = {}
        for result in results:
            category = result.term_category or "general"
            if category not in categories:
                categories[category] = {"count": 0, "avg_confidence": 0.0}
            categories[category]["count"] += 1
            categories[category]["avg_confidence"] += result.confidence_score
        
        # Calcular promedios por categoría
        for category in categories:
            count = categories[category]["count"]
            categories[category]["avg_confidence"] /= count
        
        # Top términos por relevancia
        top_terms = sorted(results, key=lambda r: r.confidence_score, reverse=True)[:10]
        
        # Fuentes más utilizadas
        source_types = {}
        for result in results:
            for source in result.medical_sources:
                source_type = source.source_type
                if source_type not in source_types:
                    source_types[source_type] = 0
                source_types[source_type] += 1
        
        response = {
            "research_job_id": str(research_job.id),
            "status": research_job.status,
            "generated_at": datetime.utcnow().isoformat(),
            
            "overview": {
                "total_terms_researched": total_results,
                "high_quality_results": high_quality_results,
                "quality_percentage": (high_quality_results / total_results) * 100,
                "needs_human_review": needs_review,
                "review_percentage": (needs_review / total_results) * 100,
                "total_sources_found": research_job.sources_found,
                "average_sources_per_term": research_job.sources_per_term_average,
                "cache_hit_rate": research_job.cache_hit_rate * 100
            },
            
            "quality_metrics": {
                "average_confidence": research_job.average_relevance_score or 0.0,
                "average_reliability": sum(r.source_reliability for r in results) / total_results,
                "high_quality_percentage": (high_quality_results / total_results) * 100
            },
            
            "distribution": {
                "by_category": categories,
                "by_source_type": source_types
            },
            
            "top_results": [
                {
                    "term": term.medical_term,
                    "category": term.term_category,
                    "confidence": term.confidence_score,
                    "sources_count": term.sources_count,
                    "quality_grade": term.quality_grade
                }
                for term in top_terms
            ],
            
            "performance": {
                "total_duration_minutes": research_job.duration_minutes,
                "average_time_per_term": (research_job.duration_seconds or 0) / max(1, total_results),
                "cache_efficiency": research_job.cache_hit_rate
            }
        }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo resumen de research: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )


@router.post("/research/term")
async def research_single_term(
    term: str,
    config: Dict[str, Any],
    background_tasks: BackgroundTasks,
    context: Optional[str] = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Investiga un término médico individual.
    
    Args:
        term: Término médico a investigar
        config: Configuración de investigación
        context: Contexto opcional
        
    Returns:
        Resultado de investigación del término
    """
    try:
        logger.info(f"Investigación individual solicitada para término: '{term}'")
        
        # Validar configuración
        try:
            research_config = ResearchConfig(**config)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Configuración inválida: {str(e)}"
            )
        
        # Verificar cache primero
        cache_service = SourceCacheService(db)
        cached_result = await cache_service.get_cached_result(term, config)
        
        if cached_result:
            return {
                "term": term,
                "from_cache": True,
                "cache_age_hours": cached_result.get("cache_age_hours", 0),
                "result": cached_result
            }
        
        # Iniciar investigación asíncrona
        task = research_single_term_task.delay(term, config, context)
        
        return {
            "message": f"Investigación iniciada para término '{term}'",
            "term": term,
            "task_id": task.id,
            "from_cache": False,
            "status_url": f"/api/v1/research/task-status/{task.id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en investigación de término: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )


@router.get("/research/task-status/{task_id}")
async def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Obtiene el estado de una tarea Celery específica.
    
    Args:
        task_id: ID de la tarea Celery
        
    Returns:
        Estado de la tarea
    """
    try:
        result = AsyncResult(task_id, app=celery_app)
        
        response = {
            "task_id": task_id,
            "status": result.status,
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else None,
            "failed": result.failed() if result.ready() else None
        }
        
        if result.ready():
            if result.successful():
                response["result"] = result.result
            elif result.failed():
                response["error"] = str(result.info)
        else:
            # Tarea en progreso, incluir info si está disponible
            if result.info and isinstance(result.info, dict):
                response["progress"] = result.info
        
        return response
        
    except Exception as e:
        logger.error(f"Error obteniendo estado de tarea: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )


@router.get("/research/presets")
async def get_research_presets() -> Dict[str, Any]:
    """
    Lista de presets de investigación disponibles.
    
    Returns:
        Presets disponibles con descripciones
    """
    presets = {
        "COMPREHENSIVE": {
            "name": "Búsqueda Exhaustiva",
            "description": "Búsqueda completa en todas las fuentes disponibles",
            "sources": ["pubmed", "who", "nih", "medlineplus", "italian_official"],
            "max_sources_per_term": 5,
            "estimated_duration_multiplier": 1.5,
            "recommended_for": ["investigación académica", "casos complejos"]
        },
        "QUICK": {
            "name": "Búsqueda Rápida",
            "description": "Búsqueda rápida en fuentes principales",
            "sources": ["pubmed", "who", "italian_official"],
            "max_sources_per_term": 3,
            "estimated_duration_multiplier": 0.8,
            "recommended_for": ["consultas rápidas", "validación básica"]
        },
        "ACADEMIC": {
            "name": "Enfoque Académico",
            "description": "Prioriza artículos peer-reviewed y fuentes académicas",
            "sources": ["pubmed", "nih"],
            "max_sources_per_term": 4,
            "estimated_duration_multiplier": 1.2,
            "recommended_for": ["investigación científica", "evidencia médica"]
        },
        "CLINICAL": {
            "name": "Enfoque Clínico",
            "description": "Enfocado en guías clínicas y información práctica",
            "sources": ["who", "nih", "medlineplus", "italian_official"],
            "max_sources_per_term": 4,
            "estimated_duration_multiplier": 1.0,
            "recommended_for": ["práctica clínica", "guías de tratamiento"]
        },
        "ITALIAN_FOCUSED": {
            "name": "Fuentes Italianas",
            "description": "Prioridad a fuentes médicas italianas oficiales",
            "sources": ["italian_official", "pubmed", "who"],
            "max_sources_per_term": 4,
            "estimated_duration_multiplier": 0.9,
            "recommended_for": ["contexto italiano", "regulaciones locales"]
        }
    }
    
    return {
        "presets": presets,
        "default_preset": "COMPREHENSIVE",
        "total_presets": len(presets)
    }


@router.get("/research/sources")
async def get_available_sources() -> Dict[str, Any]:
    """
    Lista de fuentes médicas disponibles.
    
    Returns:
        Fuentes disponibles con información
    """
    sources = {
        "pubmed": {
            "name": "PubMed/NCBI",
            "description": "Base de datos de literatura médica peer-reviewed",
            "authority_score": 0.95,
            "language": "en",
            "access_type": "free",
            "official": True,
            "peer_reviewed": True,
            "specialties": ["all"]
        },
        "who": {
            "name": "World Health Organization",
            "description": "Organización Mundial de la Salud - recursos oficiales",
            "authority_score": 0.95,
            "language": "en",
            "access_type": "free",
            "official": True,
            "peer_reviewed": False,
            "specialties": ["epidemiology", "public_health", "guidelines"]
        },
        "nih": {
            "name": "National Institutes of Health",
            "description": "Instituto Nacional de Salud de EE.UU.",
            "authority_score": 0.9,
            "language": "en",
            "access_type": "free",
            "official": True,
            "peer_reviewed": False,
            "specialties": ["research", "clinical_info"]
        },
        "medlineplus": {
            "name": "MedlinePlus",
            "description": "Información médica para pacientes (NIH/NLM)",
            "authority_score": 0.8,
            "language": "en/es",
            "access_type": "free",
            "official": True,
            "peer_reviewed": False,
            "specialties": ["patient_education", "drug_info"]
        },
        "italian_official": {
            "name": "Fuentes Italianas Oficiales",
            "description": "ISS, AIFA, Ministero della Salute",
            "authority_score": 0.85,
            "language": "it",
            "access_type": "free",
            "official": True,
            "peer_reviewed": False,
            "specialties": ["italian_regulation", "local_guidelines"]
        }
    }
    
    return {
        "sources": sources,
        "total_sources": len(sources),
        "languages_supported": ["en", "it", "es"],
        "last_updated": datetime.utcnow().isoformat()
    }


@router.get("/research/health")
async def research_health_check(
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Verifica el estado de todos los servicios de research.
    
    Returns:
        Estado de salud del sistema de research
    """
    try:
        # Iniciar verificación asíncrona
        task = health_check_sources_task.delay()
        
        # Verificación básica inmediata
        basic_health = {
            "service": "research_system",
            "status": "checking",
            "task_id": task.id,
            "check_initiated_at": datetime.utcnow().isoformat(),
            "endpoints_available": [
                "start_research",
                "get_status",
                "get_results",
                "single_term_research",
                "cache_management"
            ]
        }
        
        return basic_health
        
    except Exception as e:
        logger.error(f"Error en health check de research: {e}")
        return {
            "service": "research_system",
            "status": "unhealthy",
            "error": str(e),
            "check_timestamp": datetime.utcnow().isoformat()
        }


@router.post("/research/cache/cleanup")
async def cleanup_research_cache(
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Inicia limpieza del cache de research.
    
    Returns:
        Información sobre la tarea de limpieza
    """
    try:
        task = cleanup_cache_task.delay()
        
        return {
            "message": "Limpieza de cache iniciada",
            "task_id": task.id,
            "status_url": f"/api/v1/research/task-status/{task.id}",
            "initiated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error iniciando limpieza de cache: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )


@router.get("/research/cache/stats")
async def get_cache_stats(
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Obtiene estadísticas del cache de research.
    
    Returns:
        Estadísticas del cache
    """
    try:
        cache_service = SourceCacheService(db)
        stats = await cache_service.get_cache_statistics()
        
        return {
            "cache_statistics": stats,
            "retrieved_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas de cache: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor: {str(e)}"
        )
