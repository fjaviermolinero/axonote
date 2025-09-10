"""
Hybrid Recommender System - Sistema híbrido de recomendaciones para AxoNote

Combina múltiples enfoques de recomendación para generar sugerencias
personalizadas de contenido médico y estrategias de estudio.
"""

from typing import Dict, List, Optional, Tuple, Any
import asyncio
import logging
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

try:
    from scipy.sparse import csr_matrix
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

from app.models.analytics import (
    LearningSession, ConceptMastery, KnowledgeConcept, 
    AIRecommendation, UserInteraction
)
from app.models.user import User
from app.models.class_session import ClassSession
from app.services.analytics.learning_analytics_engine import LearningAnalyticsEngine

logger = logging.getLogger(__name__)


class HybridRecommenderSystem:
    """
    Sistema híbrido de recomendaciones que combina:
    - Collaborative Filtering
    - Content-Based Filtering  
    - Knowledge Graph Embeddings
    - Learning Analytics
    - Medical Domain Expertise
    """
    
    def __init__(self):
        self.collaborative_filter = CollaborativeFilter()
        self.content_filter = ContentBasedFilter()
        self.knowledge_graph_recommender = KnowledgeGraphRecommender()
        self.learning_analytics = LearningAnalyticsEngine()
        
        # Pesos para combinar diferentes enfoques
        self.recommendation_weights = {
            "collaborative": 0.25,
            "content": 0.20,
            "knowledge_graph": 0.30,
            "learning_analytics": 0.25
        }
        
        # Cache para mejorar rendimiento
        self._user_profiles_cache = {}
        self._content_cache = {}
        
    async def generate_recommendations(
        self,
        user_id: str,
        recommendation_type: str = "study_content",
        limit: int = 10,
        context: Optional[Dict[str, Any]] = None,
        db: Session = None
    ) -> List[Dict[str, Any]]:
        """
        Genera recomendaciones híbridas personalizadas.
        
        Args:
            user_id: ID del usuario
            recommendation_type: Tipo de recomendación 
                - 'study_content': Contenido para estudiar
                - 'review_schedule': Programación de repaso
                - 'learning_path': Rutas de aprendizaje
                - 'study_methods': Métodos de estudio óptimos
            limit: Número máximo de recomendaciones
            context: Contexto adicional (tema actual, tiempo disponible, etc.)
            db: Sesión de base de datos
        """
        logger.info(f"Generating {recommendation_type} recommendations for user {user_id}")
        
        try:
            # 1. Obtener perfil completo del usuario
            user_profile = await self._get_comprehensive_user_profile(user_id, db)
            
            # 2. Generar recomendaciones de cada sistema en paralelo
            recommendation_tasks = [
                self.collaborative_filter.recommend(user_id, limit * 2, context, db),
                self.content_filter.recommend(user_profile, recommendation_type, limit * 2, context, db),
                self.knowledge_graph_recommender.recommend(user_id, user_profile, limit * 2, context, db),
                self._generate_analytics_based_recommendations(user_id, recommendation_type, limit * 2, context, db)
            ]
            
            recommendation_results = await asyncio.gather(*recommendation_tasks, return_exceptions=True)
            
            # 3. Procesar resultados y manejar errores
            collaborative_recs = recommendation_results[0] if not isinstance(recommendation_results[0], Exception) else []
            content_recs = recommendation_results[1] if not isinstance(recommendation_results[1], Exception) else []
            knowledge_recs = recommendation_results[2] if not isinstance(recommendation_results[2], Exception) else []
            analytics_recs = recommendation_results[3] if not isinstance(recommendation_results[3], Exception) else []
            
            # 4. Combinar y rankear recomendaciones
            hybrid_recommendations = await self._combine_recommendations(
                {
                    "collaborative": collaborative_recs,
                    "content": content_recs,
                    "knowledge_graph": knowledge_recs,
                    "learning_analytics": analytics_recs
                },
                user_profile,
                context
            )
            
            # 5. Diversificar resultados
            diversified_recs = await self._diversify_recommendations(
                hybrid_recommendations, user_profile
            )
            
            # 6. Aplicar filtros de negocio
            filtered_recs = await self._apply_business_filters(
                diversified_recs, user_profile, recommendation_type, context
            )
            
            # 7. Añadir metadata y explicaciones
            enriched_recs = await self._enrich_recommendations(filtered_recs, user_profile)
            
            logger.info(f"Generated {len(enriched_recs)} recommendations for user {user_id}")
            return enriched_recs[:limit]
            
        except Exception as e:
            logger.error(f"Error generating recommendations for user {user_id}: {str(e)}")
            # Fallback a recomendaciones básicas
            return await self._generate_fallback_recommendations(user_id, recommendation_type, limit, db)
    
    async def _combine_recommendations(
        self,
        recommendation_sources: Dict[str, List[Dict]],
        user_profile: Dict,
        context: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Combina recomendaciones de múltiples fuentes usando scores ponderados.
        """
        
        # Normalizar scores de cada fuente
        normalized_sources = {}
        for source, recs in recommendation_sources.items():
            if recs:
                scores = [rec.get("score", 0) for rec in recs]
                if scores:
                    max_score = max(scores)
                    min_score = min(scores)
                    score_range = max_score - min_score if max_score > min_score else 1
                    
                    normalized_recs = []
                    for rec in recs:
                        original_score = rec.get("score", 0)
                        normalized_score = (original_score - min_score) / score_range if score_range > 0 else 0
                        
                        normalized_recs.append({
                            **rec,
                            "normalized_score": normalized_score,
                            "original_score": original_score,
                            "source": source
                        })
                    normalized_sources[source] = normalized_recs
        
        # Agrupar por contenido (mismo content_id)
        content_groups = {}
        for source, recs in normalized_sources.items():
            for rec in recs:
                content_id = rec.get("content_id")
                if not content_id:
                    continue
                    
                if content_id not in content_groups:
                    content_groups[content_id] = {
                        "content_id": content_id,
                        "content_data": rec.get("content_data", {}),
                        "sources": {},
                        "total_score": 0,
                        "confidence": 0,
                        "reasoning_components": []
                    }
                
                weight = self.recommendation_weights[source]
                weighted_score = rec["normalized_score"] * weight
                
                content_groups[content_id]["sources"][source] = {
                    "score": rec["normalized_score"],
                    "original_score": rec.get("original_score", 0),
                    "weighted_score": weighted_score,
                    "reasoning": rec.get("reasoning", "")
                }
                content_groups[content_id]["total_score"] += weighted_score
                
                if rec.get("reasoning"):
                    content_groups[content_id]["reasoning_components"].append(
                        f"{source}: {rec['reasoning']}"
                    )
        
        # Calcular confidence score basado en número de fuentes y consistencia
        for content_id, group in content_groups.items():
            source_count = len(group["sources"])
            max_sources = len(self.recommendation_weights)
            
            # Confidence basado en número de fuentes
            coverage_confidence = source_count / max_sources
            
            # Confidence basado en consistencia de scores
            source_scores = [source_data["score"] for source_data in group["sources"].values()]
            if len(source_scores) > 1:
                score_std = np.std(source_scores)
                consistency_confidence = 1.0 / (1.0 + score_std)
            else:
                consistency_confidence = 0.5
            
            group["confidence"] = (coverage_confidence * 0.6 + consistency_confidence * 0.4)
        
        # Aplicar boost contextual
        if context:
            content_groups = await self._apply_contextual_boost(content_groups, context, user_profile)
        
        # Ordenar por score total
        combined_recommendations = list(content_groups.values())
        combined_recommendations.sort(key=lambda x: x["total_score"], reverse=True)
        
        return combined_recommendations
    
    async def _diversify_recommendations(
        self, 
        recommendations: List[Dict], 
        user_profile: Dict
    ) -> List[Dict]:
        """
        Diversifica las recomendaciones para evitar redundancia.
        """
        
        if not recommendations:
            return []
        
        diversified = []
        seen_categories = set()
        seen_difficulties = set()
        
        # Parámetros de diversificación
        max_per_category = 3
        difficulty_spread_target = 3  # Queremos spread en al menos 3 niveles de dificultad
        
        for rec in recommendations:
            content_data = rec.get("content_data", {})
            category = content_data.get("category", "unknown")
            difficulty = self._discretize_difficulty(content_data.get("difficulty", 0.5))
            
            # Verificar diversidad de categoría
            category_count = sum(1 for dr in diversified if dr.get("content_data", {}).get("category") == category)
            
            # Verificar diversidad de dificultad
            should_add = True
            
            if category_count >= max_per_category:
                # Demasiadas recomendaciones de esta categoría
                should_add = False
            elif len(seen_difficulties) < difficulty_spread_target:
                # Aún necesitamos más diversidad de dificultad
                if difficulty in seen_difficulties and len(diversified) > 5:
                    should_add = False
            
            if should_add:
                diversified.append(rec)
                seen_categories.add(category)
                seen_difficulties.add(difficulty)
            
            # Límite para el proceso de diversificación
            if len(diversified) >= len(recommendations) * 0.8:
                break
        
        # Añadir recomendaciones restantes si no hemos alcanzado el límite
        for rec in recommendations:
            if rec not in diversified and len(diversified) < len(recommendations):
                diversified.append(rec)
        
        return diversified
    
    async def _apply_business_filters(
        self,
        recommendations: List[Dict],
        user_profile: Dict,
        recommendation_type: str,
        context: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Aplica filtros de negocio específicos.
        """
        
        filtered = []
        
        for rec in recommendations:
            content_data = rec.get("content_data", {})
            
            # Filtro 1: Nivel apropiado para el usuario
            user_level = user_profile.get("skill_level", 0.5)
            content_difficulty = content_data.get("difficulty", 0.5)
            
            # Permitir contenido ligeramente más difícil (zona de desarrollo próximo)
            if content_difficulty > user_level + 0.3:
                continue
            
            # Filtro 2: Prerequisitos cumplidos
            prerequisites = content_data.get("prerequisites", [])
            if prerequisites and not await self._check_prerequisites(user_profile["user_id"], prerequisites):
                continue
            
            # Filtro 3: No recomendar contenido recientemente estudiado
            if await self._recently_studied(user_profile["user_id"], rec["content_id"]):
                continue
            
            # Filtro 4: Filtros específicos por tipo de recomendación
            if recommendation_type == "review_schedule":
                # Solo contenido que necesita repaso
                if not await self._needs_review(user_profile["user_id"], rec["content_id"]):
                    continue
            elif recommendation_type == "learning_path":
                # Solo contenido que sigue una progresión lógica
                if not await self._fits_learning_path(user_profile, content_data):
                    continue
            
            # Filtro 5: Contexto temporal (tiempo disponible)
            if context and "available_time_minutes" in context:
                estimated_time = content_data.get("estimated_study_time", 30)
                if estimated_time > context["available_time_minutes"] * 1.2:  # 20% de tolerancia
                    continue
            
            filtered.append(rec)
        
        return filtered
    
    async def _enrich_recommendations(
        self, 
        recommendations: List[Dict], 
        user_profile: Dict
    ) -> List[Dict[str, Any]]:
        """
        Enriquece las recomendaciones con metadata adicional y explicaciones.
        """
        
        enriched = []
        
        for i, rec in enumerate(recommendations):
            # Calcular explicación compuesta
            explanation = self._generate_explanation(rec, user_profile, i + 1)
            
            # Añadir metadata adicional
            enriched_rec = {
                **rec,
                "rank": i + 1,
                "explanation": explanation,
                "estimated_benefit": self._calculate_estimated_benefit(rec, user_profile),
                "urgency_score": self._calculate_urgency_score(rec, user_profile),
                "personalization_factors": self._extract_personalization_factors(rec, user_profile),
                "alternative_approaches": await self._suggest_alternative_approaches(rec, user_profile)
            }
            
            enriched.append(enriched_rec)
        
        return enriched
    
    async def _generate_analytics_based_recommendations(
        self,
        user_id: str,
        recommendation_type: str,
        limit: int,
        context: Optional[Dict],
        db: Session
    ) -> List[Dict]:
        """
        Genera recomendaciones basadas en analytics de aprendizaje.
        """
        
        recommendations = []
        
        try:
            # Obtener insights del usuario
            insights = await self.learning_analytics.get_user_learning_insights(user_id, 30, db)
            
            # Recomendaciones basadas en areas de mejora
            improvement_areas = insights.get("learning_trends", {}).get("improvement_areas", [])
            for area in improvement_areas:
                recommendations.append({
                    "content_id": f"improvement_{area}",
                    "content_data": {
                        "title": f"Mejora en {area}",
                        "category": area,
                        "difficulty": 0.6
                    },
                    "score": 0.8,
                    "reasoning": f"Área identificada para mejora basada en analytics"
                })
            
            # Recomendaciones basadas en patrones de rendimiento
            performance_patterns = insights.get("performance_patterns", {})
            optimal_times = performance_patterns.get("optimal_times", [])
            
            if context and "current_time" in context:
                current_hour = context["current_time"].hour
                if any(abs(current_hour - int(time.split(":")[0])) <= 1 for time in optimal_times):
                    # Boost para contenido difícil durante horarios óptimos
                    recommendations.append({
                        "content_id": "challenging_content",
                        "content_data": {
                            "title": "Contenido desafiante - horario óptimo",
                            "category": "advanced",
                            "difficulty": 0.8
                        },
                        "score": 0.9,
                        "reasoning": "Horario óptimo detectado para contenido desafiante"
                    })
            
            # Recomendaciones basadas en predicciones futuras
            future_predictions = insights.get("future_predictions", {})
            if future_predictions.get("trend") == "declining":
                recommendations.append({
                    "content_id": "review_fundamentals",
                    "content_data": {
                        "title": "Repaso de fundamentos",
                        "category": "review",
                        "difficulty": 0.3
                    },
                    "score": 0.85,
                    "reasoning": "Tendencia declinante detectada - repaso recomendado"
                })
            
        except Exception as e:
            logger.warning(f"Error generating analytics-based recommendations: {str(e)}")
        
        return recommendations[:limit]
    
    # Métodos auxiliares
    async def _get_comprehensive_user_profile(self, user_id: str, db: Session) -> Dict:
        """Obtiene perfil completo del usuario con cache."""
        
        if user_id in self._user_profiles_cache:
            cached_profile = self._user_profiles_cache[user_id]
            # Verificar si el cache es reciente (últimos 10 minutos)
            if (datetime.utcnow() - cached_profile["cached_at"]).seconds < 600:
                return cached_profile["profile"]
        
        # Obtener datos del usuario
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"user_id": user_id, "error": "User not found"}
        
        # Obtener estadísticas de estudio
        recent_sessions = db.query(LearningSession).filter(
            LearningSession.user_id == user_id,
            LearningSession.created_at >= datetime.utcnow() - timedelta(days=30)
        ).all()
        
        # Obtener mastery de conceptos
        masteries = db.query(ConceptMastery).filter(
            ConceptMastery.user_id == user_id
        ).all()
        
        profile = {
            "user_id": user_id,
            "email": user.email,
            "role": getattr(user, 'role', 'student'),
            "study_statistics": {
                "total_sessions": len(recent_sessions),
                "total_study_time": sum(s.duration_seconds or 0 for s in recent_sessions),
                "average_effectiveness": np.mean([s.effectiveness_score or 0.5 for s in recent_sessions]) if recent_sessions else 0.5,
                "last_study_date": max([s.created_at for s in recent_sessions]) if recent_sessions else None
            },
            "knowledge_state": {
                "total_concepts": len(masteries),
                "average_mastery": np.mean([m.mastery_level for m in masteries]) if masteries else 0.0,
                "strong_areas": [m.concept.category for m in masteries if m.mastery_level > 0.7],
                "weak_areas": [m.concept.category for m in masteries if m.mastery_level < 0.3]
            },
            "preferences": getattr(user, 'preferences', {}),
            "skill_level": np.mean([m.mastery_level for m in masteries]) if masteries else 0.5
        }
        
        # Cache del perfil
        self._user_profiles_cache[user_id] = {
            "profile": profile,
            "cached_at": datetime.utcnow()
        }
        
        return profile
    
    async def _apply_contextual_boost(
        self,
        content_groups: Dict,
        context: Dict,
        user_profile: Dict
    ) -> Dict:
        """Aplica boost contextual a las recomendaciones."""
        
        for content_id, group in content_groups.items():
            boost_factor = 1.0
            
            # Boost por contexto temporal
            if "current_time" in context:
                current_hour = context["current_time"].hour
                optimal_hours = user_profile.get("optimal_study_hours", [9, 10, 15, 16])
                if current_hour in optimal_hours:
                    boost_factor *= 1.2
            
            # Boost por tiempo disponible
            if "available_time_minutes" in context:
                content_time = group["content_data"].get("estimated_study_time", 30)
                available_time = context["available_time_minutes"]
                
                if 0.8 <= content_time / available_time <= 1.2:  # Tiempo perfecto
                    boost_factor *= 1.3
                elif content_time <= available_time * 0.5:  # Tiempo sobrado
                    boost_factor *= 1.1
            
            # Boost por especialidad
            if "current_specialty" in context:
                content_specialty = group["content_data"].get("medical_specialty")
                if content_specialty == context["current_specialty"]:
                    boost_factor *= 1.4
            
            group["total_score"] *= boost_factor
            group["contextual_boost"] = boost_factor
        
        return content_groups
    
    def _discretize_difficulty(self, difficulty: float) -> str:
        """Convierte dificultad numérica a categoría discreta."""
        if difficulty < 0.3:
            return "easy"
        elif difficulty < 0.6:
            return "medium"
        elif difficulty < 0.8:
            return "hard"
        else:
            return "expert"
    
    async def _check_prerequisites(self, user_id: str, prerequisites: List[str]) -> bool:
        """Verifica si el usuario cumple los prerequisitos."""
        # Implementación simplificada - en producción consultar mastery real
        return True  # Por ahora asumimos que todos los prerequisitos se cumplen
    
    async def _recently_studied(self, user_id: str, content_id: str) -> bool:
        """Verifica si el contenido fue estudiado recientemente."""
        # Implementación simplificada
        return False  # Por ahora no filtramos por contenido reciente
    
    async def _needs_review(self, user_id: str, content_id: str) -> bool:
        """Verifica si el contenido necesita repaso."""
        # Implementación simplificada
        return True  # Por ahora asumimos que todo necesita repaso
    
    async def _fits_learning_path(self, user_profile: Dict, content_data: Dict) -> bool:
        """Verifica si el contenido encaja en la ruta de aprendizaje."""
        # Implementación simplificada
        return True
    
    def _generate_explanation(self, rec: Dict, user_profile: Dict, rank: int) -> str:
        """Genera explicación para la recomendación."""
        
        reasons = []
        
        # Razones basadas en fuentes
        sources = rec.get("sources", {})
        if "collaborative" in sources:
            reasons.append("usuarios similares también estudiaron este contenido")
        if "content" in sources:
            reasons.append("similar a tu contenido preferido")
        if "knowledge_graph" in sources:
            reasons.append("siguiente paso lógico en tu aprendizaje")
        if "learning_analytics" in sources:
            reasons.append("optimizado según tus patrones de estudio")
        
        # Razones basadas en contexto
        confidence = rec.get("confidence", 0.5)
        if confidence > 0.8:
            reasons.append("alta confianza en la recomendación")
        
        # Combinar razones
        if reasons:
            explanation = f"Recomendado porque {', '.join(reasons)}."
        else:
            explanation = "Contenido relevante para tu perfil de aprendizaje."
        
        return explanation
    
    def _calculate_estimated_benefit(self, rec: Dict, user_profile: Dict) -> float:
        """Calcula el beneficio estimado de la recomendación."""
        
        base_benefit = rec.get("total_score", 0.5)
        confidence = rec.get("confidence", 0.5)
        
        # Ajustar por nivel de usuario
        content_difficulty = rec.get("content_data", {}).get("difficulty", 0.5)
        user_level = user_profile.get("skill_level", 0.5)
        
        # Zona de desarrollo próximo (Vygotsky)
        if 0 <= content_difficulty - user_level <= 0.2:
            difficulty_factor = 1.3  # Dificultad perfecta
        elif content_difficulty < user_level:
            difficulty_factor = 0.7  # Muy fácil
        else:
            difficulty_factor = 0.8  # Muy difícil
        
        estimated_benefit = base_benefit * confidence * difficulty_factor
        return min(1.0, estimated_benefit)
    
    def _calculate_urgency_score(self, rec: Dict, user_profile: Dict) -> float:
        """Calcula la urgencia de la recomendación."""
        
        urgency = 0.5  # Urgencia base
        
        # Aumentar urgencia para áreas débiles
        content_category = rec.get("content_data", {}).get("category", "")
        weak_areas = user_profile.get("knowledge_state", {}).get("weak_areas", [])
        
        if content_category in weak_areas:
            urgency += 0.3
        
        # Aumentar urgencia para recomendaciones de repaso
        if rec.get("recommendation_type") == "review":
            urgency += 0.2
        
        return min(1.0, urgency)
    
    def _extract_personalization_factors(self, rec: Dict, user_profile: Dict) -> Dict[str, Any]:
        """Extrae factores de personalización aplicados."""
        
        return {
            "user_level": user_profile.get("skill_level", 0.5),
            "strong_areas": user_profile.get("knowledge_state", {}).get("strong_areas", []),
            "weak_areas": user_profile.get("knowledge_state", {}).get("weak_areas", []),
            "recent_activity": user_profile.get("study_statistics", {}).get("total_sessions", 0),
            "recommendation_confidence": rec.get("confidence", 0.5)
        }
    
    async def _suggest_alternative_approaches(self, rec: Dict, user_profile: Dict) -> List[str]:
        """Sugiere enfoques alternativos para el contenido."""
        
        alternatives = []
        content_difficulty = rec.get("content_data", {}).get("difficulty", 0.5)
        
        if content_difficulty > 0.7:
            alternatives.extend([
                "Dividir en sesiones más cortas",
                "Buscar contenido de apoyo más básico",
                "Estudiar con técnica Pomodoro"
            ])
        
        if rec.get("content_data", {}).get("category") in ["pharmacology", "pathology"]:
            alternatives.extend([
                "Usar flashcards para memorización",
                "Crear mapas conceptuales",
                "Practicar con casos clínicos"
            ])
        
        return alternatives[:3]  # Limitar a 3 alternativas
    
    async def _generate_fallback_recommendations(
        self,
        user_id: str,
        recommendation_type: str,
        limit: int,
        db: Session
    ) -> List[Dict[str, Any]]:
        """Genera recomendaciones básicas como fallback."""
        
        fallback_recs = [
            {
                "content_id": "basic_anatomy",
                "content_data": {
                    "title": "Anatomía Básica",
                    "category": "anatomy",
                    "difficulty": 0.3
                },
                "total_score": 0.6,
                "explanation": "Recomendación básica para comenzar el estudio",
                "rank": 1
            },
            {
                "content_id": "medical_terminology",
                "content_data": {
                    "title": "Terminología Médica",
                    "category": "general",
                    "difficulty": 0.4
                },
                "total_score": 0.5,
                "explanation": "Fundamental para el estudio médico",
                "rank": 2
            }
        ]
        
        return fallback_recs[:limit]


class CollaborativeFilter:
    """Filtrado colaborativo basado en similitud entre usuarios."""
    
    def __init__(self):
        self.user_similarity_cache = {}
        
    async def recommend(
        self, 
        user_id: str, 
        limit: int,
        context: Optional[Dict],
        db: Session
    ) -> List[Dict[str, Any]]:
        """Recomendaciones basadas en usuarios similares."""
        
        try:
            # Obtener usuarios similares
            similar_users = await self._find_similar_users(user_id, db, top_k=20)
            
            if not similar_users:
                return []
            
            recommendations = []
            
            for similar_user_id, similarity_score in similar_users:
                # Obtener contenido bien evaluado por usuario similar
                positive_content = await self._get_user_positive_content(similar_user_id, db)
                
                # Filtrar contenido ya visto por el usuario target
                user_seen_content = await self._get_user_seen_content(user_id, db)
                
                for content in positive_content:
                    if content["content_id"] not in user_seen_content:
                        recommendations.append({
                            "content_id": content["content_id"],
                            "content_data": content,
                            "score": similarity_score * content.get("rating", 0.5),
                            "reasoning": f"Usuarios con intereses similares también estudiaron este contenido",
                            "source_user_similarity": similarity_score
                        })
            
            # Agregar scores por content_id duplicado
            aggregated = self._aggregate_duplicate_recommendations(recommendations)
            aggregated.sort(key=lambda x: x["score"], reverse=True)
            
            return aggregated[:limit]
            
        except Exception as e:
            logger.error(f"Error in collaborative filtering: {str(e)}")
            return []
    
    async def _find_similar_users(self, user_id: str, db: Session, top_k: int = 20) -> List[Tuple[str, float]]:
        """Encuentra usuarios similares basado en patrones de estudio."""
        
        # Obtener sesiones del usuario
        user_sessions = db.query(LearningSession).filter(
            LearningSession.user_id == user_id
        ).all()
        
        if not user_sessions:
            return []
        
        # Crear perfil de estudio del usuario
        user_profile = self._create_study_profile(user_sessions)
        
        # Obtener otros usuarios con sesiones
        other_users = db.query(LearningSession.user_id).filter(
            LearningSession.user_id != user_id
        ).distinct().all()
        
        similarities = []
        
        for (other_user_id,) in other_users:
            other_sessions = db.query(LearningSession).filter(
                LearningSession.user_id == other_user_id
            ).all()
            
            other_profile = self._create_study_profile(other_sessions)
            similarity = self._calculate_user_similarity(user_profile, other_profile)
            
            if similarity > 0.1:  # Threshold mínimo de similitud
                similarities.append((str(other_user_id), similarity))
        
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]
    
    def _create_study_profile(self, sessions: List[LearningSession]) -> Dict[str, float]:
        """Crea perfil de estudio basado en sesiones."""
        
        if not sessions:
            return {}
        
        # Preferencias de horario
        hours = [s.started_at.hour for s in sessions if s.started_at]
        hour_distribution = {h: hours.count(h) / len(hours) for h in set(hours)} if hours else {}
        
        # Duración promedio de sesión
        durations = [s.duration_seconds or 0 for s in sessions]
        avg_duration = np.mean(durations) if durations else 0
        
        # Tipos de sesión preferidos
        session_types = [s.session_type for s in sessions]
        type_distribution = {t: session_types.count(t) / len(session_types) for t in set(session_types)}
        
        # Efectividad promedio
        effectiveness_scores = [s.effectiveness_score or 0.5 for s in sessions]
        avg_effectiveness = np.mean(effectiveness_scores)
        
        return {
            "hour_distribution": hour_distribution,
            "avg_duration": avg_duration,
            "type_distribution": type_distribution,
            "avg_effectiveness": avg_effectiveness,
            "total_sessions": len(sessions)
        }
    
    def _calculate_user_similarity(self, profile1: Dict, profile2: Dict) -> float:
        """Calcula similitud entre dos perfiles de usuario."""
        
        if not profile1 or not profile2:
            return 0.0
        
        similarities = []
        
        # Similitud de horarios
        hours1 = profile1.get("hour_distribution", {})
        hours2 = profile2.get("hour_distribution", {})
        if hours1 and hours2:
            hour_sim = self._calculate_distribution_similarity(hours1, hours2)
            similarities.append(hour_sim * 0.3)
        
        # Similitud de tipos de sesión
        types1 = profile1.get("type_distribution", {})
        types2 = profile2.get("type_distribution", {})
        if types1 and types2:
            type_sim = self._calculate_distribution_similarity(types1, types2)
            similarities.append(type_sim * 0.4)
        
        # Similitud de duración
        dur1 = profile1.get("avg_duration", 0)
        dur2 = profile2.get("avg_duration", 0)
        if dur1 > 0 and dur2 > 0:
            duration_sim = 1.0 / (1.0 + abs(dur1 - dur2) / max(dur1, dur2))
            similarities.append(duration_sim * 0.2)
        
        # Similitud de efectividad
        eff1 = profile1.get("avg_effectiveness", 0.5)
        eff2 = profile2.get("avg_effectiveness", 0.5)
        effectiveness_sim = 1.0 - abs(eff1 - eff2)
        similarities.append(effectiveness_sim * 0.1)
        
        return sum(similarities) if similarities else 0.0
    
    def _calculate_distribution_similarity(self, dist1: Dict, dist2: Dict) -> float:
        """Calcula similitud entre dos distribuciones."""
        
        all_keys = set(dist1.keys()) | set(dist2.keys())
        if not all_keys:
            return 0.0
        
        # Calcular distancia coseno
        vec1 = [dist1.get(key, 0) for key in all_keys]
        vec2 = [dist2.get(key, 0) for key in all_keys]
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    async def _get_user_positive_content(self, user_id: str, db: Session) -> List[Dict]:
        """Obtiene contenido evaluado positivamente por el usuario."""
        
        # Obtener sesiones con alta efectividad
        good_sessions = db.query(LearningSession).filter(
            LearningSession.user_id == user_id,
            LearningSession.effectiveness_score >= 0.7
        ).all()
        
        positive_content = []
        for session in good_sessions:
            if session.class_session_id:
                positive_content.append({
                    "content_id": str(session.class_session_id),
                    "rating": session.effectiveness_score,
                    "title": f"Session {session.id}",
                    "category": session.session_type
                })
        
        return positive_content
    
    async def _get_user_seen_content(self, user_id: str, db: Session) -> set:
        """Obtiene contenido ya visto por el usuario."""
        
        sessions = db.query(LearningSession).filter(
            LearningSession.user_id == user_id
        ).all()
        
        seen_content = set()
        for session in sessions:
            if session.class_session_id:
                seen_content.add(str(session.class_session_id))
        
        return seen_content
    
    def _aggregate_duplicate_recommendations(self, recommendations: List[Dict]) -> List[Dict]:
        """Agrega recomendaciones duplicadas."""
        
        aggregated = {}
        
        for rec in recommendations:
            content_id = rec["content_id"]
            if content_id not in aggregated:
                aggregated[content_id] = rec.copy()
                aggregated[content_id]["source_count"] = 1
            else:
                # Promediar scores
                existing = aggregated[content_id]
                existing["score"] = (existing["score"] + rec["score"]) / 2
                existing["source_count"] += 1
        
        return list(aggregated.values())


class ContentBasedFilter:
    """Filtrado basado en contenido usando características del material médico."""
    
    def __init__(self):
        if SCIPY_AVAILABLE:
            self.content_vectorizer = TfidfVectorizer(
                max_features=1000,
                stop_words=None,  # Usar stop words personalizadas para italiano médico
                ngram_range=(1, 2)
            )
        self.medical_taxonomy = self._load_medical_taxonomy()
    
    async def recommend(
        self,
        user_profile: Dict,
        recommendation_type: str,
        limit: int,
        context: Optional[Dict],
        db: Session
    ) -> List[Dict[str, Any]]:
        """Recomendaciones basadas en el contenido y perfil del usuario."""
        
        try:
            user_id = user_profile["user_id"]
            
            # Obtener historial de contenido del usuario
            user_content_history = await self._get_user_content_history(user_id, db)
            
            if not user_content_history:
                return await self._get_popular_content(limit, db)
            
            # Crear perfil de preferencias del usuario
            user_content_profile = self._build_user_content_profile(user_content_history)
            
            # Obtener contenido candidato
            candidate_content = await self._get_candidate_content(user_profile, recommendation_type, db)
            
            recommendations = []
            
            for content in candidate_content:
                # Similitud de contenido
                content_similarity = self._calculate_content_similarity(user_content_profile, content)
                
                # Relevancia médica basada en especialidad
                medical_relevance = self._calculate_medical_relevance(content, user_profile)
                
                # Dificultad apropiada
                difficulty_match = self._calculate_difficulty_match(content, user_profile)
                
                # Score compuesto
                final_score = (
                    content_similarity * 0.4 +
                    medical_relevance * 0.4 +
                    difficulty_match * 0.2
                )
                
                recommendations.append({
                    "content_id": content.get("id", f"content_{len(recommendations)}"),
                    "content_data": content,
                    "score": final_score,
                    "reasoning": f"Similar a contenido previamente estudiado con alta efectividad",
                    "similarity_breakdown": {
                        "content_similarity": content_similarity,
                        "medical_relevance": medical_relevance,
                        "difficulty_match": difficulty_match
                    }
                })
            
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]
            
        except Exception as e:
            logger.error(f"Error in content-based filtering: {str(e)}")
            return []
    
    def _load_medical_taxonomy(self) -> Dict:
        """Carga taxonomía médica para clasificación."""
        return {
            "anatomia": {"weight": 0.6, "keywords": ["organo", "sistema", "struttura"]},
            "fisiologia": {"weight": 0.8, "keywords": ["funzione", "processo", "meccanismo"]},
            "patologia": {"weight": 0.9, "keywords": ["malattia", "sintomo", "diagnosi"]},
            "farmacologia": {"weight": 0.95, "keywords": ["farmaco", "medicina", "dosaggio"]},
            "clinica": {"weight": 0.85, "keywords": ["paziente", "trattamento", "terapia"]}
        }
    
    async def _get_user_content_history(self, user_id: str, db: Session) -> List[Dict]:
        """Obtiene historial de contenido del usuario."""
        
        # Obtener sesiones con alta efectividad
        effective_sessions = db.query(LearningSession).filter(
            LearningSession.user_id == user_id,
            LearningSession.effectiveness_score >= 0.6
        ).order_by(LearningSession.created_at.desc()).limit(20).all()
        
        content_history = []
        for session in effective_sessions:
            content_history.append({
                "session_id": str(session.id),
                "session_type": session.session_type,
                "effectiveness": session.effectiveness_score,
                "duration": session.duration_seconds,
                "metadata": session.metadata or {}
            })
        
        return content_history
    
    def _build_user_content_profile(self, content_history: List[Dict]) -> Dict:
        """Construye perfil de contenido del usuario."""
        
        if not content_history:
            return {}
        
        # Preferencias de tipo de sesión
        session_types = [item["session_type"] for item in content_history]
        type_preferences = {t: session_types.count(t) / len(session_types) for t in set(session_types)}
        
        # Duración preferida
        durations = [item.get("duration", 0) for item in content_history if item.get("duration")]
        avg_duration = np.mean(durations) if durations else 1800  # 30 min default
        
        # Efectividad promedio por tipo
        effectiveness_by_type = {}
        for session_type in set(session_types):
            type_sessions = [item for item in content_history if item["session_type"] == session_type]
            avg_eff = np.mean([s.get("effectiveness", 0.5) for s in type_sessions])
            effectiveness_by_type[session_type] = avg_eff
        
        return {
            "type_preferences": type_preferences,
            "preferred_duration": avg_duration,
            "effectiveness_by_type": effectiveness_by_type,
            "total_sessions": len(content_history)
        }
    
    async def _get_candidate_content(self, user_profile: Dict, recommendation_type: str, db: Session) -> List[Dict]:
        """Obtiene contenido candidato para recomendación."""
        
        # Simular contenido disponible - en producción vendría de base de datos
        candidate_content = [
            {
                "id": "anatomy_cardiovascular",
                "title": "Sistema Cardiovascular",
                "category": "anatomia",
                "difficulty": 0.5,
                "medical_specialty": "cardiologia",
                "estimated_duration": 45,
                "keywords": ["corazón", "vascular", "circulación"]
            },
            {
                "id": "physiology_respiratory",
                "title": "Fisiología Respiratoria",
                "category": "fisiologia",
                "difficulty": 0.7,
                "medical_specialty": "neumologia",
                "estimated_duration": 60,
                "keywords": ["respiración", "pulmón", "oxígeno"]
            },
            {
                "id": "pathology_diabetes",
                "title": "Diabetes Mellitus",
                "category": "patologia",
                "difficulty": 0.8,
                "medical_specialty": "endocrinologia",
                "estimated_duration": 90,
                "keywords": ["diabetes", "glucosa", "insulina"]
            }
        ]
        
        return candidate_content
    
    async def _get_popular_content(self, limit: int, db: Session) -> List[Dict]:
        """Obtiene contenido popular como fallback."""
        
        # Contenido popular por defecto
        popular_content = [
            {
                "content_id": "intro_anatomy",
                "content_data": {
                    "title": "Introducción a la Anatomía",
                    "category": "anatomia",
                    "difficulty": 0.3
                },
                "score": 0.7,
                "reasoning": "Contenido popular entre estudiantes de medicina"
            }
        ]
        
        return popular_content[:limit]
    
    def _calculate_content_similarity(self, user_profile: Dict, content: Dict) -> float:
        """Calcula similitud de contenido."""
        
        if not user_profile:
            return 0.5
        
        # Similitud basada en tipo de contenido
        content_category = content.get("category", "unknown")
        type_preferences = user_profile.get("type_preferences", {})
        
        # Si el usuario ha estudiado esta categoría antes
        if content_category in type_preferences:
            type_similarity = type_preferences[content_category]
        else:
            type_similarity = 0.3  # Penalty por categoría nueva
        
        # Similitud basada en duración
        content_duration = content.get("estimated_duration", 30)
        preferred_duration = user_profile.get("preferred_duration", 1800) / 60  # Convertir a minutos
        
        duration_similarity = 1.0 / (1.0 + abs(content_duration - preferred_duration) / max(content_duration, preferred_duration))
        
        # Score compuesto
        similarity = type_similarity * 0.7 + duration_similarity * 0.3
        return min(1.0, similarity)
    
    def _calculate_medical_relevance(self, content: Dict, user_profile: Dict) -> float:
        """Calcula relevancia médica del contenido."""
        
        # Relevancia basada en áreas de fortaleza/debilidad
        content_category = content.get("category", "unknown")
        strong_areas = user_profile.get("knowledge_state", {}).get("strong_areas", [])
        weak_areas = user_profile.get("knowledge_state", {}).get("weak_areas", [])
        
        if content_category in weak_areas:
            relevance = 0.9  # Alta relevancia para áreas débiles
        elif content_category in strong_areas:
            relevance = 0.6  # Menor relevancia para áreas fuertes
        else:
            relevance = 0.7  # Relevancia neutra
        
        # Ajustar por especialidad médica si coincide con rol
        user_role = user_profile.get("role", "student")
        content_specialty = content.get("medical_specialty", "")
        
        if user_role in ["doctor", "resident"] and content_specialty:
            relevance *= 1.2  # Boost para profesionales
        
        return min(1.0, relevance)
    
    def _calculate_difficulty_match(self, content: Dict, user_profile: Dict) -> float:
        """Calcula qué tan apropiada es la dificultad."""
        
        content_difficulty = content.get("difficulty", 0.5)
        user_level = user_profile.get("skill_level", 0.5)
        
        # Zona de desarrollo próximo (ligeramente más difícil que el nivel actual)
        optimal_difficulty_range = (user_level - 0.1, user_level + 0.3)
        
        if optimal_difficulty_range[0] <= content_difficulty <= optimal_difficulty_range[1]:
            return 1.0  # Dificultad perfecta
        elif content_difficulty < user_level - 0.2:
            return 0.6  # Muy fácil
        elif content_difficulty > user_level + 0.4:
            return 0.4  # Muy difícil
        else:
            return 0.8  # Aceptable
        
        
class KnowledgeGraphRecommender:
    """Recomendaciones basadas en grafo de conocimiento médico."""
    
    def __init__(self):
        self.concept_graph = self._build_concept_graph()
    
    async def recommend(
        self,
        user_id: str,
        user_profile: Dict,
        limit: int,
        context: Optional[Dict],
        db: Session
    ) -> List[Dict[str, Any]]:
        """Recomendaciones basadas en estructura del grafo de conocimiento."""
        
        try:
            # Obtener estado actual de conocimiento del usuario
            user_knowledge_state = await self._get_user_knowledge_state(user_id, db)
            
            # Identificar gaps en el conocimiento
            knowledge_gaps = self._identify_knowledge_gaps(user_knowledge_state)
            
            # Encontrar rutas de aprendizaje óptimas
            learning_paths = self._find_optimal_learning_paths(user_knowledge_state, knowledge_gaps)
            
            recommendations = []
            
            for path in learning_paths[:3]:  # Top 3 rutas
                for step in path["steps"][:5]:  # Top 5 pasos por ruta
                    concept_name = step["concept_name"]
                    
                    # Simular contenido para el concepto
                    content = self._get_content_for_concept(concept_name)
                    
                    if content:
                        # Score basado en posición en la ruta y relevancia
                        position_score = 1.0 / (step["position"] + 1)  # Más alto para pasos tempranos
                        relevance_score = step["relevance_score"]
                        prerequisite_readiness = step["prerequisite_readiness"]
                        
                        final_score = (
                            position_score * 0.3 +
                            relevance_score * 0.4 +
                            prerequisite_readiness * 0.3
                        )
                        
                        recommendations.append({
                            "content_id": content["id"],
                            "content_data": content,
                            "score": final_score,
                            "reasoning": f"Siguiente paso óptimo en ruta de aprendizaje: {path['name']}",
                            "learning_path_info": {
                                "path_name": path["name"],
                                "step_position": step["position"],
                                "total_steps": len(path["steps"]),
                                "concept_name": concept_name,
                                "prerequisites_met": step["prerequisite_readiness"] > 0.7
                            }
                        })
            
            recommendations.sort(key=lambda x: x["score"], reverse=True)
            return recommendations[:limit]
            
        except Exception as e:
            logger.error(f"Error in knowledge graph recommendations: {str(e)}")
            return []
    
    def _build_concept_graph(self) -> Dict:
        """Construye grafo simplificado de conceptos médicos."""
        
        # Grafo simplificado - en producción sería mucho más complejo
        return {
            "nodes": {
                "anatomia_basica": {"difficulty": 0.3, "category": "anatomia"},
                "fisiologia_celular": {"difficulty": 0.5, "category": "fisiologia", "prerequisites": ["anatomia_basica"]},
                "patologia_general": {"difficulty": 0.7, "category": "patologia", "prerequisites": ["fisiologia_celular"]},
                "farmacologia_basica": {"difficulty": 0.8, "category": "farmacologia", "prerequisites": ["patologia_general"]},
                "clinica_medica": {"difficulty": 0.9, "category": "clinica", "prerequisites": ["farmacologia_basica"]}
            },
            "paths": {
                "medicina_general": ["anatomia_basica", "fisiologia_celular", "patologia_general", "farmacologia_basica", "clinica_medica"],
                "ciencias_basicas": ["anatomia_basica", "fisiologia_celular"],
                "aplicacion_clinica": ["patologia_general", "farmacologia_basica", "clinica_medica"]
            }
        }
    
    async def _get_user_knowledge_state(self, user_id: str, db: Session) -> Dict:
        """Obtiene estado de conocimiento del usuario."""
        
        masteries = db.query(ConceptMastery).filter(
            ConceptMastery.user_id == user_id
        ).all()
        
        knowledge_state = {}
        for mastery in masteries:
            concept_name = mastery.concept.name if mastery.concept else f"concept_{mastery.concept_id}"
            knowledge_state[concept_name] = {
                "mastery_level": mastery.mastery_level,
                "confidence": mastery.confidence_score,
                "last_studied": mastery.last_studied_at
            }
        
        return knowledge_state
    
    def _identify_knowledge_gaps(self, knowledge_state: Dict) -> List[str]:
        """Identifica gaps en el conocimiento."""
        
        gaps = []
        graph_concepts = self.concept_graph["nodes"].keys()
        
        for concept in graph_concepts:
            if concept not in knowledge_state or knowledge_state[concept]["mastery_level"] < 0.7:
                gaps.append(concept)
        
        return gaps
    
    def _find_optimal_learning_paths(self, knowledge_state: Dict, gaps: List[str]) -> List[Dict]:
        """Encuentra rutas de aprendizaje óptimas."""
        
        paths = []
        
        for path_name, path_concepts in self.concept_graph["paths"].items():
            # Calcular progreso en esta ruta
            completed_concepts = sum(
                1 for concept in path_concepts 
                if concept in knowledge_state and knowledge_state[concept]["mastery_level"] >= 0.7
            )
            
            progress = completed_concepts / len(path_concepts)
            
            # Encontrar próximo concepto a estudiar
            next_concepts = []
            for i, concept in enumerate(path_concepts):
                if concept in gaps:
                    # Verificar si prerrequisitos están cumplidos
                    prerequisites = self.concept_graph["nodes"][concept].get("prerequisites", [])
                    prerequisites_met = all(
                        prereq in knowledge_state and knowledge_state[prereq]["mastery_level"] >= 0.7
                        for prereq in prerequisites
                    )
                    
                    readiness = 1.0 if prerequisites_met else 0.3
                    relevance = 1.0 - (i / len(path_concepts))  # Conceptos tempranos más relevantes
                    
                    next_concepts.append({
                        "concept_name": concept,
                        "position": i,
                        "relevance_score": relevance,
                        "prerequisite_readiness": readiness
                    })
            
            if next_concepts:
                paths.append({
                    "name": path_name,
                    "progress": progress,
                    "steps": next_concepts,
                    "priority": progress + len(next_concepts) * 0.1  # Boost para rutas con más oportunidades
                })
        
        paths.sort(key=lambda x: x["priority"], reverse=True)
        return paths
    
    def _get_content_for_concept(self, concept_name: str) -> Optional[Dict]:
        """Obtiene contenido para un concepto específico."""
        
        # Mapeo simplificado concepto -> contenido
        content_mapping = {
            "anatomia_basica": {
                "id": "anatomy_intro",
                "title": "Introducción a la Anatomía",
                "category": "anatomia",
                "difficulty": 0.3
            },
            "fisiologia_celular": {
                "id": "cell_physiology",
                "title": "Fisiología Celular",
                "category": "fisiologia", 
                "difficulty": 0.5
            },
            "patologia_general": {
                "id": "general_pathology",
                "title": "Patología General",
                "category": "patologia",
                "difficulty": 0.7
            }
        }
        
        return content_mapping.get(concept_name)
