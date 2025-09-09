"""
Servicio LLM para procesamiento de texto con IA.
Versión inicial con stubs para desarrollo.
"""

from typing import Any, Dict, Optional
import httpx

from app.core import settings
from app.services.base import BaseService, ServiceNotAvailableError


class LLMService(BaseService):
    """Servicio para LLM local y remoto."""
    
    def __init__(self):
        super().__init__()
        self.local_client: Optional[httpx.AsyncClient] = None
    
    async def _setup(self) -> None:
        """Configurar cliente LLM."""
        self.local_client = httpx.AsyncClient(timeout=30.0)
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar salud del servicio LLM."""
        health = {
            "local_provider": settings.LLM_PROVIDER,
            "local_available": False,
            "remote_available": bool(settings.OPENAI_API_KEY) and settings.FEATURE_REMOTE_TURBO
        }
        
        # Verificar LLM local
        try:
            if settings.LLM_PROVIDER == "lmstudio":
                response = await self.local_client.get(f"{settings.LMSTUDIO_BASE_URL}/models")
                health["local_available"] = response.status_code == 200
            elif settings.LLM_PROVIDER == "ollama":
                response = await self.local_client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                health["local_available"] = response.status_code == 200
        except Exception as e:
            health["local_error"] = str(e)
        
        health["status"] = "healthy" if health["local_available"] or health["remote_available"] else "degraded"
        return health
    
    async def process_text(self, text: str, task: str) -> Dict[str, Any]:
        """Procesar texto con LLM."""
        # TODO: Implementar en fases posteriores
        self.logger.info("Procesamiento LLM (placeholder)", task=task, text_length=len(text))
        return {"result": "placeholder", "confidence": 0.9}
    
    async def cleanup(self) -> None:
        """Limpiar recursos."""
        if self.local_client:
            await self.local_client.aclose()
        await super().cleanup()


# Instancia global
llm_service = LLMService()
