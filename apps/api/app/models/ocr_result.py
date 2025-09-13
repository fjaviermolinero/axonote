"""
Modelo OCRResult - Resultado de procesamiento OCR.
Representa el resultado de extracción de texto de documentos e imágenes médicas.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, 
    ForeignKey, JSON, DateTime
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class TipoContenidoOCR(str, Enum):
    """Tipos de contenido detectado por OCR."""
    PDF_MEDICO = "pdf_medico"                    # PDF con contenido médico
    SLIDE_PRESENTACION = "slide_presentacion"   # Slide de presentación
    DIAGRAMA_MEDICO = "diagrama_medico"         # Diagrama o esquema médico
    TEXTO_IMAGEN = "texto_imagen"               # Imagen con texto puro
    DOCUMENTO_ESCANEADO = "documento_escaneado" # Documento escaneado
    RECETA_MEDICA = "receta_medica"             # Receta o prescripción
    INFORME_MEDICO = "informe_medico"           # Informe médico
    MIXED_CONTENT = "mixed_content"             # Contenido mixto
    OTHER = "other"                             # Otro tipo


class EstadoOCR(str, Enum):
    """Estados del procesamiento OCR."""
    PENDING = "pending"         # Esperando procesamiento
    PROCESSING = "processing"   # Procesando
    COMPLETED = "completed"     # Completado exitosamente
    FAILED = "failed"          # Falló el procesamiento
    REVIEWING = "reviewing"     # Requiere revisión manual
    APPROVED = "approved"       # Aprobado tras revisión


class MotorOCR(str, Enum):
    """Motores OCR disponibles."""
    TESSERACT = "tesseract"         # Tesseract con configuración médica
    EASYOCR = "easyocr"            # EasyOCR para textos complejos
    PADDLE = "paddle"              # PaddleOCR para texto multilíngüe
    AZURE_VISION = "azure_vision"   # Azure Computer Vision (futuro)
    GOOGLE_VISION = "google_vision" # Google Vision API (futuro)


class OCRResult(BaseModel):
    """
    Resultado de procesamiento OCR de documentos médicos.
    
    Almacena el texto extraído, metadatos del procesamiento,
    análisis de contenido médico y métricas de calidad.
    """
    
    __tablename__ = "ocr_results"
    
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
    # METADATOS DEL ARCHIVO FUENTE
    # ==============================================
    
    # Identificador del archivo en MinIO
    source_file_id = Column(String(500), nullable=False, index=True)
    
    # Nombre original del archivo
    source_filename = Column(String(500), nullable=False)
    
    # Tipo de archivo fuente
    source_type = Column(String(50), nullable=False)  # pdf, png, jpg, tiff, etc.
    
    # Tamaño del archivo en bytes
    file_size = Column(Integer, nullable=False)
    
    # MIME type del archivo
    mime_type = Column(String(100), nullable=False)
    
    # Hash MD5 del archivo para detección de duplicados
    file_hash = Column(String(32), nullable=True, index=True)
    
    # ==============================================
    # CONFIGURACIÓN DE PROCESAMIENTO
    # ==============================================
    
    # Motor OCR utilizado
    ocr_engine = Column(String(50), nullable=False, default=MotorOCR.TESSERACT)
    
    # Idiomas configurados para OCR
    languages = Column(String(100), nullable=False, default="ita,eng")
    
    # Umbral de confianza configurado
    confidence_threshold = Column(Float, nullable=False, default=0.7)
    
    # Configuración específica del motor OCR (JSON)
    ocr_config = Column(JSON, nullable=True)
    
    # DPI utilizado para el procesamiento
    processing_dpi = Column(Integer, nullable=True, default=300)
    
    # ==============================================
    # RESULTADOS OCR
    # ==============================================
    
    # Texto extraído completo
    extracted_text = Column(Text, nullable=True)
    
    # Texto corregido con post-procesamiento médico
    corrected_text = Column(Text, nullable=True)
    
    # Datos completos del OCR en formato JSON
    # Incluye word boxes, confidence por palabra, etc.
    raw_ocr_data = Column(JSON, nullable=True)
    
    # Puntuación de confianza promedio
    confidence_score = Column(Float, nullable=True)
    
    # Puntuación de calidad calculada
    quality_score = Column(Float, nullable=True)
    
    # ==============================================
    # ANÁLISIS DE CONTENIDO
    # ==============================================
    
    # Idioma detectado del texto extraído
    detected_language = Column(String(10), nullable=True)
    
    # Tipo de contenido detectado
    content_type = Column(String(50), nullable=True)
    
    # Es contenido médico validado
    is_medical_content = Column(Boolean, nullable=False, default=False)
    
    # Términos médicos detectados (JSON array)
    medical_terms_detected = Column(JSON, nullable=True, default=list)
    
    # Especialidad médica detectada
    medical_specialty = Column(String(100), nullable=True)
    
    # Tags automáticos generados
    auto_tags = Column(JSON, nullable=True, default=list)
    
    # Análisis de estructura del documento
    document_structure = Column(JSON, nullable=True)
    
    # ==============================================
    # CONTROL DE CALIDAD
    # ==============================================
    
    # Estado del procesamiento OCR
    status = Column(String(20), nullable=False, default=EstadoOCR.PENDING)
    
    # Requiere revisión manual
    requires_review = Column(Boolean, nullable=False, default=False)
    
    # Motivo de revisión requerida
    review_reason = Column(String(200), nullable=True)
    
    # Notas de revisión manual
    review_notes = Column(Text, nullable=True)
    
    # Validado manualmente
    is_validated = Column(Boolean, nullable=False, default=False)
    
    # Usuario que validó (futuro)
    validated_by = Column(String(100), nullable=True)
    
    # Fecha de validación
    validated_at = Column(DateTime, nullable=True)
    
    # ==============================================
    # MÉTRICAS DE PERFORMANCE
    # ==============================================
    
    # Tiempo de procesamiento en segundos
    processing_time = Column(Float, nullable=True)
    
    # Número de páginas procesadas
    pages_processed = Column(Integer, nullable=False, default=1)
    
    # Número de palabras extraídas
    words_extracted = Column(Integer, nullable=True)
    
    # Número de caracteres en el texto extraído
    characters_extracted = Column(Integer, nullable=True)
    
    # Memoria utilizada durante el procesamiento (MB)
    memory_used_mb = Column(Float, nullable=True)
    
    # ==============================================
    # METADATOS ADICIONALES
    # ==============================================
    
    # Información de errores si el procesamiento falló
    error_message = Column(Text, nullable=True)
    
    # Detalles técnicos del error (JSON)
    error_details = Column(JSON, nullable=True)
    
    # Número de intentos de procesamiento
    processing_attempts = Column(Integer, nullable=False, default=1)
    
    # Última fecha de intento de procesamiento
    last_attempt_at = Column(DateTime, nullable=True)
    
    # Metadatos adicionales flexibles (JSON)
    ocr_metadata = Column(JSON, nullable=True, default=dict)
    
    # ==============================================
    # RELACIONES
    # ==============================================
    
    # Relación con la clase
    class_session = relationship(
        "ClassSession", 
        back_populates="ocr_results"
    )
    
    # Relación con micro-memos generados desde este OCR
    micro_memos = relationship(
        "MicroMemo", 
        back_populates="source_ocr",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return (
            f"<OCRResult("
            f"id={self.id}, "
            f"filename='{self.source_filename}', "
            f"content_type='{self.content_type}', "
            f"confidence={self.confidence_score:.3f}, "
            f"status='{self.status}'"
            f")>"
        )
    
    @property
    def is_completed(self) -> bool:
        """True si el procesamiento OCR está completado."""
        return self.status == EstadoOCR.COMPLETED
    
    @property
    def has_error(self) -> bool:
        """True si hay error en el procesamiento."""
        return self.status == EstadoOCR.FAILED
    
    @property
    def needs_review(self) -> bool:
        """True si requiere revisión manual."""
        return self.requires_review or self.status == EstadoOCR.REVIEWING
    
    @property
    def processing_success_rate(self) -> float:
        """Tasa de éxito del procesamiento (0-1)."""
        if self.processing_attempts == 0:
            return 0.0
        return 1.0 if self.is_completed else 0.0
    
    @property
    def text_quality_score(self) -> float:
        """Puntuación de calidad del texto extraído."""
        if not self.extracted_text:
            return 0.0
        
        # Calcular basado en confianza, longitud y contenido médico
        base_score = self.confidence_score or 0.0
        
        # Bonus por contenido médico validado
        if self.is_medical_content:
            base_score += 0.1
        
        # Bonus por texto con longitud adecuada
        if self.characters_extracted and self.characters_extracted > 100:
            base_score += 0.05
        
        return min(base_score, 1.0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario con información resumida."""
        return {
            "id": str(self.id),
            "class_session_id": str(self.class_session_id),
            "source_filename": self.source_filename,
            "content_type": self.content_type,
            "confidence_score": self.confidence_score,
            "quality_score": self.quality_score,
            "is_medical_content": self.is_medical_content,
            "status": self.status,
            "requires_review": self.requires_review,
            "pages_processed": self.pages_processed,
            "words_extracted": self.words_extracted,
            "processing_time": self.processing_time,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "medical_terms_count": len(self.medical_terms_detected or []),
            "medical_specialty": self.medical_specialty
        }
