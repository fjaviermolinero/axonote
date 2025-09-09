"""
Servicio de post-procesamiento de transcripciones médicas.
Incluye corrección ASR, NER médico y análisis de estructura pedagógica.
"""

import re
import time
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

import ahocorasick
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.medical_terminology import MedicalTerminology
from app.services.base import BaseService


class PostProcessingService(BaseService):
    """
    Servicio completo de post-procesamiento para transcripciones médicas.
    
    Incluye corrección de errores ASR, extracción de entidades médicas (NER),
    análisis de estructura pedagógica y métricas de calidad automáticas.
    """
    
    def __init__(self):
        super().__init__()
        self.medical_dict: Dict[str, Dict] = {}
        self.aho_corasick: Optional[ahocorasick.Automaton] = None
        self.correction_patterns: List[Tuple[str, str]] = []
        self.is_initialized = False
        
    async def _setup(self) -> None:
        """Configurar diccionario médico y algoritmos de búsqueda."""
        await self._load_medical_dictionary()
        await self._setup_aho_corasick()
        await self._setup_correction_patterns()
        self.is_initialized = True
        
    async def _load_medical_dictionary(self) -> None:
        """Cargar diccionario médico desde base de datos."""
        try:
            db: Session = next(get_db())
            
            # Cargar términos médicos activos
            terms = db.query(MedicalTerminology).filter(
                MedicalTerminology.activo == True
            ).all()
            
            self.medical_dict = {}
            for term in terms:
                # Término principal
                self.medical_dict[term.termino_normalizado.lower()] = {
                    "original": term.termino_original,
                    "categoria": term.categoria,
                    "definicion_italiana": term.definicion_italiana,
                    "definicion_espanola": term.definicion_espanola,
                    "especialidad": term.especialidad_medica,
                    "sinonimos": term.sinonimos,
                    "variantes_asr": term.variantes_asr,
                    "confianza": term.confianza_correccion
                }
                
                # Agregar sinónimos
                for sinonimo in term.sinonimos:
                    if sinonimo:
                        self.medical_dict[sinonimo.lower()] = self.medical_dict[term.termino_normalizado.lower()]
                
                # Agregar variantes ASR
                for variante in term.variantes_asr:
                    if variante:
                        self.medical_dict[variante.lower()] = self.medical_dict[term.termino_normalizado.lower()]
            
            self.logger.info(f"Diccionario médico cargado: {len(self.medical_dict)} términos")
            
        except Exception as e:
            self.logger.error(f"Error cargando diccionario médico: {e}")
            self.medical_dict = {}
    
    async def _setup_aho_corasick(self) -> None:
        """Configurar algoritmo Aho-Corasick para búsqueda rápida."""
        try:
            self.aho_corasick = ahocorasick.Automaton()
            
            for i, term in enumerate(self.medical_dict.keys()):
                self.aho_corasick.add_word(term, (i, term))
            
            self.aho_corasick.make_automaton()
            self.logger.info("Algoritmo Aho-Corasick configurado")
            
        except Exception as e:
            self.logger.error(f"Error configurando Aho-Corasick: {e}")
            self.aho_corasick = None
    
    async def _setup_correction_patterns(self) -> None:
        """Configurar patrones de corrección comunes para ASR italiano."""
        # Patrones comunes de errores ASR en italiano médico
        self.correction_patterns = [
            # Correcciones fonéticas comunes
            (r'\bcardiaco\b', 'cardiaco'),
            (r'\bpolmonare\b', 'polmonare'),
            (r'\bneurologico\b', 'neurologico'),
            (r'\bfarmacologico\b', 'farmacologico'),
            
            # Correcciones de terminaciones
            (r'(\w+)zione\b', r'\1zione'),  # -zione endings
            (r'(\w+)logia\b', r'\1logia'),  # -logia endings
            
            # Correcciones de artículos y preposiciones
            (r'\bdel la\b', 'della'),
            (r'\bnel la\b', 'nella'),
            (r'\bal la\b', 'alla'),
            
            # Números y medidas
            (r'\bmilli grammi\b', 'milligrammi'),
            (r'\bmicro grammi\b', 'microgrammi'),
            (r'\bchilo grammi\b', 'chilogrammi'),
        ]
    
    async def correct_asr_errors(
        self,
        transcription: str,
        confidence_threshold: float = 0.8
    ) -> Dict[str, Any]:
        """
        Corregir errores comunes de ASR en terminología médica italiana.
        
        Args:
            transcription: Texto de la transcripción original
            confidence_threshold: Umbral de confianza para aplicar correcciones
            
        Returns:
            Resultado de corrección con texto mejorado y métricas
        """
        if not self.is_initialized:
            await self._setup()
        
        start_time = time.time()
        corrected_text = transcription
        corrections = []
        
        try:
            # 1. Aplicar patrones de corrección generales
            for pattern, replacement in self.correction_patterns:
                matches = list(re.finditer(pattern, corrected_text, re.IGNORECASE))
                for match in reversed(matches):  # Reverse para mantener posiciones
                    original = match.group()
                    corrected = re.sub(pattern, replacement, original, flags=re.IGNORECASE)
                    
                    if original.lower() != corrected.lower():
                        corrected_text = (
                            corrected_text[:match.start()] + 
                            corrected + 
                            corrected_text[match.end():]
                        )
                        corrections.append({
                            "type": "pattern",
                            "original": original,
                            "corrected": corrected,
                            "position": match.start(),
                            "confidence": 0.9
                        })
            
            # 2. Aplicar correcciones del diccionario médico
            if self.aho_corasick:
                # Buscar términos médicos mal transcritos
                text_lower = corrected_text.lower()
                
                for end_pos, (insert_order, keyword) in self.aho_corasick.iter(text_lower):
                    start_pos = end_pos - len(keyword) + 1
                    
                    # Verificar que es una palabra completa
                    if (start_pos > 0 and text_lower[start_pos - 1].isalnum()) or \
                       (end_pos < len(text_lower) - 1 and text_lower[end_pos + 1].isalnum()):
                        continue
                    
                    term_info = self.medical_dict[keyword]
                    if term_info["confianza"] >= confidence_threshold:
                        # Aplicar corrección
                        original_word = corrected_text[start_pos:end_pos + 1]
                        corrected_word = term_info["original"]
                        
                        if original_word.lower() != corrected_word.lower():
                            corrected_text = (
                                corrected_text[:start_pos] + 
                                corrected_word + 
                                corrected_text[end_pos + 1:]
                            )
                            corrections.append({
                                "type": "medical_term",
                                "original": original_word,
                                "corrected": corrected_word,
                                "position": start_pos,
                                "confidence": term_info["confianza"],
                                "categoria": term_info["categoria"]
                            })
            
            # 3. Calcular métricas de mejora
            processing_time = time.time() - start_time
            improvement_score = len(corrections) / max(len(transcription.split()), 1)
            
            return {
                "success": True,
                "original_text": transcription,
                "corrected_text": corrected_text,
                "corrections": corrections,
                "num_corrections": len(corrections),
                "improvement_score": improvement_score,
                "confidence_avg": sum(c["confidence"] for c in corrections) / max(len(corrections), 1),
                "processing_time": processing_time
            }
            
        except Exception as e:
            self.logger.error(f"Error en corrección ASR: {e}")
            return {
                "success": False,
                "error": str(e),
                "original_text": transcription,
                "corrected_text": transcription,
                "corrections": [],
                "processing_time": time.time() - start_time
            }
    
    async def extract_medical_entities(
        self,
        text: str,
        include_definitions: bool = True
    ) -> Dict[str, Any]:
        """
        Extraer entidades médicas mediante NER especializado.
        
        Args:
            text: Texto para analizar
            include_definitions: Si incluir definiciones de términos
            
        Returns:
            Entidades médicas categorizadas con metadatos
        """
        if not self.is_initialized:
            await self._setup()
        
        start_time = time.time()
        
        try:
            entities = {
                "anatomia": [],
                "patologia": [],
                "farmacologia": [],
                "procedimientos": [],
                "sintomas": [],
                "diagnostico": [],
                "terapia": [],
                "otros": []
            }
            
            detected_terms = []
            text_lower = text.lower()
            
            if self.aho_corasick:
                # Buscar términos médicos con Aho-Corasick
                for end_pos, (insert_order, keyword) in self.aho_corasick.iter(text_lower):
                    start_pos = end_pos - len(keyword) + 1
                    
                    # Verificar que es una palabra completa
                    if (start_pos > 0 and text_lower[start_pos - 1].isalnum()) or \
                       (end_pos < len(text_lower) - 1 and text_lower[end_pos + 1].isalnum()):
                        continue
                    
                    term_info = self.medical_dict[keyword]
                    original_term = text[start_pos:end_pos + 1]
                    
                    entity = {
                        "termino": term_info["original"],
                        "termino_detectado": original_term,
                        "posicion": [start_pos, end_pos + 1],
                        "categoria": term_info["categoria"],
                        "especialidad": term_info["especialidad"],
                        "confianza": 0.95
                    }
                    
                    if include_definitions:
                        entity.update({
                            "definicion_italiana": term_info["definicion_italiana"],
                            "definicion_espanola": term_info["definicion_espanola"],
                            "sinonimos": term_info["sinonimos"]
                        })
                    
                    # Categorizar entidad
                    categoria = term_info["categoria"]
                    if categoria in entities:
                        entities[categoria].append(entity)
                    else:
                        entities["otros"].append(entity)
                    
                    detected_terms.append(term_info["original"])
            
            # Generar glosario de la clase
            glossary = {}
            for categoria, terms in entities.items():
                for term in terms:
                    if term["termino"] not in glossary:
                        glossary[term["termino"]] = {
                            "categoria": term["categoria"],
                            "definicion_espanola": term.get("definicion_espanola", ""),
                            "especialidad": term["especialidad"],
                            "frecuencia": 1
                        }
                    else:
                        glossary[term["termino"]]["frecuencia"] += 1
            
            # Calcular métricas
            total_entities = sum(len(terms) for terms in entities.values())
            processing_time = time.time() - start_time
            
            return {
                "success": True,
                "entities": entities,
                "detected_terms": list(set(detected_terms)),
                "glossary": glossary,
                "total_entities": total_entities,
                "entities_by_category": {cat: len(terms) for cat, terms in entities.items()},
                "precision_estimate": 0.9,  # Estimación basada en diccionario curado
                "processing_time": processing_time
            }
            
        except Exception as e:
            self.logger.error(f"Error en extracción NER: {e}")
            return {
                "success": False,
                "error": str(e),
                "entities": {},
                "processing_time": time.time() - start_time
            }
    
    async def analyze_class_structure(
        self,
        transcription: str,
        diarization_data: Dict
    ) -> Dict[str, Any]:
        """
        Analizar estructura pedagógica de la clase médica.
        
        Args:
            transcription: Texto de la transcripción
            diarization_data: Datos de diarización con speakers
            
        Returns:
            Análisis estructural de la clase
        """
        start_time = time.time()
        
        try:
            # 1. Identificar segmentos temporales
            segments = self._identify_temporal_segments(transcription, diarization_data)
            
            # 2. Clasificar tipos de actividad pedagógica
            activities = self._classify_pedagogical_activities(segments)
            
            # 3. Analizar participación de speakers
            participation = self._analyze_speaker_participation(diarization_data)
            
            # 4. Detectar momentos clave de aprendizaje
            key_moments = self._detect_key_learning_moments(segments)
            
            # 5. Generar flujo de clase
            class_flow = self._generate_class_flow(activities)
            
            processing_time = time.time() - start_time
            
            return {
                "success": True,
                "segments": segments,
                "activities": activities,
                "participation": participation,
                "key_moments": key_moments,
                "class_flow": class_flow,
                "total_segments": len(segments),
                "activity_distribution": self._calculate_activity_distribution(activities),
                "processing_time": processing_time
            }
            
        except Exception as e:
            self.logger.error(f"Error en análisis de estructura: {e}")
            return {
                "success": False,
                "error": str(e),
                "processing_time": time.time() - start_time
            }
    
    def _identify_temporal_segments(self, transcription: str, diarization_data: Dict) -> List[Dict]:
        """Identificar segmentos temporales basados en diarización."""
        segments = []
        
        if not diarization_data or "segments" not in diarization_data:
            # Fallback: segmentar por párrafos
            paragraphs = transcription.split('\n\n')
            for i, paragraph in enumerate(paragraphs):
                if paragraph.strip():
                    segments.append({
                        "id": i,
                        "text": paragraph.strip(),
                        "start_time": i * 30,  # Estimación
                        "end_time": (i + 1) * 30,
                        "speaker": "unknown",
                        "role": "unknown"
                    })
        else:
            # Usar datos de diarización
            for i, segment in enumerate(diarization_data["segments"]):
                segments.append({
                    "id": i,
                    "text": segment.get("text", ""),
                    "start_time": segment.get("start", 0),
                    "end_time": segment.get("end", 0),
                    "speaker": segment.get("speaker", "unknown"),
                    "role": segment.get("role", "unknown"),
                    "confidence": segment.get("confidence", 0.0)
                })
        
        return segments
    
    def _classify_pedagogical_activities(self, segments: List[Dict]) -> List[Dict]:
        """Clasificar actividades pedagógicas en cada segmento."""
        # Patrones para identificar tipos de actividad
        activity_patterns = {
            "introduccion": [
                "bienvenidos", "oggi", "argomento", "iniziamo", "parleremo", 
                "studieremo", "vedremo", "obiettivo"
            ],
            "explicacion": [
                "quindi", "per esempio", "importante", "ricordate", "come sapete",
                "infatti", "inoltre", "dunque", "cioè"
            ],
            "pregunta": [
                "domanda", "chi sa", "qualcuno", "cosa pensate", "secondo voi",
                "come", "perché", "quando", "dove", "?"
            ],
            "respuesta": [
                "esatto", "corretto", "bene", "perfetto", "giusto", "bravo",
                "no", "sbagliato", "attenzione"
            ],
            "interaccion": [
                "studente", "professore", "dottore", "scusi", "prego",
                "grazie", "capisce", "chiaro"
            ],
            "resumen": [
                "riassumendo", "concludendo", "importante ricordare", 
                "in sintesi", "quindi"
            ],
            "cierre": [
                "fine", "prossima volta", "arrivederci", "grazie", "finito",
                "basta", "stop"
            ]
        }
        
        classified_segments = []
        
        for segment in segments:
            text = segment["text"].lower()
            scores = {}
            
            # Calcular puntuación para cada tipo de actividad
            for activity, patterns in activity_patterns.items():
                score = 0
                for pattern in patterns:
                    if pattern in text:
                        score += 1
                scores[activity] = score / len(patterns)
            
            # Determinar actividad principal
            best_activity = max(scores, key=scores.get) if scores else "explicacion"
            confidence = scores.get(best_activity, 0.0)
            
            classified_segment = {
                **segment,
                "activity_type": best_activity,
                "activity_confidence": confidence,
                "activity_scores": scores
            }
            
            classified_segments.append(classified_segment)
        
        return classified_segments
    
    def _analyze_speaker_participation(self, diarization_data: Dict) -> Dict[str, Any]:
        """Analizar participación de cada speaker."""
        if not diarization_data or "segments" not in diarization_data:
            return {"error": "No hay datos de diarización disponibles"}
        
        speaker_stats = defaultdict(lambda: {
            "total_time": 0.0,
            "segment_count": 0,
            "role": "unknown",
            "avg_segment_duration": 0.0,
            "participation_percentage": 0.0
        })
        
        total_time = 0.0
        
        for segment in diarization_data["segments"]:
            speaker = segment.get("speaker", "unknown")
            duration = segment.get("end", 0) - segment.get("start", 0)
            
            speaker_stats[speaker]["total_time"] += duration
            speaker_stats[speaker]["segment_count"] += 1
            speaker_stats[speaker]["role"] = segment.get("role", "unknown")
            
            total_time += duration
        
        # Calcular estadísticas finales
        for speaker, stats in speaker_stats.items():
            if stats["segment_count"] > 0:
                stats["avg_segment_duration"] = stats["total_time"] / stats["segment_count"]
            if total_time > 0:
                stats["participation_percentage"] = (stats["total_time"] / total_time) * 100
        
        return {
            "speakers": dict(speaker_stats),
            "total_speakers": len(speaker_stats),
            "total_duration": total_time,
            "most_active_speaker": max(speaker_stats.keys(), 
                                     key=lambda x: speaker_stats[x]["total_time"]) if speaker_stats else None
        }
    
    def _detect_key_learning_moments(self, segments: List[Dict]) -> List[Dict]:
        """Detectar momentos clave de aprendizaje."""
        key_moments = []
        
        # Patrones que indican momentos importantes
        important_patterns = [
            "importante", "fondamentale", "ricordate", "attenzione",
            "chiave", "essenziale", "cruciale", "significativo"
        ]
        
        question_patterns = ["?", "domanda", "perché", "come", "cosa"]
        
        for segment in segments:
            text = segment["text"].lower()
            importance_score = 0
            
            # Verificar patrones importantes
            for pattern in important_patterns:
                if pattern in text:
                    importance_score += 2
            
            # Verificar preguntas
            for pattern in question_patterns:
                if pattern in text:
                    importance_score += 1
            
            # Si hay interacción profesor-estudiante
            if segment.get("activity_type") in ["pregunta", "respuesta", "interaccion"]:
                importance_score += 1
            
            # Si el segmento es suficientemente importante
            if importance_score >= 2:
                key_moments.append({
                    "timestamp": segment.get("start_time", 0),
                    "duration": segment.get("end_time", 0) - segment.get("start_time", 0),
                    "text": segment["text"][:200] + "..." if len(segment["text"]) > 200 else segment["text"],
                    "importance_score": importance_score,
                    "activity_type": segment.get("activity_type", "unknown"),
                    "speaker": segment.get("speaker", "unknown")
                })
        
        # Ordenar por importancia
        key_moments.sort(key=lambda x: x["importance_score"], reverse=True)
        
        return key_moments[:10]  # Top 10 momentos más importantes
    
    def _generate_class_flow(self, activities: List[Dict]) -> Dict[str, Any]:
        """Generar flujo general de la clase."""
        if not activities:
            return {"error": "No hay actividades para analizar"}
        
        # Agrupar actividades consecutivas del mismo tipo
        flow_segments = []
        current_activity = None
        current_start = 0
        current_duration = 0
        
        for activity in activities:
            activity_type = activity.get("activity_type", "unknown")
            
            if activity_type != current_activity:
                if current_activity:
                    flow_segments.append({
                        "activity": current_activity,
                        "start_time": current_start,
                        "duration": current_duration,
                        "percentage": 0  # Se calculará después
                    })
                
                current_activity = activity_type
                current_start = activity.get("start_time", 0)
                current_duration = activity.get("end_time", 0) - activity.get("start_time", 0)
            else:
                current_duration += activity.get("end_time", 0) - activity.get("start_time", 0)
        
        # Agregar último segmento
        if current_activity:
            flow_segments.append({
                "activity": current_activity,
                "start_time": current_start,
                "duration": current_duration,
                "percentage": 0
            })
        
        # Calcular porcentajes
        total_duration = sum(seg["duration"] for seg in flow_segments)
        if total_duration > 0:
            for segment in flow_segments:
                segment["percentage"] = (segment["duration"] / total_duration) * 100
        
        return {
            "segments": flow_segments,
            "total_duration": total_duration,
            "main_activities": [seg["activity"] for seg in flow_segments if seg["percentage"] > 10]
        }
    
    def _calculate_activity_distribution(self, activities: List[Dict]) -> Dict[str, float]:
        """Calcular distribución de tipos de actividad."""
        activity_counts = defaultdict(int)
        total_activities = len(activities)
        
        for activity in activities:
            activity_type = activity.get("activity_type", "unknown")
            activity_counts[activity_type] += 1
        
        # Convertir a porcentajes
        distribution = {}
        for activity, count in activity_counts.items():
            distribution[activity] = (count / total_activities) * 100 if total_activities > 0 else 0
        
        return distribution
    
    async def cleanup(self) -> None:
        """Limpiar recursos del servicio."""
        self.medical_dict.clear()
        self.aho_corasick = None
        self.correction_patterns.clear()
        self.is_initialized = False
