# AxoNote API

API backend para AxoNote - Plataforma PWA para grabación y transcripción de clases médicas.

## Características

- FastAPI con documentación automática
- Base de datos PostgreSQL con SQLAlchemy
- Procesamiento de audio con Whisper
- Sistema de autenticación JWT
- Integración con servicios de almacenamiento (MinIO)
- Procesamiento asíncrono con Celery
- Análisis LLM y post-procesamiento
- Integración con fuentes médicas

## Desarrollo

```bash
# Instalar dependencias
poetry install

# Ejecutar migraciones
alembic upgrade head

# Ejecutar aplicación
uvicorn app.main:app --reload
```
