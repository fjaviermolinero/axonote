"""
Modelos para gestión administrativa y dashboards.
Control de usuarios, métricas y configuración del sistema.
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, JSON, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from enum import Enum

from app.models.base import BaseModel


class TipoEvento(str, Enum):
    """Tipos de eventos para auditoría."""
    LOGIN = "login"
    LOGOUT = "logout"
    CREAR_USUARIO = "crear_usuario"
    MODIFICAR_USUARIO = "modificar_usuario"
    ELIMINAR_USUARIO = "eliminar_usuario"
    CREAR_TENANT = "crear_tenant"
    MODIFICAR_TENANT = "modificar_tenant"
    SUSPENDER_TENANT = "suspender_tenant"
    CAMBIAR_PLAN = "cambiar_plan"
    SUBIR_ARCHIVO = "subir_archivo"
    PROCESAR_AUDIO = "procesar_audio"
    EXPORT_DATOS = "export_datos"
    CONFIGURAR_SISTEMA = "configurar_sistema"
    ERROR_SISTEMA = "error_sistema"
    ACCESO_DENEGADO = "acceso_denegado"


class EventoAuditoria(BaseModel):
    """
    Registro de auditoría para tracking de acciones administrativas.
    """
    __tablename__ = "eventos_auditoria"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Información del evento
    tipo_evento = Column(String(50), nullable=False)
    accion = Column(String(255), nullable=False)
    descripcion = Column(Text, nullable=True)
    resultado = Column(String(20), nullable=False)  # exito, error, advertencia
    
    # Contexto del usuario
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    ip_address = Column(String(45), nullable=False)  # IPv6 compatible
    user_agent = Column(Text, nullable=True)
    
    # Detalles técnicos
    recurso_afectado = Column(String(255), nullable=True)
    recurso_id = Column(String(255), nullable=True)
    datos_anteriores = Column(JSON, nullable=True)
    datos_nuevos = Column(JSON, nullable=True)
    metadatos = Column(JSON, nullable=False, default=dict)
    
    # Información de tiempo
    fecha_evento = Column(DateTime(timezone=True), server_default=func.now())
    duracion_ms = Column(Integer, nullable=True)
    
    # Geolocalización (opcional)
    pais = Column(String(3), nullable=True)
    ciudad = Column(String(100), nullable=True)
    
    # Relationships
    usuario = relationship("Usuario")
    tenant = relationship("Tenant")

    def __repr__(self):
        return f"<EventoAuditoria(tipo='{self.tipo_evento}', usuario_id={self.usuario_id})>"


class ConfiguracionSistema(BaseModel):
    """
    Configuración global del sistema AxoNote.
    """
    __tablename__ = "configuracion_sistema"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clave = Column(String(100), unique=True, nullable=False)
    valor = Column(JSON, nullable=False)
    tipo = Column(String(50), nullable=False)  # string, number, boolean, json, array
    categoria = Column(String(50), nullable=False)  # ai, security, billing, ui, etc.
    
    # Metadatos
    descripcion = Column(Text, nullable=True)
    valor_por_defecto = Column(JSON, nullable=True)
    modificable_runtime = Column(Boolean, nullable=False, default=True)
    requiere_reinicio = Column(Boolean, nullable=False, default=False)
    sensible = Column(Boolean, nullable=False, default=False)  # ocultar en logs
    
    # Control de cambios
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_actualizacion = Column(DateTime(timezone=True), onupdate=func.now())
    modificado_por = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    
    # Relationships
    usuario_modificador = relationship("Usuario")

    def __repr__(self):
        return f"<ConfiguracionSistema(clave='{self.clave}', categoria='{self.categoria}')>"


class MetricaSistema(BaseModel):
    """
    Métricas globales del sistema para monitoring y alertas.
    """
    __tablename__ = "metricas_sistema"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Información temporal
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    periodo_minutos = Column(Integer, nullable=False, default=5)  # agregación
    
    # Métricas de performance
    cpu_usage_percent = Column(Float, nullable=False, default=0.0)
    memory_usage_percent = Column(Float, nullable=False, default=0.0)
    disk_usage_percent = Column(Float, nullable=False, default=0.0)
    gpu_usage_percent = Column(Float, nullable=True)
    gpu_memory_percent = Column(Float, nullable=True)
    
    # Métricas de aplicación
    requests_total = Column(Integer, nullable=False, default=0)
    requests_success = Column(Integer, nullable=False, default=0)
    requests_error = Column(Integer, nullable=False, default=0)
    response_time_avg_ms = Column(Float, nullable=False, default=0.0)
    response_time_p95_ms = Column(Float, nullable=False, default=0.0)
    
    # Métricas de usuarios
    usuarios_activos = Column(Integer, nullable=False, default=0)
    sesiones_activas = Column(Integer, nullable=False, default=0)
    tenants_activos = Column(Integer, nullable=False, default=0)
    
    # Métricas de procesamiento
    jobs_pendientes = Column(Integer, nullable=False, default=0)
    jobs_procesando = Column(Integer, nullable=False, default=0)
    jobs_completados = Column(Integer, nullable=False, default=0)
    jobs_fallidos = Column(Integer, nullable=False, default=0)
    tiempo_promedio_job_ms = Column(Float, nullable=False, default=0.0)
    
    # Métricas de almacenamiento
    storage_usado_gb = Column(Float, nullable=False, default=0.0)
    storage_total_gb = Column(Float, nullable=False, default=0.0)
    archivos_subidos = Column(Integer, nullable=False, default=0)
    
    # Métricas de base de datos
    db_connections_active = Column(Integer, nullable=False, default=0)
    db_connections_max = Column(Integer, nullable=False, default=0)
    db_query_avg_ms = Column(Float, nullable=False, default=0.0)
    db_size_mb = Column(Float, nullable=False, default=0.0)
    
    # Métricas de cache
    redis_memory_mb = Column(Float, nullable=False, default=0.0)
    redis_hits = Column(Integer, nullable=False, default=0)
    redis_misses = Column(Integer, nullable=False, default=0)
    
    # Métricas de AI/ML
    whisper_requests = Column(Integer, nullable=False, default=0)
    diarization_requests = Column(Integer, nullable=False, default=0)
    llm_requests = Column(Integer, nullable=False, default=0)
    ocr_requests = Column(Integer, nullable=False, default=0)
    tts_requests = Column(Integer, nullable=False, default=0)
    
    # Alertas activas
    alertas_criticas = Column(Integer, nullable=False, default=0)
    alertas_advertencias = Column(Integer, nullable=False, default=0)

    def __repr__(self):
        return f"<MetricaSistema(timestamp={self.timestamp}, cpu={self.cpu_usage_percent}%)>"


class AlertaSistema(BaseModel):
    """
    Alertas del sistema para notificación a administradores.
    """
    __tablename__ = "alertas_sistema"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Información de la alerta
    nombre = Column(String(255), nullable=False)
    descripcion = Column(Text, nullable=False)
    severidad = Column(String(20), nullable=False)  # critica, alta, media, baja, info
    categoria = Column(String(50), nullable=False)  # performance, security, business, etc.
    
    # Estado
    activa = Column(Boolean, nullable=False, default=True)
    reconocida = Column(Boolean, nullable=False, default=False)
    resuelta = Column(Boolean, nullable=False, default=False)
    
    # Contexto
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    recurso_afectado = Column(String(255), nullable=True)
    
    # Datos de la alerta
    valor_actual = Column(Float, nullable=True)
    valor_umbral = Column(Float, nullable=True)
    metrica_asociada = Column(String(100), nullable=True)
    datos_contexto = Column(JSON, nullable=False, default=dict)
    
    # Acciones
    accion_automatica = Column(String(255), nullable=True)
    accion_ejecutada = Column(Boolean, nullable=False, default=False)
    notificacion_enviada = Column(Boolean, nullable=False, default=False)
    
    # Timestamps
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_reconocimiento = Column(DateTime(timezone=True), nullable=True)
    fecha_resolucion = Column(DateTime(timezone=True), nullable=True)
    ultima_actualizacion = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Usuario que reconoció/resolvió
    reconocida_por = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    resuelta_por = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    notas_resolucion = Column(Text, nullable=True)
    
    # Relationships
    tenant = relationship("Tenant")
    usuario = relationship("Usuario", foreign_keys=[usuario_id])
    usuario_reconocimiento = relationship("Usuario", foreign_keys=[reconocida_por])
    usuario_resolucion = relationship("Usuario", foreign_keys=[resuelta_por])

    def __repr__(self):
        return f"<AlertaSistema(nombre='{self.nombre}', severidad='{self.severidad}')>"

    @property
    def duracion_activa(self):
        """Calcula cuánto tiempo ha estado activa la alerta."""
        from datetime import datetime, timezone
        if self.resuelta:
            return self.fecha_resolucion - self.fecha_creacion
        return datetime.now(timezone.utc) - self.fecha_creacion

    def puede_reconocerse(self):
        """Verifica si la alerta puede ser reconocida."""
        return self.activa and not self.reconocida and not self.resuelta

    def puede_resolverse(self):
        """Verifica si la alerta puede ser marcada como resuelta."""
        return self.activa and not self.resuelta


class NotificacionAdmin(BaseModel):
    """
    Notificaciones para administradores del sistema.
    """
    __tablename__ = "notificaciones_admin"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Destinatario
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    
    # Contenido
    titulo = Column(String(255), nullable=False)
    mensaje = Column(Text, nullable=False)
    tipo = Column(String(50), nullable=False)  # info, warning, error, success
    categoria = Column(String(50), nullable=False)  # system, security, billing, user, etc.
    
    # Metadatos
    datos_adicionales = Column(JSON, nullable=False, default=dict)
    accion_url = Column(String(500), nullable=True)
    accion_texto = Column(String(100), nullable=True)
    
    # Estado
    leida = Column(Boolean, nullable=False, default=False)
    archivada = Column(Boolean, nullable=False, default=False)
    
    # Timestamps
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_lectura = Column(DateTime(timezone=True), nullable=True)
    fecha_expiracion = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    usuario = relationship("Usuario")

    def __repr__(self):
        return f"<NotificacionAdmin(titulo='{self.titulo}', usuario_id={self.usuario_id})>"

    @property
    def expirada(self):
        """Verifica si la notificación ha expirado."""
        if not self.fecha_expiracion:
            return False
        from datetime import datetime, timezone
        return datetime.now(timezone.utc) > self.fecha_expiracion
