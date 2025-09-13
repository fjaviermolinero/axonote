"""
Modelos de base de datos para Analytics y AI - Sprint 3
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import Column, String, Integer, Float, Text, ForeignKey, TIMESTAMP, Boolean
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class LearningSession(Base):
    """
    Sesión de aprendizaje del usuario para tracking detallado.
    """
    __tablename__ = "learning_sessions"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    class_session_id = Column(PGUUID(as_uuid=True), ForeignKey("class_sessions.id"))
    started_at = Column(TIMESTAMP(timezone=True), nullable=False)
    ended_at = Column(TIMESTAMP(timezone=True))
    duration_seconds = Column(Integer)
    session_type = Column(String(50), nullable=False)  # 'study', 'review', 'practice', 'assessment'
    effectiveness_score = Column(Float)  # [0-1] score de efectividad
    engagement_score = Column(Float)     # [0-1] score de engagement
    attention_score = Column(Float)      # [0-1] score de atención
    session_metadata = Column(JSONB, default={})
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="learning_sessions")
    class_session = relationship("ClassSession", back_populates="learning_sessions")
    interactions = relationship("UserInteraction", back_populates="learning_session", cascade="all, delete-orphan")


class UserInteraction(Base):
    """
    Interacciones detalladas del usuario durante las sesiones.
    """
    __tablename__ = "user_interactions"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    learning_session_id = Column(PGUUID(as_uuid=True), ForeignKey("learning_sessions.id"), nullable=False)
    interaction_type = Column(String(50), nullable=False)  # 'click', 'scroll', 'pause', 'highlight', 'note'
    element_type = Column(String(50))  # 'concept', 'definition', 'example', 'quiz'
    element_id = Column(String(100))
    timestamp_offset = Column(Integer, nullable=False)  # Segundos desde inicio de sesión
    duration_seconds = Column(Integer)
    properties = Column(JSONB, default={})
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # Relationships
    learning_session = relationship("LearningSession", back_populates="interactions")


class KnowledgeConcept(Base):
    """
    Conceptos del grafo de conocimiento médico.
    """
    __tablename__ = "knowledge_concepts"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name = Column(String(200), nullable=False, unique=True)
    category = Column(String(100), nullable=False)  # 'anatomy', 'physiology', 'pathology', etc.
    difficulty_base = Column(Float, nullable=False, default=0.5)  # [0-1] dificultad base
    medical_specialty = Column(String(100))
    prerequisites = Column(JSONB, default=[])  # Array de concept_ids
    learning_objectives = Column(ARRAY(Text))
    session_metadata = Column(JSONB, default={})
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # Relationships
    masteries = relationship("ConceptMastery", back_populates="concept", cascade="all, delete-orphan")


class ConceptMastery(Base):
    """
    Mastery de conceptos por usuario - núcleo del learning analytics.
    """
    __tablename__ = "concept_mastery"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    concept_id = Column(PGUUID(as_uuid=True), ForeignKey("knowledge_concepts.id"), nullable=False)
    mastery_level = Column(Float, nullable=False, default=0.0)  # [0-1] nivel de dominio
    confidence_score = Column(Float, nullable=False, default=0.0)  # [0-1] confianza del score
    last_studied_at = Column(TIMESTAMP(timezone=True))
    study_count = Column(Integer, default=0)
    correct_responses = Column(Integer, default=0)
    total_responses = Column(Integer, default=0)
    retention_probability = Column(Float)  # Predicción de retención
    next_review_at = Column(TIMESTAMP(timezone=True))  # Próxima revisión sugerida
    forgetting_rate = Column(Float, default=0.3)  # Tasa de olvido individual
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="concept_masteries")
    concept = relationship("KnowledgeConcept", back_populates="masteries")
    
    @property
    def accuracy_rate(self) -> float:
        """Calcula tasa de aciertos."""
        if self.total_responses == 0:
            return 0.0
        return self.correct_responses / self.total_responses


class StudyPattern(Base):
    """
    Patrones de estudio identificados por ML.
    """
    __tablename__ = "study_patterns"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    pattern_type = Column(String(50), nullable=False)  # 'temporal', 'content', 'behavioral'
    pattern_name = Column(String(100), nullable=False)  # 'morning_learner', 'visual_preferrer', etc.
    pattern_data = Column(JSONB, nullable=False)  # Datos específicos del patrón
    confidence_score = Column(Float, nullable=False)  # [0-1] confianza en el patrón
    impact_score = Column(Float)  # Impacto en el aprendizaje
    discovered_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    last_observed_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="study_patterns")


class PerformanceMetric(Base):
    """
    Métricas de rendimiento agregadas.
    """
    __tablename__ = "performance_metrics"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    metric_type = Column(String(50), nullable=False)  # 'weekly', 'monthly', 'concept_specific'
    time_period_start = Column(TIMESTAMP(timezone=True), nullable=False)
    time_period_end = Column(TIMESTAMP(timezone=True), nullable=False)
    metrics = Column(JSONB, nullable=False)  # Métricas específicas del período
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="performance_metrics")


class AIRecommendation(Base):
    """
    Recomendaciones generadas por IA.
    """
    __tablename__ = "ai_recommendations"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    recommendation_type = Column(String(50), nullable=False)  # 'content', 'timing', 'method', 'review'
    content_id = Column(PGUUID(as_uuid=True))  # Puede referenciar class_sessions, concepts, etc.
    priority_score = Column(Float, nullable=False)  # [0-1] prioridad de la recomendación
    reasoning = Column(Text)  # Explicación de por qué se recomienda
    recommendation_data = Column(JSONB, nullable=False)  # Datos específicos de la recomendación
    status = Column(String(20), default='pending')  # 'pending', 'viewed', 'accepted', 'dismissed'
    expires_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="ai_recommendations")


class VoiceProfile(Base):
    """
    Perfiles de voz para voice cloning.
    """
    __tablename__ = "voice_profiles"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    voice_id = Column(String(100), nullable=False, unique=True)
    professor_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    voice_name = Column(String(100), nullable=False)
    language = Column(String(10), nullable=False)  # 'it', 'en', 'es', 'de', 'fr'
    speaker_embedding = Column(JSONB, nullable=False)  # Vector embedding del speaker
    model_path = Column(String(500))  # Path al modelo entrenado
    quality_metrics = Column(JSONB, default={})  # Métricas de calidad de la voz
    capabilities = Column(JSONB, default={})  # Capacidades (emociones, velocidad, etc.)
    training_data = Column(JSONB, default={})  # Metadata del entrenamiento
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # Relationships
    professor = relationship("User", back_populates="voice_profiles")
    conversations = relationship("Conversation", back_populates="voice_profile")


class Conversation(Base):
    """
    Conversaciones del asistente de estudio IA.
    """
    __tablename__ = "conversations"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    topic = Column(String(200), nullable=False)
    conversation_type = Column(String(50), nullable=False)  # 'explanation', 'quiz', 'case_study', 'pronunciation'
    professor_voice_id = Column(String(100), ForeignKey("voice_profiles.voice_id"))
    conversation_state = Column(JSONB, default={})  # Estado actual de la conversación
    started_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    ended_at = Column(TIMESTAMP(timezone=True))
    session_metadata = Column(JSONB, default={})
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    voice_profile = relationship("VoiceProfile", back_populates="conversations")
    messages = relationship("ConversationMessage", back_populates="conversation", cascade="all, delete-orphan")


class ConversationMessage(Base):
    """
    Mensajes individuales de las conversaciones.
    """
    __tablename__ = "conversation_messages"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    conversation_id = Column(PGUUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    sender_type = Column(String(20), nullable=False)  # 'user' or 'assistant'
    message_type = Column(String(20), nullable=False)  # 'text', 'audio', 'multimodal'
    text_content = Column(Text)
    audio_path = Column(String(500))  # Path al archivo de audio
    session_metadata = Column(JSONB, default={})  # Metadatos adicionales (emociones, conceptos, etc.)
    timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")


# Extender modelos existentes con relationships
def extend_user_model():
    """
    Función para extender el modelo User con las nuevas relaciones.
    Se debe llamar después de importar el modelo User.
    """
    from app.models.user import User
    
    # Agregar relaciones al modelo User existente
    User.learning_sessions = relationship("LearningSession", back_populates="user")
    User.concept_masteries = relationship("ConceptMastery", back_populates="user")
    User.study_patterns = relationship("StudyPattern", back_populates="user")
    User.performance_metrics = relationship("PerformanceMetric", back_populates="user")
    User.ai_recommendations = relationship("AIRecommendation", back_populates="user")
    User.voice_profiles = relationship("VoiceProfile", back_populates="professor")
    User.conversations = relationship("Conversation", back_populates="user")


def extend_class_session_model():
    """
    Función para extender el modelo ClassSession con las nuevas relaciones.
    """
    from app.models.class_session import ClassSession
    
    # Agregar relación al modelo ClassSession existente
    ClassSession.learning_sessions = relationship("LearningSession", back_populates="class_session")
