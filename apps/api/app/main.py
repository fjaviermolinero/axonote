"""
Aplicación principal FastAPI para Axonote.
Punto de entrada de la API con configuración de middlewares y routers.
"""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
import time
from typing import Callable

from app.core import settings, setup_logging, SecurityHeaders, api_logger
from app.api.v1.api import api_router


# Configurar logging al inicio
setup_logging()

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

# Crear aplicación FastAPI
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.ENABLE_SWAGGER else None,
    docs_url="/docs" if settings.ENABLE_SWAGGER else None,
    redoc_url="/redoc" if settings.ENABLE_REDOC else None,
)

# Configurar rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ==============================================
# MIDDLEWARES
# ==============================================

@app.middleware("http")
async def add_security_headers(request: Request, call_next: Callable) -> Response:
    """Añadir headers de seguridad a todas las respuestas."""
    response = await call_next(request)
    
    # Añadir headers de seguridad
    security_headers = SecurityHeaders.get_security_headers()
    for header, value in security_headers.items():
        response.headers[header] = value
    
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next: Callable) -> Response:
    """Middleware para logging de requests."""
    start_time = time.time()
    
    # Log request inicio
    api_logger.info(
        "Request iniciado",
        method=request.method,
        path=request.url.path,
        query_params=str(request.query_params),
        user_agent=request.headers.get("user-agent"),
        client_ip=get_remote_address(request)
    )
    
    # Procesar request
    response = await call_next(request)
    
    # Calcular tiempo de procesamiento
    process_time = time.time() - start_time
    
    # Log response
    api_logger.info(
        "Request completado",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        process_time_ms=round(process_time * 1000, 2)
    )
    
    # Añadir header de tiempo de procesamiento
    response.headers["X-Process-Time"] = str(process_time)
    
    return response


# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware GZip para compresión
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Middleware para hosts confiables (solo en producción)
if settings.APP_ENV == "production":
    app.add_middleware(
        TrustedHostMiddleware, 
        allowed_hosts=["*"]  # Configurar según necesidades
    )


# ==============================================
# EXCEPTION HANDLERS
# ==============================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handler global para excepciones no manejadas."""
    api_logger.error(
        "Excepción no manejada",
        method=request.method,
        path=request.url.path,
        error_type=type(exc).__name__,
        error_message=str(exc),
        client_ip=get_remote_address(request)
    )
    
    # En desarrollo, mostrar detalles del error
    if settings.DEBUG:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Error interno del servidor",
                "detail": str(exc),
                "type": type(exc).__name__
            }
        )
    
    # En producción, mensaje genérico
    return JSONResponse(
        status_code=500,
        content={
            "error": "Error interno del servidor",
            "message": "Ha ocurrido un error inesperado. Por favor, inténtalo de nuevo."
        }
    )


# ==============================================
# ROUTERS
# ==============================================

# Incluir router principal de API v1
app.include_router(
    api_router, 
    prefix=settings.API_V1_STR,
    tags=["api-v1"]
)


# ==============================================
# ENDPOINTS BÁSICOS
# ==============================================

@app.get("/")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def root(request: Request) -> dict:
    """Endpoint raíz con información básica."""
    return {
        "message": f"Bienvenido a {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "api_docs": "/docs" if settings.ENABLE_SWAGGER else None,
        "status": "operational"
    }


@app.get("/health")
@limiter.limit("30/minute")
async def health_check(request: Request) -> dict:
    """Endpoint de health check para monitorización."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "services": {
            "api": "operational",
            "database": "pending",  # Se verificará en endpoints específicos
            "redis": "pending",     # Se verificará en endpoints específicos
            "storage": "pending"    # Se verificará en endpoints específicos
        }
    }


@app.get("/ping")
@limiter.limit("100/minute")
async def ping(request: Request) -> dict:
    """Endpoint simple de ping para verificación básica."""
    return {"message": "pong", "timestamp": time.time()}


# ==============================================
# STARTUP/SHUTDOWN EVENTS
# ==============================================

@app.on_event("startup")
async def startup_event():
    """Eventos de inicio de la aplicación."""
    api_logger.info(
        "Iniciando Axonote API",
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
        debug=settings.DEBUG
    )
    
    # TODO: Verificar conexiones a servicios externos
    # - Base de datos PostgreSQL
    # - Redis
    # - MinIO/Storage
    # - LLM local (si está disponible)


@app.on_event("shutdown")
async def shutdown_event():
    """Eventos de cierre de la aplicación."""
    api_logger.info(
        "Cerrando Axonote API",
        version=settings.APP_VERSION
    )
    
    # TODO: Cerrar conexiones y limpiar recursos


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
