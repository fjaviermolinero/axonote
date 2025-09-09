"""
Sistema de logging estructurado para Axonote.
Utiliza loguru para logs JSON estructurados con contexto médico.
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from app.core.config import settings


class LoggingSetup:
    """Configuración centralizada de logging."""
    
    def __init__(self):
        self._configured = False
    
    def setup_logging(self) -> None:
        """Configurar sistema de logging estructurado."""
        if self._configured:
            return
        
        # Remover handler por defecto
        logger.remove()
        
        # Configurar formato según configuración
        if settings.LOG_FORMAT == "json":
            log_format = self._get_json_format()
        else:
            log_format = self._get_text_format()
        
        # Handler para consola (siempre activo)
        logger.add(
            sys.stdout,
            format=log_format,
            level=settings.LOG_LEVEL,
            enqueue=True,
            colorize=settings.LOG_FORMAT != "json",
        )
        
        # Handler para archivo (si está configurado)
        if settings.LOG_FILE:
            log_path = Path(settings.LOG_FILE)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            logger.add(
                settings.LOG_FILE,
                format=log_format,
                level=settings.LOG_LEVEL,
                rotation="10 MB",
                retention="30 days",
                compression="gz",
                enqueue=True,
            )
        
        # Handler para errores (siempre a archivo separado)
        if settings.LOG_FILE:
            error_log = str(Path(settings.LOG_FILE).with_suffix('.error.log'))
            logger.add(
                error_log,
                format=log_format,
                level="ERROR",
                rotation="5 MB",
                retention="90 days",
                compression="gz",
                enqueue=True,
            )
        
        self._configured = True
        logger.info("Sistema de logging configurado", 
                   level=settings.LOG_LEVEL, 
                   format=settings.LOG_FORMAT)
    
    def _get_json_format(self) -> str:
        """Formato JSON estructurado."""
        return (
            '{"timestamp": "{time:YYYY-MM-DD HH:mm:ss.SSS}", '
            '"level": "{level}", '
            '"logger": "{name}", '
            '"message": "{message}", '
            '"module": "{module}", '
            '"function": "{function}", '
            '"line": {line}, '
            '"extra": {extra}}'
        )
    
    def _get_text_format(self) -> str:
        """Formato texto legible."""
        return (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )


# Instancia global
logging_setup = LoggingSetup()


def setup_logging() -> None:
    """Configurar logging de la aplicación."""
    logging_setup.setup_logging()


def get_logger(name: str) -> Any:
    """Obtener logger con contexto específico."""
    return logger.bind(logger_name=name)


class ContextLogger:
    """Logger con contexto médico específico."""
    
    def __init__(self, context: str):
        self.context = context
        self.logger = logger.bind(context=context)
    
    def log_transcription_start(
        self, 
        class_id: str, 
        audio_duration: float,
        model: str
    ) -> None:
        """Log inicio de transcripción."""
        self.logger.info(
            "Iniciando transcripción",
            class_id=class_id,
            audio_duration_sec=audio_duration,
            whisper_model=model,
            operation="transcription_start"
        )
    
    def log_transcription_complete(
        self, 
        class_id: str, 
        confidence: float,
        processing_time: float,
        word_count: int
    ) -> None:
        """Log finalización de transcripción."""
        self.logger.info(
            "Transcripción completada",
            class_id=class_id,
            asr_confidence=confidence,
            processing_time_sec=processing_time,
            word_count=word_count,
            operation="transcription_complete"
        )
    
    def log_diarization_result(
        self, 
        class_id: str, 
        speakers_detected: int,
        teacher_segments: int,
        student_segments: int
    ) -> None:
        """Log resultado de diarización."""
        self.logger.info(
            "Diarización completada",
            class_id=class_id,
            speakers_detected=speakers_detected,
            teacher_segments=teacher_segments,
            student_segments=student_segments,
            operation="diarization_complete"
        )
    
    def log_llm_processing(
        self, 
        class_id: str, 
        provider: str,
        model: str,
        tokens_used: int,
        cost_eur: Optional[float] = None
    ) -> None:
        """Log procesamiento LLM."""
        extra_data = {
            "class_id": class_id,
            "llm_provider": provider,
            "llm_model": model,
            "tokens_used": tokens_used,
            "operation": "llm_processing"
        }
        
        if cost_eur is not None:
            extra_data["cost_eur"] = cost_eur
        
        self.logger.info("Procesamiento LLM completado", **extra_data)
    
    def log_notion_sync(
        self, 
        class_id: str, 
        page_id: str,
        blocks_created: int,
        relations_created: int
    ) -> None:
        """Log sincronización con Notion."""
        self.logger.info(
            "Sincronización Notion completada",
            class_id=class_id,
            notion_page_id=page_id,
            blocks_created=blocks_created,
            relations_created=relations_created,
            operation="notion_sync"
        )
    
    def log_error(
        self, 
        operation: str, 
        error_msg: str,
        class_id: Optional[str] = None,
        **kwargs
    ) -> None:
        """Log error con contexto médico."""
        error_data = {
            "operation": operation,
            "error_message": error_msg,
            **kwargs
        }
        
        if class_id:
            error_data["class_id"] = class_id
        
        self.logger.error("Error en operación", **error_data)


# Loggers específicos por contexto
transcription_logger = ContextLogger("transcription")
diarization_logger = ContextLogger("diarization")
llm_logger = ContextLogger("llm")
notion_logger = ContextLogger("notion")
api_logger = ContextLogger("api")
celery_logger = ContextLogger("celery")
