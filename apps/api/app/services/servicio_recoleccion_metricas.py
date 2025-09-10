# -*- coding: utf-8 -*-
"""
Servicio para recolección automática de métricas del sistema y procesamiento.
"""

from typing import Dict, List, Optional, Any
import psutil
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

try:
    import GPUtil
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

from app.models.sesion_metrica import SesionMetrica
from app.models.metrica_procesamiento import MetricaProcesamiento
from app.models.metrica_calidad import MetricaCalidad
from app.models.metrica_sistema import MetricaSistema
from app.core.logging import logger


class ServicioRecoleccionMetricas:
    """Servicio para recolección automática de métricas del sistema."""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.sesion_actual_id: Optional[uuid.UUID] = None
        logger.info("ServicioRecoleccionMetricas inicializado")
    
    def iniciar_sesion_metrica(
        self, 
        nombre_sesion: str,
        tipo_sesion: str = "procesamiento_clase",
        id_sesion_clase: Optional[uuid.UUID] = None,
        id_profesor: Optional[uuid.UUID] = None
    ) -> uuid.UUID:
        """Inicia una nueva sesión de métricas."""
        try:
            sesion = SesionMetrica(
                nombre_sesion=nombre_sesion,
                tipo_sesion=tipo_sesion,
                id_sesion_clase=id_sesion_clase,
                id_profesor=id_profesor,
                tiempo_inicio=datetime.now(timezone.utc)
            )
            
            self.db.add(sesion)
            self.db.commit()
            self.sesion_actual_id = sesion.session_id
            
            logger.info(f"Sesión de métricas iniciada: {sesion.session_id}")
            return sesion.session_id
            
        except Exception as e:
            logger.error(f"Error al iniciar sesión de métricas: {str(e)}")
            self.db.rollback()
            raise
    
    def registrar_metrica_procesamiento(
        self,
        tipo_metrica: str,
        nombre_componente: str,
        tiempo_inicio: datetime,
        tiempo_fin: datetime,
        puntuacion_calidad: Optional[float] = None,
        puntuacion_confianza: Optional[float] = None,
        tamano_entrada_bytes: Optional[int] = None,
        tamano_salida_bytes: Optional[int] = None,
        metadatos: Optional[Dict] = None,
        detalles_error: Optional[str] = None,
        id_sesion: Optional[uuid.UUID] = None
    ) -> uuid.UUID:
        """Registra una métrica de procesamiento."""
        try:
            id_sesion = id_sesion or self.sesion_actual_id
            
            if not id_sesion:
                raise ValueError("No hay sesión activa para registrar métricas")
            
            # Obtener métricas de sistema actuales
            metricas_sistema = self._obtener_metricas_sistema_actuales()
            
            duracion_ms = int((tiempo_fin - tiempo_inicio).total_seconds() * 1000)
            
            metrica = MetricaProcesamiento(
                id_sesion_metrica=id_sesion,
                tipo_metrica=tipo_metrica,
                nombre_componente=nombre_componente,
                tiempo_inicio=tiempo_inicio,
                tiempo_fin=tiempo_fin,
                duracion_ms=duracion_ms,
                tamano_entrada_bytes=tamano_entrada_bytes,
                tamano_salida_bytes=tamano_salida_bytes,
                puntuacion_calidad=puntuacion_calidad,
                puntuacion_confianza=puntuacion_confianza,
                uso_cpu_porcentaje=metricas_sistema.get("cpu_porcentaje"),
                uso_memoria_mb=metricas_sistema.get("memoria_mb"),
                uso_gpu_porcentaje=metricas_sistema.get("gpu_porcentaje"),
                memoria_gpu_mb=metricas_sistema.get("gpu_memoria_mb"),
                metadatos=metadatos,
                detalles_error=detalles_error
            )
            
            self.db.add(metrica)
            self.db.commit()
            
            # Actualizar contador en sesión
            self._actualizar_contador_metricas(id_sesion)
            
            logger.info(f"Métrica de procesamiento registrada: {metrica.metrica_id}")
            return metrica.metrica_id
            
        except Exception as e:
            logger.error(f"Error al registrar métrica de procesamiento: {str(e)}")
            self.db.rollback()
            raise
    
    def registrar_metrica_calidad(
        self,
        puntuacion_wer: Optional[float] = None,
        puntuacion_der: Optional[float] = None,
        confianza_promedio: Optional[float] = None,
        tasa_validez_json: Optional[float] = None,
        precision_terminos_medicos: Optional[float] = None,
        completitud_contenido: Optional[float] = None,
        cantidad_terminos_extraidos: Optional[float] = None,
        precision_definiciones: Optional[float] = None,
        id_sesion: Optional[uuid.UUID] = None
    ) -> uuid.UUID:
        """Registra métricas de calidad."""
        try:
            id_sesion = id_sesion or self.sesion_actual_id
            
            if not id_sesion:
                raise ValueError("No hay sesión activa para registrar métricas")
            
            metrica = MetricaCalidad(
                id_sesion_metrica=id_sesion,
                puntuacion_wer=puntuacion_wer,
                puntuacion_der=puntuacion_der,
                confianza_promedio=confianza_promedio,
                tasa_validez_json=tasa_validez_json,
                precision_terminos_medicos=precision_terminos_medicos,
                completitud_contenido=completitud_contenido,
                cantidad_terminos_extraidos=cantidad_terminos_extraidos,
                precision_definiciones=precision_definiciones
            )
            
            self.db.add(metrica)
            self.db.commit()
            
            # Verificar alertas de calidad
            alertas = metrica.detectar_alertas_calidad()
            if alertas:
                self._procesar_alertas_calidad(alertas, id_sesion)
            
            logger.info(f"Métrica de calidad registrada: {metrica.metrica_id}")
            return metrica.metrica_id
            
        except Exception as e:
            logger.error(f"Error al registrar métrica de calidad: {str(e)}")
            self.db.rollback()
            raise
    
    def registrar_metrica_sistema_manual(
        self,
        nombre_metrica: str,
        categoria: str,
        valor: float,
        unidad: str,
        componente: Optional[str] = None,
        nodo_servidor: Optional[str] = None,
        etiquetas: Optional[Dict] = None,
        id_sesion: Optional[uuid.UUID] = None
    ) -> uuid.UUID:
        """Registra una métrica de sistema específica."""
        try:
            metrica = MetricaSistema(
                id_sesion_metrica=id_sesion,
                nombre_metrica=nombre_metrica,
                categoria_metrica=categoria,
                valor=valor,
                unidad=unidad,
                componente=componente,
                nodo_servidor=nodo_servidor,
                etiquetas=etiquetas
            )
            
            self.db.add(metrica)
            self.db.commit()
            
            logger.debug(f"Métrica de sistema registrada: {nombre_metrica}={valor}{unidad}")
            return metrica.metrica_id
            
        except Exception as e:
            logger.error(f"Error al registrar métrica de sistema: {str(e)}")
            self.db.rollback()
            raise
    
    def capturar_snapshot_sistema(
        self, 
        componente: str = "sistema_general",
        id_sesion: Optional[uuid.UUID] = None
    ) -> List[uuid.UUID]:
        """Captura un snapshot completo de métricas del sistema."""
        try:
            metricas_ids = []
            timestamp = datetime.now(timezone.utc)
            
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            metrica_id = self.registrar_metrica_sistema_manual(
                "cpu_usage", "sistema", cpu_percent, "percent", 
                componente, etiquetas={"snapshot": True}, id_sesion=id_sesion
            )
            metricas_ids.append(metrica_id)
            
            # Memoria
            memoria = psutil.virtual_memory()
            memoria_mb = memoria.used / (1024 * 1024)
            metrica_id = self.registrar_metrica_sistema_manual(
                "memory_usage", "sistema", memoria_mb, "mb",
                componente, etiquetas={"snapshot": True, "total_mb": memoria.total / (1024 * 1024)}, 
                id_sesion=id_sesion
            )
            metricas_ids.append(metrica_id)
            
            # Disco
            disco = psutil.disk_usage('/')
            disco_percent = (disco.used / disco.total) * 100
            metrica_id = self.registrar_metrica_sistema_manual(
                "disk_usage", "sistema", disco_percent, "percent",
                componente, etiquetas={"snapshot": True}, id_sesion=id_sesion
            )
            metricas_ids.append(metrica_id)
            
            # GPU (si está disponible)
            if GPU_AVAILABLE:
                try:
                    gpus = GPUtil.getGPUs()
                    if gpus:
                        gpu = gpus[0]  # Primera GPU
                        
                        # Uso GPU
                        metrica_id = self.registrar_metrica_sistema_manual(
                            "gpu_usage", "gpu", gpu.load * 100, "percent",
                            "gpu_0", etiquetas={"snapshot": True, "gpu_name": gpu.name}, 
                            id_sesion=id_sesion
                        )
                        metricas_ids.append(metrica_id)
                        
                        # Memoria GPU
                        metrica_id = self.registrar_metrica_sistema_manual(
                            "gpu_memory", "gpu", gpu.memoryUsed, "mb",
                            "gpu_0", etiquetas={"snapshot": True, "total_mb": gpu.memoryTotal}, 
                            id_sesion=id_sesion
                        )
                        metricas_ids.append(metrica_id)
                        
                        # Temperatura GPU
                        metrica_id = self.registrar_metrica_sistema_manual(
                            "gpu_temperature", "gpu", gpu.temperature, "celsius",
                            "gpu_0", etiquetas={"snapshot": True}, id_sesion=id_sesion
                        )
                        metricas_ids.append(metrica_id)
                        
                except Exception as e:
                    logger.warning(f"Error capturando métricas GPU: {str(e)}")
            
            logger.info(f"Snapshot de sistema capturado: {len(metricas_ids)} métricas")
            return metricas_ids
            
        except Exception as e:
            logger.error(f"Error al capturar snapshot del sistema: {str(e)}")
            raise
    
    def completar_sesion(
        self, 
        id_sesion: Optional[uuid.UUID] = None,
        estado: str = "completada"
    ) -> None:
        """Completa una sesión de métricas."""
        try:
            id_sesion = id_sesion or self.sesion_actual_id
            
            if not id_sesion:
                raise ValueError("No hay sesión para completar")
            
            sesion = self.db.query(SesionMetrica).filter(
                SesionMetrica.session_id == id_sesion
            ).first()
            
            if sesion:
                sesion.completar_sesion(estado)
                
                # Actualizar contadores finales
                sesion.total_metricas_recolectadas = self._contar_metricas_sesion(id_sesion)
                
                self.db.commit()
                logger.info(f"Sesión de métricas completada: {id_sesion}")
            
            self.sesion_actual_id = None
            
        except Exception as e:
            logger.error(f"Error al completar sesión de métricas: {str(e)}")
            self.db.rollback()
            raise
    
    def _obtener_metricas_sistema_actuales(self) -> Dict[str, float]:
        """Obtiene métricas actuales del sistema."""
        metricas = {}
        
        try:
            # CPU y memoria
            metricas["cpu_porcentaje"] = psutil.cpu_percent()
            memoria = psutil.virtual_memory()
            metricas["memoria_mb"] = memoria.used / (1024 * 1024)
            
            # GPU (si está disponible)
            if GPU_AVAILABLE:
                try:
                    gpus = GPUtil.getGPUs()
                    if gpus:
                        gpu = gpus[0]  # Primera GPU
                        metricas["gpu_porcentaje"] = gpu.load * 100
                        metricas["gpu_memoria_mb"] = gpu.memoryUsed
                except Exception:
                    pass  # GPU no disponible o error
                    
        except Exception as e:
            logger.warning(f"Error obteniendo métricas del sistema: {str(e)}")
        
        return metricas
    
    def _actualizar_contador_metricas(self, id_sesion: uuid.UUID) -> None:
        """Actualiza el contador de métricas en la sesión."""
        try:
            sesion = self.db.query(SesionMetrica).filter(
                SesionMetrica.session_id == id_sesion
            ).first()
            
            if sesion:
                sesion.total_metricas_recolectadas += 1
                self.db.commit()
                
        except Exception as e:
            logger.warning(f"Error actualizando contador de métricas: {str(e)}")
    
    def _contar_metricas_sesion(self, id_sesion: uuid.UUID) -> int:
        """Cuenta el total de métricas asociadas a una sesión."""
        try:
            total_procesamiento = self.db.query(MetricaProcesamiento).filter(
                MetricaProcesamiento.id_sesion_metrica == id_sesion
            ).count()
            
            total_calidad = self.db.query(MetricaCalidad).filter(
                MetricaCalidad.id_sesion_metrica == id_sesion
            ).count()
            
            total_sistema = self.db.query(MetricaSistema).filter(
                MetricaSistema.id_sesion_metrica == id_sesion
            ).count()
            
            return total_procesamiento + total_calidad + total_sistema
            
        except Exception as e:
            logger.warning(f"Error contando métricas de sesión: {str(e)}")
            return 0
    
    def _procesar_alertas_calidad(self, alertas: List[Dict], id_sesion: uuid.UUID) -> None:
        """Procesa alertas de calidad detectadas."""
        try:
            sesion = self.db.query(SesionMetrica).filter(
                SesionMetrica.session_id == id_sesion
            ).first()
            
            if sesion:
                for alerta in alertas:
                    if alerta["severidad"] == "critica":
                        sesion.contador_alertas_criticas += 1
                    elif alerta["severidad"] == "warning":
                        sesion.contador_alertas_warning += 1
                
                self.db.commit()
                
                # Log de alertas
                for alerta in alertas:
                    logger.warning(f"Alerta de calidad [{alerta['severidad']}]: {alerta['mensaje']}")
                    
        except Exception as e:
            logger.error(f"Error procesando alertas de calidad: {str(e)}")
    
    def obtener_sesion_actual(self) -> Optional[SesionMetrica]:
        """Obtiene la sesión actual de métricas."""
        if self.sesion_actual_id:
            return self.db.query(SesionMetrica).filter(
                SesionMetrica.session_id == self.sesion_actual_id
            ).first()
        return None
