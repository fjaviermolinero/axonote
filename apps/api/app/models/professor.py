"""
Modelo Professor - Profesor/Docente.
Entidad opcional para gestión de profesores (según FEATURE_PROFESSOR_ENTITY).
"""

from typing import List
from sqlalchemy import Column, String, JSON, Index, Integer, Date
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Professor(BaseModel):
    """
    Profesor/Docente universitario.
    
    Entidad opcional que se crea automáticamente si FEATURE_PROFESSOR_ENTITY=true.
    Permite agrupar clases por profesor y gestionar alias/variaciones del nombre.
    """
    
    __tablename__ = "professors"
    
    # ==============================================
    # INFORMACIÓN BÁSICA
    # ==============================================
    
    nombre = Column(String(200), nullable=False, index=True)
    
    # Slug único para URLs amigables (ej: "dr-francesco-rossi")
    slug = Column(String(250), nullable=False, unique=True, index=True)
    
    # ==============================================
    # GESTIÓN DE ALIAS
    # ==============================================
    
    # JSON con variaciones del nombre para detección automática
    # Ejemplo: ["Dr. Francesco Rossi", "Prof. Rossi", "F. Rossi", "Francesco"]
    alias_json = Column(JSON, nullable=True)
    
    # ==============================================
    # INFORMACIÓN ADICIONAL (OPCIONAL)
    # ==============================================
    
    titulo = Column(String(100), nullable=True)      # Dr., Prof., Dott., etc.
    departamento = Column(String(200), nullable=True)
    email = Column(String(300), nullable=True)
    
    # ==============================================
    # METADATOS
    # ==============================================
    
    # Total de clases registradas
    total_clases = Column(Integer, nullable=False, default=0)
    
    # Última fecha de clase
    ultima_clase = Column(Date, nullable=True)
    
    # ==============================================
    # RELACIONES
    # ==============================================
    
    # Relación con las clases del profesor
    class_sessions = relationship(
        "ClassSession", 
        back_populates="profesor",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return (
            f"<Professor("
            f"id={self.id}, "
            f"nombre='{self.nombre}', "
            f"slug='{self.slug}', "
            f"total_clases={self.total_clases}"
            f")>"
        )
    
    @property
    def nombre_completo(self) -> str:
        """Nombre completo con título si existe."""
        if self.titulo:
            return f"{self.titulo} {self.nombre}"
        return self.nombre
    
    @property
    def alias_list(self) -> List[str]:
        """Lista de alias para detección."""
        if self.alias_json:
            return self.alias_json
        return [self.nombre]
    
    def add_alias(self, nuevo_alias: str) -> None:
        """Añadir un nuevo alias si no existe."""
        aliases = self.alias_list
        if nuevo_alias not in aliases:
            aliases.append(nuevo_alias)
            self.alias_json = aliases
    
    def matches_name(self, nombre_busqueda: str) -> bool:
        """
        Verificar si un nombre coincide con este profesor.
        Compara contra nombre principal y todos los alias.
        """
        nombre_lower = nombre_busqueda.lower().strip()
        
        # Comparar con nombre principal
        if nombre_lower == self.nombre.lower():
            return True
        
        # Comparar con alias
        for alias in self.alias_list:
            if nombre_lower == alias.lower():
                return True
        
        # Comparación fuzzy básica (contiene)
        for alias in self.alias_list:
            if nombre_lower in alias.lower() or alias.lower() in nombre_lower:
                return True
        
        return False
    
    @classmethod
    def generate_slug(cls, nombre: str) -> str:
        """
        Generar slug único a partir del nombre.
        Ejemplo: "Dr. Francesco Rossi" -> "dr-francesco-rossi"
        """
        import re
        import unicodedata
        
        # Normalizar unicode y convertir a ASCII
        slug = unicodedata.normalize('NFKD', nombre)
        slug = slug.encode('ascii', 'ignore').decode('ascii')
        
        # Convertir a minúsculas y remover caracteres especiales
        slug = re.sub(r'[^\w\s-]', '', slug.lower())
        
        # Reemplazar espacios y múltiples guiones con un solo guión
        slug = re.sub(r'[-\s]+', '-', slug)
        
        # Remover guiones del inicio y final
        slug = slug.strip('-')
        
        return slug


# Índices compuestos para optimizar consultas frecuentes
Index('idx_professor_nombre_slug', Professor.nombre, Professor.slug)
Index('idx_professor_slug_unique', Professor.slug, unique=True)
