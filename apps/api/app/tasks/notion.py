"""Tareas de sincronización con Notion."""

from app.workers.celery_app import celery_app
from app.core import api_logger


@celery_app.task(name="sync_to_notion")
def sync_to_notion_task(class_id: str):
    """Sincronizar clase con Notion."""
    # TODO: Implementar en Fase 8  
    api_logger.info("Notion sync placeholder", class_id=class_id)
    return {"notion_page_id": "placeholder"}
