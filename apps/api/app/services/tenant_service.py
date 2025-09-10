"""
Servicio para gestión de tenants (multi-tenant architecture).
Maneja organizaciones, configuraciones y métricas por tenant.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from datetime import datetime, timezone, timedelta
import secrets
import string
import re

from app.models.tenant import Tenant, TenantConfiguracion, TenantMetrica, TenantInvitacion
from app.models.usuario import Usuario
from app.core.logging import get_logger

logger = get_logger(__name__)


class TenantService:
    """Servicio para gestión de tenants y arquitectura multi-tenant."""

    def __init__(self, db: Session):
        self.db = db

    def crear_tenant(
        self,
        nombre: str,
        tipo_institucion: str,
        pais: str,
        ciudad: str,
        email_contacto: str,
        plan: str = "basic",
        configuracion_inicial: Optional[Dict[str, Any]] = None,
        branding_inicial: Optional[Dict[str, Any]] = None
    ) -> Tenant:
        """
        Crea un nuevo tenant con configuración inicial.
        """
        # Generar slug único
        slug = self._generar_slug(nombre)
        
        # Verificar que el slug sea único
        while self.db.query(Tenant).filter(Tenant.slug == slug).first():
            slug = f"{slug}-{secrets.token_hex(3)}"

        # Configuración por defecto según el plan
        configuracion = self._configuracion_por_plan(plan)
        if configuracion_inicial:
            configuracion.update(configuracion_inicial)

        # Branding por defecto
        branding = {
            "color_primario": "#2563eb",
            "color_secundario": "#1e40af",
            "nombre_mostrar": nombre
        }
        if branding_inicial:
            branding.update(branding_inicial)

        # Crear tenant
        tenant = Tenant(
            nombre=nombre,
            slug=slug,
            tipo_institucion=tipo_institucion,
            pais=pais,
            ciudad=ciudad,
            email_contacto=email_contacto,
            plan=plan,
            configuracion=configuracion,
            branding=branding,
            **self._limites_por_plan(plan)
        )

        self.db.add(tenant)
        self.db.commit()
        self.db.refresh(tenant)

        # Crear configuraciones iniciales
        self._crear_configuraciones_iniciales(tenant.id)

        logger.info(f"Tenant creado: {tenant.nombre} (ID: {tenant.id})")
        return tenant

    def obtener_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Obtiene un tenant por ID."""
        return self.db.query(Tenant).filter(Tenant.id == tenant_id).first()

    def obtener_tenant_por_slug(self, slug: str) -> Optional[Tenant]:
        """Obtiene un tenant por slug."""
        return self.db.query(Tenant).filter(Tenant.slug == slug).first()

    def obtener_tenant_por_dominio(self, dominio: str) -> Optional[Tenant]:
        """Obtiene un tenant por dominio personalizado."""
        return self.db.query(Tenant).filter(Tenant.dominio_personalizado == dominio).first()

    def listar_tenants(
        self,
        activos_solo: bool = True,
        plan: Optional[str] = None,
        tipo_institucion: Optional[str] = None,
        pais: Optional[str] = None,
        limite: int = 100,
        offset: int = 0
    ) -> List[Tenant]:
        """Lista tenants con filtros opcionales."""
        query = self.db.query(Tenant)

        if activos_solo:
            query = query.filter(Tenant.activo == True)
        if plan:
            query = query.filter(Tenant.plan == plan)
        if tipo_institucion:
            query = query.filter(Tenant.tipo_institucion == tipo_institucion)
        if pais:
            query = query.filter(Tenant.pais == pais)

        return query.offset(offset).limit(limite).all()

    def actualizar_tenant(
        self,
        tenant_id: str,
        datos: Dict[str, Any],
        usuario_id: Optional[str] = None
    ) -> Optional[Tenant]:
        """Actualiza un tenant con los datos proporcionados."""
        tenant = self.obtener_tenant(tenant_id)
        if not tenant:
            return None

        # Campos actualizables
        campos_permitidos = {
            'nombre', 'tipo_institucion', 'ciudad', 'direccion', 'telefono',
            'email_contacto', 'sitio_web', 'configuracion', 'branding'
        }

        for campo, valor in datos.items():
            if campo in campos_permitidos and hasattr(tenant, campo):
                setattr(tenant, campo, valor)

        # Si se actualiza el nombre, regenerar slug si es necesario
        if 'nombre' in datos and datos['nombre'] != tenant.nombre:
            nuevo_slug = self._generar_slug(datos['nombre'])
            if nuevo_slug != tenant.slug:
                # Verificar que el nuevo slug sea único
                while self.db.query(Tenant).filter(
                    and_(Tenant.slug == nuevo_slug, Tenant.id != tenant_id)
                ).first():
                    nuevo_slug = f"{nuevo_slug}-{secrets.token_hex(3)}"
                tenant.slug = nuevo_slug

        self.db.commit()
        self.db.refresh(tenant)

        logger.info(f"Tenant actualizado: {tenant.nombre} (ID: {tenant_id})")
        return tenant

    def cambiar_plan(
        self,
        tenant_id: str,
        nuevo_plan: str,
        usuario_id: Optional[str] = None
    ) -> Optional[Tenant]:
        """Cambia el plan de un tenant y ajusta los límites."""
        tenant = self.obtener_tenant(tenant_id)
        if not tenant:
            return None

        plan_anterior = tenant.plan
        limites = self._limites_por_plan(nuevo_plan)
        
        tenant.plan = nuevo_plan
        tenant.limite_usuarios = limites['limite_usuarios']
        tenant.limite_almacenamiento_gb = limites['limite_almacenamiento_gb']
        tenant.limite_horas_procesamiento = limites['limite_horas_procesamiento']

        # Actualizar configuración según el nuevo plan
        configuracion_nueva = self._configuracion_por_plan(nuevo_plan)
        tenant.configuracion.update(configuracion_nueva)

        self.db.commit()
        self.db.refresh(tenant)

        logger.info(f"Plan cambiado para tenant {tenant.nombre}: {plan_anterior} → {nuevo_plan}")
        return tenant

    def suspender_tenant(
        self,
        tenant_id: str,
        motivo: str,
        usuario_id: Optional[str] = None
    ) -> Optional[Tenant]:
        """Suspende un tenant."""
        tenant = self.obtener_tenant(tenant_id)
        if not tenant:
            return None

        tenant.activo = False
        tenant.fecha_suspension = datetime.now(timezone.utc)
        tenant.motivo_suspension = motivo

        self.db.commit()
        self.db.refresh(tenant)

        logger.warning(f"Tenant suspendido: {tenant.nombre} - Motivo: {motivo}")
        return tenant

    def reactivar_tenant(self, tenant_id: str, usuario_id: Optional[str] = None) -> Optional[Tenant]:
        """Reactiva un tenant suspendido."""
        tenant = self.obtener_tenant(tenant_id)
        if not tenant:
            return None

        tenant.activo = True
        tenant.fecha_suspension = None
        tenant.motivo_suspension = None

        self.db.commit()
        self.db.refresh(tenant)

        logger.info(f"Tenant reactivado: {tenant.nombre}")
        return tenant

    def obtener_metricas_tenant(
        self,
        tenant_id: str,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
        tipo_periodo: str = "mensual"
    ) -> List[TenantMetrica]:
        """Obtiene métricas de un tenant para un período específico."""
        query = self.db.query(TenantMetrica).filter(TenantMetrica.tenant_id == tenant_id)

        if fecha_inicio:
            query = query.filter(TenantMetrica.fecha_inicio >= fecha_inicio)
        if fecha_fin:
            query = query.filter(TenantMetrica.fecha_fin <= fecha_fin)
        if tipo_periodo:
            query = query.filter(TenantMetrica.tipo_periodo == tipo_periodo)

        return query.order_by(desc(TenantMetrica.fecha_inicio)).all()

    def crear_invitacion(
        self,
        tenant_id: str,
        email: str,
        rol_asignado: str,
        mensaje_personalizado: Optional[str] = None,
        enviada_por: str = None,
        dias_expiracion: int = 7
    ) -> TenantInvitacion:
        """Crea una invitación para unirse a un tenant."""
        # Verificar que el tenant existe
        tenant = self.obtener_tenant(tenant_id)
        if not tenant:
            raise ValueError("Tenant no encontrado")

        # Verificar que el usuario no existe ya en el tenant
        usuario_existente = self.db.query(Usuario).filter(
            and_(Usuario.email == email, Usuario.tenant_id == tenant_id)
        ).first()
        if usuario_existente:
            raise ValueError("Usuario ya pertenece a este tenant")

        # Generar token único
        token = secrets.token_urlsafe(32)
        fecha_expiracion = datetime.now(timezone.utc) + timedelta(days=dias_expiracion)

        invitacion = TenantInvitacion(
            tenant_id=tenant_id,
            email=email,
            rol_asignado=rol_asignado,
            token=token,
            fecha_expiracion=fecha_expiracion,
            mensaje_personalizado=mensaje_personalizado,
            enviada_por=enviada_por
        )

        self.db.add(invitacion)
        self.db.commit()
        self.db.refresh(invitacion)

        logger.info(f"Invitación creada para {email} en tenant {tenant.nombre}")
        return invitacion

    def procesar_invitacion(self, token: str, usuario_id: str) -> Optional[TenantInvitacion]:
        """Procesa una invitación aceptada por un usuario."""
        invitacion = self.db.query(TenantInvitacion).filter(
            TenantInvitacion.token == token
        ).first()

        if not invitacion:
            return None

        if invitacion.expirada:
            raise ValueError("La invitación ha expirado")

        if invitacion.aceptada:
            raise ValueError("La invitación ya ha sido aceptada")

        # Marcar como aceptada
        invitacion.aceptada = True
        invitacion.fecha_aceptacion = datetime.now(timezone.utc)
        invitacion.usuario_id = usuario_id

        self.db.commit()
        self.db.refresh(invitacion)

        logger.info(f"Invitación aceptada: {invitacion.email} → tenant {invitacion.tenant_id}")
        return invitacion

    def _generar_slug(self, nombre: str) -> str:
        """Genera un slug a partir del nombre del tenant."""
        # Convertir a minúsculas y reemplazar espacios
        slug = nombre.lower().replace(' ', '-')
        
        # Remover caracteres especiales excepto guiones
        slug = re.sub(r'[^a-z0-9\-]', '', slug)
        
        # Remover guiones múltiples
        slug = re.sub(r'-+', '-', slug)
        
        # Remover guiones al inicio y final
        slug = slug.strip('-')
        
        # Limitar longitud
        return slug[:50]

    def _limites_por_plan(self, plan: str) -> Dict[str, int]:
        """Retorna los límites según el plan."""
        limites = {
            "basic": {
                "limite_usuarios": 25,
                "limite_almacenamiento_gb": 10,
                "limite_horas_procesamiento": 50
            },
            "pro": {
                "limite_usuarios": 100,
                "limite_almacenamiento_gb": 100,
                "limite_horas_procesamiento": 500
            },
            "enterprise": {
                "limite_usuarios": 1000,
                "limite_almacenamiento_gb": 1000,
                "limite_horas_procesamiento": 10000
            }
        }
        return limites.get(plan, limites["basic"])

    def _configuracion_por_plan(self, plan: str) -> Dict[str, Any]:
        """Retorna la configuración por defecto según el plan."""
        configuraciones = {
            "basic": {
                "analytics_avanzado": False,
                "api_acceso": False,
                "sso_habilitado": False,
                "retention_dias": 90,
                "export_formatos": ["pdf", "json"],
                "whisper_model": "medium"
            },
            "pro": {
                "analytics_avanzado": True,
                "api_acceso": True,
                "sso_habilitado": False,
                "retention_dias": 365,
                "export_formatos": ["pdf", "docx", "json", "csv"],
                "whisper_model": "large-v3"
            },
            "enterprise": {
                "analytics_avanzado": True,
                "api_acceso": True,
                "sso_habilitado": True,
                "retention_dias": 1095,  # 3 años
                "export_formatos": ["pdf", "docx", "json", "csv", "anki", "html"],
                "whisper_model": "large-v3",
                "white_label": True,
                "backup_automatico": True,
                "soporte_prioritario": True
            }
        }
        
        base_config = {
            "idioma_por_defecto": "es",
            "zona_horaria": "Europe/Madrid",
            "diarizacion_habilitada": True,
            "research_automatico": True,
            "tts_habilitado": True,
            "ocr_habilitado": True,
            "notificaciones_email": True
        }
        
        plan_config = configuraciones.get(plan, configuraciones["basic"])
        base_config.update(plan_config)
        return base_config

    def _crear_configuraciones_iniciales(self, tenant_id: str):
        """Crea configuraciones iniciales para un nuevo tenant."""
        configuraciones_iniciales = [
            {
                "clave": "max_file_size_mb",
                "valor": 500,
                "tipo": "number",
                "categoria": "uploads",
                "descripcion": "Tamaño máximo de archivo en MB"
            },
            {
                "clave": "session_timeout_minutes",
                "valor": 480,  # 8 horas
                "tipo": "number",
                "categoria": "security",
                "descripcion": "Timeout de sesión en minutos"
            },
            {
                "clave": "backup_frequency_days",
                "valor": 7,
                "tipo": "number",
                "categoria": "backup",
                "descripcion": "Frecuencia de backup automático en días"
            }
        ]

        for config in configuraciones_iniciales:
            config_obj = TenantConfiguracion(
                tenant_id=tenant_id,
                **config
            )
            self.db.add(config_obj)

        self.db.commit()
