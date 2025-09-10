"""
Modelo MicroMemoCollection - Colección de micro-memos.
Representa una colección organizada de micro-memos para estudio estructurado.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, 
    ForeignKey, JSON, DateTime, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from app.models.micro_memo import micro_memo_collection_association


class TipoColeccion(str, Enum):
    """Tipos de colecciones de micro-memos."""
    AUTO = "auto"                      # Generada automáticamente
    CUSTOM = "custom"                  # Creada manualmente
    CLASS_BASED = "class_based"        # Basada en una clase específica
    SPECIALTY_BASED = "specialty_based" # Basada en especialidad médica
    EXAM_PREP = "exam_prep"            # Preparación para examen
    REVIEW_SESSION = "review_session"   # Sesión de repaso
    SPACED_REPETITION = "spaced_repetition" # Repetición espaciada
    DAILY_PRACTICE = "daily_practice"   # Práctica diaria
    WEAKNESS_FOCUS = "weakness_focus"   # Enfoque en debilidades


class EstadoColeccion(str, Enum):
    """Estados de una colección."""
    DRAFT = "draft"                    # Borrador
    ACTIVE = "active"                  # Activa para estudio
    COMPLETED = "completed"            # Completada
    PAUSED = "paused"                  # Pausada temporalmente
    ARCHIVED = "archived"              # Archivada
    NEEDS_UPDATE = "needs_update"      # Necesita actualización


class ModoEstudio(str, Enum):
    """Modos de estudio disponibles."""
    SEQUENTIAL = "sequential"          # Orden secuencial
    RANDOM = "random"                 # Orden aleatorio
    PRIORITY_BASED = "priority_based" # Basado en prioridad
    DIFFICULTY_ASC = "difficulty_asc" # Dificultad ascendente
    DIFFICULTY_DESC = "difficulty_desc" # Dificultad descendente
    SPACED_REPETITION = "spaced_repetition" # Repetición espaciada
    ADAPTIVE = "adaptive"             # Adaptativo basado en performance


class MicroMemoCollection(BaseModel):
    """
    Colección organizada de micro-memos para estudio estructurado.
    
    Permite agrupar micro-memos por criterios específicos y configurar
    estrategias de estudio personalizadas.
    """
    
    __tablename__ = "micro_memo_collections"
    
    # ==============================================
    # INFORMACIÓN BÁSICA
    # ==============================================
    
    # Nombre de la colección
    name = Column(String(300), nullable=False, index=True)
    
    # Descripción detallada
    description = Column(Text, nullable=True)
    
    # Tipo de colección
    collection_type = Column(String(50), nullable=False, default=TipoColeccion.CUSTOM)
    
    # Estado actual
    status = Column(String(30), nullable=False, default=EstadoColeccion.DRAFT)
    
    # Es pública (futuro - para compartir colecciones)
    is_public = Column(Boolean, nullable=False, default=False)
    
    # Creador de la colección (futuro)
    created_by = Column(String(100), nullable=True)
    
    # ==============================================
    # CRITERIOS DE SELECCIÓN AUTOMÁTICA
    # ==============================================
    
    # Criterios de inclusión automática (JSON)
    auto_include_criteria = Column(JSON, nullable=True)
    
    # Tags incluidos en la colección
    tags_included = Column(JSON, nullable=True, default=list)
    
    # Tags excluidos de la colección
    tags_excluded = Column(JSON, nullable=True, default=list)
    
    # Rango de dificultad permitido
    difficulty_range = Column(JSON, nullable=True)  # {"min": "easy", "max": "hard"}
    
    # Filtro por especialidad médica
    specialty_filter = Column(String(100), nullable=True)
    
    # Filtro por clases específicas (array de UUIDs)
    class_sessions_filter = Column(JSON, nullable=True, default=list)
    
    # Mínima puntuación de calidad requerida
    min_quality_score = Column(Float, nullable=True, default=0.7)
    
    # Solo incluir memos validados
    only_validated = Column(Boolean, nullable=False, default=False)
    
    # ==============================================
    # CONFIGURACIÓN DE ESTUDIO
    # ==============================================
    
    # Modo de estudio por defecto
    study_mode = Column(String(30), nullable=False, default=ModoEstudio.SEQUENTIAL)
    
    # Máximo de micro-memos por sesión
    max_memos_per_session = Column(Integer, nullable=False, default=20)
    
    # Tiempo máximo por sesión (minutos)
    max_session_time = Column(Integer, nullable=True, default=30)
    
    # Habilitar repetición espaciada
    enable_spaced_repetition = Column(Boolean, nullable=False, default=True)
    
    # Intervalo mínimo entre revisiones (horas)
    min_review_interval_hours = Column(Integer, nullable=False, default=4)
    
    # Reordenar automáticamente por performance
    auto_reorder_by_performance = Column(Boolean, nullable=False, default=True)
    
    # Incluir nuevos memos automáticamente
    auto_include_new_memos = Column(Boolean, nullable=False, default=False)
    
    # ==============================================
    # MÉTRICAS Y ESTADÍSTICAS
    # ==============================================
    
    # Número total de micro-memos
    total_memos = Column(Integer, nullable=False, default=0)
    
    # Número de memos completados al menos una vez
    memos_studied = Column(Integer, nullable=False, default=0)
    
    # Número de memos dominados (success_rate > 0.8)
    memos_mastered = Column(Integer, nullable=False, default=0)
    
    # Tasa de completitud (0-1)
    completion_rate = Column(Float, nullable=False, default=0.0)
    
    # Precisión promedio de la colección (0-1)
    avg_accuracy = Column(Float, nullable=False, default=0.0)
    
    # Tiempo promedio por memo (segundos)
    avg_time_per_memo = Column(Float, nullable=True)
    
    # Tiempo total de estudio acumulado (minutos)
    total_study_time = Column(Integer, nullable=False, default=0)
    
    # Distribución por dificultad (JSON)
    difficulty_distribution = Column(JSON, nullable=True, default=dict)
    
    # Distribución por especialidad (JSON)
    specialty_distribution = Column(JSON, nullable=True, default=dict)
    
    # ==============================================
    # TRACKING DE PROGRESO
    # ==============================================
    
    # Última fecha de estudio
    last_studied = Column(DateTime, nullable=True)
    
    # Próxima sesión recomendada
    next_session_recommended = Column(DateTime, nullable=True)
    
    # Racha actual de días estudiando
    current_streak = Column(Integer, nullable=False, default=0)
    
    # Racha máxima alcanzada
    best_streak = Column(Integer, nullable=False, default=0)
    
    # Número total de sesiones de estudio
    total_sessions = Column(Integer, nullable=False, default=0)
    
    # Promedio de memos por sesión
    avg_memos_per_session = Column(Float, nullable=True)
    
    # ==============================================
    # CONFIGURACIÓN AVANZADA
    # ==============================================
    
    # Algoritmo de espaciado personalizado (JSON)
    custom_spacing_algorithm = Column(JSON, nullable=True)
    
    # Configuración de notificaciones
    notification_settings = Column(JSON, nullable=True, default=dict)
    
    # Objetivos de estudio (JSON)
    study_goals = Column(JSON, nullable=True, default=dict)
    
    # Configuración de gamificación
    gamification_settings = Column(JSON, nullable=True, default=dict)
    
    # ==============================================
    # METADATOS
    # ==============================================
    
    # Fecha de última actualización automática
    last_auto_update = Column(DateTime, nullable=True)
    
    # Versión de la colección
    version = Column(Integer, nullable=False, default=1)
    
    # Metadatos adicionales flexibles
    metadata = Column(JSON, nullable=True, default=dict)
    
    # Notas del creador
    creator_notes = Column(Text, nullable=True)
    
    # ==============================================
    # RELACIONES
    # ==============================================
    
    # Relación many-to-many con micro-memos
    memos = relationship(
        "MicroMemo",
        secondary=micro_memo_collection_association,
        back_populates="collections",
        order_by="MicroMemo.study_priority.desc()"
    )
    
    def __repr__(self) -> str:
        return (
            f"<MicroMemoCollection("
            f"id={self.id}, "
            f"name='{self.name}', "
            f"type='{self.collection_type}', "
            f"total_memos={self.total_memos}, "
            f"completion_rate={self.completion_rate:.2f}"
            f")>"
        )
    
    @property
    def is_active(self) -> bool:
        """True si la colección está activa para estudio."""
        return self.status == EstadoColeccion.ACTIVE
    
    @property
    def needs_study(self) -> bool:
        """True si la colección necesita ser estudiada."""
        if not self.next_session_recommended:
            return True
        return datetime.utcnow() >= self.next_session_recommended
    
    @property
    def progress_percentage(self) -> float:
        """Porcentaje de progreso de la colección (0-100)."""
        return min(self.completion_rate * 100, 100.0)
    
    @property
    def difficulty_level(self) -> str:
        """Nivel de dificultad promedio de la colección."""
        if not self.difficulty_distribution:
            return "medium"
        
        # Calcular nivel promedio basado en distribución
        total_weight = 0
        weighted_sum = 0
        weights = {
            "very_easy": 1,
            "easy": 2,
            "medium": 3,
            "hard": 4,
            "very_hard": 5,
            "expert": 6
        }
        
        for level, count in self.difficulty_distribution.items():
            if level in weights:
                weight = weights[level]
                weighted_sum += weight * count
                total_weight += count
        
        if total_weight == 0:
            return "medium"
        
        avg_weight = weighted_sum / total_weight
        
        if avg_weight <= 1.5:
            return "very_easy"
        elif avg_weight <= 2.5:
            return "easy"
        elif avg_weight <= 3.5:
            return "medium"
        elif avg_weight <= 4.5:
            return "hard"
        elif avg_weight <= 5.5:
            return "very_hard"
        else:
            return "expert"
    
    def calculate_next_session(self) -> datetime:
        """Calcula la próxima sesión recomendada."""
        if not self.last_studied:
            return datetime.utcnow()
        
        # Basado en completion_rate y configuración
        if self.completion_rate < 0.3:
            # Colección nueva, estudiar pronto
            return self.last_studied + timedelta(hours=self.min_review_interval_hours)
        elif self.completion_rate < 0.7:
            # En progreso, estudiar regularmente
            return self.last_studied + timedelta(hours=self.min_review_interval_hours * 2)
        else:
            # Casi completada, espaciar más
            return self.last_studied + timedelta(hours=self.min_review_interval_hours * 4)
    
    def update_statistics(self):
        """Actualiza las estadísticas de la colección."""
        if not self.memos:
            return
        
        # Actualizar contadores básicos
        self.total_memos = len(self.memos)
        self.memos_studied = sum(1 for memo in self.memos if memo.times_studied > 0)
        self.memos_mastered = sum(1 for memo in self.memos if memo.success_rate and memo.success_rate > 0.8)
        
        # Calcular completion_rate
        if self.total_memos > 0:
            self.completion_rate = self.memos_studied / self.total_memos
        
        # Calcular precisión promedio
        accuracies = [memo.success_rate for memo in self.memos if memo.success_rate is not None]
        if accuracies:
            self.avg_accuracy = sum(accuracies) / len(accuracies)
        
        # Calcular tiempo promedio por memo
        times = [memo.avg_response_time for memo in self.memos if memo.avg_response_time is not None]
        if times:
            self.avg_time_per_memo = sum(times) / len(times)
        
        # Distribución por dificultad
        difficulty_counts = {}
        for memo in self.memos:
            level = memo.difficulty_level
            difficulty_counts[level] = difficulty_counts.get(level, 0) + 1
        self.difficulty_distribution = difficulty_counts
        
        # Distribución por especialidad
        specialty_counts = {}
        for memo in self.memos:
            if memo.medical_specialty:
                specialty = memo.medical_specialty
                specialty_counts[specialty] = specialty_counts.get(specialty, 0) + 1
        self.specialty_distribution = specialty_counts
        
        # Calcular próxima sesión
        self.next_session_recommended = self.calculate_next_session()
    
    def get_study_session(self, max_memos: Optional[int] = None) -> List[Dict[str, Any]]:
        """Obtiene los micro-memos para una sesión de estudio."""
        max_memos = max_memos or self.max_memos_per_session
        
        # Filtrar memos listos para estudio
        available_memos = [memo for memo in self.memos if memo.is_ready_for_study]
        
        if self.study_mode == ModoEstudio.SPACED_REPETITION:
            # Priorizar memos que necesitan revisión
            available_memos.sort(key=lambda m: (
                not m.needs_review_soon,  # False viene primero (necesitan revisión)
                m.next_review or datetime.min,
                -m.study_priority
            ))
        elif self.study_mode == ModoEstudio.PRIORITY_BASED:
            available_memos.sort(key=lambda m: -m.study_priority)
        elif self.study_mode == ModoEstudio.DIFFICULTY_ASC:
            available_memos.sort(key=lambda m: m.difficulty_score)
        elif self.study_mode == ModoEstudio.DIFFICULTY_DESC:
            available_memos.sort(key=lambda m: -m.difficulty_score)
        elif self.study_mode == ModoEstudio.RANDOM:
            import random
            random.shuffle(available_memos)
        # SEQUENTIAL es el orden por defecto
        
        # Limitar al máximo por sesión
        session_memos = available_memos[:max_memos]
        
        return [memo.to_study_card() for memo in session_memos]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario con información completa."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "collection_type": self.collection_type,
            "status": self.status,
            "study_mode": self.study_mode,
            "total_memos": self.total_memos,
            "memos_studied": self.memos_studied,
            "memos_mastered": self.memos_mastered,
            "completion_rate": self.completion_rate,
            "avg_accuracy": self.avg_accuracy,
            "progress_percentage": self.progress_percentage,
            "difficulty_level": self.difficulty_level,
            "difficulty_distribution": self.difficulty_distribution,
            "specialty_distribution": self.specialty_distribution,
            "max_memos_per_session": self.max_memos_per_session,
            "max_session_time": self.max_session_time,
            "enable_spaced_repetition": self.enable_spaced_repetition,
            "last_studied": self.last_studied.isoformat() if self.last_studied else None,
            "next_session_recommended": self.next_session_recommended.isoformat() if self.next_session_recommended else None,
            "needs_study": self.needs_study,
            "current_streak": self.current_streak,
            "best_streak": self.best_streak,
            "total_sessions": self.total_sessions,
            "total_study_time": self.total_study_time,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "tags_included": self.tags_included or [],
            "specialty_filter": self.specialty_filter,
            "study_goals": self.study_goals or {}
        }
    
    def to_summary(self) -> Dict[str, Any]:
        """Convertir a resumen para listados."""
        return {
            "id": str(self.id),
            "name": self.name,
            "collection_type": self.collection_type,
            "status": self.status,
            "total_memos": self.total_memos,
            "completion_rate": self.completion_rate,
            "progress_percentage": self.progress_percentage,
            "difficulty_level": self.difficulty_level,
            "needs_study": self.needs_study,
            "last_studied": self.last_studied.isoformat() if self.last_studied else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
