"""
Schemas para Analytics API - Sprint 3
Modelos Pydantic para validación de datos de analytics
"""

from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, validator


# Schemas para Learning Sessions
class LearningSessionCreate(BaseModel):
    """Schema para crear una sesión de aprendizaje."""
    class_session_id: Optional[UUID] = None
    started_at: Optional[datetime] = None
    session_type: str = Field(..., description="Tipo de sesión: study, review, practice, assessment")
    metadata: Optional[Dict[str, Any]] = None


class LearningSessionResponse(BaseModel):
    """Schema para respuesta de sesión de aprendizaje."""
    id: UUID
    user_id: UUID
    class_session_id: Optional[UUID]
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    session_type: str
    effectiveness_score: Optional[float] = None
    engagement_score: Optional[float] = None
    attention_score: Optional[float] = None
    metadata: Dict[str, Any]

    class Config:
        orm_mode = True


# Schemas para User Interactions
class UserInteractionCreate(BaseModel):
    """Schema para crear una interacción de usuario."""
    interaction_type: str = Field(..., description="Tipo: click, scroll, pause, highlight, note")
    element_type: Optional[str] = Field(None, description="Tipo de elemento: concept, definition, example, quiz")
    element_id: Optional[str] = Field(None, description="ID del elemento")
    timestamp_offset: int = Field(..., description="Segundos desde inicio de sesión")
    duration_seconds: Optional[int] = None
    properties: Optional[Dict[str, Any]] = None


class UserInteractionResponse(BaseModel):
    """Schema para respuesta de interacción."""
    id: UUID
    learning_session_id: UUID
    interaction_type: str
    element_type: Optional[str]
    element_id: Optional[str]
    timestamp_offset: int
    duration_seconds: Optional[int]
    properties: Dict[str, Any]
    created_at: datetime

    class Config:
        orm_mode = True


# Schemas para Analysis Response
class LearningTrends(BaseModel):
    """Tendencias de aprendizaje."""
    weekly_metrics: Dict[str, Any]
    effectiveness_trend: float
    trend_direction: str = Field(..., description="improving, declining, stable")
    strengths: List[str]
    improvement_areas: List[str]


class KnowledgeEvolution(BaseModel):
    """Evolución del conocimiento."""
    total_concepts: int
    average_mastery: float
    mastery_distribution: Dict[str, int]
    strongest_areas: List[str]
    areas_for_improvement: List[str]


class PerformancePatterns(BaseModel):
    """Patrones de rendimiento."""
    optimal_times: List[str]
    optimal_duration: float
    break_frequency: int
    most_effective_session_type: str
    performance_consistency: float


class FuturePredictions(BaseModel):
    """Predicciones futuras."""
    predicted_effectiveness_next_week: float
    confidence: float
    trend: str
    recommendation: str


class StudyOptimization(BaseModel):
    """Optimización de estudio."""
    optimal_study_times: List[str]
    recommended_session_length: float
    suggested_break_frequency: int


class AnalysisResponse(BaseModel):
    """Respuesta completa de análisis de aprendizaje."""
    user_id: str
    analysis_period: Dict[str, Any]
    learning_trends: LearningTrends
    knowledge_evolution: KnowledgeEvolution
    performance_patterns: PerformancePatterns
    future_predictions: FuturePredictions
    recommendations: List[str]
    study_optimization: StudyOptimization


# Schemas para AI Recommendations
class RecommendationResponse(BaseModel):
    """Schema para respuesta de recomendación de IA."""
    id: UUID
    recommendation_type: str = Field(..., description="Tipo: content, timing, method, review")
    priority_score: float = Field(..., ge=0, le=1, description="Prioridad 0-1")
    reasoning: Optional[str] = None
    recommendation_data: Dict[str, Any]
    status: str = Field(..., description="pending, viewed, accepted, dismissed")
    created_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        orm_mode = True


# Schemas para Difficulty Analysis
class DifficultyBreakdown(BaseModel):
    """Desglose de dificultad por componentes."""
    lexical_difficulty: float = Field(..., ge=0, le=1)
    medical_difficulty: float = Field(..., ge=0, le=1)
    conceptual_difficulty: float = Field(..., ge=0, le=1)
    syntactic_difficulty: float = Field(..., ge=0, le=1)
    information_density: float = Field(..., ge=0, le=1)


class DifficultyAnalysisResponse(BaseModel):
    """Respuesta de análisis de dificultad."""
    overall_difficulty: float = Field(..., ge=0, le=1, description="Dificultad general 0-1")
    difficulty_breakdown: DifficultyBreakdown
    estimated_study_time_minutes: float = Field(..., gt=0, description="Tiempo estimado en minutos")
    prerequisite_concepts: List[str]
    complexity_indicators: List[str]
    recommendations: List[str]
    confidence_score: float = Field(..., ge=0, le=1, description="Confianza en la estimación")


# Schemas para Concept Mastery
class ConceptMasteryResponse(BaseModel):
    """Respuesta de mastery de conceptos."""
    concept_id: UUID
    concept_name: str
    category: str
    mastery_level: float = Field(..., ge=0, le=1)
    confidence_score: float = Field(..., ge=0, le=1)
    study_count: int = Field(..., ge=0)
    accuracy_rate: float = Field(..., ge=0, le=1)
    last_studied_at: Optional[datetime] = None
    next_review_at: Optional[datetime] = None
    retention_probability: Optional[float] = Field(None, ge=0, le=1)


# Schemas para Retention Prediction
class RetentionPrediction(BaseModel):
    """Predicción de retención para un concepto."""
    retention_probability: float = Field(..., ge=0, le=1)
    optimal_review_days: float = Field(..., gt=0)
    confidence_score: float = Field(..., ge=0, le=1)
    next_review_date: str = Field(..., description="Fecha ISO para próxima revisión")
    prediction_method: str = Field(..., description="ml_model, heuristic, default")
    factors: Optional[Dict[str, Any]] = None


class RetentionPredictionResponse(BaseModel):
    """Respuesta completa de predicción de retención."""
    user_id: str
    predictions: Dict[str, RetentionPrediction]
    generated_at: str = Field(..., description="Timestamp ISO de generación")


# Schemas para Performance Metrics
class PerformanceMetricResponse(BaseModel):
    """Respuesta de métricas de rendimiento."""
    id: UUID
    metric_type: str = Field(..., description="weekly, monthly, concept_specific")
    time_period_start: datetime
    time_period_end: datetime
    metrics: Dict[str, Any]
    created_at: datetime

    class Config:
        orm_mode = True


# Schemas para Session Analytics
class InteractionPatterns(BaseModel):
    """Patrones de interacción del usuario."""
    attention_score: float = Field(..., ge=0, le=1)
    focus_duration: float = Field(..., ge=0)
    distraction_events: int = Field(..., ge=0)
    temporal_consistency: float = Field(..., ge=0, le=1)
    optimal_timing: float = Field(..., ge=0, le=1)
    navigation_efficiency: float = Field(..., ge=0, le=1)
    content_exploration: float = Field(..., ge=0, le=1)
    engagement_level: float = Field(..., ge=0, le=1)


class LearningEffectiveness(BaseModel):
    """Efectividad del aprendizaje."""
    comprehension_rate: float = Field(..., ge=0, le=1)
    mastery_progress: float = Field(..., ge=0, le=1)
    efficiency_score: float = Field(..., ge=0, le=1)
    retention_likelihood: float = Field(..., ge=0, le=1)
    overall_effectiveness: float = Field(..., ge=0, le=1)


class ConceptUpdate(BaseModel):
    """Actualización de concepto durante la sesión."""
    concept_name: str
    old_mastery_level: float = Field(..., ge=0, le=1)
    new_mastery_level: float = Field(..., ge=0, le=1)
    mastery_improvement: float = Field(..., ge=-1, le=1)
    confidence: float = Field(..., ge=0, le=1)
    interaction_duration: float = Field(..., ge=0)


class SessionAnalysisResponse(BaseModel):
    """Respuesta completa de análisis de sesión."""
    session_id: str
    user_id: str
    timestamp: str
    learning_effectiveness: LearningEffectiveness
    interaction_patterns: InteractionPatterns
    concept_mastery_updates: Dict[str, ConceptUpdate]
    retention_predictions: Dict[str, RetentionPrediction]
    study_recommendations: List[Dict[str, Any]]
    performance_metrics: Dict[str, float]
    session_summary: Dict[str, Any]


# Schemas para Voice Profiles (preparación para voice cloning)
class VoiceProfileCreate(BaseModel):
    """Schema para crear perfil de voz."""
    voice_name: str = Field(..., min_length=1, max_length=100)
    language: str = Field(..., regex="^(it|en|es|de|fr)$")
    training_audio_urls: List[str] = Field(..., min_items=1, max_items=20)


class VoiceProfileResponse(BaseModel):
    """Respuesta de perfil de voz."""
    id: UUID
    voice_id: str
    professor_id: Optional[UUID] = None
    voice_name: str
    language: str
    quality_metrics: Dict[str, Any]
    capabilities: Dict[str, Any]
    training_data: Dict[str, Any]
    created_at: datetime

    class Config:
        orm_mode = True


# Schemas para Conversations (preparación para conversational AI)
class ConversationCreate(BaseModel):
    """Schema para crear conversación."""
    topic: str = Field(..., min_length=1, max_length=200)
    conversation_type: str = Field(..., regex="^(explanation|quiz|case_study|pronunciation)$")
    professor_voice_id: Optional[str] = None


class ConversationResponse(BaseModel):
    """Respuesta de conversación."""
    id: UUID
    user_id: UUID
    topic: str
    conversation_type: str
    professor_voice_id: Optional[str] = None
    conversation_state: Dict[str, Any]
    started_at: datetime
    ended_at: Optional[datetime] = None
    metadata: Dict[str, Any]

    class Config:
        orm_mode = True


# Validators
@validator('session_type')
def validate_session_type(cls, v):
    """Valida tipos de sesión permitidos."""
    allowed_types = ['study', 'review', 'practice', 'assessment']
    if v not in allowed_types:
        raise ValueError(f'session_type must be one of: {allowed_types}')
    return v


@validator('interaction_type')
def validate_interaction_type(cls, v):
    """Valida tipos de interacción permitidos."""
    allowed_types = ['click', 'scroll', 'pause', 'highlight', 'note', 'quiz_attempt', 'read', 'practice']
    if v not in allowed_types:
        raise ValueError(f'interaction_type must be one of: {allowed_types}')
    return v


# Aplicar validators a las clases correspondientes
LearningSessionCreate.__validators__['session_type'] = validate_session_type
UserInteractionCreate.__validators__['interaction_type'] = validate_interaction_type


# Health Check Schema
class HealthCheckResponse(BaseModel):
    """Respuesta de health check."""
    status: str = Field(..., description="healthy, degraded, unhealthy")
    components: Dict[str, str]
    timestamp: str
    version: Optional[str] = None
    error: Optional[str] = None
