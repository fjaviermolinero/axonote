# -*- coding: utf-8 -*-
"""
Servicio para generar datos del dashboard y analytics.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, desc, and_
from sqlalchemy.orm import Session

from app.models.sesion_metrica import SesionMetrica
from app.models.metrica_procesamiento import MetricaProcesamiento
from app.models.metrica_calidad import MetricaCalidad
from app.models.metrica_sistema import MetricaSistema
from app.core.logging import logger


class ServicioDashboard:
    """Servicio para generar datos del dashboard y analytics."""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        logger.info("ServicioDashboard inicializado")
    
    def obtener_resumen_tiempo_real(self) -> Dict:
        """Obtiene overview en tiempo real del sistema."""
        try:
            ahora = datetime.now(timezone.utc)
            ultima_hora = ahora - timedelta(hours=1)
            ultimas_24h = ahora - timedelta(hours=24)
            
            # Sesiones activas
            sesiones_activas = self.db.query(SesionMetrica).filter(
                SesionMetrica.estado == "activa"
            ).count()
            
            # Métricas últimas 24h
            metricas_recientes = self.db.query(MetricaProcesamiento).filter(
                MetricaProcesamiento.tiempo_inicio >= ultimas_24h
            ).count()
            
            # Calidad promedio reciente
            calidad_promedio = self.db.query(
                func.avg(MetricaCalidad.confianza_promedio)
            ).filter(
                MetricaCalidad.created_at >= ultimas_24h
            ).scalar() or 0.0
            
            # Estado del sistema
            estado_sistema = self._calcular_estado_sistema()
            
            # Métricas de GPU/CPU más recientes
            metricas_sistema_recientes = self._obtener_metricas_sistema_recientes()
            
            resumen = {
                "timestamp": ahora.isoformat(),
                "sesiones_activas": sesiones_activas,
                "metricas_24h": metricas_recientes,
                "calidad_promedio_24h": round(calidad_promedio, 3),
                "estado_sistema": estado_sistema,
                "metricas_sistema": metricas_sistema_recientes,
                "alertas_activas": self._obtener_alertas_activas()
            }
            
            logger.debug("Resumen en tiempo real generado exitosamente")
            return resumen
            
        except Exception as e:
            logger.error(f"Error generando resumen en tiempo real: {str(e)}")
            raise
    
    def obtener_rendimiento_procesamiento(
        self, 
        horas: int = 24,
        tipo_metrica: Optional[str] = None
    ) -> Dict:
        """Obtiene métricas de rendimiento de procesamiento."""
        try:
            desde = datetime.now(timezone.utc) - timedelta(hours=horas)
            
            query = self.db.query(MetricaProcesamiento).filter(
                MetricaProcesamiento.tiempo_inicio >= desde
            )
            
            if tipo_metrica:
                query = query.filter(MetricaProcesamiento.tipo_metrica == tipo_metrica)
            
            metricas = query.all()
            
            if not metricas:
                return {
                    "error": "No hay datos disponibles",
                    "periodo_horas": horas,
                    "tipo_metrica": tipo_metrica
                }
            
            # Agregar estadísticas
            duraciones = [m.duracion_ms for m in metricas]
            puntuaciones_calidad = [m.puntuacion_calidad for m in metricas if m.puntuacion_calidad is not None]
            puntuaciones_confianza = [m.puntuacion_confianza for m in metricas if m.puntuacion_confianza is not None]
            
            # Agrupar por tipo de procesamiento
            por_tipo = {}
            for metrica in metricas:
                tipo = metrica.tipo_metrica
                if tipo not in por_tipo:
                    por_tipo[tipo] = []
                por_tipo[tipo].append(metrica)
            
            estadisticas_por_tipo = {}
            for tipo, metricas_tipo in por_tipo.items():
                duraciones_tipo = [m.duracion_ms for m in metricas_tipo]
                estadisticas_por_tipo[tipo] = {
                    "cantidad": len(metricas_tipo),
                    "duracion_promedio_ms": round(sum(duraciones_tipo) / len(duraciones_tipo), 2),
                    "duracion_min_ms": min(duraciones_tipo),
                    "duracion_max_ms": max(duraciones_tipo),
                    "tasa_exito": self._calcular_tasa_exito(metricas_tipo)
                }
            
            resultado = {
                "periodo_horas": horas,
                "tipo_metrica": tipo_metrica,
                "total_operaciones": len(metricas),
                "duracion_promedio_ms": round(sum(duraciones) / len(duraciones), 2),
                "duracion_min_ms": min(duraciones),
                "duracion_max_ms": max(duraciones),
                "calidad_promedio": round(sum(puntuaciones_calidad) / len(puntuaciones_calidad), 3) if puntuaciones_calidad else None,
                "confianza_promedio": round(sum(puntuaciones_confianza) / len(puntuaciones_confianza), 3) if puntuaciones_confianza else None,
                "tasa_exito_general": self._calcular_tasa_exito(metricas),
                "estadisticas_por_tipo": estadisticas_por_tipo
            }
            
            logger.debug(f"Métricas de rendimiento generadas para {horas}h")
            return resultado
            
        except Exception as e:
            logger.error(f"Error obteniendo rendimiento de procesamiento: {str(e)}")
            raise
    
    def obtener_analytics_uso(self, dias: int = 7) -> Dict:
        """Obtiene analytics de uso de la plataforma."""
        try:
            desde = datetime.now(timezone.utc) - timedelta(days=dias)
            
            # Sesiones por día
            sesiones_diarias = self.db.query(
                func.date(SesionMetrica.tiempo_inicio).label("fecha"),
                func.count(SesionMetrica.session_id).label("cantidad")
            ).filter(
                SesionMetrica.tiempo_inicio >= desde
            ).group_by(
                func.date(SesionMetrica.tiempo_inicio)
            ).order_by("fecha").all()
            
            # Tipos de sesión más comunes
            tipos_sesion = self.db.query(
                SesionMetrica.tipo_sesion,
                func.count(SesionMetrica.session_id).label("cantidad")
            ).filter(
                SesionMetrica.tiempo_inicio >= desde
            ).group_by(SesionMetrica.tipo_sesion).all()
            
            # Duración promedio por tipo
            duraciones_promedio = self.db.query(
                SesionMetrica.tipo_sesion,
                func.avg(SesionMetrica.duracion_segundos).label("duracion_promedio")
            ).filter(
                SesionMetrica.tiempo_inicio >= desde,
                SesionMetrica.duracion_segundos.isnot(None)
            ).group_by(SesionMetrica.tipo_sesion).all()
            
            # Estadísticas de estados
            estados_sesiones = self.db.query(
                SesionMetrica.estado,
                func.count(SesionMetrica.session_id).label("cantidad")
            ).filter(
                SesionMetrica.tiempo_inicio >= desde
            ).group_by(SesionMetrica.estado).all()
            
            resultado = {
                "periodo_dias": dias,
                "sesiones_diarias": [
                    {"fecha": str(row.fecha), "cantidad": row.cantidad} 
                    for row in sesiones_diarias
                ],
                "tipos_sesion": [
                    {"tipo": row.tipo_sesion, "cantidad": row.cantidad} 
                    for row in tipos_sesion
                ],
                "duraciones_promedio": [
                    {
                        "tipo": row.tipo_sesion, 
                        "duracion_promedio_minutos": round(row.duracion_promedio / 60, 2) if row.duracion_promedio else 0
                    }
                    for row in duraciones_promedio
                ],
                "estados_sesiones": [
                    {"estado": row.estado, "cantidad": row.cantidad}
                    for row in estados_sesiones
                ]
            }
            
            logger.debug(f"Analytics de uso generados para {dias} días")
            return resultado
            
        except Exception as e:
            logger.error(f"Error obteniendo analytics de uso: {str(e)}")
            raise
    
    def obtener_tendencias_calidad(self, dias: int = 30) -> Dict:
        """Obtiene tendencias de calidad a lo largo del tiempo."""
        try:
            desde = datetime.now(timezone.utc) - timedelta(days=dias)
            
            # Tendencia WER y confianza por día
            tendencia_calidad = self.db.query(
                func.date(MetricaCalidad.created_at).label("fecha"),
                func.avg(MetricaCalidad.puntuacion_wer).label("wer_promedio"),
                func.avg(MetricaCalidad.confianza_promedio).label("confianza_promedio"),
                func.avg(MetricaCalidad.precision_terminos_medicos).label("precision_terminos"),
                func.count(MetricaCalidad.metrica_id).label("cantidad_metricas")
            ).filter(
                MetricaCalidad.created_at >= desde
            ).group_by(
                func.date(MetricaCalidad.created_at)
            ).order_by("fecha").all()
            
            # Métricas por tipo de procesamiento
            calidad_por_tipo = self.db.query(
                MetricaProcesamiento.tipo_metrica,
                func.avg(MetricaProcesamiento.puntuacion_calidad).label("calidad_promedio"),
                func.avg(MetricaProcesamiento.puntuacion_confianza).label("confianza_promedio"),
                func.count(MetricaProcesamiento.metrica_id).label("cantidad")
            ).filter(
                MetricaProcesamiento.tiempo_inicio >= desde
            ).group_by(MetricaProcesamiento.tipo_metrica).all()
            
            # Alertas de calidad por día
            alertas_diarias = self.db.query(
                func.date(SesionMetrica.tiempo_inicio).label("fecha"),
                func.sum(SesionMetrica.contador_alertas_criticas).label("alertas_criticas"),
                func.sum(SesionMetrica.contador_alertas_warning).label("alertas_warning")
            ).filter(
                SesionMetrica.tiempo_inicio >= desde
            ).group_by(
                func.date(SesionMetrica.tiempo_inicio)
            ).order_by("fecha").all()
            
            resultado = {
                "periodo_dias": dias,
                "tendencia_calidad": [
                    {
                        "fecha": str(row.fecha),
                        "wer_promedio": round(row.wer_promedio, 4) if row.wer_promedio else None,
                        "confianza_promedio": round(row.confianza_promedio, 3) if row.confianza_promedio else None,
                        "precision_terminos": round(row.precision_terminos, 3) if row.precision_terminos else None,
                        "cantidad_metricas": row.cantidad_metricas
                    }
                    for row in tendencia_calidad
                ],
                "calidad_por_tipo": [
                    {
                        "tipo": row.tipo_metrica,
                        "calidad_promedio": round(row.calidad_promedio, 3) if row.calidad_promedio else None,
                        "confianza_promedio": round(row.confianza_promedio, 3) if row.confianza_promedio else None,
                        "cantidad": row.cantidad
                    }
                    for row in calidad_por_tipo
                ],
                "alertas_diarias": [
                    {
                        "fecha": str(row.fecha),
                        "alertas_criticas": row.alertas_criticas or 0,
                        "alertas_warning": row.alertas_warning or 0
                    }
                    for row in alertas_diarias
                ]
            }
            
            logger.debug(f"Tendencias de calidad generadas para {dias} días")
            return resultado
            
        except Exception as e:
            logger.error(f"Error obteniendo tendencias de calidad: {str(e)}")
            raise
    
    def obtener_metricas_sistema_tiempo_real(self, limite: int = 50) -> Dict:
        """Obtiene las métricas de sistema más recientes."""
        try:
            # Métricas recientes por categoría
            metricas_recientes = self.db.query(MetricaSistema).filter(
                MetricaSistema.timestamp >= datetime.now(timezone.utc) - timedelta(hours=1)
            ).order_by(desc(MetricaSistema.timestamp)).limit(limite).all()
            
            # Agrupar por categoría y nombre
            por_categoria = {}
            for metrica in metricas_recientes:
                categoria = metrica.categoria_metrica
                if categoria not in por_categoria:
                    por_categoria[categoria] = {}
                
                nombre = metrica.nombre_metrica
                if nombre not in por_categoria[categoria]:
                    por_categoria[categoria][nombre] = []
                
                por_categoria[categoria][nombre].append(metrica.obtener_resumen_metrica())
            
            # Obtener últimos valores por métrica clave
            metricas_clave = ["cpu_usage", "memory_usage", "gpu_usage", "gpu_memory", "gpu_temperature"]
            ultimos_valores = {}
            
            for nombre_metrica in metricas_clave:
                ultima_metrica = self.db.query(MetricaSistema).filter(
                    MetricaSistema.nombre_metrica == nombre_metrica
                ).order_by(desc(MetricaSistema.timestamp)).first()
                
                if ultima_metrica:
                    ultimos_valores[nombre_metrica] = ultima_metrica.obtener_resumen_metrica()
            
            resultado = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metricas_por_categoria": por_categoria,
                "ultimos_valores": ultimos_valores,
                "cantidad_metricas": len(metricas_recientes)
            }
            
            logger.debug("Métricas de sistema en tiempo real obtenidas")
            return resultado
            
        except Exception as e:
            logger.error(f"Error obteniendo métricas de sistema en tiempo real: {str(e)}")
            raise
    
    def _calcular_estado_sistema(self) -> str:
        """Calcula el estado general de salud del sistema."""
        try:
            # Verificar métricas críticas recientes
            ahora = datetime.now(timezone.utc)
            ultima_hora = ahora - timedelta(hours=1)
            
            # Contar alertas críticas recientes
            alertas_criticas = self.db.query(
                func.sum(SesionMetrica.contador_alertas_criticas)
            ).filter(
                SesionMetrica.tiempo_inicio >= ultima_hora
            ).scalar() or 0
            
            # Verificar métricas de sistema críticas
            metricas_criticas = self.db.query(MetricaSistema).filter(
                and_(
                    MetricaSistema.timestamp >= ultima_hora,
                    MetricaSistema.nombre_metrica.in_(["cpu_usage", "memory_usage", "gpu_usage"])
                )
            ).all()
            
            sistema_critico = False
            for metrica in metricas_criticas:
                if metrica.esta_en_umbral_critico:
                    sistema_critico = True
                    break
            
            if alertas_criticas > 5 or sistema_critico:
                return "critico"
            elif alertas_criticas > 0:
                return "warning"
            else:
                return "saludable"
                
        except Exception as e:
            logger.warning(f"Error calculando estado del sistema: {str(e)}")
            return "desconocido"
    
    def _obtener_metricas_sistema_recientes(self) -> Dict:
        """Obtiene las métricas de sistema más recientes."""
        try:
            metricas_clave = ["cpu_usage", "memory_usage", "gpu_usage", "gpu_memory"]
            resultado = {}
            
            for nombre_metrica in metricas_clave:
                ultima_metrica = self.db.query(MetricaSistema).filter(
                    MetricaSistema.nombre_metrica == nombre_metrica
                ).order_by(desc(MetricaSistema.timestamp)).first()
                
                if ultima_metrica:
                    resultado[nombre_metrica] = {
                        "valor": ultima_metrica.valor,
                        "unidad": ultima_metrica.unidad,
                        "estado": ultima_metrica.obtener_estado_salud(),
                        "timestamp": ultima_metrica.timestamp.isoformat()
                    }
            
            return resultado
            
        except Exception as e:
            logger.warning(f"Error obteniendo métricas de sistema recientes: {str(e)}")
            return {}
    
    def _obtener_alertas_activas(self) -> List[Dict]:
        """Obtiene alertas activas del sistema."""
        try:
            # Por ahora retorna lista vacía
            # TODO: Implementar sistema de alertas persistentes
            return []
            
        except Exception as e:
            logger.warning(f"Error obteniendo alertas activas: {str(e)}")
            return []
    
    def _calcular_tasa_exito(self, metricas: List[MetricaProcesamiento]) -> float:
        """Calcula la tasa de éxito basada en métricas."""
        if not metricas:
            return 0.0
        
        exitosos = sum(1 for m in metricas if m.fue_exitoso)
        return round(exitosos / len(metricas), 3)
