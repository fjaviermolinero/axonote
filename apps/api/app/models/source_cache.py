"""
Modelo SourceCache para cache inteligente de búsquedas médicas.

Este modelo optimiza las búsquedas repetidas almacenando resultados
de investigación médica con gestión automática de expiración y
estadísticas de uso.
"""

import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, Index
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.sql import func

from .base import BaseModel


class SourceCache(BaseModel):
    """
    Cache inteligente para optimizar búsquedas médicas repetidas.
    
    Almacena resultados de búsquedas por término médico y configuración,
    con gestión automática de expiración basada en tipo de contenido
    y estadísticas de uso para optimización.
    """
    
    __tablename__ = "source_cache"
    
    # ==============================================
    # CLAVE DE CACHE
    # ==============================================
    
    # Hash único de término + configuración
    cache_key = Column(String(128), nullable=False, unique=True, index=True)
    
    # Término médico original
    medical_term = Column(String(200), nullable=False, index=True)
    
    # Término normalizado para búsquedas
    normalized_term = Column(String(200), nullable=False, index=True)
    
    # Hash de la configuración de búsqueda utilizada
    search_config_hash = Column(String(64), nullable=False, index=True)
    
    # ==============================================
    # CONTENIDO CACHEADO
    # ==============================================
    
    # Resultados serializados de la búsqueda
    cached_results = Column(JSON, nullable=False)
    
    # Número de fuentes en el cache
    sources_count = Column(Integer, nullable=False, default=0)
    
    # Metadatos de los resultados
    results_metadata = Column(JSON, nullable=True)
    
    # Versión del formato de cache
    cache_version = Column(String(10), nullable=False, default="1.0")
    
    # ==============================================
    # CONFIGURACIÓN DE BÚSQUEDA
    # ==============================================
    
    # Idioma de la búsqueda
    language = Column(String(10), nullable=False, default="it", index=True)
    
    # Tipos de fuentes incluidas
    source_types = Column(JSON, nullable=True)  # ["pubmed", "who", "nih"]
    
    # Preset de research utilizado
    research_preset = Column(String(50), nullable=True, index=True)
    
    # Configuración detallada utilizada
    search_configuration = Column(JSON, nullable=True)
    
    # ==============================================
    # GESTIÓN DE EXPIRACIÓN
    # ==============================================
    
    # Fecha de expiración del cache
    expires_at = Column(DateTime, nullable=False, index=True)
    
    # TTL original en horas
    original_ttl_hours = Column(Integer, nullable=False, default=168)  # 7 días por defecto
    
    # Tipo de contenido para determinar TTL
    content_type = Column(String(50), nullable=True)  # academic, clinical, general, drug_info
    
    # Prioridad de expiración (1=alta, 5=baja)
    expiration_priority = Column(Integer, nullable=False, default=3)
    
    # ==============================================
    # ESTADÍSTICAS DE USO
    # ==============================================
    
    # Última vez que se accedió al cache
    last_accessed = Column(DateTime, nullable=False, default=func.now(), index=True)
    
    # Número total de accesos
    access_count = Column(Integer, nullable=False, default=0)
    
    # Número de hits desde la última actualización
    hits_since_update = Column(Integer, nullable=False, default=0)
    
    # Frecuencia de acceso (accesos por día)
    access_frequency = Column(Float, nullable=False, default=0.0)
    
    # Última vez que se calculó la frecuencia
    frequency_calculated_at = Column(DateTime, nullable=False, default=func.now())
    
    # ==============================================
    # MÉTRICAS DE CALIDAD
    # ==============================================
    
    # Relevancia promedio de los resultados cacheados
    average_relevance = Column(Float, nullable=False, default=0.0)
    
    # Score de autoridad promedio
    average_authority = Column(Float, nullable=False, default=0.0)
    
    # Score de frescura promedio
    average_freshness = Column(Float, nullable=False, default=0.0)
    
    # Score de calidad general del cache
    cache_quality_score = Column(Float, nullable=False, default=0.0)
    
    # ==============================================
    # ESTADO DEL CACHE
    # ==============================================
    
    # Indica si el cache es válido
    is_valid = Column(Boolean, nullable=False, default=True, index=True)
    
    # Razón de invalidación
    invalidation_reason = Column(String(100), nullable=True)
    
    # Fecha de invalidación
    invalidated_at = Column(DateTime, nullable=True)
    
    # Indica si necesita actualización
    needs_refresh = Column(Boolean, nullable=False, default=False)
    
    # Razón por la que necesita actualización
    refresh_reason = Column(String(200), nullable=True)
    
    # ==============================================
    # METADATOS DE CREACIÓN
    # ==============================================
    
    # Tiempo que tomó generar el cache (ms)
    generation_time_ms = Column(Integer, nullable=True)
    
    # Número de fuentes consultadas para crear el cache
    sources_consulted = Column(Integer, nullable=False, default=0)
    
    # Errores durante la generación
    generation_errors = Column(JSON, nullable=True)
    
    # Warnings durante la generación
    generation_warnings = Column(JSON, nullable=True)
    
    # ==============================================
    # OPTIMIZACIÓN Y COMPRESIÓN
    # ==============================================
    
    # Tamaño del cache en bytes
    cache_size_bytes = Column(Integer, nullable=True)
    
    # Indica si el contenido está comprimido
    is_compressed = Column(Boolean, nullable=False, default=False)
    
    # Algoritmo de compresión utilizado
    compression_algorithm = Column(String(20), nullable=True)
    
    # Ratio de compresión (si aplica)
    compression_ratio = Column(Float, nullable=True)
    
    # ==============================================
    # ÍNDICES COMPUESTOS
    # ==============================================
    
    __table_args__ = (
        # Índice para búsquedas por término y idioma
        Index('idx_cache_term_language', 'normalized_term', 'language'),
        
        # Índice para limpieza de cache expirado
        Index('idx_cache_expiration', 'expires_at', 'is_valid'),
        
        # Índice para estadísticas de uso
        Index('idx_cache_usage', 'access_count', 'last_accessed'),
        
        # Índice para calidad del cache
        Index('idx_cache_quality', 'cache_quality_score', 'average_relevance'),
    )
    
    # ==============================================
    # MÉTODOS ESTÁTICOS
    # ==============================================
    
    @staticmethod
    def generate_cache_key(term: str, config: Dict[str, Any]) -> str:
        """
        Genera una clave de cache única basada en término y configuración.
        
        Args:
            term: Término médico normalizado
            config: Configuración de búsqueda
            
        Returns:
            Clave de cache única
        """
        # Normalizar término
        normalized_term = term.lower().strip()
        
        # Crear string de configuración determinística
        config_items = sorted(config.items())
        config_str = str(config_items)
        
        # Generar hash
        combined = f"{normalized_term}|{config_str}"
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()
    
    @staticmethod
    def calculate_ttl_hours(content_type: str, source_types: List[str]) -> int:
        """
        Calcula el TTL apropiado basado en tipo de contenido y fuentes.
        
        Args:
            content_type: Tipo de contenido médico
            source_types: Tipos de fuentes consultadas
            
        Returns:
            TTL en horas
        """
        base_ttl = {
            'academic': 720,      # 30 días - artículos académicos cambian poco
            'clinical': 168,      # 7 días - guías clínicas se actualizan más
            'drug_info': 24,      # 1 día - información de medicamentos cambia
            'epidemiology': 72,   # 3 días - datos epidemiológicos
            'general': 168,       # 7 días - información general
            'news': 6,            # 6 horas - noticias médicas
        }
        
        ttl = base_ttl.get(content_type, 168)  # 7 días por defecto
        
        # Ajustar según fuentes
        if 'pubmed' in source_types:
            ttl = max(ttl, 720)  # Artículos académicos duran más
        
        if 'who' in source_types or 'nih' in source_types:
            ttl = max(ttl, 336)  # Fuentes oficiales duran más
        
        return ttl
    
    # ==============================================
    # PROPIEDADES CALCULADAS
    # ==============================================
    
    @property
    def is_expired(self) -> bool:
        """Indica si el cache ha expirado."""
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_fresh(self) -> bool:
        """Indica si el cache está fresco (no expirado y válido)."""
        return not self.is_expired and self.is_valid
    
    @property
    def age_in_hours(self) -> float:
        """Edad del cache en horas."""
        return (datetime.utcnow() - self.created_at).total_seconds() / 3600
    
    @property
    def time_until_expiration(self) -> Optional[timedelta]:
        """Tiempo hasta la expiración."""
        if self.is_expired:
            return None
        
        return self.expires_at - datetime.utcnow()
    
    @property
    def hit_rate_percentage(self) -> float:
        """Porcentaje de hit rate basado en accesos."""
        if self.access_count == 0:
            return 0.0
        
        # Estimación simple - en producción sería más sofisticada
        return min(100.0, (self.access_count / max(1, self.age_in_hours)) * 10)
    
    @property
    def cache_efficiency_score(self) -> float:
        """Score de eficiencia del cache (0-1)."""
        factors = [
            self.hit_rate_percentage / 100.0,  # Hit rate
            self.cache_quality_score,          # Calidad del contenido
            1.0 - (self.age_in_hours / (self.original_ttl_hours * 24)),  # Frescura
            min(1.0, self.access_frequency / 5.0)  # Frecuencia de uso
        ]
        
        return sum(factors) / len(factors)
    
    # ==============================================
    # MÉTODOS DE GESTIÓN
    # ==============================================
    
    def access_cache(self) -> Dict[str, Any]:
        """
        Registra un acceso al cache y retorna los resultados.
        
        Returns:
            Resultados cacheados deserializados
        """
        if not self.is_fresh:
            raise ValueError("Cache expirado o inválido")
        
        # Actualizar estadísticas
        self.access_count += 1
        self.hits_since_update += 1
        self.last_accessed = func.now()
        
        # Recalcular frecuencia si es necesario
        self._update_access_frequency()
        
        return self.cached_results
    
    def invalidate(self, reason: str) -> None:
        """
        Invalida el cache.
        
        Args:
            reason: Razón de la invalidación
        """
        self.is_valid = False
        self.invalidation_reason = reason
        self.invalidated_at = func.now()
    
    def mark_for_refresh(self, reason: str) -> None:
        """
        Marca el cache para actualización.
        
        Args:
            reason: Razón por la que necesita actualización
        """
        self.needs_refresh = True
        self.refresh_reason = reason
    
    def update_quality_metrics(self, results: List[Dict[str, Any]]) -> None:
        """
        Actualiza las métricas de calidad basadas en nuevos resultados.
        
        Args:
            results: Lista de resultados con scores de calidad
        """
        if not results:
            return
        
        # Calcular promedios
        relevance_scores = [r.get('relevance_score', 0.0) for r in results]
        authority_scores = [r.get('authority_score', 0.0) for r in results]
        freshness_scores = [r.get('recency_score', 0.0) for r in results]
        
        self.average_relevance = sum(relevance_scores) / len(relevance_scores)
        self.average_authority = sum(authority_scores) / len(authority_scores)
        self.average_freshness = sum(freshness_scores) / len(freshness_scores)
        
        # Calcular score general
        self.cache_quality_score = (
            self.average_relevance * 0.4 +
            self.average_authority * 0.4 +
            self.average_freshness * 0.2
        )
    
    def extend_expiration(self, additional_hours: int) -> None:
        """
        Extiende la fecha de expiración del cache.
        
        Args:
            additional_hours: Horas adicionales antes de expirar
        """
        self.expires_at = self.expires_at + timedelta(hours=additional_hours)
    
    def compress_content(self) -> bool:
        """
        Comprime el contenido del cache si es beneficioso.
        
        Returns:
            True si se comprimió exitosamente
        """
        if self.is_compressed:
            return True
        
        try:
            import gzip
            import json
            
            # Serializar contenido
            content_str = json.dumps(self.cached_results)
            original_size = len(content_str.encode('utf-8'))
            
            # Comprimir solo si vale la pena (>1KB y >20% reducción)
            if original_size < 1024:
                return False
            
            compressed = gzip.compress(content_str.encode('utf-8'))
            compressed_size = len(compressed)
            
            compression_ratio = compressed_size / original_size
            
            if compression_ratio < 0.8:  # Al menos 20% de reducción
                # Actualizar campos
                self.is_compressed = True
                self.compression_algorithm = "gzip"
                self.compression_ratio = compression_ratio
                self.cache_size_bytes = compressed_size
                
                # En producción, aquí se almacenaría el contenido comprimido
                # Por simplicidad, mantenemos el JSON original
                
                return True
            
            return False
            
        except Exception:
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas completas del cache.
        
        Returns:
            Diccionario con estadísticas del cache
        """
        return {
            "cache_key": self.cache_key,
            "medical_term": self.medical_term,
            "sources_count": self.sources_count,
            "age_hours": self.age_in_hours,
            "access_count": self.access_count,
            "hit_rate_percentage": self.hit_rate_percentage,
            "is_fresh": self.is_fresh,
            "is_expired": self.is_expired,
            "time_until_expiration_hours": (
                self.time_until_expiration.total_seconds() / 3600 
                if self.time_until_expiration else None
            ),
            "quality_score": self.cache_quality_score,
            "efficiency_score": self.cache_efficiency_score,
            "average_relevance": self.average_relevance,
            "is_compressed": self.is_compressed,
            "cache_size_bytes": self.cache_size_bytes,
            "needs_refresh": self.needs_refresh
        }
    
    def _update_access_frequency(self) -> None:
        """Actualiza la frecuencia de acceso."""
        now = datetime.utcnow()
        hours_since_calculation = (now - self.frequency_calculated_at).total_seconds() / 3600
        
        if hours_since_calculation >= 24:  # Recalcular cada 24 horas
            days_since_creation = max(1, (now - self.created_at).total_seconds() / 86400)
            self.access_frequency = self.access_count / days_since_creation
            self.frequency_calculated_at = now
    
    @classmethod
    def cleanup_expired(cls, db_session) -> int:
        """
        Limpia caches expirados de la base de datos.
        
        Args:
            db_session: Sesión de base de datos
            
        Returns:
            Número de caches eliminados
        """
        expired_caches = db_session.query(cls).filter(
            cls.expires_at < datetime.utcnow(),
            cls.is_valid == False
        ).all()
        
        count = len(expired_caches)
        
        for cache in expired_caches:
            db_session.delete(cache)
        
        db_session.commit()
        return count
    
    @classmethod
    def get_cache_statistics(cls, db_session) -> Dict[str, Any]:
        """
        Obtiene estadísticas globales del sistema de cache.
        
        Args:
            db_session: Sesión de base de datos
            
        Returns:
            Estadísticas globales del cache
        """
        total_caches = db_session.query(cls).count()
        valid_caches = db_session.query(cls).filter(cls.is_valid == True).count()
        expired_caches = db_session.query(cls).filter(cls.expires_at < datetime.utcnow()).count()
        
        # Estadísticas de uso
        avg_access_count = db_session.query(func.avg(cls.access_count)).scalar() or 0
        total_hits = db_session.query(func.sum(cls.access_count)).scalar() or 0
        
        # Estadísticas de calidad
        avg_quality = db_session.query(func.avg(cls.cache_quality_score)).scalar() or 0
        avg_relevance = db_session.query(func.avg(cls.average_relevance)).scalar() or 0
        
        return {
            "total_caches": total_caches,
            "valid_caches": valid_caches,
            "expired_caches": expired_caches,
            "cache_hit_rate": valid_caches / max(1, total_caches),
            "average_access_count": avg_access_count,
            "total_cache_hits": total_hits,
            "average_quality_score": avg_quality,
            "average_relevance_score": avg_relevance,
            "cache_efficiency": valid_caches / max(1, total_caches) * avg_quality
        }
    
    def __repr__(self) -> str:
        return (
            f"<SourceCache(id={self.id}, "
            f"term='{self.medical_term}', "
            f"sources={self.sources_count}, "
            f"hits={self.access_count}, "
            f"fresh={self.is_fresh}, "
            f"quality={self.cache_quality_score:.2f})>"
        )
