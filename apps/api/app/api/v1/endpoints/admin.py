"""
Endpoints para administración del sistema.
Dashboard administrativo, gestión de tenants, usuarios y configuración.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta

from app.core.database import get_db
from app.core.security import get_current_active_user
from app.models.usuario import Usuario
from app.services.admin_service import AdminService
from app.services.tenant_service import TenantService
from app.schemas.base import ResponseModel
from app.core.decorador_metricas import medir_tiempo_respuesta

router = APIRouter(prefix="/admin", tags=["admin"])


def get_admin_user(current_user: Usuario = Depends(get_current_active_user)) -> Usuario:
    """Verifica que el usuario actual sea administrador."""
    if not current_user.es_admin:
        raise HTTPException(status_code=403, detail="Acceso denegado: Se requieren privilegios de administrador")
    return current_user


@router.get("/dashboard/overview")
@medir_tiempo_respuesta
async def obtener_dashboard_overview(
    request: Request,
    db: Session = Depends(get_db),
    admin_user: Usuario = Depends(get_admin_user)
) -> ResponseModel:
    """
    Obtiene datos generales para el dashboard administrativo.
    """
    admin_service = AdminService(db)
    
    try:
        overview = admin_service.obtener_dashboard_overview()
        
        # Registrar acceso al dashboard
        admin_service.registrar_evento(
            tipo_evento="dashboard_access",
            accion="Dashboard overview consultado",
            usuario_id=str(admin_user.id),
            ip_address=request.client.host if request.client else "unknown"
        )
        
        return ResponseModel(
            status="success",
            message="Dashboard overview obtenido exitosamente",
            data=overview
        )
        
    except Exception as e:
        admin_service.registrar_evento(
            tipo_evento="error_sistema",
            accion="Error obteniendo dashboard overview",
            resultado="error",
            usuario_id=str(admin_user.id),
            descripcion=str(e)
        )
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/tenants")
@medir_tiempo_respuesta
async def listar_tenants_admin(
    activos_solo: bool = Query(True, description="Mostrar solo tenants activos"),
    plan: Optional[str] = Query(None, description="Filtrar por plan"),
    tipo_institucion: Optional[str] = Query(None, description="Filtrar por tipo de institución"),
    pais: Optional[str] = Query(None, description="Filtrar por país"),
    limite: int = Query(50, ge=1, le=500, description="Límite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginación"),
    db: Session = Depends(get_db),
    admin_user: Usuario = Depends(get_admin_user)
) -> ResponseModel:
    """
    Lista todos los tenants del sistema con filtros opcionales.
    """
    tenant_service = TenantService(db)
    
    try:
        tenants = tenant_service.listar_tenants(
            activos_solo=activos_solo,
            plan=plan,
            tipo_institucion=tipo_institucion,
            pais=pais,
            limite=limite,
            offset=offset
        )
        
        # Preparar datos para respuesta
        tenants_data = []
        for tenant in tenants:
            tenants_data.append({
                "id": str(tenant.id),
                "nombre": tenant.nombre,
                "slug": tenant.slug,
                "tipo_institucion": tenant.tipo_institucion,
                "pais": tenant.pais,
                "ciudad": tenant.ciudad,
                "plan": tenant.plan,
                "activo": tenant.activo,
                "fecha_creacion": tenant.fecha_creacion.isoformat() if tenant.fecha_creacion else None,
                "usuarios_count": len(tenant.usuarios),
                "limite_usuarios": tenant.limite_usuarios,
                "limite_almacenamiento_gb": tenant.limite_almacenamiento_gb,
                "email_contacto": tenant.email_contacto,
                "fecha_suspension": tenant.fecha_suspension.isoformat() if tenant.fecha_suspension else None,
                "motivo_suspension": tenant.motivo_suspension
            })
        
        return ResponseModel(
            status="success",
            message=f"Se encontraron {len(tenants)} tenants",
            data={
                "tenants": tenants_data,
                "pagination": {
                    "limite": limite,
                    "offset": offset,
                    "total": len(tenants_data)
                }
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error obteniendo lista de tenants")


@router.get("/tenants/{tenant_id}")
@medir_tiempo_respuesta
async def obtener_tenant_detalle(
    tenant_id: str,
    db: Session = Depends(get_db),
    admin_user: Usuario = Depends(get_admin_user)
) -> ResponseModel:
    """
    Obtiene detalles completos de un tenant específico.
    """
    tenant_service = TenantService(db)
    admin_service = AdminService(db)
    
    try:
        tenant = tenant_service.obtener_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")
        
        # Obtener métricas recientes del tenant
        fecha_inicio = datetime.now(timezone.utc) - timedelta(days=30)
        metricas = tenant_service.obtener_metricas_tenant(
            tenant_id=tenant_id,
            fecha_inicio=fecha_inicio,
            tipo_periodo="mensual"
        )
        
        # Obtener eventos de auditoría recientes
        eventos, _ = admin_service.obtener_eventos_auditoria(
            tenant_id=tenant_id,
            fecha_inicio=fecha_inicio,
            limite=20
        )
        
        tenant_data = {
            "id": str(tenant.id),
            "nombre": tenant.nombre,
            "slug": tenant.slug,
            "dominio_personalizado": tenant.dominio_personalizado,
            "tipo_institucion": tenant.tipo_institucion,
            "pais": tenant.pais,
            "ciudad": tenant.ciudad,
            "direccion": tenant.direccion,
            "telefono": tenant.telefono,
            "email_contacto": tenant.email_contacto,
            "sitio_web": tenant.sitio_web,
            "plan": tenant.plan,
            "activo": tenant.activo,
            "fecha_creacion": tenant.fecha_creacion.isoformat() if tenant.fecha_creacion else None,
            "fecha_suspension": tenant.fecha_suspension.isoformat() if tenant.fecha_suspension else None,
            "motivo_suspension": tenant.motivo_suspension,
            "configuracion": tenant.configuracion_completa,
            "branding": tenant.branding_completo,
            "limites": {
                "usuarios": tenant.limite_usuarios,
                "almacenamiento_gb": tenant.limite_almacenamiento_gb,
                "horas_procesamiento": tenant.limite_horas_procesamiento
            },
            "uso_actual": {
                "usuarios": len(tenant.usuarios),
                "almacenamiento_gb": tenant.uso_almacenamiento_gb(),
                "horas_mes_actual": tenant.uso_horas_mes_actual()
            },
            "usuarios": [
                {
                    "id": str(u.id),
                    "nombre_completo": u.nombre_completo,
                    "email": u.email,
                    "rol": u.rol,
                    "activo": u.activo,
                    "ultimo_login": u.ultimo_login.isoformat() if u.ultimo_login else None
                }
                for u in tenant.usuarios
            ],
            "metricas_recientes": [
                {
                    "fecha_inicio": m.fecha_inicio.isoformat(),
                    "fecha_fin": m.fecha_fin.isoformat(),
                    "usuarios_activos": m.usuarios_activos,
                    "sesiones_procesadas": m.sesiones_procesadas,
                    "minutos_audio_procesados": m.minutos_audio_procesados
                }
                for m in metricas[:5]  # Solo las 5 más recientes
            ],
            "eventos_recientes": [
                {
                    "fecha": e.fecha_evento.isoformat(),
                    "tipo_evento": e.tipo_evento,
                    "accion": e.accion,
                    "resultado": e.resultado,
                    "usuario": e.usuario.nombre_completo if e.usuario else None
                }
                for e in eventos[:10]  # Solo los 10 más recientes
            ]
        }
        
        return ResponseModel(
            status="success",
            message="Detalles del tenant obtenidos exitosamente",
            data=tenant_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error obteniendo detalles del tenant")


@router.put("/tenants/{tenant_id}/plan")
@medir_tiempo_respuesta
async def cambiar_plan_tenant(
    tenant_id: str,
    nuevo_plan: str,
    request: Request,
    db: Session = Depends(get_db),
    admin_user: Usuario = Depends(get_admin_user)
) -> ResponseModel:
    """
    Cambia el plan de un tenant.
    """
    if nuevo_plan not in ["basic", "pro", "enterprise"]:
        raise HTTPException(status_code=400, detail="Plan inválido")
    
    tenant_service = TenantService(db)
    admin_service = AdminService(db)
    
    try:
        tenant = tenant_service.cambiar_plan(
            tenant_id=tenant_id,
            nuevo_plan=nuevo_plan,
            usuario_id=str(admin_user.id)
        )
        
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")
        
        # Registrar evento de auditoría
        admin_service.registrar_evento(
            tipo_evento="cambiar_plan",
            accion=f"Plan cambiado a {nuevo_plan}",
            usuario_id=str(admin_user.id),
            tenant_id=tenant_id,
            ip_address=request.client.host if request.client else "unknown",
            recurso_afectado="tenant",
            recurso_id=tenant_id,
            datos_nuevos={"plan": nuevo_plan}
        )
        
        return ResponseModel(
            status="success",
            message=f"Plan del tenant cambiado a {nuevo_plan}",
            data={
                "tenant_id": str(tenant.id),
                "plan_anterior": tenant.plan,
                "plan_nuevo": nuevo_plan
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error cambiando plan del tenant")


@router.put("/tenants/{tenant_id}/suspend")
@medir_tiempo_respuesta
async def suspender_tenant(
    tenant_id: str,
    motivo: str,
    request: Request,
    db: Session = Depends(get_db),
    admin_user: Usuario = Depends(get_admin_user)
) -> ResponseModel:
    """
    Suspende un tenant.
    """
    if not motivo or len(motivo.strip()) < 10:
        raise HTTPException(status_code=400, detail="Motivo de suspensión requerido (mínimo 10 caracteres)")
    
    tenant_service = TenantService(db)
    admin_service = AdminService(db)
    
    try:
        tenant = tenant_service.suspender_tenant(
            tenant_id=tenant_id,
            motivo=motivo,
            usuario_id=str(admin_user.id)
        )
        
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")
        
        # Registrar evento de auditoría
        admin_service.registrar_evento(
            tipo_evento="suspender_tenant",
            accion=f"Tenant suspendido: {motivo}",
            usuario_id=str(admin_user.id),
            tenant_id=tenant_id,
            ip_address=request.client.host if request.client else "unknown",
            recurso_afectado="tenant",
            recurso_id=tenant_id,
            datos_nuevos={"motivo": motivo}
        )
        
        return ResponseModel(
            status="success",
            message="Tenant suspendido exitosamente",
            data={
                "tenant_id": str(tenant.id),
                "motivo": motivo,
                "fecha_suspension": tenant.fecha_suspension.isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error suspendiendo tenant")


@router.put("/tenants/{tenant_id}/reactivate")
@medir_tiempo_respuesta
async def reactivar_tenant(
    tenant_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin_user: Usuario = Depends(get_admin_user)
) -> ResponseModel:
    """
    Reactiva un tenant suspendido.
    """
    tenant_service = TenantService(db)
    admin_service = AdminService(db)
    
    try:
        tenant = tenant_service.reactivar_tenant(
            tenant_id=tenant_id,
            usuario_id=str(admin_user.id)
        )
        
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")
        
        # Registrar evento de auditoría
        admin_service.registrar_evento(
            tipo_evento="reactivar_tenant",
            accion="Tenant reactivado",
            usuario_id=str(admin_user.id),
            tenant_id=tenant_id,
            ip_address=request.client.host if request.client else "unknown",
            recurso_afectado="tenant",
            recurso_id=tenant_id
        )
        
        return ResponseModel(
            status="success",
            message="Tenant reactivado exitosamente",
            data={
                "tenant_id": str(tenant.id),
                "fecha_reactivacion": datetime.now(timezone.utc).isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error reactivando tenant")


@router.get("/system/metrics")
@medir_tiempo_respuesta
async def obtener_metricas_sistema(
    horas: int = Query(24, ge=1, le=168, description="Horas de historial"),
    db: Session = Depends(get_db),
    admin_user: Usuario = Depends(get_admin_user)
) -> ResponseModel:
    """
    Obtiene métricas del sistema para un período específico.
    """
    admin_service = AdminService(db)
    
    try:
        fecha_inicio = datetime.now(timezone.utc) - timedelta(hours=horas)
        metricas = admin_service.obtener_metricas_sistema(
            fecha_inicio=fecha_inicio,
            limite=100
        )
        
        metricas_data = [
            {
                "timestamp": m.timestamp.isoformat(),
                "cpu_usage": m.cpu_usage_percent,
                "memory_usage": m.memory_usage_percent,
                "disk_usage": m.disk_usage_percent,
                "gpu_usage": m.gpu_usage_percent,
                "response_time_avg": m.response_time_avg_ms,
                "requests_total": m.requests_total,
                "usuarios_activos": m.usuarios_activos,
                "jobs_pendientes": m.jobs_pendientes,
                "jobs_procesando": m.jobs_procesando
            }
            for m in metricas
        ]
        
        return ResponseModel(
            status="success",
            message=f"Métricas de las últimas {horas} horas obtenidas",
            data={
                "metricas": metricas_data,
                "periodo_horas": horas,
                "total_puntos": len(metricas_data)
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error obteniendo métricas del sistema")


@router.get("/system/alerts")
@medir_tiempo_respuesta
async def obtener_alertas_sistema(
    activas_solo: bool = Query(True, description="Mostrar solo alertas activas"),
    severidad: Optional[str] = Query(None, description="Filtrar por severidad"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoría"),
    limite: int = Query(50, ge=1, le=200, description="Límite de resultados"),
    db: Session = Depends(get_db),
    admin_user: Usuario = Depends(get_admin_user)
) -> ResponseModel:
    """
    Obtiene alertas del sistema con filtros opcionales.
    """
    admin_service = AdminService(db)
    
    try:
        alertas = admin_service.obtener_alertas(
            activas_solo=activas_solo,
            severidad=severidad,
            categoria=categoria,
            limite=limite
        )
        
        alertas_data = [
            {
                "id": str(a.id),
                "nombre": a.nombre,
                "descripcion": a.descripcion,
                "severidad": a.severidad,
                "categoria": a.categoria,
                "activa": a.activa,
                "reconocida": a.reconocida,
                "resuelta": a.resuelta,
                "fecha_creacion": a.fecha_creacion.isoformat(),
                "fecha_reconocimiento": a.fecha_reconocimiento.isoformat() if a.fecha_reconocimiento else None,
                "fecha_resolucion": a.fecha_resolucion.isoformat() if a.fecha_resolucion else None,
                "valor_actual": a.valor_actual,
                "valor_umbral": a.valor_umbral,
                "metrica_asociada": a.metrica_asociada,
                "tenant_id": str(a.tenant_id) if a.tenant_id else None,
                "duracion_activa_segundos": int(a.duracion_activa.total_seconds()) if a.activa else None
            }
            for a in alertas
        ]
        
        return ResponseModel(
            status="success",
            message=f"Se encontraron {len(alertas)} alertas",
            data={
                "alertas": alertas_data,
                "filtros": {
                    "activas_solo": activas_solo,
                    "severidad": severidad,
                    "categoria": categoria
                }
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error obteniendo alertas del sistema")


@router.put("/system/alerts/{alerta_id}/acknowledge")
@medir_tiempo_respuesta
async def reconocer_alerta(
    alerta_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin_user: Usuario = Depends(get_admin_user)
) -> ResponseModel:
    """
    Reconoce una alerta del sistema.
    """
    admin_service = AdminService(db)
    
    try:
        alerta = admin_service.reconocer_alerta(
            alerta_id=alerta_id,
            reconocida_por=str(admin_user.id)
        )
        
        if not alerta:
            raise HTTPException(status_code=404, detail="Alerta no encontrada o no puede ser reconocida")
        
        # Registrar evento de auditoría
        admin_service.registrar_evento(
            tipo_evento="reconocer_alerta",
            accion=f"Alerta reconocida: {alerta.nombre}",
            usuario_id=str(admin_user.id),
            ip_address=request.client.host if request.client else "unknown",
            recurso_afectado="alerta",
            recurso_id=alerta_id
        )
        
        return ResponseModel(
            status="success",
            message="Alerta reconocida exitosamente",
            data={
                "alerta_id": str(alerta.id),
                "fecha_reconocimiento": alerta.fecha_reconocimiento.isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error reconociendo alerta")


@router.get("/audit/events")
@medir_tiempo_respuesta
async def obtener_eventos_auditoria(
    fecha_inicio: Optional[datetime] = Query(None, description="Fecha inicio del período"),
    fecha_fin: Optional[datetime] = Query(None, description="Fecha fin del período"),
    tipo_evento: Optional[str] = Query(None, description="Tipo de evento"),
    usuario_id: Optional[str] = Query(None, description="ID del usuario"),
    tenant_id: Optional[str] = Query(None, description="ID del tenant"),
    resultado: Optional[str] = Query(None, description="Resultado del evento"),
    limite: int = Query(100, ge=1, le=1000, description="Límite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginación"),
    db: Session = Depends(get_db),
    admin_user: Usuario = Depends(get_admin_user)
) -> ResponseModel:
    """
    Obtiene eventos de auditoría con filtros opcionales.
    """
    admin_service = AdminService(db)
    
    try:
        eventos, total = admin_service.obtener_eventos_auditoria(
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            tipo_evento=tipo_evento,
            usuario_id=usuario_id,
            tenant_id=tenant_id,
            resultado=resultado,
            limite=limite,
            offset=offset
        )
        
        eventos_data = [
            {
                "id": str(e.id),
                "fecha_evento": e.fecha_evento.isoformat(),
                "tipo_evento": e.tipo_evento,
                "accion": e.accion,
                "descripcion": e.descripcion,
                "resultado": e.resultado,
                "usuario": {
                    "id": str(e.usuario.id),
                    "nombre_completo": e.usuario.nombre_completo,
                    "email": e.usuario.email
                } if e.usuario else None,
                "tenant": {
                    "id": str(e.tenant.id),
                    "nombre": e.tenant.nombre
                } if e.tenant else None,
                "ip_address": e.ip_address,
                "user_agent": e.user_agent,
                "recurso_afectado": e.recurso_afectado,
                "recurso_id": e.recurso_id,
                "duracion_ms": e.duracion_ms,
                "metadatos": e.metadatos
            }
            for e in eventos
        ]
        
        return ResponseModel(
            status="success",
            message=f"Se encontraron {len(eventos)} eventos de auditoría",
            data={
                "eventos": eventos_data,
                "pagination": {
                    "limite": limite,
                    "offset": offset,
                    "total": total
                },
                "filtros": {
                    "fecha_inicio": fecha_inicio.isoformat() if fecha_inicio else None,
                    "fecha_fin": fecha_fin.isoformat() if fecha_fin else None,
                    "tipo_evento": tipo_evento,
                    "resultado": resultado
                }
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error obteniendo eventos de auditoría")
