"""
Modelo UploadSession - Gestión de subidas por chunks.
Maneja el estado de uploads chunked con recovery y validación de integridad.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import enum

from sqlalchemy import (
    Column, String, Text, Integer, Float, DateTime, 
    Enum, ForeignKey, JSON, Boolean
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class EstadoUpload(str, enum.Enum):
    """Estados del proceso de upload por chunks."""
    INICIADO = "iniciado"           # Sesión creada, esperando chunks
    SUBIENDO = "subiendo"           # Chunks siendo subidos
    VALIDANDO = "validando"         # Verificando integridad de chunks
    ENSAMBLANDO = "ensamblando"     # Uniendo chunks en archivo final
    COMPLETADO = "completado"       # Upload exitoso, archivo listo
    ERROR = "error"                 # Error en el proceso
    CANCELADO = "cancelado"         # Cancelado por usuario
    EXPIRADO = "expirado"           # Sesión expirada por timeout


class UploadSession(BaseModel):
    """
    Sesión de upload por chunks para grabaciones de audio.
    
    Gestiona el estado completo de un upload chunked con:
    - Tracking de chunks individuales
    - Validación de integridad
    - Recovery automático
    - Timeout y cleanup
    """
    
    __tablename__ = "upload_sessions"
    
    # ==============================================
    # INFORMACIÓN BÁSICA DE LA SESIÓN
    # ==============================================
    
    # ID de la sesión de clase asociada
    class_session_id = Column(UUID(as_uuid=True), ForeignKey("class_sessions.id"), nullable=False, index=True)
    
    # Información del archivo
    filename_original = Column(String(500), nullable=False)
    filename_sanitized = Column(String(500), nullable=False)
    content_type = Column(String(100), nullable=False)
    file_size_total = Column(Integer, nullable=True)  # Tamaño total estimado en bytes
    
    # ==============================================
    # CONFIGURACIÓN DE CHUNKS
    # ==============================================
    
    chunk_size = Column(Integer, nullable=False, default=10485760)  # 10MB por defecto
    total_chunks_expected = Column(Integer, nullable=True)
    chunks_received = Column(Integer, nullable=False, default=0)
    
    # ==============================================
    # ESTADO Y CONTROL
    # ==============================================
    
    estado = Column(
        Enum(EstadoUpload),
        nullable=False,
        default=EstadoUpload.INICIADO,
        index=True
    )
    
    # Timestamps importantes
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_chunk_at = Column(DateTime, nullable=True)  # Último chunk recibido
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)    # Expiración de la sesión
    
    # ==============================================
    # TRACKING DE CHUNKS
    # ==============================================
    
    # Metadata de chunks recibidos: {chunk_number: {size, checksum, received_at}}
    chunks_metadata = Column(JSON, nullable=False, default=dict)
    
    # Lista de chunks faltantes (para recovery)
    missing_chunks = Column(JSON, nullable=False, default=list)
    
    # ==============================================
    # VALIDACIÓN E INTEGRIDAD
    # ==============================================
    
    # Checksum del archivo completo (MD5 o SHA256)
    file_checksum_expected = Column(String(128), nullable=True)
    file_checksum_actual = Column(String(128), nullable=True)
    
    # Validación de chunks individuales
    chunk_validation_enabled = Column(Boolean, nullable=False, default=True)
    
    # ==============================================
    # STORAGE Y UBICACIÓN
    # ==============================================
    
    # Ruta base en MinIO para los chunks
    storage_path_chunks = Column(String(1000), nullable=False)
    
    # Ruta del archivo final ensamblado
    storage_path_final = Column(String(1000), nullable=True)
    
    # URL final del archivo (cuando esté completado)
    final_file_url = Column(String(1000), nullable=True)
    
    # ==============================================
    # INFORMACIÓN DE ERRORES
    # ==============================================
    
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    
    # ==============================================
    # MÉTRICAS DE RENDIMIENTO
    # ==============================================
    
    bytes_uploaded = Column(Integer, nullable=False, default=0)
    upload_speed_bps = Column(Float, nullable=True)  # Bytes por segundo promedio
    total_upload_time_sec = Column(Float, nullable=True)
    
    # ==============================================
    # RELACIONES
    # ==============================================
    
    class_session = relationship("ClassSession", back_populates="upload_sessions")
    
    def __repr__(self) -> str:
        return (
            f"<UploadSession("
            f"id={self.id}, "
            f"class_session_id={self.class_session_id}, "
            f"estado='{self.estado}', "
            f"chunks={self.chunks_received}/{self.total_chunks_expected}, "
            f"filename='{self.filename_sanitized}'"
            f")>"
        )
    
    @property
    def is_active(self) -> bool:
        """True si la sesión está activa (no completada, cancelada o expirada)."""
        return self.estado in [EstadoUpload.INICIADO, EstadoUpload.SUBIENDO, EstadoUpload.VALIDANDO, EstadoUpload.ENSAMBLANDO]
    
    @property
    def is_completed(self) -> bool:
        """True si el upload está completado exitosamente."""
        return self.estado == EstadoUpload.COMPLETADO
    
    @property
    def has_error(self) -> bool:
        """True si hay error en el upload."""
        return self.estado == EstadoUpload.ERROR
    
    @property
    def is_expired(self) -> bool:
        """True si la sesión ha expirado."""
        return datetime.utcnow() > self.expires_at
    
    @property
    def progress_percentage(self) -> float:
        """Porcentaje de progreso del upload (0-100)."""
        if not self.total_chunks_expected or self.total_chunks_expected == 0:
            return 0.0
        
        return min(100.0, (self.chunks_received / self.total_chunks_expected) * 100.0)
    
    @property
    def upload_speed_mbps(self) -> Optional[float]:
        """Velocidad de upload en MB/s."""
        if self.upload_speed_bps:
            return self.upload_speed_bps / (1024 * 1024)
        return None
    
    @property
    def eta_seconds(self) -> Optional[int]:
        """Tiempo estimado restante en segundos."""
        if not self.upload_speed_bps or not self.file_size_total:
            return None
        
        bytes_remaining = self.file_size_total - self.bytes_uploaded
        if bytes_remaining <= 0:
            return 0
        
        return int(bytes_remaining / self.upload_speed_bps)
    
    @property
    def chunks_missing_list(self) -> list:
        """Lista de números de chunks faltantes."""
        if not self.total_chunks_expected:
            return []
        
        received_chunks = set(self.chunks_metadata.keys())
        expected_chunks = set(range(1, self.total_chunks_expected + 1))
        missing = expected_chunks - received_chunks
        
        return sorted(list(missing))
    
    def add_chunk_metadata(self, chunk_number: int, size: int, checksum: Optional[str] = None) -> None:
        """
        Agregar metadata de un chunk recibido.
        
        Args:
            chunk_number: Número del chunk (1-based)
            size: Tamaño del chunk en bytes
            checksum: Checksum del chunk (opcional)
        """
        if not self.chunks_metadata:
            self.chunks_metadata = {}
        
        self.chunks_metadata[str(chunk_number)] = {
            "size": size,
            "checksum": checksum,
            "received_at": datetime.utcnow().isoformat(),
            "order": chunk_number
        }
        
        self.chunks_received = len(self.chunks_metadata)
        self.bytes_uploaded = sum(chunk["size"] for chunk in self.chunks_metadata.values())
        self.last_chunk_at = datetime.utcnow()
    
    def is_chunk_received(self, chunk_number: int) -> bool:
        """Verificar si un chunk específico ha sido recibido."""
        return str(chunk_number) in (self.chunks_metadata or {})
    
    def get_chunk_info(self, chunk_number: int) -> Optional[Dict[str, Any]]:
        """Obtener información de un chunk específico."""
        if not self.chunks_metadata:
            return None
        return self.chunks_metadata.get(str(chunk_number))
    
    def mark_as_completed(self, final_file_url: str, file_checksum: Optional[str] = None) -> None:
        """Marcar la sesión como completada."""
        self.estado = EstadoUpload.COMPLETADO
        self.final_file_url = final_file_url
        self.file_checksum_actual = file_checksum
        self.completed_at = datetime.utcnow()
        
        if self.started_at:
            self.total_upload_time_sec = (datetime.utcnow() - self.started_at).total_seconds()
        
        if self.total_upload_time_sec and self.bytes_uploaded:
            self.upload_speed_bps = self.bytes_uploaded / self.total_upload_time_sec
    
    def mark_as_error(self, error_message: str, error_details: Optional[Dict[str, Any]] = None) -> None:
        """Marcar la sesión como error."""
        self.estado = EstadoUpload.ERROR
        self.error_message = error_message
        self.error_details = error_details
        self.retry_count += 1
    
    def update_expiration(self, hours: int = 24) -> None:
        """Actualizar tiempo de expiración."""
        self.expires_at = datetime.utcnow() + timedelta(hours=hours)
    
    @classmethod
    def default_expiration(cls) -> datetime:
        """Tiempo de expiración por defecto (24 horas)."""
        return datetime.utcnow() + timedelta(hours=24)


class ChunkUpload(BaseModel):
    """
    Registro individual de chunk subido.
    
    Tabla auxiliar para tracking detallado de chunks individuales.
    Útil para debugging y recovery granular.
    """
    
    __tablename__ = "chunk_uploads"
    
    # Relación con la sesión de upload
    upload_session_id = Column(UUID(as_uuid=True), ForeignKey("upload_sessions.id"), nullable=False, index=True)
    
    # Información del chunk
    chunk_number = Column(Integer, nullable=False)  # 1-based
    chunk_size = Column(Integer, nullable=False)
    chunk_checksum = Column(String(128), nullable=True)
    
    # Storage
    storage_path = Column(String(1000), nullable=False)
    
    # Metadata
    content_type = Column(String(100), nullable=True)
    upload_time_sec = Column(Float, nullable=True)
    
    # Timestamps
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relaciones
    upload_session = relationship("UploadSession")
    
    def __repr__(self) -> str:
        return (
            f"<ChunkUpload("
            f"id={self.id}, "
            f"session_id={self.upload_session_id}, "
            f"chunk={self.chunk_number}, "
            f"size={self.chunk_size}"
            f")>"
        )


# Agregar relaciones inversas a los modelos existentes
# Esto se hace en el archivo de inicialización de modelos
