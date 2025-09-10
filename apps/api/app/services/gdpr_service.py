"""
Servicio de compliance GDPR para Axonote.
Implementa todas las funcionalidades requeridas por el GDPR para protección de datos.
"""

import json
import zipfile
import tempfile
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from fastapi import HTTPException, status

from app.models.usuario import Usuario, LogAuditoria, TipoEventoAuditoria, NivelSeveridad
from app.models.class_session_segura import ClassSessionSegura
from app.services.encryption_service import ServicioCifrado
from app.services.auditoria_service import ServicioAuditoria
from app.core.config import settings


class TipoSolicitudGDPR:
    """Tipos de solicitudes GDPR."""
    ACCESO = "acceso"                    # Derecho de acceso (Art. 15)
    RECTIFICACION = "rectificacion"      # Derecho de rectificación (Art. 16)
    SUPRESION = "supresion"              # Derecho al olvido (Art. 17)
    PORTABILIDAD = "portabilidad"        # Derecho a la portabilidad (Art. 20)
    LIMITACION = "limitacion"            # Derecho a la limitación (Art. 18)
    OPOSICION = "oposicion"              # Derecho de oposición (Art. 21)


class EstadoSolicitudGDPR:
    """Estados de una solicitud GDPR."""
    PENDIENTE = "pendiente"
    EN_PROCESO = "en_proceso"
    COMPLETADA = "completada"
    RECHAZADA = "rechazada"
    CANCELADA = "cancelada"


class ConsentimientoGDPR:
    """Tipos de consentimiento GDPR."""
    PROCESAMIENTO_DATOS_MEDICOS = "procesamiento_datos_medicos"
    ANALISIS_IA = "analisis_ia"
    ALMACENAMIENTO_TRANSCRIPCIONES = "almacenamiento_transcripciones"
    INTEGRACION_NOTION = "integracion_notion"
    COOKIES_ANALITICAS = "cookies_analiticas"
    COMUNICACIONES_MARKETING = "comunicaciones_marketing"
    COMPARTIR_DATOS_TERCEROS = "compartir_datos_terceros"


class ServicioGDPR:
    """
    Servicio completo de compliance GDPR.
    Implementa todos los derechos del usuario según el GDPR.
    """
    
    def __init__(self, db: Session, servicio_cifrado: ServicioCifrado, servicio_auditoria: ServicioAuditoria):
        self.db = db
        self.cifrado = servicio_cifrado
        self.auditoria = servicio_auditoria
        
        # Configuración de retención de datos
        self.retencion_datos_dias = {
            "logs_auditoria": 2555,  # 7 años para logs de auditoría
            "sesiones_clase": 1825,  # 5 años para datos académicos
            "datos_usuario": 2555,   # 7 años para datos de usuario
            "consentimientos": 3650  # 10 años para registros de consentimiento
        }
    
    async def procesar_solicitud_acceso(
        self,
        usuario_id: str,
        incluir_datos_tecnicos: bool = False
    ) -> Dict[str, Any]:
        """
        Procesa una solicitud de acceso a datos personales (Art. 15 GDPR).
        
        Args:
            usuario_id: ID del usuario solicitante
            incluir_datos_tecnicos: Si incluir datos técnicos detallados
            
        Returns:
            Dict con todos los datos personales del usuario
        """
        
        usuario = self.db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        # Registrar solicitud de acceso
        await self.auditoria.log_evento(
            tipo_evento=TipoEventoAuditoria.SOLICITUD_DATOS_GDPR,
            descripcion=f"Solicitud de acceso a datos personales: {usuario.email}",
            usuario_id=usuario_id,
            datos_evento={
                "tipo_solicitud": TipoSolicitudGDPR.ACCESO,
                "incluir_datos_tecnicos": incluir_datos_tecnicos
            }
        )
        
        # Recopilar datos personales
        datos_personales = {
            "informacion_usuario": await self._obtener_datos_usuario(usuario),
            "consentimientos": await self._obtener_consentimientos_usuario(usuario_id),
            "sesiones_clase": await self._obtener_sesiones_usuario(usuario_id, incluir_datos_tecnicos),
            "actividad_reciente": await self._obtener_actividad_usuario(usuario_id),
            "configuraciones": await self._obtener_configuraciones_usuario(usuario),
            "metadatos_procesamiento": await self._obtener_metadatos_procesamiento(usuario_id)
        }
        
        if incluir_datos_tecnicos:
            datos_personales["datos_tecnicos"] = await self._obtener_datos_tecnicos(usuario_id)
        
        # Generar reporte
        reporte = {
            "solicitud": {
                "tipo": TipoSolicitudGDPR.ACCESO,
                "fecha_solicitud": datetime.utcnow().isoformat(),
                "usuario_id": usuario_id,
                "email": usuario.email
            },
            "datos_personales": datos_personales,
            "informacion_legal": {
                "base_legal_procesamiento": "Consentimiento del interesado (Art. 6.1.a GDPR)",
                "finalidad_procesamiento": "Transcripción y análisis de contenido médico educativo",
                "periodo_retencion": "5 años desde la última actividad",
                "derechos_usuario": [
                    "Derecho de acceso (Art. 15)",
                    "Derecho de rectificación (Art. 16)", 
                    "Derecho de supresión (Art. 17)",
                    "Derecho a la portabilidad (Art. 20)",
                    "Derecho de oposición (Art. 21)"
                ]
            }
        }
        
        return reporte
    
    async def procesar_solicitud_portabilidad(self, usuario_id: str) -> str:
        """
        Procesa una solicitud de portabilidad de datos (Art. 20 GDPR).
        
        Args:
            usuario_id: ID del usuario solicitante
            
        Returns:
            Path del archivo ZIP con los datos exportados
        """
        
        usuario = self.db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        # Registrar solicitud
        await self.auditoria.log_evento(
            tipo_evento=TipoEventoAuditoria.SOLICITUD_DATOS_GDPR,
            descripcion=f"Solicitud de portabilidad de datos: {usuario.email}",
            usuario_id=usuario_id,
            datos_evento={"tipo_solicitud": TipoSolicitudGDPR.PORTABILIDAD}
        )
        
        # Crear directorio temporal
        temp_dir = tempfile.mkdtemp()
        temp_path = Path(temp_dir)
        
        try:
            # Exportar datos en formato estructurado
            await self._exportar_datos_usuario(usuario_id, temp_path)
            await self._exportar_sesiones_clase(usuario_id, temp_path)
            await self._exportar_consentimientos(usuario_id, temp_path)
            await self._exportar_configuraciones(usuario_id, temp_path)
            
            # Crear archivo ZIP
            zip_path = temp_path / f"datos_personales_{usuario_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in temp_path.rglob('*.json'):
                    if file_path != zip_path:
                        zipf.write(file_path, file_path.relative_to(temp_path))
            
            # Calcular hash del archivo para integridad
            with open(zip_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            
            # Registrar exportación completada
            await self.auditoria.log_evento(
                tipo_evento=TipoEventoAuditoria.EXPORTACION_DATOS,
                descripcion=f"Exportación de datos completada: {usuario.email}",
                usuario_id=usuario_id,
                datos_evento={
                    "archivo_zip": str(zip_path),
                    "hash_archivo": file_hash,
                    "tamaño_bytes": zip_path.stat().st_size
                }
            )
            
            return str(zip_path)
            
        except Exception as e:
            # Limpiar archivos temporales en caso de error
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error exportando datos: {str(e)}"
            )
    
    async def procesar_solicitud_supresion(
        self,
        usuario_id: str,
        motivo: str,
        confirmar_eliminacion: bool = False
    ) -> Dict[str, Any]:
        """
        Procesa una solicitud de supresión/olvido (Art. 17 GDPR).
        
        Args:
            usuario_id: ID del usuario
            motivo: Motivo de la solicitud
            confirmar_eliminacion: Confirmación explícita requerida
            
        Returns:
            Dict con resultado de la operación
        """
        
        if not confirmar_eliminacion:
            raise HTTPException(
                status_code=400,
                detail="Debe confirmar explícitamente la eliminación de datos"
            )
        
        usuario = self.db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        # Registrar solicitud
        await self.auditoria.log_evento(
            tipo_evento=TipoEventoAuditoria.SOLICITUD_DATOS_GDPR,
            descripcion=f"Solicitud de supresión de datos: {usuario.email}",
            usuario_id=usuario_id,
            datos_evento={
                "tipo_solicitud": TipoSolicitudGDPR.SUPRESION,
                "motivo": motivo
            }
        )
        
        # Verificar si hay obligaciones legales que impidan la eliminación
        obligaciones_legales = await self._verificar_obligaciones_legales(usuario_id)
        if obligaciones_legales:
            return {
                "eliminacion_completa": False,
                "motivo_rechazo": "Existen obligaciones legales que requieren retención de datos",
                "obligaciones": obligaciones_legales,
                "datos_anonimizados": True
            }
        
        # Proceder con eliminación/anonimización
        resultado = await self._eliminar_datos_usuario(usuario_id, motivo)
        
        # Registrar eliminación completada
        await self.auditoria.log_evento(
            tipo_evento=TipoEventoAuditoria.ELIMINACION_DATOS_GDPR,
            descripcion=f"Eliminación de datos completada: {usuario.email}",
            usuario_id=usuario_id,
            datos_evento={
                "eliminacion_completa": resultado["eliminacion_completa"],
                "datos_eliminados": resultado["datos_eliminados"],
                "datos_anonimizados": resultado["datos_anonimizados"]
            }
        )
        
        return resultado
    
    async def gestionar_consentimientos(
        self,
        usuario_id: str,
        consentimientos: Dict[str, bool],
        version_politica: str
    ) -> Dict[str, Any]:
        """
        Gestiona los consentimientos del usuario.
        
        Args:
            usuario_id: ID del usuario
            consentimientos: Dict con tipos de consentimiento y valores
            version_politica: Versión de la política de privacidad
            
        Returns:
            Dict con estado actualizado de consentimientos
        """
        
        usuario = self.db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        # Obtener consentimientos anteriores
        consentimientos_anteriores = usuario.consentimientos.copy() if usuario.consentimientos else {}
        
        # Actualizar consentimientos
        usuario.consentimientos = consentimientos
        usuario.fecha_consentimiento = datetime.utcnow()
        usuario.version_politica_aceptada = version_politica
        
        # Identificar cambios
        cambios = []
        for tipo, valor in consentimientos.items():
            valor_anterior = consentimientos_anteriores.get(tipo)
            if valor_anterior != valor:
                cambios.append({
                    "tipo": tipo,
                    "anterior": valor_anterior,
                    "nuevo": valor
                })
        
        self.db.commit()
        
        # Registrar cambios de consentimiento
        for cambio in cambios:
            evento_tipo = (TipoEventoAuditoria.CONSENTIMIENTO_OTORGADO 
                          if cambio["nuevo"] else 
                          TipoEventoAuditoria.CONSENTIMIENTO_REVOCADO)
            
            await self.auditoria.log_evento(
                tipo_evento=evento_tipo,
                descripcion=f"Consentimiento {'otorgado' if cambio['nuevo'] else 'revocado'}: {cambio['tipo']}",
                usuario_id=usuario_id,
                datos_evento={
                    "tipo_consentimiento": cambio["tipo"],
                    "valor_anterior": cambio["anterior"],
                    "valor_nuevo": cambio["nuevo"],
                    "version_politica": version_politica
                }
            )
        
        # Aplicar consecuencias de cambios de consentimiento
        await self._aplicar_cambios_consentimiento(usuario_id, cambios)
        
        return {
            "consentimientos_actualizados": consentimientos,
            "cambios_aplicados": len(cambios),
            "fecha_actualizacion": usuario.fecha_consentimiento.isoformat(),
            "version_politica": version_politica
        }
    
    async def verificar_cumplimiento_retencion(self) -> Dict[str, Any]:
        """
        Verifica el cumplimiento de las políticas de retención de datos.
        
        Returns:
            Dict con estadísticas de cumplimiento
        """
        
        ahora = datetime.utcnow()
        resultados = {
            "fecha_verificacion": ahora.isoformat(),
            "politicas_retencion": self.retencion_datos_dias,
            "datos_expirados": {},
            "acciones_requeridas": []
        }
        
        # Verificar logs de auditoría expirados
        fecha_limite_logs = ahora - timedelta(days=self.retencion_datos_dias["logs_auditoria"])
        logs_expirados = self.db.query(LogAuditoria).filter(
            LogAuditoria.timestamp < fecha_limite_logs
        ).count()
        
        if logs_expirados > 0:
            resultados["datos_expirados"]["logs_auditoria"] = logs_expirados
            resultados["acciones_requeridas"].append({
                "tipo": "eliminar_logs_antiguos",
                "cantidad": logs_expirados,
                "fecha_limite": fecha_limite_logs.isoformat()
            })
        
        # Verificar sesiones de clase expiradas
        fecha_limite_sesiones = ahora - timedelta(days=self.retencion_datos_dias["sesiones_clase"])
        sesiones_expiradas = self.db.query(ClassSessionSegura).filter(
            ClassSessionSegura.created_at < fecha_limite_sesiones
        ).count()
        
        if sesiones_expiradas > 0:
            resultados["datos_expirados"]["sesiones_clase"] = sesiones_expiradas
            resultados["acciones_requeridas"].append({
                "tipo": "anonimizar_sesiones_antiguas",
                "cantidad": sesiones_expiradas,
                "fecha_limite": fecha_limite_sesiones.isoformat()
            })
        
        # Verificar usuarios inactivos
        fecha_limite_usuarios = ahora - timedelta(days=self.retencion_datos_dias["datos_usuario"])
        usuarios_inactivos = self.db.query(Usuario).filter(
            or_(
                Usuario.ultimo_acceso < fecha_limite_usuarios,
                Usuario.ultimo_acceso.is_(None)
            ),
            Usuario.created_at < fecha_limite_usuarios
        ).count()
        
        if usuarios_inactivos > 0:
            resultados["datos_expirados"]["usuarios_inactivos"] = usuarios_inactivos
            resultados["acciones_requeridas"].append({
                "tipo": "notificar_usuarios_inactivos",
                "cantidad": usuarios_inactivos,
                "fecha_limite": fecha_limite_usuarios.isoformat()
            })
        
        return resultados
    
    async def _obtener_datos_usuario(self, usuario: Usuario) -> Dict[str, Any]:
        """Obtiene datos básicos del usuario."""
        return {
            "id": str(usuario.id),
            "email": usuario.email,
            "nombre_completo": usuario.nombre_completo,
            "rol": usuario.rol.value,
            "estado": usuario.estado.value,
            "verificado": usuario.verificado,
            "mfa_habilitado": usuario.mfa_habilitado,
            "fecha_registro": usuario.created_at.isoformat() if usuario.created_at else None,
            "ultimo_acceso": usuario.ultimo_acceso.isoformat() if usuario.ultimo_acceso else None,
            "ultimo_cambio_password": usuario.ultimo_cambio_password.isoformat() if usuario.ultimo_cambio_password else None
        }
    
    async def _obtener_consentimientos_usuario(self, usuario_id: str) -> Dict[str, Any]:
        """Obtiene historial de consentimientos del usuario."""
        usuario = self.db.query(Usuario).filter(Usuario.id == usuario_id).first()
        
        return {
            "consentimientos_actuales": usuario.consentimientos if usuario.consentimientos else {},
            "fecha_consentimiento": usuario.fecha_consentimiento.isoformat() if usuario.fecha_consentimiento else None,
            "version_politica_aceptada": usuario.version_politica_aceptada,
            "historial_cambios": await self._obtener_historial_consentimientos(usuario_id)
        }
    
    async def _obtener_sesiones_usuario(self, usuario_id: str, incluir_contenido: bool = False) -> List[Dict[str, Any]]:
        """Obtiene sesiones de clase del usuario."""
        sesiones = self.db.query(ClassSessionSegura).filter(
            ClassSessionSegura.usuario_id == usuario_id
        ).all()
        
        datos_sesiones = []
        for sesion in sesiones:
            datos_sesion = {
                "id": str(sesion.id),
                "fecha": sesion.fecha.isoformat(),
                "asignatura": sesion.asignatura,
                "tema": sesion.tema,
                "duracion_minutos": sesion.duracion_minutos,
                "estado_pipeline": sesion.estado_pipeline.value,
                "fecha_creacion": sesion.created_at.isoformat() if sesion.created_at else None,
                "tiene_datos_sensibles": sesion.tiene_datos_sensibles
            }
            
            if incluir_contenido and sesion.tiene_datos_sensibles:
                # Solo incluir contenido si se solicita explícitamente
                datos_sesion["contenido"] = {
                    "transcripcion_disponible": bool(sesion.transcripcion_md),
                    "resumen_disponible": bool(sesion.resumen_md),
                    "glosario_disponible": bool(sesion.glosario_json),
                    "preguntas_disponibles": bool(sesion.preguntas_json)
                }
            
            datos_sesiones.append(datos_sesion)
        
        return datos_sesiones
    
    async def _obtener_actividad_usuario(self, usuario_id: str) -> Dict[str, Any]:
        """Obtiene actividad reciente del usuario."""
        # Obtener logs de los últimos 30 días
        fecha_limite = datetime.utcnow() - timedelta(days=30)
        
        logs_recientes = self.db.query(LogAuditoria).filter(
            LogAuditoria.usuario_id == usuario_id,
            LogAuditoria.timestamp >= fecha_limite
        ).order_by(LogAuditoria.timestamp.desc()).limit(100).all()
        
        actividad = []
        for log in logs_recientes:
            actividad.append({
                "fecha": log.timestamp.isoformat(),
                "tipo_evento": log.tipo_evento.value,
                "descripcion": log.descripcion,
                "resultado": log.resultado,
                "ip_address": log.ip_address
            })
        
        return {
            "actividad_reciente": actividad,
            "total_eventos_30_dias": len(actividad)
        }
    
    async def _obtener_configuraciones_usuario(self, usuario: Usuario) -> Dict[str, Any]:
        """Obtiene configuraciones del usuario."""
        return {
            "preferencias": usuario.preferencias if usuario.preferencias else {},
            "configuracion_notificaciones": usuario.configuracion_notificaciones if usuario.configuracion_notificaciones else {}
        }
    
    async def _obtener_metadatos_procesamiento(self, usuario_id: str) -> Dict[str, Any]:
        """Obtiene metadatos sobre el procesamiento de datos."""
        return {
            "base_legal": "Consentimiento del interesado (Art. 6.1.a GDPR)",
            "finalidades": [
                "Transcripción de audio médico educativo",
                "Análisis y resumen de contenido",
                "Generación de material de estudio",
                "Sincronización con herramientas de productividad"
            ],
            "categorias_datos": [
                "Datos de identificación (email, nombre)",
                "Datos de contenido educativo (transcripciones, notas)",
                "Datos técnicos (logs de actividad, métricas de uso)",
                "Datos de preferencias (configuraciones, consentimientos)"
            ],
            "destinatarios": [
                "Usuario propietario de los datos",
                "Servicios de IA para procesamiento (OpenAI, modelos locales)",
                "Servicios de almacenamiento (MinIO local)",
                "Servicios de productividad (Notion, si autorizado)"
            ],
            "transferencias_internacionales": "Solo a servicios de IA si autorizado explícitamente",
            "periodo_retencion": "5 años desde la última actividad o hasta revocación del consentimiento"
        }
    
    async def _obtener_datos_tecnicos(self, usuario_id: str) -> Dict[str, Any]:
        """Obtiene datos técnicos detallados."""
        return {
            "sesiones_activas": await self._contar_sesiones_activas(usuario_id),
            "uso_almacenamiento": await self._calcular_uso_almacenamiento(usuario_id),
            "estadisticas_procesamiento": await self._obtener_estadisticas_procesamiento(usuario_id),
            "configuraciones_tecnicas": await self._obtener_configuraciones_tecnicas(usuario_id)
        }
    
    async def _eliminar_datos_usuario(self, usuario_id: str, motivo: str) -> Dict[str, Any]:
        """Elimina o anonimiza datos del usuario."""
        
        usuario = self.db.query(Usuario).filter(Usuario.id == usuario_id).first()
        
        # Anonimizar datos del usuario (mantener para integridad de auditoría)
        email_original = usuario.email
        usuario.email = f"usuario_eliminado_{usuario_id[:8]}@gdpr.local"
        usuario.nombre_completo = "Usuario Eliminado (GDPR)"
        usuario.password_hash = "ELIMINADO_GDPR"
        usuario.estado = "inactivo"
        usuario.mfa_secreto = None
        usuario.codigos_recuperacion = []
        usuario.consentimientos = {}
        usuario.preferencias = {}
        usuario.configuracion_notificaciones = {}
        
        # Eliminar datos sensibles de sesiones
        sesiones = self.db.query(ClassSessionSegura).filter(
            ClassSessionSegura.usuario_id == usuario_id
        ).all()
        
        datos_eliminados = {
            "sesiones_procesadas": len(sesiones),
            "datos_sensibles_eliminados": 0
        }
        
        for sesion in sesiones:
            if sesion.tiene_datos_sensibles:
                sesion.limpiar_datos_sensibles()
                datos_eliminados["datos_sensibles_eliminados"] += 1
        
        self.db.commit()
        
        return {
            "eliminacion_completa": True,
            "datos_eliminados": datos_eliminados,
            "datos_anonimizados": {
                "usuario_anonimizado": True,
                "email_original": email_original,
                "sesiones_anonimizadas": len(sesiones)
            },
            "motivo": motivo,
            "fecha_eliminacion": datetime.utcnow().isoformat()
        }
    
    async def _verificar_obligaciones_legales(self, usuario_id: str) -> List[str]:
        """Verifica si existen obligaciones legales que impidan la eliminación."""
        
        obligaciones = []
        
        # Verificar si hay investigaciones en curso
        # (Esto sería específico del contexto legal de la organización)
        
        # Verificar retención por motivos contables/fiscales
        # (Específico de la jurisdicción)
        
        # Por ahora, no hay obligaciones legales implementadas
        return obligaciones
    
    async def _aplicar_cambios_consentimiento(self, usuario_id: str, cambios: List[Dict]):
        """Aplica las consecuencias de cambios en consentimientos."""
        
        for cambio in cambios:
            tipo_consentimiento = cambio["tipo"]
            nuevo_valor = cambio["nuevo"]
            
            if tipo_consentimiento == ConsentimientoGDPR.ALMACENAMIENTO_TRANSCRIPCIONES and not nuevo_valor:
                # Si revoca consentimiento para almacenar transcripciones, eliminarlas
                await self._eliminar_transcripciones_usuario(usuario_id)
            
            elif tipo_consentimiento == ConsentimientoGDPR.INTEGRACION_NOTION and not nuevo_valor:
                # Si revoca consentimiento para Notion, eliminar sincronización
                await self._eliminar_sincronizacion_notion(usuario_id)
            
            elif tipo_consentimiento == ConsentimientoGDPR.ANALISIS_IA and not nuevo_valor:
                # Si revoca consentimiento para análisis IA, eliminar análisis
                await self._eliminar_analisis_ia_usuario(usuario_id)
    
    async def _eliminar_transcripciones_usuario(self, usuario_id: str):
        """Elimina transcripciones del usuario."""
        sesiones = self.db.query(ClassSessionSegura).filter(
            ClassSessionSegura.usuario_id == usuario_id
        ).all()
        
        for sesion in sesiones:
            sesion.transcripcion_md = None
        
        self.db.commit()
    
    async def _eliminar_sincronizacion_notion(self, usuario_id: str):
        """Elimina datos de sincronización con Notion."""
        sesiones = self.db.query(ClassSessionSegura).filter(
            ClassSessionSegura.usuario_id == usuario_id
        ).all()
        
        for sesion in sesiones:
            sesion.notion_page_id = None
            sesion.notion_synced_at = None
        
        self.db.commit()
    
    async def _eliminar_analisis_ia_usuario(self, usuario_id: str):
        """Elimina análisis generados por IA."""
        sesiones = self.db.query(ClassSessionSegura).filter(
            ClassSessionSegura.usuario_id == usuario_id
        ).all()
        
        for sesion in sesiones:
            sesion.resumen_md = None
            sesion.ampliacion_md = None
            sesion.glosario_json = None
            sesion.preguntas_json = None
            sesion.tarjetas_json = None
        
        self.db.commit()
    
    # Métodos helper para exportación
    async def _exportar_datos_usuario(self, usuario_id: str, temp_path: Path):
        """Exporta datos básicos del usuario."""
        usuario = self.db.query(Usuario).filter(Usuario.id == usuario_id).first()
        datos = await self._obtener_datos_usuario(usuario)
        
        with open(temp_path / "datos_usuario.json", "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)
    
    async def _exportar_sesiones_clase(self, usuario_id: str, temp_path: Path):
        """Exporta sesiones de clase del usuario."""
        sesiones = await self._obtener_sesiones_usuario(usuario_id, incluir_contenido=True)
        
        with open(temp_path / "sesiones_clase.json", "w", encoding="utf-8") as f:
            json.dump(sesiones, f, indent=2, ensure_ascii=False)
    
    async def _exportar_consentimientos(self, usuario_id: str, temp_path: Path):
        """Exporta consentimientos del usuario."""
        consentimientos = await self._obtener_consentimientos_usuario(usuario_id)
        
        with open(temp_path / "consentimientos.json", "w", encoding="utf-8") as f:
            json.dump(consentimientos, f, indent=2, ensure_ascii=False)
    
    async def _exportar_configuraciones(self, usuario_id: str, temp_path: Path):
        """Exporta configuraciones del usuario."""
        usuario = self.db.query(Usuario).filter(Usuario.id == usuario_id).first()
        configuraciones = await self._obtener_configuraciones_usuario(usuario)
        
        with open(temp_path / "configuraciones.json", "w", encoding="utf-8") as f:
            json.dump(configuraciones, f, indent=2, ensure_ascii=False)
    
    # Métodos helper para datos técnicos
    async def _contar_sesiones_activas(self, usuario_id: str) -> int:
        """Cuenta sesiones activas del usuario."""
        return self.db.query(ClassSessionSegura).filter(
            ClassSessionSegura.usuario_id == usuario_id,
            ClassSessionSegura.estado_pipeline != "done"
        ).count()
    
    async def _calcular_uso_almacenamiento(self, usuario_id: str) -> Dict[str, Any]:
        """Calcula uso de almacenamiento del usuario."""
        # Esto sería específico de la implementación de almacenamiento
        return {
            "total_mb": 0,
            "audio_mb": 0,
            "transcripciones_mb": 0,
            "otros_mb": 0
        }
    
    async def _obtener_estadisticas_procesamiento(self, usuario_id: str) -> Dict[str, Any]:
        """Obtiene estadísticas de procesamiento."""
        sesiones = self.db.query(ClassSessionSegura).filter(
            ClassSessionSegura.usuario_id == usuario_id
        ).all()
        
        return {
            "total_sesiones": len(sesiones),
            "sesiones_completadas": sum(1 for s in sesiones if s.is_completed),
            "tiempo_total_procesamiento": sum(s.tiempo_procesamiento_sec or 0 for s in sesiones),
            "tokens_utilizados_total": sum(s.tokens_utilizados or 0 for s in sesiones)
        }
    
    async def _obtener_configuraciones_tecnicas(self, usuario_id: str) -> Dict[str, Any]:
        """Obtiene configuraciones técnicas del usuario."""
        return {
            "idioma_preferido": "es",
            "calidad_audio": "alta",
            "modelo_ia_preferido": "local"
        }
    
    async def _obtener_historial_consentimientos(self, usuario_id: str) -> List[Dict[str, Any]]:
        """Obtiene historial de cambios de consentimientos."""
        logs = self.db.query(LogAuditoria).filter(
            LogAuditoria.usuario_id == usuario_id,
            LogAuditoria.tipo_evento.in_([
                TipoEventoAuditoria.CONSENTIMIENTO_OTORGADO,
                TipoEventoAuditoria.CONSENTIMIENTO_REVOCADO
            ])
        ).order_by(LogAuditoria.timestamp.desc()).all()
        
        historial = []
        for log in logs:
            historial.append({
                "fecha": log.timestamp.isoformat(),
                "tipo_evento": log.tipo_evento.value,
                "descripcion": log.descripcion,
                "datos_evento": log.datos_evento
            })
        
        return historial
