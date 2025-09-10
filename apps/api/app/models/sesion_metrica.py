# -*- coding: utf-8 -*-
"""
Modelo para sesiones de métricas - agrupa métricas relacionadas temporalmente.
"""

from sqlalchemy import Column, String, DateTime, Boolean, Integer, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime, timezone

from app.models.base import BaseModel


class SesionMetrica(BaseModel):
    """
    Sesión de métricas que agrupa todas las métricas generadas durante
    el procesamiento de una clase o período específico.
    
    Permite rastrear la evolución completa del pipeline para análisis
    y optimización del rendimiento.
    """
    __tablename__ = "sesiones_metricas"

    # Identificación
    session_id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        comment="ID único de la sesión de métricas"
    )
    
    # Metadatos de Sesión
    nombre_sesion = Column(
        String(255), 
        nullable=False,
        comment="Nombre descriptivo de la sesión (ej: 'Clase Cardiología 2024-01-15')"
    )
    
    tipo_sesion = Column(
        String(50), 
        nullable=False, 
        default="procesamiento_clase",
        comment="Tipo de sesión: procesamiento_clase, monitoreo_sistema, auditoria_calidad"
    )
    
    # Temporal
    tiempo_inicio = Column(
        DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc),
        comment="Inicio de la sesión de métricas"
    )
    
    tiempo_fin = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Fin de la sesión de métricas"
    )
    
    duracion_segundos = Column(
        Integer,
        nullable=True,
        comment="Duración total de la sesión en segundos"
    )
    
    # Estado
    estado = Column(
        String(20), 
        nullable=False, 
        default="activa",
        comment="Estado: activa, completada, fallida, cancelada"
    )
    
    es_activa = Column(
        Boolean, 
        nullable=False, 
        default=True,
        comment="Si la sesión está activa para recibir nuevas métricas"
    )
    
    # Contexto de Negocio
    id_sesion_clase = Column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID de la sesión de clase asociada (si aplica)"
    )
    
    id_profesor = Column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID del profesor asociado (si aplica)"
    )
    
    # Resumen de Métricas
    total_metricas_recolectadas = Column(
        Integer, 
        nullable=False, 
        default=0,
        comment="Total de métricas recolectadas en esta sesión"
    )
    
    contador_alertas_criticas = Column(
        Integer, 
        nullable=False, 
        default=0,
        comment="Número de alertas críticas generadas"
    )
    
    contador_alertas_warning = Column(
        Integer, 
        nullable=False, 
        default=0,
        comment="Número de alertas de warning generadas"
    )
    
    # Metadatos Adicionales
    etiquetas = Column(
        JSON,
        nullable=True,
        comment="Tags adicionales para categorización: ['cardiologia', 'italiano', 'alta_calidad']"
    )
    
    datos_contexto = Column(
        JSON,
        nullable=True,
        comment="Datos de contexto adicionales específicos de la sesión"
    )
    
    notas = Column(
        Text,
        nullable=True,
        comment="Notas adicionales sobre la sesión"
    )
    
    # Relaciones
    metricas_procesamiento = relationship(
        "MetricaProcesamiento", 
        back_populates="sesion_metrica",
        cascade="all, delete-orphan"
    )
    
    metricas_calidad = relationship(
        "MetricaCalidad", 
        back_populates="sesion_metrica",
        cascade="all, delete-orphan"
    )
    
    metricas_sistema = relationship(
        "MetricaSistema", 
        back_populates="sesion_metrica",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self):
        return f"<SesionMetrica(id={self.session_id}, nombre='{self.nombre_sesion}', estado='{self.estado}')>"
    
    @property
    def esta_completada(self) -> bool:
        """Indica si la sesión ha terminado."""
        return self.estado in ["completada", "fallida", "cancelada"]
    
    @property
    def duracion_total(self) -> int:
        """Duración total en segundos, calculada si tiempo_fin está disponible."""
        if self.tiempo_fin and self.tiempo_inicio:
            return int((self.tiempo_fin - self.tiempo_inicio).total_seconds())
        return self.duracion_segundos or 0
    
    def completar_sesion(self, estado: str = "completada") -> None:
        """
        Completa la sesión de métricas.
        
        Args:
            estado: Estado final ('completada', 'fallida', 'cancelada')
        """
        self.tiempo_fin = datetime.now(timezone.utc)
        self.duracion_segundos = self.duracion_total
        self.estado = estado
        self.es_activa = False
    
    def anadir_etiqueta(self, etiqueta: str) -> None:
        """Añade una etiqueta a la sesión."""
        if self.etiquetas is None:
            self.etiquetas = []
        if etiqueta not in self.etiquetas:
            self.etiquetas.append(etiqueta)
    
    def obtener_resumen(self) -> dict:
        """Retorna un resumen de la sesión para dashboard."""
        return {
            "session_id": str(self.session_id),
            "nombre": self.nombre_sesion,
            "tipo": self.tipo_sesion,
            "estado": self.estado,
            "duracion": self.duracion_total,
            "cantidad_metricas": self.total_metricas_recolectadas,
            "alertas_criticas": self.contador_alertas_criticas,
            "alertas_warning": self.contador_alertas_warning,
            "etiquetas": self.etiquetas or [],
            "tiempo_inicio": self.tiempo_inicio.isoformat() if self.tiempo_inicio else None,
            "tiempo_fin": self.tiempo_fin.isoformat() if self.tiempo_fin else None
        }
