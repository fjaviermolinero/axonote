"""
Modelos para templates y estructuras de Notion.
Define los templates disponibles y configuraciones de formato.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, String, Text, Boolean, JSON, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class TipoTemplateNotion(str, Enum):
    """Tipos de templates disponibles para Notion."""
    CLASE_MAGISTRAL = "clase_magistral"
    SEMINARIO_CLINICO = "seminario_clinico"
    CASO_CLINICO = "caso_clinico"
    CONFERENCIA = "conferencia"
    WORKSHOP = "workshop"
    REUNION_EQUIPO = "reunion_equipo"
    EXAMEN_ORAL = "examen_oral"
    PRESENTACION = "presentacion"
    TUTORIAL = "tutorial"
    CUSTOM = "custom"


class EstadoTemplateNotion(str, Enum):
    """Estados de un template."""
    ACTIVO = "activo"
    INACTIVO = "inactivo"
    EN_PRUEBA = "en_prueba"
    DEPRECATED = "deprecated"


class NotionTemplate(Base):
    """
    Template de Notion para diferentes tipos de contenido.
    
    Define la estructura, propiedades y bloques que se crean
    automáticamente para cada tipo de clase o contenido.
    """
    __tablename__ = "notion_templates"
    
    # Identificadores
    id: UUID = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    template_name: str = Column(String(100), nullable=False, unique=True)
    template_type: TipoTemplateNotion = Column(String(50), nullable=False, index=True)
    
    # Información básica
    display_name: str = Column(String(150), nullable=False)
    description: str = Column(Text, nullable=True)
    version: str = Column(String(20), nullable=False, default="1.0.0")
    
    # Configuración del template
    template_config: Dict[str, Any] = Column(JSON, nullable=False)
    """
    Configuración completa del template:
    {
        "page_properties": {
            "Profesor": {"type": "title"},
            "Materia": {"type": "select", "options": [...]},
            "Fecha": {"type": "date"},
            "Duración": {"type": "number"},
            "Estado": {"type": "select", "options": ["Procesado", "En Revisión", "Completo"]},
            "Calidad": {"type": "select", "options": ["Alta", "Media", "Baja"]},
            "Tags": {"type": "multi_select"}
        },
        "block_structure": [
            {
                "type": "header",
                "template": "header_with_metadata",
                "config": {...}
            },
            {
                "type": "summary",
                "template": "collapsible_summary",
                "config": {...}
            },
            ...
        ],
        "auto_detection_rules": [
            {
                "condition": "duration > 60 AND speakers > 1",
                "confidence": 0.9
            }
        ]
    }
    """
    
    # Reglas de auto-detección
    auto_detection_rules: List[Dict[str, Any]] = Column(JSON, nullable=False, default=list)
    """
    Reglas para detección automática del template:
    [
        {
            "condition": "keywords_match",
            "keywords": ["caso clínico", "diagnóstico", "tratamiento"],
            "weight": 0.8
        },
        {
            "condition": "duration_range",
            "min_minutes": 30,
            "max_minutes": 90,
            "weight": 0.6
        },
        {
            "condition": "speaker_count",
            "min_speakers": 1,
            "max_speakers": 3,
            "weight": 0.5
        }
    ]
    """
    
    # Configuración de contenido
    content_mapping: Dict[str, Any] = Column(JSON, nullable=False, default=dict)
    """
    Mapeo de contenido de Axonote a bloques Notion:
    {
        "transcription": {
            "target_block": "transcription_block",
            "format": "toggle_with_paragraphs",
            "max_length": 5000,
            "truncate_strategy": "smart"
        },
        "llm_analysis": {
            "summary": {
                "target_block": "summary_block",
                "format": "callout"
            },
            "key_concepts": {
                "target_block": "concepts_list",
                "format": "bulleted_list"
            },
            "medical_terms": {
                "target_block": "terminology_database",
                "format": "table"
            }
        },
        "research_results": {
            "target_block": "sources_section",
            "format": "embed_database",
            "max_sources": 20
        }
    }
    """
    
    # Configuración de estilo
    style_config: Dict[str, Any] = Column(JSON, nullable=False, default=dict)
    """
    Configuración de estilo y formato:
    {
        "colors": {
            "primary": "blue",
            "secondary": "gray",
            "success": "green",
            "warning": "orange",
            "error": "red"
        },
        "icons": {
            "page_icon": "🎓",
            "header_icon": "📚",
            "summary_icon": "📋",
            "transcription_icon": "🎵",
            "analysis_icon": "🔬",
            "sources_icon": "📖"
        },
        "formatting": {
            "use_callouts": true,
            "use_toggles": true,
            "use_dividers": true,
            "code_block_language": "text"
        }
    }
    """
    
    # Estado y metadatos
    status: EstadoTemplateNotion = Column(String(20), nullable=False, default=EstadoTemplateNotion.ACTIVO)
    is_default: bool = Column(Boolean, nullable=False, default=False)
    priority: int = Column(Integer, nullable=False, default=100)  # Para ordenar templates
    
    # Estadísticas de uso
    usage_stats: Dict[str, Any] = Column(JSON, nullable=False, default=dict)
    """
    Estadísticas de uso del template:
    {
        "total_uses": 45,
        "success_rate": 0.95,
        "avg_generation_time": 2.3,
        "last_used": "2024-01-15T10:30:00Z",
        "user_ratings": {
            "average": 4.2,
            "count": 12
        }
    }
    """
    
    # Timestamps
    created_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at: Optional[datetime] = Column(DateTime, nullable=True)
    
    # Relaciones
    template_instances = relationship("NotionTemplateInstance", back_populates="template", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return (
            f"<NotionTemplate("
            f"name={self.template_name}, "
            f"type={self.template_type}, "
            f"status={self.status}"
            f")>"
        )
    
    @property
    def is_active(self) -> bool:
        """Verificar si el template está activo."""
        return self.status == EstadoTemplateNotion.ACTIVO
    
    @property
    def auto_detection_confidence(self) -> float:
        """Calcular confianza promedio de auto-detección."""
        if not self.auto_detection_rules:
            return 0.0
        
        weights = [rule.get("weight", 0.5) for rule in self.auto_detection_rules]
        return sum(weights) / len(weights)
    
    def calculate_match_score(self, content_data: Dict[str, Any]) -> float:
        """
        Calcular score de coincidencia para auto-detección.
        
        Args:
            content_data: Datos del contenido a evaluar
            
        Returns:
            Score de 0.0 a 1.0 indicando qué tan bien coincide
        """
        if not self.auto_detection_rules:
            return 0.0
        
        total_score = 0.0
        total_weight = 0.0
        
        for rule in self.auto_detection_rules:
            condition = rule.get("condition")
            weight = rule.get("weight", 0.5)
            
            rule_score = self._evaluate_detection_rule(rule, content_data)
            total_score += rule_score * weight
            total_weight += weight
        
        return total_score / total_weight if total_weight > 0 else 0.0
    
    def _evaluate_detection_rule(self, rule: Dict[str, Any], content_data: Dict[str, Any]) -> float:
        """Evaluar una regla específica de detección."""
        condition = rule.get("condition")
        
        if condition == "keywords_match":
            return self._evaluate_keywords_match(rule, content_data)
        elif condition == "duration_range":
            return self._evaluate_duration_range(rule, content_data)
        elif condition == "speaker_count":
            return self._evaluate_speaker_count(rule, content_data)
        elif condition == "content_length":
            return self._evaluate_content_length(rule, content_data)
        
        return 0.0
    
    def _evaluate_keywords_match(self, rule: Dict[str, Any], content_data: Dict[str, Any]) -> float:
        """Evaluar coincidencia de keywords."""
        keywords = rule.get("keywords", [])
        if not keywords:
            return 0.0
        
        # Buscar keywords en transcript y análisis
        text_sources = [
            content_data.get("transcription", {}).get("text", ""),
            content_data.get("llm_analysis", {}).get("summary", ""),
            " ".join(content_data.get("llm_analysis", {}).get("key_concepts", []))
        ]
        
        full_text = " ".join(text_sources).lower()
        matches = sum(1 for keyword in keywords if keyword.lower() in full_text)
        
        return matches / len(keywords)
    
    def _evaluate_duration_range(self, rule: Dict[str, Any], content_data: Dict[str, Any]) -> float:
        """Evaluar rango de duración."""
        duration = content_data.get("duration_minutes", 0)
        min_duration = rule.get("min_minutes", 0)
        max_duration = rule.get("max_minutes", float('inf'))
        
        if min_duration <= duration <= max_duration:
            # Score completo si está en rango
            return 1.0
        elif duration < min_duration:
            # Score parcial si está cerca del mínimo
            diff = min_duration - duration
            return max(0.0, 1.0 - (diff / min_duration))
        else:
            # Score parcial si está cerca del máximo
            if max_duration == float('inf'):
                return 0.5  # Penalizar levemente duraciones muy largas
            diff = duration - max_duration
            return max(0.0, 1.0 - (diff / max_duration))
    
    def _evaluate_speaker_count(self, rule: Dict[str, Any], content_data: Dict[str, Any]) -> float:
        """Evaluar número de speakers."""
        speaker_count = content_data.get("speaker_count", 1)
        min_speakers = rule.get("min_speakers", 1)
        max_speakers = rule.get("max_speakers", 10)
        
        if min_speakers <= speaker_count <= max_speakers:
            return 1.0
        else:
            # Score parcial basado en cercanía al rango
            if speaker_count < min_speakers:
                return speaker_count / min_speakers
            else:
                return max_speakers / speaker_count
    
    def _evaluate_content_length(self, rule: Dict[str, Any], content_data: Dict[str, Any]) -> float:
        """Evaluar longitud del contenido."""
        text_length = len(content_data.get("transcription", {}).get("text", ""))
        min_length = rule.get("min_length", 0)
        max_length = rule.get("max_length", float('inf'))
        
        if min_length <= text_length <= max_length:
            return 1.0
        elif text_length < min_length:
            return text_length / min_length if min_length > 0 else 0.0
        else:
            if max_length == float('inf'):
                return 0.8  # Penalizar levemente textos muy largos
            return max_length / text_length
    
    def update_usage_stats(self, generation_time: float, success: bool, rating: Optional[float] = None) -> None:
        """Actualizar estadísticas de uso."""
        if not self.usage_stats:
            self.usage_stats = {
                "total_uses": 0,
                "success_count": 0,
                "total_generation_time": 0.0,
                "user_ratings": {"total": 0.0, "count": 0}
            }
        
        self.usage_stats["total_uses"] += 1
        self.usage_stats["total_generation_time"] += generation_time
        
        if success:
            self.usage_stats["success_count"] += 1
        
        # Calcular métricas derivadas
        total_uses = self.usage_stats["total_uses"]
        self.usage_stats["success_rate"] = self.usage_stats["success_count"] / total_uses
        self.usage_stats["avg_generation_time"] = self.usage_stats["total_generation_time"] / total_uses
        
        # Actualizar rating si se proporciona
        if rating is not None:
            ratings = self.usage_stats["user_ratings"]
            ratings["total"] += rating
            ratings["count"] += 1
            ratings["average"] = ratings["total"] / ratings["count"]
        
        self.last_used_at = datetime.utcnow()


class NotionTemplateInstance(Base):
    """
    Instancia específica de un template aplicado a contenido.
    
    Registra cómo se aplicó un template específico, qué bloques
    se generaron y qué modificaciones se hicieron.
    """
    __tablename__ = "notion_template_instances"
    
    # Identificadores
    id: UUID = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    template_id: UUID = Column(
        PG_UUID(as_uuid=True), 
        ForeignKey("notion_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Elemento al que se aplicó
    entity_type: str = Column(String(50), nullable=False)
    entity_id: UUID = Column(PG_UUID(as_uuid=True), nullable=False)
    notion_page_id: str = Column(String(100), nullable=False, index=True)
    
    # Configuración aplicada
    applied_config: Dict[str, Any] = Column(JSON, nullable=False)
    """Configuración específica aplicada en esta instancia"""
    
    # Resultado de la aplicación
    generated_blocks: List[Dict[str, Any]] = Column(JSON, nullable=False, default=list)
    """Bloques generados para esta instancia"""
    
    generation_metadata: Dict[str, Any] = Column(JSON, nullable=False, default=dict)
    """
    Metadatos de la generación:
    {
        "generation_time": 2.3,
        "blocks_created": 12,
        "auto_detected": true,
        "confidence_score": 0.85,
        "customizations_applied": ["custom_icon", "modified_structure"]
    }
    """
    
    # Estado
    is_active: bool = Column(Boolean, nullable=False, default=True)
    
    # Timestamps
    created_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_modified_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    template = relationship("NotionTemplate", back_populates="template_instances")
    
    def __repr__(self) -> str:
        return (
            f"<NotionTemplateInstance("
            f"id={self.id}, "
            f"template_id={self.template_id}, "
            f"entity_type={self.entity_type}, "
            f"notion_page_id={self.notion_page_id}"
            f")>"
        )


class NotionBlockTemplate(Base):
    """
    Template específico para bloques individuales de Notion.
    
    Define plantillas reutilizables para diferentes tipos de
    bloques que se pueden combinar en templates más grandes.
    """
    __tablename__ = "notion_block_templates"
    
    # Identificadores
    id: UUID = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    block_name: str = Column(String(100), nullable=False, unique=True)
    block_type: str = Column(String(50), nullable=False)  # "header", "summary", "transcription", etc.
    
    # Información básica
    display_name: str = Column(String(150), nullable=False)
    description: str = Column(Text, nullable=True)
    
    # Configuración del bloque
    block_config: Dict[str, Any] = Column(JSON, nullable=False)
    """
    Configuración del bloque:
    {
        "notion_block_type": "toggle",
        "structure": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": "{{title}}"}
                }
            ],
            "children": [...]
        },
        "variables": {
            "title": {"type": "string", "required": true},
            "content": {"type": "string", "required": true},
            "icon": {"type": "emoji", "default": "📋"}
        }
    }
    """
    
    # Variables y parámetros
    variables: Dict[str, Any] = Column(JSON, nullable=False, default=dict)
    """Definición de variables del template"""
    
    # Estado
    is_active: bool = Column(Boolean, nullable=False, default=True)
    
    # Timestamps
    created_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: datetime = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self) -> str:
        return (
            f"<NotionBlockTemplate("
            f"name={self.block_name}, "
            f"type={self.block_type}"
            f")>"
        )
