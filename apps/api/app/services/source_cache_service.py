"""
Servicio de gestión de cache para fuentes médicas.

Gestiona el cache inteligente de búsquedas médicas con
optimización automática, limpieza y estadísticas de uso.
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.models import SourceCache
from app.services.base import BaseService

logger = logging.getLogger(__name__)


class SourceCacheService(BaseService):
    """
    Servicio de gestión de cache para fuentes médicas.
    
    Proporciona funcionalidad completa de cache inteligente
    con gestión automática de expiración, limpieza y
    optimización basada en patrones de uso.
    """
    
    def __init__(self, db: Session):
        super().__init__("source_cache")
        self.db = db
        
        # Configuración de cache
        self.default_ttl_hours = 168  # 7 días
        self.max_cache_size_mb = 1024  # 1GB
        self.cleanup_interval_hours = 24
        
        logger.info("SourceCacheService inicializado")
    
    async def get_cached_result(
        self,
        term: str,
        config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene resultado cacheado para un término y configuración.
        
        Args:
            term: Término médico
            config: Configuración de búsqueda
            
        Returns:
            Resultado cacheado o None si no existe
        """
        try:
            # Generar clave de cache
            cache_key = self._generate_cache_key(term, config)
            
            # Buscar en cache
            cached = self.db.query(SourceCache).filter(
                SourceCache.cache_key == cache_key,
                SourceCache.is_valid == True,
                SourceCache.expires_at > datetime.utcnow()
            ).first()
            
            if cached:
                # Registrar acceso
                result = cached.access_cache()
                self.db.commit()
                
                logger.debug(f"Cache hit para término '{term}'")
                return result
            else:
                logger.debug(f"Cache miss para término '{term}'")
                return None
                
        except Exception as e:
            logger.error(f"Error obteniendo cache: {e}")
            return None
    
    async def save_to_cache(
        self,
        term: str,
        config: Dict[str, Any],
        results: Dict[str, Any],
        ttl_hours: Optional[int] = None
    ) -> bool:
        """
        Guarda resultados en el cache.
        
        Args:
            term: Término médico
            config: Configuración de búsqueda
            results: Resultados a cachear
            ttl_hours: TTL personalizado en horas
            
        Returns:
            True si se guardó exitosamente
        """
        try:
            # Generar clave de cache
            cache_key = self._generate_cache_key(term, config)
            
            # Verificar si ya existe
            existing = self.db.query(SourceCache).filter(
                SourceCache.cache_key == cache_key
            ).first()
            
            if existing:
                # Actualizar cache existente
                existing.cached_results = results
                existing.sources_count = len(results.get('sources', []))
                existing.last_accessed = func.now()
                existing.is_valid = True
                
                # Extender expiración si es necesario
                if ttl_hours:
                    existing.expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)
                
                cache_entry = existing
            else:
                # Crear nueva entrada de cache
                ttl = ttl_hours or self._calculate_ttl(config, results)
                
                cache_entry = SourceCache(
                    cache_key=cache_key,
                    medical_term=term,
                    normalized_term=term.lower().strip(),
                    search_config_hash=self._hash_config(config),
                    cached_results=results,
                    sources_count=len(results.get('sources', [])),
                    language=config.get('language', 'it'),
                    source_types=config.get('enabled_sources', []),
                    research_preset=config.get('preset', 'COMPREHENSIVE'),
                    search_configuration=config,
                    expires_at=datetime.utcnow() + timedelta(hours=ttl),
                    original_ttl_hours=ttl,
                    generation_time_ms=results.get('search_duration_ms', 0),
                    sources_consulted=results.get('sources_consulted', 0)
                )
                
                self.db.add(cache_entry)
            
            # Actualizar métricas de calidad
            if results.get('sources'):
                cache_entry.update_quality_metrics(results['sources'])
            
            # Comprimir si es beneficioso
            cache_entry.compress_content()
            
            self.db.commit()
            
            logger.debug(f"Resultado cacheado para término '{term}' con TTL de {cache_entry.original_ttl_hours}h")
            return True
            
        except Exception as e:
            logger.error(f"Error guardando en cache: {e}")
            self.db.rollback()
            return False
    
    async def invalidate_cache(
        self,
        term: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        reason: str = "manual_invalidation"
    ) -> int:
        """
        Invalida entradas de cache específicas o todas.
        
        Args:
            term: Término específico a invalidar (None = todos)
            config: Configuración específica (None = todas)
            reason: Razón de la invalidación
            
        Returns:
            Número de entradas invalidadas
        """
        try:
            query = self.db.query(SourceCache).filter(SourceCache.is_valid == True)
            
            if term:
                query = query.filter(SourceCache.medical_term == term)
            
            if config:
                config_hash = self._hash_config(config)
                query = query.filter(SourceCache.search_config_hash == config_hash)
            
            caches_to_invalidate = query.all()
            count = len(caches_to_invalidate)
            
            for cache in caches_to_invalidate:
                cache.invalidate(reason)
            
            self.db.commit()
            
            logger.info(f"Invalidadas {count} entradas de cache. Razón: {reason}")
            return count
            
        except Exception as e:
            logger.error(f"Error invalidando cache: {e}")
            self.db.rollback()
            return 0
    
    async def cleanup_expired_cache(self) -> Dict[str, int]:
        """
        Limpia cache expirado y optimiza almacenamiento.
        
        Returns:
            Estadísticas de limpieza
        """
        try:
            stats = {
                'expired_removed': 0,
                'invalid_removed': 0,
                'low_usage_removed': 0,
                'total_before': 0,
                'total_after': 0
            }
            
            # Contar total antes
            stats['total_before'] = self.db.query(SourceCache).count()
            
            # 1. Remover cache expirado
            expired_caches = self.db.query(SourceCache).filter(
                SourceCache.expires_at < datetime.utcnow()
            ).all()
            
            for cache in expired_caches:
                self.db.delete(cache)
            stats['expired_removed'] = len(expired_caches)
            
            # 2. Remover cache inválido
            invalid_caches = self.db.query(SourceCache).filter(
                SourceCache.is_valid == False
            ).all()
            
            for cache in invalid_caches:
                self.db.delete(cache)
            stats['invalid_removed'] = len(invalid_caches)
            
            # 3. Remover cache con poco uso (opcional)
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            low_usage_caches = self.db.query(SourceCache).filter(
                and_(
                    SourceCache.created_at < cutoff_date,
                    SourceCache.access_count < 2
                )
            ).all()
            
            for cache in low_usage_caches:
                self.db.delete(cache)
            stats['low_usage_removed'] = len(low_usage_caches)
            
            self.db.commit()
            
            # Contar total después
            stats['total_after'] = self.db.query(SourceCache).count()
            
            logger.info(f"Limpieza de cache completada: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error en limpieza de cache: {e}")
            self.db.rollback()
            return {}
    
    async def get_cache_statistics(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas completas del cache.
        
        Returns:
            Estadísticas detalladas del cache
        """
        try:
            # Estadísticas básicas
            total_entries = self.db.query(SourceCache).count()
            valid_entries = self.db.query(SourceCache).filter(
                SourceCache.is_valid == True
            ).count()
            expired_entries = self.db.query(SourceCache).filter(
                SourceCache.expires_at < datetime.utcnow()
            ).count()
            
            # Estadísticas de uso
            total_hits = self.db.query(func.sum(SourceCache.access_count)).scalar() or 0
            avg_access_count = self.db.query(func.avg(SourceCache.access_count)).scalar() or 0
            
            # Estadísticas de calidad
            avg_quality = self.db.query(func.avg(SourceCache.cache_quality_score)).scalar() or 0
            avg_relevance = self.db.query(func.avg(SourceCache.average_relevance)).scalar() or 0
            
            # Estadísticas por preset
            preset_stats = self.db.query(
                SourceCache.research_preset,
                func.count(SourceCache.id).label('count')
            ).group_by(SourceCache.research_preset).all()
            
            # Estadísticas por idioma
            language_stats = self.db.query(
                SourceCache.language,
                func.count(SourceCache.id).label('count')
            ).group_by(SourceCache.language).all()
            
            # Cache más populares
            popular_terms = self.db.query(
                SourceCache.medical_term,
                func.sum(SourceCache.access_count).label('total_hits')
            ).group_by(SourceCache.medical_term).order_by(
                func.sum(SourceCache.access_count).desc()
            ).limit(10).all()
            
            return {
                'overview': {
                    'total_entries': total_entries,
                    'valid_entries': valid_entries,
                    'expired_entries': expired_entries,
                    'cache_hit_rate': valid_entries / max(1, total_entries),
                    'total_cache_hits': total_hits,
                    'average_access_count': avg_access_count
                },
                'quality': {
                    'average_quality_score': avg_quality,
                    'average_relevance_score': avg_relevance
                },
                'distribution': {
                    'by_preset': {preset: count for preset, count in preset_stats},
                    'by_language': {lang: count for lang, count in language_stats}
                },
                'popular_terms': [
                    {'term': term, 'hits': hits} 
                    for term, hits in popular_terms
                ],
                'last_updated': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas de cache: {e}")
            return {}
    
    async def optimize_cache(self) -> Dict[str, Any]:
        """
        Optimiza el cache basado en patrones de uso.
        
        Returns:
            Resultados de optimización
        """
        try:
            optimization_results = {
                'compressed_entries': 0,
                'extended_ttl': 0,
                'reduced_ttl': 0,
                'revalidated_entries': 0
            }
            
            # 1. Comprimir entradas grandes sin comprimir
            large_uncompressed = self.db.query(SourceCache).filter(
                and_(
                    SourceCache.is_compressed == False,
                    SourceCache.cache_size_bytes > 1024  # > 1KB
                )
            ).all()
            
            for cache in large_uncompressed:
                if cache.compress_content():
                    optimization_results['compressed_entries'] += 1
            
            # 2. Extender TTL para cache muy usado
            popular_cache = self.db.query(SourceCache).filter(
                and_(
                    SourceCache.access_count > 10,
                    SourceCache.expires_at > datetime.utcnow(),
                    SourceCache.expires_at < datetime.utcnow() + timedelta(days=1)
                )
            ).all()
            
            for cache in popular_cache:
                cache.extend_expiration(72)  # Extender 3 días
                optimization_results['extended_ttl'] += 1
            
            # 3. Reducir TTL para cache poco usado
            unpopular_cache = self.db.query(SourceCache).filter(
                and_(
                    SourceCache.access_count < 2,
                    SourceCache.created_at < datetime.utcnow() - timedelta(days=7),
                    SourceCache.expires_at > datetime.utcnow() + timedelta(days=3)
                )
            ).all()
            
            for cache in unpopular_cache:
                new_expiry = datetime.utcnow() + timedelta(days=1)
                if new_expiry < cache.expires_at:
                    cache.expires_at = new_expiry
                    optimization_results['reduced_ttl'] += 1
            
            self.db.commit()
            
            logger.info(f"Optimización de cache completada: {optimization_results}")
            return optimization_results
            
        except Exception as e:
            logger.error(f"Error optimizando cache: {e}")
            self.db.rollback()
            return {}
    
    def _generate_cache_key(self, term: str, config: Dict[str, Any]) -> str:
        """Genera clave de cache única."""
        normalized_term = term.lower().strip()
        config_str = self._serialize_config(config)
        combined = f"{normalized_term}|{config_str}"
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()
    
    def _serialize_config(self, config: Dict[str, Any]) -> str:
        """Serializa configuración de forma determinística."""
        # Extraer campos relevantes para cache
        relevant_fields = [
            'preset', 'language', 'max_sources_per_term',
            'enabled_sources', 'include_related_terms'
        ]
        
        config_items = []
        for field in relevant_fields:
            if field in config:
                value = config[field]
                if isinstance(value, list):
                    value = sorted(value)  # Orden consistente
                config_items.append(f"{field}:{value}")
        
        return "|".join(config_items)
    
    def _hash_config(self, config: Dict[str, Any]) -> str:
        """Genera hash de configuración."""
        config_str = self._serialize_config(config)
        return hashlib.md5(config_str.encode('utf-8')).hexdigest()
    
    def _calculate_ttl(self, config: Dict[str, Any], results: Dict[str, Any]) -> int:
        """Calcula TTL apropiado basado en configuración y resultados."""
        base_ttl = self.default_ttl_hours
        
        # Ajustar según tipos de fuentes
        source_types = config.get('enabled_sources', [])
        if 'pubmed' in source_types:
            base_ttl = max(base_ttl, 720)  # 30 días para académico
        
        if any(source in source_types for source in ['who', 'nih']):
            base_ttl = max(base_ttl, 336)  # 14 días para oficiales
        
        # Ajustar según calidad de resultados
        sources = results.get('sources', [])
        if sources:
            avg_quality = sum(s.get('overall_score', 0.5) for s in sources) / len(sources)
            if avg_quality > 0.8:
                base_ttl = int(base_ttl * 1.5)  # Extender para alta calidad
            elif avg_quality < 0.5:
                base_ttl = int(base_ttl * 0.5)  # Reducir para baja calidad
        
        return min(base_ttl, 2160)  # Máximo 90 días
    
    async def health_check(self) -> Dict[str, Any]:
        """Verifica el estado del servicio de cache."""
        try:
            # Verificar conectividad a BD
            cache_count = self.db.query(SourceCache).count()
            
            # Verificar cache reciente
            recent_cache = self.db.query(SourceCache).filter(
                SourceCache.created_at > datetime.utcnow() - timedelta(hours=24)
            ).count()
            
            # Calcular estadísticas básicas
            valid_cache = self.db.query(SourceCache).filter(
                SourceCache.is_valid == True
            ).count()
            
            hit_rate = valid_cache / max(1, cache_count)
            
            return {
                'service': 'source_cache',
                'status': 'healthy',
                'cache_entries': cache_count,
                'valid_entries': valid_cache,
                'recent_entries_24h': recent_cache,
                'cache_hit_rate': hit_rate,
                'health_score': min(1.0, hit_rate + 0.2),
                'last_check': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'service': 'source_cache',
                'status': 'unhealthy',
                'error': str(e),
                'last_check': datetime.utcnow().isoformat()
            }
