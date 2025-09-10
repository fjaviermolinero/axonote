"""
Middleware de rate limiting para FastAPI.
Integra el servicio de rate limiting con el pipeline de requests.
"""

import time
from typing import Callable, Optional
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.rate_limiter_service import (
    ServicioRateLimiting, TipoLimite, ConfiguracionLimite, EstrategiaLimite
)
from app.core.config import settings


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """
    Middleware de rate limiting que se aplica automáticamente a todas las requests.
    Implementa múltiples capas de protección y configuraciones específicas por endpoint.
    """
    
    def __init__(self, app, redis_client):
        super().__init__(app)
        self.rate_limiter = ServicioRateLimiting(redis_client)
        
        # Endpoints que requieren configuración especial
        self.endpoints_especiales = {
            "/api/v1/auth/login": {
                "tipo": TipoLimite.POR_IP,
                "config": ConfiguracionLimite(
                    limite_requests=5,
                    ventana_segundos=300,
                    estrategia=EstrategiaLimite.SLIDING_WINDOW,
                    mensaje_personalizado="Demasiados intentos de login desde esta IP"
                )
            },
            "/api/v1/auth/register": {
                "tipo": TipoLimite.POR_IP,
                "config": ConfiguracionLimite(
                    limite_requests=3,
                    ventana_segundos=3600,
                    estrategia=EstrategiaLimite.SLIDING_WINDOW,
                    mensaje_personalizado="Límite de registros por hora excedido"
                )
            },
            "/api/v1/recordings/upload": {
                "tipo": TipoLimite.POR_USUARIO,
                "config": ConfiguracionLimite(
                    limite_requests=20,
                    ventana_segundos=3600,
                    estrategia=EstrategiaLimite.TOKEN_BUCKET,
                    burst_permitido=5
                )
            }
        }
        
        # Endpoints exentos de rate limiting
        self.endpoints_exentos = {
            "/health",
            "/health/simple",
            "/health/detailed",
            "/docs",
            "/redoc",
            "/openapi.json"
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Procesa la request aplicando rate limiting."""
        
        start_time = time.time()
        
        # Verificar si el endpoint está exento
        if self._es_endpoint_exento(request.url.path):
            return await call_next(request)
        
        # Verificar si la IP está bloqueada
        ip_address = self._obtener_ip_real(request)
        bloqueo_info = await self.rate_limiter.verificar_ip_bloqueada(ip_address)
        
        if bloqueo_info:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "IP bloqueada",
                    "razon": bloqueo_info.get("razon", "Comportamiento sospechoso"),
                    "bloqueado_hasta": bloqueo_info.get("bloqueado_en", 0) + bloqueo_info.get("duracion", 3600)
                },
                headers={
                    "X-Blocked-IP": "true",
                    "X-Block-Reason": bloqueo_info.get("razon", "unknown")
                }
            )
        
        try:
            # Aplicar rate limiting por capas
            await self._aplicar_rate_limiting_por_capas(request)
            
            # Procesar request
            response = await call_next(request)
            
            # Añadir headers informativos de rate limiting
            await self._anadir_headers_rate_limiting(request, response)
            
            # Registrar métricas de tiempo de respuesta
            tiempo_procesamiento = time.time() - start_time
            await self._registrar_metricas_respuesta(request, response, tiempo_procesamiento)
            
            return response
            
        except HTTPException as e:
            # Si es un error de rate limiting, retornar respuesta JSON personalizada
            if e.status_code == 429:
                return JSONResponse(
                    status_code=e.status_code,
                    content={
                        "error": "Rate limit exceeded",
                        "message": e.detail,
                        "timestamp": int(time.time())
                    },
                    headers=e.headers or {}
                )
            else:
                raise
        
        except Exception as e:
            # Log del error y continuar
            print(f"Error en rate limiting middleware: {str(e)}")
            return await call_next(request)
    
    async def _aplicar_rate_limiting_por_capas(self, request: Request):
        """Aplica múltiples capas de rate limiting."""
        
        # Obtener información del usuario si está autenticado
        usuario_id, rol_usuario = await self._obtener_info_usuario(request)
        
        # Capa 1: Rate limiting global por IP (muy permisivo)
        await self.rate_limiter.verificar_limite(
            request=request,
            tipo=TipoLimite.POR_IP,
            configuracion_personalizada=ConfiguracionLimite(
                limite_requests=1000,
                ventana_segundos=3600,
                estrategia=EstrategiaLimite.SLIDING_WINDOW,
                mensaje_personalizado="Límite global por IP excedido"
            )
        )
        
        # Capa 2: Rate limiting específico por endpoint
        endpoint_config = self.endpoints_especiales.get(request.url.path)
        if endpoint_config:
            await self.rate_limiter.verificar_limite(
                request=request,
                tipo=endpoint_config["tipo"],
                usuario_id=usuario_id,
                rol_usuario=rol_usuario,
                configuracion_personalizada=endpoint_config["config"]
            )
        
        # Capa 3: Rate limiting por usuario (si está autenticado)
        if usuario_id:
            await self.rate_limiter.verificar_limite(
                request=request,
                tipo=TipoLimite.POR_USUARIO,
                usuario_id=usuario_id,
                rol_usuario=rol_usuario
            )
        
        # Capa 4: Rate limiting por endpoint genérico
        if not endpoint_config:
            await self.rate_limiter.verificar_limite(
                request=request,
                tipo=TipoLimite.POR_ENDPOINT,
                usuario_id=usuario_id,
                rol_usuario=rol_usuario,
                configuracion_personalizada=ConfiguracionLimite(
                    limite_requests=100,
                    ventana_segundos=3600,
                    estrategia=EstrategiaLimite.SLIDING_WINDOW
                )
            )
    
    async def _obtener_info_usuario(self, request: Request) -> tuple[Optional[str], Optional[str]]:
        """Obtiene información del usuario autenticado desde el token JWT."""
        
        try:
            # Obtener token del header Authorization
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return None, None
            
            token = auth_header.split(" ")[1]
            
            # Decodificar token JWT
            from jose import jwt
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=["HS256"]
            )
            
            usuario_id = payload.get("sub")
            rol_usuario = payload.get("rol")
            
            return usuario_id, rol_usuario
            
        except Exception:
            # Si hay error decodificando el token, continuar sin usuario
            return None, None
    
    async def _anadir_headers_rate_limiting(self, request: Request, response: Response):
        """Añade headers informativos sobre el estado del rate limiting."""
        
        try:
            # Obtener estadísticas actuales
            usuario_id, rol_usuario = await self._obtener_info_usuario(request)
            
            # Estadísticas por IP
            stats_ip = await self.rate_limiter.obtener_estadisticas_limite(
                request, TipoLimite.POR_IP
            )
            
            response.headers["X-RateLimit-Limit-IP"] = str(stats_ip.get("limite", 0))
            response.headers["X-RateLimit-Remaining-IP"] = str(stats_ip.get("requests_restantes", 0))
            
            # Estadísticas por usuario (si está autenticado)
            if usuario_id:
                stats_usuario = await self.rate_limiter.obtener_estadisticas_limite(
                    request, TipoLimite.POR_USUARIO, usuario_id
                )
                
                response.headers["X-RateLimit-Limit-User"] = str(stats_usuario.get("limite", 0))
                response.headers["X-RateLimit-Remaining-User"] = str(stats_usuario.get("requests_restantes", 0))
            
        except Exception:
            # Si hay error, no añadir headers
            pass
    
    async def _registrar_metricas_respuesta(
        self,
        request: Request,
        response: Response,
        tiempo_procesamiento: float
    ):
        """Registra métricas de respuesta para monitoreo."""
        
        try:
            # Registrar tiempo de respuesta lento
            if tiempo_procesamiento > 5.0:  # Más de 5 segundos
                ip_address = self._obtener_ip_real(request)
                endpoint = request.url.path
                
                # Incrementar contador de respuestas lentas
                clave_lenta = f"axonote:metrics:slow_response:{endpoint}"
                self.rate_limiter.redis.incr(clave_lenta)
                self.rate_limiter.redis.expire(clave_lenta, 3600)
            
            # Registrar errores 5xx
            if 500 <= response.status_code < 600:
                clave_error = f"axonote:metrics:server_errors:{response.status_code}"
                self.rate_limiter.redis.incr(clave_error)
                self.rate_limiter.redis.expire(clave_error, 3600)
            
        except Exception:
            # Si hay error registrando métricas, continuar
            pass
    
    def _es_endpoint_exento(self, path: str) -> bool:
        """Verifica si un endpoint está exento de rate limiting."""
        
        # Verificar paths exactos
        if path in self.endpoints_exentos:
            return True
        
        # Verificar prefijos exentos
        prefijos_exentos = ["/static/", "/favicon.ico"]
        for prefijo in prefijos_exentos:
            if path.startswith(prefijo):
                return True
        
        return False
    
    def _obtener_ip_real(self, request: Request) -> str:
        """Obtiene la IP real considerando proxies."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        cf_connecting_ip = request.headers.get("CF-Connecting-IP")
        if cf_connecting_ip:
            return cf_connecting_ip.strip()
        
        return request.client.host if request.client else "unknown"


class RateLimitDecorator:
    """
    Decorador para aplicar rate limiting específico a endpoints individuales.
    Permite configuración granular por función.
    """
    
    def __init__(
        self,
        limite_requests: int,
        ventana_segundos: int,
        tipo: TipoLimite = TipoLimite.POR_IP,
        estrategia: EstrategiaLimite = EstrategiaLimite.SLIDING_WINDOW,
        mensaje_personalizado: Optional[str] = None,
        burst_permitido: Optional[int] = None
    ):
        self.config = ConfiguracionLimite(
            limite_requests=limite_requests,
            ventana_segundos=ventana_segundos,
            estrategia=estrategia,
            mensaje_personalizado=mensaje_personalizado,
            burst_permitido=burst_permitido
        )
        self.tipo = tipo
    
    def __call__(self, func):
        """Decorador que aplica rate limiting a una función."""
        
        async def wrapper(*args, **kwargs):
            # Obtener request del contexto
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                # Si no hay request, ejecutar función sin rate limiting
                return await func(*args, **kwargs)
            
            # Aplicar rate limiting
            from app.core.database import get_redis
            redis_client = get_redis()
            rate_limiter = ServicioRateLimiting(redis_client)
            
            # Obtener info de usuario
            usuario_id, rol_usuario = await self._obtener_info_usuario(request)
            
            await rate_limiter.verificar_limite(
                request=request,
                tipo=self.tipo,
                usuario_id=usuario_id,
                rol_usuario=rol_usuario,
                configuracion_personalizada=self.config
            )
            
            # Ejecutar función original
            return await func(*args, **kwargs)
        
        return wrapper
    
    async def _obtener_info_usuario(self, request: Request) -> tuple[Optional[str], Optional[str]]:
        """Obtiene información del usuario del token JWT."""
        try:
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return None, None
            
            token = auth_header.split(" ")[1]
            
            from jose import jwt
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=["HS256"]
            )
            
            return payload.get("sub"), payload.get("rol")
            
        except Exception:
            return None, None


# Decoradores predefinidos para casos comunes
rate_limit_auth = RateLimitDecorator(
    limite_requests=5,
    ventana_segundos=300,
    tipo=TipoLimite.POR_IP,
    mensaje_personalizado="Demasiados intentos de autenticación"
)

rate_limit_upload = RateLimitDecorator(
    limite_requests=10,
    ventana_segundos=3600,
    tipo=TipoLimite.POR_USUARIO,
    estrategia=EstrategiaLimite.TOKEN_BUCKET,
    burst_permitido=3
)

rate_limit_api = RateLimitDecorator(
    limite_requests=100,
    ventana_segundos=3600,
    tipo=TipoLimite.POR_USUARIO,
    estrategia=EstrategiaLimite.SLIDING_WINDOW
)
