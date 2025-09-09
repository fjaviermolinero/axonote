"""
Servicio de diarización de speakers con pyannote-audio.
Separa voces de profesor y alumnos en clases médicas con clustering inteligente.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import torch
from pydantic import BaseModel

from app.core import api_logger, settings
from app.services.base import BaseService, ServiceNotAvailableError


class SegmentoDiarizacion(BaseModel):
    """Segmento individual de diarización."""
    start: float
    end: float
    speaker_id: str
    confidence: float
    duration: float


class SpeakerInfo(BaseModel):
    """Información de un speaker identificado."""
    speaker_id: str
    tipo_speaker: str  # "profesor", "alumno_1", "alumno_2", etc.
    tiempo_total_habla_sec: float
    num_segmentos: int
    confianza_clasificacion: float
    embedding_promedio: Optional[List[float]] = None


class AnalisisParticipacion(BaseModel):
    """Análisis de participación en la clase."""
    speaker_principal: str  # Probablemente el profesor
    porcentaje_habla_profesor: float
    porcentaje_habla_alumnos: float
    turnos_de_palabra: int
    interrupciones_detectadas: int
    momentos_silencio_sec: float


class ResultadoDiarizacion(BaseModel):
    """Resultado completo de diarización."""
    num_speakers_detectados: int
    speakers_info: List[SpeakerInfo]
    segmentos_diarizacion: List[SegmentoDiarizacion]
    analisis_participacion: AnalisisParticipacion
    calidad_separacion: float  # Métrica de calidad 0-1
    tiempo_procesamiento_sec: float
    configuracion_usada: Dict[str, Any]
    embeddings_speakers: Dict[str, List[float]]  # Para re-identificación


class ConfiguracionDiarizacion(BaseModel):
    """Configuración para pipeline de diarización."""
    min_speakers: int = 1
    max_speakers: int = 6
    threshold_clustering: float = 0.6
    min_segment_duration: float = 0.25
    max_speaker_duration: float = 30.0
    usar_vad: bool = True
    optimizar_para_educacion: bool = True


class DiarizationService(BaseService):
    """
    Servicio de diarización con pyannote-audio v3.1.
    Optimizado para separación de speakers en clases médicas.
    """

    def __init__(self):
        super().__init__()
        self.pipeline_diarizacion = None
        self.embedding_model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.modelo_cargado = False
        
        # Configuraciones predefinidas
        self.configuraciones = self._get_configuraciones_diarizacion()
        
        # Estadísticas de rendimiento
        self.estadisticas = {
            "diarizaciones_completadas": 0,
            "tiempo_total_procesamiento": 0.0,
            "tiempo_promedio_por_minuto": 0.0,
            "speakers_detectados_total": 0,
            "accuracy_clasificacion_estimada": 0.0
        }

    def _get_configuraciones_diarizacion(self) -> Dict[str, ConfiguracionDiarizacion]:
        """Configuraciones optimizadas para diferentes tipos de clases médicas."""
        return {
            "MEDICAL_CLASS_STANDARD": ConfiguracionDiarizacion(
                min_speakers=1,
                max_speakers=6,  # 1 profesor + hasta 5 alumnos
                threshold_clustering=0.6,
                min_segment_duration=0.25,
                max_speaker_duration=30.0,
                usar_vad=True,
                optimizar_para_educacion=True
            ),
            
            "MEDICAL_SMALL_GROUP": ConfiguracionDiarizacion(
                min_speakers=1,
                max_speakers=3,  # Sesiones pequeñas
                threshold_clustering=0.55,  # Más sensible
                min_segment_duration=0.2,
                max_speaker_duration=60.0,  # Más tiempo por turn
                usar_vad=True,
                optimizar_para_educacion=True
            ),
            
            "MEDICAL_LARGE_LECTURE": ConfiguracionDiarizacion(
                min_speakers=1,
                max_speakers=10,  # Clases grandes
                threshold_clustering=0.65,  # Menos sensible para evitar over-segmentation
                min_segment_duration=0.3,
                max_speaker_duration=15.0,  # Turnos más cortos
                usar_vad=True,
                optimizar_para_educacion=True
            ),
            
            "MEDICAL_INTERVIEW": ConfiguracionDiarizacion(
                min_speakers=2,
                max_speakers=2,  # Solo entrevistador/entrevistado
                threshold_clustering=0.5,
                min_segment_duration=0.5,
                max_speaker_duration=120.0,  # Respuestas largas permitidas
                usar_vad=True,
                optimizar_para_educacion=False
            )
        }

    async def _setup(self) -> None:
        """Configurar el servicio y cargar modelos."""
        try:
            await self._verificar_dependencias()
            await self._cargar_modelos_diarizacion()
            self.modelo_cargado = True
            
            self.logger.info(
                "DiarizationService configurado exitosamente",
                device=str(self.device),
                hf_token_disponible=bool(settings.HF_TOKEN)
            )
        except Exception as e:
            self.logger.error("Error configurando DiarizationService", error=str(e))
            raise ServiceNotAvailableError(f"DiarizationService no disponible: {e}")

    async def _verificar_dependencias(self) -> None:
        """Verificar que todas las dependencias estén disponibles."""
        try:
            import pyannote.audio
            from pyannote.audio import Pipeline
            from pyannote.audio.pipelines.speaker_diarization import SpeakerDiarization
        except ImportError as e:
            raise ServiceNotAvailableError(f"pyannote-audio no instalado: {e}")
        
        if not settings.HF_TOKEN:
            raise ServiceNotAvailableError(
                "HF_TOKEN requerido para pyannote-audio. "
                "Obtén token en https://huggingface.co/settings/tokens"
            )
        
        # Verificar GPU si está disponible
        if self.device.type == "cuda":
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            self.logger.info(
                "GPU detectada para diarización",
                gpu_name=torch.cuda.get_device_name(0),
                gpu_memory_gb=round(gpu_memory, 1)
            )

    async def _cargar_modelos_diarizacion(self) -> None:
        """Cargar pipeline de diarización de pyannote."""
        try:
            from pyannote.audio import Pipeline
            
            self.logger.info("Cargando pipeline de diarización pyannote")
            
            # Cargar pipeline pre-entrenado
            self.pipeline_diarizacion = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=settings.HF_TOKEN
            )
            
            # Mover a GPU si está disponible
            if self.device.type == "cuda":
                self.pipeline_diarizacion = self.pipeline_diarizacion.to(self.device)
            
            self.logger.info("Pipeline de diarización cargado exitosamente")
            
        except Exception as e:
            self.logger.error("Error cargando pipeline de diarización", error=str(e))
            raise

    async def diarizar_audio(
        self,
        ruta_audio: str,
        configuracion: str = "MEDICAL_CLASS_STANDARD",
        num_speakers: Optional[int] = None,
        progress_callback: Optional[callable] = None
    ) -> ResultadoDiarizacion:
        """
        Realizar diarización de speakers en archivo de audio.
        
        Args:
            ruta_audio: Ruta al archivo de audio
            configuracion: Nombre de configuración predefinida
            num_speakers: Número exacto de speakers si se conoce
            progress_callback: Función para reportar progreso
            
        Returns:
            ResultadoDiarizacion con speakers identificados y análisis
        """
        if not self.modelo_cargado:
            await self._setup()
        
        inicio_tiempo = time.time()
        config = self.configuraciones[configuracion]
        
        try:
            self.logger.info(
                "Iniciando diarización",
                ruta_audio=ruta_audio,
                configuracion=configuracion,
                num_speakers=num_speakers
            )
            
            if progress_callback:
                await progress_callback({"stage": "inicio", "progress": 0.0})
            
            # Configurar pipeline con parámetros específicos
            await self._configurar_pipeline(config, num_speakers)
            
            if progress_callback:
                await progress_callback({"stage": "configuracion_completada", "progress": 10.0})
            
            # Ejecutar diarización
            self.logger.info("Ejecutando diarización con pyannote")
            diarizacion_raw = self.pipeline_diarizacion(ruta_audio)
            
            if progress_callback:
                await progress_callback({"stage": "diarizacion_completada", "progress": 60.0})
            
            # Procesar resultados
            segmentos_procesados = await self._procesar_segmentos_diarizacion(diarizacion_raw)
            
            if progress_callback:
                await progress_callback({"stage": "procesamiento_segmentos", "progress": 75.0})
            
            # Extraer embeddings de speakers
            embeddings_speakers = await self._extraer_embeddings_speakers(
                ruta_audio, segmentos_procesados
            )
            
            # Clasificar speakers en roles médicos
            speakers_info = await self._clasificar_speakers_medicos(
                segmentos_procesados, 
                embeddings_speakers,
                config
            )
            
            if progress_callback:
                await progress_callback({"stage": "clasificacion_completada", "progress": 90.0})
            
            # Análisis de participación
            analisis_participacion = await self._analizar_participacion(
                segmentos_procesados, speakers_info
            )
            
            # Calcular métricas de calidad
            calidad_separacion = await self._calcular_calidad_separacion(
                segmentos_procesados, embeddings_speakers
            )
            
            tiempo_procesamiento = time.time() - inicio_tiempo
            
            # Crear resultado
            resultado = ResultadoDiarizacion(
                num_speakers_detectados=len(speakers_info),
                speakers_info=speakers_info,
                segmentos_diarizacion=segmentos_procesados,
                analisis_participacion=analisis_participacion,
                calidad_separacion=calidad_separacion,
                tiempo_procesamiento_sec=tiempo_procesamiento,
                configuracion_usada=config.dict(),
                embeddings_speakers=embeddings_speakers
            )
            
            # Actualizar estadísticas
            self._actualizar_estadisticas(resultado)
            
            if progress_callback:
                await progress_callback({"stage": "completado", "progress": 100.0})
            
            self.logger.info(
                "Diarización completada exitosamente",
                num_speakers=len(speakers_info),
                tiempo_procesamiento=tiempo_procesamiento,
                calidad_separacion=calidad_separacion
            )
            
            return resultado
            
        except Exception as e:
            self.logger.error(
                "Error en diarización",
                ruta_audio=ruta_audio,
                configuracion=configuracion,
                error=str(e),
                tiempo_transcurrido=time.time() - inicio_tiempo
            )
            raise

    async def _configurar_pipeline(
        self, 
        config: ConfiguracionDiarizacion, 
        num_speakers: Optional[int]
    ) -> None:
        """Configurar parámetros del pipeline de diarización."""
        try:
            # Configurar clustering
            if num_speakers:
                # Número exacto de speakers conocido
                self.pipeline_diarizacion.instantiate({
                    "clustering": {
                        "method": "centroid",
                        "min_cluster_size": max(1, num_speakers // 4),
                        "threshold": config.threshold_clustering,
                        "constraint": "num_clusters",
                        "num_clusters": num_speakers
                    }
                })
            else:
                # Clustering adaptativo
                self.pipeline_diarizacion.instantiate({
                    "clustering": {
                        "method": "centroid", 
                        "min_cluster_size": 5,
                        "threshold": config.threshold_clustering,
                        "constraint": "min_max_clusters",
                        "min_clusters": config.min_speakers,
                        "max_clusters": config.max_speakers
                    }
                })
            
            # Configurar segmentación
            self.pipeline_diarizacion.instantiate({
                "segmentation": {
                    "min_duration_off": config.min_segment_duration,
                    "min_duration_on": config.min_segment_duration * 2
                }
            })
            
            self.logger.info("Pipeline configurado", config=config.dict())
            
        except Exception as e:
            self.logger.error("Error configurando pipeline", error=str(e))
            raise

    async def _procesar_segmentos_diarizacion(self, diarizacion_raw) -> List[SegmentoDiarizacion]:
        """Procesar segmentos brutos de diarización."""
        segmentos = []
        
        for segmento, _, speaker_id in diarizacion_raw.itertracks(yield_label=True):
            segmento_obj = SegmentoDiarizacion(
                start=float(segmento.start),
                end=float(segmento.end),
                speaker_id=str(speaker_id),
                confidence=1.0,  # pyannote no proporciona confidence por segmento
                duration=float(segmento.end - segmento.start)
            )
            segmentos.append(segmento_obj)
        
        # Ordenar por tiempo de inicio
        segmentos.sort(key=lambda x: x.start)
        
        self.logger.info(
            "Segmentos procesados",
            num_segmentos=len(segmentos),
            speakers_unicos=len(set(s.speaker_id for s in segmentos))
        )
        
        return segmentos

    async def _extraer_embeddings_speakers(
        self, 
        ruta_audio: str, 
        segmentos: List[SegmentoDiarizacion]
    ) -> Dict[str, List[float]]:
        """Extraer embeddings promedio para cada speaker."""
        try:
            from pyannote.audio import Model
            from pyannote.audio.core.inference import Inference
            import soundfile as sf
            
            # Cargar modelo de embeddings
            if not self.embedding_model:
                self.embedding_model = Model.from_pretrained(
                    "pyannote/embedding",
                    use_auth_token=settings.HF_TOKEN
                )
                if self.device.type == "cuda":
                    self.embedding_model = self.embedding_model.to(self.device)
            
            # Cargar audio
            audio, sample_rate = sf.read(ruta_audio)
            if len(audio.shape) > 1:
                audio = audio.mean(axis=1)  # Convertir a mono
            
            embeddings_speakers = {}
            
            # Agrupar segmentos por speaker
            segmentos_por_speaker = {}
            for segmento in segmentos:
                if segmento.speaker_id not in segmentos_por_speaker:
                    segmentos_por_speaker[segmento.speaker_id] = []
                segmentos_por_speaker[segmento.speaker_id].append(segmento)
            
            # Extraer embeddings para cada speaker
            inference = Inference(self.embedding_model, window="whole")
            
            for speaker_id, speaker_segmentos in segmentos_por_speaker.items():
                embeddings_segmentos = []
                
                for segmento in speaker_segmentos[:10]:  # Limitar a 10 segmentos por speaker
                    try:
                        start_sample = int(segmento.start * sample_rate)
                        end_sample = int(segmento.end * sample_rate)
                        
                        # Extraer segmento de audio
                        audio_segmento = audio[start_sample:end_sample]
                        
                        if len(audio_segmento) > sample_rate * 0.5:  # Mínimo 0.5 segundos
                            # Obtener embedding
                            embedding = inference({"audio": audio_segmento, "sample_rate": sample_rate})
                            embeddings_segmentos.append(embedding)
                            
                    except Exception as e:
                        self.logger.warning(f"Error extrayendo embedding para segmento: {e}")
                        continue
                
                # Promedio de embeddings
                if embeddings_segmentos:
                    embedding_promedio = np.mean(embeddings_segmentos, axis=0)
                    embeddings_speakers[speaker_id] = embedding_promedio.tolist()
                else:
                    # Embedding dummy si no se pudo extraer
                    embeddings_speakers[speaker_id] = [0.0] * 512
            
            self.logger.info(
                "Embeddings extraídos",
                num_speakers=len(embeddings_speakers),
                embedding_dimension=len(next(iter(embeddings_speakers.values())))
            )
            
            return embeddings_speakers
            
        except Exception as e:
            self.logger.error("Error extrayendo embeddings", error=str(e))
            # Retornar embeddings dummy
            speakers_unicos = list(set(s.speaker_id for s in segmentos))
            return {speaker_id: [0.0] * 512 for speaker_id in speakers_unicos}

    async def _clasificar_speakers_medicos(
        self,
        segmentos: List[SegmentoDiarizacion],
        embeddings: Dict[str, List[float]],
        config: ConfiguracionDiarizacion
    ) -> List[SpeakerInfo]:
        """Clasificar speakers en roles médicos (profesor, alumnos)."""
        speakers_info = []
        
        # Calcular estadísticas por speaker
        stats_speakers = {}
        for segmento in segmentos:
            speaker_id = segmento.speaker_id
            if speaker_id not in stats_speakers:
                stats_speakers[speaker_id] = {
                    "tiempo_total": 0.0,
                    "num_segmentos": 0,
                    "segmentos": []
                }
            
            stats_speakers[speaker_id]["tiempo_total"] += segmento.duration
            stats_speakers[speaker_id]["num_segmentos"] += 1
            stats_speakers[speaker_id]["segmentos"].append(segmento)
        
        # Ordenar speakers por tiempo de habla (descendente)
        speakers_ordenados = sorted(
            stats_speakers.items(),
            key=lambda x: x[1]["tiempo_total"],
            reverse=True
        )
        
        # Clasificación heurística para contexto educativo
        for i, (speaker_id, stats) in enumerate(speakers_ordenados):
            if config.optimizar_para_educacion and i == 0:
                # El speaker con más tiempo de habla probablemente es el profesor
                tipo_speaker = "profesor"
                confianza = 0.8 + (stats["tiempo_total"] / sum(s[1]["tiempo_total"] for s in speakers_ordenados)) * 0.2
            else:
                # Los demás son alumnos
                tipo_speaker = f"alumno_{i}" if config.optimizar_para_educacion else f"speaker_{i+1}"
                confianza = 0.7
            
            speaker_info = SpeakerInfo(
                speaker_id=speaker_id,
                tipo_speaker=tipo_speaker,
                tiempo_total_habla_sec=stats["tiempo_total"],
                num_segmentos=stats["num_segmentos"],
                confianza_clasificacion=min(confianza, 1.0),
                embedding_promedio=embeddings.get(speaker_id, [])
            )
            speakers_info.append(speaker_info)
        
        self.logger.info(
            "Speakers clasificados",
            num_speakers=len(speakers_info),
            profesor_detectado=any(s.tipo_speaker == "profesor" for s in speakers_info)
        )
        
        return speakers_info

    async def _analizar_participacion(
        self,
        segmentos: List[SegmentoDiarizacion],
        speakers_info: List[SpeakerInfo]
    ) -> AnalisisParticipacion:
        """Analizar patrones de participación en la clase."""
        
        # Identificar profesor
        speaker_principal = None
        tiempo_profesor = 0.0
        tiempo_alumnos = 0.0
        
        for speaker in speakers_info:
            if speaker.tipo_speaker == "profesor":
                speaker_principal = speaker.speaker_id
                tiempo_profesor = speaker.tiempo_total_habla_sec
            else:
                tiempo_alumnos += speaker.tiempo_total_habla_sec
        
        # Si no hay profesor identificado, usar el speaker con más tiempo
        if not speaker_principal:
            speaker_principal = max(speakers_info, key=lambda x: x.tiempo_total_habla_sec).speaker_id
            tiempo_profesor = max(s.tiempo_total_habla_sec for s in speakers_info)
            tiempo_alumnos = sum(s.tiempo_total_habla_sec for s in speakers_info) - tiempo_profesor
        
        tiempo_total = tiempo_profesor + tiempo_alumnos
        
        # Calcular turnos de palabra
        turnos = 0
        speaker_anterior = None
        
        for segmento in segmentos:
            if speaker_anterior and speaker_anterior != segmento.speaker_id:
                turnos += 1
            speaker_anterior = segmento.speaker_id
        
        # Detectar interrupciones (solapamientos)
        interrupciones = 0
        for i in range(len(segmentos) - 1):
            if segmentos[i].end > segmentos[i + 1].start:
                interrupciones += 1
        
        # Calcular silencios
        tiempo_total_audio = segmentos[-1].end if segmentos else 0
        tiempo_total_habla = sum(s.duration for s in segmentos)
        momentos_silencio = tiempo_total_audio - tiempo_total_habla
        
        return AnalisisParticipacion(
            speaker_principal=speaker_principal,
            porcentaje_habla_profesor=(tiempo_profesor / tiempo_total * 100) if tiempo_total > 0 else 0,
            porcentaje_habla_alumnos=(tiempo_alumnos / tiempo_total * 100) if tiempo_total > 0 else 0,
            turnos_de_palabra=turnos,
            interrupciones_detectadas=interrupciones,
            momentos_silencio_sec=max(0, momentos_silencio)
        )

    async def _calcular_calidad_separacion(
        self,
        segmentos: List[SegmentoDiarizacion],
        embeddings: Dict[str, List[float]]
    ) -> float:
        """Calcular métrica de calidad de separación de speakers."""
        try:
            if len(embeddings) < 2:
                return 1.0  # Perfecto si solo hay un speaker
            
            # Calcular distancias entre embeddings de speakers
            speakers_ids = list(embeddings.keys())
            distancias = []
            
            for i in range(len(speakers_ids)):
                for j in range(i + 1, len(speakers_ids)):
                    emb1 = np.array(embeddings[speakers_ids[i]])
                    emb2 = np.array(embeddings[speakers_ids[j]])
                    
                    # Distancia coseno
                    if np.linalg.norm(emb1) > 0 and np.linalg.norm(emb2) > 0:
                        cosine_dist = 1 - np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
                        distancias.append(cosine_dist)
            
            # Calidad basada en separación promedio
            if distancias:
                separacion_promedio = np.mean(distancias)
                calidad = min(1.0, separacion_promedio * 2)  # Escalar a 0-1
            else:
                calidad = 0.5  # Valor neutro si no se puede calcular
            
            return float(calidad)
            
        except Exception as e:
            self.logger.warning("Error calculando calidad de separación", error=str(e))
            return 0.5

    def _actualizar_estadisticas(self, resultado: ResultadoDiarizacion) -> None:
        """Actualizar estadísticas de rendimiento."""
        self.estadisticas["diarizaciones_completadas"] += 1
        self.estadisticas["tiempo_total_procesamiento"] += resultado.tiempo_procesamiento_sec
        self.estadisticas["speakers_detectados_total"] += resultado.num_speakers_detectados
        
        # Actualizar promedio de tiempo por minuto (estimado basado en duración típica)
        duracion_estimada_min = 60  # Asumir 60 minutos promedio
        tiempo_por_minuto = resultado.tiempo_procesamiento_sec / duracion_estimada_min
        
        total_completadas = self.estadisticas["diarizaciones_completadas"]
        self.estadisticas["tiempo_promedio_por_minuto"] = (
            (self.estadisticas["tiempo_promedio_por_minuto"] * (total_completadas - 1) + tiempo_por_minuto)
            / total_completadas
        )
        
        # Actualizar accuracy estimada basada en calidad de separación
        self.estadisticas["accuracy_clasificacion_estimada"] = (
            (self.estadisticas["accuracy_clasificacion_estimada"] * (total_completadas - 1) + resultado.calidad_separacion)
            / total_completadas
        )

    async def health_check(self) -> Dict[str, Any]:
        """Verificar estado del servicio."""
        health = {
            "service": "DiarizationService",
            "status": "unknown",
            "modelo_cargado": self.modelo_cargado,
            "device": str(self.device),
            "hf_token_disponible": bool(settings.HF_TOKEN),
            "estadisticas": self.estadisticas.copy()
        }
        
        try:
            if self.modelo_cargado and self.pipeline_diarizacion:
                health["status"] = "healthy"
                health["pipeline_info"] = "Pipeline pyannote cargado y operativo"
                
                # Información adicional de GPU
                if self.device.type == "cuda":
                    health["gpu_memory_allocated_mb"] = torch.cuda.memory_allocated() / (1024**2)
                    health["gpu_memory_free_mb"] = (
                        torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated()
                    ) / (1024**2)
            else:
                health["status"] = "degraded"
                health["mensaje"] = "Pipeline no cargado"
                
        except Exception as e:
            health["status"] = "error"
            health["error"] = str(e)
        
        return health

    async def cleanup(self) -> None:
        """Limpiar recursos del servicio."""
        try:
            if self.device.type == "cuda":
                torch.cuda.empty_cache()
            
            self.pipeline_diarizacion = None
            self.embedding_model = None
            self.modelo_cargado = False
            
            self.logger.info("DiarizationService cleanup completado")
        except Exception as e:
            self.logger.error("Error en cleanup de DiarizationService", error=str(e))
        
        await super().cleanup()


# Instancia global del servicio
diarization_service = DiarizationService()
