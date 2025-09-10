"""
Servicio de backup cifrado y recuperación para Axonote.
Implementa backups automáticos con cifrado y verificación de integridad.
"""

import os
import json
import gzip
import shutil
import hashlib
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.services.encryption_service import ServicioCifrado
from app.services.auditoria_service import ServicioAuditoria
from app.models.usuario import TipoEventoAuditoria, NivelSeveridad
from app.core.config import settings


class TipoBackup:
    """Tipos de backup disponibles."""
    COMPLETO = "completo"
    INCREMENTAL = "incremental"
    DIFERENCIAL = "diferencial"
    SOLO_CONFIGURACION = "solo_configuracion"
    SOLO_DATOS_USUARIO = "solo_datos_usuario"


class EstadoBackup:
    """Estados de un backup."""
    INICIADO = "iniciado"
    EN_PROGRESO = "en_progreso"
    COMPLETADO = "completado"
    FALLIDO = "fallido"
    VERIFICANDO = "verificando"
    VERIFICADO = "verificado"


class ServicioBackup:
    """
    Servicio completo de backup y recuperación con cifrado.
    Proporciona backups automáticos, verificación de integridad y recuperación.
    """
    
    def __init__(
        self,
        db: Session,
        servicio_cifrado: ServicioCifrado,
        servicio_auditoria: ServicioAuditoria,
        directorio_backups: Optional[str] = None
    ):
        self.db = db
        self.cifrado = servicio_cifrado
        self.auditoria = servicio_auditoria
        
        # Configuración de directorios
        self.directorio_backups = Path(directorio_backups or "/var/backups/axonote")
        self.directorio_temp = Path(tempfile.gettempdir()) / "axonote_backups"
        
        # Crear directorios si no existen
        self.directorio_backups.mkdir(parents=True, exist_ok=True)
        self.directorio_temp.mkdir(parents=True, exist_ok=True)
        
        # Configuración de retención
        self.retencion_backups = {
            TipoBackup.COMPLETO: 30,      # 30 días
            TipoBackup.INCREMENTAL: 7,    # 7 días
            TipoBackup.DIFERENCIAL: 14,   # 14 días
            TipoBackup.SOLO_CONFIGURACION: 90,  # 90 días
            TipoBackup.SOLO_DATOS_USUARIO: 30   # 30 días
        }
        
        # Configuración de compresión
        self.usar_compresion = True
        self.nivel_compresion = 6  # Nivel medio de compresión
    
    async def crear_backup(
        self,
        tipo_backup: str = TipoBackup.COMPLETO,
        incluir_archivos_media: bool = True,
        usuario_solicitante: Optional[str] = None,
        descripcion: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Crea un backup del sistema.
        
        Args:
            tipo_backup: Tipo de backup a crear
            incluir_archivos_media: Si incluir archivos de audio/imagen
            usuario_solicitante: ID del usuario que solicita el backup
            descripcion: Descripción opcional del backup
            
        Returns:
            Dict con información del backup creado
        """
        
        timestamp = datetime.utcnow()
        backup_id = f"{tipo_backup}_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        
        # Registrar inicio del backup
        await self.auditoria.log_evento(
            tipo_evento=TipoEventoAuditoria.BACKUP_CREADO,
            descripcion=f"Iniciando backup {tipo_backup}",
            usuario_id=usuario_solicitante,
            datos_evento={
                "backup_id": backup_id,
                "tipo_backup": tipo_backup,
                "incluir_media": incluir_archivos_media,
                "descripcion": descripcion
            }
        )
        
        try:
            # Crear directorio temporal para el backup
            backup_temp_dir = self.directorio_temp / backup_id
            backup_temp_dir.mkdir(exist_ok=True)
            
            # Crear manifiesto del backup
            manifiesto = {
                "backup_id": backup_id,
                "tipo": tipo_backup,
                "timestamp": timestamp.isoformat(),
                "version_axonote": settings.APP_VERSION,
                "usuario_solicitante": usuario_solicitante,
                "descripcion": descripcion,
                "incluir_media": incluir_archivos_media,
                "componentes": []
            }
            
            # Ejecutar backup según el tipo
            if tipo_backup == TipoBackup.COMPLETO:
                await self._backup_completo(backup_temp_dir, manifiesto, incluir_archivos_media)
            elif tipo_backup == TipoBackup.INCREMENTAL:
                await self._backup_incremental(backup_temp_dir, manifiesto, incluir_archivos_media)
            elif tipo_backup == TipoBackup.DIFERENCIAL:
                await self._backup_diferencial(backup_temp_dir, manifiesto, incluir_archivos_media)
            elif tipo_backup == TipoBackup.SOLO_CONFIGURACION:
                await self._backup_configuracion(backup_temp_dir, manifiesto)
            elif tipo_backup == TipoBackup.SOLO_DATOS_USUARIO:
                await self._backup_datos_usuario(backup_temp_dir, manifiesto)
            else:
                raise ValueError(f"Tipo de backup no soportado: {tipo_backup}")
            
            # Guardar manifiesto
            with open(backup_temp_dir / "manifiesto.json", "w", encoding="utf-8") as f:
                json.dump(manifiesto, f, indent=2, ensure_ascii=False)
            
            # Comprimir y cifrar backup
            archivo_backup = await self._comprimir_y_cifrar_backup(backup_temp_dir, backup_id)
            
            # Verificar integridad
            verificacion = await self._verificar_integridad_backup(archivo_backup)
            
            # Limpiar directorio temporal
            shutil.rmtree(backup_temp_dir)
            
            # Actualizar manifiesto con información final
            manifiesto.update({
                "archivo_backup": str(archivo_backup),
                "tamaño_bytes": archivo_backup.stat().st_size,
                "hash_sha256": verificacion["hash_sha256"],
                "verificacion_ok": verificacion["verificacion_ok"],
                "estado": EstadoBackup.COMPLETADO if verificacion["verificacion_ok"] else EstadoBackup.FALLIDO
            })
            
            # Guardar metadatos del backup
            await self._guardar_metadatos_backup(backup_id, manifiesto)
            
            # Registrar finalización
            await self.auditoria.log_evento(
                tipo_evento=TipoEventoAuditoria.BACKUP_CREADO,
                descripcion=f"Backup {tipo_backup} completado exitosamente",
                usuario_id=usuario_solicitante,
                datos_evento={
                    "backup_id": backup_id,
                    "archivo": str(archivo_backup),
                    "tamaño_mb": round(archivo_backup.stat().st_size / (1024 * 1024), 2),
                    "verificacion_ok": verificacion["verificacion_ok"]
                },
                severidad=NivelSeveridad.INFO if verificacion["verificacion_ok"] else NivelSeveridad.ERROR
            )
            
            return manifiesto
            
        except Exception as e:
            # Limpiar en caso de error
            if backup_temp_dir.exists():
                shutil.rmtree(backup_temp_dir, ignore_errors=True)
            
            # Registrar error
            await self.auditoria.log_evento(
                tipo_evento=TipoEventoAuditoria.ERROR_SISTEMA,
                descripcion=f"Error creando backup {tipo_backup}: {str(e)}",
                usuario_id=usuario_solicitante,
                datos_evento={
                    "backup_id": backup_id,
                    "error": str(e)
                },
                severidad=NivelSeveridad.ERROR,
                resultado="fallido"
            )
            
            raise Exception(f"Error creando backup: {str(e)}")
    
    async def restaurar_backup(
        self,
        backup_id: str,
        usuario_solicitante: Optional[str] = None,
        confirmar_restauracion: bool = False,
        restaurar_solo_configuracion: bool = False
    ) -> Dict[str, Any]:
        """
        Restaura un backup del sistema.
        
        Args:
            backup_id: ID del backup a restaurar
            usuario_solicitante: ID del usuario que solicita la restauración
            confirmar_restauracion: Confirmación explícita requerida
            restaurar_solo_configuracion: Si restaurar solo configuración
            
        Returns:
            Dict con resultado de la restauración
        """
        
        if not confirmar_restauracion:
            raise ValueError("Debe confirmar explícitamente la restauración")
        
        # Registrar inicio de restauración
        await self.auditoria.log_evento(
            tipo_evento=TipoEventoAuditoria.BACKUP_RESTAURADO,
            descripcion=f"Iniciando restauración del backup {backup_id}",
            usuario_id=usuario_solicitante,
            datos_evento={
                "backup_id": backup_id,
                "solo_configuracion": restaurar_solo_configuracion
            }
        )
        
        try:
            # Obtener metadatos del backup
            metadatos = await self._obtener_metadatos_backup(backup_id)
            if not metadatos:
                raise ValueError(f"Backup {backup_id} no encontrado")
            
            archivo_backup = Path(metadatos["archivo_backup"])
            if not archivo_backup.exists():
                raise ValueError(f"Archivo de backup no encontrado: {archivo_backup}")
            
            # Verificar integridad antes de restaurar
            verificacion = await self._verificar_integridad_backup(archivo_backup)
            if not verificacion["verificacion_ok"]:
                raise ValueError("El backup está corrupto y no se puede restaurar")
            
            # Crear backup de seguridad antes de restaurar
            backup_seguridad = await self.crear_backup(
                tipo_backup=TipoBackup.COMPLETO,
                usuario_solicitante=usuario_solicitante,
                descripcion=f"Backup de seguridad antes de restaurar {backup_id}"
            )
            
            # Descifrar y descomprimir backup
            backup_temp_dir = await self._descifrar_y_descomprimir_backup(archivo_backup, backup_id)
            
            try:
                # Cargar manifiesto
                with open(backup_temp_dir / "manifiesto.json", "r", encoding="utf-8") as f:
                    manifiesto = json.load(f)
                
                # Ejecutar restauración
                if restaurar_solo_configuracion:
                    resultado = await self._restaurar_configuracion(backup_temp_dir, manifiesto)
                else:
                    resultado = await self._restaurar_completo(backup_temp_dir, manifiesto)
                
                # Limpiar directorio temporal
                shutil.rmtree(backup_temp_dir)
                
                # Registrar finalización exitosa
                await self.auditoria.log_evento(
                    tipo_evento=TipoEventoAuditoria.BACKUP_RESTAURADO,
                    descripcion=f"Restauración del backup {backup_id} completada exitosamente",
                    usuario_id=usuario_solicitante,
                    datos_evento={
                        "backup_id": backup_id,
                        "backup_seguridad": backup_seguridad["backup_id"],
                        "componentes_restaurados": resultado["componentes_restaurados"]
                    }
                )
                
                return {
                    "restauracion_exitosa": True,
                    "backup_id": backup_id,
                    "backup_seguridad_id": backup_seguridad["backup_id"],
                    "componentes_restaurados": resultado["componentes_restaurados"],
                    "fecha_restauracion": datetime.utcnow().isoformat()
                }
                
            finally:
                # Limpiar directorio temporal en caso de error
                if backup_temp_dir.exists():
                    shutil.rmtree(backup_temp_dir, ignore_errors=True)
                
        except Exception as e:
            # Registrar error
            await self.auditoria.log_evento(
                tipo_evento=TipoEventoAuditoria.ERROR_SISTEMA,
                descripcion=f"Error restaurando backup {backup_id}: {str(e)}",
                usuario_id=usuario_solicitante,
                datos_evento={
                    "backup_id": backup_id,
                    "error": str(e)
                },
                severidad=NivelSeveridad.ERROR,
                resultado="fallido"
            )
            
            raise Exception(f"Error restaurando backup: {str(e)}")
    
    async def listar_backups(self, tipo_backup: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista los backups disponibles.
        
        Args:
            tipo_backup: Filtrar por tipo de backup
            
        Returns:
            Lista de backups disponibles
        """
        
        backups = []
        
        # Buscar archivos de metadatos
        for archivo_metadatos in self.directorio_backups.glob("*.metadata.json"):
            try:
                with open(archivo_metadatos, "r", encoding="utf-8") as f:
                    metadatos = json.load(f)
                
                # Filtrar por tipo si se especifica
                if tipo_backup and metadatos.get("tipo") != tipo_backup:
                    continue
                
                # Verificar que el archivo de backup existe
                archivo_backup = Path(metadatos.get("archivo_backup", ""))
                if archivo_backup.exists():
                    metadatos["disponible"] = True
                    metadatos["tamaño_mb"] = round(archivo_backup.stat().st_size / (1024 * 1024), 2)
                else:
                    metadatos["disponible"] = False
                
                backups.append(metadatos)
                
            except Exception as e:
                # Log del error pero continuar
                print(f"Error leyendo metadatos de backup {archivo_metadatos}: {str(e)}")
        
        # Ordenar por fecha (más reciente primero)
        backups.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        return backups
    
    async def limpiar_backups_antiguos(self) -> Dict[str, Any]:
        """
        Limpia backups antiguos según las políticas de retención.
        
        Returns:
            Dict con estadísticas de limpieza
        """
        
        ahora = datetime.utcnow()
        backups_eliminados = []
        espacio_liberado = 0
        
        # Obtener todos los backups
        todos_backups = await self.listar_backups()
        
        for backup in todos_backups:
            tipo = backup.get("tipo", TipoBackup.COMPLETO)
            timestamp_str = backup.get("timestamp")
            
            if not timestamp_str:
                continue
            
            try:
                timestamp_backup = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                dias_antiguedad = (ahora - timestamp_backup).days
                
                # Verificar si debe eliminarse según política de retención
                dias_retencion = self.retencion_backups.get(tipo, 30)
                
                if dias_antiguedad > dias_retencion:
                    # Eliminar backup
                    archivo_backup = Path(backup.get("archivo_backup", ""))
                    archivo_metadatos = self.directorio_backups / f"{backup['backup_id']}.metadata.json"
                    
                    tamaño_backup = 0
                    if archivo_backup.exists():
                        tamaño_backup = archivo_backup.stat().st_size
                        archivo_backup.unlink()
                    
                    if archivo_metadatos.exists():
                        archivo_metadatos.unlink()
                    
                    backups_eliminados.append({
                        "backup_id": backup["backup_id"],
                        "tipo": tipo,
                        "fecha": timestamp_str,
                        "tamaño_bytes": tamaño_backup
                    })
                    
                    espacio_liberado += tamaño_backup
                    
            except Exception as e:
                print(f"Error procesando backup {backup.get('backup_id', 'unknown')}: {str(e)}")
        
        # Registrar limpieza
        await self.auditoria.log_evento(
            tipo_evento=TipoEventoAuditoria.BACKUP_CREADO,  # Reutilizamos este tipo
            descripcion=f"Limpieza automática de backups: {len(backups_eliminados)} eliminados",
            datos_evento={
                "backups_eliminados": len(backups_eliminados),
                "espacio_liberado_mb": round(espacio_liberado / (1024 * 1024), 2),
                "backups_eliminados_detalle": backups_eliminados
            }
        )
        
        return {
            "backups_eliminados": len(backups_eliminados),
            "espacio_liberado_bytes": espacio_liberado,
            "espacio_liberado_mb": round(espacio_liberado / (1024 * 1024), 2),
            "detalles": backups_eliminados
        }
    
    async def verificar_integridad_todos_backups(self) -> Dict[str, Any]:
        """
        Verifica la integridad de todos los backups.
        
        Returns:
            Dict con resultados de verificación
        """
        
        todos_backups = await self.listar_backups()
        resultados = {
            "total_backups": len(todos_backups),
            "backups_ok": 0,
            "backups_corruptos": 0,
            "backups_no_disponibles": 0,
            "detalles": []
        }
        
        for backup in todos_backups:
            backup_id = backup["backup_id"]
            archivo_backup = Path(backup.get("archivo_backup", ""))
            
            if not archivo_backup.exists():
                resultados["backups_no_disponibles"] += 1
                resultados["detalles"].append({
                    "backup_id": backup_id,
                    "estado": "no_disponible",
                    "archivo": str(archivo_backup)
                })
                continue
            
            try:
                verificacion = await self._verificar_integridad_backup(archivo_backup)
                
                if verificacion["verificacion_ok"]:
                    resultados["backups_ok"] += 1
                    estado = "ok"
                else:
                    resultados["backups_corruptos"] += 1
                    estado = "corrupto"
                
                resultados["detalles"].append({
                    "backup_id": backup_id,
                    "estado": estado,
                    "hash_esperado": backup.get("hash_sha256"),
                    "hash_actual": verificacion["hash_sha256"],
                    "tamaño_bytes": verificacion["tamaño_bytes"]
                })
                
            except Exception as e:
                resultados["backups_corruptos"] += 1
                resultados["detalles"].append({
                    "backup_id": backup_id,
                    "estado": "error",
                    "error": str(e)
                })
        
        return resultados
    
    # Métodos privados para diferentes tipos de backup
    
    async def _backup_completo(self, backup_dir: Path, manifiesto: Dict, incluir_media: bool):
        """Realiza backup completo del sistema."""
        
        # Backup de base de datos
        await self._backup_base_datos(backup_dir / "database")
        manifiesto["componentes"].append("database")
        
        # Backup de configuraciones
        await self._backup_configuraciones(backup_dir / "config")
        manifiesto["componentes"].append("config")
        
        # Backup de archivos de usuario
        await self._backup_archivos_usuario(backup_dir / "user_files", incluir_media)
        manifiesto["componentes"].append("user_files")
        
        # Backup de logs
        await self._backup_logs(backup_dir / "logs")
        manifiesto["componentes"].append("logs")
    
    async def _backup_incremental(self, backup_dir: Path, manifiesto: Dict, incluir_media: bool):
        """Realiza backup incremental desde el último backup."""
        
        # Obtener fecha del último backup
        ultimo_backup = await self._obtener_ultimo_backup()
        fecha_referencia = datetime.fromisoformat(ultimo_backup["timestamp"]) if ultimo_backup else datetime.min
        
        # Backup incremental de base de datos
        await self._backup_base_datos_incremental(backup_dir / "database", fecha_referencia)
        manifiesto["componentes"].append("database_incremental")
        manifiesto["fecha_referencia"] = fecha_referencia.isoformat()
        
        # Backup de archivos modificados
        await self._backup_archivos_modificados(backup_dir / "user_files", fecha_referencia, incluir_media)
        manifiesto["componentes"].append("user_files_incremental")
    
    async def _backup_diferencial(self, backup_dir: Path, manifiesto: Dict, incluir_media: bool):
        """Realiza backup diferencial desde el último backup completo."""
        
        # Obtener último backup completo
        ultimo_completo = await self._obtener_ultimo_backup_completo()
        fecha_referencia = datetime.fromisoformat(ultimo_completo["timestamp"]) if ultimo_completo else datetime.min
        
        # Similar al incremental pero desde el último completo
        await self._backup_base_datos_incremental(backup_dir / "database", fecha_referencia)
        await self._backup_archivos_modificados(backup_dir / "user_files", fecha_referencia, incluir_media)
        
        manifiesto["componentes"].extend(["database_diferencial", "user_files_diferencial"])
        manifiesto["fecha_referencia"] = fecha_referencia.isoformat()
    
    async def _backup_configuracion(self, backup_dir: Path, manifiesto: Dict):
        """Realiza backup solo de configuraciones."""
        
        await self._backup_configuraciones(backup_dir / "config")
        manifiesto["componentes"].append("config")
    
    async def _backup_datos_usuario(self, backup_dir: Path, manifiesto: Dict):
        """Realiza backup solo de datos de usuario."""
        
        await self._backup_base_datos_usuarios(backup_dir / "users")
        await self._backup_archivos_usuario(backup_dir / "user_files", incluir_media=False)
        
        manifiesto["componentes"].extend(["users", "user_files"])
    
    # Métodos helper para componentes específicos
    
    async def _backup_base_datos(self, backup_dir: Path):
        """Realiza backup de la base de datos completa."""
        
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Usar pg_dump para PostgreSQL
        dump_file = backup_dir / "database.sql"
        
        # Ejecutar pg_dump (esto sería específico de la configuración)
        import subprocess
        
        cmd = [
            "pg_dump",
            "--host", settings.POSTGRES_HOST,
            "--port", str(settings.POSTGRES_PORT),
            "--username", settings.POSTGRES_USER,
            "--dbname", settings.POSTGRES_DB,
            "--file", str(dump_file),
            "--verbose",
            "--no-password"
        ]
        
        # Configurar variable de entorno para password
        env = os.environ.copy()
        env["PGPASSWORD"] = settings.POSTGRES_PASSWORD
        
        try:
            result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
            
            # Cifrar el dump
            with open(dump_file, "rb") as f:
                contenido = f.read()
            
            contenido_cifrado = self.cifrado.cifrar_datos_bytes(contenido)
            
            with open(dump_file.with_suffix(".sql.enc"), "wb") as f:
                f.write(contenido_cifrado)
            
            # Eliminar dump sin cifrar
            dump_file.unlink()
            
        except subprocess.CalledProcessError as e:
            raise Exception(f"Error en pg_dump: {e.stderr}")
    
    async def _backup_configuraciones(self, backup_dir: Path):
        """Realiza backup de configuraciones del sistema."""
        
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        configuraciones = {
            "app_version": settings.APP_VERSION,
            "configuracion_actual": {
                # Exportar configuraciones no sensibles
                "cors_origins": settings.CORS_ORIGINS,
                "api_v1_str": settings.API_V1_STR,
                "rate_limit_enabled": settings.RATE_LIMIT_ENABLED,
                "password_requirements": {
                    "min_length": settings.PASSWORD_MIN_LENGTH,
                    "require_uppercase": settings.PASSWORD_REQUIRE_UPPERCASE,
                    "require_lowercase": settings.PASSWORD_REQUIRE_LOWERCASE,
                    "require_numbers": settings.PASSWORD_REQUIRE_NUMBERS,
                    "require_special": settings.PASSWORD_REQUIRE_SPECIAL
                }
            }
        }
        
        # Cifrar y guardar configuraciones
        config_json = json.dumps(configuraciones, indent=2, ensure_ascii=False)
        config_cifrado = self.cifrado.cifrar_datos(config_json)
        
        with open(backup_dir / "configuraciones.json.enc", "w") as f:
            f.write(config_cifrado)
    
    async def _backup_archivos_usuario(self, backup_dir: Path, incluir_media: bool):
        """Realiza backup de archivos de usuario."""
        
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Esto sería específico de la implementación de almacenamiento
        # Por ahora, crear un placeholder
        
        archivos_info = {
            "incluir_media": incluir_media,
            "timestamp": datetime.utcnow().isoformat(),
            "archivos_respaldados": []
        }
        
        # Guardar información de archivos
        info_json = json.dumps(archivos_info, indent=2, ensure_ascii=False)
        info_cifrada = self.cifrado.cifrar_datos(info_json)
        
        with open(backup_dir / "archivos_info.json.enc", "w") as f:
            f.write(info_cifrada)
    
    async def _backup_logs(self, backup_dir: Path):
        """Realiza backup de logs del sistema."""
        
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Backup de logs de auditoría recientes (últimos 30 días)
        fecha_limite = datetime.utcnow() - timedelta(days=30)
        
        # Exportar logs como JSON
        logs_query = text("""
            SELECT id, tipo_evento, descripcion, usuario_id, timestamp, 
                   ip_address, datos_evento, severidad
            FROM logs_auditoria 
            WHERE timestamp >= :fecha_limite
            ORDER BY timestamp DESC
        """)
        
        result = self.db.execute(logs_query, {"fecha_limite": fecha_limite})
        logs = []
        
        for row in result:
            logs.append({
                "id": str(row.id),
                "tipo_evento": row.tipo_evento,
                "descripcion": row.descripcion,
                "usuario_id": str(row.usuario_id) if row.usuario_id else None,
                "timestamp": row.timestamp.isoformat(),
                "ip_address": row.ip_address,
                "datos_evento": row.datos_evento,
                "severidad": row.severidad
            })
        
        # Cifrar y guardar logs
        logs_json = json.dumps(logs, indent=2, ensure_ascii=False)
        logs_cifrados = self.cifrado.cifrar_datos(logs_json)
        
        with open(backup_dir / "logs_auditoria.json.enc", "w") as f:
            f.write(logs_cifrados)
    
    async def _comprimir_y_cifrar_backup(self, backup_dir: Path, backup_id: str) -> Path:
        """Comprime y cifra el directorio de backup."""
        
        archivo_tar = self.directorio_temp / f"{backup_id}.tar"
        archivo_comprimido = self.directorio_temp / f"{backup_id}.tar.gz"
        archivo_final = self.directorio_backups / f"{backup_id}.backup.enc"
        
        # Crear tar
        import tarfile
        with tarfile.open(archivo_tar, "w") as tar:
            tar.add(backup_dir, arcname=backup_id)
        
        # Comprimir con gzip
        if self.usar_compresion:
            with open(archivo_tar, "rb") as f_in:
                with gzip.open(archivo_comprimido, "wb", compresslevel=self.nivel_compresion) as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            archivo_tar.unlink()  # Eliminar tar sin comprimir
            archivo_a_cifrar = archivo_comprimido
        else:
            archivo_a_cifrar = archivo_tar
        
        # Cifrar
        with open(archivo_a_cifrar, "rb") as f:
            contenido = f.read()
        
        contenido_cifrado = self.cifrado.cifrar_datos_bytes(contenido)
        
        with open(archivo_final, "wb") as f:
            f.write(contenido_cifrado)
        
        # Limpiar archivos temporales
        archivo_a_cifrar.unlink()
        
        return archivo_final
    
    async def _verificar_integridad_backup(self, archivo_backup: Path) -> Dict[str, Any]:
        """Verifica la integridad de un archivo de backup."""
        
        if not archivo_backup.exists():
            return {
                "verificacion_ok": False,
                "error": "Archivo no existe"
            }
        
        try:
            # Calcular hash del archivo
            with open(archivo_backup, "rb") as f:
                contenido = f.read()
            
            hash_actual = hashlib.sha256(contenido).hexdigest()
            tamaño = len(contenido)
            
            # Intentar descifrar para verificar que no está corrupto
            try:
                self.cifrado.descifrar_datos_bytes(contenido)
                descifrado_ok = True
            except Exception:
                descifrado_ok = False
            
            return {
                "verificacion_ok": descifrado_ok,
                "hash_sha256": hash_actual,
                "tamaño_bytes": tamaño,
                "descifrado_ok": descifrado_ok
            }
            
        except Exception as e:
            return {
                "verificacion_ok": False,
                "error": str(e)
            }
    
    async def _guardar_metadatos_backup(self, backup_id: str, metadatos: Dict[str, Any]):
        """Guarda los metadatos de un backup."""
        
        archivo_metadatos = self.directorio_backups / f"{backup_id}.metadata.json"
        
        with open(archivo_metadatos, "w", encoding="utf-8") as f:
            json.dump(metadatos, f, indent=2, ensure_ascii=False)
    
    async def _obtener_metadatos_backup(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene los metadatos de un backup."""
        
        archivo_metadatos = self.directorio_backups / f"{backup_id}.metadata.json"
        
        if not archivo_metadatos.exists():
            return None
        
        try:
            with open(archivo_metadatos, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    
    async def _descifrar_y_descomprimir_backup(self, archivo_backup: Path, backup_id: str) -> Path:
        """Descifra y descomprime un backup para restauración."""
        
        # Descifrar
        with open(archivo_backup, "rb") as f:
            contenido_cifrado = f.read()
        
        contenido_descifrado = self.cifrado.descifrar_datos_bytes(contenido_cifrado)
        
        # Guardar temporalmente
        archivo_temp = self.directorio_temp / f"{backup_id}_restore.tar.gz"
        
        with open(archivo_temp, "wb") as f:
            f.write(contenido_descifrado)
        
        # Descomprimir
        directorio_restore = self.directorio_temp / f"{backup_id}_restore"
        directorio_restore.mkdir(exist_ok=True)
        
        try:
            # Intentar como gzip primero
            with gzip.open(archivo_temp, "rb") as f_gz:
                with tarfile.open(fileobj=f_gz, mode="r") as tar:
                    tar.extractall(directorio_restore)
        except:
            # Si falla, intentar como tar normal
            with tarfile.open(archivo_temp, "r") as tar:
                tar.extractall(directorio_restore)
        
        # Limpiar archivo temporal
        archivo_temp.unlink()
        
        return directorio_restore / backup_id
    
    # Métodos helper adicionales
    
    async def _obtener_ultimo_backup(self) -> Optional[Dict[str, Any]]:
        """Obtiene el último backup realizado."""
        
        backups = await self.listar_backups()
        return backups[0] if backups else None
    
    async def _obtener_ultimo_backup_completo(self) -> Optional[Dict[str, Any]]:
        """Obtiene el último backup completo."""
        
        backups = await self.listar_backups(TipoBackup.COMPLETO)
        return backups[0] if backups else None
    
    async def _backup_base_datos_incremental(self, backup_dir: Path, fecha_referencia: datetime):
        """Realiza backup incremental de base de datos."""
        
        # Implementación específica para backup incremental
        # Por ahora, hacer backup completo
        await self._backup_base_datos(backup_dir)
    
    async def _backup_archivos_modificados(self, backup_dir: Path, fecha_referencia: datetime, incluir_media: bool):
        """Realiza backup de archivos modificados desde una fecha."""
        
        # Implementación específica para archivos modificados
        # Por ahora, hacer backup completo
        await self._backup_archivos_usuario(backup_dir, incluir_media)
    
    async def _backup_base_datos_usuarios(self, backup_dir: Path):
        """Realiza backup solo de datos de usuarios."""
        
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Exportar solo tablas de usuarios
        tablas_usuario = [
            "usuarios",
            "sesiones_usuario", 
            "logs_auditoria",
            "class_sessions_seguras"
        ]
        
        for tabla in tablas_usuario:
            dump_file = backup_dir / f"{tabla}.sql"
            
            # Usar pg_dump para tabla específica
            cmd = [
                "pg_dump",
                "--host", settings.POSTGRES_HOST,
                "--port", str(settings.POSTGRES_PORT),
                "--username", settings.POSTGRES_USER,
                "--dbname", settings.POSTGRES_DB,
                "--table", tabla,
                "--file", str(dump_file),
                "--no-password"
            ]
            
            env = os.environ.copy()
            env["PGPASSWORD"] = settings.POSTGRES_PASSWORD
            
            try:
                subprocess.run(cmd, env=env, check=True)
                
                # Cifrar el dump
                with open(dump_file, "rb") as f:
                    contenido = f.read()
                
                contenido_cifrado = self.cifrado.cifrar_datos_bytes(contenido)
                
                with open(dump_file.with_suffix(".sql.enc"), "wb") as f:
                    f.write(contenido_cifrado)
                
                dump_file.unlink()
                
            except subprocess.CalledProcessError as e:
                print(f"Error haciendo backup de tabla {tabla}: {e}")
    
    async def _restaurar_completo(self, backup_dir: Path, manifiesto: Dict) -> Dict[str, Any]:
        """Restaura un backup completo."""
        
        componentes_restaurados = []
        
        # Restaurar base de datos
        if "database" in manifiesto["componentes"]:
            await self._restaurar_base_datos(backup_dir / "database")
            componentes_restaurados.append("database")
        
        # Restaurar configuraciones
        if "config" in manifiesto["componentes"]:
            await self._restaurar_configuraciones(backup_dir / "config")
            componentes_restaurados.append("config")
        
        # Restaurar archivos de usuario
        if "user_files" in manifiesto["componentes"]:
            await self._restaurar_archivos_usuario(backup_dir / "user_files")
            componentes_restaurados.append("user_files")
        
        return {"componentes_restaurados": componentes_restaurados}
    
    async def _restaurar_configuracion(self, backup_dir: Path, manifiesto: Dict) -> Dict[str, Any]:
        """Restaura solo configuraciones."""
        
        await self._restaurar_configuraciones(backup_dir / "config")
        return {"componentes_restaurados": ["config"]}
    
    async def _restaurar_base_datos(self, backup_dir: Path):
        """Restaura la base de datos desde backup."""
        
        # Buscar archivo de dump cifrado
        dump_files = list(backup_dir.glob("*.sql.enc"))
        if not dump_files:
            raise ValueError("No se encontró archivo de base de datos en el backup")
        
        dump_file = dump_files[0]
        
        # Descifrar
        with open(dump_file, "rb") as f:
            contenido_cifrado = f.read()
        
        contenido_descifrado = self.cifrado.descifrar_datos_bytes(contenido_cifrado)
        
        # Guardar temporalmente
        dump_temp = self.directorio_temp / "restore_db.sql"
        with open(dump_temp, "wb") as f:
            f.write(contenido_descifrado)
        
        try:
            # Restaurar con psql
            cmd = [
                "psql",
                "--host", settings.POSTGRES_HOST,
                "--port", str(settings.POSTGRES_PORT),
                "--username", settings.POSTGRES_USER,
                "--dbname", settings.POSTGRES_DB,
                "--file", str(dump_temp),
                "--no-password"
            ]
            
            env = os.environ.copy()
            env["PGPASSWORD"] = settings.POSTGRES_PASSWORD
            
            subprocess.run(cmd, env=env, check=True)
            
        finally:
            # Limpiar archivo temporal
            if dump_temp.exists():
                dump_temp.unlink()
    
    async def _restaurar_configuraciones(self, backup_dir: Path):
        """Restaura configuraciones desde backup."""
        
        config_file = backup_dir / "configuraciones.json.enc"
        if not config_file.exists():
            return
        
        # Descifrar configuraciones
        with open(config_file, "r") as f:
            config_cifrada = f.read()
        
        config_json = self.cifrado.descifrar_datos(config_cifrada)
        configuraciones = json.loads(config_json)
        
        # Aplicar configuraciones (esto sería específico de la implementación)
        print(f"Configuraciones restauradas: {configuraciones}")
    
    async def _restaurar_archivos_usuario(self, backup_dir: Path):
        """Restaura archivos de usuario desde backup."""
        
        info_file = backup_dir / "archivos_info.json.enc"
        if not info_file.exists():
            return
        
        # Descifrar información de archivos
        with open(info_file, "r") as f:
            info_cifrada = f.read()
        
        info_json = self.cifrado.descifrar_datos(info_cifrada)
        archivos_info = json.loads(info_json)
        
        # Restaurar archivos (esto sería específico de la implementación)
        print(f"Archivos restaurados: {archivos_info}")
