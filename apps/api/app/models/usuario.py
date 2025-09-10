"""
Modelos de usuario y autenticación para Axonote.
Incluye usuarios, roles, sesiones y auditoría de seguridad.
"""

import uuid
import enum
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import (
    Column, String, Boolean, DateTime, Text, Enum, Integer, 
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class RolUsuario(str, enum.Enum):
    """Roles de usuario en el sistema."""
    ADMIN = "admin"
    MEDICO = "medico"
    ESTUDIANTE = "estudiante"
    INVITADO = "invitado"


class EstadoUsuario(str, enum.Enum):
    """Estados posibles de un usuario."""
    ACTIVO = "activo"
    INACTIVO = "inactivo"
    BLOQUEADO = "bloqueado"
    PENDIENTE_VERIFICACION = "pendiente_verificacion"


class Usuario(Base):
    """
    Modelo de usuario del sistema.
    Incluye autenticación, autorización y metadatos de seguridad.
    """
    __tablename__ = "usuarios"

    # Identificación
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, index=True, nullable=False)
    nombre_completo = Column(String(255), nullable=False)
    
    # Autenticación
    password_hash = Column(String(255), nullable=False)
    rol = Column(Enum(RolUsuario), default=RolUsuario.ESTUDIANTE, nullable=False)
    estado = Column(Enum(EstadoUsuario), default=EstadoUsuario.PENDIENTE_VERIFICACION, nullable=False)
    
    # Verificación de email
    verificado = Column(Boolean, default=False, nullable=False)
    token_verificacion = Column(String(255), nullable=True)
    fecha_verificacion = Column(DateTime(timezone=True), nullable=True)
    
    # MFA (Multi-Factor Authentication)
    mfa_habilitado = Column(Boolean, default=False, nullable=False)
    mfa_secreto = Column(String(255), nullable=True)  # Secreto TOTP cifrado
    codigos_recuperacion = Column(JSONB, default=list)  # Códigos de recuperación cifrados
    
    # Seguridad
    ultimo_acceso = Column(DateTime(timezone=True), nullable=True)
    ultimo_cambio_password = Column(DateTime(timezone=True), nullable=True)
    intentos_fallidos = Column(Integer, default=0, nullable=False)
    bloqueado_hasta = Column(DateTime(timezone=True), nullable=True)
    razon_bloqueo = Column(String(500), nullable=True)
    
    # Metadatos de sesión
    ip_ultimo_acceso = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent_ultimo = Column(Text, nullable=True)
    
    # Consentimientos GDPR
    consentimientos = Column(JSONB, default=dict, nullable=False)
    fecha_consentimiento = Column(DateTime(timezone=True), nullable=True)
    version_politica_aceptada = Column(String(50), nullable=True)
    
    # Preferencias de usuario
    preferencias = Column(JSONB, default=dict, nullable=False)
    configuracion_notificaciones = Column(JSONB, default=dict, nullable=False)
    
    # Auditoría
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    
    # Relaciones
    sesiones = relationship("SesionUsuario", back_populates="usuario", cascade="all, delete-orphan")
    logs_auditoria = relationship("LogAuditoria", back_populates="usuario")
    class_sessions = relationship("ClassSession", back_populates="usuario")
    creado_por = relationship("Usuario", remote_side=[id])
    
    # Índices
    __table_args__ = (
        Index('idx_usuario_email_activo', 'email', 'estado'),
        Index('idx_usuario_ultimo_acceso', 'ultimo_acceso'),
        Index('idx_usuario_intentos_fallidos', 'intentos_fallidos'),
    )
    
    def __repr__(self):
        return f"<Usuario(id={self.id}, email='{self.email}', rol='{self.rol}')>"
    
    @property
    def esta_bloqueado(self) -> bool:
        """Verifica si el usuario está actualmente bloqueado."""
        if self.estado == EstadoUsuario.BLOQUEADO:
            return True
        if self.bloqueado_hasta and self.bloqueado_hasta > datetime.utcnow():
            return True
        return False
    
    @property
    def puede_autenticarse(self) -> bool:
        """Verifica si el usuario puede autenticarse."""
        return (
            self.estado == EstadoUsuario.ACTIVO and
            not self.esta_bloqueado and
            self.verificado
        )
    
    def incrementar_intentos_fallidos(self):
        """Incrementa el contador de intentos fallidos."""
        self.intentos_fallidos += 1
        
        # Bloquear temporalmente después de 5 intentos
        if self.intentos_fallidos >= 5:
            from datetime import timedelta
            self.bloqueado_hasta = datetime.utcnow() + timedelta(minutes=30)
            self.razon_bloqueo = "Múltiples intentos de acceso fallidos"
    
    def resetear_intentos_fallidos(self):
        """Resetea el contador de intentos fallidos."""
        self.intentos_fallidos = 0
        self.bloqueado_hasta = None
        self.razon_bloqueo = None


class SesionUsuario(Base):
    """
    Modelo de sesión de usuario para gestión de tokens JWT.
    Permite invalidar sesiones específicas y rastrear actividad.
    """
    __tablename__ = "sesiones_usuario"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    
    # Identificadores de tokens JWT
    token_jti = Column(String(255), unique=True, index=True, nullable=False)  # Access token JTI
    refresh_token_jti = Column(String(255), unique=True, index=True, nullable=False)  # Refresh token JTI
    
    # Metadatos de sesión
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(Text, nullable=True)
    dispositivo_info = Column(JSONB, default=dict)  # Información del dispositivo/navegador
    
    # Geolocalización (opcional)
    pais = Column(String(2), nullable=True)  # Código ISO del país
    ciudad = Column(String(100), nullable=True)
    coordenadas = Column(JSONB, nullable=True)  # {"lat": float, "lng": float}
    
    # Control de sesión
    activa = Column(Boolean, default=True, nullable=False)
    expira_en = Column(DateTime(timezone=True), nullable=False)
    ultimo_uso = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Metadatos de seguridad
    es_sospechosa = Column(Boolean, default=False, nullable=False)
    razon_sospecha = Column(String(500), nullable=True)
    
    # Auditoría
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    invalidada_en = Column(DateTime(timezone=True), nullable=True)
    invalidada_por = Column(String(100), nullable=True)  # "usuario", "admin", "sistema"
    
    # Relaciones
    usuario = relationship("Usuario", back_populates="sesiones")
    
    # Índices
    __table_args__ = (
        Index('idx_sesion_usuario_activa', 'usuario_id', 'activa'),
        Index('idx_sesion_token_jti', 'token_jti'),
        Index('idx_sesion_refresh_jti', 'refresh_token_jti'),
        Index('idx_sesion_expiracion', 'expira_en'),
    )
    
    def __repr__(self):
        return f"<SesionUsuario(id={self.id}, usuario_id={self.usuario_id}, activa={self.activa})>"
    
    @property
    def esta_expirada(self) -> bool:
        """Verifica si la sesión ha expirado."""
        return datetime.utcnow() > self.expira_en
    
    @property
    def esta_valida(self) -> bool:
        """Verifica si la sesión es válida (activa y no expirada)."""
        return self.activa and not self.esta_expirada
    
    def invalidar(self, razon: str = "usuario"):
        """Invalida la sesión."""
        self.activa = False
        self.invalidada_en = datetime.utcnow()
        self.invalidada_por = razon
    
    def actualizar_ultimo_uso(self):
        """Actualiza el timestamp del último uso."""
        self.ultimo_uso = datetime.utcnow()


class TipoEventoAuditoria(str, enum.Enum):
    """Tipos de eventos de auditoría."""
    # Autenticación
    LOGIN_EXITOSO = "login_exitoso"
    LOGIN_FALLIDO = "login_fallido"
    LOGOUT = "logout"
    CAMBIO_PASSWORD = "cambio_password"
    RESET_PASSWORD = "reset_password"
    MFA_HABILITADO = "mfa_habilitado"
    MFA_DESHABILITADO = "mfa_deshabilitado"
    MFA_CODIGO_USADO = "mfa_codigo_usado"
    
    # Gestión de usuarios
    USUARIO_CREADO = "usuario_creado"
    USUARIO_MODIFICADO = "usuario_modificado"
    USUARIO_BLOQUEADO = "usuario_bloqueado"
    USUARIO_DESBLOQUEADO = "usuario_desbloqueado"
    USUARIO_ELIMINADO = "usuario_eliminado"
    
    # Datos y sesiones
    SESION_CREADA = "sesion_creada"
    SESION_INVALIDADA = "sesion_invalidada"
    ACCESO_DATOS_SENSIBLES = "acceso_datos_sensibles"
    MODIFICACION_DATOS = "modificacion_datos"
    EXPORTACION_DATOS = "exportacion_datos"
    ELIMINACION_DATOS = "eliminacion_datos"
    
    # Sistema y configuración
    CAMBIO_CONFIGURACION = "cambio_configuracion"
    ERROR_SISTEMA = "error_sistema"
    BACKUP_CREADO = "backup_creado"
    BACKUP_RESTAURADO = "backup_restaurado"
    
    # Seguridad
    INTENTO_ACCESO_NO_AUTORIZADO = "intento_acceso_no_autorizado"
    RATE_LIMIT_EXCEDIDO = "rate_limit_excedido"
    DETECCION_ANOMALIA = "deteccion_anomalia"
    VIOLACION_SEGURIDAD = "violacion_seguridad"
    IP_BLOQUEADA = "ip_bloqueada"
    
    # GDPR y compliance
    CONSENTIMIENTO_OTORGADO = "consentimiento_otorgado"
    CONSENTIMIENTO_REVOCADO = "consentimiento_revocado"
    SOLICITUD_DATOS_GDPR = "solicitud_datos_gdpr"
    ELIMINACION_DATOS_GDPR = "eliminacion_datos_gdpr"


class NivelSeveridad(str, enum.Enum):
    """Niveles de severidad para eventos de auditoría."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogAuditoria(Base):
    """
    Modelo de log de auditoría para trazabilidad completa.
    Registra todos los eventos importantes del sistema.
    """
    __tablename__ = "logs_auditoria"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Información del evento
    tipo_evento = Column(Enum(TipoEventoAuditoria), nullable=False)
    severidad = Column(Enum(NivelSeveridad), default=NivelSeveridad.INFO, nullable=False)
    descripcion = Column(Text, nullable=False)
    resultado = Column(String(50), nullable=True)  # "exitoso", "fallido", "bloqueado"
    
    # Usuario y sesión
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    sesion_id = Column(UUID(as_uuid=True), nullable=True)
    usuario_afectado_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    
    # Contexto técnico
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    endpoint = Column(String(255), nullable=True)
    metodo_http = Column(String(10), nullable=True)
    codigo_respuesta = Column(Integer, nullable=True)
    
    # Datos del evento (JSON)
    datos_evento = Column(JSONB, default=dict)
    datos_antes = Column(JSONB, nullable=True)  # Estado antes del cambio
    datos_despues = Column(JSONB, nullable=True)  # Estado después del cambio
    
    # Contexto adicional
    recurso_afectado = Column(String(255), nullable=True)  # ID del recurso afectado
    tipo_recurso = Column(String(100), nullable=True)  # Tipo de recurso (sesion, usuario, etc.)
    
    # Metadatos de seguridad
    hash_integridad = Column(String(64), nullable=True)  # SHA-256 del evento
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Correlación de eventos
    evento_padre_id = Column(UUID(as_uuid=True), ForeignKey("logs_auditoria.id"), nullable=True)
    trace_id = Column(String(100), nullable=True)  # Para correlacionar eventos relacionados
    
    # Relaciones
    usuario = relationship("Usuario", foreign_keys=[usuario_id], back_populates="logs_auditoria")
    usuario_afectado = relationship("Usuario", foreign_keys=[usuario_afectado_id])
    evento_padre = relationship("LogAuditoria", remote_side=[id])
    
    # Índices
    __table_args__ = (
        Index('idx_auditoria_usuario_timestamp', 'usuario_id', 'timestamp'),
        Index('idx_auditoria_tipo_timestamp', 'tipo_evento', 'timestamp'),
        Index('idx_auditoria_severidad', 'severidad'),
        Index('idx_auditoria_ip_timestamp', 'ip_address', 'timestamp'),
        Index('idx_auditoria_trace_id', 'trace_id'),
    )
    
    def __repr__(self):
        return f"<LogAuditoria(id={self.id}, tipo={self.tipo_evento}, usuario_id={self.usuario_id})>"
    
    def generar_hash_integridad(self) -> str:
        """Genera hash SHA-256 para verificar integridad del log."""
        import hashlib
        import json
        
        datos_hash = {
            "tipo_evento": self.tipo_evento,
            "descripcion": self.descripcion,
            "usuario_id": str(self.usuario_id) if self.usuario_id else None,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "datos_evento": self.datos_evento
        }
        
        json_str = json.dumps(datos_hash, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(json_str.encode('utf-8')).hexdigest()


class PermisosUsuario(Base):
    """
    Modelo para permisos granulares de usuario.
    Permite control de acceso fino más allá de roles básicos.
    """
    __tablename__ = "permisos_usuario"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    
    # Permisos específicos
    recurso = Column(String(100), nullable=False)  # "sesiones", "usuarios", "configuracion"
    accion = Column(String(50), nullable=False)    # "crear", "leer", "actualizar", "eliminar"
    permitido = Column(Boolean, default=True, nullable=False)
    
    # Restricciones adicionales
    condiciones = Column(JSONB, default=dict)  # Condiciones específicas del permiso
    
    # Metadatos
    otorgado_por = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    fecha_otorgado = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fecha_expiracion = Column(DateTime(timezone=True), nullable=True)
    activo = Column(Boolean, default=True, nullable=False)
    
    # Relaciones
    usuario = relationship("Usuario", foreign_keys=[usuario_id])
    otorgado_por_usuario = relationship("Usuario", foreign_keys=[otorgado_por])
    
    # Índices
    __table_args__ = (
        UniqueConstraint('usuario_id', 'recurso', 'accion', name='uq_usuario_recurso_accion'),
        Index('idx_permisos_usuario_recurso', 'usuario_id', 'recurso'),
    )
    
    def __repr__(self):
        return f"<PermisosUsuario(usuario_id={self.usuario_id}, recurso='{self.recurso}', accion='{self.accion}')>"
    
    @property
    def esta_vigente(self) -> bool:
        """Verifica si el permiso está vigente."""
        if not self.activo:
            return False
        if self.fecha_expiracion and self.fecha_expiracion < datetime.utcnow():
            return False
        return True
