"""
Servicio de auditoría y logs de seguridad para Axonote.
Proporciona trazabilidad completa de acciones y eventos del sistema.
"""

import json
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from fastapi import Request

from app.models.usuario import (
    LogAuditoria, TipoEventoAuditoria, NivelSeveridad, Usuario
)
from app.core.config import settings


class ServicioAuditoria:
    """
    Servicio completo de auditoría para el sistema Axonote.
    Registra, consulta y analiza eventos de seguridad y operaciones.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    async def log_evento(
        self,
        tipo_evento: TipoEventoAuditoria,
        descripcion: str,
        usuario_id: Optional[str] = None,
        sesion_id: Optional[str] = None,
        usuario_afectado_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        endpoint: Optional[str] = None,
        metodo_http: Optional[str] = None,
        codigo_respuesta: Optional[int] = None,
        datos_evento: Optional[Dict] = None,
        datos_antes: Optional[Dict] = None,
        datos_despues: Optional[Dict] = None,
        recurso_afectado: Optional[str] = None,
        tipo_recurso: Optional[str] = None,
        resultado: str = "exitoso",
        severidad: NivelSeveridad = NivelSeveridad.INFO,
        trace_id: Optional[str] = None,
        evento_padre_id: Optional[str] = None
    ) -> LogAuditoria:
        """
        Registra un evento de auditoría completo.
        
        Args:
            tipo_evento: Tipo de evento según enum
            descripcion: Descripción legible del evento
            usuario_id: ID del usuario que ejecuta la acción
            sesion_id: ID de la sesión activa
            usuario_afectado_id: ID del usuario afectado (si diferente)
            ip_address: Dirección IP del cliente
            user_agent: User agent del navegador
            endpoint: Endpoint de la API accedido
            metodo_http: Método HTTP (GET, POST, etc.)
            codigo_respuesta: Código de respuesta HTTP
            datos_evento: Datos específicos del evento
            datos_antes: Estado antes del cambio
            datos_despues: Estado después del cambio
            recurso_afectado: ID del recurso afectado
            tipo_recurso: Tipo de recurso (sesion, usuario, etc.)
            resultado: Resultado de la operación
            severidad: Nivel de severidad del evento
            trace_id: ID para correlacionar eventos relacionados
            evento_padre_id: ID del evento padre si es parte de una secuencia
            
        Returns:
            LogAuditoria: Entrada de log creada
        """
        
        # Sanitizar datos sensibles
        datos_evento_sanitizados = self._sanitizar_datos_sensibles(datos_evento or {})
        datos_antes_sanitizados = self._sanitizar_datos_sensibles(datos_antes or {}) if datos_antes else None
        datos_despues_sanitizados = self._sanitizar_datos_sensibles(datos_despues or {}) if datos_despues else None
        
        # Crear entrada de log
        log_entry = LogAuditoria(
            tipo_evento=tipo_evento,
            severidad=severidad,
            descripcion=descripcion,
            resultado=resultado,
            usuario_id=usuario_id,
            sesion_id=sesion_id,
            usuario_afectado_id=usuario_afectado_id,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint=endpoint,
            metodo_http=metodo_http,
            codigo_respuesta=codigo_respuesta,
            datos_evento=datos_evento_sanitizados,
            datos_antes=datos_antes_sanitizados,
            datos_despues=datos_despues_sanitizados,
            recurso_afectado=recurso_afectado,
            tipo_recurso=tipo_recurso,
            trace_id=trace_id,
            evento_padre_id=evento_padre_id
        )
        
        # Generar hash de integridad
        log_entry.hash_integridad = log_entry.generar_hash_integridad()
        
        # Guardar en base de datos
        self.db.add(log_entry)
        self.db.flush()  # Para obtener el ID sin hacer commit
        
        # Procesar evento crítico si es necesario
        if self._es_evento_critico(tipo_evento, severidad):
            await self._procesar_evento_critico(log_entry)
        
        return log_entry
    
    async def log_evento_desde_request(
        self,
        request: Request,
        tipo_evento: TipoEventoAuditoria,
        descripcion: str,
        usuario_id: Optional[str] = None,
        **kwargs
    ) -> LogAuditoria:
        """
        Registra un evento extrayendo información automáticamente del Request.
        
        Args:
            request: Request de FastAPI
            tipo_evento: Tipo de evento
            descripcion: Descripción del evento
            usuario_id: ID del usuario (si está disponible)
            **kwargs: Argumentos adicionales para log_evento
            
        Returns:
            LogAuditoria: Entrada de log creada
        """
        
        # Extraer información del request
        ip_address = self._obtener_ip_real(request)
        user_agent = request.headers.get("User-Agent", "")
        endpoint = str(request.url.path)
        metodo_http = request.method
        
        return await self.log_evento(
            tipo_evento=tipo_evento,
            descripcion=descripcion,
            usuario_id=usuario_id,
            ip_address=ip_address,
            user_agent=user_agent,
            endpoint=endpoint,
            metodo_http=metodo_http,
            **kwargs
        )
    
    async def buscar_eventos(
        self,
        usuario_id: Optional[str] = None,
        tipo_evento: Optional[TipoEventoAuditoria] = None,
        severidad: Optional[NivelSeveridad] = None,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
        resultado: Optional[str] = None,
        trace_id: Optional[str] = None,
        limite: int = 100,
        offset: int = 0,
        orden_desc: bool = True
    ) -> List[LogAuditoria]:
        """
        Busca eventos de auditoría con filtros múltiples.
        
        Args:
            usuario_id: Filtrar por usuario
            tipo_evento: Filtrar por tipo de evento
            severidad: Filtrar por severidad
            fecha_inicio: Fecha de inicio del rango
            fecha_fin: Fecha de fin del rango
            ip_address: Filtrar por IP
            endpoint: Filtrar por endpoint
            resultado: Filtrar por resultado
            trace_id: Filtrar por trace ID
            limite: Número máximo de resultados
            offset: Offset para paginación
            orden_desc: Ordenar por fecha descendente
            
        Returns:
            List[LogAuditoria]: Lista de eventos encontrados
        """
        
        query = self.db.query(LogAuditoria)
        
        # Aplicar filtros
        if usuario_id:
            query = query.filter(
                or_(
                    LogAuditoria.usuario_id == usuario_id,
                    LogAuditoria.usuario_afectado_id == usuario_id
                )
            )
        
        if tipo_evento:
            query = query.filter(LogAuditoria.tipo_evento == tipo_evento)
        
        if severidad:
            query = query.filter(LogAuditoria.severidad == severidad)
        
        if fecha_inicio:
            query = query.filter(LogAuditoria.timestamp >= fecha_inicio)
        
        if fecha_fin:
            query = query.filter(LogAuditoria.timestamp <= fecha_fin)
        
        if ip_address:
            query = query.filter(LogAuditoria.ip_address == ip_address)
        
        if endpoint:
            query = query.filter(LogAuditoria.endpoint.like(f"%{endpoint}%"))
        
        if resultado:
            query = query.filter(LogAuditoria.resultado == resultado)
        
        if trace_id:
            query = query.filter(LogAuditoria.trace_id == trace_id)
        
        # Ordenar
        if orden_desc:
            query = query.order_by(desc(LogAuditoria.timestamp))
        else:
            query = query.order_by(LogAuditoria.timestamp)
        
        # Paginación
        query = query.offset(offset).limit(limite)
        
        return query.all()
    
    async def obtener_estadisticas_auditoria(
        self,
        fecha_inicio: Optional[datetime] = None,
        fecha_fin: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Obtiene estadísticas de auditoría para un período.
        
        Args:
            fecha_inicio: Inicio del período (por defecto últimas 24h)
            fecha_fin: Fin del período (por defecto ahora)
            
        Returns:
            Dict con estadísticas de auditoría
        """
        
        if not fecha_inicio:
            fecha_inicio = datetime.utcnow() - timedelta(days=1)
        
        if not fecha_fin:
            fecha_fin = datetime.utcnow()
        
        # Query base con filtro de fechas
        base_query = self.db.query(LogAuditoria).filter(
            and_(
                LogAuditoria.timestamp >= fecha_inicio,
                LogAuditoria.timestamp <= fecha_fin
            )
        )
        
        # Total de eventos
        total_eventos = base_query.count()
        
        # Eventos por tipo
        eventos_por_tipo = {}
        for tipo_evento in TipoEventoAuditoria:
            count = base_query.filter(LogAuditoria.tipo_evento == tipo_evento).count()
            if count > 0:
                eventos_por_tipo[tipo_evento.value] = count
        
        # Eventos por severidad
        eventos_por_severidad = {}
        for severidad in NivelSeveridad:
            count = base_query.filter(LogAuditoria.severidad == severidad).count()
            if count > 0:
                eventos_por_severidad[severidad.value] = count
        
        # Eventos por resultado
        eventos_exitosos = base_query.filter(LogAuditoria.resultado == "exitoso").count()
        eventos_fallidos = base_query.filter(LogAuditoria.resultado == "fallido").count()
        eventos_bloqueados = base_query.filter(LogAuditoria.resultado == "bloqueado").count()
        
        # Top IPs con más actividad
        top_ips = (
            base_query
            .filter(LogAuditoria.ip_address.isnot(None))
            .with_entities(LogAuditoria.ip_address, func.count(LogAuditoria.id).label('count'))
            .group_by(LogAuditoria.ip_address)
            .order_by(desc('count'))
            .limit(10)
            .all()
        )
        
        # Top usuarios con más actividad
        top_usuarios = (
            base_query
            .filter(LogAuditoria.usuario_id.isnot(None))
            .with_entities(LogAuditoria.usuario_id, func.count(LogAuditoria.id).label('count'))
            .group_by(LogAuditoria.usuario_id)
            .order_by(desc('count'))
            .limit(10)
            .all()
        )
        
        # Endpoints más accedidos
        top_endpoints = (
            base_query
            .filter(LogAuditoria.endpoint.isnot(None))
            .with_entities(LogAuditoria.endpoint, func.count(LogAuditoria.id).label('count'))
            .group_by(LogAuditoria.endpoint)
            .order_by(desc('count'))
            .limit(10)
            .all()
        )
        
        return {
            "periodo": {
                "inicio": fecha_inicio.isoformat(),
                "fin": fecha_fin.isoformat()
            },
            "resumen": {
                "total_eventos": total_eventos,
                "eventos_exitosos": eventos_exitosos,
                "eventos_fallidos": eventos_fallidos,
                "eventos_bloqueados": eventos_bloqueados,
                "tasa_exito": (eventos_exitosos / total_eventos * 100) if total_eventos > 0 else 0
            },
            "eventos_por_tipo": eventos_por_tipo,
            "eventos_por_severidad": eventos_por_severidad,
            "top_ips": [{"ip": ip, "count": count} for ip, count in top_ips],
            "top_usuarios": [{"usuario_id": str(uid), "count": count} for uid, count in top_usuarios],
            "top_endpoints": [{"endpoint": ep, "count": count} for ep, count in top_endpoints]
        }
    
    async def verificar_integridad_logs(
        self,
        fecha_inicio: Optional[datetime] = None,
        limite: int = 1000
    ) -> Dict[str, Any]:
        """
        Verifica la integridad de los logs de auditoría.
        
        Args:
            fecha_inicio: Fecha desde la cual verificar
            limite: Número máximo de logs a verificar
            
        Returns:
            Dict con resultados de la verificación
        """
        
        query = self.db.query(LogAuditoria)
        
        if fecha_inicio:
            query = query.filter(LogAuditoria.timestamp >= fecha_inicio)
        
        logs = query.order_by(desc(LogAuditoria.timestamp)).limit(limite).all()
        
        logs_verificados = 0
        logs_comprometidos = []
        logs_sin_hash = []
        
        for log in logs:
            logs_verificados += 1
            
            if not log.hash_integridad:
                logs_sin_hash.append(str(log.id))
                continue
            
            # Recalcular hash y comparar
            hash_actual = log.generar_hash_integridad()
            
            if hash_actual != log.hash_integridad:
                logs_comprometidos.append({
                    "id": str(log.id),
                    "timestamp": log.timestamp.isoformat(),
                    "tipo_evento": log.tipo_evento.value,
                    "hash_esperado": log.hash_integridad,
                    "hash_actual": hash_actual
                })
        
        integridad_ok = len(logs_comprometidos) == 0 and len(logs_sin_hash) == 0
        
        return {
            "integridad_ok": integridad_ok,
            "logs_verificados": logs_verificados,
            "logs_comprometidos": len(logs_comprometidos),
            "logs_sin_hash": len(logs_sin_hash),
            "detalles_comprometidos": logs_comprometidos,
            "logs_sin_hash_ids": logs_sin_hash
        }
    
    async def limpiar_logs_antiguos(self, dias_retencion: Optional[int] = None) -> int:
        """
        Limpia logs de auditoría antiguos según política de retención.
        
        Args:
            dias_retencion: Días de retención (por defecto desde settings)
            
        Returns:
            Número de logs eliminados
        """
        
        if not dias_retencion:
            dias_retencion = settings.AUDIT_LOG_RETENTION_DAYS
        
        fecha_limite = datetime.utcnow() - timedelta(days=dias_retencion)
        
        # Contar logs a eliminar
        logs_a_eliminar = self.db.query(LogAuditoria).filter(
            LogAuditoria.timestamp < fecha_limite
        ).count()
        
        # Eliminar logs antiguos
        self.db.query(LogAuditoria).filter(
            LogAuditoria.timestamp < fecha_limite
        ).delete()
        
        self.db.commit()
        
        # Log de la limpieza
        await self.log_evento(
            tipo_evento=TipoEventoAuditoria.BACKUP_CREADO,  # Reutilizamos este tipo
            descripcion=f"Limpieza automática de logs: {logs_a_eliminar} logs eliminados",
            datos_evento={
                "logs_eliminados": logs_a_eliminar,
                "fecha_limite": fecha_limite.isoformat(),
                "dias_retencion": dias_retencion
            },
            severidad=NivelSeveridad.INFO
        )
        
        return logs_a_eliminar
    
    def _sanitizar_datos_sensibles(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitiza datos sensibles antes de almacenar en logs.
        
        Args:
            datos: Diccionario con datos a sanitizar
            
        Returns:
            Diccionario sanitizado
        """
        
        if not isinstance(datos, dict):
            return datos
        
        datos_sanitizados = datos.copy()
        
        # Campos sensibles a sanitizar
        campos_sensibles = settings.AUDIT_LOG_SENSITIVE_FIELDS
        
        for campo in campos_sensibles:
            if campo in datos_sanitizados:
                if isinstance(datos_sanitizados[campo], str) and len(datos_sanitizados[campo]) > 0:
                    # Mostrar solo primeros y últimos caracteres
                    valor = datos_sanitizados[campo]
                    if len(valor) > 6:
                        datos_sanitizados[campo] = f"{valor[:3]}***{valor[-3:]}"
                    else:
                        datos_sanitizados[campo] = "***"
                else:
                    datos_sanitizados[campo] = "***"
        
        # Sanitizar recursivamente diccionarios anidados
        for clave, valor in datos_sanitizados.items():
            if isinstance(valor, dict):
                datos_sanitizados[clave] = self._sanitizar_datos_sensibles(valor)
            elif isinstance(valor, list):
                datos_sanitizados[clave] = [
                    self._sanitizar_datos_sensibles(item) if isinstance(item, dict) else item
                    for item in valor
                ]
        
        return datos_sanitizados
    
    def _es_evento_critico(
        self,
        tipo_evento: TipoEventoAuditoria,
        severidad: NivelSeveridad
    ) -> bool:
        """
        Determina si un evento es crítico y requiere procesamiento especial.
        
        Args:
            tipo_evento: Tipo de evento
            severidad: Severidad del evento
            
        Returns:
            True si es crítico, False si no
        """
        
        # Eventos siempre críticos
        eventos_criticos = {
            TipoEventoAuditoria.INTENTO_ACCESO_NO_AUTORIZADO,
            TipoEventoAuditoria.VIOLACION_SEGURIDAD,
            TipoEventoAuditoria.DETECCION_ANOMALIA,
            TipoEventoAuditoria.USUARIO_BLOQUEADO,
            TipoEventoAuditoria.IP_BLOQUEADA
        }
        
        # Severidades críticas
        severidades_criticas = {
            NivelSeveridad.ERROR,
            NivelSeveridad.CRITICAL
        }
        
        return tipo_evento in eventos_criticos or severidad in severidades_criticas
    
    async def _procesar_evento_critico(self, log_entry: LogAuditoria):
        """
        Procesa eventos críticos con acciones adicionales.
        
        Args:
            log_entry: Entrada de log del evento crítico
        """
        
        # TODO: Implementar acciones para eventos críticos:
        # - Enviar alertas por email/Slack
        # - Notificar a administradores
        # - Activar medidas de seguridad automáticas
        # - Integrar con sistemas de monitoreo externos
        
        pass
    
    def _obtener_ip_real(self, request: Request) -> str:
        """Obtiene la IP real del request considerando proxies."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        cf_connecting_ip = request.headers.get("CF-Connecting-IP")
        if cf_connecting_ip:
            return cf_connecting_ip.strip()
        
        return request.client.host if request.client else "unknown"
