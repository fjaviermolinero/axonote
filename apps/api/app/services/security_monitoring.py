"""
Servicio de monitoreo de seguridad y alertas para Axonote.
Detecta anomalías, patrones sospechosos y genera alertas en tiempo real.
"""

import time
import json
import redis
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Set, Tuple
from dataclasses import dataclass
from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from app.models.usuario import Usuario, LogAuditoria, TipoEventoAuditoria, NivelSeveridad
from app.services.auditoria_service import ServicioAuditoria
from app.core.config import settings


class TipoAlerta(str, Enum):
    """Tipos de alertas de seguridad."""
    INTENTO_FUERZA_BRUTA = "intento_fuerza_bruta"
    ACCESO_SOSPECHOSO = "acceso_sospechoso"
    UBICACION_ANOMALA = "ubicacion_anomala"
    PATRON_ATAQUE = "patron_ataque"
    VOLUMEN_INUSUAL = "volumen_inusual"
    ERROR_SISTEMA_CRITICO = "error_sistema_critico"
    DATOS_COMPROMETIDOS = "datos_comprometidos"
    CONFIGURACION_MODIFICADA = "configuracion_modificada"
    USUARIO_PRIVILEGIADO = "usuario_privilegiado"
    RATE_LIMIT_EXCEDIDO = "rate_limit_excedido"


class SeveridadAlerta(str, Enum):
    """Severidad de las alertas."""
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "critica"


@dataclass
class Alerta:
    """Estructura de una alerta de seguridad."""
    id: str
    tipo: TipoAlerta
    severidad: SeveridadAlerta
    titulo: str
    descripcion: str
    timestamp: datetime
    usuario_id: Optional[str] = None
    ip_address: Optional[str] = None
    datos_adicionales: Optional[Dict[str, Any]] = None
    acciones_recomendadas: Optional[List[str]] = None
    estado: str = "nueva"  # nueva, investigando, resuelta, falso_positivo


class ServicioMonitoreoSeguridad:
    """
    Servicio completo de monitoreo de seguridad.
    Detecta amenazas, analiza patrones y genera alertas automáticas.
    """
    
    def __init__(self, db: Session, redis_client: redis.Redis, servicio_auditoria: ServicioAuditoria):
        self.db = db
        self.redis = redis_client
        self.auditoria = servicio_auditoria
        
        # Configuración de detección
        self.config_deteccion = {
            "fuerza_bruta": {
                "intentos_maximos": 5,
                "ventana_minutos": 15,
                "bloqueo_minutos": 30
            },
            "ubicacion_anomala": {
                "distancia_maxima_km": 1000,
                "tiempo_minimo_horas": 2
            },
            "volumen_inusual": {
                "multiplicador_normal": 3,
                "ventana_analisis_horas": 24
            },
            "patron_ataque": {
                "patrones_sql": [
                    r"UNION\s+SELECT",
                    r"DROP\s+TABLE",
                    r"INSERT\s+INTO.*VALUES",
                    r"UPDATE.*SET.*WHERE"
                ],
                "patrones_xss": [
                    r"<script[^>]*>",
                    r"javascript:",
                    r"on\w+\s*="
                ]
            }
        }
        
        # Cache de alertas recientes
        self.cache_alertas = {}
        self.alertas_activas = set()
        
        # Configuración de notificaciones
        self.canales_notificacion = {
            SeveridadAlerta.CRITICA: ["email", "slack", "sms"],
            SeveridadAlerta.ALTA: ["email", "slack"],
            SeveridadAlerta.MEDIA: ["email"],
            SeveridadAlerta.BAJA: ["log"]
        }
    
    async def iniciar_monitoreo(self):
        """Inicia el monitoreo continuo de seguridad."""
        
        # Crear tareas de monitoreo en background
        tareas = [
            asyncio.create_task(self._monitorear_intentos_login()),
            asyncio.create_task(self._monitorear_patrones_acceso()),
            asyncio.create_task(self._monitorear_anomalias_ubicacion()),
            asyncio.create_task(self._monitorear_volumen_requests()),
            asyncio.create_task(self._monitorear_errores_sistema()),
            asyncio.create_task(self._limpiar_alertas_antiguas())
        ]
        
        # Ejecutar tareas concurrentemente
        await asyncio.gather(*tareas, return_exceptions=True)
    
    async def analizar_evento_tiempo_real(
        self,
        tipo_evento: TipoEventoAuditoria,
        usuario_id: Optional[str],
        ip_address: Optional[str],
        datos_evento: Dict[str, Any]
    ) -> List[Alerta]:
        """
        Analiza un evento en tiempo real y genera alertas si es necesario.
        
        Args:
            tipo_evento: Tipo de evento de auditoría
            usuario_id: ID del usuario involucrado
            ip_address: Dirección IP del evento
            datos_evento: Datos adicionales del evento
            
        Returns:
            Lista de alertas generadas
        """
        
        alertas_generadas = []
        
        # Análisis específico por tipo de evento
        if tipo_evento == TipoEventoAuditoria.LOGIN_FALLIDO:
            alertas = await self._analizar_login_fallido(usuario_id, ip_address, datos_evento)
            alertas_generadas.extend(alertas)
        
        elif tipo_evento == TipoEventoAuditoria.LOGIN_EXITOSO:
            alertas = await self._analizar_login_exitoso(usuario_id, ip_address, datos_evento)
            alertas_generadas.extend(alertas)
        
        elif tipo_evento == TipoEventoAuditoria.INTENTO_ACCESO_NO_AUTORIZADO:
            alertas = await self._analizar_acceso_no_autorizado(usuario_id, ip_address, datos_evento)
            alertas_generadas.extend(alertas)
        
        elif tipo_evento == TipoEventoAuditoria.RATE_LIMIT_EXCEDIDO:
            alertas = await self._analizar_rate_limit_excedido(ip_address, datos_evento)
            alertas_generadas.extend(alertas)
        
        elif tipo_evento == TipoEventoAuditoria.ERROR_SISTEMA:
            alertas = await self._analizar_error_sistema(datos_evento)
            alertas_generadas.extend(alertas)
        
        # Procesar alertas generadas
        for alerta in alertas_generadas:
            await self._procesar_alerta(alerta)
        
        return alertas_generadas
    
    async def obtener_dashboard_seguridad(self) -> Dict[str, Any]:
        """
        Obtiene datos para el dashboard de seguridad.
        
        Returns:
            Dict con métricas y alertas de seguridad
        """
        
        ahora = datetime.utcnow()
        hace_24h = ahora - timedelta(hours=24)
        hace_7d = ahora - timedelta(days=7)
        
        # Estadísticas de alertas
        alertas_24h = await self._contar_alertas_periodo(hace_24h, ahora)
        alertas_7d = await self._contar_alertas_periodo(hace_7d, ahora)
        
        # Alertas activas por severidad
        alertas_activas = await self._obtener_alertas_activas()
        
        # Eventos de seguridad recientes
        eventos_recientes = await self._obtener_eventos_seguridad_recientes(limite=20)
        
        # Métricas de autenticación
        metricas_auth = await self._obtener_metricas_autenticacion(hace_24h)
        
        # Top IPs sospechosas
        ips_sospechosas = await self._obtener_ips_sospechosas(hace_24h)
        
        # Estado del sistema
        estado_sistema = await self._obtener_estado_sistema()
        
        return {
            "timestamp": ahora.isoformat(),
            "resumen": {
                "alertas_24h": alertas_24h,
                "alertas_7d": alertas_7d,
                "alertas_activas": len(alertas_activas),
                "estado_general": self._calcular_estado_general(alertas_activas)
            },
            "alertas_por_severidad": {
                "critica": len([a for a in alertas_activas if a.severidad == SeveridadAlerta.CRITICA]),
                "alta": len([a for a in alertas_activas if a.severidad == SeveridadAlerta.ALTA]),
                "media": len([a for a in alertas_activas if a.severidad == SeveridadAlerta.MEDIA]),
                "baja": len([a for a in alertas_activas if a.severidad == SeveridadAlerta.BAJA])
            },
            "eventos_recientes": eventos_recientes,
            "metricas_autenticacion": metricas_auth,
            "ips_sospechosas": ips_sospechosas,
            "estado_sistema": estado_sistema,
            "alertas_activas": [self._alerta_to_dict(a) for a in alertas_activas[:10]]  # Top 10
        }
    
    async def investigar_alerta(
        self,
        alerta_id: str,
        investigador_id: str,
        notas: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Marca una alerta como en investigación y recopila contexto adicional.
        
        Args:
            alerta_id: ID de la alerta
            investigador_id: ID del usuario investigador
            notas: Notas de la investigación
            
        Returns:
            Dict con contexto de investigación
        """
        
        # Obtener alerta
        alerta = await self._obtener_alerta(alerta_id)
        if not alerta:
            raise ValueError(f"Alerta {alerta_id} no encontrada")
        
        # Marcar como en investigación
        alerta.estado = "investigando"
        await self._actualizar_alerta(alerta)
        
        # Recopilar contexto adicional
        contexto = await self._recopilar_contexto_investigacion(alerta)
        
        # Registrar inicio de investigación
        await self.auditoria.log_evento(
            tipo_evento=TipoEventoAuditoria.DETECCION_ANOMALIA,
            descripcion=f"Investigación iniciada para alerta {alerta_id}",
            usuario_id=investigador_id,
            datos_evento={
                "alerta_id": alerta_id,
                "tipo_alerta": alerta.tipo.value,
                "severidad": alerta.severidad.value,
                "notas": notas
            }
        )
        
        return {
            "alerta": self._alerta_to_dict(alerta),
            "contexto": contexto,
            "investigador": investigador_id,
            "fecha_inicio": datetime.utcnow().isoformat(),
            "notas": notas
        }
    
    async def resolver_alerta(
        self,
        alerta_id: str,
        resolucion: str,
        investigador_id: str,
        es_falso_positivo: bool = False,
        acciones_tomadas: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Resuelve una alerta de seguridad.
        
        Args:
            alerta_id: ID de la alerta
            resolucion: Descripción de la resolución
            investigador_id: ID del investigador
            es_falso_positivo: Si es un falso positivo
            acciones_tomadas: Lista de acciones tomadas
            
        Returns:
            Dict con resultado de la resolución
        """
        
        alerta = await self._obtener_alerta(alerta_id)
        if not alerta:
            raise ValueError(f"Alerta {alerta_id} no encontrada")
        
        # Actualizar estado
        alerta.estado = "falso_positivo" if es_falso_positivo else "resuelta"
        await self._actualizar_alerta(alerta)
        
        # Registrar resolución
        await self.auditoria.log_evento(
            tipo_evento=TipoEventoAuditoria.DETECCION_ANOMALIA,
            descripcion=f"Alerta {alerta_id} {'marcada como falso positivo' if es_falso_positivo else 'resuelta'}",
            usuario_id=investigador_id,
            datos_evento={
                "alerta_id": alerta_id,
                "resolucion": resolucion,
                "es_falso_positivo": es_falso_positivo,
                "acciones_tomadas": acciones_tomadas or []
            }
        )
        
        # Aprender de falsos positivos para mejorar detección
        if es_falso_positivo:
            await self._aprender_falso_positivo(alerta)
        
        return {
            "alerta_id": alerta_id,
            "estado": alerta.estado,
            "resolucion": resolucion,
            "investigador": investigador_id,
            "fecha_resolucion": datetime.utcnow().isoformat(),
            "acciones_tomadas": acciones_tomadas or []
        }
    
    # Métodos de análisis específicos
    
    async def _analizar_login_fallido(
        self,
        usuario_id: Optional[str],
        ip_address: Optional[str],
        datos_evento: Dict[str, Any]
    ) -> List[Alerta]:
        """Analiza intentos de login fallidos para detectar fuerza bruta."""
        
        alertas = []
        
        if not ip_address:
            return alertas
        
        # Contar intentos fallidos recientes desde esta IP
        ventana = timedelta(minutes=self.config_deteccion["fuerza_bruta"]["ventana_minutos"])
        desde = datetime.utcnow() - ventana
        
        intentos_ip = self.db.query(LogAuditoria).filter(
            and_(
                LogAuditoria.tipo_evento == TipoEventoAuditoria.LOGIN_FALLIDO,
                LogAuditoria.ip_address == ip_address,
                LogAuditoria.timestamp >= desde
            )
        ).count()
        
        max_intentos = self.config_deteccion["fuerza_bruta"]["intentos_maximos"]
        
        if intentos_ip >= max_intentos:
            # Generar alerta de fuerza bruta
            alerta = Alerta(
                id=f"brute_force_{ip_address}_{int(time.time())}",
                tipo=TipoAlerta.INTENTO_FUERZA_BRUTA,
                severidad=SeveridadAlerta.ALTA,
                titulo=f"Intento de fuerza bruta detectado desde {ip_address}",
                descripcion=f"Se detectaron {intentos_ip} intentos de login fallidos desde la IP {ip_address} en los últimos {self.config_deteccion['fuerza_bruta']['ventana_minutos']} minutos",
                timestamp=datetime.utcnow(),
                usuario_id=usuario_id,
                ip_address=ip_address,
                datos_adicionales={
                    "intentos_fallidos": intentos_ip,
                    "ventana_minutos": self.config_deteccion["fuerza_bruta"]["ventana_minutos"],
                    "email_objetivo": datos_evento.get("email")
                },
                acciones_recomendadas=[
                    f"Bloquear IP {ip_address} temporalmente",
                    "Investigar origen de la IP",
                    "Notificar al usuario si se identificó la cuenta objetivo",
                    "Revisar logs de firewall"
                ]
            )
            alertas.append(alerta)
        
        return alertas
    
    async def _analizar_login_exitoso(
        self,
        usuario_id: Optional[str],
        ip_address: Optional[str],
        datos_evento: Dict[str, Any]
    ) -> List[Alerta]:
        """Analiza logins exitosos para detectar anomalías."""
        
        alertas = []
        
        if not usuario_id or not ip_address:
            return alertas
        
        # Obtener ubicación histórica del usuario
        ubicaciones_historicas = await self._obtener_ubicaciones_usuario(usuario_id)
        
        # Verificar si es una ubicación nueva/sospechosa
        if await self._es_ubicacion_anomala(ip_address, ubicaciones_historicas):
            alerta = Alerta(
                id=f"location_anomaly_{usuario_id}_{int(time.time())}",
                tipo=TipoAlerta.UBICACION_ANOMALA,
                severidad=SeveridadAlerta.MEDIA,
                titulo=f"Acceso desde ubicación inusual",
                descripcion=f"Usuario accedió desde una ubicación geográfica inusual: {ip_address}",
                timestamp=datetime.utcnow(),
                usuario_id=usuario_id,
                ip_address=ip_address,
                datos_adicionales={
                    "ubicacion_estimada": await self._obtener_ubicacion_ip(ip_address),
                    "ubicaciones_historicas": ubicaciones_historicas[:5]  # Últimas 5
                },
                acciones_recomendadas=[
                    "Verificar con el usuario si el acceso fue legítimo",
                    "Revisar actividad reciente de la cuenta",
                    "Considerar habilitar MFA si no está activo"
                ]
            )
            alertas.append(alerta)
        
        # Verificar horario inusual
        if await self._es_horario_inusual(usuario_id, datetime.utcnow()):
            alerta = Alerta(
                id=f"unusual_time_{usuario_id}_{int(time.time())}",
                tipo=TipoAlerta.ACCESO_SOSPECHOSO,
                severidad=SeveridadAlerta.BAJA,
                titulo=f"Acceso en horario inusual",
                descripcion=f"Usuario accedió en un horario fuera de su patrón normal",
                timestamp=datetime.utcnow(),
                usuario_id=usuario_id,
                ip_address=ip_address,
                datos_adicionales={
                    "hora_acceso": datetime.utcnow().strftime("%H:%M"),
                    "patron_horario": await self._obtener_patron_horario_usuario(usuario_id)
                },
                acciones_recomendadas=[
                    "Monitorear actividad de la sesión",
                    "Verificar si hay actividad sospechosa posterior"
                ]
            )
            alertas.append(alerta)
        
        return alertas
    
    async def _analizar_acceso_no_autorizado(
        self,
        usuario_id: Optional[str],
        ip_address: Optional[str],
        datos_evento: Dict[str, Any]
    ) -> List[Alerta]:
        """Analiza intentos de acceso no autorizado."""
        
        alerta = Alerta(
            id=f"unauthorized_{ip_address}_{int(time.time())}",
            tipo=TipoAlerta.PATRON_ATAQUE,
            severidad=SeveridadAlerta.ALTA,
            titulo="Intento de acceso no autorizado",
            descripcion=f"Se detectó un intento de acceso no autorizado desde {ip_address}",
            timestamp=datetime.utcnow(),
            usuario_id=usuario_id,
            ip_address=ip_address,
            datos_adicionales=datos_evento,
            acciones_recomendadas=[
                f"Bloquear IP {ip_address} inmediatamente",
                "Investigar el tipo de ataque",
                "Revisar logs de seguridad detallados",
                "Verificar integridad del sistema"
            ]
        )
        
        return [alerta]
    
    async def _analizar_rate_limit_excedido(
        self,
        ip_address: Optional[str],
        datos_evento: Dict[str, Any]
    ) -> List[Alerta]:
        """Analiza excesos de rate limiting."""
        
        # Contar excesos recientes de esta IP
        clave_contador = f"rate_limit_exceeded:{ip_address}"
        excesos_recientes = self.redis.incr(clave_contador)
        self.redis.expire(clave_contador, 3600)  # Expira en 1 hora
        
        # Generar alerta si hay muchos excesos
        if excesos_recientes >= 10:  # 10 excesos en 1 hora
            alerta = Alerta(
                id=f"rate_limit_abuse_{ip_address}_{int(time.time())}",
                tipo=TipoAlerta.RATE_LIMIT_EXCEDIDO,
                severidad=SeveridadAlerta.MEDIA,
                titulo=f"Abuso de rate limiting desde {ip_address}",
                descripcion=f"IP {ip_address} ha excedido rate limits {excesos_recientes} veces en la última hora",
                timestamp=datetime.utcnow(),
                ip_address=ip_address,
                datos_adicionales={
                    "excesos_recientes": excesos_recientes,
                    "endpoint": datos_evento.get("endpoint"),
                    "user_agent": datos_evento.get("user_agent")
                },
                acciones_recomendadas=[
                    f"Considerar bloquear IP {ip_address}",
                    "Investigar si es tráfico legítimo o ataque",
                    "Ajustar límites si es necesario"
                ]
            )
            return [alerta]
        
        return []
    
    async def _analizar_error_sistema(self, datos_evento: Dict[str, Any]) -> List[Alerta]:
        """Analiza errores del sistema para detectar problemas críticos."""
        
        # Verificar si es un error crítico
        error_msg = datos_evento.get("error", "").lower()
        errores_criticos = [
            "database connection failed",
            "out of memory",
            "disk full",
            "security violation",
            "authentication bypass",
            "privilege escalation"
        ]
        
        es_critico = any(error_critico in error_msg for error_critico in errores_criticos)
        
        if es_critico:
            alerta = Alerta(
                id=f"critical_error_{int(time.time())}",
                tipo=TipoAlerta.ERROR_SISTEMA_CRITICO,
                severidad=SeveridadAlerta.CRITICA,
                titulo="Error crítico del sistema detectado",
                descripcion=f"Se detectó un error crítico: {datos_evento.get('error', 'Error desconocido')}",
                timestamp=datetime.utcnow(),
                datos_adicionales=datos_evento,
                acciones_recomendadas=[
                    "Investigar inmediatamente la causa del error",
                    "Verificar estado de servicios críticos",
                    "Revisar logs del sistema",
                    "Considerar activar procedimientos de emergencia"
                ]
            )
            return [alerta]
        
        return []
    
    # Métodos de monitoreo continuo
    
    async def _monitorear_intentos_login(self):
        """Monitorea intentos de login en tiempo real."""
        
        while True:
            try:
                # Analizar intentos de login de los últimos 5 minutos
                hace_5min = datetime.utcnow() - timedelta(minutes=5)
                
                intentos_recientes = self.db.query(LogAuditoria).filter(
                    and_(
                        LogAuditoria.tipo_evento.in_([
                            TipoEventoAuditoria.LOGIN_FALLIDO,
                            TipoEventoAuditoria.LOGIN_EXITOSO
                        ]),
                        LogAuditoria.timestamp >= hace_5min
                    )
                ).all()
                
                # Agrupar por IP y analizar patrones
                ips_intentos = {}
                for intento in intentos_recientes:
                    ip = intento.ip_address
                    if ip not in ips_intentos:
                        ips_intentos[ip] = {"exitosos": 0, "fallidos": 0}
                    
                    if intento.tipo_evento == TipoEventoAuditoria.LOGIN_EXITOSO:
                        ips_intentos[ip]["exitosos"] += 1
                    else:
                        ips_intentos[ip]["fallidos"] += 1
                
                # Detectar patrones sospechosos
                for ip, stats in ips_intentos.items():
                    if stats["fallidos"] > 3 and stats["exitosos"] == 0:
                        # Posible ataque de fuerza bruta
                        await self._generar_alerta_fuerza_bruta(ip, stats["fallidos"])
                
                await asyncio.sleep(300)  # Esperar 5 minutos
                
            except Exception as e:
                print(f"Error en monitoreo de login: {str(e)}")
                await asyncio.sleep(60)  # Esperar 1 minuto en caso de error
    
    async def _monitorear_patrones_acceso(self):
        """Monitorea patrones de acceso anómalos."""
        
        while True:
            try:
                # Analizar patrones de los últimos 15 minutos
                hace_15min = datetime.utcnow() - timedelta(minutes=15)
                
                # Obtener actividad por usuario
                actividad_usuarios = self.db.query(
                    LogAuditoria.usuario_id,
                    func.count(LogAuditoria.id).label('eventos'),
                    func.count(func.distinct(LogAuditoria.ip_address)).label('ips_distintas')
                ).filter(
                    LogAuditoria.timestamp >= hace_15min,
                    LogAuditoria.usuario_id.isnot(None)
                ).group_by(LogAuditoria.usuario_id).all()
                
                for usuario_id, eventos, ips_distintas in actividad_usuarios:
                    # Detectar actividad desde múltiples IPs
                    if ips_distintas > 3:  # Más de 3 IPs diferentes
                        await self._generar_alerta_multiples_ips(usuario_id, ips_distintas)
                    
                    # Detectar volumen inusual de actividad
                    promedio_usuario = await self._obtener_promedio_actividad_usuario(usuario_id)
                    if eventos > promedio_usuario * 5:  # 5x más actividad de lo normal
                        await self._generar_alerta_volumen_inusual(usuario_id, eventos, promedio_usuario)
                
                await asyncio.sleep(900)  # Esperar 15 minutos
                
            except Exception as e:
                print(f"Error en monitoreo de patrones: {str(e)}")
                await asyncio.sleep(300)
    
    async def _monitorear_anomalias_ubicacion(self):
        """Monitorea anomalías de ubicación geográfica."""
        
        while True:
            try:
                # Analizar logins de los últimos 30 minutos
                hace_30min = datetime.utcnow() - timedelta(minutes=30)
                
                logins_recientes = self.db.query(LogAuditoria).filter(
                    and_(
                        LogAuditoria.tipo_evento == TipoEventoAuditoria.LOGIN_EXITOSO,
                        LogAuditoria.timestamp >= hace_30min,
                        LogAuditoria.usuario_id.isnot(None),
                        LogAuditoria.ip_address.isnot(None)
                    )
                ).all()
                
                for login in logins_recientes:
                    # Verificar si es una ubicación nueva para el usuario
                    if await self._es_ubicacion_nueva(login.usuario_id, login.ip_address):
                        ubicacion = await self._obtener_ubicacion_ip(login.ip_address)
                        await self._generar_alerta_ubicacion_nueva(
                            login.usuario_id, 
                            login.ip_address, 
                            ubicacion
                        )
                
                await asyncio.sleep(1800)  # Esperar 30 minutos
                
            except Exception as e:
                print(f"Error en monitoreo de ubicaciones: {str(e)}")
                await asyncio.sleep(600)
    
    async def _monitorear_volumen_requests(self):
        """Monitorea volumen inusual de requests."""
        
        while True:
            try:
                # Analizar requests de los últimos 10 minutos
                hace_10min = datetime.utcnow() - timedelta(minutes=10)
                
                # Contar requests por IP
                requests_por_ip = self.db.query(
                    LogAuditoria.ip_address,
                    func.count(LogAuditoria.id).label('requests')
                ).filter(
                    LogAuditoria.timestamp >= hace_10min,
                    LogAuditoria.ip_address.isnot(None)
                ).group_by(LogAuditoria.ip_address).all()
                
                for ip_address, requests in requests_por_ip:
                    # Detectar volumen excesivo (más de 100 requests en 10 min)
                    if requests > 100:
                        await self._generar_alerta_volumen_excesivo(ip_address, requests)
                
                await asyncio.sleep(600)  # Esperar 10 minutos
                
            except Exception as e:
                print(f"Error en monitoreo de volumen: {str(e)}")
                await asyncio.sleep(300)
    
    async def _monitorear_errores_sistema(self):
        """Monitorea errores críticos del sistema."""
        
        while True:
            try:
                # Analizar errores de los últimos 5 minutos
                hace_5min = datetime.utcnow() - timedelta(minutes=5)
                
                errores_recientes = self.db.query(LogAuditoria).filter(
                    and_(
                        LogAuditoria.tipo_evento == TipoEventoAuditoria.ERROR_SISTEMA,
                        LogAuditoria.timestamp >= hace_5min,
                        LogAuditoria.severidad.in_([NivelSeveridad.ERROR, NivelSeveridad.CRITICAL])
                    )
                ).all()
                
                # Agrupar errores similares
                errores_agrupados = {}
                for error in errores_recientes:
                    error_tipo = error.datos_evento.get("error_type", "unknown")
                    if error_tipo not in errores_agrupados:
                        errores_agrupados[error_tipo] = []
                    errores_agrupados[error_tipo].append(error)
                
                # Generar alertas para errores frecuentes
                for error_tipo, errores in errores_agrupados.items():
                    if len(errores) > 5:  # Más de 5 errores del mismo tipo
                        await self._generar_alerta_errores_frecuentes(error_tipo, len(errores))
                
                await asyncio.sleep(300)  # Esperar 5 minutos
                
            except Exception as e:
                print(f"Error en monitoreo de errores: {str(e)}")
                await asyncio.sleep(60)
    
    async def _limpiar_alertas_antiguas(self):
        """Limpia alertas antiguas del cache."""
        
        while True:
            try:
                # Limpiar alertas resueltas de más de 7 días
                hace_7d = datetime.utcnow() - timedelta(days=7)
                
                alertas_a_limpiar = []
                for alerta_id, alerta in self.cache_alertas.items():
                    if (alerta.estado in ["resuelta", "falso_positivo"] and 
                        alerta.timestamp < hace_7d):
                        alertas_a_limpiar.append(alerta_id)
                
                for alerta_id in alertas_a_limpiar:
                    del self.cache_alertas[alerta_id]
                    self.alertas_activas.discard(alerta_id)
                
                await asyncio.sleep(86400)  # Limpiar una vez al día
                
            except Exception as e:
                print(f"Error en limpieza de alertas: {str(e)}")
                await asyncio.sleep(3600)  # Reintentar en 1 hora
    
    # Métodos helper
    
    async def _procesar_alerta(self, alerta: Alerta):
        """Procesa una alerta generada."""
        
        # Evitar duplicados recientes
        clave_duplicado = f"{alerta.tipo}_{alerta.ip_address or 'no_ip'}_{alerta.usuario_id or 'no_user'}"
        if clave_duplicado in self.alertas_activas:
            return
        
        # Guardar en cache
        self.cache_alertas[alerta.id] = alerta
        self.alertas_activas.add(clave_duplicado)
        
        # Guardar en Redis para persistencia
        await self._guardar_alerta_redis(alerta)
        
        # Enviar notificaciones según severidad
        canales = self.canales_notificacion.get(alerta.severidad, ["log"])
        for canal in canales:
            await self._enviar_notificacion(alerta, canal)
        
        # Registrar en auditoría
        await self.auditoria.log_evento(
            tipo_evento=TipoEventoAuditoria.DETECCION_ANOMALIA,
            descripcion=f"Alerta de seguridad generada: {alerta.titulo}",
            usuario_id=alerta.usuario_id,
            ip_address=alerta.ip_address,
            datos_evento={
                "alerta_id": alerta.id,
                "tipo": alerta.tipo.value,
                "severidad": alerta.severidad.value,
                "datos_adicionales": alerta.datos_adicionales
            },
            severidad=NivelSeveridad.WARNING if alerta.severidad in [SeveridadAlerta.BAJA, SeveridadAlerta.MEDIA] else NivelSeveridad.ERROR
        )
    
    async def _enviar_notificacion(self, alerta: Alerta, canal: str):
        """Envía notificación de alerta por el canal especificado."""
        
        if canal == "email":
            await self._enviar_email_alerta(alerta)
        elif canal == "slack":
            await self._enviar_slack_alerta(alerta)
        elif canal == "sms":
            await self._enviar_sms_alerta(alerta)
        elif canal == "log":
            print(f"ALERTA DE SEGURIDAD: {alerta.titulo} - {alerta.descripcion}")
    
    async def _enviar_email_alerta(self, alerta: Alerta):
        """Envía alerta por email."""
        # TODO: Implementar envío de email
        pass
    
    async def _enviar_slack_alerta(self, alerta: Alerta):
        """Envía alerta a Slack."""
        # TODO: Implementar integración con Slack
        pass
    
    async def _enviar_sms_alerta(self, alerta: Alerta):
        """Envía alerta por SMS."""
        # TODO: Implementar envío de SMS
        pass
    
    def _alerta_to_dict(self, alerta: Alerta) -> Dict[str, Any]:
        """Convierte una alerta a diccionario."""
        return {
            "id": alerta.id,
            "tipo": alerta.tipo.value,
            "severidad": alerta.severidad.value,
            "titulo": alerta.titulo,
            "descripcion": alerta.descripcion,
            "timestamp": alerta.timestamp.isoformat(),
            "usuario_id": alerta.usuario_id,
            "ip_address": alerta.ip_address,
            "datos_adicionales": alerta.datos_adicionales,
            "acciones_recomendadas": alerta.acciones_recomendadas,
            "estado": alerta.estado
        }
    
    # Métodos placeholder para funcionalidades específicas
    # (Estos se implementarían según los requisitos específicos)
    
    async def _obtener_ubicaciones_usuario(self, usuario_id: str) -> List[Dict[str, Any]]:
        """Obtiene ubicaciones históricas del usuario."""
        return []  # TODO: Implementar
    
    async def _es_ubicacion_anomala(self, ip_address: str, ubicaciones_historicas: List) -> bool:
        """Determina si una IP representa una ubicación anómala."""
        return False  # TODO: Implementar con servicio de geolocalización
    
    async def _obtener_ubicacion_ip(self, ip_address: str) -> Dict[str, Any]:
        """Obtiene ubicación geográfica de una IP."""
        return {"pais": "Unknown", "ciudad": "Unknown"}  # TODO: Implementar
    
    async def _es_horario_inusual(self, usuario_id: str, timestamp: datetime) -> bool:
        """Determina si el horario de acceso es inusual para el usuario."""
        return False  # TODO: Implementar análisis de patrones horarios
    
    async def _obtener_patron_horario_usuario(self, usuario_id: str) -> Dict[str, Any]:
        """Obtiene el patrón horario normal del usuario."""
        return {"horario_habitual": "09:00-18:00"}  # TODO: Implementar
    
    async def _obtener_promedio_actividad_usuario(self, usuario_id: str) -> int:
        """Obtiene el promedio de actividad del usuario."""
        return 10  # TODO: Implementar cálculo real
    
    async def _es_ubicacion_nueva(self, usuario_id: str, ip_address: str) -> bool:
        """Determina si es una ubicación nueva para el usuario."""
        return False  # TODO: Implementar
    
    async def _guardar_alerta_redis(self, alerta: Alerta):
        """Guarda alerta en Redis."""
        clave = f"alerta:{alerta.id}"
        valor = json.dumps(self._alerta_to_dict(alerta))
        self.redis.setex(clave, 86400 * 7, valor)  # Expira en 7 días
    
    async def _obtener_alerta(self, alerta_id: str) -> Optional[Alerta]:
        """Obtiene una alerta por ID."""
        return self.cache_alertas.get(alerta_id)
    
    async def _actualizar_alerta(self, alerta: Alerta):
        """Actualiza una alerta."""
        self.cache_alertas[alerta.id] = alerta
        await self._guardar_alerta_redis(alerta)
    
    # Métodos para generar alertas específicas
    
    async def _generar_alerta_fuerza_bruta(self, ip_address: str, intentos: int):
        """Genera alerta de fuerza bruta."""
        # Implementación específica
        pass
    
    async def _generar_alerta_multiples_ips(self, usuario_id: str, num_ips: int):
        """Genera alerta por múltiples IPs."""
        # Implementación específica
        pass
    
    async def _generar_alerta_volumen_inusual(self, usuario_id: str, eventos: int, promedio: int):
        """Genera alerta por volumen inusual."""
        # Implementación específica
        pass
    
    async def _generar_alerta_ubicacion_nueva(self, usuario_id: str, ip_address: str, ubicacion: Dict):
        """Genera alerta por ubicación nueva."""
        # Implementación específica
        pass
    
    async def _generar_alerta_volumen_excesivo(self, ip_address: str, requests: int):
        """Genera alerta por volumen excesivo."""
        # Implementación específica
        pass
    
    async def _generar_alerta_errores_frecuentes(self, error_tipo: str, cantidad: int):
        """Genera alerta por errores frecuentes."""
        # Implementación específica
        pass
    
    # Métodos para dashboard
    
    async def _contar_alertas_periodo(self, desde: datetime, hasta: datetime) -> int:
        """Cuenta alertas en un período."""
        return len([a for a in self.cache_alertas.values() 
                   if desde <= a.timestamp <= hasta])
    
    async def _obtener_alertas_activas(self) -> List[Alerta]:
        """Obtiene alertas activas."""
        return [a for a in self.cache_alertas.values() 
                if a.estado in ["nueva", "investigando"]]
    
    async def _obtener_eventos_seguridad_recientes(self, limite: int = 20) -> List[Dict]:
        """Obtiene eventos de seguridad recientes."""
        eventos = self.db.query(LogAuditoria).filter(
            LogAuditoria.tipo_evento.in_([
                TipoEventoAuditoria.LOGIN_FALLIDO,
                TipoEventoAuditoria.INTENTO_ACCESO_NO_AUTORIZADO,
                TipoEventoAuditoria.RATE_LIMIT_EXCEDIDO,
                TipoEventoAuditoria.DETECCION_ANOMALIA
            ])
        ).order_by(LogAuditoria.timestamp.desc()).limit(limite).all()
        
        return [{
            "timestamp": evento.timestamp.isoformat(),
            "tipo": evento.tipo_evento.value,
            "descripcion": evento.descripcion,
            "ip_address": evento.ip_address,
            "severidad": evento.severidad.value
        } for evento in eventos]
    
    async def _obtener_metricas_autenticacion(self, desde: datetime) -> Dict[str, Any]:
        """Obtiene métricas de autenticación."""
        logins_exitosos = self.db.query(LogAuditoria).filter(
            and_(
                LogAuditoria.tipo_evento == TipoEventoAuditoria.LOGIN_EXITOSO,
                LogAuditoria.timestamp >= desde
            )
        ).count()
        
        logins_fallidos = self.db.query(LogAuditoria).filter(
            and_(
                LogAuditoria.tipo_evento == TipoEventoAuditoria.LOGIN_FALLIDO,
                LogAuditoria.timestamp >= desde
            )
        ).count()
        
        return {
            "logins_exitosos": logins_exitosos,
            "logins_fallidos": logins_fallidos,
            "tasa_exito": (logins_exitosos / (logins_exitosos + logins_fallidos) * 100) if (logins_exitosos + logins_fallidos) > 0 else 0
        }
    
    async def _obtener_ips_sospechosas(self, desde: datetime) -> List[Dict[str, Any]]:
        """Obtiene IPs con actividad sospechosa."""
        ips_actividad = self.db.query(
            LogAuditoria.ip_address,
            func.count(LogAuditoria.id).label('eventos'),
            func.sum(func.case([(LogAuditoria.tipo_evento == TipoEventoAuditoria.LOGIN_FALLIDO, 1)], else_=0)).label('fallidos')
        ).filter(
            LogAuditoria.timestamp >= desde,
            LogAuditoria.ip_address.isnot(None)
        ).group_by(LogAuditoria.ip_address).having(
            or_(
                func.count(LogAuditoria.id) > 50,  # Más de 50 eventos
                func.sum(func.case([(LogAuditoria.tipo_evento == TipoEventoAuditoria.LOGIN_FALLIDO, 1)], else_=0)) > 5  # Más de 5 fallidos
            )
        ).order_by(func.count(LogAuditoria.id).desc()).limit(10).all()
        
        return [{
            "ip_address": ip,
            "total_eventos": eventos,
            "logins_fallidos": fallidos or 0,
            "sospechosa": (fallidos or 0) > 5 or eventos > 100
        } for ip, eventos, fallidos in ips_actividad]
    
    async def _obtener_estado_sistema(self) -> Dict[str, Any]:
        """Obtiene estado general del sistema."""
        return {
            "estado": "normal",  # normal, alerta, critico
            "servicios_activos": True,
            "base_datos_conectada": True,
            "redis_conectado": True,
            "espacio_disco_ok": True,
            "memoria_ok": True
        }
    
    def _calcular_estado_general(self, alertas_activas: List[Alerta]) -> str:
        """Calcula el estado general basado en alertas activas."""
        if any(a.severidad == SeveridadAlerta.CRITICA for a in alertas_activas):
            return "critico"
        elif any(a.severidad == SeveridadAlerta.ALTA for a in alertas_activas):
            return "alerta"
        elif len(alertas_activas) > 10:
            return "alerta"
        else:
            return "normal"
    
    async def _recopilar_contexto_investigacion(self, alerta: Alerta) -> Dict[str, Any]:
        """Recopila contexto adicional para investigación de alerta."""
        contexto = {
            "eventos_relacionados": [],
            "actividad_usuario": {},
            "actividad_ip": {},
            "patrones_detectados": []
        }
        
        # Obtener eventos relacionados
        if alerta.usuario_id:
            eventos_usuario = self.db.query(LogAuditoria).filter(
                and_(
                    LogAuditoria.usuario_id == alerta.usuario_id,
                    LogAuditoria.timestamp >= alerta.timestamp - timedelta(hours=24),
                    LogAuditoria.timestamp <= alerta.timestamp + timedelta(hours=1)
                )
            ).order_by(LogAuditoria.timestamp.desc()).limit(50).all()
            
            contexto["eventos_relacionados"] = [{
                "timestamp": e.timestamp.isoformat(),
                "tipo": e.tipo_evento.value,
                "descripcion": e.descripcion,
                "ip_address": e.ip_address
            } for e in eventos_usuario]
        
        if alerta.ip_address:
            eventos_ip = self.db.query(LogAuditoria).filter(
                and_(
                    LogAuditoria.ip_address == alerta.ip_address,
                    LogAuditoria.timestamp >= alerta.timestamp - timedelta(hours=24),
                    LogAuditoria.timestamp <= alerta.timestamp + timedelta(hours=1)
                )
            ).order_by(LogAuditoria.timestamp.desc()).limit(50).all()
            
            contexto["actividad_ip"] = {
                "total_eventos": len(eventos_ip),
                "usuarios_afectados": len(set(e.usuario_id for e in eventos_ip if e.usuario_id)),
                "tipos_evento": list(set(e.tipo_evento.value for e in eventos_ip))
            }
        
        return contexto
    
    async def _aprender_falso_positivo(self, alerta: Alerta):
        """Aprende de falsos positivos para mejorar detección."""
        # TODO: Implementar machine learning para reducir falsos positivos
        pass
