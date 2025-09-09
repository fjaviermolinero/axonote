"""
Esquemas Pydantic para validación de datos en Axonote.
Define todos los modelos de entrada y salida de la API.
"""

from .class_session import (
    ClassSessionCreate,
    ClassSessionUpdate,
    ClassSessionResponse,
    ClassSessionList
)
from .professor import (
    ProfessorCreate,
    ProfessorUpdate,
    ProfessorResponse
)
from .source import (
    SourceCreate,
    SourceResponse
)
from .term import (
    TermCreate,
    TermResponse
)
from .card import (
    CardCreate,
    CardResponse,
    CardStudySession
)

__all__ = [
    "ClassSessionCreate",
    "ClassSessionUpdate", 
    "ClassSessionResponse",
    "ClassSessionList",
    "ProfessorCreate",
    "ProfessorUpdate",
    "ProfessorResponse",
    "SourceCreate",
    "SourceResponse",
    "TermCreate",
    "TermResponse",
    "CardCreate",
    "CardResponse",
    "CardStudySession"
]
