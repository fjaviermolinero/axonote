"""
Endpoints de health check y monitorización del sistema.
Verifica el estado de todos los servicios críticos.
"""

import asyncio
import time
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core import settings, api_logger
from app.core.database import get_db

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.get("/detailed")
async def detailed_health_check(
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Health check detallado de todos los servicios.
    Verifica conectividad y estado de cada componente.
    """
    start_time = time.time()
    health_status = {
        "status": "healthy",
        "timestamp": start_time,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "checks": {}
    }
    
    # Verificar base de datos PostgreSQL
    try:
        result = await db.execute("SELECT 1")
        await result.fetchone()
        health_status["checks"]["database"] = {
            "status": "healthy",
            "message": "PostgreSQL connection successful",
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }
        api_logger.info("Health check: Database OK")
    except Exception as e:
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}",
            "error": str(e)
        }
        health_status["status"] = "degraded"
        api_logger.error("Health check: Database FAILED", error=str(e))
    
    # Verificar Redis (Celery broker)
    redis_start = time.time()
    try:
        import redis
        redis_client = redis.from_url(str(settings.REDIS_URL))
        redis_client.ping()
        health_status["checks"]["redis"] = {
            "status": "healthy",
            "message": "Redis connection successful",
            "response_time_ms": round((time.time() - redis_start) * 1000, 2)
        }
        api_logger.info("Health check: Redis OK")
    except Exception as e:
        health_status["checks"]["redis"] = {
            "status": "unhealthy", 
            "message": f"Redis connection failed: {str(e)}",
            "error": str(e)
        }
        health_status["status"] = "degraded"
        api_logger.error("Health check: Redis FAILED", error=str(e))
    
    # Verificar MinIO/Storage
    storage_start = time.time()
    try:
        if settings.STORAGE_BACKEND == "minio":
            from minio import Minio
            minio_client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE
            )
            # Verificar si el bucket existe
            bucket_exists = minio_client.bucket_exists(settings.MINIO_BUCKET)
            if bucket_exists:
                health_status["checks"]["storage"] = {
                    "status": "healthy",
                    "message": f"MinIO bucket '{settings.MINIO_BUCKET}' accessible",
                    "response_time_ms": round((time.time() - storage_start) * 1000, 2)
                }
            else:
                health_status["checks"]["storage"] = {
                    "status": "warning",
                    "message": f"MinIO accessible but bucket '{settings.MINIO_BUCKET}' not found"
                }
            api_logger.info("Health check: MinIO OK", bucket_exists=bucket_exists)
        else:
            health_status["checks"]["storage"] = {
                "status": "skipped",
                "message": f"Storage backend '{settings.STORAGE_BACKEND}' not implemented in health check"
            }
    except Exception as e:
        health_status["checks"]["storage"] = {
            "status": "unhealthy",
            "message": f"Storage connection failed: {str(e)}",
            "error": str(e)
        }
        health_status["status"] = "degraded"
        api_logger.error("Health check: Storage FAILED", error=str(e))
    
    # Verificar LLM local (si está configurado)
    llm_start = time.time()
    try:
        if settings.LLM_PROVIDER in ["lmstudio", "ollama"]:
            import httpx
            base_url = (
                settings.LMSTUDIO_BASE_URL 
                if settings.LLM_PROVIDER == "lmstudio" 
                else settings.OLLAMA_BASE_URL
            )
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                if settings.LLM_PROVIDER == "lmstudio":
                    response = await client.get(f"{base_url}/models")
                else:  # ollama
                    response = await client.get(f"{base_url}/api/tags")
                
                if response.status_code == 200:
                    health_status["checks"]["llm_local"] = {
                        "status": "healthy",
                        "message": f"{settings.LLM_PROVIDER.title()} server accessible",
                        "provider": settings.LLM_PROVIDER,
                        "response_time_ms": round((time.time() - llm_start) * 1000, 2)
                    }
                    api_logger.info("Health check: LLM Local OK", provider=settings.LLM_PROVIDER)
                else:
                    health_status["checks"]["llm_local"] = {
                        "status": "unhealthy",
                        "message": f"{settings.LLM_PROVIDER.title()} server returned {response.status_code}"
                    }
        else:
            health_status["checks"]["llm_local"] = {
                "status": "skipped",
                "message": f"LLM provider '{settings.LLM_PROVIDER}' not checked"
            }
    except Exception as e:
        health_status["checks"]["llm_local"] = {
            "status": "unhealthy",
            "message": f"LLM local connection failed: {str(e)}",
            "error": str(e)
        }
        api_logger.error("Health check: LLM Local FAILED", error=str(e))
    
    # Verificar Celery workers
    try:
        from celery import Celery
        celery_app = Celery(broker=str(settings.CELERY_BROKER_URL))
        
        # Obtener estadísticas de workers activos
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()
        
        if active_workers:
            worker_count = len(active_workers)
            health_status["checks"]["celery_workers"] = {
                "status": "healthy",
                "message": f"{worker_count} Celery worker(s) active",
                "worker_count": worker_count,
                "workers": list(active_workers.keys())
            }
            api_logger.info("Health check: Celery Workers OK", worker_count=worker_count)
        else:
            health_status["checks"]["celery_workers"] = {
                "status": "warning",
                "message": "No Celery workers found",
                "worker_count": 0
            }
            api_logger.warning("Health check: No Celery workers found")
    except Exception as e:
        health_status["checks"]["celery_workers"] = {
            "status": "unhealthy",
            "message": f"Celery check failed: {str(e)}",
            "error": str(e)
        }
        api_logger.error("Health check: Celery FAILED", error=str(e))
    
    # Calcular tiempo total
    total_time = time.time() - start_time
    health_status["total_check_time_ms"] = round(total_time * 1000, 2)
    
    # Determinar estado general
    unhealthy_services = [
        name for name, check in health_status["checks"].items() 
        if check["status"] == "unhealthy"
    ]
    
    if unhealthy_services:
        health_status["status"] = "unhealthy"
        health_status["unhealthy_services"] = unhealthy_services
    elif any(check["status"] == "warning" for check in health_status["checks"].values()):
        health_status["status"] = "degraded"
    
    api_logger.info(
        "Health check completado",
        status=health_status["status"],
        total_time_ms=health_status["total_check_time_ms"],
        services_checked=len(health_status["checks"])
    )
    
    return health_status


@router.get("/simple")
async def simple_health_check() -> Dict[str, Any]:
    """Health check simple y rápido."""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "message": "API is operational"
    }


@router.get("/metrics")
async def health_metrics() -> Dict[str, Any]:
    """Métricas básicas del sistema para monitorización."""
    import psutil
    import os
    
    # Métricas del sistema
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # Métricas del proceso
    process = psutil.Process(os.getpid())
    process_memory = process.memory_info()
    
    return {
        "timestamp": time.time(),
        "system": {
            "cpu_percent": cpu_percent,
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_percent": memory.percent
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "used_percent": round((disk.used / disk.total) * 100, 2)
            }
        },
        "process": {
            "memory_mb": round(process_memory.rss / (1024**2), 2),
            "cpu_percent": process.cpu_percent(),
            "pid": os.getpid(),
            "threads": process.num_threads()
        },
        "app": {
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV
        }
    }
