"""
Modelo Source - Fuentes médicas utilizadas.
Representa fuentes bibliográficas y médicas utilizadas para ampliación de contenido.
"""

from typing import Optional
from sqlalchemy import Column, String, Integer, ForeignKey, Index, Text, Float, Boolean, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Source(BaseModel):
    """
    Fuente médica/bibliográfica utilizada en ampliación de contenido.
    
    Almacena información de las fuentes verificadas utilizadas para
    enriquecer el contenido de las clases con información médica adicional.
    """
    
    __tablename__ = "sources"
    
    # ==============================================
    # RELACIÓN CON CLASE
    # ==============================================
    
    class_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("class_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # ==============================================
    # INFORMACIÓN BIBLIOGRÁFICA
    # ==============================================
    
    titulo = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False, index=True)
    
    # Editor/Organización (WHO, CDC, NIH, etc.)
    editor = Column(String(200), nullable=False, index=True)
    
    # Tipo de fuente
    tipo = Column(String(50), nullable=False, index=True)  # article, guideline, report, etc.
    
    # Año de publicación
    anio = Column(Integer, nullable=True, index=True)
    
    # DOI o PMID si está disponible
    doi_pmid = Column(String(200), nullable=True, index=True)
    
    # ==============================================
    # METADATOS DE USO
    # ==============================================
    
    # ID único del anchor en el contenido ([^1], [^2], etc.)
    anchor_id = Column(String(10), nullable=False)
    
    # Extracto relevante citado
    extracto = Column(Text, nullable=True)
    
    # Confianza en la fuente (0-1)
    confianza = Column(Float, nullable=True, default=1.0)
    
    # Fecha de acceso a la URL
    fecha_acceso = Column(Date, nullable=True)
    
    # ==============================================
    # VERIFICACIÓN DE CALIDAD
    # ==============================================
    
    # URL verificada y accesible
    url_verificada = Column(Boolean, nullable=False, default=False)
    
    # Contenido relacionado con el tema de la clase
    contenido_relevante = Column(Boolean, nullable=False, default=True)
    
    # Fuente en whitelist de fuentes médicas aprobadas
    fuente_aprobada = Column(Boolean, nullable=False, default=False)
    
    # ==============================================
    # RELACIONES
    # ==============================================
    
    class_session = relationship("ClassSession", back_populates="sources")
    
    def __repr__(self) -> str:
        return (
            f"<Source("
            f"id={self.id}, "
            f"titulo='{self.titulo[:50]}...', "
            f"editor='{self.editor}', "
            f"anchor_id='{self.anchor_id}'"
            f")>"
        )
    
    @property
    def citation_vancouver(self) -> str:
        """
        Generar cita en formato Vancouver/AMA simplificado.
        Ejemplo: "1. Título — Editor; 2023. URL (DOI/PMID)"
        """
        citation = f"{self.titulo} — {self.editor}"
        
        if self.anio:
            citation += f"; {self.anio}"
        
        citation += f". {self.url}"
        
        if self.doi_pmid:
            if self.doi_pmid.startswith("10."):
                citation += f" (DOI: {self.doi_pmid})"
            else:
                citation += f" (PMID: {self.doi_pmid})"
        
        return citation
    
    @property
    def domain(self) -> Optional[str]:
        """Extraer dominio de la URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.url)
            return parsed.netloc.lower()
        except Exception:
            return None
    
    @property
    def is_trusted_source(self) -> bool:
        """Verificar si es una fuente de confianza."""
        if not self.domain:
            return False
        
        trusted_domains = [
            "who.int", "ecdc.europa.eu", "cdc.gov", "nih.gov",
            "pubmed.ncbi.nlm.nih.gov", "nice.org.uk", "ema.europa.eu",
            "cochrane.org"
        ]
        
        return any(domain in self.domain for domain in trusted_domains)
    
    def validate_url(self) -> bool:
        """
        Validar que la URL sea accesible.
        Actualiza url_verificada según el resultado.
        """
        try:
            import httpx
            response = httpx.get(self.url, timeout=10)
            self.url_verificada = response.status_code == 200
            return self.url_verificada
        except Exception:
            self.url_verificada = False
            return False


# Índices para optimizar consultas frecuentes
Index('idx_source_class_anchor', Source.class_id, Source.anchor_id)
Index('idx_source_editor_tipo', Source.editor, Source.tipo)
Index('idx_source_url_domain', Source.url)  # Para búsquedas por dominio
Index('idx_source_anio', Source.anio)  # Para filtros por año
