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
    # INTEGRACIÓN NOTION - FASE 8 COMPLETA
    # ==============================================
    
    # Configuración Básica
    NOTION_TOKEN: Optional[str] = None
    NOTION_VERSION: str = "2022-06-28"
    NOTION_WORKSPACE_ID: Optional[str] = None
    
    # Databases IDs
    NOTION_DB_CLASSES: Optional[str] = None
    NOTION_DB_SOURCES: Optional[str] = None
    NOTION_DB_TERMS: Optional[str] = None
    NOTION_DB_CARDS: Optional[str] = None
    NOTION_DB_PROFESSORS: Optional[str] = None
    NOTION_DB_RESEARCH: Optional[str] = None
    
    # Sincronización Automática
    NOTION_AUTO_SYNC_ENABLED: bool = True
    NOTION_SYNC_ON_COMPLETION: bool = True
    NOTION_SYNC_INTERVAL_MINUTES: int = 15
    NOTION_BATCH_SYNC_SIZE: int = 10
    
    # Templates y Estructuras
    NOTION_DEFAULT_TEMPLATE: str = "clase_magistral"
    NOTION_AUTO_DETECT_TEMPLATE: bool = True
    NOTION_CUSTOM_TEMPLATES_PATH: str = "data/notion_templates/"
    NOTION_TEMPLATE_VALIDATION: str = "strict"  # strict | loose
    
    # Gestión de Contenido
    NOTION_MAX_PAGE_SIZE_MB: int = 50
    NOTION_MAX_BLOCKS_PER_PAGE: int = 2000
    NOTION_CONTENT_TRUNCATION: str = "smart"  # smart | hard | none
    NOTION_PRESERVE_FORMATTING: bool = True
    
    # Attachments y Multimedia
    NOTION_UPLOAD_ATTACHMENTS: bool = True
    NOTION_MAX_ATTACHMENT_SIZE_MB: int = 50
    NOTION_ATTACHMENT_STORAGE: str = "hybrid"  # notion | minio | hybrid
    NOTION_COMPRESS_AUDIO: bool = True
    NOTION_AUDIO_FORMAT: str = "mp3"
    
    # Sincronización Bidireccional
    NOTION_BIDIRECTIONAL_SYNC: bool = True
    NOTION_CONFLICT_RESOLUTION: str = "auto"  # auto | manual | overwrite
    NOTION_CHANGE_DETECTION_INTERVAL: int = 5
    NOTION_MERGE_STRATEGY: str = "smart"  # smart | overwrite | manual
    
    # Performance y Rate Limiting
    NOTION_REQUESTS_PER_SECOND: float = 3.0
    NOTION_CONCURRENT_UPLOADS: int = 2
    NOTION_RETRY_ATTEMPTS: int = 3
    NOTION_TIMEOUT_SECONDS: int = 30
    NOTION_CACHE_PAGES: bool = True
    
    # Validación y Calidad
    NOTION_VALIDATE_BEFORE_SYNC: bool = True
    NOTION_CONTENT_QUALITY_CHECK: bool = True
    NOTION_DUPLICATE_DETECTION: bool = True
    NOTION_BACKUP_BEFORE_SYNC: bool = True
    
    # Notificaciones y Logs
    NOTION_SYNC_NOTIFICATIONS: bool = True
    NOTION_ERROR_NOTIFICATIONS: bool = True
    NOTION_DETAILED_LOGGING: bool = True
    NOTION_METRICS_COLLECTION: bool = True
    
    # Configuración Avanzada
    NOTION_API_RETRIES_BACKOFF: str = "exponential"  # linear | exponential
    NOTION_PARALLEL_PROCESSING: bool = True
    NOTION_MEMORY_OPTIMIZATION: bool = True
    NOTION_EXPERIMENTAL_FEATURES: bool = False
    
    # ==============================================
    # CONFIGURACIÓN LLM
    # ==============================================
    
    LLM_PROVIDER: str = "lmstudio"  # lmstudio | ollama | openai
    
    # Local LLM (LM Studio / Ollama)
    LMSTUDIO_BASE_URL: str = "http://lmstudio:1234"
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    LLM_MODEL_NAME: str = "qwen2.5-14b-instruct"
    LLM_MAX_TOKENS: int = 4000
    LLM_TEMPERATURE: float = 0.1
    
    # OpenAI (fallback remoto)
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_MAX_MONTHLY_COST: float = 25.0
    
    # ==============================================
    # POST-PROCESAMIENTO Y ANÁLISIS
    # ==============================================
    
    # Corrección ASR
    ENABLE_ASR_CORRECTION: bool = True
    ASR_CONFIDENCE_THRESHOLD: float = 0.8
    MEDICAL_DICT_PATH: str = "data/medical_dict_it.json"
    
    # NER Médico
    ENABLE_MEDICAL_NER: bool = True
    NER_CONFIDENCE_THRESHOLD: float = 0.8
    NER_INCLUDE_DEFINITIONS: bool = True
    
    # Análisis de estructura
    ENABLE_STRUCTURE_ANALYSIS: bool = True
    STRUCTURE_MIN_SEGMENT_SEC: int = 30
    
    # Calidad y validación
    QUALITY_MIN_COHERENCE: float = 0.7
    QUALITY_MIN_COMPLETENESS: float = 0.6
    AUTO_REVIEW_THRESHOLD: float = 0.8
    ENABLE_QUALITY_GATES: bool = True
    
    # Procesamiento
    MAX_PROCESSING_TIME_MINUTES: int = 120
    ENABLE_AUDIO_NORMALIZATION: bool = True
    PROCESSING_CHUNK_SIZE_SEC: int = 600
    
    # ==============================================
    # RESEARCH Y FUENTES MÉDICAS - FASE 6
    # ==============================================
    
    # Configuración general de research
    ENABLE_MEDICAL_RESEARCH: bool = True
    RESEARCH_DEFAULT_PRESET: str = "COMPREHENSIVE"
    RESEARCH_DEFAULT_LANGUAGE: str = "it"
    RESEARCH_MAX_CONCURRENT_JOBS: int = 3
    RESEARCH_TIMEOUT_MINUTES: int = 30
    
    # APIs oficiales
    NCBI_API_KEY: Optional[str] = None
    NCBI_EMAIL: str = "research@axonote.com"
    WHO_API_KEY: Optional[str] = None
    NIH_API_KEY: Optional[str] = None
    
    # Rate limiting
    PUBMED_REQUESTS_PER_SECOND: float = 3.0
    WHO_REQUESTS_PER_SECOND: float = 2.0
    GENERAL_REQUESTS_PER_SECOND: float = 5.0
    
    # Cache configuration
    RESEARCH_CACHE_ENABLED: bool = True
    RESEARCH_CACHE_TTL_HOURS: int = 168  # 7 días
    RESEARCH_CACHE_MAX_SIZE_MB: int = 1024  # 1GB
    RESEARCH_CACHE_CLEANUP_INTERVAL_HOURS: int = 24
    
    # Validación de contenido
    CONTENT_VALIDATION_ENABLED: bool = True
    MIN_RELEVANCE_SCORE: float = 0.6
    MIN_AUTHORITY_SCORE: float = 0.7
    ENABLE_FACT_CHECKING: bool = True
    ENABLE_PEER_REVIEW_PRIORITY: bool = True
    
    # Fuentes específicas
    ENABLE_PUBMED_SEARCH: bool = True
    ENABLE_WHO_SEARCH: bool = True
    ENABLE_NIH_SEARCH: bool = True
    ENABLE_MEDLINEPLUS_SEARCH: bool = True
    ENABLE_ITALIAN_SOURCES: bool = True
    ENABLE_WEB_SCRAPING: bool = False  # Deshabilitado por defecto
    
    # Límites de búsqueda
    MAX_SOURCES_PER_TERM: int = 5
    MAX_SEARCH_RESULTS: int = 20
    SEARCH_TIMEOUT_SECONDS: int = 30
    
    # Idiomas y localización
    SUPPORTED_RESEARCH_LANGUAGES: List[str] = ["it", "en", "es"]
    TRANSLATION_SERVICE_ENABLED: bool = True
    ITALIAN_SOURCES_PRIORITY: bool = True
    
    # Métricas y monitoring
    RESEARCH_METRICS_ENABLED: bool = True
    RESEARCH_PERFORMANCE_LOGGING: bool = True
    RESEARCH_ERROR_REPORTING: bool = True
    
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
    HF_TOKEN: Optional[str] = None  # Hugging Face token para pyannote
    
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
    
    # ==============================================
    # OCR CONFIGURATION - FASE 9
    # ==============================================
    
    # Configuración Básica OCR
    OCR_ENABLED: bool = True
    OCR_ENGINE: str = "tesseract"  # tesseract, easyocr, paddle
    OCR_LANGUAGES: str = "ita+eng"  # Idiomas soportados
    OCR_CONFIDENCE_THRESHOLD: float = 0.7  # Umbral mínimo de confianza
    OCR_MAX_FILE_SIZE_MB: int = 50  # Tamaño máximo archivo
    OCR_SUPPORTED_FORMATS: str = "pdf,png,jpg,jpeg,tiff,bmp"  # Formatos soportados
    
    # Tesseract específico
    TESSERACT_CMD: Optional[str] = None  # Path al ejecutable, None = auto
    TESSERACT_CONFIG_DIR: Optional[str] = None  # Directorio configuraciones
    TESSERACT_MEDICAL_DICT: Optional[str] = None  # Diccionario médico italiano
    
    # Pre-procesamiento imagen
    OCR_IMAGE_PREPROCESSING: bool = True
    OCR_IMAGE_DPI: int = 300
    OCR_IMAGE_ENHANCE: bool = True
    OCR_IMAGE_DESKEW: bool = True
    
    # Performance OCR
    OCR_CONCURRENT_PROCESSING: int = 2  # Procesamiento concurrente
    OCR_CHUNK_SIZE: int = 4  # Páginas por chunk
    OCR_TIMEOUT_SECONDS: int = 300  # Timeout procesamiento
    OCR_RETRY_ATTEMPTS: int = 3  # Intentos de retry
    
    # Validación calidad
    OCR_REQUIRE_MEDICAL_VALIDATION: bool = True  # Validar contenido médico
    OCR_MIN_TEXT_LENGTH: int = 50  # Mínimo texto extraído
    OCR_MAX_NOISE_RATIO: float = 0.3  # Máximo ratio de ruido
    
    # ==============================================
    # MICRO-MEMOS CONFIGURATION - FASE 9
    # ==============================================
    
    # Configuración Básica
    MICROMEMOS_ENABLED: bool = True
    MICROMEMOS_AUTO_GENERATE: bool = True  # Auto-generar tras OCR/LLM
    MICROMEMOS_MIN_CONFIDENCE: float = 0.6  # Confianza mínima para auto-gen
    MICROMEMOS_MAX_PER_CONCEPT: int = 3  # Máximo memos por concepto
    MICROMEMOS_DIFFICULTY_BALANCE: bool = True  # Balancear dificultades
    
    # Generación automática
    MICROMEMOS_AUTO_TRIGGER_OCR: bool = True  # Trigger tras OCR exitoso
    MICROMEMOS_AUTO_TRIGGER_LLM: bool = True  # Trigger tras análisis LLM
    MICROMEMOS_AUTO_COLLECTION: bool = True  # Crear colecciones automáticas
    
    # Templates y tipos
    MICROMEMOS_TYPES: str = "definition,concept,process,case,fact,comparison,symptom,treatment"
    MICROMEMOS_DEFAULT_STUDY_TIME: int = 5  # Minutos por memo
    MICROMEMOS_SPACED_REPETITION: bool = True  # Habilitar repetición espaciada
    
    # Performance
    MICROMEMOS_BATCH_SIZE: int = 20  # Memos por batch LLM
    MICROMEMOS_CONCURRENT_GENERATION: int = 1  # Generación concurrente
    MICROMEMOS_LLM_TIMEOUT: int = 60  # Timeout LLM por memo
    
    # Calidad
    MICROMEMOS_QUALITY_THRESHOLD: float = 0.7  # Umbral calidad mínima
    MICROMEMOS_REQUIRE_REVIEW_THRESHOLD: float = 0.6  # Umbral para revisión manual
    MICROMEMOS_AUTO_APPROVE_THRESHOLD: float = 0.9  # Umbral auto-aprobación
    
    # ==============================================
    # NOTION INTEGRATION EXTENSION - FASE 9
    # ==============================================
    
    # Nuevas databases para Fase 9
    NOTION_DB_OCR_RESULTS: Optional[str] = None  # Database resultados OCR
    NOTION_DB_MICROMEMOS: Optional[str] = None  # Database micro-memos
    NOTION_DB_COLLECTIONS: Optional[str] = None  # Database colecciones
    
    # Templates OCR
    NOTION_OCR_TEMPLATE: str = "ocr_content"  # Template para contenido OCR
    NOTION_SYNC_OCR: bool = True  # Sincronizar contenido OCR
    NOTION_OCR_PAGE_LIMIT: int = 50  # Límite documentos OCR por página
    
    # Templates micro-memos
    NOTION_SYNC_MICROMEMOS: bool = True  # Sincronizar micro-memos
    NOTION_MICROMEMO_PAGE_LIMIT: int = 100  # Límite memos por página
    NOTION_CREATE_INDIVIDUAL_MEMO_PAGES: bool = False  # Páginas individuales por memo
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Instancia global de configuración
settings = Settings()


def get_settings() -> Settings:
    """Obtener configuración de la aplicación."""
    return settings
