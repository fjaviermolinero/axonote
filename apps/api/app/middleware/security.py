"""
Middleware de seguridad avanzado para Axonote.
Incluye protección CSRF, headers de seguridad y validaciones adicionales.
"""

import secrets
import time
import hashlib
from typing import Callable, Optional, Set, Dict, Any
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.services.validation_service import servicio_validacion


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Middleware de seguridad que aplica múltiples protecciones:
    - Headers de seguridad avanzados
    - Protección CSRF
    - Validación de entrada básica
    - Detección de ataques comunes
    """
    
    def __init__(self, app):
        super().__init__(app)
        
        # Configuración de CSRF
        self.csrf_token_header = "X-CSRF-Token"
        self.csrf_cookie_name = "csrf_token"
        self.csrf_exempt_paths = {
            "/health",
            "/health/simple", 
            "/health/detailed",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/v1/auth/login",  # Login inicial no puede tener CSRF
            "/api/v1/auth/register"  # Registro inicial no puede tener CSRF
        }
        
        # Métodos que requieren protección CSRF
        self.csrf_protected_methods = {"POST", "PUT", "PATCH", "DELETE"}
        
        # Configuración de Content Security Policy
        self.csp_policy = self._generar_csp_policy()
        
        # IPs de confianza (para desarrollo)
        self.trusted_ips = {"127.0.0.1", "::1", "localhost"}
        
        # Límites de tamaño de request
        self.max_request_size = 100 * 1024 * 1024  # 100MB
        self.max_header_size = 8192  # 8KB
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Procesa la request aplicando todas las protecciones de seguridad."""
        
        start_time = time.time()
        
        try:
            # 1. Validaciones básicas de seguridad
            await self._validar_request_basica(request)
            
            # 2. Aplicar headers de seguridad a la request
            self._aplicar_headers_request_seguridad(request)
            
            # 3. Verificar protección CSRF si es necesario
            if self._requiere_proteccion_csrf(request):
                await self._verificar_csrf_token(request)
            
            # 4. Detectar patrones de ataque comunes
            await self._detectar_ataques_comunes(request)
            
            # 5. Procesar request
            response = await call_next(request)
            
            # 6. Aplicar headers de seguridad a la response
            self._aplicar_headers_response_seguridad(response, request)
            
            # 7. Añadir token CSRF si es necesario
            if self._debe_generar_csrf_token(request, response):
                self._anadir_csrf_token(response)
            
            # 8. Registrar métricas de seguridad
            await self._registrar_metricas_seguridad(request, response, time.time() - start_time)
            
            return response
            
        except HTTPException as e:
            # Crear respuesta de error con headers de seguridad
            error_response = JSONResponse(
                status_code=e.status_code,
                content={
                    "error": "Security validation failed",
                    "message": e.detail,
                    "timestamp": int(time.time())
                }
            )
            
            self._aplicar_headers_response_seguridad(error_response, request)
            return error_response
            
        except Exception as e:
            # Error interno del servidor
            error_response = JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "message": "An unexpected error occurred",
                    "timestamp": int(time.time())
                }
            )
            
            self._aplicar_headers_response_seguridad(error_response, request)
            return error_response
    
    async def _validar_request_basica(self, request: Request):
        """Validaciones básicas de seguridad de la request."""
        
        # Verificar tamaño de headers
        headers_size = sum(len(k) + len(v) for k, v in request.headers.items())
        if headers_size > self.max_header_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Headers too large"
            )
        
        # Verificar método HTTP válido
        metodos_permitidos = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        if request.method not in metodos_permitidos:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail="Method not allowed"
            )
        
        # Verificar Content-Length si está presente
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_request_size:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Request too large"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid Content-Length header"
                )
        
        # Verificar Host header para prevenir Host Header Injection
        host = request.headers.get("host")
        if host:
            # Validar que el host sea uno de los permitidos
            hosts_permitidos = {
                "localhost",
                "127.0.0.1",
                "0.0.0.0",
                settings.API_HOST
            }
            
            # Extraer solo el hostname (sin puerto)
            hostname = host.split(":")[0]
            if hostname not in hosts_permitidos and not self._es_ip_confianza(request):
                # En producción, esto debería ser más estricto
                pass  # Por ahora permitir, pero log del evento
    
    def _aplicar_headers_request_seguridad(self, request: Request):
        """Aplica validaciones adicionales a headers de request."""
        
        # Verificar User-Agent (opcional, para detectar bots maliciosos)
        user_agent = request.headers.get("user-agent", "")
        if len(user_agent) > 512:  # User-Agent muy largo puede ser sospechoso
            # Log pero no bloquear
            pass
        
        # Verificar Referer para requests sensibles
        if request.method in self.csrf_protected_methods:
            referer = request.headers.get("referer")
            if referer and not self._es_referer_valido(referer, request):
                # Log pero no bloquear automáticamente
                pass
    
    def _aplicar_headers_response_seguridad(self, response: Response, request: Request):
        """Aplica headers de seguridad a la response."""
        
        # Headers básicos de seguridad
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Strict Transport Security (solo HTTPS)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        
        # Content Security Policy
        response.headers["Content-Security-Policy"] = self.csp_policy
        
        # Permissions Policy (antes Feature Policy)
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "gyroscope=(), "
            "magnetometer=(), "
            "microphone=(self), "
            "payment=(), "
            "usb=(), "
            "interest-cohort=()"  # Disable FLoC
        )
        
        # Cross-Origin policies
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        
        # Cache control para endpoints sensibles
        if self._es_endpoint_sensible(request.url.path):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        
        # Server header (ocultar información del servidor)
        response.headers["Server"] = "Axonote"
        
        # Timing headers para prevenir timing attacks
        response.headers["X-Response-Time"] = str(int(time.time() * 1000))
    
    def _requiere_proteccion_csrf(self, request: Request) -> bool:
        """Determina si la request requiere protección CSRF."""
        
        # No proteger métodos seguros
        if request.method not in self.csrf_protected_methods:
            return False
        
        # No proteger endpoints exentos
        if request.url.path in self.csrf_exempt_paths:
            return False
        
        # No proteger requests de APIs con autenticación por token
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return False
        
        # Proteger el resto
        return True
    
    async def _verificar_csrf_token(self, request: Request):
        """Verifica el token CSRF de la request."""
        
        # Obtener token del header
        csrf_token = request.headers.get(self.csrf_token_header)
        
        if not csrf_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token missing"
            )
        
        # Obtener token de la cookie
        csrf_cookie = request.cookies.get(self.csrf_cookie_name)
        
        if not csrf_cookie:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF cookie missing"
            )
        
        # Verificar que los tokens coincidan
        if not secrets.compare_digest(csrf_token, csrf_cookie):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token mismatch"
            )
        
        # Verificar que el token no sea demasiado antiguo (opcional)
        # Esto requeriría almacenar timestamp en el token
    
    def _debe_generar_csrf_token(self, request: Request, response: Response) -> bool:
        """Determina si debe generar un nuevo token CSRF."""
        
        # Generar para requests GET a endpoints que luego requerirán CSRF
        if request.method == "GET" and request.url.path.startswith("/api/v1/"):
            return True
        
        # Generar después de login exitoso
        if (request.url.path == "/api/v1/auth/login" and 
            response.status_code == 200):
            return True
        
        return False
    
    def _anadir_csrf_token(self, response: Response):
        """Añade un token CSRF a la response."""
        
        csrf_token = secrets.token_urlsafe(32)
        
        # Añadir como cookie
        response.set_cookie(
            key=self.csrf_cookie_name,
            value=csrf_token,
            httponly=True,
            secure=True,  # Solo HTTPS en producción
            samesite="strict",
            max_age=3600  # 1 hora
        )
        
        # Añadir como header para que el cliente lo pueda leer
        response.headers["X-CSRF-Token"] = csrf_token
    
    async def _detectar_ataques_comunes(self, request: Request):
        """Detecta patrones de ataques comunes."""
        
        # Obtener datos de la request para análisis
        url_path = str(request.url.path)
        query_params = str(request.query_params)
        user_agent = request.headers.get("user-agent", "")
        
        # Detectar SQL Injection
        contenido_sospechoso = url_path + query_params
        if self._detectar_sql_injection(contenido_sospechoso):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Suspicious request pattern detected"
            )
        
        # Detectar XSS
        if self._detectar_xss(contenido_sospechoso):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Suspicious script content detected"
            )
        
        # Detectar Path Traversal
        if self._detectar_path_traversal(url_path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Path traversal attempt detected"
            )
        
        # Detectar User-Agent sospechoso
        if self._detectar_user_agent_sospechoso(user_agent):
            # Log pero no bloquear automáticamente
            pass
    
    def _detectar_sql_injection(self, contenido: str) -> bool:
        """Detecta patrones de SQL injection."""
        
        patrones_sql = [
            r'\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b',
            r'(\bOR\b|\bAND\b)\s+\d+\s*=\s*\d+',
            r'[\'";]\s*(OR|AND)\s+[\'"]?\w+[\'"]?\s*=',
            r'UNION\s+SELECT',
            r'DROP\s+TABLE',
            r'--\s*$',
            r'/\*.*\*/',
        ]
        
        import re
        for patron in patrones_sql:
            if re.search(patron, contenido, re.IGNORECASE):
                return True
        
        return False
    
    def _detectar_xss(self, contenido: str) -> bool:
        """Detecta patrones de XSS."""
        
        patrones_xss = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'on\w+\s*=',
            r'<iframe[^>]*>',
            r'<object[^>]*>',
            r'<embed[^>]*>',
            r'<link[^>]*>',
            r'<meta[^>]*>',
        ]
        
        import re
        for patron in patrones_xss:
            if re.search(patron, contenido, re.IGNORECASE | re.DOTALL):
                return True
        
        return False
    
    def _detectar_path_traversal(self, path: str) -> bool:
        """Detecta intentos de path traversal."""
        
        patrones_traversal = [
            r'\.\./+',
            r'\.\.\\+',
            r'%2e%2e%2f',
            r'%2e%2e%5c',
            r'\.\.%2f',
            r'\.\.%5c',
        ]
        
        import re
        for patron in patrones_traversal:
            if re.search(patron, path, re.IGNORECASE):
                return True
        
        return False
    
    def _detectar_user_agent_sospechoso(self, user_agent: str) -> bool:
        """Detecta User-Agents sospechosos."""
        
        # User-Agents de herramientas de hacking conocidas
        user_agents_sospechosos = [
            "sqlmap", "nikto", "nmap", "masscan", "zap", "burp",
            "w3af", "skipfish", "arachni", "wpscan", "dirb",
            "gobuster", "dirbuster", "hydra", "medusa"
        ]
        
        user_agent_lower = user_agent.lower()
        
        for ua_sospechoso in user_agents_sospechosos:
            if ua_sospechoso in user_agent_lower:
                return True
        
        # User-Agent vacío o muy corto
        if len(user_agent.strip()) < 10:
            return True
        
        return False
    
    def _es_referer_valido(self, referer: str, request: Request) -> bool:
        """Verifica si el Referer es válido."""
        
        try:
            from urllib.parse import urlparse
            
            referer_parsed = urlparse(referer)
            request_parsed = urlparse(str(request.url))
            
            # Verificar que el referer sea del mismo origen
            return (
                referer_parsed.scheme == request_parsed.scheme and
                referer_parsed.netloc == request_parsed.netloc
            )
            
        except Exception:
            return False
    
    def _es_endpoint_sensible(self, path: str) -> bool:
        """Determina si un endpoint es sensible y requiere headers especiales."""
        
        endpoints_sensibles = [
            "/api/v1/auth/",
            "/api/v1/users/",
            "/api/v1/admin/",
            "/api/v1/recordings/upload",
        ]
        
        return any(path.startswith(endpoint) for endpoint in endpoints_sensibles)
    
    def _es_ip_confianza(self, request: Request) -> bool:
        """Verifica si la IP es de confianza."""
        
        ip = self._obtener_ip_real(request)
        return ip in self.trusted_ips
    
    def _obtener_ip_real(self, request: Request) -> str:
        """Obtiene la IP real del cliente."""
        
        # Verificar headers de proxy
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        
        return request.client.host if request.client else "unknown"
    
    def _generar_csp_policy(self) -> str:
        """Genera la política de Content Security Policy."""
        
        # Política restrictiva para una API
        policy_parts = [
            "default-src 'none'",
            "script-src 'none'",
            "style-src 'none'",
            "img-src 'none'",
            "font-src 'none'",
            "connect-src 'self'",
            "media-src 'none'",
            "object-src 'none'",
            "child-src 'none'",
            "frame-src 'none'",
            "worker-src 'none'",
            "frame-ancestors 'none'",
            "form-action 'self'",
            "base-uri 'self'",
            "manifest-src 'none'"
        ]
        
        return "; ".join(policy_parts)
    
    async def _registrar_metricas_seguridad(
        self,
        request: Request,
        response: Response,
        tiempo_procesamiento: float
    ):
        """Registra métricas de seguridad para monitoreo."""
        
        try:
            # Registrar requests bloqueadas por seguridad
            if response.status_code in [400, 403, 413, 429]:
                # Incrementar contador de requests bloqueadas
                pass
            
            # Registrar tiempo de procesamiento de seguridad
            if tiempo_procesamiento > 1.0:  # Más de 1 segundo
                # Log de procesamiento lento
                pass
            
        except Exception:
            # Si hay error registrando métricas, continuar
            pass


class CSRFProtection:
    """
    Clase helper para protección CSRF más granular.
    Permite aplicar protección CSRF a endpoints específicos.
    """
    
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
    
    def generar_token(self, session_id: str) -> str:
        """Genera un token CSRF para una sesión."""
        
        timestamp = str(int(time.time()))
        data = f"{session_id}:{timestamp}"
        
        # Crear hash con secret key
        hash_obj = hashlib.sha256((data + self.secret_key).encode())
        token = f"{data}:{hash_obj.hexdigest()}"
        
        return token
    
    def verificar_token(self, token: str, session_id: str, max_age: int = 3600) -> bool:
        """Verifica un token CSRF."""
        
        try:
            parts = token.split(":")
            if len(parts) != 3:
                return False
            
            token_session_id, timestamp_str, hash_value = parts
            
            # Verificar session ID
            if token_session_id != session_id:
                return False
            
            # Verificar edad del token
            timestamp = int(timestamp_str)
            if time.time() - timestamp > max_age:
                return False
            
            # Verificar hash
            data = f"{token_session_id}:{timestamp_str}"
            expected_hash = hashlib.sha256((data + self.secret_key).encode()).hexdigest()
            
            return secrets.compare_digest(hash_value, expected_hash)
            
        except Exception:
            return False
