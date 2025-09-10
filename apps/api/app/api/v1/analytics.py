"""
Analytics API Endpoints - Sprint 3
Endpoints para Learning Analytics, Recommendations y AI features
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.analytics import (
    LearningSession, UserInteraction, KnowledgeConcept, 
    ConceptMastery, AIRecommendation, PerformanceMetric
)
from app.services.analytics.learning_analytics_engine import LearningAnalyticsEngine
from app.services.ml.retention_predictor import RetentionPredictor
from app.services.ml.difficulty_estimator import DifficultyEstimator
from app.schemas.analytics import (
    LearningSessionCreate, LearningSessionResponse,
    UserInteractionCreate, AnalysisResponse,
    RecommendationResponse, DifficultyAnalysisResponse
)

router = APIRouter()
analytics_engine = LearningAnalyticsEngine()
retention_predictor = RetentionPredictor()
difficulty_estimator = DifficultyEstimator()


@router.post("/sessions", response_model=LearningSessionResponse)
async def create_learning_session(
    session_data: LearningSessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Crea una nueva sesión de aprendizaje.
    """
    try:
        learning_session = LearningSession(
            user_id=current_user.id,
            class_session_id=session_data.class_session_id,
            started_at=session_data.started_at or datetime.utcnow(),
            session_type=session_data.session_type,
            metadata=session_data.metadata or {}
        )
        
        db.add(learning_session)
        db.commit()
        db.refresh(learning_session)
        
        return LearningSessionResponse(
            id=learning_session.id,
            user_id=learning_session.user_id,
            class_session_id=learning_session.class_session_id,
            started_at=learning_session.started_at,
            session_type=learning_session.session_type,
            metadata=learning_session.metadata
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating learning session: {str(e)}")


@router.put("/sessions/{session_id}/end")
async def end_learning_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Finaliza una sesión de aprendizaje y ejecuta análisis completo.
    """
    try:
        # Obtener sesión
        session = db.query(LearningSession).filter(
            LearningSession.id == session_id,
            LearningSession.user_id == current_user.id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Learning session not found")
        
        # Finalizar sesión
        session.ended_at = datetime.utcnow()
        if session.started_at:
            session.duration_seconds = int((session.ended_at - session.started_at).total_seconds())
        
        db.commit()
        
        # Ejecutar análisis de la sesión
        analysis_result = await analytics_engine.analyze_learning_session(
            str(session_id), str(current_user.id), db
        )
        
        return {
            "message": "Learning session ended successfully",
            "session_id": str(session_id),
            "analysis": analysis_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error ending learning session: {str(e)}")


@router.post("/sessions/{session_id}/interactions")
async def add_user_interaction(
    session_id: UUID,
    interaction_data: UserInteractionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Añade una interacción del usuario a la sesión de aprendizaje.
    """
    try:
        # Verificar que la sesión existe y pertenece al usuario
        session = db.query(LearningSession).filter(
            LearningSession.id == session_id,
            LearningSession.user_id == current_user.id
        ).first()
        
        if not session:
            raise HTTPException(status_code=404, detail="Learning session not found")
        
        # Crear interacción
        interaction = UserInteraction(
            learning_session_id=session_id,
            interaction_type=interaction_data.interaction_type,
            element_type=interaction_data.element_type,
            element_id=interaction_data.element_id,
            timestamp_offset=interaction_data.timestamp_offset,
            duration_seconds=interaction_data.duration_seconds,
            properties=interaction_data.properties or {}
        )
        
        db.add(interaction)
        db.commit()
        
        return {
            "message": "Interaction added successfully",
            "interaction_id": str(interaction.id)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding interaction: {str(e)}")


@router.get("/insights", response_model=AnalysisResponse)
async def get_learning_insights(
    timeframe_days: int = Query(30, description="Number of days to analyze"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene insights completos del aprendizaje del usuario.
    """
    try:
        insights = await analytics_engine.get_user_learning_insights(
            str(current_user.id), timeframe_days, db
        )
        
        return AnalysisResponse(
            user_id=str(current_user.id),
            analysis_period=insights["analysis_period"],
            learning_trends=insights.get("learning_trends", {}),
            knowledge_evolution=insights.get("knowledge_evolution", {}),
            performance_patterns=insights.get("performance_patterns", {}),
            future_predictions=insights.get("future_predictions", {}),
            recommendations=insights.get("recommendations", []),
            study_optimization=insights.get("study_optimization", {})
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating insights: {str(e)}")


@router.get("/recommendations", response_model=List[RecommendationResponse])
async def get_ai_recommendations(
    status: Optional[str] = Query(None, description="Filter by status: pending, viewed, accepted, dismissed"),
    limit: int = Query(10, description="Maximum number of recommendations"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene recomendaciones de IA para el usuario.
    """
    try:
        query = db.query(AIRecommendation).filter(
            AIRecommendation.user_id == current_user.id
        )
        
        if status:
            query = query.filter(AIRecommendation.status == status)
        
        recommendations = query.order_by(
            AIRecommendation.priority_score.desc(),
            AIRecommendation.created_at.desc()
        ).limit(limit).all()
        
        return [
            RecommendationResponse(
                id=rec.id,
                recommendation_type=rec.recommendation_type,
                priority_score=rec.priority_score,
                reasoning=rec.reasoning,
                recommendation_data=rec.recommendation_data,
                status=rec.status,
                created_at=rec.created_at,
                expires_at=rec.expires_at
            )
            for rec in recommendations
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting recommendations: {str(e)}")


@router.put("/recommendations/{recommendation_id}/status")
async def update_recommendation_status(
    recommendation_id: UUID,
    status: str = Body(..., description="New status: viewed, accepted, dismissed"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Actualiza el estado de una recomendación.
    """
    try:
        recommendation = db.query(AIRecommendation).filter(
            AIRecommendation.id == recommendation_id,
            AIRecommendation.user_id == current_user.id
        ).first()
        
        if not recommendation:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        
        if status not in ["viewed", "accepted", "dismissed"]:
            raise HTTPException(status_code=400, detail="Invalid status")
        
        recommendation.status = status
        db.commit()
        
        return {
            "message": "Recommendation status updated successfully",
            "recommendation_id": str(recommendation_id),
            "new_status": status
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating recommendation: {str(e)}")


@router.post("/content/difficulty", response_model=DifficultyAnalysisResponse)
async def analyze_content_difficulty(
    content: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Analiza la dificultad de contenido médico.
    """
    try:
        # Obtener perfil del usuario para personalización
        user_profile = {
            "user_id": str(current_user.id),
            "role": getattr(current_user, 'role', 'student'),
            "skill_level": 0.5,  # Se calcularía basado en performance histórica
            "study_statistics": {}  # Se obtendría de la base de datos
        }
        
        # Analizar dificultad
        difficulty_analysis = await difficulty_estimator.estimate_content_difficulty(
            content, user_profile
        )
        
        return DifficultyAnalysisResponse(
            overall_difficulty=difficulty_analysis["overall_difficulty"],
            difficulty_breakdown=difficulty_analysis["difficulty_breakdown"],
            estimated_study_time_minutes=difficulty_analysis["estimated_study_time_minutes"],
            prerequisite_concepts=difficulty_analysis["prerequisite_concepts"],
            complexity_indicators=difficulty_analysis["complexity_indicators"],
            recommendations=difficulty_analysis["recommendations"],
            confidence_score=difficulty_analysis["confidence_score"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing content difficulty: {str(e)}")


@router.get("/concepts/mastery")
async def get_concept_mastery(
    category: Optional[str] = Query(None, description="Filter by concept category"),
    limit: int = Query(50, description="Maximum number of concepts"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene el estado de mastery de conceptos del usuario.
    """
    try:
        query = db.query(ConceptMastery).filter(
            ConceptMastery.user_id == current_user.id
        ).join(KnowledgeConcept)
        
        if category:
            query = query.filter(KnowledgeConcept.category == category)
        
        masteries = query.order_by(
            ConceptMastery.mastery_level.desc()
        ).limit(limit).all()
        
        return [
            {
                "concept_id": str(mastery.concept_id),
                "concept_name": mastery.concept.name,
                "category": mastery.concept.category,
                "mastery_level": mastery.mastery_level,
                "confidence_score": mastery.confidence_score,
                "study_count": mastery.study_count,
                "accuracy_rate": mastery.accuracy_rate,
                "last_studied_at": mastery.last_studied_at,
                "next_review_at": mastery.next_review_at,
                "retention_probability": mastery.retention_probability
            }
            for mastery in masteries
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting concept mastery: {str(e)}")


@router.get("/performance/metrics")
async def get_performance_metrics(
    metric_type: str = Query("weekly", description="Type of metrics: weekly, monthly, concept_specific"),
    limit: int = Query(10, description="Number of metric periods"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Obtiene métricas de rendimiento del usuario.
    """
    try:
        metrics = db.query(PerformanceMetric).filter(
            PerformanceMetric.user_id == current_user.id,
            PerformanceMetric.metric_type == metric_type
        ).order_by(
            PerformanceMetric.time_period_start.desc()
        ).limit(limit).all()
        
        return [
            {
                "id": str(metric.id),
                "metric_type": metric.metric_type,
                "time_period_start": metric.time_period_start,
                "time_period_end": metric.time_period_end,
                "metrics": metric.metrics,
                "created_at": metric.created_at
            }
            for metric in metrics
        ]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting performance metrics: {str(e)}")


@router.post("/retention/predict")
async def predict_retention(
    concept_ids: List[UUID] = Body(..., description="List of concept IDs to analyze"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Predice retención para conceptos específicos.
    """
    try:
        # Obtener conceptos y sus datos de mastery
        concept_updates = {}
        
        for concept_id in concept_ids:
            mastery = db.query(ConceptMastery).filter(
                ConceptMastery.user_id == current_user.id,
                ConceptMastery.concept_id == concept_id
            ).first()
            
            if mastery:
                concept_updates[str(concept_id)] = {
                    "new_mastery_level": mastery.mastery_level,
                    "confidence": mastery.confidence_score,
                    "study_count": mastery.study_count
                }
        
        if not concept_updates:
            raise HTTPException(status_code=404, detail="No mastery data found for specified concepts")
        
        # Predecir retención
        predictions = await retention_predictor.predict_retention(
            str(current_user.id), concept_updates, db
        )
        
        return {
            "user_id": str(current_user.id),
            "predictions": predictions,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error predicting retention: {str(e)}")


@router.get("/health")
async def analytics_health_check():
    """
    Health check para el sistema de analytics.
    """
    try:
        # Verificar componentes del sistema
        components_status = {
            "analytics_engine": "operational",
            "retention_predictor": "operational" if retention_predictor else "unavailable",
            "difficulty_estimator": "operational" if difficulty_estimator else "unavailable",
            "database": "operational"
        }
        
        overall_status = "healthy" if all(
            status == "operational" for status in components_status.values()
        ) else "degraded"
        
        return {
            "status": overall_status,
            "components": components_status,
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0"
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
