"""
Configuración de base de datos SQLAlchemy para Axonote.
Incluye configuración de conexión, sesiones y utilidades.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import StaticPool

from app.core.config import settings

# Base para modelos SQLAlchemy
Base = declarative_base()

# Importar todos los modelos para que SQLAlchemy los registre
def import_models():
    """Importar todos los modelos para registro en metadata."""
    from app.models import class_session, professor, source, term, card  # noqa

# Configurar engine con opciones optimizadas
engine_kwargs = {
    "echo": settings.DATABASE_ECHO,
    "pool_size": settings.DATABASE_POOL_SIZE,
    "max_overflow": settings.DATABASE_MAX_OVERFLOW,
    "pool_pre_ping": True,  # Verificar conexiones antes de usar
}

# Para testing, usar SQLite en memoria con configuración especial
if "sqlite" in str(settings.DATABASE_URL):
    engine_kwargs.update({
        "poolclass": StaticPool,
        "connect_args": {"check_same_thread": False}
    })

# Crear engine asíncrono
engine = create_async_engine(
    str(settings.DATABASE_URL),
    **engine_kwargs
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependencia para obtener sesión de base de datos.
    Se usa en FastAPI endpoints con Depends().
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Alias para compatibilidad
get_async_db = get_db


async def create_tables():
    """
    Crear todas las tablas en la base de datos.
    Usado para testing y setup inicial.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables():
    """
    Eliminar todas las tablas de la base de datos.
    Usado para testing y reset de desarrollo.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def check_db_connection() -> bool:
    """
    Verificar conexión a la base de datos.
    Retorna True si la conexión es exitosa.
    """
    try:
        async with AsyncSessionLocal() as session:
            await session.execute("SELECT 1")
            return True
    except Exception:
        return False
