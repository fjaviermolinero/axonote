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
from .research_job import ResearchJob
from .research_result import ResearchResult
from .medical_source import MedicalSource
from .source_cache import SourceCache
from .notion_sync_record import NotionSyncRecord, NotionWorkspace, NotionConflictResolution
from .notion_template import NotionTemplate, NotionTemplateInstance, NotionBlockTemplate
from .ocr_result import OCRResult
from .micro_memo import MicroMemo
from .micro_memo_collection import MicroMemoCollection
from .export_session import ExportSession
from .tts_result import TTSResult
from .sesion_metrica import SesionMetrica
from .metrica_procesamiento import MetricaProcesamiento
from .metrica_calidad import MetricaCalidad
from .metrica_sistema import MetricaSistema

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
    "MedicalTerminology",
    "ResearchJob",
    "ResearchResult",
    "MedicalSource",
    "SourceCache",
    "NotionSyncRecord",
    "NotionWorkspace", 
    "NotionConflictResolution",
    "NotionTemplate",
    "NotionTemplateInstance",
    "NotionBlockTemplate",
    "OCRResult",
    "MicroMemo",
    "MicroMemoCollection",
    "ExportSession",
    "TTSResult",
    "SesionMetrica",
    "MetricaProcesamiento",
    "MetricaCalidad",
    "MetricaSistema"
]
