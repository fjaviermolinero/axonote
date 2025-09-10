"""
Servicio para gestión administrativa del sistema.
Dashboard, métricas, alertas y configuración global.
"""

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc, asc
from datetime import datetime, timezone, timedelta
import json

from app.models.admin import (
    EventoAuditoria, ConfiguracionSistema, MetricaSistema, 
    AlertaSistema, NotificacionAdmin, TipoEvento
)
from app.models.tenant import Tenant, TenantMetrica
from app.models.usuario import Usuario
from app.models.class_session import ClassSession
from app.models.processing_job import ProcessingJob
from app.core.logging import get_logger

logger = get_logger(__name__)


class AdminService:
    """Servicio para funcionalidades administrativas del sistema."""

    def __init__(self, db: Session):
        self.db = db

    # ========================================================================
    # GESTIÓN DE EVENTOS DE AUDITORÍA
    # ========================================================================

    def registrar_evento(
        self,
        tipo_evento: str,
        accion: str,
        resultado: str = "exito",
        usuario_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        ip_address: str = "unknown",
        user_agent: Optional[str] = None,
        descripcion: Optional[str] = None,
        recurso_afectado: Optional[str] = None,
        recurso_id: Optional[str] = None,
        datos_anteriores: Optional[Dict] = None,
        datos_nuevos: Optional[Dict] = None,
        metadatos: Optional[Dict] = None,
        duracion_ms: Optional[int] = None
    ) -> EventoAuditoria:
        """Registra un evento de auditoría en el sistema."""
        evento = EventoAuditoria(
            tipo_evento=tipo_evento,
            accion=accion,
            descripcion=descripcion,
            resultado=resultado,
            usuario_id=usuario_id,
            tenant_id=tenant_id,
            ip_address=ip_address,
            user_agent=user_agent,
            recurso_afectado=recurso_afectado,
            recurso_id=recurso_id,
            datos_anteriores=datos_anteriores,
            datos_nuevos=datos_nuevos,
            metadatos=metadatos or {},
            duracion_ms=duracion_ms
        )

        self.db.add(evento)
        self.db.commit()
        self.db.refresh(evento)

        logger.info(f"Evento auditoria registrado: {tipo_evento} - {accion} - {resultado}")
        return evento

    def obtener_eventos_auditoria(
        self,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
        tipo_evento: Optional[str] = None,
        usuario_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        resultado: Optional[str] = None,
        limite: int = 100,
        offset: int = 0
    ) -> Tuple[List[EventoAuditoria], int]:
        """Obtiene eventos de auditoría con filtros."""
        query = self.db.query(EventoAuditoria)

        if fecha_inicio:
            query = query.filter(EventoAuditoria.fecha_evento >= fecha_inicio)
        if fecha_fin:
            query = query.filter(EventoAuditoria.fecha_evento <= fecha_fin)
        if tipo_evento:
            query = query.filter(EventoAuditoria.tipo_evento == tipo_evento)
        if usuario_id:
            query = query.filter(EventoAuditoria.usuario_id == usuario_id)
        if tenant_id:
            query = query.filter(EventoAuditoria.tenant_id == tenant_id)
        if resultado:
            query = query.filter(EventoAuditoria.resultado == resultado)

        total = query.count()
        eventos = query.order_by(desc(EventoAuditoria.fecha_evento)).offset(offset).limit(limite).all()

        return eventos, total

    # ========================================================================
    # CONFIGURACIÓN DEL SISTEMA
    # ========================================================================

    def obtener_configuracion(self, clave: str) -> Optional[ConfiguracionSistema]:
        """Obtiene una configuración específica del sistema."""
        return self.db.query(ConfiguracionSistema).filter(
            ConfiguracionSistema.clave == clave
        ).first()

    def actualizar_configuracion(
        self,
        clave: str,
        valor: Any,
        usuario_id: Optional[str] = None
    ) -> ConfiguracionSistema:
        """Actualiza o crea una configuración del sistema."""
        config = self.obtener_configuracion(clave)
        
        valor_anterior = None
        if config:
            valor_anterior = config.valor
            config.valor = valor
            config.modificado_por = usuario_id
            config.version += 1
        else:
            # Crear nueva configuración
            config = ConfiguracionSistema(
                clave=clave,
                valor=valor,
                tipo=self._detectar_tipo(valor),
                categoria="general",
                modificado_por=usuario_id
            )
            self.db.add(config)

        self.db.commit()
        self.db.refresh(config)

        # Registrar evento de auditoría
        self.registrar_evento(
            tipo_evento=TipoEvento.CONFIGURAR_SISTEMA,
            accion=f"Configuración '{clave}' {'actualizada' if valor_anterior else 'creada'}",
            usuario_id=usuario_id,
            recurso_afectado="configuracion_sistema",
            recurso_id=clave,
            datos_anteriores={"valor": valor_anterior} if valor_anterior else None,
            datos_nuevos={"valor": valor}
        )

        logger.info(f"Configuración actualizada: {clave} = {valor}")
        return config

    def obtener_todas_configuraciones(
        self,
        categoria: Optional[str] = None,
        incluir_sensibles: bool = False
    ) -> List[ConfiguracionSistema]:
        """Obtiene todas las configuraciones del sistema."""
        query = self.db.query(ConfiguracionSistema)

        if categoria:
            query = query.filter(ConfiguracionSistema.categoria == categoria)
        if not incluir_sensibles:
            query = query.filter(ConfiguracionSistema.sensible == False)

        return query.order_by(ConfiguracionSistema.categoria, ConfiguracionSistema.clave).all()

    # ========================================================================
    # MÉTRICAS DEL SISTEMA
    # ========================================================================

    def registrar_metricas_sistema(self, metricas: Dict[str, Any]) -> MetricaSistema:
        """Registra métricas del sistema."""
        metrica = MetricaSistema(**metricas)
        self.db.add(metrica)
        self.db.commit()
        self.db.refresh(metrica)
        return metrica

    def obtener_metricas_sistema(
        self,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
        limite: int = 100
    ) -> List[MetricaSistema]:
        """Obtiene métricas del sistema para un período."""
        query = self.db.query(MetricaSistema)

        if fecha_inicio:
            query = query.filter(MetricaSistema.timestamp >= fecha_inicio)
        if fecha_fin:
            query = query.filter(MetricaSistema.timestamp <= fecha_fin)

        return query.order_by(desc(MetricaSistema.timestamp)).limit(limite).all()

    def obtener_dashboard_overview(self) -> Dict[str, Any]:
        """Obtiene datos generales para el dashboard administrativo."""
        # Métricas básicas
        total_tenants = self.db.query(Tenant).count()
        tenants_activos = self.db.query(Tenant).filter(Tenant.activo == True).count()
        total_usuarios = self.db.query(Usuario).count()
        usuarios_activos = self.db.query(Usuario).filter(
            Usuario.ultimo_login >= datetime.now(timezone.utc) - timedelta(days=30)
        ).count()

        # Sesiones y procesamiento
        total_sesiones = self.db.query(ClassSession).count()
        sesiones_ultima_semana = self.db.query(ClassSession).filter(
            ClassSession.fecha_creacion >= datetime.now(timezone.utc) - timedelta(days=7)
        ).count()

        jobs_pendientes = self.db.query(ProcessingJob).filter(
            ProcessingJob.estado == "pendiente"
        ).count()
        jobs_procesando = self.db.query(ProcessingJob).filter(
            ProcessingJob.estado == "procesando"
        ).count()

        # Alertas activas
        alertas_criticas = self.db.query(AlertaSistema).filter(
            and_(AlertaSistema.activa == True, AlertaSistema.severidad == "critica")
        ).count()

        # Métricas recientes (última hora)
        metricas_recientes = self.db.query(MetricaSistema).filter(
            MetricaSistema.timestamp >= datetime.now(timezone.utc) - timedelta(hours=1)
        ).order_by(desc(MetricaSistema.timestamp)).first()

        # Uso por plan
        uso_por_plan = self.db.query(
            Tenant.plan,
            func.count(Tenant.id).label('count')
        ).filter(Tenant.activo == True).group_by(Tenant.plan).all()

        return {
            "resumen": {
                "total_tenants": total_tenants,
                "tenants_activos": tenants_activos,
                "total_usuarios": total_usuarios,
                "usuarios_activos": usuarios_activos,
                "total_sesiones": total_sesiones,
                "sesiones_ultima_semana": sesiones_ultima_semana,
                "jobs_pendientes": jobs_pendientes,
                "jobs_procesando": jobs_procesando,
                "alertas_criticas": alertas_criticas
            },
            "metricas_sistema": {
                "cpu_usage": metricas_recientes.cpu_usage_percent if metricas_recientes else 0,
                "memory_usage": metricas_recientes.memory_usage_percent if metricas_recientes else 0,
                "response_time_avg": metricas_recientes.response_time_avg_ms if metricas_recientes else 0,
                "requests_total": metricas_recientes.requests_total if metricas_recientes else 0
            },
            "distribucion_planes": [{"plan": plan, "count": count} for plan, count in uso_por_plan],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    # ========================================================================
    # GESTIÓN DE ALERTAS
    # ========================================================================

    def crear_alerta(
        self,
        nombre: str,
        descripcion: str,
        severidad: str,
        categoria: str,
        tenant_id: Optional[str] = None,
        usuario_id: Optional[str] = None,
        recurso_afectado: Optional[str] = None,
        valor_actual: Optional[float] = None,
        valor_umbral: Optional[float] = None,
        metrica_asociada: Optional[str] = None,
        datos_contexto: Optional[Dict] = None,
        accion_automatica: Optional[str] = None
    ) -> AlertaSistema:
        """Crea una nueva alerta del sistema."""
        alerta = AlertaSistema(
            nombre=nombre,
            descripcion=descripcion,
            severidad=severidad,
            categoria=categoria,
            tenant_id=tenant_id,
            usuario_id=usuario_id,
            recurso_afectado=recurso_afectado,
            valor_actual=valor_actual,
            valor_umbral=valor_umbral,
            metrica_asociada=metrica_asociada,
            datos_contexto=datos_contexto or {},
            accion_automatica=accion_automatica
        )

        self.db.add(alerta)
        self.db.commit()
        self.db.refresh(alerta)

        logger.warning(f"Alerta creada: {nombre} - {severidad}")
        return alerta

    def reconocer_alerta(
        self,
        alerta_id: str,
        reconocida_por: str
    ) -> Optional[AlertaSistema]:
        """Marca una alerta como reconocida."""
        alerta = self.db.query(AlertaSistema).filter(AlertaSistema.id == alerta_id).first()
        if not alerta or not alerta.puede_reconocerse():
            return None

        alerta.reconocida = True
        alerta.fecha_reconocimiento = datetime.now(timezone.utc)
        alerta.reconocida_por = reconocida_por

        self.db.commit()
        self.db.refresh(alerta)

        logger.info(f"Alerta reconocida: {alerta.nombre}")
        return alerta

    def resolver_alerta(
        self,
        alerta_id: str,
        resuelta_por: str,
        notas_resolucion: Optional[str] = None
    ) -> Optional[AlertaSistema]:
        """Marca una alerta como resuelta."""
        alerta = self.db.query(AlertaSistema).filter(AlertaSistema.id == alerta_id).first()
        if not alerta or not alerta.puede_resolverse():
            return None

        alerta.resuelta = True
        alerta.activa = False
        alerta.fecha_resolucion = datetime.now(timezone.utc)
        alerta.resuelta_por = resuelta_por
        alerta.notas_resolucion = notas_resolucion

        self.db.commit()
        self.db.refresh(alerta)

        logger.info(f"Alerta resuelta: {alerta.nombre}")
        return alerta

    def obtener_alertas(
        self,
        activas_solo: bool = True,
        severidad: Optional[str] = None,
        categoria: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limite: int = 50
    ) -> List[AlertaSistema]:
        """Obtiene alertas del sistema con filtros."""
        query = self.db.query(AlertaSistema)

        if activas_solo:
            query = query.filter(AlertaSistema.activa == True)
        if severidad:
            query = query.filter(AlertaSistema.severidad == severidad)
        if categoria:
            query = query.filter(AlertaSistema.categoria == categoria)
        if tenant_id:
            query = query.filter(AlertaSistema.tenant_id == tenant_id)

        return query.order_by(
            desc(AlertaSistema.fecha_creacion)
        ).limit(limite).all()

    # ========================================================================
    # NOTIFICACIONES ADMINISTRATIVAS
    # ========================================================================

    def crear_notificacion(
        self,
        usuario_id: str,
        titulo: str,
        mensaje: str,
        tipo: str = "info",
        categoria: str = "system",
        datos_adicionales: Optional[Dict] = None,
        accion_url: Optional[str] = None,
        accion_texto: Optional[str] = None,
        fecha_expiracion: Optional[datetime] = None
    ) -> NotificacionAdmin:
        """Crea una notificación para un administrador."""
        notificacion = NotificacionAdmin(
            usuario_id=usuario_id,
            titulo=titulo,
            mensaje=mensaje,
            tipo=tipo,
            categoria=categoria,
            datos_adicionales=datos_adicionales or {},
            accion_url=accion_url,
            accion_texto=accion_texto,
            fecha_expiracion=fecha_expiracion
        )

        self.db.add(notificacion)
        self.db.commit()
        self.db.refresh(notificacion)

        logger.info(f"Notificación creada para usuario {usuario_id}: {titulo}")
        return notificacion

    def obtener_notificaciones_usuario(
        self,
        usuario_id: str,
        no_leidas_solo: bool = False,
        limite: int = 20
    ) -> List[NotificacionAdmin]:
        """Obtiene notificaciones de un usuario específico."""
        query = self.db.query(NotificacionAdmin).filter(
            NotificacionAdmin.usuario_id == usuario_id
        )

        if no_leidas_solo:
            query = query.filter(NotificacionAdmin.leida == False)

        # Filtrar expiradas
        query = query.filter(
            or_(
                NotificacionAdmin.fecha_expiracion.is_(None),
                NotificacionAdmin.fecha_expiracion > datetime.now(timezone.utc)
            )
        )

        return query.order_by(desc(NotificacionAdmin.fecha_creacion)).limit(limite).all()

    def marcar_notificacion_leida(self, notificacion_id: str) -> Optional[NotificacionAdmin]:
        """Marca una notificación como leída."""
        notificacion = self.db.query(NotificacionAdmin).filter(
            NotificacionAdmin.id == notificacion_id
        ).first()

        if not notificacion:
            return None

        notificacion.leida = True
        notificacion.fecha_lectura = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(notificacion)

        return notificacion

    # ========================================================================
    # UTILIDADES PRIVADAS
    # ========================================================================

    def _detectar_tipo(self, valor: Any) -> str:
        """Detecta el tipo de una configuración basado en su valor."""
        if isinstance(valor, bool):
            return "boolean"
        elif isinstance(valor, int):
            return "number"
        elif isinstance(valor, float):
            return "number"
        elif isinstance(valor, str):
            return "string"
        elif isinstance(valor, (list, tuple)):
            return "array"
        elif isinstance(valor, dict):
            return "json"
        else:
            return "string"
