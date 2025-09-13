"""
Modelo MicroMemo - Micro-memo/flashcard de estudio.
Representa tarjetas de estudio generadas automáticamente desde contenido procesado.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, 
    ForeignKey, JSON, DateTime, Table
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class TipoMicroMemo(str, Enum):
    """Tipos de micro-memos disponibles."""
    DEFINITION = "definition"       # Definición de término médico
    CONCEPT = "concept"            # Explicación de concepto complejo
    PROCESS = "process"            # Descripción de proceso/procedimiento
    CASE = "case"                  # Caso clínico con diagnóstico
    FACT = "fact"                  # Dato o hecho médico importante
    COMPARISON = "comparison"       # Comparación entre conceptos
    CLASSIFICATION = "classification" # Clasificación médica
    SYMPTOM = "symptom"            # Síntoma y diagnóstico diferencial
    TREATMENT = "treatment"        # Tratamiento o terapia
    ANATOMY = "anatomy"            # Anatomía y fisiología


class NivelDificultad(str, Enum):
    """Niveles de dificultad para micro-memos."""
    VERY_EASY = "very_easy"        # Muy fácil - conceptos básicos
    EASY = "easy"                  # Fácil - conceptos fundamentales
    MEDIUM = "medium"              # Medio - conceptos intermedios
    HARD = "hard"                  # Difícil - conceptos avanzados
    VERY_HARD = "very_hard"        # Muy difícil - conceptos expertos
    EXPERT = "expert"              # Experto - nivel especialización


class FuenteMicroMemo(str, Enum):
    """Fuentes de donde se genera el micro-memo."""
    TRANSCRIPTION = "transcription"    # Desde transcripción de clase
    OCR = "ocr"                       # Desde resultado OCR
    LLM_ANALYSIS = "llm_analysis"     # Desde análisis LLM
    RESEARCH = "research"             # Desde research médico
    MANUAL = "manual"                 # Creado manualmente
    HYBRID = "hybrid"                 # Combinación de múltiples fuentes


class EstadoMicroMemo(str, Enum):
    """Estados del micro-memo."""
    DRAFT = "draft"                   # Borrador generado
    PENDING_REVIEW = "pending_review" # Esperando revisión
    APPROVED = "approved"             # Aprobado para estudio
    REJECTED = "rejected"             # Rechazado
    NEEDS_IMPROVEMENT = "needs_improvement" # Necesita mejoras
    ARCHIVED = "archived"             # Archivado


class EspecialidadMedica(str, Enum):
    """Especialidades médicas para clasificación."""
    GENERAL = "general"                    # Medicina general
    CARDIOLOGY = "cardiology"             # Cardiología
    PULMONOLOGY = "pulmonology"           # Neumología
    NEUROLOGY = "neurology"               # Neurología
    GASTROENTEROLOGY = "gastroenterology" # Gastroenterología
    ENDOCRINOLOGY = "endocrinology"       # Endocrinología
    INFECTIOUS_DISEASE = "infectious_disease" # Infectología
    ONCOLOGY = "oncology"                 # Oncología
    SURGERY = "surgery"                   # Cirugía
    PEDIATRICS = "pediatrics"             # Pediatría
    GYNECOLOGY = "gynecology"             # Ginecología
    DERMATOLOGY = "dermatology"           # Dermatología
    PSYCHIATRY = "psychiatry"             # Psiquiatría
    RADIOLOGY = "radiology"               # Radiología
    PHARMACOLOGY = "pharmacology"         # Farmacología
    ANATOMY = "anatomy"                   # Anatomía
    PHYSIOLOGY = "physiology"             # Fisiología
    PATHOLOGY = "pathology"               # Patología
    OTHER = "other"                       # Otra especialidad


# Tabla de asociación many-to-many para colecciones
micro_memo_collection_association = Table(
    'micro_memo_collection_items',
    BaseModel.metadata,
    Column('micro_memo_id', UUID(as_uuid=True), ForeignKey('micro_memos.id'), primary_key=True),
    Column('collection_id', UUID(as_uuid=True), ForeignKey('micro_memo_collections.id'), primary_key=True),
    Column('position', Integer, nullable=True),  # Posición en la colección
    Column('added_at', DateTime, nullable=False, default=datetime.utcnow)
)


class MicroMemo(BaseModel):
    """
    Micro-memo/flashcard de estudio médico.
    
    Representa una tarjeta de estudio generada automáticamente
    desde contenido procesado (transcripciones, OCR, research).
    """
    
    __tablename__ = "micro_memos"
    
    # ==============================================
    # RELACIÓN CON CLASE
    # ==============================================
    
    class_session_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("class_sessions.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    
    # ==============================================
    # FUENTE DEL MICRO-MEMO
    # ==============================================
    
    # Tipo de fuente que generó el micro-memo
    source_type = Column(String(50), nullable=False, default=FuenteMicroMemo.MANUAL)
    
    # ID del resultado OCR fuente (si aplica)
    source_ocr_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("ocr_results.id", ondelete="SET NULL"), 
        nullable=True
    )
    
    # ID del análisis LLM fuente (si aplica)
    source_llm_analysis_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("llm_analysis_results.id", ondelete="SET NULL"), 
        nullable=True
    )
    
    # ID del resultado de research fuente (si aplica)
    source_research_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("research_results.id", ondelete="SET NULL"), 
        nullable=True
    )
    
    # ==============================================
    # CONTENIDO DEL MICRO-MEMO
    # ==============================================
    
    # Título/resumen del micro-memo
    title = Column(String(300), nullable=False, index=True)
    
    # Pregunta de la flashcard
    question = Column(Text, nullable=False)
    
    # Respuesta correcta
    answer = Column(Text, nullable=False)
    
    # Explicación adicional (opcional)
    explanation = Column(Text, nullable=True)
    
    # Pistas o ayudas para recordar
    hints = Column(JSON, nullable=True, default=list)
    
    # Información adicional de contexto
    additional_info = Column(Text, nullable=True)
    
    # ==============================================
    # CLASIFICACIÓN Y METADATOS
    # ==============================================
    
    # Tipo de micro-memo
    memo_type = Column(String(50), nullable=False, default=TipoMicroMemo.DEFINITION)
    
    # Nivel de dificultad
    difficulty_level = Column(String(20), nullable=False, default=NivelDificultad.MEDIUM)
    
    # Especialidad médica
    medical_specialty = Column(String(50), nullable=True)
    
    # Tags para categorización
    tags = Column(JSON, nullable=True, default=list)
    
    # Palabras clave principales
    keywords = Column(JSON, nullable=True, default=list)
    
    # Idioma del contenido
    language = Column(String(10), nullable=False, default="ita")
    
    # ==============================================
    # REFERENCIAS Y CONTEXTO
    # ==============================================
    
    # Fragmento de contexto original (máximo 500 chars)
    context_snippet = Column(String(500), nullable=True)
    
    # Términos médicos relacionados
    related_terms = Column(JSON, nullable=True, default=list)
    
    # Referencias bibliográficas o fuentes
    references = Column(JSON, nullable=True, default=list)
    
    # Enlaces a recursos externos
    external_links = Column(JSON, nullable=True, default=list)
    
    # ==============================================
    # CONFIGURACIÓN DE ESTUDIO
    # ==============================================
    
    # Prioridad de estudio (1-10, donde 10 es máxima prioridad)
    study_priority = Column(Integer, nullable=False, default=5)
    
    # Tiempo estimado de estudio en minutos
    estimated_study_time = Column(Integer, nullable=True, default=5)
    
    # Frecuencia de revisión recomendada (días)
    review_frequency_days = Column(Integer, nullable=True, default=7)
    
    # Habilitar repetición espaciada
    enable_spaced_repetition = Column(Boolean, nullable=False, default=True)
    
    # ==============================================
    # VALIDACIÓN Y CALIDAD
    # ==============================================
    
    # Estado del micro-memo
    status = Column(String(30), nullable=False, default=EstadoMicroMemo.DRAFT)
    
    # Puntuación de confianza de la generación automática (0-1)
    confidence_score = Column(Float, nullable=True)
    
    # Puntuación de calidad calculada (0-1)
    quality_score = Column(Float, nullable=True)
    
    # Requiere revisión manual
    requires_review = Column(Boolean, nullable=False, default=False)
    
    # Motivo de revisión requerida
    review_reason = Column(String(200), nullable=True)
    
    # Está validado manualmente
    is_validated = Column(Boolean, nullable=False, default=False)
    
    # Notas de validación
    validation_notes = Column(Text, nullable=True)
    
    # Usuario que validó (futuro)
    validated_by = Column(String(100), nullable=True)
    
    # Fecha de validación
    validated_at = Column(DateTime, nullable=True)
    
    # ==============================================
    # MÉTRICAS DE ESTUDIO Y PERFORMANCE
    # ==============================================
    
    # Número total de veces estudiado
    times_studied = Column(Integer, nullable=False, default=0)
    
    # Número de veces respondido correctamente
    times_correct = Column(Integer, nullable=False, default=0)
    
    # Número de veces respondido incorrectamente
    times_incorrect = Column(Integer, nullable=False, default=0)
    
    # Tasa de aciertos (calculada automáticamente)
    success_rate = Column(Float, nullable=True, default=0.0)
    
    # Tiempo promedio de respuesta en segundos
    avg_response_time = Column(Float, nullable=True)
    
    # Última vez que se estudió
    last_studied = Column(DateTime, nullable=True)
    
    # Próxima fecha de revisión recomendada
    next_review = Column(DateTime, nullable=True)
    
    # Número de días desde la última revisión
    days_since_last_review = Column(Integer, nullable=True)
    
    # Intervalo actual de repetición espaciada (días)
    current_interval = Column(Integer, nullable=True, default=1)
    
    # Factor de facilidad para repetición espaciada
    ease_factor = Column(Float, nullable=True, default=2.5)
    
    # ==============================================
    # METADATOS ADICIONALES
    # ==============================================
    
    # Información de errores en la generación
    generation_errors = Column(JSON, nullable=True)
    
    # Metadatos de generación (modelo LLM usado, etc.)
    generation_metadata = Column(JSON, nullable=True)
    
    # Metadatos adicionales flexibles
    memo_metadata = Column(JSON, nullable=True, default=dict)
    
    # Versión del micro-memo (para tracking de cambios)
    version = Column(Integer, nullable=False, default=1)
    
    # ==============================================
    # RELACIONES
    # ==============================================
    
    # Relación con la clase
    class_session = relationship(
        "ClassSession", 
        back_populates="micro_memos"
    )
    
    # Relación con resultado OCR (si aplica)
    source_ocr = relationship(
        "OCRResult", 
        back_populates="micro_memos"
    )
    
    # Relación con análisis LLM (si aplica)
    source_llm_analysis = relationship(
        "LLMAnalysisResult", 
        back_populates="micro_memos"
    )
    
    # Relación con resultado de research (si aplica)
    source_research = relationship(
        "ResearchResult", 
        back_populates="micro_memos"
    )
    
    # Relación many-to-many con colecciones
    collections = relationship(
        "MicroMemoCollection",
        secondary=micro_memo_collection_association,
        back_populates="memos"
    )
    
    def __repr__(self) -> str:
        return (
            f"<MicroMemo("
            f"id={self.id}, "
            f"title='{self.title[:30]}...', "
            f"type='{self.memo_type}', "
            f"difficulty='{self.difficulty_level}', "
            f"status='{self.status}'"
            f")>"
        )
    
    @property
    def is_approved(self) -> bool:
        """True si el micro-memo está aprobado para estudio."""
        return self.status == EstadoMicroMemo.APPROVED
    
    @property
    def is_ready_for_study(self) -> bool:
        """True si está listo para ser estudiado."""
        return self.status in [EstadoMicroMemo.APPROVED, EstadoMicroMemo.DRAFT] and not self.requires_review
    
    @property
    def needs_review_soon(self) -> bool:
        """True si necesita revisión pronto basado en repetición espaciada."""
        if not self.next_review:
            return True
        return datetime.utcnow() >= self.next_review
    
    @property
    def difficulty_score(self) -> float:
        """Puntuación numérica de dificultad (1-5)."""
        difficulty_mapping = {
            NivelDificultad.VERY_EASY: 1.0,
            NivelDificultad.EASY: 2.0,
            NivelDificultad.MEDIUM: 3.0,
            NivelDificultad.HARD: 4.0,
            NivelDificultad.VERY_HARD: 4.5,
            NivelDificultad.EXPERT: 5.0
        }
        return difficulty_mapping.get(self.difficulty_level, 3.0)
    
    @property
    def performance_rating(self) -> str:
        """Rating de performance basado en success_rate."""
        if self.success_rate is None or self.times_studied < 3:
            return "insufficient_data"
        
        if self.success_rate >= 0.9:
            return "excellent"
        elif self.success_rate >= 0.7:
            return "good"
        elif self.success_rate >= 0.5:
            return "needs_practice"
        else:
            return "difficult"
    
    def calculate_next_review(self) -> datetime:
        """Calcula la próxima fecha de revisión usando repetición espaciada."""
        if not self.last_studied:
            return datetime.utcnow() + timedelta(days=1)
        
        # Algoritmo simplificado de repetición espaciada
        if self.times_studied == 0:
            interval = 1
        elif self.times_studied == 1:
            interval = 3
        else:
            # Usar ease_factor y success_rate para calcular intervalo
            base_interval = self.current_interval or 1
            if self.success_rate and self.success_rate >= 0.8:
                interval = int(base_interval * (self.ease_factor or 2.5))
            else:
                interval = max(1, int(base_interval * 0.6))  # Reducir intervalo si hay problemas
        
        return self.last_studied + timedelta(days=interval)
    
    def record_study_session(self, correct: bool, response_time: Optional[float] = None):
        """Registra una sesión de estudio."""
        self.times_studied += 1
        self.last_studied = datetime.utcnow()
        
        if correct:
            self.times_correct += 1
        else:
            self.times_incorrect += 1
        
        # Actualizar success_rate
        self.success_rate = self.times_correct / self.times_studied
        
        # Actualizar tiempo promedio de respuesta
        if response_time:
            if self.avg_response_time:
                self.avg_response_time = (self.avg_response_time + response_time) / 2
            else:
                self.avg_response_time = response_time
        
        # Calcular próxima revisión
        self.next_review = self.calculate_next_review()
        
        # Actualizar intervalo actual
        if correct and self.success_rate and self.success_rate >= 0.8:
            self.current_interval = min(30, (self.current_interval or 1) * 2)
        elif not correct:
            self.current_interval = 1  # Reiniciar intervalo si falla
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario con información completa."""
        return {
            "id": str(self.id),
            "class_session_id": str(self.class_session_id),
            "title": self.title,
            "question": self.question,
            "answer": self.answer,
            "explanation": self.explanation,
            "memo_type": self.memo_type,
            "difficulty_level": self.difficulty_level,
            "medical_specialty": self.medical_specialty,
            "tags": self.tags or [],
            "keywords": self.keywords or [],
            "language": self.language,
            "study_priority": self.study_priority,
            "estimated_study_time": self.estimated_study_time,
            "status": self.status,
            "confidence_score": self.confidence_score,
            "quality_score": self.quality_score,
            "requires_review": self.requires_review,
            "is_validated": self.is_validated,
            "times_studied": self.times_studied,
            "success_rate": self.success_rate,
            "last_studied": self.last_studied.isoformat() if self.last_studied else None,
            "next_review": self.next_review.isoformat() if self.next_review else None,
            "needs_review_soon": self.needs_review_soon,
            "performance_rating": self.performance_rating,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "source_type": self.source_type,
            "related_terms": self.related_terms or [],
            "references": self.references or []
        }
    
    def to_study_card(self) -> Dict[str, Any]:
        """Convertir a formato de tarjeta de estudio simplificado."""
        return {
            "id": str(self.id),
            "title": self.title,
            "question": self.question,
            "answer": self.answer,
            "explanation": self.explanation,
            "hints": self.hints or [],
            "difficulty": self.difficulty_level,
            "specialty": self.medical_specialty,
            "tags": self.tags or [],
            "priority": self.study_priority,
            "estimated_time": self.estimated_study_time,
            "times_studied": self.times_studied,
            "success_rate": self.success_rate,
            "needs_review": self.needs_review_soon
        }
