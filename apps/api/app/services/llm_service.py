"""
Servicio LLM para análisis de texto médico con Qwen2.5-14B local y OpenAI fallback.
Incluye análisis completo, corrección de terminología y generación de resúmenes.
"""

import json
import re
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

import httpx
from openai import AsyncOpenAI

from app.core import settings
from app.services.base import BaseService, ServiceNotAvailableError


class LLMService(BaseService):
    """
    Servicio completo de LLM para análisis de transcripciones médicas.
    
    Soporta LLM local (Qwen2.5-14B via LM Studio/Ollama) con fallback
    a OpenAI. Incluye análisis médico especializado, corrección de terminología
    y generación de resúmenes estructurados.
    """
    
    def __init__(self):
        super().__init__()
        self.local_client: Optional[httpx.AsyncClient] = None
        self.openai_client: Optional[AsyncOpenAI] = None
        self.monthly_cost: float = 0.0
        self.request_count: int = 0
        
    async def _setup(self) -> None:
        """Configurar clientes LLM local y remoto."""
        # Cliente local (LM Studio/Ollama)
        self.local_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(max_connections=5)
        )
        
        # Cliente OpenAI (si está configurado)
        if settings.OPENAI_API_KEY:
            self.openai_client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                timeout=60.0
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar salud completa del servicio LLM."""
        health = {
            "local_provider": settings.LLM_PROVIDER,
            "local_model": settings.LLM_MODEL_NAME,
            "local_available": False,
            "remote_available": bool(settings.OPENAI_API_KEY) and settings.FEATURE_REMOTE_TURBO,
            "monthly_cost_eur": self.monthly_cost,
            "monthly_limit_eur": settings.OPENAI_MAX_MONTHLY_COST,
            "request_count": self.request_count
        }
        
        # Verificar LLM local
        try:
            if settings.LLM_PROVIDER == "lmstudio":
                response = await self.local_client.get(f"{settings.LMSTUDIO_BASE_URL}/v1/models")
                if response.status_code == 200:
                    models = response.json()
                    health["local_available"] = len(models.get("data", [])) > 0
                    health["local_models"] = [m.get("id") for m in models.get("data", [])]
            elif settings.LLM_PROVIDER == "ollama":
                response = await self.local_client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                if response.status_code == 200:
                    models = response.json()
                    health["local_available"] = len(models.get("models", [])) > 0
                    health["local_models"] = [m.get("name") for m in models.get("models", [])]
        except Exception as e:
            health["local_error"] = str(e)
        
        # Verificar OpenAI
        if self.openai_client:
            try:
                # Test simple para verificar conectividad
                await self.openai_client.models.list()
                health["remote_available"] = True
            except Exception as e:
                health["remote_error"] = str(e)
                health["remote_available"] = False
        
        # Estado general
        health["status"] = "healthy" if health["local_available"] or health["remote_available"] else "degraded"
        health["can_process"] = health["local_available"] or (
            health["remote_available"] and 
            self.monthly_cost < settings.OPENAI_MAX_MONTHLY_COST
        )
        
        return health
    
    async def analyze_medical_transcription(
        self,
        transcription: str,
        diarization_data: Dict,
        preset: str = "MEDICAL_COMPREHENSIVE"
    ) -> Dict[str, Any]:
        """
        Análisis completo de transcripción médica con LLM.
        
        Args:
            transcription: Texto de la transcripción
            diarization_data: Datos de diarización con speakers
            preset: Configuración predefinida de análisis
            
        Returns:
            Resultado estructurado del análisis LLM
        """
        start_time = time.time()
        
        try:
            # Obtener configuración del preset
            config = self._get_analysis_config(preset)
            
            # Preparar contexto médico
            context = self._prepare_medical_context(transcription, diarization_data)
            
            # Decidir qué LLM usar
            use_local = await self._should_use_local_llm()
            
            if use_local:
                result = await self._analyze_with_local_llm(context, config)
                provider = "local"
                model_name = settings.LLM_MODEL_NAME
            else:
                result = await self._analyze_with_openai(context, config)
                provider = "openai"
                model_name = settings.OPENAI_MODEL
            
            # Calcular métricas
            processing_time = time.time() - start_time
            
            # Validar y mejorar resultado
            validated_result = await self._validate_and_improve_result(result, context)
            
            return {
                "success": True,
                "provider": provider,
                "model_name": model_name,
                "preset": preset,
                "processing_time": processing_time,
                "tokens_used": result.get("tokens_used", 0),
                "cost_eur": result.get("cost_eur", 0.0),
                **validated_result
            }
            
        except Exception as e:
            self.logger.error(f"Error en análisis LLM: {e}")
            return {
                "success": False,
                "error": str(e),
                "processing_time": time.time() - start_time
            }
    
    def _get_analysis_config(self, preset: str) -> Dict:
        """Configuraciones predefinidas para análisis médico."""
        configs = {
            "MEDICAL_COMPREHENSIVE": {
                "max_tokens": 4000,
                "temperature": 0.1,
                "system_prompt": self._get_medical_system_prompt(),
                "tasks": ["resumen", "conceptos", "estructura", "terminologia"],
                "response_format": "json"
            },
            "MEDICAL_QUICK": {
                "max_tokens": 2000,
                "temperature": 0.2,
                "system_prompt": self._get_quick_system_prompt(),
                "tasks": ["resumen", "conceptos"],
                "response_format": "json"
            },
            "TERMINOLOGY_FOCUSED": {
                "max_tokens": 3000,
                "temperature": 0.05,
                "system_prompt": self._get_terminology_prompt(),
                "tasks": ["terminologia", "definiciones"],
                "response_format": "json"
            },
            "STRUCTURE_ANALYSIS": {
                "max_tokens": 2500,
                "temperature": 0.1,
                "system_prompt": self._get_structure_prompt(),
                "tasks": ["estructura", "participacion"],
                "response_format": "json"
            }
        }
        return configs.get(preset, configs["MEDICAL_COMPREHENSIVE"])
    
    def _prepare_medical_context(self, transcription: str, diarization_data: Dict) -> Dict:
        """Preparar contexto médico para el análisis LLM."""
        # Extraer información de speakers
        speakers_info = {}
        if diarization_data and "segments" in diarization_data:
            for segment in diarization_data["segments"]:
                speaker = segment.get("speaker", "unknown")
                if speaker not in speakers_info:
                    speakers_info[speaker] = {
                        "total_time": 0,
                        "segments_count": 0,
                        "role": segment.get("role", "unknown")
                    }
                speakers_info[speaker]["total_time"] += segment.get("duration", 0)
                speakers_info[speaker]["segments_count"] += 1
        
        # Estadísticas básicas del texto
        word_count = len(transcription.split())
        estimated_duration = word_count / 150  # ~150 WPM promedio
        
        return {
            "transcription": transcription,
            "word_count": word_count,
            "estimated_duration_min": estimated_duration,
            "speakers_info": speakers_info,
            "num_speakers": len(speakers_info),
            "diarization_available": bool(diarization_data)
        }
    
    async def _should_use_local_llm(self) -> bool:
        """Determinar si usar LLM local o remoto."""
        # Verificar disponibilidad local
        health = await self.health_check()
        if not health["local_available"]:
            return False
        
        # Si no hay OpenAI configurado, usar local
        if not health["remote_available"]:
            return True
        
        # Verificar límite de costo mensual
        if self.monthly_cost >= settings.OPENAI_MAX_MONTHLY_COST:
            return True
        
        # Por defecto, preferir local (privacidad y costo)
        return True
    
    async def _analyze_with_local_llm(self, context: Dict, config: Dict) -> Dict[str, Any]:
        """Análisis con LLM local (LM Studio/Ollama)."""
        messages = [
            {"role": "system", "content": config["system_prompt"]},
            {"role": "user", "content": self._build_analysis_prompt(context, config)}
        ]
        
        if settings.LLM_PROVIDER == "lmstudio":
            return await self._call_lmstudio(messages, config)
        elif settings.LLM_PROVIDER == "ollama":
            return await self._call_ollama(messages, config)
        else:
            raise ServiceNotAvailableError(f"Proveedor LLM no soportado: {settings.LLM_PROVIDER}")
    
    async def _call_lmstudio(self, messages: List[Dict], config: Dict) -> Dict[str, Any]:
        """Llamada a LM Studio API."""
        payload = {
            "model": settings.LLM_MODEL_NAME,
            "messages": messages,
            "max_tokens": config["max_tokens"],
            "temperature": config["temperature"],
            "stream": False
        }
        
        response = await self.local_client.post(
            f"{settings.LMSTUDIO_BASE_URL}/v1/chat/completions",
            json=payload
        )
        response.raise_for_status()
        
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        return {
            "content": content,
            "tokens_used": result.get("usage", {}).get("total_tokens", 0),
            "cost_eur": 0.0  # Local es gratis
        }
    
    async def _call_ollama(self, messages: List[Dict], config: Dict) -> Dict[str, Any]:
        """Llamada a Ollama API."""
        # Convertir mensajes al formato de Ollama
        prompt = f"{messages[0]['content']}\n\nUser: {messages[1]['content']}\nAssistant:"
        
        payload = {
            "model": settings.LLM_MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": config["temperature"],
                "num_predict": config["max_tokens"]
            }
        }
        
        response = await self.local_client.post(
            f"{settings.OLLAMA_BASE_URL}/api/generate",
            json=payload
        )
        response.raise_for_status()
        
        result = response.json()
        
        return {
            "content": result["response"],
            "tokens_used": result.get("eval_count", 0) + result.get("prompt_eval_count", 0),
            "cost_eur": 0.0  # Local es gratis
        }
    
    async def _analyze_with_openai(self, context: Dict, config: Dict) -> Dict[str, Any]:
        """Análisis con OpenAI API."""
        messages = [
            {"role": "system", "content": config["system_prompt"]},
            {"role": "user", "content": self._build_analysis_prompt(context, config)}
        ]
        
        response = await self.openai_client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            max_tokens=config["max_tokens"],
            temperature=config["temperature"]
        )
        
        # Calcular costo aproximado (gpt-4o-mini: $0.15/1M input, $0.6/1M output)
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        cost_usd = (input_tokens * 0.15 + output_tokens * 0.6) / 1_000_000
        cost_eur = cost_usd * 0.92  # Conversión aproximada USD->EUR
        
        # Actualizar contador de costo mensual
        self.monthly_cost += cost_eur
        self.request_count += 1
        
        return {
            "content": response.choices[0].message.content,
            "tokens_used": response.usage.total_tokens,
            "cost_eur": cost_eur
        }
    
    def _build_analysis_prompt(self, context: Dict, config: Dict) -> str:
        """Construir prompt específico para análisis médico."""
        prompt_parts = [
            "Analiza la siguiente transcripción de una clase médica en italiano:",
            f"\n**TRANSCRIPCIÓN ({context['word_count']} palabras):**",
            context["transcription"],
        ]
        
        if context["diarization_available"]:
            prompt_parts.extend([
                f"\n**INFORMACIÓN DE SPEAKERS:**",
                f"- Número de speakers detectados: {context['num_speakers']}",
                f"- Información detallada: {json.dumps(context['speakers_info'], indent=2)}"
            ])
        
        prompt_parts.extend([
            f"\n**TAREAS REQUERIDAS:** {', '.join(config['tasks'])}",
            "\n**FORMATO DE RESPUESTA:** JSON válido con las siguientes claves:",
            "- resumen_principal: Resumen en español con citas breves en italiano",
            "- conceptos_clave: Lista de conceptos médicos importantes",
            "- estructura_clase: Análisis de la estructura pedagógica",
            "- terminologia_medica: Términos médicos con definiciones",
            "- momentos_clave: Momentos importantes con timestamps",
            "- confianza_analisis: Puntuación de confianza (0.0-1.0)",
            "- coherencia_score: Puntuación de coherencia del contenido",
            "- completitud_score: Puntuación de completitud del análisis"
        ])
        
        return "\n".join(prompt_parts)
    
    async def _validate_and_improve_result(self, result: Dict, context: Dict) -> Dict[str, Any]:
        """Validar y mejorar el resultado del análisis LLM."""
        try:
            # Intentar parsear JSON si viene como string
            content = result["content"]
            if isinstance(content, str):
                # Limpiar y extraer JSON
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    content = json.loads(json_match.group())
                else:
                    # Fallback: crear estructura básica
                    content = {
                        "resumen_principal": content[:500] + "...",
                        "conceptos_clave": [],
                        "confianza_analisis": 0.5
                    }
            
            # Validar campos requeridos
            validated = {
                "resumen_principal": content.get("resumen_principal", ""),
                "conceptos_clave": content.get("conceptos_clave", []),
                "estructura_clase": content.get("estructura_clase", {}),
                "terminologia_medica": content.get("terminologia_medica", {}),
                "momentos_clave": content.get("momentos_clave", []),
                "confianza_analisis": float(content.get("confianza_analisis", 0.7)),
                "coherencia_score": float(content.get("coherencia_score", 0.7)),
                "completitud_score": float(content.get("completitud_score", 0.7))
            }
            
            # Calcular métricas adicionales
            validated["needs_review"] = validated["confianza_analisis"] < 0.8
            validated["quality_score"] = (
                validated["confianza_analisis"] * 0.4 +
                validated["coherencia_score"] * 0.3 +
                validated["completitud_score"] * 0.3
            )
            
            return validated
            
        except Exception as e:
            self.logger.error(f"Error validando resultado LLM: {e}")
            # Resultado fallback
            return {
                "resumen_principal": "Error en el análisis LLM",
                "conceptos_clave": [],
                "estructura_clase": {},
                "terminologia_medica": {},
                "momentos_clave": [],
                "confianza_analisis": 0.0,
                "coherencia_score": 0.0,
                "completitud_score": 0.0,
                "needs_review": True,
                "quality_score": 0.0,
                "error": str(e)
            }
    
    def _get_medical_system_prompt(self) -> str:
        """Prompt del sistema para análisis médico completo."""
        return """Eres un asistente especializado en análisis de clases médicas universitarias en italiano. 

Tu tarea es analizar transcripciones de clases médicas y generar:
1. Resúmenes estructurados en español con citas precisas en italiano
2. Identificación de conceptos médicos clave
3. Análisis de la estructura pedagógica de la clase
4. Extracción de terminología médica especializada
5. Identificación de momentos clave de aprendizaje

IMPORTANTE:
- Mantén la precisión médica y terminológica
- Usa citas breves en italiano solo cuando aporten valor
- Estructura el contenido de forma pedagógica
- Identifica claramente profesor vs estudiantes
- Responde SIEMPRE en formato JSON válido"""
    
    def _get_quick_system_prompt(self) -> str:
        """Prompt para análisis rápido."""
        return """Eres un asistente médico que genera resúmenes rápidos de clases médicas en italiano.

Genera un resumen conciso en español con los conceptos médicos más importantes.
Mantén la terminología médica precisa.
Responde en formato JSON válido."""
    
    def _get_terminology_prompt(self) -> str:
        """Prompt enfocado en terminología."""
        return """Eres un experto en terminología médica italiana.

Extrae y analiza todos los términos médicos de la transcripción.
Para cada término proporciona:
- Definición en italiano
- Traducción/explicación en español  
- Categoría médica (anatomía, patología, farmacología, etc.)
- Contexto de uso en la clase

Responde en formato JSON válido."""
    
    def _get_structure_prompt(self) -> str:
        """Prompt para análisis de estructura."""
        return """Eres un pedagogo médico especializado en análisis de clases.

Analiza la estructura pedagógica de la clase:
- Introducción y objetivos
- Desarrollo del contenido
- Momentos de interacción profesor-estudiante
- Preguntas y respuestas
- Conclusiones y resumen
- Participación de estudiantes

Responde en formato JSON válido."""
    
    async def cleanup(self) -> None:
        """Limpiar recursos del servicio."""
        if self.local_client:
            await self.local_client.aclose()
        if self.openai_client:
            await self.openai_client.close()
