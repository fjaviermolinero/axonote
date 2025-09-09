"""
Servicio Notion para sincronización de datos.
Versión inicial con funcionalidades básicas.
"""

from typing import Any, Dict, Optional
from notion_client import Client

from app.core import settings
from app.services.base import BaseService, ServiceNotAvailableError, ServiceConfigurationError


class NotionService(BaseService):
    """Servicio para integración con Notion."""
    
    def __init__(self):
        super().__init__()
        self.client: Optional[Client] = None
    
    async def _setup(self) -> None:
        """Configurar cliente Notion."""
        if not settings.NOTION_TOKEN:
            raise ServiceConfigurationError(
                "Notion",
                "Token de Notion no configurado"
            )
        
        try:
            self.client = Client(auth=settings.NOTION_TOKEN)
        except Exception as e:
            raise ServiceConfigurationError(
                "Notion",
                f"Error configurando cliente Notion: {str(e)}"
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar salud del servicio Notion."""
        try:
            if not self.client:
                await self.initialize()
            
            # TODO: Hacer llamada básica a Notion API
            return {
                "status": "healthy" if settings.NOTION_TOKEN else "not_configured",
                "token_configured": bool(settings.NOTION_TOKEN),
                "databases_configured": bool(
                    settings.NOTION_DB_CLASSES and
                    settings.NOTION_DB_SOURCES and
                    settings.NOTION_DB_TERMS and
                    settings.NOTION_DB_CARDS
                )
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def create_class_page(self, class_data: Dict[str, Any]) -> Optional[str]:
        """Crear página de clase en Notion."""
        # TODO: Implementar en fases posteriores
        self.logger.info("Creación de página Notion (placeholder)", class_id=class_data.get("id"))
        return None


# Instancia global
notion_service = NotionService()
