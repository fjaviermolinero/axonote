"""
Servicio ChunkService - Gestión de uploads por chunks.
Maneja el ciclo completo de upload chunked con recovery y validación.
"""

import asyncio
import hashlib
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from io import BytesIO
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import UploadFile

from app.core import settings, api_logger
from app.core.security import sanitize_filename
from app.models import UploadSession, ChunkUpload, ClassSession, EstadoUpload
from app.services.base import BaseService, ServiceConfigurationError, ServiceNotAvailableError
from app.services.minio_service import minio_service


class ChunkService(BaseService):
    """Servicio para gestión de uploads por chunks con recovery automático."""
    
    def __init__(self):
        super().__init__()
        self.temp_dir = Path(tempfile.gettempdir()) / "axonote_chunks"
        self.max_chunk_size = settings.MAX_CHUNK_SIZE_MB * 1024 * 1024  # MB a bytes
        self.session_timeout_hours = 24
        
    async def _setup(self) -> None:
        """Configurar servicio de chunks."""
        try:
            # Crear directorio temporal para chunks si no existe
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            
            self.logger.info(
                "ChunkService configurado",
                temp_dir=str(self.temp_dir),
                max_chunk_size_mb=settings.MAX_CHUNK_SIZE_MB
            )
            
        except Exception as e:
            raise ServiceConfigurationError(
                "ChunkService",
                f"Error configurando directorio temporal: {str(e)}"
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar salud del servicio de chunks."""
        try:
            # Verificar que el directorio temporal es accesible
            test_file = self.temp_dir / "health_check.tmp"
            test_file.write_text("test")
            test_file.unlink()
            
            # Verificar MinIO
            minio_health = await minio_service.health_check()
            
            return {
                "status": "healthy",
                "temp_dir": str(self.temp_dir),
                "temp_dir_writable": True,
                "max_chunk_size_mb": settings.MAX_CHUNK_SIZE_MB,
                "minio_available": minio_health.get("status") == "healthy"
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "temp_dir": str(self.temp_dir)
            }
    
    async def create_upload_session(
        self,
        db: AsyncSession,
        class_session_id: str,
        filename: str,
        content_type: str,
        file_size_total: Optional[int] = None,
        chunk_size: Optional[int] = None,
        file_checksum: Optional[str] = None
    ) -> UploadSession:
        """
        Crear nueva sesión de upload por chunks.
        
        Args:
            db: Sesión de base de datos
            class_session_id: ID de la sesión de clase
            filename: Nombre original del archivo
            content_type: Tipo MIME
            file_size_total: Tamaño total del archivo (opcional)
            chunk_size: Tamaño de chunk personalizado (opcional)
            file_checksum: Checksum esperado del archivo completo (opcional)
        
        Returns:
            Sesión de upload creada
        """
        try:
            # Verificar que la sesión de clase existe
            result = await db.execute(
                select(ClassSession).where(ClassSession.id == class_session_id)
            )
            class_session = result.scalar_one_or_none()
            
            if not class_session:
                raise ValueError(f"ClassSession {class_session_id} no encontrada")
            
            # Sanitizar nombre de archivo
            filename_sanitized = sanitize_filename(filename)
            
            # Configurar chunk size
            chunk_size = chunk_size or (settings.MAX_CHUNK_SIZE_MB * 1024 * 1024)
            
            # Calcular chunks esperados
            total_chunks_expected = None
            if file_size_total:
                total_chunks_expected = (file_size_total + chunk_size - 1) // chunk_size
            
            # Generar rutas de storage
            storage_path_chunks = f"uploads/{class_session_id}/chunks"
            
            # Crear sesión de upload
            upload_session = UploadSession(
                class_session_id=class_session_id,
                filename_original=filename,
                filename_sanitized=filename_sanitized,
                content_type=content_type,
                file_size_total=file_size_total,
                chunk_size=chunk_size,
                total_chunks_expected=total_chunks_expected,
                file_checksum_expected=file_checksum,
                storage_path_chunks=storage_path_chunks,
                expires_at=UploadSession.default_expiration()
            )
            
            db.add(upload_session)
            await db.commit()
            await db.refresh(upload_session)
            
            self.logger.info(
                "Sesión de upload creada",
                upload_session_id=str(upload_session.id),
                class_session_id=class_session_id,
                filename=filename_sanitized,
                total_chunks=total_chunks_expected,
                chunk_size_mb=chunk_size / (1024 * 1024)
            )
            
            return upload_session
            
        except Exception as e:
            self.logger.error(
                "Error creando sesión de upload",
                class_session_id=class_session_id,
                filename=filename,
                error=str(e)
            )
            raise ServiceNotAvailableError(
                "ChunkService",
                f"Error creando sesión de upload: {str(e)}"
            )
    
    async def upload_chunk(
        self,
        db: AsyncSession,
        upload_session_id: str,
        chunk_number: int,
        chunk_data: bytes,
        total_chunks: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Subir un chunk individual.
        
        Args:
            db: Sesión de base de datos
            upload_session_id: ID de la sesión de upload
            chunk_number: Número del chunk (1-based)
            chunk_data: Datos del chunk
            total_chunks: Total de chunks esperados (para actualizar si es necesario)
        
        Returns:
            Información del chunk subido
        """
        try:
            # Obtener sesión de upload
            result = await db.execute(
                select(UploadSession).where(UploadSession.id == upload_session_id)
            )
            upload_session = result.scalar_one_or_none()
            
            if not upload_session:
                raise ValueError(f"UploadSession {upload_session_id} no encontrada")
            
            if not upload_session.is_active:
                raise ValueError(f"Sesión de upload inactiva: {upload_session.estado}")
            
            if upload_session.is_expired:
                upload_session.estado = EstadoUpload.EXPIRADO
                await db.commit()
                raise ValueError("Sesión de upload expirada")
            
            # Validar chunk
            chunk_size = len(chunk_data)
            if chunk_size > self.max_chunk_size:
                raise ValueError(f"Chunk demasiado grande: {chunk_size} bytes")
            
            # Verificar si el chunk ya fue recibido
            if upload_session.is_chunk_received(chunk_number):
                self.logger.warning(
                    "Chunk duplicado recibido",
                    upload_session_id=upload_session_id,
                    chunk_number=chunk_number
                )
                return {
                    "status": "duplicate",
                    "message": "Chunk ya fue recibido anteriormente"
                }
            
            # Calcular checksum del chunk
            chunk_checksum = hashlib.md5(chunk_data).hexdigest()
            
            # Guardar chunk en storage temporal
            chunk_path = await self._store_chunk_temporarily(
                upload_session_id, chunk_number, chunk_data
            )
            
            # Subir chunk a MinIO
            object_name = f"{upload_session.storage_path_chunks}/chunk_{chunk_number:06d}"
            chunk_file = BytesIO(chunk_data)
            
            await minio_service.upload_file(
                chunk_file,
                object_name,
                content_type="application/octet-stream",
                metadata={
                    "upload_session_id": upload_session_id,
                    "chunk_number": str(chunk_number),
                    "chunk_size": str(chunk_size),
                    "chunk_checksum": chunk_checksum
                }
            )
            
            # Actualizar metadata de la sesión
            upload_session.add_chunk_metadata(chunk_number, chunk_size, chunk_checksum)
            
            # Actualizar total de chunks si se proporciona
            if total_chunks and upload_session.total_chunks_expected != total_chunks:
                upload_session.total_chunks_expected = total_chunks
            
            # Actualizar estado
            if upload_session.estado == EstadoUpload.INICIADO:
                upload_session.estado = EstadoUpload.SUBIENDO
            
            # Crear registro de chunk individual
            chunk_upload = ChunkUpload(
                upload_session_id=upload_session.id,
                chunk_number=chunk_number,
                chunk_size=chunk_size,
                chunk_checksum=chunk_checksum,
                storage_path=object_name,
                content_type="application/octet-stream"
            )
            
            db.add(chunk_upload)
            await db.commit()
            
            self.logger.info(
                "Chunk subido exitosamente",
                upload_session_id=upload_session_id,
                chunk_number=chunk_number,
                chunk_size=chunk_size,
                progress=f"{upload_session.chunks_received}/{upload_session.total_chunks_expected or '?'}"
            )
            
            # Verificar si todos los chunks están completos
            is_complete = (
                upload_session.total_chunks_expected and 
                upload_session.chunks_received >= upload_session.total_chunks_expected
            )
            
            return {
                "status": "received",
                "chunk_number": chunk_number,
                "chunk_size": chunk_size,
                "chunk_checksum": chunk_checksum,
                "chunks_received": upload_session.chunks_received,
                "total_chunks": upload_session.total_chunks_expected,
                "progress_percentage": upload_session.progress_percentage,
                "is_complete": is_complete,
                "upload_ready_for_assembly": is_complete
            }
            
        except Exception as e:
            self.logger.error(
                "Error subiendo chunk",
                upload_session_id=upload_session_id,
                chunk_number=chunk_number,
                error=str(e)
            )
            
            # Marcar sesión como error si es crítico
            if "no encontrada" in str(e) or "expirada" in str(e):
                try:
                    upload_session.mark_as_error(str(e))
                    await db.commit()
                except:
                    pass
            
            raise ServiceNotAvailableError(
                "ChunkService",
                f"Error subiendo chunk: {str(e)}"
            )
    
    async def assemble_file(
        self,
        db: AsyncSession,
        upload_session_id: str,
        validate_checksum: bool = True
    ) -> str:
        """
        Ensamblar archivo final a partir de los chunks.
        
        Args:
            db: Sesión de base de datos
            upload_session_id: ID de la sesión de upload
            validate_checksum: Si validar checksum del archivo final
        
        Returns:
            URL del archivo final ensamblado
        """
        try:
            # Obtener sesión de upload
            result = await db.execute(
                select(UploadSession).where(UploadSession.id == upload_session_id)
            )
            upload_session = result.scalar_one_or_none()
            
            if not upload_session:
                raise ValueError(f"UploadSession {upload_session_id} no encontrada")
            
            if upload_session.is_completed:
                return upload_session.final_file_url
            
            # Verificar que todos los chunks están presentes
            missing_chunks = upload_session.chunks_missing_list
            if missing_chunks:
                raise ValueError(f"Chunks faltantes: {missing_chunks}")
            
            upload_session.estado = EstadoUpload.ENSAMBLANDO
            await db.commit()
            
            self.logger.info(
                "Iniciando ensamblado de archivo",
                upload_session_id=upload_session_id,
                total_chunks=upload_session.total_chunks_expected,
                filename=upload_session.filename_sanitized
            )
            
            # Crear archivo temporal para ensamblado
            temp_file_path = self.temp_dir / f"assembly_{upload_session_id}.tmp"
            
            # Ensamblar chunks en orden
            with open(temp_file_path, 'wb') as final_file:
                for chunk_num in range(1, upload_session.total_chunks_expected + 1):
                    chunk_object = f"{upload_session.storage_path_chunks}/chunk_{chunk_num:06d}"
                    
                    # Descargar chunk de MinIO
                    chunk_data = await minio_service.download_file(chunk_object)
                    final_file.write(chunk_data)
            
            # Validar checksum si está disponible
            final_checksum = None
            if validate_checksum or upload_session.file_checksum_expected:
                final_checksum = await self._calculate_file_checksum(temp_file_path)
                
                if upload_session.file_checksum_expected:
                    if final_checksum != upload_session.file_checksum_expected:
                        raise ValueError(
                            f"Checksum no coincide. Esperado: {upload_session.file_checksum_expected}, "
                            f"Actual: {final_checksum}"
                        )
            
            # Subir archivo final a MinIO
            final_object_name = f"recordings/{upload_session.class_session_id}/{upload_session.filename_sanitized}"
            
            with open(temp_file_path, 'rb') as final_file:
                final_url = await minio_service.upload_file(
                    final_file,
                    final_object_name,
                    content_type=upload_session.content_type,
                    metadata={
                        "upload_session_id": upload_session_id,
                        "original_filename": upload_session.filename_original,
                        "total_chunks": str(upload_session.total_chunks_expected),
                        "file_checksum": final_checksum or "",
                        "assembled_at": datetime.utcnow().isoformat()
                    }
                )
            
            # Limpiar archivo temporal
            temp_file_path.unlink()
            
            # Actualizar sesión como completada
            upload_session.mark_as_completed(final_url, final_checksum)
            upload_session.storage_path_final = final_object_name
            
            await db.commit()
            
            # Limpiar chunks temporales (opcional, en background)
            asyncio.create_task(self._cleanup_chunks(upload_session_id))
            
            self.logger.info(
                "Archivo ensamblado exitosamente",
                upload_session_id=upload_session_id,
                final_url=final_url,
                file_size=upload_session.bytes_uploaded,
                checksum=final_checksum
            )
            
            return final_url
            
        except Exception as e:
            self.logger.error(
                "Error ensamblando archivo",
                upload_session_id=upload_session_id,
                error=str(e)
            )
            
            # Marcar sesión como error
            try:
                upload_session.mark_as_error(f"Error en ensamblado: {str(e)}")
                await db.commit()
            except:
                pass
            
            raise ServiceNotAvailableError(
                "ChunkService",
                f"Error ensamblando archivo: {str(e)}"
            )
    
    async def get_upload_status(
        self,
        db: AsyncSession,
        upload_session_id: str
    ) -> Dict[str, Any]:
        """
        Obtener estado detallado de una sesión de upload.
        
        Args:
            db: Sesión de base de datos
            upload_session_id: ID de la sesión de upload
        
        Returns:
            Estado detallado de la sesión
        """
        try:
            result = await db.execute(
                select(UploadSession).where(UploadSession.id == upload_session_id)
            )
            upload_session = result.scalar_one_or_none()
            
            if not upload_session:
                raise ValueError(f"UploadSession {upload_session_id} no encontrada")
            
            # Verificar expiración
            if upload_session.is_expired and upload_session.is_active:
                upload_session.estado = EstadoUpload.EXPIRADO
                await db.commit()
            
            return {
                "upload_session_id": upload_session_id,
                "estado": upload_session.estado,
                "filename": upload_session.filename_sanitized,
                "content_type": upload_session.content_type,
                "chunks_received": upload_session.chunks_received,
                "total_chunks_expected": upload_session.total_chunks_expected,
                "progress_percentage": upload_session.progress_percentage,
                "bytes_uploaded": upload_session.bytes_uploaded,
                "file_size_total": upload_session.file_size_total,
                "upload_speed_mbps": upload_session.upload_speed_mbps,
                "eta_seconds": upload_session.eta_seconds,
                "missing_chunks": upload_session.chunks_missing_list,
                "started_at": upload_session.started_at,
                "last_chunk_at": upload_session.last_chunk_at,
                "expires_at": upload_session.expires_at,
                "is_expired": upload_session.is_expired,
                "is_completed": upload_session.is_completed,
                "has_error": upload_session.has_error,
                "error_message": upload_session.error_message,
                "final_file_url": upload_session.final_file_url,
                "retry_count": upload_session.retry_count
            }
            
        except Exception as e:
            self.logger.error(
                "Error obteniendo estado de upload",
                upload_session_id=upload_session_id,
                error=str(e)
            )
            raise ServiceNotAvailableError(
                "ChunkService",
                f"Error obteniendo estado: {str(e)}"
            )
    
    async def cleanup_expired_sessions(self, db: AsyncSession) -> int:
        """
        Limpiar sesiones de upload expiradas.
        
        Args:
            db: Sesión de base de datos
        
        Returns:
            Número de sesiones limpiadas
        """
        try:
            # Encontrar sesiones expiradas
            result = await db.execute(
                select(UploadSession).where(
                    UploadSession.expires_at < datetime.utcnow(),
                    UploadSession.estado.in_([
                        EstadoUpload.INICIADO,
                        EstadoUpload.SUBIENDO,
                        EstadoUpload.VALIDANDO,
                        EstadoUpload.ENSAMBLANDO
                    ])
                )
            )
            expired_sessions = result.scalars().all()
            
            cleanup_count = 0
            for session in expired_sessions:
                try:
                    # Marcar como expirada
                    session.estado = EstadoUpload.EXPIRADO
                    
                    # Limpiar chunks de MinIO
                    await self._cleanup_chunks(str(session.id))
                    
                    cleanup_count += 1
                    
                except Exception as e:
                    self.logger.error(
                        "Error limpiando sesión expirada",
                        upload_session_id=str(session.id),
                        error=str(e)
                    )
            
            await db.commit()
            
            if cleanup_count > 0:
                self.logger.info(
                    "Sesiones expiradas limpiadas",
                    count=cleanup_count
                )
            
            return cleanup_count
            
        except Exception as e:
            self.logger.error(
                "Error en cleanup de sesiones expiradas",
                error=str(e)
            )
            return 0
    
    async def _store_chunk_temporarily(
        self,
        upload_session_id: str,
        chunk_number: int,
        chunk_data: bytes
    ) -> str:
        """Guardar chunk temporalmente en disco local."""
        chunk_dir = self.temp_dir / upload_session_id
        chunk_dir.mkdir(parents=True, exist_ok=True)
        
        chunk_path = chunk_dir / f"chunk_{chunk_number:06d}"
        
        with open(chunk_path, 'wb') as f:
            f.write(chunk_data)
        
        return str(chunk_path)
    
    async def _calculate_file_checksum(self, file_path: Path) -> str:
        """Calcular checksum MD5 de un archivo."""
        hash_md5 = hashlib.md5()
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        
        return hash_md5.hexdigest()
    
    async def _cleanup_chunks(self, upload_session_id: str) -> None:
        """Limpiar chunks temporales de una sesión."""
        try:
            # Limpiar directorio temporal local
            chunk_dir = self.temp_dir / upload_session_id
            if chunk_dir.exists():
                shutil.rmtree(chunk_dir)
            
            # TODO: Limpiar chunks de MinIO (opcional, pueden mantenerse para recovery)
            # Los chunks en MinIO pueden mantenerse por un tiempo para permitir recovery
            
            self.logger.info(
                "Chunks temporales limpiados",
                upload_session_id=upload_session_id
            )
            
        except Exception as e:
            self.logger.error(
                "Error limpiando chunks temporales",
                upload_session_id=upload_session_id,
                error=str(e)
            )


# Instancia global del servicio
chunk_service = ChunkService()
