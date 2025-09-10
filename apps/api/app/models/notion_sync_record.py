"""
Modelo para tracking de sincronización con Notion.
Registra el estado de sincronización de cada elemento con Notion.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Integer, String, Text, Boolean, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class EstadoSincronizacionNotion(str, Enum):
    """Estados de sincronización con Notion."""
    PENDIENTE = "pendiente"              # Pendiente de sincronización inicial
    SINCRONIZANDO = "sincronizando"      # En proceso de sincronización
    SINCRONIZADO = "sincronizado"        # Sincronizado correctamente
    ERROR = "error"                      # Error en sincronización
    CONFLICTO = "conflicto"              # Conflicto detectado (requiere revisión manual)
    DESACTUALIZADO = "desactualizado"    # Notion más reciente que local
    NECESITA_UPDATE = "necesita_update"  # Local más reciente que Notion


class NotionSyncRecord(Base):
    """
    Registro de sincronización de elementos con Notion.
    
    Trackea el estado de sincronización de cada ClassSession, ResearchJob,
    o cualquier otro elemento que deba sincronizarse con Notion.
    """
    __tablename__ = "notion_sync_records"
    
    # Identificadores
    id: UUID = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Elemento sincronizado (polimórfico)
    entity_type: str = Column(String(50), nullable=False)  # "class_session", "research_job", etc.
    entity_id: UUID = Column(PG_UUID(as_uuid=True), nullable=False)
    
    # Identificadores Notion
    notion_page_id: Optional[str] = Column(String(100), nullable=True, index=True)
    notion_database_id: Optional[str] = Column(String(100), nullable=True)
    notion_workspace_id: Optional[str] = Column(String(100), nullable=True)
    
    # Estado de sincronización
    sync_status: EstadoSincronizacionNotion = Column(
        String(20), 
        nullable=False, 
        default=EstadoSincronizacionNotion.PENDIENTE,
        index=True
    )
    
    # Timestamps de sincronización
    created_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_sync_at: Optional[datetime] = Column(DateTime, nullable=True)
    last_notion_update: Optional[datetime] = Column(DateTime, nullable=True)
    last_local_update: Optional[datetime] = Column(DateTime, nullable=True)
    
    # Metadatos de sincronización
    sync_metadata: Dict[str, Any] = Column(JSON, nullable=False, default=dict)
    """
    Metadatos sobre el proceso de sincronización:
    {
        "template_used": "clase_magistral",
        "blocks_created": 15,
        "attachments_uploaded": 2,
        "properties_synced": {...},
        "last_content_hash": "abc123...",
        "sync_duration_seconds": 45.2,
        "notion_api_version": "2022-06-28"
    }
    """
    
    # Gestión de errores y conflictos
    error_count: int = Column(Integer, nullable=False, default=0)
    error_details: Optional[str] = Column(Text, nullable=True)
    conflict_data: Optional[Dict[str, Any]] = Column(JSON, nullable=True)
    """
    Datos de conflictos detectados:
    {
        "conflict_type": "content_modified",
        "local_changes": {...},
        "notion_changes": {...},
        "merge_strategy": "manual",
        "resolution_required": true
    }
    """
    
    # Configuración específica
    sync_config: Dict[str, Any] = Column(JSON, nullable=False, default=dict)
    """
    Configuración específica para este elemento:
    {
        "auto_sync": true,
        "bidirectional": true,
        "template_type": "clase_magistral",
        "include_attachments": true,
        "conflict_resolution": "auto"
    }
    """
    
    # Métricas de performance
    performance_metrics: Dict[str, Any] = Column(JSON, nullable=False, default=dict)
    """
    Métricas de performance:
    {
        "avg_sync_time": 30.5,
        "total_syncs": 12,
        "success_rate": 0.95,
        "last_upload_size_mb": 2.4,
        "api_calls_last_sync": 8
    }
    """
    
    # Control de activación
    is_active: bool = Column(Boolean, nullable=False, default=True)
    is_bidirectional: bool = Column(Boolean, nullable=False, default=True)
    
    # Índices adicionales para consultas frecuentes
    __table_args__ = (
        {"schema": None}  # Se puede configurar schema si es necesario
    )
    
    def __repr__(self) -> str:
        return (
            f"<NotionSyncRecord("
            f"id={self.id}, "
            f"entity_type={self.entity_type}, "
            f"entity_id={self.entity_id}, "
            f"status={self.sync_status}, "
            f"notion_page_id={self.notion_page_id}"
            f")>"
        )
    
    @property
    def needs_sync(self) -> bool:
        """Determinar si el elemento necesita sincronización."""
        return self.sync_status in [
            EstadoSincronizacionNotion.PENDIENTE,
            EstadoSincronizacionNotion.NECESITA_UPDATE,
            EstadoSincronizacionNotion.ERROR
        ]
    
    @property
    def has_conflicts(self) -> bool:
        """Verificar si hay conflictos pendientes."""
        return self.sync_status == EstadoSincronizacionNotion.CONFLICTO
    
    @property
    def is_healthy(self) -> bool:
        """Verificar si la sincronización está en estado saludable."""
        return (
            self.sync_status == EstadoSincronizacionNotion.SINCRONIZADO and
            self.error_count < 3 and
            not self.has_conflicts
        )
    
    def mark_sync_start(self) -> None:
        """Marcar el inicio de un proceso de sincronización."""
        self.sync_status = EstadoSincronizacionNotion.SINCRONIZANDO
        self.last_sync_at = datetime.utcnow()
    
    def mark_sync_success(
        self, 
        notion_page_id: str, 
        metadata: Dict[str, Any] = None
    ) -> None:
        """Marcar sincronización exitosa."""
        self.sync_status = EstadoSincronizacionNotion.SINCRONIZADO
        self.notion_page_id = notion_page_id
        self.last_sync_at = datetime.utcnow()
        self.error_count = 0
        self.error_details = None
        
        if metadata:
            self.sync_metadata.update(metadata)
    
    def mark_sync_error(self, error_message: str) -> None:
        """Marcar error en sincronización."""
        self.sync_status = EstadoSincronizacionNotion.ERROR
        self.error_count += 1
        self.error_details = error_message
        self.last_sync_at = datetime.utcnow()
    
    def mark_conflict(self, conflict_data: Dict[str, Any]) -> None:
        """Marcar conflicto detectado."""
        self.sync_status = EstadoSincronizacionNotion.CONFLICTO
        self.conflict_data = conflict_data
        self.last_sync_at = datetime.utcnow()
    
    def update_performance_metrics(self, sync_duration: float, api_calls: int) -> None:
        """Actualizar métricas de performance."""
        if not self.performance_metrics:
            self.performance_metrics = {}
        
        # Incrementar contador de syncs
        total_syncs = self.performance_metrics.get("total_syncs", 0) + 1
        
        # Calcular promedio de tiempo
        avg_time = self.performance_metrics.get("avg_sync_time", 0)
        new_avg_time = ((avg_time * (total_syncs - 1)) + sync_duration) / total_syncs
        
        # Calcular tasa de éxito
        success_count = self.performance_metrics.get("success_count", 0)
        if self.sync_status == EstadoSincronizacionNotion.SINCRONIZADO:
            success_count += 1
        success_rate = success_count / total_syncs
        
        self.performance_metrics.update({
            "total_syncs": total_syncs,
            "success_count": success_count,
            "avg_sync_time": round(new_avg_time, 2),
            "success_rate": round(success_rate, 3),
            "api_calls_last_sync": api_calls,
            "last_sync_duration": round(sync_duration, 2)
        })


class NotionWorkspace(Base):
    """
    Configuración de workspace Notion para una instalación de Axonote.
    
    Permite manejar múltiples workspaces o configuraciones de Notion
    para diferentes organizaciones o propósitos.
    """
    __tablename__ = "notion_workspaces"
    
    # Identificadores
    id: UUID = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_name: str = Column(String(100), nullable=False)
    description: Optional[str] = Column(Text, nullable=True)
    
    # Identificadores Notion
    notion_workspace_id: Optional[str] = Column(String(100), nullable=True, unique=True)
    notion_integration_token: str = Column(String(200), nullable=False)
    
    # Configuración de databases
    database_ids: Dict[str, str] = Column(JSON, nullable=False, default=dict)
    """
    Mapeo de tipos de entidad a database IDs:
    {
        "classes": "db_classes_id",
        "professors": "db_professors_id", 
        "sources": "db_sources_id",
        "terms": "db_terms_id",
        "cards": "db_cards_id",
        "research": "db_research_id"
    }
    """
    
    # Configuración de templates
    template_configs: Dict[str, Any] = Column(JSON, nullable=False, default=dict)
    """
    Configuración de templates por tipo:
    {
        "clase_magistral": {
            "template_id": "template_123",
            "properties": {...},
            "auto_detect_rules": [...]
        },
        "seminario_clinico": {...}
    }
    """
    
    # Configuración de sincronización
    sync_settings: Dict[str, Any] = Column(JSON, nullable=False, default=dict)
    """
    Configuración de sincronización:
    {
        "auto_sync_enabled": true,
        "sync_interval_minutes": 15,
        "bidirectional_sync": true,
        "conflict_resolution": "auto",
        "max_retries": 3,
        "include_attachments": true
    }
    """
    
    # Estado y control
    is_active: bool = Column(Boolean, nullable=False, default=True)
    is_default: bool = Column(Boolean, nullable=False, default=False)
    
    # Timestamps
    created_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_health_check: Optional[datetime] = Column(DateTime, nullable=True)
    
    # Métricas del workspace
    workspace_metrics: Dict[str, Any] = Column(JSON, nullable=False, default=dict)
    """
    Métricas del workspace:
    {
        "total_pages_created": 142,
        "total_syncs_performed": 1250,
        "avg_sync_success_rate": 0.95,
        "total_attachments_uploaded": 89,
        "storage_used_mb": 450.2,
        "api_calls_this_month": 2500
    }
    """
    
    def __repr__(self) -> str:
        return (
            f"<NotionWorkspace("
            f"id={self.id}, "
            f"name={self.workspace_name}, "
            f"active={self.is_active}, "
            f"default={self.is_default}"
            f")>"
        )
    
    @property
    def has_required_databases(self) -> bool:
        """Verificar si tiene todas las databases requeridas."""
        required_dbs = ["classes", "professors", "sources", "terms"]
        return all(db_type in self.database_ids for db_type in required_dbs)
    
    @property
    def is_healthy(self) -> bool:
        """Verificar si el workspace está en estado saludable."""
        return (
            self.is_active and
            self.has_required_databases and
            self.notion_integration_token is not None
        )
    
    def get_database_id(self, entity_type: str) -> Optional[str]:
        """Obtener database ID para un tipo de entidad."""
        return self.database_ids.get(entity_type)
    
    def update_metrics(self, metric_updates: Dict[str, Any]) -> None:
        """Actualizar métricas del workspace."""
        if not self.workspace_metrics:
            self.workspace_metrics = {}
        
        self.workspace_metrics.update(metric_updates)
        self.updated_at = datetime.utcnow()


class NotionConflictResolution(Base):
    """
    Registro de resoluciones de conflictos en sincronización bidireccional.
    
    Mantiene un historial de conflictos detectados y cómo fueron resueltos
    para aprendizaje automático y auditoría.
    """
    __tablename__ = "notion_conflict_resolutions"
    
    # Identificadores
    id: UUID = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    sync_record_id: UUID = Column(
        PG_UUID(as_uuid=True), 
        ForeignKey("notion_sync_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Datos del conflicto
    conflict_type: str = Column(String(50), nullable=False)  # "content_modified", "property_changed", etc.
    conflict_description: str = Column(Text, nullable=False)
    
    # Datos de las versiones en conflicto
    local_data: Dict[str, Any] = Column(JSON, nullable=False)
    notion_data: Dict[str, Any] = Column(JSON, nullable=False)
    
    # Resolución aplicada
    resolution_strategy: str = Column(String(50), nullable=False)  # "auto", "manual", "overwrite_local", etc.
    resolution_data: Dict[str, Any] = Column(JSON, nullable=False)
    resolved_by: Optional[str] = Column(String(100), nullable=True)  # Usuario que resolvió manualmente
    
    # Timestamps
    detected_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at: Optional[datetime] = Column(DateTime, nullable=True)
    
    # Estado
    is_resolved: bool = Column(Boolean, nullable=False, default=False)
    
    # Relación con el sync record
    sync_record = relationship("NotionSyncRecord", backref="conflict_resolutions")
    
    def __repr__(self) -> str:
        return (
            f"<NotionConflictResolution("
            f"id={self.id}, "
            f"type={self.conflict_type}, "
            f"resolved={self.is_resolved}"
            f")>"
        )
    
    def mark_resolved(
        self, 
        resolution_strategy: str, 
        resolution_data: Dict[str, Any],
        resolved_by: Optional[str] = None
    ) -> None:
        """Marcar conflicto como resuelto."""
        self.resolution_strategy = resolution_strategy
        self.resolution_data = resolution_data
        self.resolved_by = resolved_by
        self.resolved_at = datetime.utcnow()
        self.is_resolved = True
