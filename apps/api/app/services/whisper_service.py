"""
Servicio de ASR (Automatic Speech Recognition) con Whisper y WhisperX.
Optimizado para hardware RTX 4090 y procesamiento de clases médicas.
"""

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
from faster_whisper import WhisperModel
from pydantic import BaseModel

from app.core import api_logger, settings
from app.services.base import BaseService, ServiceNotAvailableError


class SegmentoTranscripcion(BaseModel):
    """Segmento individual de transcripción."""
    start: float
    end: float
    text: str
    confidence: float
    words: Optional[List[Dict[str, Any]]] = None


class ResultadoTranscripcion(BaseModel):
    """Resultado completo de transcripción."""
    texto_completo: str
    segmentos: List[SegmentoTranscripcion]
    idioma_detectado: str
    confianza_global: float
    duracion_audio_sec: float
    tiempo_procesamiento_sec: float
    num_palabras: int
    palabras_por_minuto: float
    modelo_usado: str
    configuracion_usada: Dict[str, Any]


class SegmentoVAD(BaseModel):
    """Segmento de Voice Activity Detection."""
    start: float
    end: float
    confidence: float


class CaracteristicasAudio(BaseModel):
    """Características detectadas del audio."""
    duracion_sec: float
    sample_rate: int
    canales: int
    formato: str
    bitrate: Optional[int]
    nivel_ruido_estimado: float
    idioma_probable: str
    calidad_estimada: str  # "high", "medium", "low"


class WhisperService(BaseService):
    """
    Servicio principal de ASR con Whisper/WhisperX.
    Optimizado para RTX 4090 y procesamiento de clases médicas italianas.
    """

    def __init__(self):
        super().__init__()
        self.modelo_whisper: Optional[WhisperModel] = None
        self.device: str = "cuda" if torch.cuda.is_available() else "cpu"
        self.compute_type: str = "float16" if self.device == "cuda" else "int8"
        self.modelo_size: str = settings.WHISPER_MODEL
        self.modelo_cargado: bool = False
        
        # Configuraciones predefinidas
        self.configuraciones = self._get_configuraciones_whisper()
        
        # Métricas de rendimiento
        self.estadisticas = {
            "transcripciones_completadas": 0,
            "tiempo_total_procesamiento": 0.0,
            "tiempo_promedio_por_minuto": 0.0,
            "memoria_gpu_maxima_mb": 0,
            "errores_count": 0
        }

    def _get_configuraciones_whisper(self) -> Dict[str, Dict[str, Any]]:
        """Configuraciones optimizadas para diferentes casos de uso médico."""
        return {
            "MEDICAL_HIGH_PRECISION": {
                "model_size": "large-v3",
                "compute_type": "float16",
                "language": "it",
                "task": "transcribe",
                "beam_size": 5,
                "best_of": 5,
                "patience": 1.0,
                "length_penalty": 1.0,
                "repetition_penalty": 1.01,
                "no_repeat_ngram_size": 0,
                "temperature": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
                "compression_ratio_threshold": 2.4,
                "log_prob_threshold": -1.0,
                "no_speech_threshold": 0.6,
                "condition_on_previous_text": True,
                "prompt_reset_on_temperature": 0.5,
                "initial_prompt": (
                    "Esta es una clase de medicina en italiano. "
                    "Incluye terminología médica, nombres de medicamentos "
                    "y conceptos clínicos especializados."
                ),
                "prefix": None,
                "suppress_blank": True,
                "suppress_tokens": [-1],
                "without_timestamps": False,
                "max_initial_timestamp": 1.0,
                "word_timestamps": True,
                "prepend_punctuations": "\"'"¿([{-",
                "append_punctuations": "\"'.。,，!！?？:：")]}、",
                "vad_filter": True,
                "vad_parameters": {
                    "threshold": 0.5,
                    "min_speech_duration_ms": 250,
                    "max_speech_duration_s": 30,
                    "min_silence_duration_ms": 100,
                    "window_size_samples": 1024,
                    "speech_pad_ms": 30
                }
            },
            
            "MEDICAL_BALANCED": {
                "model_size": "medium",
                "compute_type": "float16",
                "language": "it",
                "beam_size": 3,
                "temperature": [0.0, 0.2, 0.4],
                "initial_prompt": "Clase de medicina en italiano con terminología médica.",
                "word_timestamps": True,
                "vad_filter": True
            },
            
            "MEDICAL_FAST": {
                "model_size": "base",
                "compute_type": "int8_float16",
                "language": "it",
                "beam_size": 1,
                "temperature": [0.0],
                "word_timestamps": False,
                "vad_filter": True
            },
            
            "MULTILINGUAL_AUTO": {
                "model_size": "large-v3",
                "compute_type": "float16",
                "language": None,  # Auto-detect
                "task": "transcribe",
                "word_timestamps": True,
                "vad_filter": True
            }
        }

    async def _setup(self) -> None:
        """Configurar el servicio y cargar modelos."""
        try:
            await self._verificar_hardware()
            await self._cargar_modelo_whisper()
            self.modelo_cargado = True
            self.logger.info(
                "WhisperService configurado exitosamente",
                modelo=self.modelo_size,
                device=self.device,
                compute_type=self.compute_type
            )
        except Exception as e:
            self.logger.error("Error configurando WhisperService", error=str(e))
            raise ServiceNotAvailableError(f"WhisperService no disponible: {e}")

    async def _verificar_hardware(self) -> None:
        """Verificar capacidades de hardware."""
        if self.device == "cuda":
            if not torch.cuda.is_available():
                raise ServiceNotAvailableError("CUDA no disponible")
            
            gpu_memory = torch.cuda.get_device_properties(0).total_memory
            gpu_memory_gb = gpu_memory / (1024**3)
            
            self.logger.info(
                "Hardware CUDA detectado",
                gpu_name=torch.cuda.get_device_name(0),
                gpu_memory_gb=round(gpu_memory_gb, 1),
                cuda_version=torch.version.cuda
            )
            
            # Verificar memoria suficiente para modelo large-v3
            if self.modelo_size == "large-v3" and gpu_memory_gb < 8:
                self.logger.warning(
                    "Memoria GPU insuficiente para large-v3, usando medium",
                    gpu_memory_gb=gpu_memory_gb
                )
                self.modelo_size = "medium"

    async def _cargar_modelo_whisper(self) -> None:
        """Cargar modelo Whisper optimizado."""
        try:
            model_dir = Path("models/whisper")
            model_dir.mkdir(parents=True, exist_ok=True)
            
            self.logger.info(
                "Cargando modelo Whisper",
                modelo=self.modelo_size,
                device=self.device,
                compute_type=self.compute_type
            )
            
            # Configurar parámetros de carga
            model_kwargs = {
                "device": self.device,
                "compute_type": self.compute_type,
                "download_root": str(model_dir),
                "local_files_only": False
            }
            
            if self.device == "cuda":
                model_kwargs.update({
                    "device_index": 0,
                    "cpu_threads": 8,
                    "num_workers": 1
                })
            
            self.modelo_whisper = WhisperModel(
                self.modelo_size,
                **model_kwargs
            )
            
            # Test de carga exitosa
            info = self.modelo_whisper.get_model_info()
            self.logger.info(
                "Modelo Whisper cargado exitosamente",
                modelo_info=info
            )
            
        except Exception as e:
            self.logger.error("Error cargando modelo Whisper", error=str(e))
            raise

    async def transcribir_audio(
        self,
        ruta_audio: str,
        configuracion: str = "MEDICAL_HIGH_PRECISION",
        idioma: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> ResultadoTranscripcion:
        """
        Transcribir archivo de audio con configuración optimizada.
        
        Args:
            ruta_audio: Ruta al archivo de audio
            configuracion: Nombre de configuración predefinida
            idioma: Código de idioma (it, en, es) o None para auto-detect
            progress_callback: Función para reportar progreso
            
        Returns:
            ResultadoTranscripcion con transcripción completa y metadatos
        """
        if not self.modelo_cargado:
            await self._setup()
        
        inicio_tiempo = time.time()
        
        try:
            # Obtener configuración
            config = self.configuraciones.get(configuracion, self.configuraciones["MEDICAL_HIGH_PRECISION"])
            if idioma:
                config = config.copy()
                config["language"] = idioma
            
            self.logger.info(
                "Iniciando transcripción",
                ruta_audio=ruta_audio,
                configuracion=configuracion,
                idioma=config.get("language", "auto")
            )
            
            # Verificar archivo de audio
            if not os.path.exists(ruta_audio):
                raise FileNotFoundError(f"Archivo de audio no encontrado: {ruta_audio}")
            
            # Reportar progreso inicial
            if progress_callback:
                await progress_callback({"stage": "inicio", "progress": 0.0})
            
            # Análizar características del audio
            caracteristicas = await self._analizar_audio(ruta_audio)
            
            if progress_callback:
                await progress_callback({"stage": "analisis_completado", "progress": 10.0})
            
            # Transcribir con Whisper
            segmentos, info_transcripcion = self.modelo_whisper.transcribe(
                ruta_audio,
                **{k: v for k, v in config.items() if k != "vad_parameters"}
            )
            
            if progress_callback:
                await progress_callback({"stage": "transcripcion_completada", "progress": 80.0})
            
            # Procesar segmentos
            lista_segmentos = []
            texto_completo_partes = []
            
            for segmento in segmentos:
                segmento_obj = SegmentoTranscripcion(
                    start=segmento.start,
                    end=segmento.end,
                    text=segmento.text.strip(),
                    confidence=getattr(segmento, 'avg_logprob', 0.0),
                    words=[
                        {
                            "word": word.word,
                            "start": word.start,
                            "end": word.end,
                            "probability": word.probability
                        }
                        for word in getattr(segmento, 'words', [])
                    ] if config.get("word_timestamps", False) else None
                )
                lista_segmentos.append(segmento_obj)
                texto_completo_partes.append(segmento.text.strip())
            
            # Construir texto completo
            texto_completo = " ".join(texto_completo_partes).strip()
            
            # Calcular métricas
            tiempo_procesamiento = time.time() - inicio_tiempo
            num_palabras = len(texto_completo.split())
            palabras_por_minuto = (num_palabras / caracteristicas.duracion_sec * 60) if caracteristicas.duracion_sec > 0 else 0
            confianza_global = np.mean([s.confidence for s in lista_segmentos]) if lista_segmentos else 0.0
            
            # Crear resultado
            resultado = ResultadoTranscripcion(
                texto_completo=texto_completo,
                segmentos=lista_segmentos,
                idioma_detectado=info_transcripcion.language,
                confianza_global=float(confianza_global),
                duracion_audio_sec=caracteristicas.duracion_sec,
                tiempo_procesamiento_sec=tiempo_procesamiento,
                num_palabras=num_palabras,
                palabras_por_minuto=palabras_por_minuto,
                modelo_usado=f"{self.modelo_size}-{self.compute_type}",
                configuracion_usada=config
            )
            
            # Actualizar estadísticas
            self._actualizar_estadisticas(resultado, tiempo_procesamiento)
            
            if progress_callback:
                await progress_callback({"stage": "completado", "progress": 100.0})
            
            self.logger.info(
                "Transcripción completada exitosamente",
                duracion_audio=caracteristicas.duracion_sec,
                tiempo_procesamiento=tiempo_procesamiento,
                num_palabras=num_palabras,
                confianza_global=confianza_global,
                idioma_detectado=info_transcripcion.language
            )
            
            return resultado
            
        except Exception as e:
            self.estadisticas["errores_count"] += 1
            self.logger.error(
                "Error en transcripción",
                ruta_audio=ruta_audio,
                configuracion=configuracion,
                error=str(e),
                tiempo_transcurrido=time.time() - inicio_tiempo
            )
            raise

    async def _analizar_audio(self, ruta_audio: str) -> CaracteristicasAudio:
        """Analizar características del archivo de audio."""
        try:
            import soundfile as sf
            import librosa
            
            # Cargar información básica
            info = sf.info(ruta_audio)
            
            # Cargar audio para análisis
            audio, sr = librosa.load(ruta_audio, sr=None, mono=True)
            
            # Calcular métricas básicas
            duracion = len(audio) / sr
            nivel_ruido = float(np.std(audio))
            
            # Estimar calidad
            if nivel_ruido < 0.01:
                calidad = "high"
            elif nivel_ruido < 0.05:
                calidad = "medium"
            else:
                calidad = "low"
            
            return CaracteristicasAudio(
                duracion_sec=duracion,
                sample_rate=info.samplerate,
                canales=info.channels,
                formato=info.format,
                bitrate=None,  # No siempre disponible
                nivel_ruido_estimado=nivel_ruido,
                idioma_probable="it",  # Default para clases médicas
                calidad_estimada=calidad
            )
            
        except Exception as e:
            self.logger.warning(
                "Error analizando audio, usando valores por defecto",
                ruta_audio=ruta_audio,
                error=str(e)
            )
            
            # Valores por defecto
            return CaracteristicasAudio(
                duracion_sec=3600.0,  # 1 hora estimada
                sample_rate=16000,
                canales=1,
                formato="unknown",
                nivel_ruido_estimado=0.02,
                idioma_probable="it",
                calidad_estimada="medium"
            )

    def _actualizar_estadisticas(self, resultado: ResultadoTranscripcion, tiempo_procesamiento: float) -> None:
        """Actualizar estadísticas de rendimiento."""
        self.estadisticas["transcripciones_completadas"] += 1
        self.estadisticas["tiempo_total_procesamiento"] += tiempo_procesamiento
        
        if resultado.duracion_audio_sec > 0:
            tiempo_por_minuto = tiempo_procesamiento / (resultado.duracion_audio_sec / 60)
            total_transcripciones = self.estadisticas["transcripciones_completadas"]
            
            # Promedio móvil
            self.estadisticas["tiempo_promedio_por_minuto"] = (
                (self.estadisticas["tiempo_promedio_por_minuto"] * (total_transcripciones - 1) + tiempo_por_minuto)
                / total_transcripciones
            )
        
        # Memoria GPU si está disponible
        if self.device == "cuda":
            memoria_actual = torch.cuda.memory_allocated() / (1024**2)  # MB
            self.estadisticas["memoria_gpu_maxima_mb"] = max(
                self.estadisticas["memoria_gpu_maxima_mb"],
                memoria_actual
            )

    async def health_check(self) -> Dict[str, Any]:
        """Verificar estado del servicio."""
        health = {
            "service": "WhisperService",
            "status": "unknown",
            "modelo_cargado": self.modelo_cargado,
            "modelo_size": self.modelo_size,
            "device": self.device,
            "compute_type": self.compute_type,
            "estadisticas": self.estadisticas.copy()
        }
        
        try:
            if self.modelo_cargado and self.modelo_whisper:
                # Test básico de funcionalidad
                health["status"] = "healthy"
                health["modelo_info"] = "Modelo Whisper cargado y operativo"
                
                # Información de GPU si está disponible
                if self.device == "cuda":
                    health["gpu_memory_free_mb"] = torch.cuda.memory_reserved() / (1024**2)
                    health["gpu_memory_allocated_mb"] = torch.cuda.memory_allocated() / (1024**2)
            else:
                health["status"] = "degraded"
                health["mensaje"] = "Modelo no cargado"
                
        except Exception as e:
            health["status"] = "error"
            health["error"] = str(e)
        
        return health

    async def optimizar_memoria_gpu(self) -> Dict[str, Any]:
        """Limpiar memoria GPU y optimizar uso."""
        if self.device != "cuda":
            return {"status": "skip", "reason": "No usando CUDA"}
        
        memoria_antes = torch.cuda.memory_allocated() / (1024**2)
        
        # Limpiar cache
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        
        memoria_despues = torch.cuda.memory_allocated() / (1024**2)
        memoria_liberada = memoria_antes - memoria_despues
        
        resultado = {
            "status": "completed",
            "memoria_antes_mb": memoria_antes,
            "memoria_despues_mb": memoria_despues,
            "memoria_liberada_mb": memoria_liberada,
            "memoria_total_mb": torch.cuda.get_device_properties(0).total_memory / (1024**2)
        }
        
        self.logger.info("Optimización de memoria GPU completada", **resultado)
        return resultado

    async def cleanup(self) -> None:
        """Limpiar recursos del servicio."""
        try:
            if self.device == "cuda":
                await self.optimizar_memoria_gpu()
            
            self.modelo_whisper = None
            self.modelo_cargado = False
            
            self.logger.info("WhisperService cleanup completado")
        except Exception as e:
            self.logger.error("Error en cleanup de WhisperService", error=str(e))
        
        await super().cleanup()


# Instancia global del servicio
whisper_service = WhisperService()
