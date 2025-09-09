"""
Configuración de Celery para Axonote.
"""

from celery import Celery

from app.core import settings

# Crear instancia de Celery
celery_app = Celery(
    "axonote",
    broker=str(settings.CELERY_BROKER_URL),
    backend=str(settings.CELERY_RESULT_BACKEND),
    include=[
        "app.tasks.processing",
        "app.tasks.export", 
        "app.tasks.notion"
    ]
)

# Configuración de Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutos máximo por tarea
    task_soft_time_limit=25 * 60,  # Soft limit a 25 minutos
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)

# Configurar ruteo de tareas por prioridad
celery_app.conf.task_routes = {
    "app.tasks.processing.*": {"queue": "processing"},
    "app.tasks.export.*": {"queue": "export"},
    "app.tasks.notion.*": {"queue": "notion"},
}

# Configurar colas
celery_app.conf.task_default_queue = "default"
celery_app.conf.task_queues = {
    "default": {"routing_key": "default"},
    "processing": {"routing_key": "processing"},
    "export": {"routing_key": "export"},
    "notion": {"routing_key": "notion"},
}
