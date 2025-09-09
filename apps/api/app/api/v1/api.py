"""
Router principal de API v1.
Agrupa todos los endpoints de la versión 1 de la API.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import health, settings, recordings

# Router principal de API v1
api_router = APIRouter()

# Incluir todos los endpoints
api_router.include_router(
    health.router,
    prefix="/health",
    tags=["health"]
)

api_router.include_router(
    settings.router,
    prefix="/settings", 
    tags=["settings"]
)

api_router.include_router(
    recordings.router,
    prefix="/recordings",
    tags=["recordings"]
)
