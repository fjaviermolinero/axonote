# -*- coding: utf-8 -*-
"""
Modelo para métricas de sistema e infraestructura.
"""

from sqlalchemy import Column, String, DateTime, Float, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone

from app.models.base import BaseModel


class MetricaSistema(BaseModel):
    """
    Métricas de infraestructura y rendimiento del sistema.
    
    Captura información sobre el estado de la infraestructura,
    recursos del servidor y rendimiento general del sistema.
    """
    __tablename__ = "metricas_sistema"

    # Identificación
    metrica_id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="ID único de la métrica de sistema"
    )
    
    id_sesion_metrica = Column(
        UUID(as_uuid=True), 
        ForeignKey("sesiones_metricas.session_id"),
        nullable=True,  # Puede ser independiente de sesión
        comment="ID de la sesión de métricas asociada (opcional)"
    )
    
    # Temporal
    timestamp = Column(
        DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc),
        comment="Momento exacto de la captura de la métrica"
    )
    
    # Identificación de la Métrica
    nombre_metrica = Column(
        String(100), 
        nullable=False,
        comment="Nombre de la métrica: cpu_usage, memory_usage, gpu_temp, etc."
    )
    
    categoria_metrica = Column(
        String(50), 
        nullable=False,
        comment="Categoría: sistema, base_datos, api, gpu, red"
    )
    
    # Valores
    valor = Column(
        Float, 
        nullable=False,
        comment="Valor numérico de la métrica"
    )
    
    unidad = Column(
        String(20), 
        nullable=False,
        comment="Unidad de medida: percent, mb, ms, count, celsius"
    )
    
    # Contexto
    nodo_servidor = Column(
        String(50),
        nullable=True,
        comment="Identificador del nodo/servidor donde se capturó la métrica"
    )
    
    componente = Column(
        String(100),
        nullable=True,
        comment="Componente específico: api_container, worker_container, postgres, redis"
    )
    
    etiquetas = Column(
        JSON,
        nullable=True,
        comment="Etiquetas adicionales para categorización y filtrado"
    )
    
    # Relaciones
    sesion_metrica = relationship(
        "SesionMetrica", 
        back_populates="metricas_sistema"
    )
    
    def __repr__(self):
        return f"<MetricaSistema(nombre='{self.nombre_metrica}', valor={self.valor}, unidad='{self.unidad}')>"
    
    @property
    def valor_normalizado(self) -> float:
        """Normaliza el valor según la unidad para comparaciones."""
        if self.unidad == "percent":
            return self.valor / 100.0
        elif self.unidad in ["mb", "gb"]:
            return self.valor
        elif self.unidad == "ms":
            return self.valor / 1000.0  # Convertir a segundos
        else:
            return self.valor
    
    @property
    def esta_en_umbral_critico(self) -> bool:
        """Determina si la métrica está en un umbral crítico."""
        umbrales_criticos = {
            "cpu_usage": 90.0,
            "memory_usage": 95.0,
            "gpu_usage": 98.0,
            "gpu_temperature": 85.0,
            "disk_usage": 90.0,
            "response_time": 5000.0,  # 5 segundos
        }
        
        umbral = umbrales_criticos.get(self.nombre_metrica)
        if umbral is not None:
            return self.valor >= umbral
        
        return False
    
    @property
    def esta_en_umbral_warning(self) -> bool:
        """Determina si la métrica está en un umbral de warning."""
        umbrales_warning = {
            "cpu_usage": 75.0,
            "memory_usage": 80.0,
            "gpu_usage": 85.0,
            "gpu_temperature": 75.0,
            "disk_usage": 75.0,
            "response_time": 2000.0,  # 2 segundos
        }
        
        umbral = umbrales_warning.get(self.nombre_metrica)
        if umbral is not None:
            return self.valor >= umbral and not self.esta_en_umbral_critico
        
        return False
    
    def obtener_estado_salud(self) -> str:
        """Retorna el estado de salud basado en la métrica."""
        if self.esta_en_umbral_critico:
            return "critico"
        elif self.esta_en_umbral_warning:
            return "warning"
        else:
            return "saludable"
    
    def obtener_resumen_metrica(self) -> dict:
        """Retorna un resumen de la métrica para dashboard."""
        return {
            "metrica_id": str(self.metrica_id),
            "nombre": self.nombre_metrica,
            "categoria": self.categoria_metrica,
            "valor": self.valor,
            "unidad": self.unidad,
            "valor_normalizado": self.valor_normalizado,
            "estado_salud": self.obtener_estado_salud(),
            "componente": self.componente,
            "nodo": self.nodo_servidor,
            "etiquetas": self.etiquetas or {},
            "timestamp": self.timestamp.isoformat()
        }
    
    def anadir_etiqueta(self, clave: str, valor: str) -> None:
        """Añade una etiqueta a la métrica."""
        if self.etiquetas is None:
            self.etiquetas = {}
        self.etiquetas[clave] = valor
    
    def obtener_etiqueta(self, clave: str, default=None):
        """Obtiene una etiqueta específica."""
        if self.etiquetas:
            return self.etiquetas.get(clave, default)
        return default
    
    @classmethod
    def crear_metrica_cpu(cls, valor: float, nodo: str = None, componente: str = None):
        """Helper para crear una métrica de CPU."""
        return cls(
            nombre_metrica="cpu_usage",
            categoria_metrica="sistema",
            valor=valor,
            unidad="percent",
            nodo_servidor=nodo,
            componente=componente
        )
    
    @classmethod
    def crear_metrica_memoria(cls, valor: float, nodo: str = None, componente: str = None):
        """Helper para crear una métrica de memoria."""
        return cls(
            nombre_metrica="memory_usage",
            categoria_metrica="sistema",
            valor=valor,
            unidad="mb",
            nodo_servidor=nodo,
            componente=componente
        )
    
    @classmethod
    def crear_metrica_gpu(cls, uso: float, memoria: float, temperatura: float = None, nodo: str = None):
        """Helper para crear métricas de GPU."""
        metricas = []
        
        # Uso de GPU
        metricas.append(cls(
            nombre_metrica="gpu_usage",
            categoria_metrica="gpu",
            valor=uso,
            unidad="percent",
            nodo_servidor=nodo,
            componente="gpu"
        ))
        
        # Memoria GPU
        metricas.append(cls(
            nombre_metrica="gpu_memory",
            categoria_metrica="gpu",
            valor=memoria,
            unidad="mb",
            nodo_servidor=nodo,
            componente="gpu"
        ))
        
        # Temperatura GPU (opcional)
        if temperatura is not None:
            metricas.append(cls(
                nombre_metrica="gpu_temperature",
                categoria_metrica="gpu",
                valor=temperatura,
                unidad="celsius",
                nodo_servidor=nodo,
                componente="gpu"
            ))
        
        return metricas
