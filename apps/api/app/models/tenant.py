"""
Modelos para arquitectura multi-tenant.
Gestión de organizaciones, usuarios y configuraciones por tenant.
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.models.base import BaseModel


class Tenant(BaseModel):
    """
    Modelo para organizaciones/instituciones (multi-tenant).
    Cada tenant representa una institución médica independiente.
    """
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(255), nullable=False, index=True)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    dominio_personalizado = Column(String(255), unique=True, nullable=True)
    
    # Información de la institución
    tipo_institucion = Column(String(50), nullable=False)  # universidad, hospital, clinica, etc.
    pais = Column(String(3), nullable=False)  # ISO 3166-1 alpha-3
    ciudad = Column(String(100), nullable=False)
    direccion = Column(Text, nullable=True)
    telefono = Column(String(20), nullable=True)
    email_contacto = Column(String(255), nullable=False)
    sitio_web = Column(String(255), nullable=True)
    
    # Configuración del tenant
    configuracion = Column(JSON, nullable=False, default=dict)
    branding = Column(JSON, nullable=False, default=dict)  # logo, colores, etc.
    
    # Limites y plan
    plan = Column(String(50), nullable=False, default="basic")  # basic, pro, enterprise
    limite_usuarios = Column(Integer, nullable=False, default=50)
    limite_almacenamiento_gb = Column(Integer, nullable=False, default=10)
    limite_horas_procesamiento = Column(Integer, nullable=False, default=100)
    
    # Estado
    activo = Column(Boolean, nullable=False, default=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_actualizacion = Column(DateTime(timezone=True), onupdate=func.now())
    fecha_suspension = Column(DateTime(timezone=True), nullable=True)
    motivo_suspension = Column(String(255), nullable=True)
    
    # Billing
    billing_email = Column(String(255), nullable=True)
    stripe_customer_id = Column(String(100), nullable=True)
    fecha_ultima_facturacion = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    usuarios = relationship("Usuario", back_populates="tenant", cascade="all, delete-orphan")
    sesiones_clase = relationship("ClassSession", back_populates="tenant")
    configuraciones_tenant = relationship("TenantConfiguracion", back_populates="tenant")
    metricas_tenant = relationship("TenantMetrica", back_populates="tenant")

    def __repr__(self):
        return f"<Tenant(id={self.id}, nombre='{self.nombre}', plan='{self.plan}')>"

    @property
    def configuracion_completa(self):
        """Configuración completa con valores por defecto."""
        config_default = {
            "idioma_por_defecto": "es",
            "zona_horaria": "Europe/Madrid",
            "formato_fecha": "DD/MM/YYYY",
            "whisper_model": "large-v3",
            "diarizacion_habilitada": True,
            "research_automatico": True,
            "notion_integracion": False,
            "export_formatos": ["pdf", "docx", "json"],
            "tts_habilitado": True,
            "ocr_habilitado": True,
            "retention_dias": 365,
            "backup_automatico": True,
            "notificaciones_email": True,
            "analytics_avanzado": False,
            "api_acceso": False,
            "sso_habilitado": False
        }
        config_default.update(self.configuracion or {})
        return config_default

    @property
    def branding_completo(self):
        """Branding completo con valores por defecto."""
        branding_default = {
            "logo_url": None,
            "color_primario": "#2563eb",
            "color_secundario": "#1e40af",
            "color_acento": "#0ea5e9",
            "fuente_principal": "Inter",
            "favicon_url": None,
            "nombre_mostrar": self.nombre,
            "eslogan": None,
            "footer_personalizado": None
        }
        branding_default.update(self.branding or {})
        return branding_default

    def puede_crear_usuario(self):
        """Verifica si el tenant puede crear más usuarios."""
        return len(self.usuarios) < self.limite_usuarios

    def uso_almacenamiento_gb(self):
        """Calcula el uso actual de almacenamiento en GB."""
        # TODO: Implementar cálculo real basado en MinIO
        return 0

    def uso_horas_mes_actual(self):
        """Calcula las horas de procesamiento usadas en el mes actual."""
        # TODO: Implementar cálculo basado en métricas
        return 0


class TenantConfiguracion(BaseModel):
    """
    Configuraciones específicas por tenant que pueden cambiar en runtime.
    """
    __tablename__ = "tenant_configuraciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    clave = Column(String(100), nullable=False)
    valor = Column(JSON, nullable=False)
    tipo = Column(String(50), nullable=False)  # string, number, boolean, json, array
    descripcion = Column(Text, nullable=True)
    categoria = Column(String(50), nullable=False)  # ai, ui, security, billing, etc.
    
    # Metadatos
    modificable_por_admin = Column(Boolean, nullable=False, default=True)
    requiere_reinicio = Column(Boolean, nullable=False, default=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    fecha_actualizacion = Column(DateTime(timezone=True), onupdate=func.now())
    modificado_por = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="configuraciones_tenant")
    usuario_modificador = relationship("Usuario", foreign_keys=[modificado_por])

    def __repr__(self):
        return f"<TenantConfiguracion(tenant_id={self.tenant_id}, clave='{self.clave}')>"


class TenantMetrica(BaseModel):
    """
    Métricas y estadísticas por tenant para billing y analytics.
    """
    __tablename__ = "tenant_metricas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    
    # Período de la métrica
    fecha_inicio = Column(DateTime(timezone=True), nullable=False)
    fecha_fin = Column(DateTime(timezone=True), nullable=False)
    tipo_periodo = Column(String(20), nullable=False)  # diario, semanal, mensual
    
    # Métricas de uso
    usuarios_activos = Column(Integer, nullable=False, default=0)
    sesiones_procesadas = Column(Integer, nullable=False, default=0)
    minutos_audio_procesados = Column(Integer, nullable=False, default=0)
    documentos_ocr = Column(Integer, nullable=False, default=0)
    exports_generados = Column(Integer, nullable=False, default=0)
    apis_calls = Column(Integer, nullable=False, default=0)
    
    # Métricas de almacenamiento
    almacenamiento_usado_gb = Column(Integer, nullable=False, default=0)
    archivos_subidos = Column(Integer, nullable=False, default=0)
    backups_creados = Column(Integer, nullable=False, default=0)
    
    # Métricas de performance
    tiempo_promedio_procesamiento = Column(Integer, nullable=False, default=0)  # segundos
    tiempo_promedio_respuesta_api = Column(Integer, nullable=False, default=0)  # ms
    tasa_exito_procesamiento = Column(Integer, nullable=False, default=100)  # porcentaje
    
    # Métricas de engagement
    logins_usuarios = Column(Integer, nullable=False, default=0)
    tiempo_promedio_sesion = Column(Integer, nullable=False, default=0)  # minutos
    features_mas_usadas = Column(JSON, nullable=False, default=list)
    
    # Billing
    costo_calculado = Column(Integer, nullable=False, default=0)  # céntimos
    facturado = Column(Boolean, nullable=False, default=False)
    fecha_facturacion = Column(DateTime(timezone=True), nullable=True)
    
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    tenant = relationship("Tenant", back_populates="metricas_tenant")

    def __repr__(self):
        return f"<TenantMetrica(tenant_id={self.tenant_id}, periodo={self.tipo_periodo})>"


class TenantInvitacion(BaseModel):
    """
    Invitaciones para que usuarios se unan a un tenant.
    """
    __tablename__ = "tenant_invitaciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    email = Column(String(255), nullable=False)
    rol_asignado = Column(String(50), nullable=False, default="user")
    
    # Token de invitación
    token = Column(String(255), unique=True, nullable=False)
    fecha_expiracion = Column(DateTime(timezone=True), nullable=False)
    
    # Estado
    aceptada = Column(Boolean, nullable=False, default=False)
    fecha_aceptacion = Column(DateTime(timezone=True), nullable=True)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    
    # Metadatos
    mensaje_personalizado = Column(Text, nullable=True)
    enviada_por = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now())
    intentos_envio = Column(Integer, nullable=False, default=0)
    fecha_ultimo_envio = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    tenant = relationship("Tenant")
    usuario_invitado = relationship("Usuario", foreign_keys=[usuario_id])
    usuario_invitador = relationship("Usuario", foreign_keys=[enviada_por])

    def __repr__(self):
        return f"<TenantInvitacion(email='{self.email}', tenant_id={self.tenant_id})>"

    @property
    def expirada(self):
        """Verifica si la invitación ha expirado."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc) > self.fecha_expiracion

    @property
    def puede_reenviarse(self):
        """Verifica si la invitación puede reenviarse."""
        return not self.aceptada and not self.expirada and self.intentos_envio < 3
