"""Tareas de exportación."""

from app.workers.celery_app import celery_app
from app.core import api_logger


@celery_app.task(name="export_to_excel")
def export_to_excel_task(class_id: str, format: str = "xlsx"):
    """Exportar clase a Excel/ODS."""
    # TODO: Implementar en Fase 10
    api_logger.info("Export placeholder", class_id=class_id, format=format)
    return {"export_url": "placeholder"}
