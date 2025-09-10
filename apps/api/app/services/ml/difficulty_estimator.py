"""
Difficulty Estimator - Estimador de dificultad de contenido médico

Este módulo implementa algoritmos para estimar la dificultad del contenido
médico basado en múltiples factores y personalización por usuario.
"""

from typing import Dict, List, Tuple, Optional, Any
import re
import logging
import numpy as np
from collections import Counter
from sqlalchemy.orm import Session

from app.models.analytics import KnowledgeConcept, ConceptMastery
from app.models.user import User

logger = logging.getLogger(__name__)


class DifficultyEstimator:
    """
    Estimador de dificultad de contenido usando múltiples métricas.
    
    Capabilities:
    - Análisis léxico y sintáctico
    - Clasificación por especialidad médica
    - Evaluación de complejidad conceptual
    - Personalización basada en perfil del usuario
    - Predicción de tiempo de estudio requerido
    """
    
    def __init__(self):
        # Pesos de complejidad por especialidad médica
        self.medical_complexity_weights = {
            "anatomia": 0.6,      # Moderada - visual y estructural
            "fisiologia": 0.8,    # Alta - procesos complejos
            "patologia": 0.9,     # Muy alta - diagnosis diferencial
            "farmacologia": 0.95, # Máxima - interacciones complejas
            "procedimientos": 0.7, # Moderada-alta - pasos secuenciales
            "clinica": 0.85,      # Alta - toma decisiones
            "cirugia": 0.8,       # Alta - precisión técnica
            "pediatria": 0.75,    # Moderada-alta - casos especiales
            "geriatria": 0.75,    # Moderada-alta - comorbilidades
            "emergencias": 0.9    # Muy alta - decisiones rápidas
        }
        
        # Base de datos de términos médicos por complejidad
        self.medical_terms_database = self._load_medical_terms_database()
        
        # Patrones sintácticos complejos
        self.complexity_patterns = {
            "conditional_statements": r'\b(si|cuando|en caso de|dependiendo|según|a menos que)\b',
            "temporal_sequences": r'\b(antes|después|durante|mientras|simultaneamente|posteriormente)\b',
            "causal_relationships": r'\b(debido a|causado por|resulta en|provoca|induce|desencadena)\b',
            "quantitative_expressions": r'\d+[.,]\d+|[\d]+\s*(mg|ml|gr|kg|años|días|horas|minutos)',
            "medical_abbreviations": r'\b[A-Z]{2,5}\b',
            "dosage_instructions": r'\b(\d+\s*(veces|dosis)|(cada|c/)\s*\d+\s*(horas|h|días|d))\b'
        }
    
    async def estimate_content_difficulty(
        self, 
        content: Dict[str, Any],
        user_profile: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Estima dificultad del contenido para un usuario específico.
        
        Args:
            content: Diccionario con el contenido a analizar
            user_profile: Perfil del usuario para personalización
            
        Returns:
            Análisis detallado de dificultad con múltiples métricas
        """
        logger.info(f"Estimating difficulty for content: {content.get('title', 'Unknown')}")
        
        try:
            text = content.get("text", "")
            if not text:
                return self._default_difficulty_analysis()
            
            # Análisis léxico del contenido
            lexical_difficulty = self._analyze_lexical_complexity(text)
            
            # Dificultad médica por categoría
            medical_difficulty = self._analyze_medical_complexity(content)
            
            # Dificultad conceptual
            conceptual_difficulty = self._analyze_conceptual_complexity(content)
            
            # Dificultad sintáctica
            syntactic_difficulty = self._analyze_syntactic_complexity(text)
            
            # Dificultad por densidad de información
            information_density = self._analyze_information_density(text)
            
            # Personalización basada en perfil del usuario
            if user_profile:
                personalized_difficulty = self._personalize_difficulty(
                    {
                        "lexical": lexical_difficulty,
                        "medical": medical_difficulty, 
                        "conceptual": conceptual_difficulty,
                        "syntactic": syntactic_difficulty,
                        "information_density": information_density
                    },
                    user_profile
                )
            else:
                # Sin personalización, usar promedio ponderado
                personalized_difficulty = self._calculate_base_difficulty(
                    lexical_difficulty, medical_difficulty, conceptual_difficulty,
                    syntactic_difficulty, information_density
                )
            
            return {
                "overall_difficulty": personalized_difficulty["overall"],
                "difficulty_breakdown": {
                    "lexical_difficulty": lexical_difficulty,
                    "medical_difficulty": medical_difficulty,
                    "conceptual_difficulty": conceptual_difficulty,
                    "syntactic_difficulty": syntactic_difficulty,
                    "information_density": information_density
                },
                "estimated_study_time_minutes": personalized_difficulty["study_time_minutes"],
                "prerequisite_concepts": self._identify_prerequisites(content),
                "difficulty_factors": personalized_difficulty["factors"],
                "complexity_indicators": self._identify_complexity_indicators(text),
                "recommendations": self._generate_study_recommendations(personalized_difficulty),
                "confidence_score": 0.8  # Confianza en la estimación
            }
            
        except Exception as e:
            logger.error(f"Error estimating content difficulty: {str(e)}")
            return self._default_difficulty_analysis()
    
    def _analyze_lexical_complexity(self, text: str) -> float:
        """Analiza complejidad léxica del texto médico."""
        
        if not text:
            return 0.0
        
        words = self._tokenize_text(text)
        if not words:
            return 0.0
        
        # Longitud promedio de palabras
        avg_word_length = sum(len(word) for word in words) / len(words)
        word_length_score = min(1.0, avg_word_length / 8.0)  # Normalizado a 8 caracteres
        
        # Términos médicos especializados
        medical_terms_count = self._count_medical_terms(text)
        medical_density = medical_terms_count / len(words)
        medical_density_score = min(1.0, medical_density * 5)  # Normalizado
        
        # Vocabulario único (diversidad léxica)
        unique_words = len(set(word.lower() for word in words))
        vocabulary_diversity = unique_words / len(words)
        diversity_score = min(1.0, vocabulary_diversity * 2)  # Más diversidad = más difícil
        
        # Términos latinos y técnicos
        latin_terms = self._count_latin_terms(words)
        latin_density = latin_terms / len(words)
        latin_score = min(1.0, latin_density * 10)
        
        # Score compuesto [0-1]
        lexical_score = (
            word_length_score * 0.25 +
            medical_density_score * 0.35 +
            diversity_score * 0.25 +
            latin_score * 0.15
        )
        
        return min(1.0, lexical_score)
    
    def _analyze_medical_complexity(self, content: Dict) -> float:
        """Analiza complejidad específica del dominio médico."""
        
        # Obtener categoría médica del contenido
        category = content.get("category", "general")
        medical_specialty = content.get("medical_specialty", "")
        
        # Score base por categoría
        base_complexity = self.medical_complexity_weights.get(
            category.lower(), 0.5
        )
        
        # Ajustar por especialidad si está disponible
        if medical_specialty:
            specialty_adjustment = self.medical_complexity_weights.get(
                medical_specialty.lower(), 0.5
            )
            base_complexity = (base_complexity + specialty_adjustment) / 2
        
        # Analizar contenido del texto para refinamiento
        text = content.get("text", "")
        if text:
            # Contar conceptos médicos avanzados
            advanced_concepts = self._count_advanced_medical_concepts(text)
            text_words = len(self._tokenize_text(text))
            
            if text_words > 0:
                concept_density = advanced_concepts / text_words
                complexity_adjustment = min(0.3, concept_density * 2)
                base_complexity = min(1.0, base_complexity + complexity_adjustment)
        
        return base_complexity
    
    def _analyze_conceptual_complexity(self, content: Dict) -> float:
        """Analiza complejidad conceptual del contenido."""
        
        text = content.get("text", "")
        if not text:
            return 0.5
        
        # Número de conceptos únicos mencionados
        concepts = self._extract_medical_concepts(text)
        concept_count = len(concepts)
        
        # Relaciones entre conceptos (palabras de conexión)
        relationship_words = self._count_relationship_words(text)
        
        # Complejidad por número de conceptos
        concept_complexity = min(1.0, concept_count / 20.0)  # Normalizado a 20 conceptos
        
        # Complejidad por interconexiones
        relationship_complexity = min(1.0, relationship_words / 50.0)  # Normalizado
        
        # Abstractness score (conceptos abstractos vs concretos)
        abstractness = self._calculate_abstractness(concepts)
        
        # Score compuesto
        conceptual_score = (
            concept_complexity * 0.4 +
            relationship_complexity * 0.3 +
            abstractness * 0.3
        )
        
        return conceptual_score
    
    def _analyze_syntactic_complexity(self, text: str) -> float:
        """Analiza complejidad sintáctica del texto."""
        
        if not text:
            return 0.0
        
        sentences = self._split_sentences(text)
        if not sentences:
            return 0.0
        
        # Longitud promedio de oraciones
        avg_sentence_length = sum(len(self._tokenize_text(s)) for s in sentences) / len(sentences)
        sentence_length_score = min(1.0, avg_sentence_length / 25.0)  # Normalizado a 25 palabras
        
        # Detección de patrones sintácticos complejos
        complexity_score = 0.0
        for pattern_name, pattern in self.complexity_patterns.items():
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            if matches > 0:
                pattern_density = matches / len(sentences)
                complexity_score += min(0.2, pattern_density * 0.5)
        
        # Uso de signos de puntuación complejos
        complex_punctuation = len(re.findall(r'[;:()[\]{}"]', text))
        punctuation_score = min(0.3, complex_punctuation / len(text) * 100)
        
        # Score sintáctico compuesto
        syntactic_score = (
            sentence_length_score * 0.5 +
            complexity_score * 0.3 +
            punctuation_score * 0.2
        )
        
        return min(1.0, syntactic_score)
    
    def _analyze_information_density(self, text: str) -> float:
        """Analiza densidad de información del texto."""
        
        if not text:
            return 0.0
        
        words = self._tokenize_text(text)
        if not words:
            return 0.0
        
        # Ratio de palabras de contenido vs palabras funcionales
        content_words = self._count_content_words(words)
        content_ratio = content_words / len(words)
        
        # Densidad de números y datos cuantitativos
        numerical_data = len(re.findall(r'\d+[.,]?\d*', text))
        numerical_density = numerical_data / len(words)
        
        # Densidad de referencias y citas
        references = len(re.findall(r'\([^)]*\d{4}[^)]*\)|\[\d+\]', text))
        reference_density = references / len(words)
        
        # Score de densidad de información
        density_score = (
            content_ratio * 0.5 +
            min(1.0, numerical_density * 10) * 0.3 +
            min(1.0, reference_density * 20) * 0.2
        )
        
        return min(1.0, density_score)
    
    def _personalize_difficulty(
        self, 
        difficulty_components: Dict[str, float],
        user_profile: Dict
    ) -> Dict[str, Any]:
        """Personaliza la estimación de dificultad basada en el perfil del usuario."""
        
        # Factores de personalización
        user_experience = user_profile.get("study_statistics", {}).get("total_sessions", 0)
        user_skill_level = user_profile.get("skill_level", 0.5)
        user_role = user_profile.get("role", "student")
        
        # Ajustes por experiencia del usuario
        experience_factor = min(1.0, user_experience / 50.0)  # Normalizado a 50 sesiones
        skill_factor = user_skill_level
        
        # Ajustes por rol
        role_adjustments = {
            "student": 1.0,      # Sin ajuste
            "resident": 0.8,     # Reduce dificultad percibida
            "doctor": 0.6,       # Reduce más
            "professor": 0.4,    # Reduce significativamente
            "researcher": 0.5    # Ajuste intermedio
        }
        role_factor = role_adjustments.get(user_role, 1.0)
        
        # Calcular dificultad personalizada
        base_difficulty = sum(difficulty_components.values()) / len(difficulty_components)
        
        # Aplicar factores de personalización
        personalized_difficulty = base_difficulty * (
            (1.0 - experience_factor * 0.3) *  # Experiencia reduce dificultad
            (1.0 - skill_factor * 0.2) *      # Skill reduce dificultad
            role_factor                        # Rol profesional reduce dificultad
        )
        
        personalized_difficulty = max(0.1, min(1.0, personalized_difficulty))
        
        # Estimar tiempo de estudio basado en dificultad personalizada
        base_time_minutes = 30  # Tiempo base para contenido promedio
        time_multiplier = 0.5 + personalized_difficulty * 1.5  # [0.5, 2.0]
        estimated_time = base_time_minutes * time_multiplier
        
        return {
            "overall": personalized_difficulty,
            "study_time_minutes": estimated_time,
            "factors": {
                "base_difficulty": base_difficulty,
                "experience_factor": experience_factor,
                "skill_factor": skill_factor,
                "role_factor": role_factor,
                "personalization_applied": True
            }
        }
    
    def _calculate_base_difficulty(
        self, 
        lexical: float, 
        medical: float, 
        conceptual: float,
        syntactic: float,
        information_density: float
    ) -> Dict[str, Any]:
        """Calcula dificultad base sin personalización."""
        
        # Pesos para diferentes componentes de dificultad
        weights = {
            "lexical": 0.25,
            "medical": 0.30,
            "conceptual": 0.25,
            "syntactic": 0.15,
            "information_density": 0.05
        }
        
        base_difficulty = (
            lexical * weights["lexical"] +
            medical * weights["medical"] +
            conceptual * weights["conceptual"] +
            syntactic * weights["syntactic"] +
            information_density * weights["information_density"]
        )
        
        # Tiempo de estudio base
        base_time = 30 * (0.5 + base_difficulty * 1.5)
        
        return {
            "overall": base_difficulty,
            "study_time_minutes": base_time,
            "factors": {
                "base_difficulty": base_difficulty,
                "personalization_applied": False
            }
        }
    
    # Métodos auxiliares
    def _load_medical_terms_database(self) -> Dict[str, Dict]:
        """Carga base de datos de términos médicos."""
        
        # Base de datos simplificada de términos médicos
        return {
            "anatomia": {
                "basic": ["corazón", "pulmón", "hígado", "riñón", "cerebro"],
                "intermediate": ["miocardio", "bronquio", "hepatocito", "nefrón", "corteza"],
                "advanced": ["endocardio", "alvéolo", "sinusoide", "podocito", "hipotálamo"]
            },
            "fisiologia": {
                "basic": ["respiración", "circulación", "digestión", "excreción"],
                "intermediate": ["homeostasis", "metabolismo", "osmosis", "difusión"],
                "advanced": ["transducción", "fosforilación", "gluconeogénesis"]
            },
            "patologia": {
                "basic": ["infección", "inflamación", "tumor", "lesión"],
                "intermediate": ["neoplasia", "metástasis", "apoptosis", "isquemia"],
                "advanced": ["carcinogénesis", "angiogénesis", "invasión"]
            },
            "farmacologia": {
                "basic": ["dosis", "efecto", "medicamento", "tratamiento"],
                "intermediate": ["farmacocinética", "farmacodinámica", "bioequivalencia"],
                "advanced": ["farmacogenómica", "toxicocinética", "metabolito"]
            }
        }
    
    def _tokenize_text(self, text: str) -> List[str]:
        """Tokeniza el texto en palabras."""
        # Tokenización simple - en producción usar librería especializada
        return re.findall(r'\b\w+\b', text.lower())
    
    def _count_medical_terms(self, text: str) -> int:
        """Cuenta términos médicos en el texto."""
        count = 0
        text_lower = text.lower()
        
        for category, levels in self.medical_terms_database.items():
            for level, terms in levels.items():
                for term in terms:
                    count += text_lower.count(term.lower())
        
        return count
    
    def _count_latin_terms(self, words: List[str]) -> int:
        """Cuenta términos en latín o con terminaciones latinas."""
        latin_patterns = [
            r'.*itis$',    # inflamación
            r'.*oma$',     # tumor
            r'.*osis$',    # condición
            r'.*emia$',    # en sangre
            r'.*pathy$',   # enfermedad
            r'.*algia$',   # dolor
            r'.*ectomy$'   # remoción quirúrgica
        ]
        
        count = 0
        for word in words:
            for pattern in latin_patterns:
                if re.match(pattern, word, re.IGNORECASE):
                    count += 1
                    break
        
        return count
    
    def _count_advanced_medical_concepts(self, text: str) -> int:
        """Cuenta conceptos médicos avanzados."""
        advanced_terms = [
            "fisiopatología", "etiopatogenia", "farmacogenética",
            "inmunopatología", "citoquinas", "apoptosis",
            "angiogénesis", "metástasis", "carcinogénesis"
        ]
        
        count = 0
        text_lower = text.lower()
        for term in advanced_terms:
            count += text_lower.count(term)
        
        return count
    
    def _extract_medical_concepts(self, text: str) -> List[str]:
        """Extrae conceptos médicos del texto."""
        concepts = []
        
        # Buscar patrones de conceptos médicos
        medical_patterns = [
            r'\b\w*itis\b',      # Inflamaciones
            r'\b\w*oma\b',       # Tumores
            r'\b\w*osis\b',      # Condiciones
            r'\b\w*emia\b',      # En sangre
            r'\b\w*pathy\b',     # Enfermedades
            r'\b\w*algia\b',     # Dolores
        ]
        
        for pattern in medical_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            concepts.extend(matches)
        
        return list(set(concepts))  # Eliminar duplicados
    
    def _count_relationship_words(self, text: str) -> int:
        """Cuenta palabras que indican relaciones entre conceptos."""
        relationship_words = [
            "causado por", "resulta en", "debido a", "provoca",
            "asociado con", "relacionado con", "en consecuencia",
            "por lo tanto", "además", "sin embargo", "aunque"
        ]
        
        count = 0
        text_lower = text.lower()
        for phrase in relationship_words:
            count += text_lower.count(phrase)
        
        return count
    
    def _calculate_abstractness(self, concepts: List[str]) -> float:
        """Calcula el nivel de abstracción de los conceptos."""
        if not concepts:
            return 0.0
        
        # Términos abstractos comunes en medicina
        abstract_terms = [
            "función", "proceso", "mecanismo", "patogénesis",
            "etiología", "fisiopatología", "homeostasis"
        ]
        
        abstract_count = sum(
            1 for concept in concepts 
            if any(abs_term in concept.lower() for abs_term in abstract_terms)
        )
        
        return abstract_count / len(concepts)
    
    def _split_sentences(self, text: str) -> List[str]:
        """Divide el texto en oraciones."""
        # División simple por puntos - en producción usar parser más sofisticado
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _count_content_words(self, words: List[str]) -> int:
        """Cuenta palabras de contenido (no funcionales)."""
        function_words = {
            "el", "la", "los", "las", "un", "una", "y", "o", "pero",
            "de", "en", "a", "por", "para", "con", "sin", "sobre",
            "es", "son", "está", "están", "fue", "fueron", "será",
            "que", "como", "cuando", "donde", "si", "porque"
        }
        
        content_count = sum(1 for word in words if word.lower() not in function_words)
        return content_count
    
    def _identify_prerequisites(self, content: Dict) -> List[str]:
        """Identifica conceptos prerequisito para el contenido."""
        
        # Análisis simplificado - en producción usar grafo de conocimiento
        category = content.get("category", "")
        
        prerequisite_map = {
            "farmacologia": ["anatomia", "fisiologia"],
            "patologia": ["anatomia", "fisiologia"],
            "clinica": ["anatomia", "fisiologia", "patologia"],
            "cirugia": ["anatomia", "fisiologia", "patologia"]
        }
        
        return prerequisite_map.get(category.lower(), [])
    
    def _identify_complexity_indicators(self, text: str) -> List[str]:
        """Identifica indicadores específicos de complejidad."""
        
        indicators = []
        
        # Patrones que indican complejidad
        if re.search(r'\b(interacción|interacciona|múltiple|complejo|diversos)\b', text, re.IGNORECASE):
            indicators.append("multiple_interactions")
        
        if re.search(r'\b(diagnóstico diferencial|diagnosis|diferenci)\b', text, re.IGNORECASE):
            indicators.append("differential_diagnosis")
        
        if re.search(r'\b(contraindicación|efectos? adverse?|toxicidad)\b', text, re.IGNORECASE):
            indicators.append("adverse_effects")
        
        if re.search(r'\b(fisiopatología|mecanismo|patogénesis)\b', text, re.IGNORECASE):
            indicators.append("pathophysiology")
        
        return indicators
    
    def _generate_study_recommendations(self, difficulty_analysis: Dict) -> List[str]:
        """Genera recomendaciones de estudio basadas en dificultad."""
        
        recommendations = []
        difficulty = difficulty_analysis["overall"]
        
        if difficulty < 0.3:
            recommendations.extend([
                "Contenido de nivel básico - ideal para revisión rápida",
                "Tiempo de estudio recomendado: 15-30 minutos"
            ])
        elif difficulty < 0.6:
            recommendations.extend([
                "Contenido de nivel intermedio - requiere atención focalizada",
                "Considera tomar notas de conceptos clave",
                "Tiempo de estudio recomendado: 30-45 minutos"
            ])
        elif difficulty < 0.8:
            recommendations.extend([
                "Contenido avanzado - requiere estudio profundo",
                "Recomendado: estudiar en sesiones cortas con descansos",
                "Crear esquemas o mapas conceptuales",
                "Tiempo de estudio recomendado: 45-90 minutos"
            ])
        else:
            recommendations.extend([
                "Contenido muy complejo - requiere preparación previa",
                "Revisar conceptos prerequisito antes de continuar",
                "Estudiar en múltiples sesiones distribuidas",
                "Buscar recursos adicionales o tutorización",
                "Tiempo de estudio recomendado: 90+ minutos"
            ])
        
        return recommendations
    
    def _default_difficulty_analysis(self) -> Dict[str, Any]:
        """Retorna análisis de dificultad por defecto."""
        
        return {
            "overall_difficulty": 0.5,
            "difficulty_breakdown": {
                "lexical_difficulty": 0.5,
                "medical_difficulty": 0.5,
                "conceptual_difficulty": 0.5,
                "syntactic_difficulty": 0.5,
                "information_density": 0.5
            },
            "estimated_study_time_minutes": 30,
            "prerequisite_concepts": [],
            "difficulty_factors": {
                "base_difficulty": 0.5,
                "personalization_applied": False
            },
            "complexity_indicators": [],
            "recommendations": ["Contenido de dificultad promedio"],
            "confidence_score": 0.3,
            "note": "Default analysis - insufficient data for detailed estimation"
        }
