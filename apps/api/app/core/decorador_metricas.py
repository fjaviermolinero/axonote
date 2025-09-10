# -*- coding: utf-8 -*-
"""
Decorador para recolección automática de métricas en funciones y métodos.
"""

from functools import wraps
from datetime import datetime, timezone
from typing import Callable, Any, Optional, Dict
import asyncio
import inspect

from app.core.logging import logger


def recopilar_metricas(
    tipo_metrica: str,
    nombre_componente: str,
    rastrear_calidad: bool = False,
    sesion_metrica_personalizada: Optional[str] = None
):
    """
    Decorador para recolección automática de métricas de rendimiento.
    
    Args:
        tipo_metrica: Tipo de procesamiento (asr, diarizacion, llm, ocr, tts)
        nombre_componente: Nombre específico del componente
        rastrear_calidad: Si debe extraer métricas de calidad del resultado
        sesion_metrica_personalizada: ID de sesión personalizada (opcional)
    
    Usage:
        @recopilar_metricas("asr", "whisper_large_v3", rastrear_calidad=True)
        async def transcribir_audio(ruta_audio: str) -> ResultadoTranscripcion:
            # Lógica de transcripción
            return resultado
    """
    
    def decorador(func: Callable) -> Callable:
        
        @wraps(func)
        async def wrapper_async(*args, **kwargs) -> Any:
            return await _ejecutar_con_metricas(
                func, args, kwargs, tipo_metrica, nombre_componente, 
                rastrear_calidad, sesion_metrica_personalizada
            )
        
        @wraps(func)
        def wrapper_sync(*args, **kwargs) -> Any:
            return asyncio.run(_ejecutar_con_metricas(
                func, args, kwargs, tipo_metrica, nombre_componente, 
                rastrear_calidad, sesion_metrica_personalizada
            ))
        
        # Retornar wrapper apropiado según si la función es async o sync
        if asyncio.iscoroutinefunction(func):
            return wrapper_async
        else:
            return wrapper_sync
    
    return decorador


async def _ejecutar_con_metricas(
    func: Callable,
    args: tuple,
    kwargs: dict,
    tipo_metrica: str,
    nombre_componente: str,
    rastrear_calidad: bool,
    sesion_personalizada: Optional[str]
) -> Any:
    """Ejecuta la función y recopila métricas automáticamente."""
    
    tiempo_inicio = datetime.now(timezone.utc)
    detalles_error = None
    resultado = None
    
    # Obtener servicio de métricas (dependency injection)
    servicio_metricas = _obtener_servicio_metricas()
    
    try:
        # Ejecutar función original
        if asyncio.iscoroutinefunction(func):
            resultado = await func(*args, **kwargs)
        else:
            resultado = func(*args, **kwargs)
        
        return resultado
        
    except Exception as e:
        detalles_error = str(e)
        logger.error(f"Error en {nombre_componente}: {detalles_error}")
        raise
        
    finally:
        tiempo_fin = datetime.now(timezone.utc)
        
        # Extraer métricas de calidad del resultado si está habilitado
        puntuacion_calidad = None
        puntuacion_confianza = None
        tamano_entrada = None
        tamano_salida = None
        metadatos_adicionales = {}
        
        if rastrear_calidad and resultado:
            if hasattr(resultado, 'metricas_calidad'):
                metricas_calidad = resultado.metricas_calidad
                puntuacion_calidad = metricas_calidad.get('puntuacion_calidad')
                puntuacion_confianza = metricas_calidad.get('puntuacion_confianza')
            
            if hasattr(resultado, 'confidence_score'):
                puntuacion_confianza = resultado.confidence_score
            
            if hasattr(resultado, 'quality_score'):
                puntuacion_calidad = resultado.quality_score
        
        # Extraer información sobre tamaños de datos
        if args:
            primer_arg = args[0]
            if isinstance(primer_arg, str) and 'audio' in nombre_componente.lower():
                # Intentar obtener tamaño del archivo de audio
                try:
                    import os
                    if os.path.exists(primer_arg):
                        tamano_entrada = os.path.getsize(primer_arg)
                except:
                    pass
        
        # Metadatos sobre la función
        metadatos_adicionales.update({
            "nombre_funcion": func.__name__,
            "cantidad_args": len(args),
            "cantidad_kwargs": len(kwargs),
            "modulo": func.__module__ if hasattr(func, '__module__') else None
        })
        
        # Registrar métrica de procesamiento
        if servicio_metricas:
            try:
                await _registrar_metrica_async(
                    servicio_metricas,
                    tipo_metrica=tipo_metrica,
                    nombre_componente=nombre_componente,
                    tiempo_inicio=tiempo_inicio,
                    tiempo_fin=tiempo_fin,
                    puntuacion_calidad=puntuacion_calidad,
                    puntuacion_confianza=puntuacion_confianza,
                    tamano_entrada_bytes=tamano_entrada,
                    tamano_salida_bytes=tamano_salida,
                    metadatos=metadatos_adicionales,
                    detalles_error=detalles_error,
                    sesion_personalizada=sesion_personalizada
                )
            except Exception as e:
                logger.warning(f"Error registrando métrica para {nombre_componente}: {str(e)}")


async def _registrar_metrica_async(
    servicio_metricas,
    tipo_metrica: str,
    nombre_componente: str,
    tiempo_inicio: datetime,
    tiempo_fin: datetime,
    puntuacion_calidad: Optional[float],
    puntuacion_confianza: Optional[float],
    tamano_entrada_bytes: Optional[int],
    tamano_salida_bytes: Optional[int],
    metadatos: Dict,
    detalles_error: Optional[str],
    sesion_personalizada: Optional[str]
):
    """Registra la métrica de forma asíncrona."""
    try:
        # Convertir sesion_personalizada a UUID si se proporciona
        id_sesion = None
        if sesion_personalizada:
            import uuid
            id_sesion = uuid.UUID(sesion_personalizada)
        
        metrica_id = servicio_metricas.registrar_metrica_procesamiento(
            tipo_metrica=tipo_metrica,
            nombre_componente=nombre_componente,
            tiempo_inicio=tiempo_inicio,
            tiempo_fin=tiempo_fin,
            puntuacion_calidad=puntuacion_calidad,
            puntuacion_confianza=puntuacion_confianza,
            tamano_entrada_bytes=tamano_entrada_bytes,
            tamano_salida_bytes=tamano_salida_bytes,
            metadatos=metadatos,
            detalles_error=detalles_error,
            id_sesion=id_sesion
        )
        
        logger.debug(f"Métrica registrada exitosamente: {metrica_id}")
        
    except Exception as e:
        logger.warning(f"Error al registrar métrica: {str(e)}")


def _obtener_servicio_metricas():
    """
    Obtiene una instancia del servicio de métricas.
    
    Esta función debe ser implementada según el patrón de dependency injection
    usado en el proyecto. Por ahora retorna None para evitar errores.
    """
    try:
        # TODO: Implementar dependency injection real
        # from app.services.servicio_recoleccion_metricas import ServicioRecoleccionMetricas
        # from app.core.database import get_db
        # db = next(get_db())
        # return ServicioRecoleccionMetricas(db)
        return None
    except Exception as e:
        logger.warning(f"No se pudo obtener servicio de métricas: {str(e)}")
        return None


# Decoradores específicos para cada tipo de procesamiento
def metricas_asr(nombre_modelo: str = "whisper", rastrear_calidad: bool = True):
    """Decorador específico para ASR."""
    return recopilar_metricas("asr", nombre_modelo, rastrear_calidad)


def metricas_diarizacion(nombre_modelo: str = "pyannote", rastrear_calidad: bool = True):
    """Decorador específico para diarización."""
    return recopilar_metricas("diarizacion", nombre_modelo, rastrear_calidad)


def metricas_llm(nombre_modelo: str = "qwen2.5", rastrear_calidad: bool = True):
    """Decorador específico para LLM."""
    return recopilar_metricas("llm", nombre_modelo, rastrear_calidad)


def metricas_ocr(nombre_motor: str = "tesseract", rastrear_calidad: bool = True):
    """Decorador específico para OCR."""
    return recopilar_metricas("ocr", nombre_motor, rastrear_calidad)


def metricas_tts(nombre_motor: str = "piper", rastrear_calidad: bool = True):
    """Decorador específico para TTS."""
    return recopilar_metricas("tts", nombre_motor, rastrear_calidad)


# Context manager para métricas manuales
class ContextoMetricas:
    """Context manager para recolección manual de métricas."""
    
    def __init__(
        self,
        tipo_metrica: str,
        nombre_componente: str,
        servicio_metricas=None,
        id_sesion: Optional[str] = None
    ):
        self.tipo_metrica = tipo_metrica
        self.nombre_componente = nombre_componente
        self.servicio_metricas = servicio_metricas or _obtener_servicio_metricas()
        self.id_sesion = id_sesion
        self.tiempo_inicio = None
        self.metrica_id = None
    
    def __enter__(self):
        self.tiempo_inicio = datetime.now(timezone.utc)
        logger.debug(f"Iniciando métricas para {self.nombre_componente}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        tiempo_fin = datetime.now(timezone.utc)
        detalles_error = str(exc_val) if exc_val else None
        
        if self.servicio_metricas and self.tiempo_inicio:
            try:
                self.metrica_id = self.servicio_metricas.registrar_metrica_procesamiento(
                    tipo_metrica=self.tipo_metrica,
                    nombre_componente=self.nombre_componente,
                    tiempo_inicio=self.tiempo_inicio,
                    tiempo_fin=tiempo_fin,
                    detalles_error=detalles_error,
                    id_sesion=self.id_sesion
                )
                logger.debug(f"Métrica registrada: {self.metrica_id}")
            except Exception as e:
                logger.warning(f"Error registrando métrica en context manager: {str(e)}")
    
    def anadir_metrica_calidad(
        self,
        puntuacion_calidad: float,
        puntuacion_confianza: Optional[float] = None
    ):
        """Añade métricas de calidad durante la ejecución."""
        if self.servicio_metricas:
            try:
                self.servicio_metricas.registrar_metrica_calidad(
                    puntuacion_calidad=puntuacion_calidad,
                    confianza_promedio=puntuacion_confianza,
                    id_sesion=self.id_sesion
                )
            except Exception as e:
                logger.warning(f"Error añadiendo métrica de calidad: {str(e)}")


# Ejemplos de uso:
"""
# Ejemplo 1: Decorador automático
@metricas_asr("whisper_large_v3", rastrear_calidad=True)
async def transcribir_audio(ruta_audio: str) -> ResultadoTranscripcion:
    # Lógica de transcripción
    resultado = whisper.transcribe(ruta_audio)
    resultado.quality_score = 0.95  # Será capturado automáticamente
    return resultado

# Ejemplo 2: Context manager manual
async def procesar_con_metricas():
    with ContextoMetricas("llm", "qwen2.5_14b") as ctx:
        respuesta = await llamar_llm(prompt)
        ctx.anadir_metrica_calidad(0.92, 0.88)
        return respuesta

# Ejemplo 3: En tasks de Celery
@celery_app.task
@metricas_asr("whisper_large_v3")
def task_transcripcion(upload_session_id: str):
    return procesar_transcripcion(upload_session_id)
"""
