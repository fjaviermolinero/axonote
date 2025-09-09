"""
Endpoints para configuración y ajustes del sistema.
Permite consultar y modificar feature flags y configuraciones.
"""

from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.core import settings, api_logger

router = APIRouter()


class FeatureFlags(BaseModel):
    """Modelo para feature flags del sistema."""
    professor_entity: bool
    strict_json: bool
    remote_turbo: bool
    calendar_integration: bool
    ocr: bool
    tts: bool
    batch_reprocess: bool


class SystemConfig(BaseModel):
    """Configuración del sistema."""
    whisper_model: str
    whisper_device: str
    default_source_language: str
    output_language: str
    supported_languages: List[str]
    max_upload_size_mb: int
    allowed_audio_formats: List[str]
    allowed_image_formats: List[str]


class SettingsResponse(BaseModel):
    """Respuesta completa de configuración."""
    feature_flags: FeatureFlags
    system_config: SystemConfig
    app_info: Dict[str, Any]


@router.get("/", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    """
    Obtener configuración actual del sistema.
    Incluye feature flags, configuración y info de la app.
    """
    api_logger.info("Consultando configuración del sistema")
    
    return SettingsResponse(
        feature_flags=FeatureFlags(
            professor_entity=settings.FEATURE_PROFESSOR_ENTITY,
            strict_json=settings.FEATURE_STRICT_JSON,
            remote_turbo=settings.FEATURE_REMOTE_TURBO,
            calendar_integration=settings.FEATURE_CALENDAR_INTEGRATION,
            ocr=settings.FEATURE_OCR,
            tts=settings.FEATURE_TTS,
            batch_reprocess=settings.FEATURE_BATCH_REPROCESS
        ),
        system_config=SystemConfig(
            whisper_model=settings.WHISPER_MODEL,
            whisper_device=settings.WHISPER_DEVICE,
            default_source_language=settings.DEFAULT_SOURCE_LANGUAGE,
            output_language=settings.OUTPUT_LANGUAGE,
            supported_languages=settings.SUPPORTED_LANGUAGES,
            max_upload_size_mb=settings.MAX_UPLOAD_SIZE_MB,
            allowed_audio_formats=settings.ALLOWED_AUDIO_FORMATS,
            allowed_image_formats=settings.ALLOWED_IMAGE_FORMATS
        ),
        app_info={
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV,
            "llm_provider": settings.LLM_PROVIDER,
            "storage_backend": settings.STORAGE_BACKEND
        }
    )


@router.get("/feature-flags")
async def get_feature_flags() -> FeatureFlags:
    """Obtener solo los feature flags actuales."""
    api_logger.info("Consultando feature flags")
    
    return FeatureFlags(
        professor_entity=settings.FEATURE_PROFESSOR_ENTITY,
        strict_json=settings.FEATURE_STRICT_JSON,
        remote_turbo=settings.FEATURE_REMOTE_TURBO,
        calendar_integration=settings.FEATURE_CALENDAR_INTEGRATION,
        ocr=settings.FEATURE_OCR,
        tts=settings.FEATURE_TTS,
        batch_reprocess=settings.FEATURE_BATCH_REPROCESS
    )


@router.post("/feature-flags")
async def update_feature_flags(flags: FeatureFlags) -> Dict[str, Any]:
    """
    Actualizar feature flags del sistema.
    NOTA: En esta versión los cambios son temporales (solo en memoria).
    """
    api_logger.info("Actualizando feature flags", new_flags=flags.dict())
    
    # TODO: En futuras versiones, persistir en base de datos
    # Por ahora, solo actualizar en memoria (settings)
    
    # Aplicar cambios (temporal)
    settings.FEATURE_PROFESSOR_ENTITY = flags.professor_entity
    settings.FEATURE_STRICT_JSON = flags.strict_json
    settings.FEATURE_REMOTE_TURBO = flags.remote_turbo
    settings.FEATURE_CALENDAR_INTEGRATION = flags.calendar_integration
    settings.FEATURE_OCR = flags.ocr
    settings.FEATURE_TTS = flags.tts
    settings.FEATURE_BATCH_REPROCESS = flags.batch_reprocess
    
    api_logger.info("Feature flags actualizados exitosamente")
    
    return {
        "message": "Feature flags actualizados",
        "updated_flags": flags.dict(),
        "note": "Los cambios son temporales hasta el reinicio del servidor"
    }


@router.get("/capabilities")
async def get_system_capabilities() -> Dict[str, Any]:
    """
    Obtener capacidades del sistema basadas en configuración actual.
    Útil para el frontend para saber qué funcionalidades mostrar.
    """
    capabilities = {
        "transcription": {
            "available": True,
            "models": ["tiny", "base", "small", "medium", "large-v3"],
            "current_model": settings.WHISPER_MODEL,
            "device": settings.WHISPER_DEVICE,
            "word_alignment": settings.USE_WHISPERX
        },
        "diarization": {
            "available": settings.USE_DIARIZATION,
            "model": settings.DIARIZATION_MODEL if settings.USE_DIARIZATION else None
        },
        "llm": {
            "local_available": settings.LLM_PROVIDER in ["lmstudio", "ollama"],
            "remote_available": bool(settings.OPENAI_API_KEY) and settings.FEATURE_REMOTE_TURBO,
            "current_provider": settings.LLM_PROVIDER,
            "local_model": settings.LOCAL_MODEL_NAME
        },
        "ocr": {
            "available": settings.FEATURE_OCR,
            "languages": settings.TESSERACT_LANG.split('+') if settings.FEATURE_OCR else []
        },
        "tts": {
            "available": settings.FEATURE_TTS,
            "voices": {
                "spanish": settings.PIPER_VOICE_ES,
                "italian": settings.PIPER_VOICE_IT
            } if settings.FEATURE_TTS else {}
        },
        "storage": {
            "backend": settings.STORAGE_BACKEND,
            "max_upload_mb": settings.MAX_UPLOAD_SIZE_MB,
            "audio_formats": settings.ALLOWED_AUDIO_FORMATS,
            "image_formats": settings.ALLOWED_IMAGE_FORMATS
        },
        "notion": {
            "available": bool(settings.NOTION_TOKEN),
            "databases_configured": all([
                settings.NOTION_DB_CLASSES,
                settings.NOTION_DB_SOURCES, 
                settings.NOTION_DB_TERMS,
                settings.NOTION_DB_CARDS
            ])
        },
        "languages": {
            "input": settings.SUPPORTED_LANGUAGES,
            "default_input": settings.DEFAULT_SOURCE_LANGUAGE,
            "output": settings.OUTPUT_LANGUAGE
        }
    }
    
    api_logger.info("Consultando capacidades del sistema")
    
    return {
        "capabilities": capabilities,
        "feature_flags": {
            "professor_entity": settings.FEATURE_PROFESSOR_ENTITY,
            "strict_json": settings.FEATURE_STRICT_JSON,
            "remote_turbo": settings.FEATURE_REMOTE_TURBO,
            "calendar_integration": settings.FEATURE_CALENDAR_INTEGRATION,
            "ocr": settings.FEATURE_OCR,
            "tts": settings.FEATURE_TTS,
            "batch_reprocess": settings.FEATURE_BATCH_REPROCESS
        }
    }


@router.get("/medical-sources")
async def get_medical_sources() -> Dict[str, List[str]]:
    """Obtener lista de fuentes médicas permitidas."""
    return {
        "allowed_sources": settings.ALLOWED_MEDICAL_SOURCES,
        "description": "Fuentes médicas verificadas y permitidas para ampliación de contenido"
    }


@router.get("/limits")
async def get_system_limits() -> Dict[str, Any]:
    """Obtener límites del sistema."""
    return {
        "upload": {
            "max_size_mb": settings.MAX_UPLOAD_SIZE_MB,
            "allowed_audio_formats": settings.ALLOWED_AUDIO_FORMATS,
            "allowed_image_formats": settings.ALLOWED_IMAGE_FORMATS
        },
        "processing": {
            "max_concurrent_transcriptions": settings.MAX_CONCURRENT_TRANSCRIPTIONS,
            "chunk_size_seconds": settings.CHUNK_SIZE_SECONDS,
            "audio_sample_rate": settings.AUDIO_SAMPLE_RATE
        },
        "api": {
            "rate_limit_per_minute": settings.RATE_LIMIT_PER_MINUTE
        },
        "llm": {
            "max_remote_cost_eur": settings.MAX_REMOTE_COST_EUR if settings.FEATURE_REMOTE_TURBO else None
        }
    }
