"""
Servicio de generación automática de micro-memos y flashcards.
Genera tarjetas de estudio desde contenido procesado (OCR, transcripciones, research).
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    ClassSession, OCRResult, LLMAnalysisResult, ResearchResult,
    MicroMemo, MicroMemoCollection, MedicalTerminology
)
from app.services.base import BaseService, ServiceConfigurationError
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class ConfiguracionMicroMemo:
    """Configuración para generación de micro-memos."""
    
    def __init__(
        self,
        max_memos_per_concept: int = 3,
        min_confidence_threshold: float = 0.6,
        balance_difficulty: bool = True,
        auto_validate_high_confidence: bool = True,
        enable_spaced_repetition: bool = True,
        target_language: str = "ita",
        specialty_focus: Optional[str] = None
    ):
        self.max_memos_per_concept = max_memos_per_concept
        self.min_confidence_threshold = min_confidence_threshold
        self.balance_difficulty = balance_difficulty
        self.auto_validate_high_confidence = auto_validate_high_confidence
        self.enable_spaced_repetition = enable_spaced_repetition
        self.target_language = target_language
        self.specialty_focus = specialty_focus


class ConceptoExtraido:
    """Concepto médico extraído para generación de micro-memo."""
    
    def __init__(
        self,
        term: str,
        context: str,
        content_type: str,
        specialty: Optional[str] = None,
        importance_score: float = 0.5,
        complexity_level: str = "medium"
    ):
        self.term = term
        self.context = context
        self.content_type = content_type
        self.specialty = specialty
        self.importance_score = importance_score
        self.complexity_level = complexity_level


class MicroMemoGenerado:
    """Resultado de generación de micro-memo."""
    
    def __init__(
        self,
        title: str,
        question: str,
        answer: str,
        explanation: Optional[str] = None,
        memo_type: str = "definition",
        difficulty_level: str = "medium",
        confidence_score: float = 0.8,
        tags: Optional[List[str]] = None,
        source_concept: Optional[ConceptoExtraido] = None
    ):
        self.title = title
        self.question = question
        self.answer = answer
        self.explanation = explanation
        self.memo_type = memo_type
        self.difficulty_level = difficulty_level
        self.confidence_score = confidence_score
        self.tags = tags or []
        self.source_concept = source_concept


class MicroMemoService(BaseService):
    """
    Servicio completo de generación automática de micro-memos.
    
    Genera flashcards de estudio médico desde contenido procesado,
    utilizando LLM para crear preguntas y respuestas estructuradas.
    """
    
    def __init__(self):
        super().__init__("micro_memo_service")
        self.settings = get_settings()
        self.llm_service: Optional[LLMService] = None
        self.is_initialized = False
        
        # Templates para diferentes tipos de micro-memos
        self.memo_templates = {
            "definition": {
                "system_prompt": """Crea una flashcard de definición médica clara y concisa en italiano.
La pregunta debe ser directa y la respuesta debe incluir definición y contexto médico relevante.""",
                "question_format": "¿Qué es {term}?",
                "difficulty_keywords": ["básico", "fundamental", "definición", "concetto"],
                "target_length": {"question": 50, "answer": 150}
            },
            "concept": {
                "system_prompt": """Crea una flashcard que explique un concepto médico complejo en italiano.
Incluye mecanismos, causas y efectos cuando sea relevante.""",
                "question_format": "Explica el concepto de {concept}",
                "difficulty_keywords": ["explicar", "concepto", "mecanismo", "processo"],
                "target_length": {"question": 80, "answer": 200}
            },
            "process": {
                "system_prompt": """Crea una flashcard sobre un proceso o procedimiento médico en italiano.
Describe los pasos principales y la relevancia clínica.""",
                "question_format": "Describe el proceso de {process}",
                "difficulty_keywords": ["processo", "procedura", "protocolo", "passi"],
                "target_length": {"question": 70, "answer": 250}
            },
            "case": {
                "system_prompt": """Crea una flashcard de caso clínico con diagnóstico en italiano.
Presenta síntomas y pide diagnóstico diferencial.""",
                "question_format": "Paziente con {symptoms}. ¿Cuál es el diagnóstico más probable?",
                "difficulty_keywords": ["caso", "paziente", "diagnosi", "sintomi"],
                "target_length": {"question": 100, "answer": 180}
            },
            "fact": {
                "system_prompt": """Crea una flashcard sobre un dato o hecho médico importante en italiano.
La información debe ser precisa y clínicamente relevante.""",
                "question_format": "¿Cuál es {fact_type} de {term}?",
                "difficulty_keywords": ["dato", "fatto", "statistica", "valore"],
                "target_length": {"question": 60, "answer": 120}
            },
            "comparison": {
                "system_prompt": """Crea una flashcard que compare conceptos médicos similares en italiano.
Destaca las diferencias clave y cuándo usar cada uno.""",
                "question_format": "¿Cuáles son las diferencias entre {concept1} y {concept2}?",
                "difficulty_keywords": ["differenza", "confronto", "versus", "similitudine"],
                "target_length": {"question": 80, "answer": 220}
            },
            "symptom": {
                "system_prompt": """Crea una flashcard sobre síntomas y diagnóstico diferencial en italiano.
Incluye síntomas clave y posibles diagnósticos.""",
                "question_format": "¿Qué condiciones pueden causar {symptom}?",
                "difficulty_keywords": ["sintomo", "segno", "manifestazione", "diagnosi"],
                "target_length": {"question": 70, "answer": 190}
            },
            "treatment": {
                "system_prompt": """Crea una flashcard sobre tratamiento o terapia médica en italiano.
Incluye indicaciones, dosificación y contraindicaciones cuando sea relevante.""",
                "question_format": "¿Cuál es el tratamiento para {condition}?",
                "difficulty_keywords": ["trattamento", "terapia", "farmaco", "cura"],
                "target_length": {"question": 60, "answer": 200}
            }
        }
        
        # Patrones para extracción de conceptos
        self.concept_patterns = {
            "medical_terms": [
                r"\b[A-Z][a-z]+ite\b",  # Inflamaciones (bronchite, artrite)
                r"\b[A-Z][a-z]+osi\b",  # Procesos patológicos (fibrosi, cirrosi)
                r"\b[A-Z][a-z]+emia\b",  # Condiciones sanguíneas (anemia, leucemia)
                r"\bsindrome di [A-Z][a-z]+\b",  # Síndromes
                r"\bmalattia di [A-Z][a-z]+\b"  # Enfermedades específicas
            ],
            "procedures": [
                r"\b[a-z]+scopia\b",  # Endoscopias
                r"\b[a-z]+grafia\b",  # Estudios de imagen
                r"\bintervento di [a-z]+\b",  # Intervenciones
                r"\btrapianto di [a-z]+\b"  # Trasplantes
            ],
            "anatomy": [
                r"\b[a-z]+ cardiaco\b",
                r"\b[a-z]+ polmonare\b",
                r"\b[a-z]+ epatico\b",
                r"\b[a-z]+ renale\b"
            ]
        }
    
    async def _setup(self) -> None:
        """Configurar servicio de micro-memos."""
        try:
            # Configurar servicio LLM
            self.llm_service = LLMService()
            await self.llm_service._setup()
            
            self.is_initialized = True
            logger.info("MicroMemoService inicializado correctamente")
            
        except Exception as e:
            raise ServiceConfigurationError(
                "MicroMemo",
                f"Error configurando servicio micro-memos: {str(e)}"
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar salud del servicio de micro-memos."""
        try:
            # Verificar LLM
            llm_health = await self.llm_service.health_check() if self.llm_service else {"status": "not_configured"}
            
            return {
                "status": "healthy" if self.is_initialized else "initializing",
                "llm_status": llm_health.get("status", "unknown"),
                "available_templates": list(self.memo_templates.keys()),
                "supported_languages": ["ita", "eng"],
                "memo_types_supported": len(self.memo_templates),
                "concept_patterns_loaded": len(self.concept_patterns)
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def generate_from_ocr(
        self,
        ocr_result: OCRResult,
        config: Optional[ConfiguracionMicroMemo] = None
    ) -> List[MicroMemo]:
        """
        Genera micro-memos desde resultado OCR.
        
        Args:
            ocr_result: Resultado de procesamiento OCR
            config: Configuración de generación
            
        Returns:
            Lista de micro-memos generados
        """
        if not self.is_initialized:
            await self._setup()
        
        config = config or ConfiguracionMicroMemo()
        
        try:
            logger.info(f"Generando micro-memos desde OCR {ocr_result.id}")
            
            # 1. Analizar contenido OCR
            content_chunks = await self._chunk_ocr_content(ocr_result)
            
            # 2. Extraer conceptos clave
            key_concepts = await self._extract_key_concepts_from_text(
                ocr_result.corrected_text or ocr_result.extracted_text,
                content_type="ocr",
                specialty=ocr_result.medical_specialty
            )
            
            # 3. Generar micro-memos por concepto
            generated_memos = []
            for concept in key_concepts:
                if len(generated_memos) >= config.max_memos_per_concept * len(key_concepts):
                    break
                
                memo_type = await self._classify_memo_type(concept)
                memo = await self._generate_memo_from_concept(concept, memo_type, config)
                
                if memo and memo.confidence_score >= config.min_confidence_threshold:
                    generated_memos.append(memo)
            
            # 4. Validar y filtrar
            validated_memos = await self._validate_memos(generated_memos, config)
            
            # 5. Convertir a modelos de BD y guardar
            saved_memos = []
            for memo_data in validated_memos:
                memo = await self._create_micro_memo_model(memo_data, ocr_result, config)
                saved_memos.append(memo)
            
            logger.info(f"Generados {len(saved_memos)} micro-memos desde OCR")
            return saved_memos
            
        except Exception as e:
            logger.error(f"Error generando micro-memos desde OCR: {str(e)}")
            raise
    
    async def generate_from_llm_analysis(
        self,
        llm_analysis: LLMAnalysisResult,
        config: Optional[ConfiguracionMicroMemo] = None
    ) -> List[MicroMemo]:
        """Genera micro-memos desde análisis LLM de transcripción."""
        if not self.is_initialized:
            await self._setup()
        
        config = config or ConfiguracionMicroMemo()
        
        try:
            logger.info(f"Generando micro-memos desde análisis LLM {llm_analysis.id}")
            
            # 1. Extraer contenido del análisis LLM
            content = llm_analysis.analysis_result
            
            # 2. Identificar puntos clave para memos
            key_points = await self._extract_memo_points_from_llm(content)
            
            # 3. Generar memos focalizados
            generated_memos = []
            for point in key_points:
                memo = await self._generate_focused_memo(point, config)
                if memo and memo.confidence_score >= config.min_confidence_threshold:
                    generated_memos.append(memo)
            
            # 4. Validar y convertir a modelos
            validated_memos = await self._validate_memos(generated_memos, config)
            saved_memos = []
            for memo_data in validated_memos:
                memo = await self._create_micro_memo_model(memo_data, llm_analysis, config)
                saved_memos.append(memo)
            
            logger.info(f"Generados {len(saved_memos)} micro-memos desde análisis LLM")
            return saved_memos
            
        except Exception as e:
            logger.error(f"Error generando micro-memos desde LLM: {str(e)}")
            raise
    
    async def generate_from_research(
        self,
        research_result: ResearchResult,
        config: Optional[ConfiguracionMicroMemo] = None
    ) -> List[MicroMemo]:
        """Genera micro-memos desde resultado de research médico."""
        if not self.is_initialized:
            await self._setup()
        
        config = config or ConfiguracionMicroMemo()
        
        try:
            logger.info(f"Generando micro-memos desde research {research_result.id}")
            
            # 1. Extraer definiciones y conceptos del research
            definitions = research_result.final_definition
            sources_content = research_result.sources_content
            
            # 2. Crear conceptos desde research
            concept = ConceptoExtraido(
                term=research_result.medical_term,
                context=definitions.get("italian", "") if isinstance(definitions, dict) else str(definitions),
                content_type="research",
                specialty=research_result.term_category,
                importance_score=research_result.confidence_score,
                complexity_level="medium"
            )
            
            # 3. Generar memos específicos para research
            memos = await self._generate_research_memos(concept, sources_content, config)
            
            # 4. Validar y convertir
            validated_memos = await self._validate_memos(memos, config)
            saved_memos = []
            for memo_data in validated_memos:
                memo = await self._create_micro_memo_model(memo_data, research_result, config)
                saved_memos.append(memo)
            
            logger.info(f"Generados {len(saved_memos)} micro-memos desde research")
            return saved_memos
            
        except Exception as e:
            logger.error(f"Error generando micro-memos desde research: {str(e)}")
            raise
    
    async def generate_collection(
        self,
        class_session: ClassSession,
        collection_config: Dict[str, Any]
    ) -> MicroMemoCollection:
        """Genera colección automática de micro-memos para una clase."""
        try:
            logger.info(f"Generando colección de micro-memos para clase {class_session.id}")
            
            # 1. Recopilar todo el contenido procesado
            all_content = await self._gather_session_content(class_session)
            
            # 2. Analizar y priorizar conceptos
            prioritized_concepts = await self._prioritize_concepts(all_content)
            
            # 3. Generar set balanceado de memos
            memo_set = await self._generate_balanced_memo_set(
                prioritized_concepts,
                collection_config
            )
            
            # 4. Crear colección
            collection = await self._create_collection_model(
                class_session=class_session,
                memos=memo_set,
                config=collection_config
            )
            
            logger.info(f"Colección creada con {len(memo_set)} micro-memos")
            return collection
            
        except Exception as e:
            logger.error(f"Error generando colección: {str(e)}")
            raise
    
    async def _chunk_ocr_content(self, ocr_result: OCRResult) -> List[Dict[str, Any]]:
        """Divide contenido OCR en chunks para análisis."""
        text = ocr_result.corrected_text or ocr_result.extracted_text
        
        # Dividir por párrafos o páginas
        if ocr_result.pages_processed > 1:
            # Usar datos por página si están disponibles
            pages_data = ocr_result.raw_ocr_data or []
            chunks = []
            for i, page_data in enumerate(pages_data):
                if isinstance(page_data, dict) and 'text' in page_data:
                    chunks.append({
                        "text": page_data['text'],
                        "source": f"page_{i+1}",
                        "confidence": page_data.get('confidence', 0.8)
                    })
            return chunks
        else:
            # Dividir por párrafos
            paragraphs = [p.strip() for p in text.split('\n\n') if p.strip() and len(p.strip()) > 50]
            return [
                {
                    "text": para,
                    "source": f"paragraph_{i+1}",
                    "confidence": ocr_result.confidence_score or 0.8
                }
                for i, para in enumerate(paragraphs)
            ]
    
    async def _extract_key_concepts_from_text(
        self,
        text: str,
        content_type: str = "text",
        specialty: Optional[str] = None
    ) -> List[ConceptoExtraido]:
        """Extrae conceptos clave del texto usando patrones y LLM."""
        concepts = []
        
        # 1. Extracción basada en patrones
        pattern_concepts = await self._extract_concepts_by_patterns(text)
        concepts.extend(pattern_concepts)
        
        # 2. Extracción con LLM para conceptos más complejos
        if self.llm_service:
            llm_concepts = await self._extract_concepts_with_llm(text, specialty)
            concepts.extend(llm_concepts)
        
        # 3. Filtrar y deduplicar
        unique_concepts = await self._deduplicate_concepts(concepts)
        
        return unique_concepts[:20]  # Limitar a 20 conceptos principales
    
    async def _extract_concepts_by_patterns(self, text: str) -> List[ConceptoExtraido]:
        """Extrae conceptos usando patrones regex."""
        concepts = []
        
        for category, patterns in self.concept_patterns.items():
            for pattern in patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    term = match.group().strip()
                    context = text[max(0, match.start()-100):match.end()+100]
                    
                    concept = ConceptoExtraido(
                        term=term,
                        context=context,
                        content_type=category,
                        importance_score=0.7,  # Score medio para patrones
                        complexity_level="medium"
                    )
                    concepts.append(concept)
        
        return concepts
    
    async def _extract_concepts_with_llm(
        self,
        text: str,
        specialty: Optional[str] = None
    ) -> List[ConceptoExtraido]:
        """Extrae conceptos médicos usando LLM."""
        try:
            prompt = f"""
            Analizza il seguente testo medico in italiano ed estrai i concetti medici più importanti.
            Per ogni concetto, fornisci:
            - termine medico
            - categoria (anatomia, patologia, procedura, farmacologia, etc.)
            - livello di importanza (1-10)
            - livello di complessità (facile, medio, difficile)
            
            Testo da analizzare:
            {text[:2000]}  # Limitar para evitar tokens excesivos
            
            Concentrati su {specialty if specialty else 'medicina generale'}.
            
            Formato di risposta JSON:
            {{
                "concepts": [
                    {{
                        "term": "termine medico",
                        "category": "categoria",
                        "importance": 8,
                        "complexity": "medio",
                        "context": "contesto breve"
                    }}
                ]
            }}
            """
            
            response = await self.llm_service.generate_structured_content(
                prompt=prompt,
                expected_format="json",
                max_tokens=1000
            )
            
            if response and response.get("success"):
                content = response["content"]
                if isinstance(content, dict) and "concepts" in content:
                    concepts = []
                    for concept_data in content["concepts"][:10]:  # Max 10 por llamada
                        concept = ConceptoExtraido(
                            term=concept_data.get("term", ""),
                            context=concept_data.get("context", ""),
                            content_type=concept_data.get("category", "general"),
                            specialty=specialty,
                            importance_score=concept_data.get("importance", 5) / 10.0,
                            complexity_level=concept_data.get("complexity", "medium")
                        )
                        concepts.append(concept)
                    return concepts
            
        except Exception as e:
            logger.warning(f"Error extrayendo conceptos con LLM: {str(e)}")
        
        return []
    
    async def _classify_memo_type(self, concept: ConceptoExtraido) -> str:
        """Clasifica el tipo de micro-memo más apropiado para un concepto."""
        
        # Clasificación basada en el tipo de contenido y término
        term_lower = concept.term.lower()
        content_type = concept.content_type.lower()
        
        # Reglas de clasificación
        if any(keyword in term_lower for keyword in ["cos'è", "che cosa", "definizione"]):
            return "definition"
        elif any(keyword in term_lower for keyword in ["procedura", "intervento", "processo"]):
            return "process"
        elif any(keyword in term_lower for keyword in ["paziente", "caso", "sintomi"]):
            return "case"
        elif any(keyword in term_lower for keyword in ["differenza", "confronto", "versus"]):
            return "comparison"
        elif any(keyword in term_lower for keyword in ["sintomo", "segno", "manifestazione"]):
            return "symptom"
        elif any(keyword in term_lower for keyword in ["terapia", "trattamento", "farmaco"]):
            return "treatment"
        elif content_type == "anatomia":
            return "definition"
        elif content_type == "patologia":
            return "concept"
        elif content_type == "procedura":
            return "process"
        else:
            return "concept"  # Default
    
    async def _generate_memo_from_concept(
        self,
        concept: ConceptoExtraido,
        memo_type: str,
        config: ConfiguracionMicroMemo
    ) -> Optional[MicroMemoGenerado]:
        """Genera un micro-memo individual desde un concepto."""
        try:
            template = self.memo_templates.get(memo_type, self.memo_templates["definition"])
            
            # Preparar prompt para LLM
            prompt = f"""
            {template['system_prompt']}
            
            Informazioni del concetto:
            - Termine: {concept.term}
            - Contesto: {concept.context[:300]}
            - Tipo di contenuto: {concept.content_type}
            - Specialità: {concept.specialty or 'medicina generale'}
            - Livello di complessità: {concept.complexity_level}
            
            Crea una flashcard in italiano con:
            - Titolo: titolo breve e descrittivo
            - Domanda: domanda chiara e specifica (max {template['target_length']['question']} caratteri)
            - Risposta: risposta completa ma concisa (max {template['target_length']['answer']} caratteri)
            - Spiegazione: spiegazione aggiuntiva se necessaria (opzionale)
            - Livello difficoltà: facile/medio/difficile
            - Tags: lista di tag rilevanti (max 5)
            
            La flashcard deve essere appropriata per lo studio medico universitario.
            Risposta in formato JSON:
            {{
                "title": "Titolo flashcard",
                "question": "Domanda della flashcard",
                "answer": "Risposta della flashcard",
                "explanation": "Spiegazione aggiuntiva (opzionale)",
                "difficulty": "medio",
                "tags": ["tag1", "tag2", "tag3"],
                "confidence": 0.85
            }}
            """
            
            # Llamar a LLM
            response = await self.llm_service.generate_structured_content(
                prompt=prompt,
                expected_format="json",
                max_tokens=800
            )
            
            if not response or not response.get("success"):
                return None
            
            memo_data = response["content"]
            
            # Validar datos esenciales
            if not memo_data.get("question") or not memo_data.get("answer"):
                return None
            
            # Crear objeto MicroMemoGenerado
            memo = MicroMemoGenerado(
                title=memo_data.get("title", concept.term),
                question=memo_data["question"],
                answer=memo_data["answer"],
                explanation=memo_data.get("explanation"),
                memo_type=memo_type,
                difficulty_level=memo_data.get("difficulty", "medium"),
                confidence_score=memo_data.get("confidence", 0.8),
                tags=memo_data.get("tags", []),
                source_concept=concept
            )
            
            return memo
            
        except Exception as e:
            logger.warning(f"Error generando memo para concepto {concept.term}: {str(e)}")
            return None
    
    async def _validate_memos(
        self,
        memos: List[MicroMemoGenerado],
        config: ConfiguracionMicroMemo
    ) -> List[MicroMemoGenerado]:
        """Valida calidad de micro-memos generados."""
        validated = []
        
        for memo in memos:
            # Verificaciones básicas
            if not memo.question or not memo.answer:
                continue
            
            # Verificar longitud apropiada
            if len(memo.question) < 10 or len(memo.answer) < 10:
                continue
            
            # Verificar que no sean demasiado largos
            if len(memo.question) > 300 or len(memo.answer) > 1000:
                continue
            
            # Verificar contenido médico
            if not await self._is_medical_content(memo.question + " " + memo.answer):
                continue
            
            # Calcular score de calidad
            quality_score = await self._calculate_memo_quality(memo)
            memo.confidence_score = quality_score
            
            # Aplicar umbral de confianza
            if quality_score >= config.min_confidence_threshold:
                validated.append(memo)
        
        return validated
    
    async def _is_medical_content(self, text: str) -> bool:
        """Verifica si el contenido es médico."""
        medical_keywords = [
            "medico", "medicina", "salute", "paziente", "malattia", "sintomo",
            "diagnosi", "terapia", "farmaco", "anatomia", "fisiologia", "patologia",
            "clinico", "ospedale", "dottore", "infermiere", "chirurgia", "intervento"
        ]
        
        text_lower = text.lower()
        medical_count = sum(1 for keyword in medical_keywords if keyword in text_lower)
        
        # Considerar médico si tiene al menos 2 palabras clave médicas
        return medical_count >= 2
    
    async def _calculate_memo_quality(self, memo: MicroMemoGenerado) -> float:
        """Calcula score de calidad de un micro-memo."""
        quality_factors = []
        
        # Factor 1: Longitud apropiada de pregunta y respuesta
        q_len = len(memo.question)
        a_len = len(memo.answer)
        
        q_score = 1.0 if 20 <= q_len <= 200 else max(0.3, 1.0 - abs(q_len - 100) / 100)
        a_score = 1.0 if 50 <= a_len <= 500 else max(0.3, 1.0 - abs(a_len - 200) / 200)
        
        quality_factors.extend([q_score, a_score])
        
        # Factor 2: Claridad (evitar palabras repetitivas)
        q_words = set(memo.question.lower().split())
        a_words = set(memo.answer.lower().split())
        
        # Penalizar demasiada repetición
        overlap = len(q_words & a_words)
        total_unique = len(q_words | a_words)
        clarity_score = 1.0 - (overlap / total_unique if total_unique > 0 else 0.5)
        quality_factors.append(max(0.3, clarity_score))
        
        # Factor 3: Confianza del LLM
        if memo.confidence_score:
            quality_factors.append(memo.confidence_score)
        
        # Factor 4: Coherencia (pregunta y respuesta relacionadas)
        coherence_score = 0.8  # Score base, podría mejorarse con análisis semántico
        quality_factors.append(coherence_score)
        
        # Promedio ponderado
        return sum(quality_factors) / len(quality_factors)
    
    async def _create_micro_memo_model(
        self,
        memo_data: MicroMemoGenerado,
        source: Union[OCRResult, LLMAnalysisResult, ResearchResult],
        config: ConfiguracionMicroMemo
    ) -> MicroMemo:
        """Crea modelo MicroMemo desde datos generados."""
        
        # Determinar el tipo de fuente y ID
        source_type = "manual"
        source_ocr_id = None
        source_llm_analysis_id = None
        source_research_id = None
        class_session_id = None
        
        if isinstance(source, OCRResult):
            source_type = "ocr"
            source_ocr_id = source.id
            class_session_id = source.class_session_id
        elif isinstance(source, LLMAnalysisResult):
            source_type = "llm_analysis"
            source_llm_analysis_id = source.id
            # Obtener class_session_id desde processing_job (requiere consulta)
        elif isinstance(source, ResearchResult):
            source_type = "research"
            source_research_id = source.id
            # Obtener class_session_id desde research_job
        
        # Determinar especialidad médica
        specialty = None
        if hasattr(source, 'medical_specialty'):
            specialty = source.medical_specialty
        elif memo_data.source_concept and memo_data.source_concept.specialty:
            specialty = memo_data.source_concept.specialty
        
        # Calcular próxima revisión si spaced repetition está habilitado
        next_review = None
        if config.enable_spaced_repetition:
            next_review = datetime.utcnow() + timedelta(days=1)  # Primera revisión en 1 día
        
        # Crear modelo MicroMemo
        micro_memo = MicroMemo(
            class_session_id=class_session_id,
            source_type=source_type,
            source_ocr_id=source_ocr_id,
            source_llm_analysis_id=source_llm_analysis_id,
            source_research_id=source_research_id,
            
            title=memo_data.title,
            question=memo_data.question,
            answer=memo_data.answer,
            explanation=memo_data.explanation,
            
            memo_type=memo_data.memo_type,
            difficulty_level=memo_data.difficulty_level,
            medical_specialty=specialty,
            tags=memo_data.tags,
            language=config.target_language,
            
            context_snippet=memo_data.source_concept.context[:500] if memo_data.source_concept else None,
            
            study_priority=min(10, max(1, int(memo_data.confidence_score * 10))),
            estimated_study_time=5,  # 5 minutos por defecto
            enable_spaced_repetition=config.enable_spaced_repetition,
            
            confidence_score=memo_data.confidence_score,
            quality_score=memo_data.confidence_score,  # Por ahora iguales
            requires_review=memo_data.confidence_score < 0.8,
            is_validated=config.auto_validate_high_confidence and memo_data.confidence_score > 0.9,
            
            next_review=next_review,
            current_interval=1,
            ease_factor=2.5
        )
        
        return micro_memo
    
    async def _deduplicate_concepts(self, concepts: List[ConceptoExtraido]) -> List[ConceptoExtraido]:
        """Elimina conceptos duplicados y similares."""
        unique_concepts = []
        seen_terms = set()
        
        for concept in concepts:
            # Normalizar término para comparación
            normalized_term = concept.term.lower().strip()
            
            # Verificar si es similar a alguno ya visto
            is_duplicate = any(
                self._terms_are_similar(normalized_term, seen_term)
                for seen_term in seen_terms
            )
            
            if not is_duplicate:
                unique_concepts.append(concept)
                seen_terms.add(normalized_term)
        
        # Ordenar por importancia
        unique_concepts.sort(key=lambda x: x.importance_score, reverse=True)
        return unique_concepts
    
    def _terms_are_similar(self, term1: str, term2: str) -> bool:
        """Verifica si dos términos médicos son similares."""
        # Verificar igualdad exacta
        if term1 == term2:
            return True
        
        # Verificar si uno contiene al otro (para variaciones)
        if term1 in term2 or term2 in term1:
            return True
        
        # Verificar similitud de Levenshtein simple
        if len(term1) > 5 and len(term2) > 5:
            common_chars = len(set(term1) & set(term2))
            max_len = max(len(term1), len(term2))
            similarity = common_chars / max_len
            return similarity > 0.8
        
        return False


# Instancia global del servicio
micro_memo_service = MicroMemoService()
