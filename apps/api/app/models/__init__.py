"""
Modelos SQLAlchemy de Axonote.
Define todas las entidades de la base de datos.
"""

from .class_session import ClassSession
from .professor import Professor 
from .source import Source
from .term import Term
from .card import Card

__all__ = [
    "ClassSession",
    "Professor", 
    "Source",
    "Term",
    "Card"
]
