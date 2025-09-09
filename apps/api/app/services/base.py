"""
Clase base para servicios.
Define interfaz común y utilidades compartidas.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.core import api_logger


class BaseService(ABC):
    """Clase base para todos los servicios."""
    
    def __init__(self):
        self.logger = api_logger
        self._initialized = False
    
    async def initialize(self) -> None:
        """Inicializar el servicio (conexiones, configuración, etc.)."""
        if not self._initialized:
            await self._setup()
            self._initialized = True
            self.logger.info(f"Servicio {self.__class__.__name__} inicializado")
    
    @abstractmethod
    async def _setup(self) -> None:
        """Configuración específica del servicio."""
        pass
    
    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Verificar salud del servicio."""
        pass
    
    async def cleanup(self) -> None:
        """Limpiar recursos del servicio."""
        self.logger.info(f"Servicio {self.__class__.__name__} limpiado")


class ExternalServiceError(Exception):
    """Excepción base para errores de servicios externos."""
    
    def __init__(self, service_name: str, message: str, details: Optional[Dict] = None):
        self.service_name = service_name
        self.message = message
        self.details = details or {}
        super().__init__(f"{service_name}: {message}")


class ServiceNotAvailableError(ExternalServiceError):
    """Servicio no disponible temporalmente."""
    pass


class ServiceConfigurationError(ExternalServiceError):
    """Error de configuración del servicio."""
    pass
