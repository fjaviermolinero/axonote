"""
Configuración central de la aplicación Axonote.
Utiliza Pydantic Settings para validación automática de variables de entorno.
"""

import secrets
from typing import Any, Dict, List, Optional, Union
from pydantic import (
    AnyHttpUrl,
    BaseSettings,
    EmailStr,
    HttpUrl,
    PostgresDsn,
    RedisDsn,
    validator,
)


class Settings(BaseSettings):
    """Configuración principal de Axonote."""
    
    # ==============================================
    # CONFIGURACIÓN BÁSICA DE LA APLICACIÓN
    # ==============================================
    
    APP_NAME: str = "Axonote API"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "API para transcripción y análisis de clases médicas"
    APP_ENV: str = "dev"
    DEBUG: bool = False
    
    # Seguridad
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 días
    
    # API Configuration
    API_PORT: int = 8000
    API_HOST: str = "0.0.0.0"
    API_V1_STR: str = "/api/v1"
    
    # CORS
    CORS_ORIGINS: List[AnyHttpUrl] = ["http://localhost:3000"]
    
    @validator("CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)
    
    # ==============================================
    # BASE DE DATOS
    # ==============================================
    
    DATABASE_URL: PostgresDsn
    DATABASE_ECHO: bool = False  # SQL logging
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    
    # ==============================================
    # REDIS Y CELERY
    # ==============================================
    
    REDIS_URL: RedisDsn = "redis://redis:6379/0"
    CELERY_BROKER_URL: RedisDsn = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: RedisDsn = "redis://redis:6379/1"
    
    # ==============================================
    # ALMACENAMIENTO (MinIO/Nextcloud)
    # ==============================================
    
    STORAGE_BACKEND: str = "minio"  # minio | nextcloud
    
    # MinIO Configuration
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "recordings"
    MINIO_SECURE: bool = False
    
    # Nextcloud Configuration (alternativa)
    NEXTCLOUD_URL: Optional[HttpUrl] = None
    NEXTCLOUD_USERNAME: Optional[str] = None
    NEXTCLOUD_PASSWORD: Optional[str] = None
    NEXTCLOUD_FOLDER: str = "recordings"
    
    # ==============================================
    # INTEGRACIÓN NOTION
    # ==============================================
    
    NOTION_TOKEN: Optional[str] = None
    NOTION_DB_CLASSES: Optional[str] = None
    NOTION_DB_SOURCES: Optional[str] = None
    NOTION_DB_TERMS: Optional[str] = None
    NOTION_DB_CARDS: Optional[str] = None
    
    # ==============================================
    # CONFIGURACIÓN LLM
    # ==============================================
    
    LLM_PROVIDER: str = "lmstudio"  # lmstudio | ollama | openai
    
    # Local LLM (LM Studio / Ollama)
    LMSTUDIO_BASE_URL: str = "http://lmstudio:1234/v1"
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    LOCAL_MODEL_NAME: str = "Qwen2.5-14B-Instruct-Q4_K_M"
    
    # OpenAI (fallback remoto)
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    MAX_REMOTE_COST_EUR: float = 25.0
    
    # ==============================================
    # ASR Y DIARIZACIÓN
    # ==============================================
    
    WHISPER_MODEL: str = "large-v3"  # tiny, base, small, medium, large-v3
    WHISPER_DEVICE: str = "cuda"  # cuda, cpu
    WHISPER_COMPUTE_TYPE: str = "float16"  # float16, int8, int8_float16
    USE_WHISPERX: bool = True
    VAD_FILTER: bool = True
    
    # Diarización
    USE_DIARIZATION: bool = True
    DIARIZATION_MODEL: str = "pyannote/speaker-diarization-3.1"
    HF_TOKEN: Optional[str] = None  # Hugging Face token
    
    # ==============================================
    # OCR CONFIGURATION
    # ==============================================
    
    TESSERACT_LANG: str = "ita+eng"
    TESSDATA_PREFIX: str = "/usr/share/tesseract-ocr/4.00/tessdata"
    OCR_DPI: int = 300
    OCR_PSM: int = 3  # Page Segmentation Mode
    
    # ==============================================
    # TTS CONFIGURATION
    # ==============================================
    
    PIPER_VOICE_ES: str = "es_ES-mls_10246-medium"
    PIPER_VOICE_IT: str = "it_IT-riccardo-x_low"
    PIPER_BIN: str = "/usr/local/bin/piper"
    TTS_SAMPLE_RATE: int = 22050
    
    # ==============================================
    # FEATURE FLAGS
    # ==============================================
    
    FEATURE_PROFESSOR_ENTITY: bool = True
    FEATURE_STRICT_JSON: bool = False
    FEATURE_REMOTE_TURBO: bool = False
    FEATURE_CALENDAR_INTEGRATION: bool = False
    FEATURE_OCR: bool = True
    FEATURE_TTS: bool = True
    FEATURE_BATCH_REPROCESS: bool = True
    
    # ==============================================
    # SEGURIDAD Y LÍMITES
    # ==============================================
    
    RATE_LIMIT_PER_MINUTE: int = 60
    MAX_UPLOAD_SIZE_MB: int = 500
    MAX_CHUNK_SIZE_MB: int = 10
    ALLOWED_AUDIO_FORMATS: List[str] = ["wav", "mp3", "m4a", "flac", "ogg"]
    ALLOWED_IMAGE_FORMATS: List[str] = ["jpg", "jpeg", "png", "webp"]
    
    # ==============================================
    # LOGGING
    # ==============================================
    
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json | text
    LOG_FILE: Optional[str] = "/app/logs/axonote.log"
    
    # ==============================================
    # FUENTES MÉDICAS Y IDIOMAS
    # ==============================================
    
    ALLOWED_MEDICAL_SOURCES: List[str] = [
        "who.int",
        "ecdc.europa.eu", 
        "cdc.gov",
        "nih.gov",
        "pubmed.ncbi.nlm.nih.gov",
        "nice.org.uk",
        "ema.europa.eu",
        "cochrane.org"
    ]
    
    DEFAULT_SOURCE_LANGUAGE: str = "it"  # Idioma principal de las clases
    OUTPUT_LANGUAGE: str = "es"  # Idioma de salida (resúmenes)
    SUPPORTED_LANGUAGES: List[str] = ["it", "en", "es"]
    
    # ==============================================
    # PROCESAMIENTO
    # ==============================================
    
    MAX_CONCURRENT_TRANSCRIPTIONS: int = 2
    CHUNK_SIZE_SECONDS: int = 30
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHANNELS: int = 1
    
    # ==============================================
    # MONITORING
    # ==============================================
    
    ENABLE_METRICS: bool = True
    METRICS_RETENTION_DAYS: int = 90
    ERROR_REPORTING: bool = True
    
    # Swagger/OpenAPI
    ENABLE_SWAGGER: bool = True
    ENABLE_REDOC: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Instancia global de configuración
settings = Settings()


def get_settings() -> Settings:
    """Obtener configuración de la aplicación."""
    return settings
