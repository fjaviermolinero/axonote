"""
Modelos SQLAlchemy de Axonote.
Define todas las entidades de la base de datos.
"""

from .class_session import ClassSession
from .professor import Professor 
from .source import Source
from .term import Term
from .card import Card
from .upload_session import UploadSession, ChunkUpload
from .processing_job import ProcessingJob
from .transcription_result import TranscriptionResult
from .diarization_result import DiarizationResult
from .llm_analysis_result import LLMAnalysisResult
from .post_processing_result import PostProcessingResult
from .medical_terminology import MedicalTerminology

__all__ = [
    "ClassSession",
    "Professor", 
    "Source",
    "Term",
    "Card",
    "UploadSession",
    "ChunkUpload",
    "ProcessingJob",
    "TranscriptionResult",
    "DiarizationResult",
    "LLMAnalysisResult",
    "PostProcessingResult",
    "MedicalTerminology"
]
