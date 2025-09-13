"""
Rate limiter para controlar la frecuencia de requests a APIs externas.

Implementa diferentes estrategias de rate limiting para respetar
los límites de las APIs de fuentes médicas externas.
"""

import asyncio
import time
from typing import Optional, Dict, Any
from collections import deque
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter asíncrono con soporte para diferentes estrategias.
    
    Controla la frecuencia de requests para respetar los límites
    de APIs externas como PubMed, WHO, etc.
    """
    
    def __init__(
        self,
        requests_per_second: float = 1.0,
        burst_size: Optional[int] = None,
        strategy: str = "token_bucket"
    ):
        """
        Inicializa el rate limiter.
        
        Args:
            requests_per_second: Número de requests permitidos por segundo
            burst_size: Tamaño máximo de burst (None = requests_per_second * 2)
            strategy: Estrategia de rate limiting ('token_bucket', 'sliding_window')
        """
        self.requests_per_second = requests_per_second
        self.burst_size = burst_size or max(1, int(requests_per_second * 2))
        self.strategy = strategy
        
        # Token bucket strategy
        self.tokens = self.burst_size
        self.last_refill = time.time()
        
        # Sliding window strategy
        self.request_times = deque()
        
        # Semáforo para controlar concurrencia
        self.semaphore = asyncio.Semaphore(self.burst_size)
        
        logger.info(f"RateLimiter inicializado: {requests_per_second} req/s, burst: {self.burst_size}")
    
    async def __aenter__(self):
        """Context manager entry - adquiere permiso para hacer request."""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - libera recursos si es necesario."""
        pass
    
    async def acquire(self) -> None:
        """
        Adquiere permiso para hacer un request.
        Bloquea hasta que sea seguro proceder.
        """
        async with self.semaphore:
            if self.strategy == "token_bucket":
                await self._acquire_token_bucket()
            elif self.strategy == "sliding_window":
                await self._acquire_sliding_window()
            else:
                raise ValueError(f"Estrategia desconocida: {self.strategy}")
    
    async def _acquire_token_bucket(self) -> None:
        """Implementación de token bucket algorithm."""
        while True:
            now = time.time()
            
            # Rellenar tokens basado en tiempo transcurrido
            time_passed = now - self.last_refill
            tokens_to_add = time_passed * self.requests_per_second
            
            self.tokens = min(self.burst_size, self.tokens + tokens_to_add)
            self.last_refill = now
            
            # Si hay tokens disponibles, usar uno
            if self.tokens >= 1:
                self.tokens -= 1
                break
            
            # Calcular tiempo de espera hasta el próximo token
            wait_time = (1 - self.tokens) / self.requests_per_second
            await asyncio.sleep(wait_time)
    
    async def _acquire_sliding_window(self) -> None:
        """Implementación de sliding window algorithm."""
        now = time.time()
        window_start = now - 1.0  # Ventana de 1 segundo
        
        # Remover requests antiguos fuera de la ventana
        while self.request_times and self.request_times[0] < window_start:
            self.request_times.popleft()
        
        # Si estamos dentro del límite, proceder
        if len(self.request_times) < self.requests_per_second:
            self.request_times.append(now)
            return
        
        # Calcular tiempo de espera
        oldest_request = self.request_times[0]
        wait_time = oldest_request + 1.0 - now
        
        if wait_time > 0:
            await asyncio.sleep(wait_time)
            # Recursión para verificar nuevamente
            await self._acquire_sliding_window()
        else:
            self.request_times.append(now)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del rate limiter.
        
        Returns:
            Diccionario con estadísticas
        """
        now = time.time()
        
        if self.strategy == "token_bucket":
            # Calcular tokens actuales
            time_passed = now - self.last_refill
            current_tokens = min(
                self.burst_size,
                self.tokens + (time_passed * self.requests_per_second)
            )
            
            return {
                "strategy": self.strategy,
                "requests_per_second": self.requests_per_second,
                "burst_size": self.burst_size,
                "current_tokens": current_tokens,
                "tokens_percentage": (current_tokens / self.burst_size) * 100,
                "last_refill": self.last_refill
            }
        
        elif self.strategy == "sliding_window":
            # Limpiar ventana
            window_start = now - 1.0
            current_requests = [t for t in self.request_times if t >= window_start]
            
            return {
                "strategy": self.strategy,
                "requests_per_second": self.requests_per_second,
                "current_requests_in_window": len(current_requests),
                "available_requests": max(0, self.requests_per_second - len(current_requests)),
                "window_utilization": (len(current_requests) / self.requests_per_second) * 100
            }
    
    def reset(self) -> None:
        """Resetea el estado del rate limiter."""
        if self.strategy == "token_bucket":
            self.tokens = self.burst_size
            self.last_refill = time.time()
        elif self.strategy == "sliding_window":
            self.request_times.clear()
        
        logger.info(f"RateLimiter reseteado")


class AdaptiveRateLimiter(RateLimiter):
    """
    Rate limiter adaptativo que ajusta automáticamente los límites
    basado en respuestas de la API (429, 503, etc.).
    """
    
    def __init__(
        self,
        initial_requests_per_second: float = 1.0,
        min_requests_per_second: float = 0.1,
        max_requests_per_second: float = 10.0,
        backoff_factor: float = 0.5,
        recovery_factor: float = 1.1,
        **kwargs
    ):
        """
        Inicializa el rate limiter adaptativo.
        
        Args:
            initial_requests_per_second: Rate inicial
            min_requests_per_second: Rate mínimo
            max_requests_per_second: Rate máximo
            backoff_factor: Factor de reducción en errores
            recovery_factor: Factor de recuperación en éxito
        """
        super().__init__(initial_requests_per_second, **kwargs)
        
        self.initial_rate = initial_requests_per_second
        self.min_rate = min_requests_per_second
        self.max_rate = max_requests_per_second
        self.backoff_factor = backoff_factor
        self.recovery_factor = recovery_factor
        
        # Estadísticas para adaptación
        self.consecutive_successes = 0
        self.consecutive_errors = 0
        self.last_adjustment = time.time()
        self.adjustment_cooldown = 10.0  # segundos
        
        logger.info(f"AdaptiveRateLimiter inicializado: {initial_requests_per_second} req/s")
    
    async def report_success(self) -> None:
        """Reporta un request exitoso para ajuste adaptativo."""
        self.consecutive_successes += 1
        self.consecutive_errors = 0
        
        # Considerar aumentar rate si hay muchos éxitos consecutivos
        if (self.consecutive_successes >= 10 and 
            time.time() - self.last_adjustment > self.adjustment_cooldown):
            await self._increase_rate()
    
    async def report_rate_limit_error(self) -> None:
        """Reporta un error de rate limit (429, 503) para ajuste."""
        self.consecutive_errors += 1
        self.consecutive_successes = 0
        
        # Reducir rate inmediatamente en errores de rate limit
        await self._decrease_rate()
    
    async def report_error(self) -> None:
        """Reporta un error general (no necesariamente rate limit)."""
        self.consecutive_successes = 0
        # No ajustar rate automáticamente para errores generales
    
    async def _increase_rate(self) -> None:
        """Aumenta el rate de requests."""
        old_rate = self.requests_per_second
        new_rate = min(self.max_rate, old_rate * self.recovery_factor)
        
        if new_rate != old_rate:
            self.requests_per_second = new_rate
            self.burst_size = max(1, int(new_rate * 2))
            self.last_adjustment = time.time()
            self.consecutive_successes = 0
            
            logger.info(f"Rate aumentado: {old_rate:.2f} -> {new_rate:.2f} req/s")
    
    async def _decrease_rate(self) -> None:
        """Disminuye el rate de requests."""
        old_rate = self.requests_per_second
        new_rate = max(self.min_rate, old_rate * self.backoff_factor)
        
        if new_rate != old_rate:
            self.requests_per_second = new_rate
            self.burst_size = max(1, int(new_rate * 2))
            self.last_adjustment = time.time()
            self.consecutive_errors = 0
            
            logger.warning(f"Rate reducido por rate limit: {old_rate:.2f} -> {new_rate:.2f} req/s")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas extendidas del rate limiter adaptativo."""
        base_stats = super().get_stats()
        
        adaptive_stats = {
            "adaptive": True,
            "initial_rate": self.initial_rate,
            "current_rate": self.requests_per_second,
            "min_rate": self.min_rate,
            "max_rate": self.max_rate,
            "consecutive_successes": self.consecutive_successes,
            "consecutive_errors": self.consecutive_errors,
            "last_adjustment": self.last_adjustment,
            "rate_adjustment_ratio": self.requests_per_second / self.initial_rate
        }
        
        return {**base_stats, **adaptive_stats}


class MultiServiceRateLimiter:
    """
    Gestor de múltiples rate limiters para diferentes servicios.
    
    Permite configurar límites específicos para cada API externa
    y gestionar todos desde un punto central.
    """
    
    def __init__(self):
        self.limiters: Dict[str, RateLimiter] = {}
        self.default_config = {
            "requests_per_second": 1.0,
            "strategy": "token_bucket"
        }
        
        logger.info("MultiServiceRateLimiter inicializado")
    
    def add_service(
        self,
        service_name: str,
        requests_per_second: float,
        **kwargs
    ) -> None:
        """
        Añade un rate limiter para un servicio específico.
        
        Args:
            service_name: Nombre del servicio
            requests_per_second: Límite de requests por segundo
            **kwargs: Configuración adicional
        """
        config = {**self.default_config, **kwargs}
        # Remover parámetros específicos para evitar duplicados
        config.pop("requests_per_second", None)
        is_adaptive = config.pop("adaptive", False)
        
        if is_adaptive:
            limiter = AdaptiveRateLimiter(requests_per_second, **config)
        else:
            limiter = RateLimiter(requests_per_second, **config)
        
        self.limiters[service_name] = limiter
        logger.info(f"Rate limiter añadido para {service_name}: {requests_per_second} req/s")
    
    def get_limiter(self, service_name: str) -> Optional[RateLimiter]:
        """
        Obtiene el rate limiter para un servicio.
        
        Args:
            service_name: Nombre del servicio
            
        Returns:
            Rate limiter del servicio o None
        """
        return self.limiters.get(service_name)
    
    async def acquire(self, service_name: str) -> None:
        """
        Adquiere permiso para hacer request a un servicio.
        
        Args:
            service_name: Nombre del servicio
        """
        limiter = self.get_limiter(service_name)
        if limiter:
            await limiter.acquire()
        else:
            logger.warning(f"No hay rate limiter configurado para {service_name}")
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Obtiene estadísticas de todos los rate limiters.
        
        Returns:
            Diccionario con estadísticas por servicio
        """
        return {
            service: limiter.get_stats()
            for service, limiter in self.limiters.items()
        }
    
    def reset_all(self) -> None:
        """Resetea todos los rate limiters."""
        for limiter in self.limiters.values():
            limiter.reset()
        
        logger.info("Todos los rate limiters reseteados")


# Instancia global para uso en servicios
global_rate_limiter = MultiServiceRateLimiter()

# Configuración por defecto para servicios conocidos
def setup_default_limiters():
    """Configura rate limiters por defecto para servicios conocidos."""
    
    # PubMed/NCBI - 3 req/s con API key, 1 req/s sin ella
    global_rate_limiter.add_service(
        "pubmed",
        requests_per_second=3.0,  # Asume API key
        adaptive=True,
        min_requests_per_second=0.5,
        max_requests_per_second=5.0
    )
    
    # WHO - Sin límites oficiales, usar conservador
    global_rate_limiter.add_service(
        "who",
        requests_per_second=2.0,
        adaptive=True
    )
    
    # NIH - Similar a PubMed
    global_rate_limiter.add_service(
        "nih",
        requests_per_second=2.0,
        adaptive=True
    )
    
    # MedlinePlus - Conservador
    global_rate_limiter.add_service(
        "medlineplus",
        requests_per_second=1.0,
        adaptive=True
    )
    
    # Fuentes italianas - Conservador
    global_rate_limiter.add_service(
        "italian_sources",
        requests_per_second=1.0,
        adaptive=True
    )

# Configurar limiters por defecto al importar
setup_default_limiters()
