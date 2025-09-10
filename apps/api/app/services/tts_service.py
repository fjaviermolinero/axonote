"""
Servicio de síntesis de voz (TTS) para contenido médico.
Utiliza Piper TTS para generar audio de alta calidad desde micro-memos y otro contenido textual.
"""

import asyncio
import json
import logging
import os
import tempfile
import subprocess
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID, uuid4
import wave
import audioop

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    TTSResult, MicroMemo, MicroMemoCollection, ClassSession,
    ExportSession, MedicalTerminology
)
from app.services.base import BaseService, ServiceConfigurationError
from app.services.minio_service import minio_service

logger = logging.getLogger(__name__)


class ConfiguracionTTS:
    """Configuración para síntesis de voz."""
    
    def __init__(
        self,
        # Configuración básica
        voice_model: str = "it_riccardo_quality",
        language: str = "ita",
        speed_factor: float = 1.0,
        audio_quality: str = "medium",  # low, medium, high, studio
        
        # Configuración de audio
        audio_format: str = "mp3",
        bitrate_kbps: int = 128,
        sample_rate_hz: int = 22050,
        channels: int = 1,
        
        # Procesamiento médico
        apply_medical_normalization: bool = True,
        expand_abbreviations: bool = True,
        use_ssml: bool = True,
        emphasize_keywords: bool = True,
        
        # Configuración para estudio
        study_mode: Optional[str] = None,  # sequential, question_pause, spaced_repetition
        pause_duration_ms: int = 1000,
        question_pause_ms: int = 3000,
        add_intro_outro: bool = False,
        
        # Batch processing
        batch_size: int = 1,
        parallel_processing: bool = False,
        
        # Calidad y validación
        min_confidence_threshold: float = 0.7,
        validate_pronunciation: bool = True,
        custom_pronunciations: Optional[Dict[str, str]] = None
    ):
        self.voice_model = voice_model
        self.language = language
        self.speed_factor = max(0.5, min(2.0, speed_factor))  # Clamp entre 0.5x y 2.0x
        self.audio_quality = audio_quality
        
        self.audio_format = audio_format
        self.bitrate_kbps = bitrate_kbps
        self.sample_rate_hz = sample_rate_hz
        self.channels = channels
        
        self.apply_medical_normalization = apply_medical_normalization
        self.expand_abbreviations = expand_abbreviations
        self.use_ssml = use_ssml
        self.emphasize_keywords = emphasize_keywords
        
        self.study_mode = study_mode
        self.pause_duration_ms = pause_duration_ms
        self.question_pause_ms = question_pause_ms
        self.add_intro_outro = add_intro_outro
        
        self.batch_size = batch_size
        self.parallel_processing = parallel_processing
        
        self.min_confidence_threshold = min_confidence_threshold
        self.validate_pronunciation = validate_pronunciation
        self.custom_pronunciations = custom_pronunciations or {}


class NormalizadorTextoMedico:
    """Normaliza texto médico para TTS óptimo."""
    
    def __init__(self, language: str = "ita"):
        self.language = language
        self.medical_dict = self._load_medical_dictionary()
        self.abbreviations = self._load_abbreviations()
        self.pronunciation_rules = self._load_pronunciation_rules()
    
    def _load_medical_dictionary(self) -> Dict[str, str]:
        """Carga diccionario de términos médicos italianos."""
        # Diccionario básico de términos médicos
        return {
            "ECG": "elettrocardiogramma",
            "RMI": "risonanza magnetica",
            "TAC": "tomografia assiale computerizzata",
            "ORL": "otorinolaringoiatria",
            "UCI": "unità di terapia intensiva",
            "PS": "pronto soccorso",
            "BMI": "indice di massa corporea",
            "PA": "pressione arteriosa",
            "FC": "frequenza cardiaca",
            "FR": "frequenza respiratoria",
            "SatO2": "saturazione di ossigeno",
            "Hb": "emoglobina",
            "GR": "globuli rossi",
            "GB": "globuli bianchi",
            "PLT": "piastrine",
            "AST": "aspartato aminotransferasi",
            "ALT": "alanina aminotransferasi",
            "LDH": "lattato deidrogenasi",
            "CK": "creatinfosfochinasi",
            "BUN": "azoto ureico",
            "PCR": "proteina C reattiva",
            "VES": "velocità di eritrosedimentazione",
            "INR": "rapporto normalizzato internazionale",
            "APTT": "tempo di tromboplastina parziale attivata"
        }
    
    def _load_abbreviations(self) -> Dict[str, str]:
        """Carga abreviaciones médicas comunes."""
        return {
            "dott.": "dottore",
            "prof.": "professore",
            "sig.": "signore",
            "sig.ra": "signora",
            "vs": "versus",
            "etc.": "eccetera",
            "ca.": "circa",
            "min.": "minuti",
            "sec.": "secondi",
            "ml": "millilitri",
            "mg": "milligrammi",
            "kg": "chilogrammi",
            "cm": "centimetri",
            "mm": "millimetri"
        }
    
    def _load_pronunciation_rules(self) -> Dict[str, str]:
        """Carga reglas de pronunciación médica."""
        return {
            "pneumonia": "polmonite",
            "dyspnea": "dispnea", 
            "tachycardia": "tachicardia",
            "bradycardia": "bradicardia",
            "hypertension": "ipertensione",
            "hypotension": "ipotensione",
            "anemia": "anemia",
            "leukemia": "leucemia",
            "lymphoma": "linfoma",
            "carcinoma": "carcinoma"
        }
    
    def normalize_text(self, text: str) -> str:
        """
        Normaliza texto médico para TTS.
        
        Args:
            text: Texto original
            
        Returns:
            Texto normalizado para síntesis
        """
        normalized = text
        
        # 1. Expandir abreviaciones
        normalized = self.expand_abbreviations(normalized)
        
        # 2. Normalizar términos médicos
        normalized = self.normalize_medical_terms(normalized)
        
        # 3. Aplicar reglas de pronunciación
        normalized = self.apply_pronunciation_rules(normalized)
        
        # 4. Limpiar caracteres especiales
        normalized = self.clean_special_characters(normalized)
        
        return normalized
    
    def expand_abbreviations(self, text: str) -> str:
        """Expande abreviaciones médicas."""
        for abbrev, expansion in self.abbreviations.items():
            # Reemplazo con word boundaries para evitar reemplazos parciales
            pattern = r'\b' + re.escape(abbrev) + r'\b'
            text = re.sub(pattern, expansion, text, flags=re.IGNORECASE)
        return text
    
    def normalize_medical_terms(self, text: str) -> str:
        """Normaliza términos médicos a su forma completa."""
        for term, expansion in self.medical_dict.items():
            pattern = r'\b' + re.escape(term) + r'\b'
            text = re.sub(pattern, expansion, text, flags=re.IGNORECASE)
        return text
    
    def apply_pronunciation_rules(self, text: str) -> str:
        """Aplica reglas específicas de pronunciación."""
        for term, pronunciation in self.pronunciation_rules.items():
            pattern = r'\b' + re.escape(term) + r'\b'
            text = re.sub(pattern, pronunciation, text, flags=re.IGNORECASE)
        return text
    
    def clean_special_characters(self, text: str) -> str:
        """Limpia caracteres especiales que pueden afectar TTS."""
        # Eliminar caracteres problemáticos
        text = re.sub(r'[^\w\s\.,;:!?\-()]', ' ', text)
        
        # Normalizar espacios múltiples
        text = re.sub(r'\s+', ' ', text)
        
        # Normalizar puntuación para pausas naturales
        text = re.sub(r'\.{2,}', '.', text)  # Múltiples puntos
        text = re.sub(r'\?{2,}', '?', text)  # Múltiples interrogaciones
        text = re.sub(r'!{2,}', '!', text)   # Múltiples exclamaciones
        
        return text.strip()
    
    def apply_ssml_emphasis(self, text: str, keywords: List[str] = None) -> str:
        """
        Aplica énfasis SSML a palabras clave médicas.
        
        Args:
            text: Texto base
            keywords: Lista de palabras clave a enfatizar
            
        Returns:
            Texto con marcado SSML
        """
        if not keywords:
            # Palabras clave médicas por defecto
            keywords = [
                "diagnosi", "sintomo", "terapia", "farmaco", "dosaggio",
                "patologia", "sindrome", "malattia", "trattamento", "cura"
            ]
        
        ssml_text = text
        
        for keyword in keywords:
            pattern = r'\b(' + re.escape(keyword) + r')\b'
            replacement = r'<emphasis level="moderate">\1</emphasis>'
            ssml_text = re.sub(pattern, replacement, ssml_text, flags=re.IGNORECASE)
        
        # Envolver en SSML root
        ssml_text = f'<speak>{ssml_text}</speak>'
        
        return ssml_text


class TTSService(BaseService):
    """
    Servicio completo de síntesis de voz médica.
    
    Utiliza Piper TTS para generar audio de alta calidad desde
    micro-memos y contenido textual médico.
    """
    
    def __init__(self):
        super().__init__("TTSService")
        self.settings = get_settings()
        self.is_initialized = False
        
        # Configuración de paths
        self.tts_base_path = Path(self.settings.TTS_STORAGE_PATH)
        self.models_path = Path(self.settings.PIPER_MODEL_PATH)
        self.piper_binary = self.settings.PIPER_CMD
        
        # Normalizador de texto médico
        self.text_normalizer = NormalizadorTextoMedico(self.settings.TTS_LANGUAGE)
        
        # Validación de configuración
        if not self.settings.TTS_ENABLED:
            raise ServiceConfigurationError("TTS service is disabled")
    
    async def _setup(self):
        """Inicializa el servicio TTS."""
        if self.is_initialized:
            return
        
        try:
            # Crear directorios necesarios
            self.tts_base_path.mkdir(parents=True, exist_ok=True)
            
            # Validar Piper TTS
            await self._validate_piper_installation()
            
            # Validar modelos de voz
            await self._validate_voice_models()
            
            # Verificar dependencias de audio
            await self._validate_audio_dependencies()
            
            self.is_initialized = True
            logger.info("TTS service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize TTS service: {e}")
            raise ServiceConfigurationError(f"TTS service setup failed: {e}")
    
    async def _validate_piper_installation(self):
        """Valida que Piper TTS esté instalado y funcional."""
        try:
            result = subprocess.run(
                [self.piper_binary, "--help"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                raise ServiceConfigurationError(f"Piper TTS not working: {result.stderr}")
                
            logger.info("Piper TTS validated successfully")
            
        except FileNotFoundError:
            raise ServiceConfigurationError(f"Piper TTS binary not found: {self.piper_binary}")
        except subprocess.TimeoutExpired:
            raise ServiceConfigurationError("Piper TTS validation timeout")
        except Exception as e:
            raise ServiceConfigurationError(f"Piper TTS validation failed: {e}")
    
    async def _validate_voice_models(self):
        """Valida que los modelos de voz estén disponibles."""
        required_models = [
            "it_riccardo_quality.onnx",
            "it_riccardo_quality.onnx.json"
        ]
        
        missing_models = []
        for model in required_models:
            model_path = self.models_path / model
            if not model_path.exists():
                missing_models.append(str(model_path))
        
        if missing_models:
            logger.warning(f"Missing voice models: {missing_models}")
            # No lanzar error - usar modelo por defecto si está disponible
    
    async def _validate_audio_dependencies(self):
        """Valida dependencias de audio (FFmpeg, etc.)."""
        try:
            # Verificar FFmpeg para conversión de audio
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                logger.warning("FFmpeg not available - limited audio conversion")
                
        except FileNotFoundError:
            logger.warning("FFmpeg not found - using basic audio processing")
        except Exception as e:
            logger.warning(f"Audio dependencies validation issue: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Verifica el estado de salud del servicio TTS."""
        if not self.is_initialized:
            await self._setup()
        
        # Verificar estado de Piper
        piper_status = "unknown"
        try:
            result = subprocess.run(
                [self.piper_binary, "--help"],
                capture_output=True,
                timeout=5
            )
            piper_status = "available" if result.returncode == 0 else "error"
        except Exception:
            piper_status = "unavailable"
        
        # Verificar modelos disponibles
        available_models = []
        if self.models_path.exists():
            for model_file in self.models_path.glob("*.onnx"):
                available_models.append(model_file.stem)
        
        return {
            "service": "TTSService",
            "status": "healthy" if piper_status == "available" else "degraded",
            "initialized": self.is_initialized,
            "piper_status": piper_status,
            "available_models": available_models,
            "default_language": self.settings.TTS_LANGUAGE,
            "storage_path": str(self.tts_base_path),
            "models_path": str(self.models_path),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def synthesize_micro_memo(
        self,
        micro_memo: MicroMemo,
        config: Optional[ConfiguracionTTS] = None,
        db: Session = None
    ) -> TTSResult:
        """
        Sintetiza audio de un micro-memo individual.
        
        Args:
            micro_memo: Micro-memo a sintetizar
            config: Configuración TTS
            db: Sesión de base de datos
            
        Returns:
            TTSResult con el audio generado
        """
        if not self.is_initialized:
            await self._setup()
        
        config = config or ConfiguracionTTS()
        
        try:
            logger.info(f"Synthesizing TTS for micro-memo {micro_memo.id}")
            
            # Crear registro TTS
            tts_result = TTSResult(
                micro_memo_id=micro_memo.id,
                class_session_id=micro_memo.class_session_id,
                tts_type="individual",
                voice_model=config.voice_model,
                language=config.language,
                speed_factor=config.speed_factor,
                original_text=f"Pregunta: {micro_memo.question}\nRespuesta: {micro_memo.answer}",
                status="processing"
            )
            
            if db:
                db.add(tts_result)
                db.commit()
                db.refresh(tts_result)
            
            # Preparar texto para síntesis
            if config.study_mode == "question_pause":
                # Modo estudio: pregunta + pausa + respuesta
                text_parts = [
                    f"Pregunta: {micro_memo.question}",
                    f"<break time='{config.question_pause_ms}ms'/>",
                    f"Respuesta: {micro_memo.answer}"
                ]
                if micro_memo.explanation:
                    text_parts.append(f"Spiegazione: {micro_memo.explanation}")
                text_content = " ".join(text_parts)
            else:
                # Modo normal: pregunta + respuesta + explicación
                text_content = f"Pregunta: {micro_memo.question}. Risposta: {micro_memo.answer}"
                if micro_memo.explanation:
                    text_content += f". Spiegazione: {micro_memo.explanation}"
            
            # Normalizar texto médico
            if config.apply_medical_normalization:
                text_content = self.text_normalizer.normalize_text(text_content)
            
            # Aplicar SSML si está habilitado
            if config.use_ssml:
                text_content = self.text_normalizer.apply_ssml_emphasis(
                    text_content,
                    keywords=[micro_memo.title] + (micro_memo.tags or [])
                )
            
            tts_result.normalized_text = text_content
            
            # Generar audio
            audio_path = await self._generate_audio(
                text_content,
                config,
                f"memo_{micro_memo.id}"
            )
            
            # Actualizar resultado
            audio_stats = await self._get_audio_stats(audio_path)
            tts_result.audio_file_path = str(audio_path)
            tts_result.audio_format = config.audio_format
            tts_result.duration_seconds = audio_stats["duration"]
            tts_result.file_size_bytes = audio_stats["size"]
            tts_result.status = "completed"
            tts_result.completed_at = datetime.utcnow()
            
            # Calcular métricas
            tts_result.synthesis_quality = await self._calculate_synthesis_quality(
                text_content, audio_path
            )
            tts_result.confidence_score = min(0.9, micro_memo.confidence_score + 0.1)
            
            if db:
                db.commit()
            
            logger.info(f"TTS synthesis completed: {audio_path}")
            return tts_result
            
        except Exception as e:
            logger.error(f"TTS synthesis failed for memo {micro_memo.id}: {e}")
            if db and tts_result:
                tts_result.status = "failed"
                tts_result.error_message = str(e)
                db.commit()
            raise
    
    async def synthesize_collection(
        self,
        collection: MicroMemoCollection,
        config: Optional[ConfiguracionTTS] = None,
        db: Session = None
    ) -> TTSResult:
        """
        Sintetiza audio de una colección completa de micro-memos.
        
        Args:
            collection: Colección de micro-memos
            config: Configuración TTS
            db: Sesión de base de datos
            
        Returns:
            TTSResult con el audio de toda la colección
        """
        if not self.is_initialized:
            await self._setup()
        
        config = config or ConfiguracionTTS()
        
        try:
            logger.info(f"Synthesizing TTS for collection {collection.id}")
            
            # Obtener micro-memos de la colección
            memos = db.query(MicroMemo).filter(
                MicroMemo.collection_id == collection.id
            ).order_by(MicroMemo.created_at).all()
            
            if not memos:
                raise ValueError(f"No memos found in collection {collection.id}")
            
            # Crear registro TTS
            tts_result = TTSResult(
                collection_id=collection.id,
                class_session_id=collection.class_session_id,
                tts_type="collection",
                voice_model=config.voice_model,
                language=config.language,
                speed_factor=config.speed_factor,
                status="processing",
                has_chapters=True
            )
            
            if db:
                db.add(tts_result)
                db.commit()
                db.refresh(tts_result)
            
            # Preparar contenido completo
            intro_text = f"Collezione di studio: {collection.name}. Iniziamo con {len(memos)} micro-memo."
            
            text_parts = [intro_text]
            chapter_markers = []
            current_time = 0.0
            
            for i, memo in enumerate(memos, 1):
                # Marcador de capítulo
                chapter_markers.append({
                    "index": i,
                    "title": memo.title,
                    "start_time": current_time,
                    "memo_id": str(memo.id)
                })
                
                # Contenido del memo
                memo_text = f"Memo {i}: {memo.title}. Pregunta: {memo.question}."
                
                # Pausa antes de la respuesta
                if config.study_mode == "question_pause":
                    memo_text += f" <break time='{config.question_pause_ms}ms'/>"
                
                memo_text += f" Risposta: {memo.answer}"
                
                if memo.explanation:
                    memo_text += f". Spiegazione: {memo.explanation}"
                
                # Separador entre memos
                memo_text += f" <break time='{config.pause_duration_ms}ms'/>"
                
                text_parts.append(memo_text)
                
                # Estimar tiempo (aproximado)
                current_time += len(memo_text) / 10.0  # ~10 caracteres por segundo
            
            # Texto final
            outro_text = f"Fine della collezione {collection.name}."
            text_parts.append(outro_text)
            
            # Combinar todo el texto
            full_text = " ".join(text_parts)
            
            # Normalizar texto médico
            if config.apply_medical_normalization:
                full_text = self.text_normalizer.normalize_text(full_text)
            
            # Aplicar SSML si está habilitado
            if config.use_ssml:
                full_text = f"<speak>{full_text}</speak>"
            
            tts_result.original_text = f"Collection: {collection.name} ({len(memos)} memos)"
            tts_result.normalized_text = full_text
            tts_result.chapter_markers = chapter_markers
            
            # Generar audio
            audio_path = await self._generate_audio(
                full_text,
                config,
                f"collection_{collection.id}"
            )
            
            # Actualizar resultado
            audio_stats = await self._get_audio_stats(audio_path)
            tts_result.audio_file_path = str(audio_path)
            tts_result.audio_format = config.audio_format
            tts_result.duration_seconds = audio_stats["duration"]
            tts_result.file_size_bytes = audio_stats["size"]
            tts_result.status = "completed"
            tts_result.completed_at = datetime.utcnow()
            
            # Métricas
            tts_result.synthesis_quality = await self._calculate_synthesis_quality(
                full_text, audio_path
            )
            tts_result.confidence_score = sum(m.confidence_score for m in memos) / len(memos)
            
            if db:
                db.commit()
            
            logger.info(f"Collection TTS synthesis completed: {audio_path}")
            return tts_result
            
        except Exception as e:
            logger.error(f"Collection TTS synthesis failed for {collection.id}: {e}")
            if db and tts_result:
                tts_result.status = "failed"
                tts_result.error_message = str(e)
                db.commit()
            raise
    
    async def _generate_audio(
        self,
        text: str,
        config: ConfiguracionTTS,
        filename_prefix: str
    ) -> Path:
        """
        Genera archivo de audio usando Piper TTS.
        
        Args:
            text: Texto a sintetizar
            config: Configuración TTS
            filename_prefix: Prefijo para el nombre del archivo
            
        Returns:
            Path del archivo de audio generado
        """
        try:
            # Crear directorio de salida
            output_dir = self.tts_base_path / "generated"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Path del modelo de voz
            model_path = self.models_path / f"{config.voice_model}.onnx"
            
            # Archivo temporal para el texto
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(text)
                text_file = f.name
            
            # Archivo de salida WAV temporal
            wav_output = output_dir / f"{filename_prefix}_{uuid4().hex[:8]}.wav"
            
            try:
                # Comando Piper TTS
                cmd = [
                    self.piper_binary,
                    "-m", str(model_path),
                    "-f", text_file,
                    "-o", str(wav_output)
                ]
                
                # Añadir configuración de velocidad si difiere de 1.0
                if config.speed_factor != 1.0:
                    cmd.extend(["--speed", str(config.speed_factor)])
                
                # Ejecutar síntesis
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minutos timeout
                )
                
                if result.returncode != 0:
                    raise RuntimeError(f"Piper TTS failed: {result.stderr}")
                
                # Convertir a formato final si es necesario
                if config.audio_format != "wav":
                    final_output = await self._convert_audio(
                        wav_output,
                        config.audio_format,
                        config.bitrate_kbps,
                        config.sample_rate_hz
                    )
                    
                    # Eliminar archivo WAV temporal
                    wav_output.unlink(missing_ok=True)
                    
                    return final_output
                else:
                    return wav_output
                    
            finally:
                # Limpiar archivo de texto temporal
                os.unlink(text_file)
                
        except Exception as e:
            logger.error(f"Audio generation failed: {e}")
            raise
    
    async def _convert_audio(
        self,
        input_path: Path,
        target_format: str,
        bitrate_kbps: int,
        sample_rate_hz: int
    ) -> Path:
        """Convierte audio a formato específico."""
        output_path = input_path.with_suffix(f".{target_format}")
        
        try:
            cmd = [
                "ffmpeg", "-y",  # Sobrescribir archivos existentes
                "-i", str(input_path),
                "-codec:a", "libmp3lame" if target_format == "mp3" else "libvorbis",
                "-b:a", f"{bitrate_kbps}k",
                "-ar", str(sample_rate_hz),
                "-ac", "1",  # Mono
                str(output_path)
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Audio conversion failed: {result.stderr}")
            
            return output_path
            
        except FileNotFoundError:
            logger.warning("FFmpeg not available - keeping WAV format")
            return input_path
        except Exception as e:
            logger.error(f"Audio conversion error: {e}")
            return input_path  # Fallback al archivo original
    
    async def _get_audio_stats(self, audio_path: Path) -> Dict[str, Any]:
        """Obtiene estadísticas del archivo de audio."""
        try:
            stats = audio_path.stat()
            
            # Intentar obtener duración con FFmpeg
            duration = 0.0
            try:
                cmd = [
                    "ffprobe", "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(audio_path)
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    duration = float(result.stdout.strip())
            except:
                pass
            
            return {
                "size": stats.st_size,
                "duration": duration,
                "created": datetime.fromtimestamp(stats.st_ctime)
            }
            
        except Exception as e:
            logger.warning(f"Could not get audio stats: {e}")
            return {"size": 0, "duration": 0.0, "created": datetime.utcnow()}
    
    async def _calculate_synthesis_quality(
        self,
        text: str,
        audio_path: Path
    ) -> float:
        """
        Calcula un score de calidad de la síntesis.
        
        Args:
            text: Texto original
            audio_path: Path del audio generado
            
        Returns:
            Score de calidad (0.0-1.0)
        """
        try:
            # Factores para calcular calidad
            quality_score = 0.8  # Base score
            
            # Factor 1: Longitud del texto vs duración del audio (ratio esperado)
            audio_stats = await self._get_audio_stats(audio_path)
            if audio_stats["duration"] > 0:
                words_count = len(text.split())
                expected_duration = words_count / 3.0  # ~3 palabras por segundo
                duration_ratio = min(1.0, expected_duration / audio_stats["duration"])
                quality_score *= duration_ratio
            
            # Factor 2: Existencia del archivo y tamaño razonable
            if audio_stats["size"] > 1000:  # Al menos 1KB
                quality_score *= 1.1
            
            # Factor 3: Términos médicos procesados correctamente
            medical_terms_count = sum(1 for term in self.text_normalizer.medical_dict.keys() 
                                    if term.lower() in text.lower())
            if medical_terms_count > 0:
                quality_score *= 1.05
            
            return min(1.0, quality_score)
            
        except Exception as e:
            logger.warning(f"Quality calculation failed: {e}")
            return 0.7  # Default score


# Instancia singleton del servicio
tts_service = TTSService()
