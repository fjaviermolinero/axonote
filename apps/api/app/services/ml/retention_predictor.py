"""
Retention Predictor - Modelo de ML para predicción de retención de conocimiento

Este módulo implementa modelos de deep learning para predecir la retención
de conocimiento médico y optimizar los horarios de repaso.
"""

from typing import Dict, List, Tuple, Optional, Any
import asyncio
import logging
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from sklearn.preprocessing import StandardScaler
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    # Fallback para cuando torch no esté disponible
    class nn:
        class Module:
            def __init__(self): pass
        class Linear:
            def __init__(self, *args, **kwargs): pass
        class ReLU:
            def __init__(self): pass
        class Dropout:
            def __init__(self, *args): pass
        class LSTM:
            def __init__(self, *args, **kwargs): pass
        class Sigmoid:
            def __init__(self): pass

from app.models.analytics import ConceptMastery, LearningSession
from app.core.config import settings

logger = logging.getLogger(__name__)


class RetentionPredictor(nn.Module if TORCH_AVAILABLE else object):
    """
    Modelo de deep learning para predicción de retención de conocimiento.
    
    Basado en:
    - Ebbinghaus forgetting curve
    - Spaced repetition research  
    - Individual learning patterns
    - Medical knowledge specifics
    
    Architecture:
    - User feature encoder
    - Content feature encoder
    - Temporal LSTM for dynamics
    - Retention probability predictor
    - Optimal timing predictor
    """
    
    def __init__(self, feature_dim: int = 64, hidden_dim: int = 128):
        if TORCH_AVAILABLE:
            super(RetentionPredictor, self).__init__()
        
        self.feature_dim = feature_dim
        self.hidden_dim = hidden_dim
        self.is_trained = False
        
        if TORCH_AVAILABLE:
            self._build_model()
        else:
            logger.warning("PyTorch not available. Using simplified retention prediction.")
            self.scaler = None
    
    def _build_model(self):
        """Construye la arquitectura del modelo."""
        
        # Encoder para features del usuario
        self.user_encoder = nn.Sequential(
            nn.Linear(self.feature_dim, self.hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(self.hidden_dim, self.hidden_dim // 2),
            nn.ReLU()
        )
        
        # Encoder para features del contenido
        self.content_encoder = nn.Sequential(
            nn.Linear(self.feature_dim, self.hidden_dim),
            nn.ReLU(), 
            nn.Dropout(0.3),
            nn.Linear(self.hidden_dim, self.hidden_dim // 2),
            nn.ReLU()
        )
        
        # LSTM para modelar dinámicas temporales
        self.temporal_lstm = nn.LSTM(
            input_size=self.hidden_dim,
            hidden_size=self.hidden_dim,
            num_layers=2,
            batch_first=True,
            dropout=0.3
        )
        
        # Predictor de retención
        self.retention_predictor = nn.Sequential(
            nn.Linear(self.hidden_dim + self.hidden_dim // 2, self.hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(self.hidden_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Sigmoid()  # Probabilidad de retención [0,1]
        )
        
        # Predictor de tiempo óptimo
        self.timing_predictor = nn.Sequential(
            nn.Linear(self.hidden_dim + self.hidden_dim // 2, self.hidden_dim),
            nn.ReLU(),
            nn.Linear(self.hidden_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.ReLU()  # Días hasta próxima revisión
        )
    
    def forward(self, user_features, content_features, temporal_sequence):
        """Forward pass del modelo."""
        if not TORCH_AVAILABLE:
            return None, None
            
        # Encode features
        user_encoded = self.user_encoder(user_features)
        content_encoded = self.content_encoder(content_features)
        
        # Process temporal dynamics
        temporal_output, (h_n, c_n) = self.temporal_lstm(temporal_sequence)
        temporal_features = h_n[-1]  # Last hidden state
        
        # Combine all features
        combined_features = torch.cat([
            user_encoded, 
            content_encoded, 
            temporal_features
        ], dim=-1)
        
        # Predict retention and optimal timing
        retention_prob = self.retention_predictor(combined_features)
        optimal_timing = self.timing_predictor(combined_features)
        
        return retention_prob, optimal_timing
    
    async def predict_retention(
        self, 
        user_id: str,
        concept_updates: Dict,
        db: Session
    ) -> Dict[str, Dict[str, Any]]:
        """
        Predice probabilidad de retención para conceptos actualizados.
        
        Args:
            user_id: ID del usuario
            concept_updates: Diccionario con actualizaciones de conceptos
            db: Sesión de base de datos
            
        Returns:
            Predicciones de retención por concepto
        """
        logger.info(f"Predicting retention for user {user_id}, {len(concept_updates)} concepts")
        
        predictions = {}
        
        try:
            for concept_id, mastery_data in concept_updates.items():
                if TORCH_AVAILABLE and self.is_trained:
                    # Usar modelo ML entrenado
                    prediction = await self._ml_prediction(user_id, concept_id, mastery_data, db)
                else:
                    # Usar heurística basada en research
                    prediction = await self._heuristic_prediction(user_id, concept_id, mastery_data, db)
                
                predictions[concept_id] = prediction
                
        except Exception as e:
            logger.error(f"Error predicting retention: {str(e)}")
            # Fallback a predicciones por defecto
            for concept_id, mastery_data in concept_updates.items():
                predictions[concept_id] = self._default_prediction(mastery_data)
        
        return predictions
    
    async def _ml_prediction(
        self, 
        user_id: str, 
        concept_id: str, 
        mastery_data: Dict,
        db: Session
    ) -> Dict[str, Any]:
        """Predicción usando modelo ML entrenado."""
        
        if not TORCH_AVAILABLE:
            return await self._heuristic_prediction(user_id, concept_id, mastery_data, db)
        
        try:
            # Preparar features
            user_features = await self._extract_user_features(user_id, db)
            content_features = await self._extract_content_features(concept_id, db)
            temporal_sequence = await self._extract_temporal_sequence(user_id, concept_id, db)
            
            # Convertir a tensores
            user_tensor = torch.tensor(user_features, dtype=torch.float32)
            content_tensor = torch.tensor(content_features, dtype=torch.float32)
            temporal_tensor = torch.tensor(temporal_sequence, dtype=torch.float32)
            
            # Predicción
            with torch.no_grad():
                retention_prob, optimal_timing = self.forward(
                    user_tensor.unsqueeze(0),
                    content_tensor.unsqueeze(0), 
                    temporal_tensor.unsqueeze(0)
                )
                
            return {
                "retention_probability": float(retention_prob.item()),
                "optimal_review_days": max(1.0, float(optimal_timing.item())),
                "confidence_score": mastery_data.get("confidence", 0.5),
                "next_review_date": (
                    datetime.utcnow() + timedelta(days=float(optimal_timing.item()))
                ).isoformat(),
                "prediction_method": "ml_model"
            }
            
        except Exception as e:
            logger.warning(f"ML prediction failed for concept {concept_id}: {str(e)}. Using heuristic.")
            return await self._heuristic_prediction(user_id, concept_id, mastery_data, db)
    
    async def _heuristic_prediction(
        self, 
        user_id: str, 
        concept_id: str, 
        mastery_data: Dict,
        db: Session
    ) -> Dict[str, Any]:
        """
        Predicción usando heurísticas basadas en research de spaced repetition.
        
        Basado en:
        - Algoritmo SM-2 (SuperMemo)
        - Curva de olvido de Ebbinghaus
        - Factores de dificultad individuales
        """
        
        # Obtener datos históricos del concepto
        mastery = db.query(ConceptMastery).filter(
            ConceptMastery.user_id == user_id,
            ConceptMastery.concept_id == concept_id
        ).first()
        
        # Factores base para el cálculo
        current_mastery = mastery_data.get("new_mastery_level", 0.5) if mastery_data else (mastery.mastery_level if mastery else 0.5)
        study_count = mastery.study_count if mastery else 1
        forgetting_rate = mastery.forgetting_rate if mastery else 0.3
        
        # Calcular probabilidad de retención basada en mastery level
        retention_probability = self._calculate_retention_probability(
            current_mastery, study_count, forgetting_rate
        )
        
        # Calcular días óptimos para próxima revisión
        optimal_days = self._calculate_optimal_review_interval(
            current_mastery, study_count, retention_probability
        )
        
        return {
            "retention_probability": retention_probability,
            "optimal_review_days": optimal_days,
            "confidence_score": min(1.0, study_count / 5),  # Más estudios = más confianza
            "next_review_date": (datetime.utcnow() + timedelta(days=optimal_days)).isoformat(),
            "prediction_method": "heuristic",
            "factors": {
                "mastery_level": current_mastery,
                "study_count": study_count,
                "forgetting_rate": forgetting_rate
            }
        }
    
    def _calculate_retention_probability(
        self, 
        mastery_level: float, 
        study_count: int, 
        forgetting_rate: float
    ) -> float:
        """
        Calcula probabilidad de retención basada en modelo de Ebbinghaus.
        
        Formula adaptada: R(t) = e^(-forgetting_rate * t / mastery_level)
        donde t = días desde último estudio
        """
        
        # Tiempo asumido desde último estudio (1 día para predicción actual)
        t = 1.0
        
        # Ajustar forgetting rate basado en mastery
        adjusted_forgetting_rate = forgetting_rate * (1.0 - mastery_level * 0.5)
        
        # Calcular retención usando curva exponencial modificada
        retention = np.exp(-adjusted_forgetting_rate * t / max(0.1, mastery_level))
        
        # Bonus por repeticiones (spaced repetition effect)
        repetition_bonus = min(0.3, study_count * 0.05)
        retention = min(1.0, retention + repetition_bonus)
        
        return float(retention)
    
    def _calculate_optimal_review_interval(
        self, 
        mastery_level: float, 
        study_count: int, 
        retention_probability: float
    ) -> float:
        """
        Calcula el intervalo óptimo para la próxima revisión.
        
        Basado en algoritmo SM-2 modificado para contexto médico.
        """
        
        # Intervalos base según número de repeticiones
        base_intervals = [1, 2, 4, 8, 15, 30, 60, 120]
        
        # Seleccionar intervalo base
        interval_index = min(study_count - 1, len(base_intervals) - 1)
        base_interval = base_intervals[interval_index]
        
        # Ajustar basado en mastery level
        mastery_factor = 0.5 + mastery_level  # [0.5, 1.5]
        
        # Ajustar basado en retention probability
        retention_factor = 0.7 + retention_probability * 0.6  # [0.7, 1.3]
        
        # Calcular intervalo final
        optimal_interval = base_interval * mastery_factor * retention_factor
        
        # Límites para contexto médico
        optimal_interval = max(1.0, min(180.0, optimal_interval))  # Entre 1 día y 6 meses
        
        return float(optimal_interval)
    
    def _default_prediction(self, mastery_data: Dict) -> Dict[str, Any]:
        """Predicción por defecto cuando fallan otros métodos."""
        
        mastery_level = mastery_data.get("new_mastery_level", 0.5)
        
        return {
            "retention_probability": 0.7,  # Conservativo
            "optimal_review_days": 3.0,    # Revisión frecuente por defecto
            "confidence_score": 0.3,       # Baja confianza
            "next_review_date": (datetime.utcnow() + timedelta(days=3)).isoformat(),
            "prediction_method": "default",
            "note": "Using default prediction due to insufficient data"
        }
    
    async def _extract_user_features(self, user_id: str, db: Session) -> List[float]:
        """Extrae features del usuario para el modelo ML."""
        
        # Obtener sesiones recientes del usuario
        recent_sessions = db.query(LearningSession).filter(
            LearningSession.user_id == user_id,
            LearningSession.created_at >= datetime.utcnow() - timedelta(days=30)
        ).all()
        
        # Features básicas del usuario
        features = [
            len(recent_sessions),  # Número de sesiones recientes
            np.mean([s.duration_seconds or 0 for s in recent_sessions]) / 3600 if recent_sessions else 0,  # Duración promedio (horas)
            np.mean([s.effectiveness_score or 0.5 for s in recent_sessions]) if recent_sessions else 0.5,  # Efectividad promedio
            np.mean([s.engagement_score or 0.5 for s in recent_sessions]) if recent_sessions else 0.5,  # Engagement promedio
            np.std([s.effectiveness_score or 0.5 for s in recent_sessions]) if len(recent_sessions) > 1 else 0.1,  # Consistencia
        ]
        
        # Padding para llegar al feature_dim requerido
        while len(features) < self.feature_dim:
            features.append(0.0)
        
        return features[:self.feature_dim]
    
    async def _extract_content_features(self, concept_id: str, db: Session) -> List[float]:
        """Extrae features del contenido/concepto para el modelo ML."""
        
        from app.models.analytics import KnowledgeConcept
        
        # Obtener información del concepto
        concept = db.query(KnowledgeConcept).filter(
            KnowledgeConcept.id == concept_id
        ).first()
        
        if not concept:
            # Features por defecto para concepto desconocido
            return [0.5] * self.feature_dim
        
        # Features del concepto
        features = [
            concept.difficulty_base,  # Dificultad base
            len(concept.prerequisites or []) / 10.0,  # Número de prerrequisitos normalizado
            1.0 if concept.medical_specialty else 0.0,  # Tiene especialidad
            len(concept.learning_objectives or []) / 5.0 if concept.learning_objectives else 0.0,  # Objetivos normalizados
        ]
        
        # Mapear categoría a feature numérica
        category_mapping = {
            "anatomy": 0.2,
            "physiology": 0.4,
            "pathology": 0.6,
            "pharmacology": 0.8,
            "clinical": 1.0
        }
        features.append(category_mapping.get(concept.category, 0.5))
        
        # Padding para llegar al feature_dim requerido
        while len(features) < self.feature_dim:
            features.append(0.0)
        
        return features[:self.feature_dim]
    
    async def _extract_temporal_sequence(
        self, 
        user_id: str, 
        concept_id: str, 
        db: Session
    ) -> List[List[float]]:
        """Extrae secuencia temporal para el LSTM."""
        
        # Obtener sesiones donde se estudió este concepto
        sessions = db.query(LearningSession).filter(
            LearningSession.user_id == user_id,
            LearningSession.created_at >= datetime.utcnow() - timedelta(days=90)
        ).order_by(LearningSession.created_at).all()
        
        # Crear secuencia temporal (últimas 10 sesiones)
        sequence = []
        for session in sessions[-10:]:
            # Features temporales de cada sesión
            session_features = [
                session.effectiveness_score or 0.5,
                session.engagement_score or 0.5,
                session.attention_score or 0.5,
                (session.duration_seconds or 0) / 3600,  # Duración en horas
            ]
            
            # Padding hasta hidden_dim
            while len(session_features) < self.hidden_dim:
                session_features.append(0.0)
            
            sequence.append(session_features[:self.hidden_dim])
        
        # Si no hay suficientes sesiones, rellenar con ceros
        while len(sequence) < 10:
            sequence.insert(0, [0.0] * self.hidden_dim)
        
        return sequence
    
    async def train_model(
        self, 
        training_data: List[Dict], 
        epochs: int = 100,
        learning_rate: float = 0.001
    ) -> Dict[str, Any]:
        """
        Entrena el modelo de predicción de retención.
        
        Args:
            training_data: Datos de entrenamiento con features y targets
            epochs: Número de épocas de entrenamiento
            learning_rate: Tasa de aprendizaje
            
        Returns:
            Métricas de entrenamiento
        """
        
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch not available. Cannot train ML model.")
            return {"error": "PyTorch not available"}
        
        logger.info(f"Training retention predictor with {len(training_data)} samples")
        
        try:
            # Preparar datos de entrenamiento
            user_features_list = []
            content_features_list = []
            temporal_sequences_list = []
            retention_targets = []
            timing_targets = []
            
            for sample in training_data:
                user_features_list.append(sample["user_features"])
                content_features_list.append(sample["content_features"])
                temporal_sequences_list.append(sample["temporal_sequence"])
                retention_targets.append(sample["retention_target"])
                timing_targets.append(sample["timing_target"])
            
            # Convertir a tensores
            user_features = torch.tensor(user_features_list, dtype=torch.float32)
            content_features = torch.tensor(content_features_list, dtype=torch.float32)
            temporal_sequences = torch.tensor(temporal_sequences_list, dtype=torch.float32)
            retention_targets = torch.tensor(retention_targets, dtype=torch.float32).unsqueeze(1)
            timing_targets = torch.tensor(timing_targets, dtype=torch.float32).unsqueeze(1)
            
            # Configurar optimizador y loss
            optimizer = torch.optim.Adam(self.parameters(), lr=learning_rate)
            mse_loss = nn.MSELoss()
            bce_loss = nn.BCELoss()
            
            # Entrenamiento
            train_losses = []
            
            for epoch in range(epochs):
                optimizer.zero_grad()
                
                # Forward pass
                retention_pred, timing_pred = self.forward(
                    user_features, content_features, temporal_sequences
                )
                
                # Calcular losses
                retention_loss = bce_loss(retention_pred, retention_targets)
                timing_loss = mse_loss(timing_pred, timing_targets)
                total_loss = retention_loss + timing_loss
                
                # Backward pass
                total_loss.backward()
                optimizer.step()
                
                train_losses.append(total_loss.item())
                
                if (epoch + 1) % 20 == 0:
                    logger.info(f"Epoch {epoch + 1}/{epochs}, Loss: {total_loss.item():.4f}")
            
            self.is_trained = True
            
            return {
                "training_completed": True,
                "epochs": epochs,
                "final_loss": train_losses[-1],
                "average_loss": np.mean(train_losses),
                "samples_trained": len(training_data)
            }
            
        except Exception as e:
            logger.error(f"Error training retention predictor: {str(e)}")
            return {"error": str(e)}
    
    def save_model(self, path: str) -> bool:
        """Guarda el modelo entrenado."""
        
        if not TORCH_AVAILABLE or not self.is_trained:
            return False
        
        try:
            torch.save({
                'model_state_dict': self.state_dict(),
                'feature_dim': self.feature_dim,
                'hidden_dim': self.hidden_dim,
                'is_trained': self.is_trained
            }, path)
            
            logger.info(f"Model saved to {path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving model: {str(e)}")
            return False
    
    def load_model(self, path: str) -> bool:
        """Carga un modelo entrenado."""
        
        if not TORCH_AVAILABLE:
            return False
        
        try:
            checkpoint = torch.load(path, map_location='cpu')
            
            self.feature_dim = checkpoint['feature_dim']
            self.hidden_dim = checkpoint['hidden_dim']
            self._build_model()  # Reconstruir arquitectura
            
            self.load_state_dict(checkpoint['model_state_dict'])
            self.is_trained = checkpoint['is_trained']
            
            logger.info(f"Model loaded from {path}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading model: {str(e)}")
            return False
