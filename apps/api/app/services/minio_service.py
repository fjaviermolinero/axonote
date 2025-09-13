"""
Servicio MinIO para gestión de almacenamiento de objetos.
Maneja subida, descarga y gestión de archivos de audio e imágenes.
"""

import asyncio
from datetime import timedelta
from typing import Any, Dict, Optional, BinaryIO
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

from app.core import settings
from app.services.base import BaseService, ServiceNotAvailableError, ServiceConfigurationError


class MinioService(BaseService):
    """Servicio para gestión de almacenamiento con MinIO."""
    
    def __init__(self):
        super().__init__("MinioService")
        self.client: Optional[Minio] = None
        self.bucket_name = settings.MINIO_BUCKET
    
    async def _setup(self) -> None:
        """Configurar cliente MinIO."""
        try:
            self.client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE
            )
            
            # Verificar y crear bucket si no existe
            await self._ensure_bucket_exists()
            
        except Exception as e:
            raise ServiceConfigurationError(
                "MinIO",
                f"Error configurando cliente MinIO: {str(e)}"
            )
    
    async def _ensure_bucket_exists(self) -> None:
        """Asegurar que el bucket existe, crearlo si no."""
        try:
            # Ejecutar en thread pool ya que minio es síncrono
            loop = asyncio.get_event_loop()
            
            bucket_exists = await loop.run_in_executor(
                None, 
                self.client.bucket_exists, 
                self.bucket_name
            )
            
            if not bucket_exists:
                await loop.run_in_executor(
                    None,
                    self.client.make_bucket,
                    self.bucket_name
                )
                self.logger.info(f"Bucket '{self.bucket_name}' creado")
            
        except S3Error as e:
            raise ServiceConfigurationError(
                "MinIO",
                f"Error gestionando bucket '{self.bucket_name}': {str(e)}"
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar salud del servicio MinIO."""
        try:
            loop = asyncio.get_event_loop()
            
            # Verificar que el bucket existe
            bucket_exists = await loop.run_in_executor(
                None,
                self.client.bucket_exists,
                self.bucket_name
            )
            
            return {
                "status": "healthy",
                "bucket_exists": bucket_exists,
                "bucket_name": self.bucket_name,
                "endpoint": settings.MINIO_ENDPOINT
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "bucket_name": self.bucket_name,
                "endpoint": settings.MINIO_ENDPOINT
            }
    
    async def upload_file(
        self,
        file_data: BinaryIO,
        object_name: str,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Subir archivo a MinIO.
        
        Args:
            file_data: Datos del archivo
            object_name: Nombre del objeto en MinIO
            content_type: Tipo MIME del archivo
            metadata: Metadatos adicionales
        
        Returns:
            URL del archivo subido
        """
        try:
            if not self.client:
                await self.initialize()
            
            loop = asyncio.get_event_loop()
            
            # Subir archivo
            await loop.run_in_executor(
                None,
                self.client.put_object,
                self.bucket_name,
                object_name,
                file_data,
                -1,  # length (auto-detect)
                content_type,
                metadata
            )
            
            # Generar URL del archivo
            file_url = f"{'https' if settings.MINIO_SECURE else 'http'}://{settings.MINIO_ENDPOINT}/{self.bucket_name}/{object_name}"
            
            self.logger.info(
                "Archivo subido a MinIO",
                object_name=object_name,
                content_type=content_type,
                url=file_url
            )
            
            return file_url
            
        except S3Error as e:
            self.logger.error(
                "Error subiendo archivo a MinIO",
                object_name=object_name,
                error=str(e)
            )
            raise ServiceNotAvailableError(
                "MinIO",
                f"Error subiendo archivo: {str(e)}"
            )
    
    async def download_file(self, object_name: str) -> bytes:
        """
        Descargar archivo de MinIO.
        
        Args:
            object_name: Nombre del objeto en MinIO
        
        Returns:
            Contenido del archivo en bytes
        """
        try:
            if not self.client:
                await self.initialize()
            
            loop = asyncio.get_event_loop()
            
            # Descargar archivo
            response = await loop.run_in_executor(
                None,
                self.client.get_object,
                self.bucket_name,
                object_name
            )
            
            content = response.read()
            response.close()
            response.release_conn()
            
            self.logger.info(
                "Archivo descargado de MinIO",
                object_name=object_name,
                size_bytes=len(content)
            )
            
            return content
            
        except S3Error as e:
            self.logger.error(
                "Error descargando archivo de MinIO",
                object_name=object_name,
                error=str(e)
            )
            raise ServiceNotAvailableError(
                "MinIO",
                f"Error descargando archivo: {str(e)}"
            )
    
    async def delete_file(self, object_name: str) -> None:
        """
        Eliminar archivo de MinIO.
        
        Args:
            object_name: Nombre del objeto a eliminar
        """
        try:
            if not self.client:
                await self.initialize()
            
            loop = asyncio.get_event_loop()
            
            await loop.run_in_executor(
                None,
                self.client.remove_object,
                self.bucket_name,
                object_name
            )
            
            self.logger.info(
                "Archivo eliminado de MinIO",
                object_name=object_name
            )
            
        except S3Error as e:
            self.logger.error(
                "Error eliminando archivo de MinIO",
                object_name=object_name,
                error=str(e)
            )
            raise ServiceNotAvailableError(
                "MinIO",
                f"Error eliminando archivo: {str(e)}"
            )
    
    async def get_presigned_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1)
    ) -> str:
        """
        Generar URL pre-firmada para acceso temporal.
        
        Args:
            object_name: Nombre del objeto
            expires: Tiempo de expiración
        
        Returns:
            URL pre-firmada
        """
        try:
            if not self.client:
                await self.initialize()
            
            loop = asyncio.get_event_loop()
            
            url = await loop.run_in_executor(
                None,
                self.client.presigned_get_object,
                self.bucket_name,
                object_name,
                expires
            )
            
            self.logger.info(
                "URL pre-firmada generada",
                object_name=object_name,
                expires_in=expires.total_seconds()
            )
            
            return url
            
        except S3Error as e:
            self.logger.error(
                "Error generando URL pre-firmada",
                object_name=object_name,
                error=str(e)
            )
            raise ServiceNotAvailableError(
                "MinIO",
                f"Error generando URL: {str(e)}"
            )
    
    async def list_files(self, prefix: str = "") -> list:
        """
        Listar archivos en el bucket.
        
        Args:
            prefix: Prefijo para filtrar archivos
        
        Returns:
            Lista de nombres de archivos
        """
        try:
            if not self.client:
                await self.initialize()
            
            loop = asyncio.get_event_loop()
            
            objects = await loop.run_in_executor(
                None,
                lambda: list(self.client.list_objects(self.bucket_name, prefix=prefix))
            )
            
            file_names = [obj.object_name for obj in objects]
            
            self.logger.info(
                "Archivos listados de MinIO",
                prefix=prefix,
                count=len(file_names)
            )
            
            return file_names
            
        except S3Error as e:
            self.logger.error(
                "Error listando archivos de MinIO",
                prefix=prefix,
                error=str(e)
            )
            raise ServiceNotAvailableError(
                "MinIO",
                f"Error listando archivos: {str(e)}"
            )


# Instancia global del servicio
minio_service = MinioService()
