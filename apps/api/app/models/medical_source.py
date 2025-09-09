"""
Modelo MedicalSource para fuentes médicas verificadas.

Este modelo representa una fuente médica específica encontrada durante
el research automático, con toda la información bibliográfica,
contenido extraído y métricas de calidad.
"""

import enum
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey, Date
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import BaseModel


class TipoFuente(str, enum.Enum):
    """Tipos de fuentes médicas disponibles."""
    PUBMED = "pubmed"                    # Artículos de PubMed/NCBI
    WHO = "who"                          # Organización Mundial de la Salud
    NIH = "nih"                          # National Institutes of Health
    MEDLINEPLUS = "medlineplus"          # MedlinePlus (NIH)
    ISS = "iss"                          # Istituto Superiore di Sanità (Italia)
    AIFA = "aifa"                        # Agenzia Italiana del Farmaco
    MINISTRY_HEALTH = "ministry_health"   # Ministero della Salute (Italia)
    MAYO_CLINIC = "mayo_clinic"          # Mayo Clinic
    CLEVELAND_CLINIC = "cleveland_clinic" # Cleveland Clinic
    WEBMD = "webmd"                      # WebMD
    HEALTHLINE = "healthline"            # Healthline
    COCHRANE = "cochrane"                # Cochrane Library
    UPTODATE = "uptodate"                # UpToDate
    EMEDICINE = "emedicine"              # eMedicine
    OTHER = "other"                      # Otras fuentes


class CategoriaContenido(str, enum.Enum):
    """Categorías de contenido médico."""
    DEFINITION = "definition"            # Definición del término
    TREATMENT = "treatment"              # Información sobre tratamiento
    DIAGNOSIS = "diagnosis"              # Información sobre diagnóstico
    EPIDEMIOLOGY = "epidemiology"        # Datos epidemiológicos
    PATHOPHYSIOLOGY = "pathophysiology"  # Fisiopatología
    CLINICAL_TRIAL = "clinical_trial"    # Ensayo clínico
    GUIDELINE = "guideline"              # Guía clínica
    REVIEW = "review"                    # Artículo de revisión
    CASE_STUDY = "case_study"            # Estudio de caso
    META_ANALYSIS = "meta_analysis"      # Meta-análisis
    DRUG_INFO = "drug_info"              # Información de medicamentos
    PATIENT_INFO = "patient_info"        # Información para pacientes
    OTHER = "other"                      # Otro tipo de contenido


class AudienciaObjetivo(str, enum.Enum):
    """Audiencia objetivo del contenido."""
    PROFESSIONAL = "professional"        # Profesionales médicos
    STUDENT = "student"                  # Estudiantes de medicina
    PATIENT = "patient"                  # Pacientes y público general
    RESEARCHER = "researcher"            # Investigadores
    MIXED = "mixed"                      # Audiencia mixta


class TipoAcceso(str, enum.Enum):
    """Tipos de acceso al contenido."""
    FREE = "free"                        # Acceso gratuito
    SUBSCRIPTION = "subscription"        # Requiere suscripción
    PAYWALL = "paywall"                  # Pago por artículo
    INSTITUTIONAL = "institutional"      # Acceso institucional
    UNKNOWN = "unknown"                  # Tipo de acceso desconocido


class MedicalSource(BaseModel):
    """
    Fuente médica específica encontrada durante el research.
    
    Representa un artículo, página web o documento médico con toda
    la información bibliográfica, contenido extraído y métricas
    de calidad y relevancia.
    """
    
    __tablename__ = "medical_sources"
    
    # ==============================================
    # RELACIÓN CON RESULTADO DE RESEARCH
    # ==============================================
    
    research_result_id = Column(
        PostgresUUID(as_uuid=True), 
        ForeignKey("research_results.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    
    # ==============================================
    # INFORMACIÓN BÁSICA DE LA FUENTE
    # ==============================================
    
    # Título del artículo/documento
    title = Column(String(500), nullable=False)
    
    # URL de acceso
    url = Column(String(1000), nullable=False)
    
    # Tipo de fuente
    source_type = Column(String(50), nullable=False, index=True)
    
    # Dominio del sitio web
    domain = Column(String(200), nullable=True, index=True)
    
    # Idioma del contenido
    language = Column(String(10), nullable=False, default="en", index=True)
    
    # ==============================================
    # METADATOS ACADÉMICOS
    # ==============================================
    
    # Autores del artículo/documento
    authors = Column(JSON, nullable=True)  # [{"name": "Author Name", "affiliation": "Institution"}]
    
    # Fecha de publicación
    publication_date = Column(Date, nullable=True, index=True)
    
    # Nombre de la revista/publicación
    journal_name = Column(String(200), nullable=True, index=True)
    
    # Factor de impacto de la revista
    journal_impact_factor = Column(Float, nullable=True)
    
    # DOI (Digital Object Identifier)
    doi = Column(String(100), nullable=True, unique=True, index=True)
    
    # PMID (PubMed ID)
    pmid = Column(String(20), nullable=True, unique=True, index=True)
    
    # PMCID (PubMed Central ID)
    pmcid = Column(String(20), nullable=True, index=True)
    
    # ISBN (para libros)
    isbn = Column(String(20), nullable=True)
    
    # Número de citas (si disponible)
    citation_count = Column(Integer, nullable=True)
    
    # ==============================================
    # CONTENIDO EXTRAÍDO
    # ==============================================
    
    # Abstract/resumen del artículo
    abstract = Column(Text, nullable=True)
    
    # Puntos clave extraídos automáticamente
    key_points = Column(JSON, nullable=True)  # ["punto1", "punto2", "punto3"]
    
    # Extracto más relevante para el término buscado
    relevant_excerpt = Column(Text, nullable=True)
    
    # Conclusiones principales
    main_conclusions = Column(Text, nullable=True)
    
    # Metodología (para artículos de investigación)
    methodology = Column(Text, nullable=True)
    
    # Resultados principales
    main_results = Column(Text, nullable=True)
    
    # Limitaciones mencionadas
    limitations = Column(Text, nullable=True)
    
    # Palabras clave del artículo
    keywords = Column(JSON, nullable=True)  # ["keyword1", "keyword2"]
    
    # ==============================================
    # CLASIFICACIÓN DE CONTENIDO
    # ==============================================
    
    # Categoría principal del contenido
    content_category = Column(String(100), nullable=True, index=True)
    
    # Categorías secundarias
    secondary_categories = Column(JSON, nullable=True)  # ["category1", "category2"]
    
    # Audiencia objetivo
    target_audience = Column(String(50), nullable=False, default=AudienciaObjetivo.PROFESSIONAL)
    
    # Nivel de complejidad (1-5)
    complexity_level = Column(Integer, nullable=True)  # 1=básico, 5=muy avanzado
    
    # Especialidad médica principal
    medical_specialty = Column(String(100), nullable=True, index=True)
    
    # Especialidades secundarias
    secondary_specialties = Column(JSON, nullable=True)
    
    # ==============================================
    # MÉTRICAS DE CALIDAD
    # ==============================================
    
    # Score de relevancia para el término buscado (0-1)
    relevance_score = Column(Float, nullable=False, default=0.0, index=True)
    
    # Score de autoridad de la fuente (0-1)
    authority_score = Column(Float, nullable=False, default=0.0, index=True)
    
    # Score de recencia basado en fecha de publicación (0-1)
    recency_score = Column(Float, nullable=False, default=0.0)
    
    # Score de calidad del contenido (0-1)
    content_quality_score = Column(Float, nullable=False, default=0.0)
    
    # Score combinado final (0-1)
    overall_score = Column(Float, nullable=False, default=0.0, index=True)
    
    # ==============================================
    # INFORMACIÓN DE ACCESO
    # ==============================================
    
    # Tipo de acceso al contenido
    access_type = Column(String(20), nullable=False, default=TipoAcceso.FREE)
    
    # Costo de acceso (si aplica)
    access_cost = Column(Float, nullable=True)
    
    # Moneda del costo
    cost_currency = Column(String(3), nullable=True)  # USD, EUR, etc.
    
    # Última vez que se accedió al contenido
    last_accessed = Column(DateTime, nullable=False, default=func.now())
    
    # Hash del contenido para detectar cambios
    content_hash = Column(String(64), nullable=True, index=True)
    
    # Tamaño del contenido en caracteres
    content_size = Column(Integer, nullable=True)
    
    # ==============================================
    # VALIDACIÓN Y VERIFICACIÓN
    # ==============================================
    
    # Verificación de hechos completada
    fact_checked = Column(Boolean, nullable=False, default=False)
    
    # Resultado de la verificación de hechos
    fact_check_result = Column(String(20), nullable=True)  # verified, disputed, false
    
    # Artículo peer-reviewed
    peer_reviewed = Column(Boolean, nullable=False, default=False)
    
    # Fuente oficial (gobierno, organización reconocida)
    official_source = Column(Boolean, nullable=False, default=False)
    
    # Nivel de evidencia (1-5, siendo 1 el más alto)
    evidence_level = Column(Integer, nullable=True)
    
    # Grado de recomendación (A, B, C, D)
    recommendation_grade = Column(String(1), nullable=True)
    
    # ==============================================
    # METADATOS DE EXTRACCIÓN
    # ==============================================
    
    # Método utilizado para extraer el contenido
    extraction_method = Column(String(50), nullable=True)  # api, scraping, manual
    
    # Versión del extractor utilizado
    extractor_version = Column(String(20), nullable=True)
    
    # Tiempo de extracción en milisegundos
    extraction_time_ms = Column(Integer, nullable=True)
    
    # Errores durante la extracción
    extraction_errors = Column(JSON, nullable=True)
    
    # Warnings durante la extracción
    extraction_warnings = Column(JSON, nullable=True)
    
    # ==============================================
    # INFORMACIÓN DE ACTUALIZACIÓN
    # ==============================================
    
    # Fecha de última actualización del contenido original
    source_last_updated = Column(DateTime, nullable=True)
    
    # Frecuencia de actualización de la fuente
    update_frequency = Column(String(20), nullable=True)  # daily, weekly, monthly, yearly
    
    # Indica si el contenido está desactualizado
    is_outdated = Column(Boolean, nullable=False, default=False)
    
    # Razón por la que está desactualizado
    outdated_reason = Column(String(200), nullable=True)
    
    # Próxima fecha de verificación
    next_check_date = Column(DateTime, nullable=True)
    
    # ==============================================
    # METADATOS ADICIONALES
    # ==============================================
    
    # Configuración específica utilizada para esta fuente
    extraction_config = Column(JSON, nullable=True)
    
    # Estadísticas de uso de esta fuente
    usage_stats = Column(JSON, nullable=True)  # {"views": 10, "citations": 5}
    
    # Flags de características especiales
    is_retracted = Column(Boolean, nullable=False, default=False)  # Artículo retirado
    is_preprint = Column(Boolean, nullable=False, default=False)   # Pre-publicación
    is_open_access = Column(Boolean, nullable=False, default=False) # Acceso abierto
    has_full_text = Column(Boolean, nullable=False, default=False)  # Texto completo disponible
    
    # Notas adicionales
    notes = Column(Text, nullable=True)
    
    # ==============================================
    # RELACIONES
    # ==============================================
    
    # Relación con el resultado de research
    research_result = relationship(
        "ResearchResult", 
        back_populates="medical_sources"
    )
    
    # ==============================================
    # PROPIEDADES CALCULADAS
    # ==============================================
    
    @property
    def age_in_days(self) -> Optional[int]:
        """Edad del artículo en días."""
        if not self.publication_date:
            return None
        
        today = date.today()
        return (today - self.publication_date).days
    
    @property
    def age_in_years(self) -> Optional[float]:
        """Edad del artículo en años."""
        if not self.age_in_days:
            return None
        
        return self.age_in_days / 365.25
    
    @property
    def is_recent(self) -> bool:
        """Indica si el artículo es reciente (< 2 años)."""
        if not self.age_in_years:
            return False
        
        return self.age_in_years < 2.0
    
    @property
    def is_high_quality(self) -> bool:
        """Indica si es una fuente de alta calidad."""
        return (
            self.peer_reviewed or
            self.official_source or
            self.authority_score > 0.8 or
            (self.journal_impact_factor and self.journal_impact_factor > 5.0)
        )
    
    @property
    def citation_info(self) -> str:
        """Genera información de cita en formato APA simplificado."""
        citation_parts = []
        
        # Autores
        if self.authors and len(self.authors) > 0:
            if len(self.authors) == 1:
                citation_parts.append(f"{self.authors[0].get('name', 'Unknown')}")
            elif len(self.authors) <= 3:
                author_names = [author.get('name', 'Unknown') for author in self.authors]
                citation_parts.append(", ".join(author_names))
            else:
                citation_parts.append(f"{self.authors[0].get('name', 'Unknown')} et al.")
        
        # Año
        if self.publication_date:
            citation_parts.append(f"({self.publication_date.year})")
        
        # Título
        citation_parts.append(f"{self.title}")
        
        # Revista
        if self.journal_name:
            citation_parts.append(f"{self.journal_name}")
        
        # DOI o URL
        if self.doi:
            citation_parts.append(f"DOI: {self.doi}")
        elif self.url:
            citation_parts.append(f"Retrieved from {self.url}")
        
        return ". ".join(citation_parts)
    
    @property
    def quality_indicators(self) -> Dict[str, bool]:
        """Indicadores de calidad de la fuente."""
        return {
            "peer_reviewed": self.peer_reviewed,
            "official_source": self.official_source,
            "recent": self.is_recent,
            "high_impact": self.journal_impact_factor and self.journal_impact_factor > 3.0,
            "open_access": self.is_open_access,
            "full_text": self.has_full_text,
            "fact_checked": self.fact_checked,
            "high_authority": self.authority_score > 0.8
        }
    
    def calculate_overall_score(self) -> float:
        """
        Calcula el score general combinando todas las métricas.
        
        Returns:
            Score general (0-1)
        """
        # Pesos para diferentes aspectos
        weights = {
            'relevance': 0.35,    # Más importante: relevancia al término
            'authority': 0.25,    # Autoridad de la fuente
            'recency': 0.15,      # Qué tan reciente es
            'quality': 0.15,      # Calidad del contenido
            'peer_review': 0.05,  # Bonus por peer review
            'official': 0.05      # Bonus por fuente oficial
        }
        
        score = (
            self.relevance_score * weights['relevance'] +
            self.authority_score * weights['authority'] +
            self.recency_score * weights['recency'] +
            self.content_quality_score * weights['quality']
        )
        
        # Bonificaciones
        if self.peer_reviewed:
            score += weights['peer_review']
        
        if self.official_source:
            score += weights['official']
        
        return min(1.0, max(0.0, score))
    
    def update_recency_score(self) -> None:
        """Actualiza el score de recencia basado en la fecha de publicación."""
        if not self.publication_date:
            self.recency_score = 0.0
            return
        
        age_years = self.age_in_years
        if age_years is None:
            self.recency_score = 0.0
            return
        
        # Score decae exponencialmente con la edad
        if age_years <= 1:
            self.recency_score = 1.0
        elif age_years <= 2:
            self.recency_score = 0.8
        elif age_years <= 5:
            self.recency_score = 0.6
        elif age_years <= 10:
            self.recency_score = 0.4
        else:
            self.recency_score = 0.2
    
    def update_authority_score(self) -> None:
        """Actualiza el score de autoridad basado en el tipo de fuente y metadatos."""
        base_scores = {
            TipoFuente.PUBMED: 0.9,
            TipoFuente.WHO: 0.95,
            TipoFuente.NIH: 0.9,
            TipoFuente.COCHRANE: 0.95,
            TipoFuente.ISS: 0.85,
            TipoFuente.AIFA: 0.8,
            TipoFuente.MAYO_CLINIC: 0.8,
            TipoFuente.CLEVELAND_CLINIC: 0.75,
            TipoFuente.UPTODATE: 0.85,
            TipoFuente.MEDLINEPLUS: 0.7,
            TipoFuente.WEBMD: 0.6,
            TipoFuente.HEALTHLINE: 0.6,
            TipoFuente.OTHER: 0.5
        }
        
        base_score = base_scores.get(self.source_type, 0.5)
        
        # Bonificaciones
        if self.peer_reviewed:
            base_score += 0.1
        
        if self.official_source:
            base_score += 0.05
        
        if self.journal_impact_factor and self.journal_impact_factor > 5:
            base_score += 0.05
        
        self.authority_score = min(1.0, base_score)
    
    def is_accessible(self) -> bool:
        """Indica si la fuente es accesible (no requiere pago)."""
        return self.access_type in [TipoAcceso.FREE, TipoAcceso.UNKNOWN]
    
    def get_summary_for_citation(self) -> Dict[str, Any]:
        """
        Obtiene información resumida para citas y referencias.
        
        Returns:
            Diccionario con información de cita
        """
        return {
            "title": self.title,
            "authors": self.authors,
            "journal": self.journal_name,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            "doi": self.doi,
            "pmid": self.pmid,
            "url": self.url,
            "source_type": self.source_type,
            "citation": self.citation_info,
            "quality_indicators": self.quality_indicators,
            "overall_score": self.overall_score
        }
    
    def mark_as_outdated(self, reason: str) -> None:
        """
        Marca la fuente como desactualizada.
        
        Args:
            reason: Razón por la que está desactualizada
        """
        self.is_outdated = True
        self.outdated_reason = reason
        self.next_check_date = None
    
    def schedule_next_check(self, days_from_now: int = 30) -> None:
        """
        Programa la próxima verificación de la fuente.
        
        Args:
            days_from_now: Días desde ahora para la próxima verificación
        """
        from datetime import timedelta
        self.next_check_date = datetime.utcnow() + timedelta(days=days_from_now)
    
    def __repr__(self) -> str:
        return (
            f"<MedicalSource(id={self.id}, "
            f"title='{self.title[:50]}...', "
            f"source_type={self.source_type}, "
            f"relevance={self.relevance_score:.2f}, "
            f"authority={self.authority_score:.2f})>"
        )
