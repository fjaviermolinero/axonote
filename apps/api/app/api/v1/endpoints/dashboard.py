# -*- coding: utf-8 -*-
"""
Endpoints REST para dashboard y métricas.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import uuid

from app.core.database import get_db
from app.services.servicio_dashboard import ServicioDashboard
from app.services.servicio_recoleccion_metricas import ServicioRecoleccionMetricas
from app.models.sesion_metrica import SesionMetrica
from app.models.metrica_procesamiento import MetricaProcesamiento
from app.models.metrica_calidad import MetricaCalidad
from app.models.metrica_sistema import MetricaSistema
from app.core.logging import logger

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/resumen")
async def obtener_resumen_dashboard(db: Session = Depends(get_db)):
    """Obtiene el resumen principal del dashboard en tiempo real."""
    try:
        servicio = ServicioDashboard(db)
        resumen = servicio.obtener_resumen_tiempo_real()
        return resumen
    except Exception as e:
        logger.error(f"Error obteniendo resumen dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/rendimiento")
async def obtener_rendimiento_procesamiento(
    horas: int = Query(24, ge=1, le=168, description="Horas hacia atrás (1-168)"),
    tipo_metrica: Optional[str] = Query(None, description="Filtrar por tipo: asr, diarizacion, llm, ocr, tts"),
    db: Session = Depends(get_db)
):
    """Obtiene métricas de rendimiento de procesamiento."""
    try:
        servicio = ServicioDashboard(db)
        rendimiento = servicio.obtener_rendimiento_procesamiento(
            horas=horas, 
            tipo_metrica=tipo_metrica
        )
        return rendimiento
    except Exception as e:
        logger.error(f"Error obteniendo rendimiento: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/uso")
async def obtener_analytics_uso(
    dias: int = Query(7, ge=1, le=90, description="Días hacia atrás (1-90)"),
    db: Session = Depends(get_db)
):
    """Obtiene analytics de uso de la plataforma."""
    try:
        servicio = ServicioDashboard(db)
        analytics = servicio.obtener_analytics_uso(dias=dias)
        return analytics
    except Exception as e:
        logger.error(f"Error obteniendo analytics de uso: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/calidad")
async def obtener_tendencias_calidad(
    dias: int = Query(30, ge=1, le=365, description="Días hacia atrás (1-365)"),
    db: Session = Depends(get_db)
):
    """Obtiene tendencias de calidad del procesamiento."""
    try:
        servicio = ServicioDashboard(db)
        tendencias = servicio.obtener_tendencias_calidad(dias=dias)
        return tendencias
    except Exception as e:
        logger.error(f"Error obteniendo tendencias de calidad: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/sistema")
async def obtener_metricas_sistema(
    limite: int = Query(50, ge=10, le=200, description="Límite de métricas (10-200)"),
    db: Session = Depends(get_db)
):
    """Obtiene métricas de sistema en tiempo real."""
    try:
        servicio = ServicioDashboard(db)
        metricas = servicio.obtener_metricas_sistema_tiempo_real(limite=limite)
        return metricas
    except Exception as e:
        logger.error(f"Error obteniendo métricas de sistema: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/sesiones")
async def obtener_sesiones_recientes(
    limite: int = Query(20, ge=1, le=100, description="Límite de sesiones (1-100)"),
    estado: Optional[str] = Query(None, description="Filtrar por estado"),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo"),
    db: Session = Depends(get_db)
):
    """Obtiene sesiones recientes de métricas."""
    try:
        query = db.query(SesionMetrica).order_by(SesionMetrica.tiempo_inicio.desc())
        
        if estado:
            query = query.filter(SesionMetrica.estado == estado)
        
        if tipo:
            query = query.filter(SesionMetrica.tipo_sesion == tipo)
        
        sesiones = query.limit(limite).all()
        
        return {
            "sesiones": [sesion.obtener_resumen() for sesion in sesiones],
            "total": len(sesiones),
            "filtros": {
                "estado": estado,
                "tipo": tipo,
                "limite": limite
            }
        }
    except Exception as e:
        logger.error(f"Error obteniendo sesiones recientes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/sesiones/{session_id}")
async def obtener_detalle_sesion(
    session_id: str,
    db: Session = Depends(get_db)
):
    """Obtiene el detalle completo de una sesión de métricas."""
    try:
        sesion_uuid = uuid.UUID(session_id)
        sesion = db.query(SesionMetrica).filter(
            SesionMetrica.session_id == sesion_uuid
        ).first()
        
        if not sesion:
            raise HTTPException(status_code=404, detail="Sesión no encontrada")
        
        # Obtener métricas asociadas
        metricas_procesamiento = db.query(MetricaProcesamiento).filter(
            MetricaProcesamiento.id_sesion_metrica == sesion_uuid
        ).all()
        
        metricas_calidad = db.query(MetricaCalidad).filter(
            MetricaCalidad.id_sesion_metrica == sesion_uuid
        ).all()
        
        metricas_sistema = db.query(MetricaSistema).filter(
            MetricaSistema.id_sesion_metrica == sesion_uuid
        ).all()
        
        return {
            "sesion": sesion.obtener_resumen(),
            "metricas_procesamiento": [m.obtener_resumen_rendimiento() for m in metricas_procesamiento],
            "metricas_calidad": [m.obtener_resumen_calidad() for m in metricas_calidad],
            "metricas_sistema": [m.obtener_resumen_metrica() for m in metricas_sistema],
            "contadores": {
                "procesamiento": len(metricas_procesamiento),
                "calidad": len(metricas_calidad),
                "sistema": len(metricas_sistema)
            }
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de sesión inválido")
    except Exception as e:
        logger.error(f"Error obteniendo detalle de sesión: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/alertas")
async def obtener_alertas_sistema(db: Session = Depends(get_db)):
    """Obtiene alertas activas del sistema."""
    try:
        servicio = ServicioDashboard(db)
        alertas = servicio._obtener_alertas_activas()
        
        # Agregar alertas de sesiones con problemas
        ahora = datetime.now()
        ultima_hora = ahora - timedelta(hours=1)
        
        sesiones_con_alertas = db.query(SesionMetrica).filter(
            SesionMetrica.tiempo_inicio >= ultima_hora,
            (SesionMetrica.contador_alertas_criticas > 0) | 
            (SesionMetrica.contador_alertas_warning > 0)
        ).all()
        
        alertas_sesiones = []
        for sesion in sesiones_con_alertas:
            if sesion.contador_alertas_criticas > 0:
                alertas_sesiones.append({
                    "tipo": "sesion_critica",
                    "severidad": "critica",
                    "mensaje": f"Sesión {sesion.nombre_sesion} tiene {sesion.contador_alertas_criticas} alertas críticas",
                    "sesion_id": str(sesion.session_id),
                    "timestamp": sesion.tiempo_inicio.isoformat()
                })
            
            if sesion.contador_alertas_warning > 0:
                alertas_sesiones.append({
                    "tipo": "sesion_warning",
                    "severidad": "warning",
                    "mensaje": f"Sesión {sesion.nombre_sesion} tiene {sesion.contador_alertas_warning} warnings",
                    "sesion_id": str(sesion.session_id),
                    "timestamp": sesion.tiempo_inicio.isoformat()
                })
        
        return {
            "alertas_sistema": alertas,
            "alertas_sesiones": alertas_sesiones,
            "total_alertas": len(alertas) + len(alertas_sesiones),
            "timestamp": ahora.isoformat()
        }
    except Exception as e:
        logger.error(f"Error obteniendo alertas: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


# Endpoints para gestión de sesiones de métricas
@router.post("/sesiones/iniciar")
async def iniciar_sesion_metricas(
    nombre_sesion: str,
    tipo_sesion: str = "procesamiento_clase",
    id_sesion_clase: Optional[str] = None,
    id_profesor: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Inicia una nueva sesión de métricas."""
    try:
        servicio = ServicioRecoleccionMetricas(db)
        
        # Convertir IDs si se proporcionan
        id_sesion_clase_uuid = uuid.UUID(id_sesion_clase) if id_sesion_clase else None
        id_profesor_uuid = uuid.UUID(id_profesor) if id_profesor else None
        
        session_id = servicio.iniciar_sesion_metrica(
            nombre_sesion=nombre_sesion,
            tipo_sesion=tipo_sesion,
            id_sesion_clase=id_sesion_clase_uuid,
            id_profesor=id_profesor_uuid
        )
        
        return {
            "session_id": str(session_id),
            "estado": "iniciada",
            "mensaje": f"Sesión '{nombre_sesion}' iniciada exitosamente"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"ID inválido: {str(e)}")
    except Exception as e:
        logger.error(f"Error iniciando sesión de métricas: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.post("/sesiones/{session_id}/completar")
async def completar_sesion_metricas(
    session_id: str,
    estado: str = "completada",
    db: Session = Depends(get_db)
):
    """Completa una sesión de métricas."""
    try:
        servicio = ServicioRecoleccionMetricas(db)
        session_uuid = uuid.UUID(session_id)
        
        if estado not in ["completada", "fallida", "cancelada"]:
            raise HTTPException(
                status_code=400, 
                detail="Estado inválido. Debe ser: completada, fallida, cancelada"
            )
        
        servicio.completar_sesion(session_uuid, estado)
        
        return {
            "session_id": session_id,
            "estado": estado,
            "mensaje": f"Sesión completada con estado: {estado}"
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de sesión inválido")
    except Exception as e:
        logger.error(f"Error completando sesión de métricas: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.post("/sistema/snapshot")
async def capturar_snapshot_sistema(
    componente: str = "sistema_general",
    session_id: Optional[str] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """Captura un snapshot completo de métricas del sistema."""
    try:
        servicio = ServicioRecoleccionMetricas(db)
        session_uuid = uuid.UUID(session_id) if session_id else None
        
        # Ejecutar captura en background para no bloquear
        def capturar_snapshot():
            try:
                metricas_ids = servicio.capturar_snapshot_sistema(
                    componente=componente,
                    id_sesion=session_uuid
                )
                logger.info(f"Snapshot capturado: {len(metricas_ids)} métricas")
            except Exception as e:
                logger.error(f"Error en background snapshot: {str(e)}")
        
        background_tasks.add_task(capturar_snapshot)
        
        return {
            "mensaje": "Captura de snapshot iniciada",
            "componente": componente,
            "session_id": session_id,
            "estado": "en_progreso"
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de sesión inválido")
    except Exception as e:
        logger.error(f"Error iniciando snapshot: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/exportar/csv")
async def exportar_metricas_csv(
    tipo: str = Query("todas", description="Tipo de métricas: todas, procesamiento, calidad, sistema"),
    dias: int = Query(7, ge=1, le=90, description="Días hacia atrás"),
    db: Session = Depends(get_db)
):
    """Exporta métricas en formato CSV."""
    try:
        # TODO: Implementar exportación CSV
        # Por ahora retorna mensaje de no implementado
        return {
            "mensaje": "Exportación CSV no implementada aún",
            "tipo": tipo,
            "dias": dias,
            "estado": "pendiente_implementacion"
        }
    except Exception as e:
        logger.error(f"Error exportando CSV: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@router.get("/stats")
async def obtener_estadisticas_generales(db: Session = Depends(get_db)):
    """Obtiene estadísticas generales del sistema."""
    try:
        # Conteos totales
        total_sesiones = db.query(SesionMetrica).count()
        total_metricas_procesamiento = db.query(MetricaProcesamiento).count()
        total_metricas_calidad = db.query(MetricaCalidad).count()
        total_metricas_sistema = db.query(MetricaSistema).count()
        
        # Sesiones por estado
        sesiones_por_estado = db.query(
            SesionMetrica.estado,
            db.func.count(SesionMetrica.session_id)
        ).group_by(SesionMetrica.estado).all()
        
        # Primera y última sesión
        primera_sesion = db.query(SesionMetrica).order_by(
            SesionMetrica.tiempo_inicio.asc()
        ).first()
        
        ultima_sesion = db.query(SesionMetrica).order_by(
            SesionMetrica.tiempo_inicio.desc()
        ).first()
        
        return {
            "totales": {
                "sesiones": total_sesiones,
                "metricas_procesamiento": total_metricas_procesamiento,
                "metricas_calidad": total_metricas_calidad,
                "metricas_sistema": total_metricas_sistema,
                "metricas_total": total_metricas_procesamiento + total_metricas_calidad + total_metricas_sistema
            },
            "sesiones_por_estado": {
                estado: cantidad for estado, cantidad in sesiones_por_estado
            },
            "periodo_datos": {
                "primera_sesion": primera_sesion.tiempo_inicio.isoformat() if primera_sesion else None,
                "ultima_sesion": ultima_sesion.tiempo_inicio.isoformat() if ultima_sesion else None
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas generales: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")
