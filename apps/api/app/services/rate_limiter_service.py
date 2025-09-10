"""
Servicio de rate limiting avanzado para Axonote.
Implementa múltiples estrategias de limitación con Redis como backend.
"""

import time
import json
import redis
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
from fastapi import HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import settings
from app.models.usuario import TipoEventoAuditoria, NivelSeveridad


class TipoLimite(str, Enum):
    """Tipos de límites de rate limiting."""
    POR_IP = "ip"
    POR_USUARIO = "user"
    POR_ENDPOINT = "endpoint"
    POR_API_KEY = "api_key"
    GLOBAL = "global"
    POR_PAIS = "country"


class EstrategiaLimite(str, Enum):
    """Estrategias de rate limiting."""
    FIXED_WINDOW = "fixed_window"      # Ventana fija
    SLIDING_WINDOW = "sliding_window"  # Ventana deslizante
    TOKEN_BUCKET = "token_bucket"      # Bucket de tokens
    LEAKY_BUCKET = "leaky_bucket"      # Bucket con fuga


class ConfiguracionLimite(BaseModel):
    """Configuración de un límite de rate limiting."""
    limite_requests: int
    ventana_segundos: int
    estrategia: EstrategiaLimite = EstrategiaLimite.SLIDING_WINDOW
    burst_permitido: Optional[int] = None  # Para token bucket
    mensaje_personalizado: Optional[str] = None
    codigo_http: int = 429


class ResultadoLimite(BaseModel):
    """Resultado de verificación de rate limiting."""
    permitido: bool
    requests_restantes: int
    tiempo_reset: int  # Timestamp de reset
    tiempo_retry_after: Optional[int] = None  # Segundos para retry
    mensaje: Optional[str] = None


class ServicioRateLimiting:
    """
    Servicio avanzado de rate limiting con múltiples estrategias.
    Utiliza Redis para persistencia y sincronización entre instancias.
    """
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.prefijo_clave = "axonote:rate_limit"
        
        # Configuraciones predefinidas por endpoint
        self.configuraciones_endpoint = {
            "/api/v1/auth/login": ConfiguracionLimite(
                limite_requests=5,
                ventana_segundos=300,  # 5 intentos por 5 minutos
                estrategia=EstrategiaLimite.SLIDING_WINDOW,
                mensaje_personalizado="Demasiados intentos de login. Intenta en 5 minutos."
            ),
            "/api/v1/auth/register": ConfiguracionLimite(
                limite_requests=3,
                ventana_segundos=3600,  # 3 registros por hora
                estrategia=EstrategiaLimite.SLIDING_WINDOW
            ),
            "/api/v1/recordings/upload": ConfiguracionLimite(
                limite_requests=10,
                ventana_segundos=3600,  # 10 uploads por hora
                estrategia=EstrategiaLimite.TOKEN_BUCKET,
                burst_permitido=3
            ),
            "/api/v1/processing/": ConfiguracionLimite(
                limite_requests=50,
                ventana_segundos=3600,  # 50 procesamientos por hora
                estrategia=EstrategiaLimite.SLIDING_WINDOW
            )
        }
        
        # Configuraciones por tipo de usuario
        self.configuraciones_usuario = {
            "admin": ConfiguracionLimite(
                limite_requests=1000,
                ventana_segundos=3600,
                estrategia=EstrategiaLimite.TOKEN_BUCKET,
                burst_permitido=100
            ),
            "medico": ConfiguracionLimite(
                limite_requests=500,
                ventana_segundos=3600,
                estrategia=EstrategiaLimite.TOKEN_BUCKET,
                burst_permitido=50
            ),
            "estudiante": ConfiguracionLimite(
                limite_requests=200,
                ventana_segundos=3600,
                estrategia=EstrategiaLimite.SLIDING_WINDOW
            ),
            "invitado": ConfiguracionLimite(
                limite_requests=50,
                ventana_segundos=3600,
                estrategia=EstrategiaLimite.SLIDING_WINDOW
            )
        }
    
    async def verificar_limite(
        self,
        request: Request,
        tipo: TipoLimite = TipoLimite.POR_IP,
        usuario_id: Optional[str] = None,
        rol_usuario: Optional[str] = None,
        configuracion_personalizada: Optional[ConfiguracionLimite] = None
    ) -> ResultadoLimite:
        """
        Verifica si se ha excedido el límite de requests.
        
        Args:
            request: Request de FastAPI
            tipo: Tipo de límite a aplicar
            usuario_id: ID del usuario (si está autenticado)
            rol_usuario: Rol del usuario para configuración específica
            configuracion_personalizada: Configuración específica a usar
            
        Returns:
            ResultadoLimite con información del límite
            
        Raises:
            HTTPException: Si se excede el límite
        """
        
        # Determinar configuración a usar
        config = self._obtener_configuracion(
            request, tipo, rol_usuario, configuracion_personalizada
        )
        
        # Generar clave única para este límite
        clave = self._generar_clave_limite(request, tipo, usuario_id)
        
        # Aplicar estrategia correspondiente
        if config.estrategia == EstrategiaLimite.SLIDING_WINDOW:
            resultado = await self._sliding_window(clave, config)
        elif config.estrategia == EstrategiaLimite.FIXED_WINDOW:
            resultado = await self._fixed_window(clave, config)
        elif config.estrategia == EstrategiaLimite.TOKEN_BUCKET:
            resultado = await self._token_bucket(clave, config)
        elif config.estrategia == EstrategiaLimite.LEAKY_BUCKET:
            resultado = await self._leaky_bucket(clave, config)
        else:
            # Fallback a sliding window
            resultado = await self._sliding_window(clave, config)
        
        # Si se excede el límite, registrar y lanzar excepción
        if not resultado.permitido:
            await self._registrar_limite_excedido(request, tipo, usuario_id, config, resultado)
            
            headers = {
                "X-RateLimit-Limit": str(config.limite_requests),
                "X-RateLimit-Remaining": str(resultado.requests_restantes),
                "X-RateLimit-Reset": str(resultado.tiempo_reset)
            }
            
            if resultado.tiempo_retry_after:
                headers["Retry-After"] = str(resultado.tiempo_retry_after)
            
            mensaje = config.mensaje_personalizado or resultado.mensaje or "Límite de requests excedido"
            
            raise HTTPException(
                status_code=config.codigo_http,
                detail=mensaje,
                headers=headers
            )
        
        return resultado
    
    async def _sliding_window(
        self,
        clave: str,
        config: ConfiguracionLimite
    ) -> ResultadoLimite:
        """Implementa sliding window usando sorted sets de Redis."""
        
        ahora = time.time()
        ventana_inicio = ahora - config.ventana_segundos
        
        pipe = self.redis.pipeline()
        
        # Remover requests antiguos fuera de la ventana
        pipe.zremrangebyscore(clave, 0, ventana_inicio)
        
        # Contar requests actuales en la ventana
        pipe.zcard(clave)
        
        # Añadir request actual
        pipe.zadd(clave, {str(ahora): ahora})
        
        # Establecer expiración
        pipe.expire(clave, config.ventana_segundos + 1)
        
        resultados = pipe.execute()
        requests_actuales = resultados[1]
        
        # Verificar límite
        permitido = requests_actuales < config.limite_requests
        requests_restantes = max(0, config.limite_requests - requests_actuales - 1)
        tiempo_reset = int(ahora + config.ventana_segundos)
        
        return ResultadoLimite(
            permitido=permitido,
            requests_restantes=requests_restantes,
            tiempo_reset=tiempo_reset,
            tiempo_retry_after=config.ventana_segundos if not permitido else None,
            mensaje=f"Sliding window: {requests_actuales}/{config.limite_requests}"
        )
    
    async def _fixed_window(
        self,
        clave: str,
        config: ConfiguracionLimite
    ) -> ResultadoLimite:
        """Implementa fixed window usando contadores de Redis."""
        
        ahora = time.time()
        ventana_actual = int(ahora // config.ventana_segundos)
        clave_ventana = f"{clave}:{ventana_actual}"
        
        pipe = self.redis.pipeline()
        
        # Incrementar contador de la ventana actual
        pipe.incr(clave_ventana)
        
        # Establecer expiración
        pipe.expire(clave_ventana, config.ventana_segundos)
        
        resultados = pipe.execute()
        requests_actuales = resultados[0]
        
        # Verificar límite
        permitido = requests_actuales <= config.limite_requests
        requests_restantes = max(0, config.limite_requests - requests_actuales)
        
        # Calcular tiempo de reset (inicio de siguiente ventana)
        siguiente_ventana = (ventana_actual + 1) * config.ventana_segundos
        tiempo_reset = int(siguiente_ventana)
        
        return ResultadoLimite(
            permitido=permitido,
            requests_restantes=requests_restantes,
            tiempo_reset=tiempo_reset,
            tiempo_retry_after=int(siguiente_ventana - ahora) if not permitido else None,
            mensaje=f"Fixed window: {requests_actuales}/{config.limite_requests}"
        )
    
    async def _token_bucket(
        self,
        clave: str,
        config: ConfiguracionLimite
    ) -> ResultadoLimite:
        """Implementa token bucket algorithm."""
        
        ahora = time.time()
        
        # Obtener estado actual del bucket
        bucket_data = self.redis.hgetall(clave)
        
        if bucket_data:
            tokens = float(bucket_data.get(b'tokens', config.limite_requests))
            ultimo_refill = float(bucket_data.get(b'last_refill', ahora))
        else:
            tokens = config.limite_requests
            ultimo_refill = ahora
        
        # Calcular tokens a añadir basado en tiempo transcurrido
        tiempo_transcurrido = ahora - ultimo_refill
        tokens_a_anadir = tiempo_transcurrido * (config.limite_requests / config.ventana_segundos)
        
        # Actualizar tokens (no exceder capacidad)
        tokens = min(config.limite_requests, tokens + tokens_a_anadir)
        
        # Verificar si hay tokens disponibles
        if tokens >= 1:
            # Consumir token
            tokens -= 1
            permitido = True
        else:
            permitido = False
        
        # Actualizar estado en Redis
        pipe = self.redis.pipeline()
        pipe.hset(clave, mapping={
            'tokens': tokens,
            'last_refill': ahora
        })
        pipe.expire(clave, config.ventana_segundos * 2)  # Expiración generosa
        pipe.execute()
        
        # Calcular tiempo hasta próximo token
        tiempo_proximo_token = (1 - tokens) / (config.limite_requests / config.ventana_segundos)
        
        return ResultadoLimite(
            permitido=permitido,
            requests_restantes=int(tokens),
            tiempo_reset=int(ahora + tiempo_proximo_token),
            tiempo_retry_after=int(tiempo_proximo_token) if not permitido else None,
            mensaje=f"Token bucket: {int(tokens)}/{config.limite_requests} tokens"
        )
    
    async def _leaky_bucket(
        self,
        clave: str,
        config: ConfiguracionLimite
    ) -> ResultadoLimite:
        """Implementa leaky bucket algorithm."""
        
        ahora = time.time()
        
        # Obtener estado del bucket
        bucket_data = self.redis.hgetall(clave)
        
        if bucket_data:
            nivel = float(bucket_data.get(b'level', 0))
            ultimo_leak = float(bucket_data.get(b'last_leak', ahora))
        else:
            nivel = 0
            ultimo_leak = ahora
        
        # Calcular cuánto se ha "filtrado" desde la última vez
        tiempo_transcurrido = ahora - ultimo_leak
        leak_rate = config.limite_requests / config.ventana_segundos
        nivel_despues_leak = max(0, nivel - (leak_rate * tiempo_transcurrido))
        
        # Verificar si hay espacio para una nueva request
        if nivel_despues_leak < config.limite_requests:
            # Añadir request al bucket
            nivel_despues_leak += 1
            permitido = True
        else:
            permitido = False
        
        # Actualizar estado
        pipe = self.redis.pipeline()
        pipe.hset(clave, mapping={
            'level': nivel_despues_leak,
            'last_leak': ahora
        })
        pipe.expire(clave, config.ventana_segundos * 2)
        pipe.execute()
        
        # Calcular tiempo hasta que haya espacio
        tiempo_hasta_espacio = (nivel_despues_leak - config.limite_requests + 1) / leak_rate
        
        return ResultadoLimite(
            permitido=permitido,
            requests_restantes=int(config.limite_requests - nivel_despues_leak),
            tiempo_reset=int(ahora + tiempo_hasta_espacio),
            tiempo_retry_after=int(tiempo_hasta_espacio) if not permitido else None,
            mensaje=f"Leaky bucket: {int(nivel_despues_leak)}/{config.limite_requests}"
        )
    
    def _obtener_configuracion(
        self,
        request: Request,
        tipo: TipoLimite,
        rol_usuario: Optional[str],
        configuracion_personalizada: Optional[ConfiguracionLimite]
    ) -> ConfiguracionLimite:
        """Obtiene la configuración de límite apropiada."""
        
        if configuracion_personalizada:
            return configuracion_personalizada
        
        # Configuración específica por endpoint
        endpoint = request.url.path
        if endpoint in self.configuraciones_endpoint:
            return self.configuraciones_endpoint[endpoint]
        
        # Configuración por rol de usuario
        if rol_usuario and rol_usuario in self.configuraciones_usuario:
            return self.configuraciones_usuario[rol_usuario]
        
        # Configuración por defecto según el tipo
        if tipo == TipoLimite.POR_IP:
            return ConfiguracionLimite(
                limite_requests=100,
                ventana_segundos=3600,
                estrategia=EstrategiaLimite.SLIDING_WINDOW
            )
        elif tipo == TipoLimite.POR_USUARIO:
            return ConfiguracionLimite(
                limite_requests=200,
                ventana_segundos=3600,
                estrategia=EstrategiaLimite.TOKEN_BUCKET,
                burst_permitido=20
            )
        else:
            # Configuración por defecto
            return ConfiguracionLimite(
                limite_requests=60,
                ventana_segundos=3600,
                estrategia=EstrategiaLimite.SLIDING_WINDOW
            )
    
    def _generar_clave_limite(
        self,
        request: Request,
        tipo: TipoLimite,
        usuario_id: Optional[str]
    ) -> str:
        """Genera la clave Redis para el rate limiting."""
        
        base = f"{self.prefijo_clave}:{tipo.value}"
        
        if tipo == TipoLimite.POR_IP:
            ip = self._obtener_ip_real(request)
            return f"{base}:{ip}"
        elif tipo == TipoLimite.POR_USUARIO and usuario_id:
            return f"{base}:{usuario_id}"
        elif tipo == TipoLimite.POR_ENDPOINT:
            endpoint = request.url.path.replace("/", "_")
            return f"{base}:{endpoint}"
        elif tipo == TipoLimite.POR_API_KEY:
            api_key = request.headers.get("X-API-Key", "unknown")
            return f"{base}:{api_key}"
        elif tipo == TipoLimite.GLOBAL:
            return f"{base}:global"
        else:
            # Fallback a IP
            ip = self._obtener_ip_real(request)
            return f"{base}:ip:{ip}"
    
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
    
    async def _registrar_limite_excedido(
        self,
        request: Request,
        tipo: TipoLimite,
        usuario_id: Optional[str],
        config: ConfiguracionLimite,
        resultado: ResultadoLimite
    ):
        """Registra cuando se excede un límite para auditoría."""
        
        # Importar aquí para evitar imports circulares
        from app.services.auth_service import ServicioAutenticacion
        
        ip_address = self._obtener_ip_real(request)
        user_agent = request.headers.get("User-Agent", "")
        endpoint = request.url.path
        
        # Registrar en logs de auditoría (si hay servicio disponible)
        try:
            # TODO: Integrar con servicio de auditoría cuando esté disponible
            pass
        except:
            pass
        
        # Incrementar contador de límites excedidos
        clave_contador = f"{self.prefijo_clave}:exceeded:{tipo.value}:{ip_address}"
        self.redis.incr(clave_contador)
        self.redis.expire(clave_contador, 86400)  # Expira en 24 horas
    
    async def obtener_estadisticas_limite(
        self,
        request: Request,
        tipo: TipoLimite = TipoLimite.POR_IP,
        usuario_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Obtiene estadísticas actuales de rate limiting."""
        
        clave = self._generar_clave_limite(request, tipo, usuario_id)
        config = self._obtener_configuracion(request, tipo, None, None)
        
        if config.estrategia == EstrategiaLimite.SLIDING_WINDOW:
            ahora = time.time()
            ventana_inicio = ahora - config.ventana_segundos
            requests_actuales = self.redis.zcount(clave, ventana_inicio, ahora)
            
            return {
                "estrategia": config.estrategia.value,
                "limite": config.limite_requests,
                "ventana_segundos": config.ventana_segundos,
                "requests_actuales": requests_actuales,
                "requests_restantes": max(0, config.limite_requests - requests_actuales),
                "porcentaje_usado": (requests_actuales / config.limite_requests) * 100
            }
        
        elif config.estrategia == EstrategiaLimite.TOKEN_BUCKET:
            bucket_data = self.redis.hgetall(clave)
            tokens = float(bucket_data.get(b'tokens', config.limite_requests)) if bucket_data else config.limite_requests
            
            return {
                "estrategia": config.estrategia.value,
                "limite": config.limite_requests,
                "tokens_disponibles": int(tokens),
                "porcentaje_disponible": (tokens / config.limite_requests) * 100
            }
        
        else:
            return {
                "estrategia": config.estrategia.value,
                "limite": config.limite_requests,
                "ventana_segundos": config.ventana_segundos
            }
    
    async def resetear_limite(
        self,
        request: Request,
        tipo: TipoLimite = TipoLimite.POR_IP,
        usuario_id: Optional[str] = None
    ) -> bool:
        """Resetea un límite específico (solo para administradores)."""
        
        clave = self._generar_clave_limite(request, tipo, usuario_id)
        return bool(self.redis.delete(clave))
    
    async def bloquear_ip(
        self,
        ip_address: str,
        duracion_segundos: int = 3600,
        razon: str = "Comportamiento sospechoso"
    ):
        """Bloquea una IP específica temporalmente."""
        
        clave_bloqueo = f"{self.prefijo_clave}:blocked:ip:{ip_address}"
        
        self.redis.setex(
            clave_bloqueo,
            duracion_segundos,
            json.dumps({
                "bloqueado_en": time.time(),
                "duracion": duracion_segundos,
                "razon": razon
            })
        )
    
    async def verificar_ip_bloqueada(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """Verifica si una IP está bloqueada."""
        
        clave_bloqueo = f"{self.prefijo_clave}:blocked:ip:{ip_address}"
        bloqueo_data = self.redis.get(clave_bloqueo)
        
        if bloqueo_data:
            return json.loads(bloqueo_data)
        
        return None
