"""
Learning Analytics Engine - Motor de análisis avanzado para AxoNote Sprint 3

Este módulo implementa el núcleo del sistema de analytics de aprendizaje,
incluyendo análisis de patrones, predicción de retención y optimización del estudio.
"""

from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import asyncio
import logging
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.models.analytics import (
    LearningSession, UserInteraction, KnowledgeConcept,
    ConceptMastery, StudyPattern, PerformanceMetric, AIRecommendation
)
from app.models.user import User
from app.core.database import get_db
from app.services.ml.retention_predictor import RetentionPredictor
from app.services.ml.difficulty_estimator import DifficultyEstimator

logger = logging.getLogger(__name__)


class LearningAnalyticsEngine:
    """
    Motor de análisis avanzado para tracking y optimización del aprendizaje.
    
    Capabilities:
    - Real-time learning pattern detection
    - Knowledge gap analysis  
    - Retention prediction
    - Optimal study timing
    - Performance forecasting
    - Personalized recommendations
    """
    
    def __init__(self):
        self.retention_predictor = RetentionPredictor()
        self.difficulty_estimator = DifficultyEstimator()
        self._knowledge_graph_cache = {}
        
    async def analyze_learning_session(
        self, 
        session_id: str, 
        user_id: str,
        db: Session
    ) -> Dict[str, Any]:
        """
        Análisis completo de una sesión de aprendizaje.
        
        Args:
            session_id: ID de la sesión de aprendizaje
            user_id: ID del usuario
            db: Sesión de base de datos
        
        Returns:
            Análisis detallado de la sesión con métricas y recomendaciones
        """
        logger.info(f"Starting learning session analysis for user {user_id}, session {session_id}")
        
        try:
            # 1. Obtener datos de la sesión
            session_data = await self._get_session_data(session_id, db)
            if not session_data:
                raise ValueError(f"Session {session_id} not found")
                
            user_profile = await self._get_user_profile(user_id, db)
            
            # 2. Analizar patrones de interacción
            interaction_patterns = await self._analyze_interaction_patterns(
                session_data, user_profile
            )
            
            # 3. Evaluar efectividad del aprendizaje
            learning_effectiveness = await self._evaluate_learning_effectiveness(
                session_data, interaction_patterns
            )
            
            # 4. Actualizar grafo de conocimiento
            concept_updates = await self._update_concept_mastery(
                user_id, session_data, learning_effectiveness, db
            )
            
            # 5. Predecir retención
            retention_predictions = await self.retention_predictor.predict_retention(
                user_id, concept_updates, db
            )
            
            # 6. Generar recomendaciones
            recommendations = await self._generate_study_recommendations(
                user_id, retention_predictions, interaction_patterns, db
            )
            
            # 7. Crear análisis completo
            analysis_result = {
                "session_id": session_id,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat(),
                "learning_effectiveness": learning_effectiveness,
                "interaction_patterns": interaction_patterns,
                "concept_mastery_updates": concept_updates,
                "retention_predictions": retention_predictions,
                "study_recommendations": recommendations,
                "performance_metrics": {
                    "attention_score": interaction_patterns.get("attention_score", 0),
                    "engagement_level": interaction_patterns.get("engagement_level", 0),
                    "comprehension_rate": learning_effectiveness.get("comprehension_rate", 0),
                    "efficiency_score": learning_effectiveness.get("efficiency_score", 0)
                },
                "session_summary": {
                    "total_concepts_studied": len(concept_updates),
                    "average_mastery_improvement": np.mean([
                        update.get("mastery_improvement", 0) 
                        for update in concept_updates.values()
                    ]) if concept_updates else 0,
                    "study_efficiency_percentile": learning_effectiveness.get("efficiency_percentile", 50)
                }
            }
            
            # 8. Guardar análisis
            await self._save_learning_analysis(analysis_result, db)
            
            logger.info(f"Learning session analysis completed for user {user_id}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error analyzing learning session {session_id}: {str(e)}")
            raise
    
    async def _analyze_interaction_patterns(
        self, 
        session_data: Dict, 
        user_profile: Dict
    ) -> Dict[str, float]:
        """
        Análisis avanzado de patrones de interacción del usuario.
        
        Analiza:
        - Patrones de atención y foco
        - Consistencia temporal de estudio
        - Eficiencia de navegación
        - Nivel de engagement
        """
        interactions = session_data.get("interactions", [])
        
        if not interactions:
            return {
                "attention_score": 0.0,
                "engagement_level": 0.0,
                "temporal_consistency": 0.0,
                "navigation_efficiency": 0.0
            }
        
        # Métricas de atención
        attention_metrics = self._calculate_attention_metrics(interactions)
        
        # Patrones temporales
        temporal_patterns = self._analyze_temporal_patterns(interactions)
        
        # Patrones de navegación
        navigation_patterns = self._analyze_navigation_patterns(interactions)
        
        # Score de engagement compuesto
        engagement_score = self._calculate_engagement_score(
            attention_metrics, temporal_patterns, navigation_patterns
        )
        
        return {
            "attention_score": attention_metrics["attention_score"],
            "focus_duration": attention_metrics["focus_duration"],
            "distraction_events": attention_metrics["distraction_events"],
            "temporal_consistency": temporal_patterns["consistency_score"],
            "optimal_timing": temporal_patterns["optimal_timing"],
            "navigation_efficiency": navigation_patterns["efficiency"],
            "content_exploration": navigation_patterns["exploration_depth"],
            "engagement_level": engagement_score,
            "interaction_velocity": len(interactions) / max(1, session_data.get("duration_seconds", 1) / 60),
            "deep_engagement_periods": attention_metrics.get("deep_focus_periods", 0)
        }
    
    async def _evaluate_learning_effectiveness(
        self, 
        session_data: Dict, 
        interaction_patterns: Dict
    ) -> Dict[str, float]:
        """
        Evaluación de la efectividad del aprendizaje usando múltiples indicadores.
        
        Métricas evaluadas:
        - Tasa de comprensión
        - Progreso en mastery de conceptos
        - Eficiencia temporal
        - Probabilidad de retención
        """
        
        # Métricas basadas en contenido
        content_metrics = self._evaluate_content_mastery(session_data)
        
        # Métricas basadas en tiempo
        time_metrics = self._evaluate_time_efficiency(session_data, interaction_patterns)
        
        # Métricas de comprensión
        comprehension_metrics = self._evaluate_comprehension(session_data)
        
        # Score compuesto de efectividad
        effectiveness_score = self._calculate_effectiveness_score(
            content_metrics, time_metrics, comprehension_metrics
        )
        
        return {
            "comprehension_rate": comprehension_metrics["comprehension_rate"],
            "mastery_progress": content_metrics["mastery_progress"],
            "efficiency_score": time_metrics["efficiency_score"],
            "retention_likelihood": effectiveness_score["retention_likelihood"],
            "overall_effectiveness": effectiveness_score["overall_score"],
            "learning_velocity": content_metrics.get("concepts_per_minute", 0),
            "knowledge_depth": comprehension_metrics.get("depth_score", 0.5),
            "efficiency_percentile": time_metrics.get("efficiency_percentile", 50)
        }
    
    async def get_user_learning_insights(
        self, 
        user_id: str, 
        timeframe_days: int = 30,
        db: Session = None
    ) -> Dict[str, Any]:
        """
        Insights completos del aprendizaje del usuario en un período.
        
        Args:
            user_id: ID del usuario
            timeframe_days: Días hacia atrás para el análisis
            db: Sesión de base de datos
            
        Returns:
            Insights detallados del aprendizaje y predicciones
        """
        
        # Obtener datos del período
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=timeframe_days)
        
        # Obtener sesiones del período
        sessions = db.query(LearningSession).filter(
            LearningSession.user_id == user_id,
            LearningSession.created_at.between(start_date, end_date)
        ).all()
        
        if not sessions:
            return {
                "user_id": user_id,
                "message": "No learning sessions found in the specified timeframe",
                "recommendations": ["Start studying to generate insights!"]
            }
        
        # Análisis agregado
        learning_trends = self._analyze_learning_trends(sessions)
        knowledge_evolution = await self._analyze_knowledge_evolution(user_id, sessions, db)
        performance_patterns = self._analyze_performance_patterns(sessions)
        
        # Predicciones futuras
        future_predictions = await self._predict_future_performance(user_id, sessions, db)
        
        return {
            "user_id": user_id,
            "analysis_period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_sessions": len(sessions),
                "total_study_hours": sum(s.duration_seconds or 0 for s in sessions) / 3600
            },
            "learning_trends": learning_trends,
            "knowledge_evolution": knowledge_evolution,
            "performance_patterns": performance_patterns,
            "future_predictions": future_predictions,
            "recommendations": await self._generate_personalized_recommendations(
                user_id, learning_trends, knowledge_evolution, db
            ),
            "strengths": learning_trends.get("strengths", []),
            "improvement_areas": learning_trends.get("improvement_areas", []),
            "study_optimization": {
                "optimal_study_times": performance_patterns.get("optimal_times", []),
                "recommended_session_length": performance_patterns.get("optimal_duration", 45),
                "suggested_break_frequency": performance_patterns.get("break_frequency", 25)
            }
        }
    
    # Métodos auxiliares de análisis
    def _calculate_attention_metrics(self, interactions: List[Dict]) -> Dict[str, float]:
        """Calcula métricas de atención basadas en interacciones."""
        if not interactions:
            return {"attention_score": 0, "focus_duration": 0, "distraction_events": 0}
        
        # Tiempo total de interacción activa
        active_time = sum(i.get("duration_seconds", 0) for i in interactions)
        
        # Eventos de distracción (pausas largas, cambios de foco)
        distraction_events = sum(
            1 for i in interactions 
            if i.get("interaction_type") == "pause" or i.get("duration_seconds", 0) > 300
        )
        
        # Períodos de foco profundo (interacciones largas y consistentes)
        deep_focus_periods = sum(
            1 for i in interactions
            if i.get("duration_seconds", 0) > 120 and i.get("interaction_type") in ["read", "study", "practice"]
        )
        
        # Score de atención (basado en consistencia de interacción)
        if active_time + distraction_events * 60 > 0:
            attention_score = min(1.0, active_time / (active_time + distraction_events * 60))
        else:
            attention_score = 0.0
        
        return {
            "attention_score": attention_score,
            "focus_duration": active_time,
            "distraction_events": distraction_events,
            "deep_focus_periods": deep_focus_periods,
            "average_interaction_duration": active_time / len(interactions) if interactions else 0
        }
    
    def _analyze_temporal_patterns(self, interactions: List[Dict]) -> Dict[str, float]:
        """Analiza patrones temporales de estudio."""
        if len(interactions) < 2:
            return {"consistency_score": 0, "optimal_timing": 0}
        
        # Análisis de consistencia temporal
        timestamps = [i.get("timestamp_offset", 0) for i in interactions]
        
        # Calcular intervalos entre interacciones
        intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
        
        # Consistencia (baja varianza = alta consistencia)
        if intervals:
            mean_interval = np.mean(intervals)
            std_interval = np.std(intervals)
            consistency_score = 1.0 / (1.0 + std_interval / mean_interval) if mean_interval > 0 else 0
        else:
            consistency_score = 0
        
        # Timing óptimo (basado en research sobre ritmos circadianos)
        optimal_hours = [9, 10, 11, 15, 16, 17]  # Horas óptimas para aprendizaje
        
        # Simular horas de estudio basado en timestamps (esto sería más preciso con timestamps reales)
        study_hours = [9 + (t % 43200) // 3600 for t in timestamps]  # Convertir a horas del día
        optimal_timing = sum(1 for h in study_hours if h in optimal_hours) / len(study_hours) if study_hours else 0
        
        return {
            "consistency_score": consistency_score,
            "optimal_timing": optimal_timing,
            "average_interval": mean_interval if intervals else 0,
            "rhythm_regularity": 1.0 - (std_interval / mean_interval) if intervals and mean_interval > 0 else 0
        }
    
    def _analyze_navigation_patterns(self, interactions: List[Dict]) -> Dict[str, float]:
        """Analiza patrones de navegación y exploración de contenido."""
        if not interactions:
            return {"efficiency": 0, "exploration_depth": 0}
        
        # Calcular eficiencia de navegación
        unique_elements = len(set(i.get("element_id", "") for i in interactions if i.get("element_id")))
        total_interactions = len(interactions)
        
        efficiency = unique_elements / total_interactions if total_interactions > 0 else 0
        
        # Profundidad de exploración
        element_types = [i.get("element_type", "") for i in interactions]
        unique_element_types = len(set(element_types))
        exploration_depth = min(1.0, unique_element_types / 5)  # Normalizado a 5 tipos principales
        
        # Patrón de revisión (volver a elementos anteriores)
        revisit_pattern = sum(
            1 for i, interaction in enumerate(interactions[1:], 1)
            if interaction.get("element_id") in [prev.get("element_id") for prev in interactions[:i]]
        ) / len(interactions) if interactions else 0
        
        return {
            "efficiency": efficiency,
            "exploration_depth": exploration_depth,
            "unique_elements_visited": unique_elements,
            "revisit_pattern": revisit_pattern,
            "content_coverage": unique_element_types
        }
    
    def _calculate_engagement_score(
        self, 
        attention_metrics: Dict, 
        temporal_patterns: Dict, 
        navigation_patterns: Dict
    ) -> float:
        """Calcula un score compuesto de engagement."""
        
        # Pesos para diferentes aspectos del engagement
        weights = {
            "attention": 0.4,
            "temporal": 0.3,
            "navigation": 0.3
        }
        
        attention_component = attention_metrics.get("attention_score", 0)
        temporal_component = temporal_patterns.get("consistency_score", 0)
        navigation_component = navigation_patterns.get("efficiency", 0)
        
        engagement_score = (
            attention_component * weights["attention"] +
            temporal_component * weights["temporal"] +
            navigation_component * weights["navigation"]
        )
        
        return min(1.0, engagement_score)
    
    def _evaluate_content_mastery(self, session_data: Dict) -> Dict[str, float]:
        """Evalúa el progreso en mastery de contenido."""
        
        # Simular análisis de mastery basado en interacciones
        interactions = session_data.get("interactions", [])
        
        # Contar interacciones de práctica/evaluación
        practice_interactions = [
            i for i in interactions 
            if i.get("element_type") in ["quiz", "practice", "exercise"]
        ]
        
        if practice_interactions:
            # Simular tasa de aciertos basada en duración de interacciones
            success_rate = sum(
                1 for i in practice_interactions 
                if i.get("duration_seconds", 0) > 30  # Interacciones largas = más probabilidad de éxito
            ) / len(practice_interactions)
        else:
            success_rate = 0.5  # Valor por defecto
        
        # Progreso de mastery estimado
        mastery_progress = min(1.0, success_rate * len(practice_interactions) / 10)
        
        # Conceptos por minuto
        total_duration = session_data.get("duration_seconds", 1)
        concepts_per_minute = len(set(i.get("element_id", "") for i in interactions)) / (total_duration / 60)
        
        return {
            "mastery_progress": mastery_progress,
            "success_rate": success_rate,
            "concepts_per_minute": concepts_per_minute,
            "practice_interactions": len(practice_interactions),
            "content_coverage": len(set(i.get("element_id", "") for i in interactions))
        }
    
    def _evaluate_time_efficiency(self, session_data: Dict, interaction_patterns: Dict) -> Dict[str, float]:
        """Evalúa la eficiencia temporal del estudio."""
        
        duration = session_data.get("duration_seconds", 1)
        interactions = session_data.get("interactions", [])
        
        # Tiempo activo vs total
        active_time = sum(i.get("duration_seconds", 0) for i in interactions)
        time_efficiency = active_time / duration if duration > 0 else 0
        
        # Velocidad de interacción
        interaction_rate = len(interactions) / (duration / 60) if duration > 0 else 0
        
        # Score de eficiencia compuesto
        efficiency_score = min(1.0, (time_efficiency * 0.7 + min(1.0, interaction_rate / 10) * 0.3))
        
        # Percentil de eficiencia (simulado)
        efficiency_percentile = min(100, efficiency_score * 100 + 10)
        
        return {
            "efficiency_score": efficiency_score,
            "time_efficiency": time_efficiency,
            "interaction_rate": interaction_rate,
            "active_time_ratio": active_time / duration if duration > 0 else 0,
            "efficiency_percentile": efficiency_percentile
        }
    
    def _evaluate_comprehension(self, session_data: Dict) -> Dict[str, float]:
        """Evalúa el nivel de comprensión basado en patrones de interacción."""
        
        interactions = session_data.get("interactions", [])
        
        # Analizar tipos de interacciones que indican comprensión
        comprehension_indicators = [
            i for i in interactions 
            if i.get("interaction_type") in ["highlight", "note", "bookmark", "quiz_correct"]
        ]
        
        # Tasa de comprensión basada en indicadores
        comprehension_rate = len(comprehension_indicators) / len(interactions) if interactions else 0
        
        # Profundidad de comprensión basada en tiempo en elementos complejos
        complex_interactions = [
            i for i in interactions 
            if i.get("element_type") in ["concept", "definition"] and i.get("duration_seconds", 0) > 60
        ]
        
        depth_score = min(1.0, len(complex_interactions) / max(1, len(interactions) * 0.3))
        
        return {
            "comprehension_rate": comprehension_rate,
            "depth_score": depth_score,
            "comprehension_indicators": len(comprehension_indicators),
            "complex_engagement": len(complex_interactions)
        }
    
    def _calculate_effectiveness_score(
        self, 
        content_metrics: Dict, 
        time_metrics: Dict, 
        comprehension_metrics: Dict
    ) -> Dict[str, float]:
        """Calcula score compuesto de efectividad del aprendizaje."""
        
        # Pesos para diferentes componentes
        weights = {
            "content": 0.4,
            "time": 0.3,
            "comprehension": 0.3
        }
        
        content_score = content_metrics.get("mastery_progress", 0)
        time_score = time_metrics.get("efficiency_score", 0)
        comprehension_score = comprehension_metrics.get("comprehension_rate", 0)
        
        overall_score = (
            content_score * weights["content"] +
            time_score * weights["time"] +
            comprehension_score * weights["comprehension"]
        )
        
        # Predicción de retención basada en efectividad
        retention_likelihood = min(1.0, overall_score * 1.2)  # Boost para scores altos
        
        return {
            "overall_score": overall_score,
            "retention_likelihood": retention_likelihood,
            "component_scores": {
                "content": content_score,
                "time": time_score,
                "comprehension": comprehension_score
            }
        }
    
    async def _get_session_data(self, session_id: str, db: Session) -> Optional[Dict]:
        """Obtiene datos completos de una sesión de aprendizaje."""
        
        session = db.query(LearningSession).filter(
            LearningSession.id == session_id
        ).first()
        
        if not session:
            return None
        
        # Obtener interacciones de la sesión
        interactions = db.query(UserInteraction).filter(
            UserInteraction.learning_session_id == session_id
        ).all()
        
        return {
            "session_id": str(session.id),
            "user_id": str(session.user_id),
            "duration_seconds": session.duration_seconds,
            "session_type": session.session_type,
            "interactions": [
                {
                    "interaction_type": interaction.interaction_type,
                    "element_type": interaction.element_type,
                    "element_id": interaction.element_id,
                    "timestamp_offset": interaction.timestamp_offset,
                    "duration_seconds": interaction.duration_seconds,
                    "properties": interaction.properties
                }
                for interaction in interactions
            ],
            "metadata": session.metadata
        }
    
    async def _get_user_profile(self, user_id: str, db: Session) -> Dict:
        """Obtiene perfil completo del usuario."""
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {}
        
        # Obtener estadísticas de estudio
        recent_sessions = db.query(LearningSession).filter(
            LearningSession.user_id == user_id,
            LearningSession.created_at >= datetime.utcnow() - timedelta(days=30)
        ).all()
        
        return {
            "user_id": str(user.id),
            "email": user.email,
            "role": getattr(user, 'role', 'student'),
            "study_statistics": {
                "total_sessions": len(recent_sessions),
                "total_study_time": sum(s.duration_seconds or 0 for s in recent_sessions),
                "average_session_duration": np.mean([s.duration_seconds or 0 for s in recent_sessions]) if recent_sessions else 0,
                "last_study_date": max([s.created_at for s in recent_sessions]) if recent_sessions else None
            },
            "preferences": getattr(user, 'preferences', {}),
            "skill_level": 0.5  # Por defecto, se calcularía basado en performance
        }
    
    async def _update_concept_mastery(
        self, 
        user_id: str, 
        session_data: Dict, 
        learning_effectiveness: Dict,
        db: Session
    ) -> Dict[str, Dict]:
        """Actualiza el mastery de conceptos basado en la sesión."""
        
        concept_updates = {}
        
        # Identificar conceptos estudiados en la sesión
        interactions = session_data.get("interactions", [])
        concept_elements = [
            i for i in interactions 
            if i.get("element_type") == "concept" and i.get("element_id")
        ]
        
        for interaction in concept_elements:
            concept_name = interaction["element_id"]
            
            # Buscar o crear concepto
            concept = db.query(KnowledgeConcept).filter(
                KnowledgeConcept.name == concept_name
            ).first()
            
            if not concept:
                # Crear nuevo concepto
                concept = KnowledgeConcept(
                    name=concept_name,
                    category="general",  # Se determinaría automáticamente
                    difficulty_base=0.5
                )
                db.add(concept)
                db.flush()
            
            # Buscar o crear mastery del usuario
            mastery = db.query(ConceptMastery).filter(
                and_(
                    ConceptMastery.user_id == user_id,
                    ConceptMastery.concept_id == concept.id
                )
            ).first()
            
            if not mastery:
                mastery = ConceptMastery(
                    user_id=user_id,
                    concept_id=concept.id,
                    mastery_level=0.0,
                    confidence_score=0.0
                )
                db.add(mastery)
            
            # Calcular mejora de mastery basada en la sesión
            interaction_duration = interaction.get("duration_seconds", 0)
            effectiveness = learning_effectiveness.get("overall_effectiveness", 0.5)
            
            # Incremento de mastery basado en tiempo y efectividad
            mastery_improvement = min(0.1, (interaction_duration / 300) * effectiveness)
            
            old_mastery_level = mastery.mastery_level
            mastery.mastery_level = min(1.0, mastery.mastery_level + mastery_improvement)
            mastery.confidence_score = min(1.0, mastery.confidence_score + mastery_improvement * 0.5)
            mastery.last_studied_at = datetime.utcnow()
            mastery.study_count += 1
            mastery.updated_at = datetime.utcnow()
            
            concept_updates[str(concept.id)] = {
                "concept_name": concept_name,
                "old_mastery_level": old_mastery_level,
                "new_mastery_level": mastery.mastery_level,
                "mastery_improvement": mastery_improvement,
                "confidence": mastery.confidence_score,
                "interaction_duration": interaction_duration
            }
        
        db.commit()
        return concept_updates
    
    async def _generate_study_recommendations(
        self, 
        user_id: str, 
        retention_predictions: Dict,
        interaction_patterns: Dict,
        db: Session
    ) -> List[Dict]:
        """Genera recomendaciones de estudio basadas en el análisis."""
        
        recommendations = []
        
        # Recomendación basada en atención
        if interaction_patterns.get("attention_score", 0) < 0.6:
            recommendations.append({
                "type": "attention_improvement",
                "priority": 0.8,
                "title": "Mejora tu concentración",
                "description": "Considera estudiar en un ambiente más silencioso o tomar descansos más frecuentes.",
                "action": "modify_environment"
            })
        
        # Recomendación basada en consistencia temporal
        if interaction_patterns.get("temporal_consistency", 0) < 0.5:
            recommendations.append({
                "type": "schedule_optimization",
                "priority": 0.7,
                "title": "Establece un horario de estudio",
                "description": "Estudiar a horas consistentes mejora la retención de información.",
                "action": "create_schedule"
            })
        
        # Recomendaciones basadas en retención
        for concept_id, prediction in retention_predictions.items():
            if prediction.get("retention_probability", 1.0) < 0.7:
                recommendations.append({
                    "type": "review_recommendation", 
                    "priority": 1.0 - prediction["retention_probability"],
                    "title": f"Revisa: {prediction.get('concept_name', 'Concepto')}",
                    "description": f"Probabilidad de retención: {prediction['retention_probability']:.1%}",
                    "action": "schedule_review",
                    "content_id": concept_id,
                    "suggested_date": prediction.get("next_review_date")
                })
        
        # Ordenar por prioridad
        recommendations.sort(key=lambda x: x["priority"], reverse=True)
        
        return recommendations[:5]  # Limitar a top 5
    
    async def _save_learning_analysis(self, analysis_result: Dict, db: Session) -> None:
        """Guarda el análisis de aprendizaje en la base de datos."""
        
        # Actualizar la sesión con métricas calculadas
        session = db.query(LearningSession).filter(
            LearningSession.id == analysis_result["session_id"]
        ).first()
        
        if session:
            session.effectiveness_score = analysis_result["learning_effectiveness"]["overall_effectiveness"]
            session.engagement_score = analysis_result["performance_metrics"]["engagement_level"]
            session.attention_score = analysis_result["performance_metrics"]["attention_score"]
            session.metadata = {
                **session.metadata,
                "analysis_timestamp": analysis_result["timestamp"],
                "analysis_version": "1.0"
            }
        
        # Guardar recomendaciones como registros separados
        for rec in analysis_result["study_recommendations"]:
            ai_recommendation = AIRecommendation(
                user_id=analysis_result["user_id"],
                recommendation_type=rec["type"],
                content_id=rec.get("content_id"),
                priority_score=rec["priority"],
                reasoning=rec["description"],
                recommendation_data=rec,
                expires_at=datetime.utcnow() + timedelta(days=7)
            )
            db.add(ai_recommendation)
        
        db.commit()
    
    # Métodos adicionales para análisis agregado
    def _analyze_learning_trends(self, sessions: List[LearningSession]) -> Dict:
        """Analiza tendencias de aprendizaje a lo largo del tiempo."""
        
        if not sessions:
            return {"trend": "no_data"}
        
        # Ordenar sesiones por fecha
        sessions_sorted = sorted(sessions, key=lambda s: s.created_at)
        
        # Calcular métricas por semana
        weekly_metrics = {}
        for session in sessions_sorted:
            week = session.created_at.isocalendar()[1]
            if week not in weekly_metrics:
                weekly_metrics[week] = {
                    "sessions": 0,
                    "total_time": 0,
                    "avg_effectiveness": 0,
                    "effectiveness_scores": []
                }
            
            weekly_metrics[week]["sessions"] += 1
            weekly_metrics[week]["total_time"] += session.duration_seconds or 0
            if session.effectiveness_score:
                weekly_metrics[week]["effectiveness_scores"].append(session.effectiveness_score)
        
        # Calcular promedios semanales
        for week_data in weekly_metrics.values():
            if week_data["effectiveness_scores"]:
                week_data["avg_effectiveness"] = np.mean(week_data["effectiveness_scores"])
        
        # Identificar tendencias
        weeks = sorted(weekly_metrics.keys())
        if len(weeks) >= 2:
            effectiveness_trend = np.polyfit(
                weeks, 
                [weekly_metrics[w]["avg_effectiveness"] for w in weeks],
                1
            )[0]
        else:
            effectiveness_trend = 0
        
        return {
            "weekly_metrics": weekly_metrics,
            "effectiveness_trend": effectiveness_trend,
            "trend_direction": "improving" if effectiveness_trend > 0.01 else "declining" if effectiveness_trend < -0.01 else "stable",
            "strengths": ["consistent_study"] if len(sessions) > 10 else [],
            "improvement_areas": ["study_frequency"] if len(sessions) < 5 else []
        }
    
    async def _analyze_knowledge_evolution(
        self, 
        user_id: str, 
        sessions: List[LearningSession], 
        db: Session
    ) -> Dict:
        """Analiza la evolución del conocimiento del usuario."""
        
        # Obtener todas las masterías del usuario
        masteries = db.query(ConceptMastery).filter(
            ConceptMastery.user_id == user_id
        ).all()
        
        if not masteries:
            return {"status": "no_mastery_data"}
        
        # Análisis de distribución de mastery
        mastery_levels = [m.mastery_level for m in masteries]
        
        return {
            "total_concepts": len(masteries),
            "average_mastery": np.mean(mastery_levels),
            "mastery_distribution": {
                "beginner": len([m for m in mastery_levels if m < 0.3]),
                "intermediate": len([m for m in mastery_levels if 0.3 <= m < 0.7]),
                "advanced": len([m for m in mastery_levels if m >= 0.7])
            },
            "strongest_areas": [
                m.concept.name for m in sorted(masteries, key=lambda x: x.mastery_level, reverse=True)[:3]
            ],
            "areas_for_improvement": [
                m.concept.name for m in sorted(masteries, key=lambda x: x.mastery_level)[:3]
            ]
        }
    
    def _analyze_performance_patterns(self, sessions: List[LearningSession]) -> Dict:
        """Analiza patrones de rendimiento del usuario."""
        
        if not sessions:
            return {"status": "no_sessions"}
        
        # Análisis de horarios óptimos (simulado)
        optimal_times = ["09:00", "10:00", "15:00", "16:00"]
        
        # Duración óptima de sesión basada en efectividad
        effective_sessions = [s for s in sessions if s.effectiveness_score and s.effectiveness_score > 0.7]
        if effective_sessions:
            optimal_duration = np.mean([s.duration_seconds / 60 for s in effective_sessions])
        else:
            optimal_duration = 45  # Default
        
        return {
            "optimal_times": optimal_times,
            "optimal_duration": optimal_duration,
            "break_frequency": 25,  # Técnica Pomodoro
            "most_effective_session_type": "study",  # Se calcularía basado en datos reales
            "performance_consistency": np.std([s.effectiveness_score or 0.5 for s in sessions])
        }
    
    async def _predict_future_performance(
        self, 
        user_id: str, 
        sessions: List[LearningSession], 
        db: Session
    ) -> Dict:
        """Predice rendimiento futuro basado en tendencias actuales."""
        
        if len(sessions) < 3:
            return {"status": "insufficient_data"}
        
        # Tendencia de efectividad
        effectiveness_scores = [s.effectiveness_score or 0.5 for s in sessions[-10:]]
        trend = np.polyfit(range(len(effectiveness_scores)), effectiveness_scores, 1)[0]
        
        # Predicción para próximas semanas
        current_avg = np.mean(effectiveness_scores)
        predicted_next_week = min(1.0, max(0.0, current_avg + trend * 7))
        
        return {
            "predicted_effectiveness_next_week": predicted_next_week,
            "confidence": 0.7,  # Se calcularía basado en varianza
            "trend": "improving" if trend > 0 else "declining" if trend < 0 else "stable",
            "recommendation": "Continue current study pattern" if trend >= 0 else "Consider adjusting study approach"
        }
    
    async def _generate_personalized_recommendations(
        self, 
        user_id: str, 
        learning_trends: Dict, 
        knowledge_evolution: Dict, 
        db: Session
    ) -> List[str]:
        """Genera recomendaciones personalizadas basadas en análisis completo."""
        
        recommendations = []
        
        # Basado en tendencias
        if learning_trends.get("trend_direction") == "declining":
            recommendations.append("Considera tomar un descanso o cambiar tu metodología de estudio")
        
        # Basado en evolución de conocimiento
        if knowledge_evolution.get("average_mastery", 0) < 0.5:
            recommendations.append("Enfócate en conceptos fundamentales antes de avanzar a temas más complejos")
        
        # Recomendaciones por defecto
        if not recommendations:
            recommendations.extend([
                "Mantén un horario de estudio consistente",
                "Usa técnicas de spaced repetition para mejor retención",
                "Toma descansos regulares para mantener la concentración"
            ])
        
        return recommendations
