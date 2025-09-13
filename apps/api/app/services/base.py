"""
Clases base para servicios de Axonote.

Define interfaces comunes y funcionalidad compartida
para todos los servicios del sistema.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class ServiceNotAvailableError(Exception):
    """Excepción lanzada cuando un servicio no está disponible."""
    pass


class ServiceConfigurationError(Exception):
    """Excepción lanzada cuando hay un error de configuración del servicio."""
    pass


class BaseService(ABC):
    """
    Clase base abstracta para todos los servicios de Axonote.
    
    Define la interfaz común y funcionalidad compartida
    que deben implementar todos los servicios.
    """
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.logger = logging.getLogger(f"{__name__}.{service_name}")
    
    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Verifica el estado de salud del servicio.
        
        Returns:
            Diccionario con información de estado
        """
        pass
    
    def log_operation(self, operation: str, **kwargs) -> None:
        """
        Registra una operación del servicio.
        
        Args:
            operation: Nombre de la operación
            **kwargs: Parámetros adicionales para el log
        """
        self.logger.info(f"{self.service_name}.{operation}", extra=kwargs)
    
    def log_error(self, operation: str, error: Exception, **kwargs) -> None:
        """
        Registra un error del servicio.
        
        Args:
            operation: Nombre de la operación que falló
            error: Excepción ocurrida
            **kwargs: Parámetros adicionales para el log
        """
        self.logger.error(
            f"{self.service_name}.{operation} failed: {str(error)}",
            extra=kwargs,
            exc_info=True
        )


class BaseSourceService(BaseService):
    """
    Clase base para servicios de fuentes médicas.
    
    Define la interfaz común que deben implementar todos
    los servicios de búsqueda en fuentes médicas externas.
    """
    
    def __init__(self, source_name: str):
        super().__init__(f"source_{source_name}")
        self.source_name = source_name
    
    @abstractmethod
    async def search_term(
        self,
        term: str,
        max_results: int = 10,
        language: str = "en",
        context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca un término médico en la fuente específica.
        
        Args:
            term: Término médico a buscar
            max_results: Número máximo de resultados
            language: Idioma preferido para los resultados
            context: Contexto opcional para refinar la búsqueda
            
        Returns:
            Lista de resultados encontrados
        """
        pass
    
    def normalize_term(self, term: str) -> str:
        """
        Normaliza un término médico para búsqueda.
        
        Args:
            term: Término original
            
        Returns:
            Término normalizado
        """
        # Normalización básica
        normalized = term.lower().strip()
        
        # Remover caracteres especiales comunes
        import re
        normalized = re.sub(r'[^\w\s-]', '', normalized)
        
        # Normalizar espacios
        normalized = re.sub(r'\s+', ' ', normalized)
        
        return normalized
    
    def calculate_base_relevance_score(
        self,
        content: str,
        search_term: str,
        title_weight: float = 0.4,
        content_weight: float = 0.6
    ) -> float:
        """
        Calcula un score base de relevancia para contenido.
        
        Args:
            content: Contenido a evaluar
            search_term: Término de búsqueda
            title_weight: Peso para coincidencias en título
            content_weight: Peso para coincidencias en contenido
            
        Returns:
            Score de relevancia (0-1)
        """
        if not content or not search_term:
            return 0.0
        
        content_lower = content.lower()
        term_lower = search_term.lower()
        
        # Contar ocurrencias
        term_count = content_lower.count(term_lower)
        
        # Calcular densidad (ocurrencias por cada 100 palabras)
        word_count = len(content.split())
        if word_count == 0:
            return 0.0
        
        density = (term_count / word_count) * 100
        
        # Normalizar densidad a score 0-1
        # Densidad óptima alrededor de 1-3%
        if density == 0:
            return 0.0
        elif density <= 1:
            return density
        elif density <= 3:
            return 1.0
        else:
            # Penalizar densidad excesiva (posible spam)
            return max(0.3, 1.0 - (density - 3) * 0.1)
    
    def extract_key_sentences(
        self,
        text: str,
        search_term: str,
        max_sentences: int = 3
    ) -> List[str]:
        """
        Extrae las oraciones más relevantes de un texto.
        
        Args:
            text: Texto completo
            search_term: Término de búsqueda
            max_sentences: Número máximo de oraciones
            
        Returns:
            Lista de oraciones relevantes
        """
        if not text or not search_term:
            return []
        
        import re
        
        # Dividir en oraciones
        sentences = re.split(r'[.!?]+', text)
        
        # Filtrar y puntuar oraciones
        scored_sentences = []
        term_lower = search_term.lower()
        
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20:  # Muy corta
                continue
            
            sentence_lower = sentence.lower()
            
            # Calcular score de la oración
            score = 0.0
            
            # Contiene el término exacto
            if term_lower in sentence_lower:
                score += 1.0
            
            # Contiene palabras del término
            term_words = term_lower.split()
            word_matches = sum(1 for word in term_words if word in sentence_lower)
            if term_words:
                score += (word_matches / len(term_words)) * 0.5
            
            # Longitud apropiada (ni muy corta ni muy larga)
            length = len(sentence)
            if 50 <= length <= 200:
                score += 0.2
            elif 200 < length <= 400:
                score += 0.1
            
            if score > 0:
                scored_sentences.append((sentence, score))
        
        # Ordenar por score y tomar las mejores
        scored_sentences.sort(key=lambda x: x[1], reverse=True)
        
        return [sentence for sentence, _ in scored_sentences[:max_sentences]]
    
    def build_source_result(
        self,
        title: str,
        url: str,
        content: str,
        search_term: str,
        **metadata
    ) -> Dict[str, Any]:
        """
        Construye un resultado estándar de fuente médica.
        
        Args:
            title: Título del documento
            url: URL de acceso
            content: Contenido principal
            search_term: Término de búsqueda
            **metadata: Metadatos adicionales
            
        Returns:
            Diccionario con resultado estructurado
        """
        # Calcular métricas básicas
        relevance_score = self.calculate_base_relevance_score(content, search_term)
        key_sentences = self.extract_key_sentences(content, search_term)
        
        # Extraer dominio de la URL
        from urllib.parse import urlparse
        try:
            domain = urlparse(url).netloc
        except:
            domain = "unknown"
        
        # Resultado base
        result = {
            'title': title,
            'url': url,
            'domain': domain,
            'content': content,
            'relevant_excerpt': ' '.join(key_sentences) if key_sentences else content[:300],
            'relevance_score': relevance_score,
            'search_term': search_term,
            'source_type': self.source_name,
            'extraction_method': 'api',
            'language': 'en',  # Por defecto, puede ser sobrescrito
            'access_type': 'free',  # Por defecto
            'peer_reviewed': False,  # Por defecto
            'official_source': False,  # Por defecto
        }
        
        # Añadir metadatos adicionales
        result.update(metadata)
        
        return result
    
    async def validate_url(self, url: str) -> bool:
        """
        Valida que una URL sea accesible.
        
        Args:
            url: URL a validar
            
        Returns:
            True si la URL es accesible
        """
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.head(url, timeout=5) as response:
                    return response.status < 400
        except:
            return False
    
    def get_source_authority_score(self) -> float:
        """
        Obtiene el score de autoridad base para esta fuente.
        
        Returns:
            Score de autoridad (0-1)
        """
        # Scores por defecto por tipo de fuente
        authority_scores = {
            'pubmed': 0.9,
            'who': 0.95,
            'nih': 0.9,
            'medlineplus': 0.7,
            'italian_official': 0.8,
            'mayo_clinic': 0.8,
            'cleveland_clinic': 0.75,
            'webmd': 0.6,
            'healthline': 0.6
        }
        
        return authority_scores.get(self.source_name, 0.5)


class BaseProcessingService(BaseService):
    """
    Clase base para servicios de procesamiento.
    
    Define funcionalidad común para servicios que procesan
    datos médicos (transcripciones, análisis, etc.).
    """
    
    def __init__(self, service_name: str):
        super().__init__(f"processing_{service_name}")
    
    def validate_input(self, data: Any, required_fields: List[str]) -> bool:
        """
        Valida que los datos de entrada tengan los campos requeridos.
        
        Args:
            data: Datos a validar
            required_fields: Lista de campos requeridos
            
        Returns:
            True si la validación es exitosa
        """
        if not isinstance(data, dict):
            return False
        
        return all(field in data and data[field] is not None for field in required_fields)
    
    def sanitize_medical_text(self, text: str) -> str:
        """
        Sanitiza texto médico removiendo información sensible.
        
        Args:
            text: Texto original
            
        Returns:
            Texto sanitizado
        """
        if not text:
            return ""
        
        import re
        
        # Remover patrones que podrían ser información personal
        # (implementación básica - en producción sería más sofisticada)
        
        # Remover números que podrían ser IDs o teléfonos
        text = re.sub(r'\b\d{6,}\b', '[ID]', text)
        
        # Remover emails
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)
        
        # Remover fechas específicas (mantener solo mes/año)
        text = re.sub(r'\b\d{1,2}/\d{1,2}/\d{4}\b', '[FECHA]', text)
        
        return text
    
    def calculate_processing_metrics(
        self,
        start_time: float,
        input_size: int,
        output_size: int
    ) -> Dict[str, Any]:
        """
        Calcula métricas de procesamiento.
        
        Args:
            start_time: Tiempo de inicio (timestamp)
            input_size: Tamaño de entrada
            output_size: Tamaño de salida
            
        Returns:
            Diccionario con métricas
        """
        import time
        
        end_time = time.time()
        duration = end_time - start_time
        
        return {
            'duration_seconds': duration,
            'input_size': input_size,
            'output_size': output_size,
            'processing_rate': input_size / duration if duration > 0 else 0,
            'compression_ratio': output_size / input_size if input_size > 0 else 1,
            'timestamp': end_time
        }