"""
Servicio OCR para procesamiento de documentos e imágenes médicas.
Utiliza Tesseract con configuraciones optimizadas para contenido médico italiano.
"""

import asyncio
import hashlib
import logging
import os
import tempfile
import time
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID, uuid4

import cv2
import numpy as np
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from pdf2image import convert_from_bytes
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import ClassSession, OCRResult, MedicalTerminology
from app.services.base import BaseService, ServiceNotAvailableError, ServiceConfigurationError
from app.services.minio_service import MinioService

logger = logging.getLogger(__name__)


class ConfiguracionOCR:
    """Configuración para procesamiento OCR."""
    
    def __init__(
        self,
        engine: str = "tesseract",
        languages: str = "ita+eng",
        confidence_threshold: float = 0.7,
        dpi: int = 300,
        enhance_image: bool = True,
        medical_mode: bool = True,
        preserve_layout: bool = True
    ):
        self.engine = engine
        self.languages = languages
        self.confidence_threshold = confidence_threshold
        self.dpi = dpi
        self.enhance_image = enhance_image
        self.medical_mode = medical_mode
        self.preserve_layout = preserve_layout


class TipoContenidoDetectado:
    """Resultado de detección de tipo de contenido."""
    
    def __init__(
        self,
        tipo: str,
        confidence: float,
        caracteristicas: Dict[str, Any]
    ):
        self.tipo = tipo
        self.confidence = confidence
        self.caracteristicas = caracteristicas


class ResultadoOCR:
    """Resultado completo del procesamiento OCR."""
    
    def __init__(
        self,
        texto_extraido: str,
        confidence_promedio: float,
        datos_por_pagina: List[Dict[str, Any]],
        metadatos: Dict[str, Any],
        tiempo_procesamiento: float
    ):
        self.texto_extraido = texto_extraido
        self.confidence_promedio = confidence_promedio
        self.datos_por_pagina = datos_por_pagina
        self.metadatos = metadatos
        self.tiempo_procesamiento = tiempo_procesamiento


class OCRService(BaseService):
    """
    Servicio completo de OCR para contenido médico.
    
    Utiliza Tesseract optimizado para texto médico italiano,
    con pre-procesamiento avanzado de imágenes y post-procesamiento
    específico para terminología médica.
    """
    
    def __init__(self):
        super().__init__("ocr_service")
        self.settings = get_settings()
        self.minio_service: Optional[MinioService] = None
        self.medical_terms_cache: Dict[str, Any] = {}
        self.is_initialized = False
        
        # Configuraciones Tesseract para diferentes tipos de contenido
        self.tesseract_configs = {
            "medical_text": "--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789àáèéìíîòóùúüÀÁÈÉÌÍÎÒÓÙÚÜ.,;:()[]{}/-_ ",
            "medical_diagram": "--oem 3 --psm 6",
            "presentation_slide": "--oem 3 --psm 3",
            "mixed_content": "--oem 3 --psm 6",
            "document_scan": "--oem 3 --psm 1",
            "single_column": "--oem 3 --psm 4",
            "table_data": "--oem 3 --psm 6"
        }
        
        # Patrones para detección de tipo de contenido
        self.content_patterns = {
            "medical_diagram": [
                r"anatomia", r"fisiologia", r"patologia", r"sindrome",
                r"muscolo", r"osso", r"organo", r"sistema", r"apparato"
            ],
            "prescription": [
                r"farmaco", r"dose", r"mg", r"ml", r"compresse",
                r"ricetta", r"prescrizione", r"terapia"
            ],
            "medical_report": [
                r"paziente", r"diagnosi", r"sintomi", r"analisi",
                r"esame", r"risultati", r"clinico"
            ],
            "presentation": [
                r"lezione", r"corso", r"capitolo", r"slide",
                r"obiettivi", r"introduzione", r"conclusioni"
            ]
        }
    
    async def _setup(self) -> None:
        """Configurar servicio OCR."""
        try:
            # Verificar instalación de Tesseract
            await self._verify_tesseract_installation()
            
            # Configurar servicio MinIO
            self.minio_service = MinioService()
            await self.minio_service._setup()
            
            # Cargar cache de terminología médica
            await self._load_medical_terms_cache()
            
            self.is_initialized = True
            logger.info("OCRService inicializado correctamente")
            
        except Exception as e:
            raise ServiceConfigurationError(
                "OCR",
                f"Error configurando servicio OCR: {str(e)}"
            )
    
    async def _verify_tesseract_installation(self) -> None:
        """Verificar que Tesseract está instalado y configurado."""
        try:
            # Verificar comando tesseract
            tesseract_cmd = self.settings.TESSERACT_CMD or pytesseract.pytesseract.tesseract_cmd
            
            loop = asyncio.get_event_loop()
            version = await loop.run_in_executor(
                None, 
                lambda: pytesseract.get_tesseract_version()
            )
            
            logger.info(f"Tesseract versión detectada: {version}")
            
            # Verificar idiomas disponibles
            langs = await loop.run_in_executor(
                None,
                lambda: pytesseract.get_languages(config='')
            )
            
            required_langs = ["ita", "eng"]
            missing_langs = [lang for lang in required_langs if lang not in langs]
            
            if missing_langs:
                raise ServiceConfigurationError(
                    "OCR",
                    f"Idiomas Tesseract faltantes: {missing_langs}. Disponibles: {langs}"
                )
            
            logger.info(f"Idiomas Tesseract disponibles: {langs}")
            
        except Exception as e:
            raise ServiceConfigurationError(
                "OCR",
                f"Error verificando instalación Tesseract: {str(e)}"
            )
    
    async def _load_medical_terms_cache(self) -> None:
        """Cargar cache de terminología médica para validación."""
        try:
            # En el futuro, cargar desde base de datos
            # Por ahora, cache básico
            self.medical_terms_cache = {
                "anatomia_terms": [
                    "cuore", "polmone", "fegato", "rene", "stomaco",
                    "cervello", "muscolo", "osso", "nervo", "vaso"
                ],
                "pathology_terms": [
                    "infezione", "tumore", "cancro", "diabete", "ipertensione",
                    "asma", "polmonite", "influenza", "sindrome", "malattia"
                ],
                "procedure_terms": [
                    "intervento", "operazione", "chirurgia", "biopsia",
                    "endoscopia", "ecografia", "radiografia", "tac", "risonanza"
                ]
            }
            
            logger.info("Cache terminología médica cargado")
            
        except Exception as e:
            logger.warning(f"Error cargando cache terminología médica: {str(e)}")
            self.medical_terms_cache = {}
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar salud del servicio OCR."""
        try:
            # Verificar Tesseract
            tesseract_version = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: pytesseract.get_tesseract_version()
            )
            
            # Verificar MinIO
            minio_health = await self.minio_service.health_check() if self.minio_service else {"status": "not_configured"}
            
            return {
                "status": "healthy" if self.is_initialized else "initializing",
                "tesseract_version": str(tesseract_version),
                "minio_status": minio_health.get("status", "unknown"),
                "supported_formats": ["pdf", "png", "jpg", "jpeg", "tiff", "bmp"],
                "supported_languages": ["ita", "eng"],
                "medical_cache_loaded": len(self.medical_terms_cache) > 0,
                "configurations_available": list(self.tesseract_configs.keys())
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def process_document(
        self,
        file_key: str,
        class_session_id: UUID,
        config: Optional[ConfiguracionOCR] = None
    ) -> OCRResult:
        """
        Procesa un documento completo con OCR.
        
        Args:
            file_key: Clave del archivo en MinIO
            class_session_id: ID de la sesión de clase
            config: Configuración OCR opcional
            
        Returns:
            OCRResult con el texto extraído y metadatos
        """
        if not self.is_initialized:
            await self._setup()
        
        start_time = time.time()
        
        try:
            # 1. Obtener archivo desde MinIO
            logger.info(f"Obteniendo archivo {file_key} desde MinIO")
            file_data = await self._get_file_from_minio(file_key)
            
            # 2. Detectar tipo de contenido
            content_type = await self._detect_content_type(file_data, file_key)
            logger.info(f"Tipo de contenido detectado: {content_type.tipo}")
            
            # 3. Preparar configuración OCR
            config = config or ConfiguracionOCR()
            ocr_config = await self._prepare_ocr_config(content_type, config)
            
            # 4. Ejecutar OCR según tipo de archivo
            if file_key.lower().endswith('.pdf'):
                ocr_data = await self._process_pdf(file_data, ocr_config)
            elif any(file_key.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.tiff', '.bmp']):
                ocr_data = await self._process_image(file_data, ocr_config)
            else:
                raise ValueError(f"Formato de archivo no soportado: {file_key}")
            
            # 5. Post-procesamiento médico
            processed_data = await self._medical_postprocessing(ocr_data, content_type)
            
            # 6. Crear y guardar registro en BD
            ocr_result = await self._save_ocr_result(
                class_session_id=class_session_id,
                file_key=file_key,
                content_type=content_type,
                ocr_data=processed_data,
                config=config,
                processing_time=time.time() - start_time
            )
            
            logger.info(f"OCR completado para {file_key} en {time.time() - start_time:.2f}s")
            return ocr_result
            
        except Exception as e:
            logger.error(f"Error procesando OCR para {file_key}: {str(e)}")
            raise
    
    async def _get_file_from_minio(self, file_key: str) -> bytes:
        """Obtiene archivo desde MinIO."""
        try:
            file_data = await self.minio_service.get_file(file_key)
            return file_data
        except Exception as e:
            raise ServiceNotAvailableError(
                "MinIO",
                f"Error obteniendo archivo {file_key}: {str(e)}"
            )
    
    async def _detect_content_type(self, file_data: bytes, filename: str) -> TipoContenidoDetectado:
        """Detecta el tipo de contenido del documento."""
        
        # Análisis básico por extensión
        file_ext = filename.lower().split('.')[-1]
        
        if file_ext == 'pdf':
            # Para PDF, intentar extraer una muestra de texto
            try:
                # Convertir primera página para análisis
                images = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: convert_from_bytes(file_data, first_page=1, last_page=1, dpi=150)
                )
                
                if images:
                    sample_text = await self._extract_sample_text(images[0])
                    content_analysis = await self._analyze_text_content(sample_text)
                    
                    return TipoContenidoDetectado(
                        tipo=content_analysis["tipo"],
                        confidence=content_analysis["confidence"],
                        caracteristicas={
                            "file_type": "pdf",
                            "text_sample": sample_text[:200],
                            "detected_patterns": content_analysis["patterns"],
                            "language_detected": content_analysis.get("language", "ita")
                        }
                    )
            except Exception as e:
                logger.warning(f"Error analizando PDF: {str(e)}")
        
        # Para imágenes, análisis básico
        return TipoContenidoDetectado(
            tipo="imagen_generica",
            confidence=0.8,
            caracteristicas={
                "file_type": file_ext,
                "analysis": "basic_image_detection"
            }
        )
    
    async def _extract_sample_text(self, image: Image.Image) -> str:
        """Extrae muestra de texto de una imagen para análisis."""
        try:
            loop = asyncio.get_event_loop()
            
            # Redimensionar para análisis rápido
            sample_image = image.resize((800, 600), Image.Resampling.LANCZOS)
            
            # OCR básico para muestra
            sample_text = await loop.run_in_executor(
                None,
                lambda: pytesseract.image_to_string(
                    sample_image,
                    lang="ita+eng",
                    config="--psm 6"
                )
            )
            
            return sample_text.strip()
            
        except Exception as e:
            logger.warning(f"Error extrayendo muestra de texto: {str(e)}")
            return ""
    
    async def _analyze_text_content(self, text: str) -> Dict[str, Any]:
        """Analiza el contenido de texto para detectar tipo de documento."""
        text_lower = text.lower()
        
        # Analizar patrones por tipo
        type_scores = {}
        detected_patterns = {}
        
        for content_type, patterns in self.content_patterns.items():
            score = 0
            found_patterns = []
            
            for pattern in patterns:
                if pattern in text_lower:
                    score += 1
                    found_patterns.append(pattern)
            
            if patterns:
                normalized_score = score / len(patterns)
                type_scores[content_type] = normalized_score
                detected_patterns[content_type] = found_patterns
        
        # Determinar tipo más probable
        if type_scores:
            best_type = max(type_scores, key=type_scores.get)
            confidence = type_scores[best_type]
        else:
            best_type = "mixed_content"
            confidence = 0.5
        
        return {
            "tipo": best_type,
            "confidence": confidence,
            "patterns": detected_patterns,
            "text_length": len(text),
            "language": "ita" if any(word in text_lower for word in ["il", "la", "di", "che", "per"]) else "eng"
        }
    
    async def _prepare_ocr_config(
        self,
        content_type: TipoContenidoDetectado,
        user_config: ConfiguracionOCR
    ) -> Dict[str, Any]:
        """Prepara configuración OCR optimizada según tipo de contenido."""
        
        # Configuración base
        config = {
            "languages": user_config.languages,
            "confidence_threshold": user_config.confidence_threshold,
            "dpi": user_config.dpi,
            "enhance_image": user_config.enhance_image
        }
        
        # Configuración específica por tipo
        if content_type.tipo in self.tesseract_configs:
            config["tesseract_config"] = self.tesseract_configs[content_type.tipo]
        else:
            config["tesseract_config"] = self.tesseract_configs["mixed_content"]
        
        # Ajustes específicos para contenido médico
        if user_config.medical_mode:
            config["medical_preprocessing"] = True
            config["medical_correction"] = True
        
        return config
    
    async def _process_pdf(self, file_data: bytes, config: Dict[str, Any]) -> ResultadoOCR:
        """Procesa PDF con OCR."""
        try:
            start_time = time.time()
            
            # Convertir PDF a imágenes
            logger.info("Convirtiendo PDF a imágenes...")
            loop = asyncio.get_event_loop()
            
            images = await loop.run_in_executor(
                None,
                lambda: convert_from_bytes(
                    file_data,
                    dpi=config["dpi"],
                    thread_count=2
                )
            )
            
            logger.info(f"PDF convertido a {len(images)} imágenes")
            
            # Procesar cada página
            all_text = []
            all_confidence = []
            pages_data = []
            
            for page_num, image in enumerate(images):
                logger.info(f"Procesando página {page_num + 1}/{len(images)}")
                
                # Pre-procesamiento de imagen si está habilitado
                if config.get("enhance_image", True):
                    image = await self._enhance_image(image, config)
                
                # OCR de la página
                page_result = await self._ocr_image(image, config)
                
                pages_data.append({
                    "page": page_num + 1,
                    "text": page_result["text"],
                    "confidence": page_result["confidence"],
                    "word_boxes": page_result.get("word_boxes", []),
                    "processing_time": page_result.get("processing_time", 0)
                })
                
                all_text.append(page_result["text"])
                all_confidence.append(page_result["confidence"])
            
            # Combinar resultados
            full_text = "\n\n".join(filter(None, all_text))
            avg_confidence = sum(all_confidence) / len(all_confidence) if all_confidence else 0
            
            return ResultadoOCR(
                texto_extraido=full_text,
                confidence_promedio=avg_confidence,
                datos_por_pagina=pages_data,
                metadatos={
                    "total_pages": len(images),
                    "processing_config": config,
                    "file_type": "pdf"
                },
                tiempo_procesamiento=time.time() - start_time
            )
            
        except Exception as e:
            logger.error(f"Error procesando PDF: {str(e)}")
            raise
    
    async def _process_image(self, file_data: bytes, config: Dict[str, Any]) -> ResultadoOCR:
        """Procesa imagen individual con OCR."""
        try:
            start_time = time.time()
            
            # Cargar imagen
            image = Image.open(BytesIO(file_data))
            logger.info(f"Imagen cargada: {image.size}, modo: {image.mode}")
            
            # Pre-procesamiento si está habilitado
            if config.get("enhance_image", True):
                image = await self._enhance_image(image, config)
            
            # OCR de la imagen
            result = await self._ocr_image(image, config)
            
            return ResultadoOCR(
                texto_extraido=result["text"],
                confidence_promedio=result["confidence"],
                datos_por_pagina=[result],
                metadatos={
                    "total_pages": 1,
                    "processing_config": config,
                    "file_type": "image",
                    "image_size": image.size
                },
                tiempo_procesamiento=time.time() - start_time
            )
            
        except Exception as e:
            logger.error(f"Error procesando imagen: {str(e)}")
            raise
    
    async def _enhance_image(self, image: Image.Image, config: Dict[str, Any]) -> Image.Image:
        """Pre-procesamiento de imagen para mejorar OCR."""
        try:
            loop = asyncio.get_event_loop()
            
            def enhance_sync():
                # Convertir a RGB si es necesario
                if image.mode != 'RGB':
                    enhanced = image.convert('RGB')
                else:
                    enhanced = image.copy()
                
                # Mejorar contraste
                enhancer = ImageEnhance.Contrast(enhanced)
                enhanced = enhancer.enhance(1.2)
                
                # Mejorar nitidez
                enhancer = ImageEnhance.Sharpness(enhanced)
                enhanced = enhancer.enhance(1.1)
                
                # Filtro para reducir ruido
                enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))
                
                return enhanced
            
            enhanced_image = await loop.run_in_executor(None, enhance_sync)
            return enhanced_image
            
        except Exception as e:
            logger.warning(f"Error mejorando imagen: {str(e)}")
            return image
    
    async def _ocr_image(self, image: Image.Image, config: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta OCR en una imagen individual."""
        try:
            loop = asyncio.get_event_loop()
            
            # Configuración Tesseract
            tesseract_config = config.get("tesseract_config", "--oem 3 --psm 6")
            languages = config.get("languages", "ita+eng")
            
            def ocr_sync():
                # Extraer texto
                text = pytesseract.image_to_string(
                    image,
                    lang=languages,
                    config=tesseract_config
                )
                
                # Obtener datos detallados con confianza
                data = pytesseract.image_to_data(
                    image,
                    lang=languages,
                    config=tesseract_config,
                    output_type=pytesseract.Output.DICT
                )
                
                return text, data
            
            text, data = await loop.run_in_executor(None, ocr_sync)
            
            # Calcular confianza promedio
            confidences = [int(conf) for conf in data['conf'] if int(conf) > 0]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            # Extraer cajas de palabras
            word_boxes = []
            for i in range(len(data['text'])):
                if int(data['conf'][i]) > config.get("confidence_threshold", 0.7) * 100:
                    word_boxes.append({
                        "text": data['text'][i],
                        "confidence": int(data['conf'][i]),
                        "bbox": [
                            data['left'][i],
                            data['top'][i],
                            data['left'][i] + data['width'][i],
                            data['top'][i] + data['height'][i]
                        ]
                    })
            
            return {
                "text": text.strip(),
                "confidence": avg_confidence / 100.0,  # Normalizar a 0-1
                "word_boxes": word_boxes,
                "raw_data": data,
                "processing_time": 0  # Se calculará a nivel superior
            }
            
        except Exception as e:
            logger.error(f"Error ejecutando OCR: {str(e)}")
            raise
    
    async def _medical_postprocessing(
        self,
        ocr_result: ResultadoOCR,
        content_type: TipoContenidoDetectado
    ) -> Dict[str, Any]:
        """Post-procesamiento específico para contenido médico."""
        try:
            text = ocr_result.texto_extraido
            
            # 1. Corrección de términos médicos conocidos
            corrected_text = await self._correct_medical_terms(text)
            
            # 2. Detección de terminología médica
            medical_terms = await self._detect_medical_terminology(corrected_text)
            
            # 3. Análisis de calidad del texto
            quality_metrics = await self._calculate_text_quality(text, ocr_result.confidence_promedio)
            
            # 4. Detección de estructura del documento
            document_structure = await self._analyze_document_structure(corrected_text)
            
            return {
                "extracted_text": text,
                "corrected_text": corrected_text,
                "confidence_score": ocr_result.confidence_promedio,
                "quality_score": quality_metrics["overall_quality"],
                "medical_terms_detected": medical_terms,
                "content_type": content_type.tipo,
                "is_medical_content": len(medical_terms) > 0 or content_type.confidence > 0.7,
                "document_structure": document_structure,
                "pages_data": ocr_result.datos_por_pagina,
                "processing_time": ocr_result.tiempo_procesamiento,
                "requires_review": quality_metrics["overall_quality"] < 0.7,
                "metadata": ocr_result.metadatos
            }
            
        except Exception as e:
            logger.error(f"Error en post-procesamiento médico: {str(e)}")
            return {
                "extracted_text": ocr_result.texto_extraido,
                "corrected_text": ocr_result.texto_extraido,
                "confidence_score": ocr_result.confidence_promedio,
                "quality_score": ocr_result.confidence_promedio,
                "medical_terms_detected": [],
                "content_type": content_type.tipo,
                "is_medical_content": False,
                "requires_review": True,
                "error": str(e)
            }
    
    async def _correct_medical_terms(self, text: str) -> str:
        """Corrige términos médicos usando el cache de terminología."""
        corrected = text
        
        # Correcciones básicas comunes en OCR médico
        medical_corrections = {
            # Correcciones específicas para texto médico italiano
            "cuora": "cuore",
            "polmoni": "polmone",
            "muscoli": "muscolo",
            "ossa": "osso",
            "malattio": "malattia",
            "sindroma": "sindrome",
            "terapio": "terapia",
            "medicino": "medicina",
            # Correcciones comunes OCR
            "rn": "m",
            "cl": "d",
            "u'": "o",
            "i'": "l"
        }
        
        for wrong, correct in medical_corrections.items():
            corrected = corrected.replace(wrong, correct)
        
        return corrected
    
    async def _detect_medical_terminology(self, text: str) -> List[Dict[str, Any]]:
        """Detecta terminología médica en el texto."""
        medical_terms = []
        text_lower = text.lower()
        
        # Buscar términos en cache
        for category, terms in self.medical_terms_cache.items():
            for term in terms:
                if term.lower() in text_lower:
                    medical_terms.append({
                        "term": term,
                        "category": category,
                        "positions": [i for i in range(len(text_lower)) if text_lower.startswith(term.lower(), i)]
                    })
        
        return medical_terms
    
    async def _calculate_text_quality(self, text: str, confidence: float) -> Dict[str, Any]:
        """Calcula métricas de calidad del texto extraído."""
        
        # Métricas básicas
        char_count = len(text)
        word_count = len(text.split())
        
        # Ratio de caracteres válidos
        valid_chars = sum(1 for c in text if c.isalnum() or c.isspace() or c in ".,;:!?()-")
        valid_char_ratio = valid_chars / char_count if char_count > 0 else 0
        
        # Detectar palabras sin sentido (muchas consonantes consecutivas)
        nonsense_words = sum(1 for word in text.split() if len(word) > 3 and len([c for c in word if c.lower() in "bcdfghjklmnpqrstvwxyz"]) / len(word) > 0.8)
        nonsense_ratio = nonsense_words / word_count if word_count > 0 else 0
        
        # Calidad general
        quality_factors = [
            confidence,  # Confianza OCR
            valid_char_ratio,  # Ratio caracteres válidos
            1.0 - nonsense_ratio,  # Inverso del ratio palabras sin sentido
            min(1.0, char_count / 50)  # Factor longitud (mejor si hay más texto)
        ]
        
        overall_quality = sum(quality_factors) / len(quality_factors)
        
        return {
            "overall_quality": overall_quality,
            "character_count": char_count,
            "word_count": word_count,
            "valid_char_ratio": valid_char_ratio,
            "nonsense_ratio": nonsense_ratio,
            "ocr_confidence": confidence
        }
    
    async def _analyze_document_structure(self, text: str) -> Dict[str, Any]:
        """Analiza la estructura del documento."""
        lines = text.split('\n')
        
        # Detectar títulos (líneas cortas, posiblemente en mayúsculas)
        titles = [line.strip() for line in lines if line.strip() and len(line.strip()) < 100 and line.strip().isupper()]
        
        # Detectar párrafos
        paragraphs = [line.strip() for line in lines if line.strip() and len(line.strip()) > 50]
        
        # Detectar listas (líneas que empiezan con números o bullets)
        lists = [line.strip() for line in lines if line.strip() and (line.strip()[0].isdigit() or line.strip().startswith(('•', '-', '*')))]
        
        return {
            "total_lines": len(lines),
            "titles_detected": len(titles),
            "paragraphs_detected": len(paragraphs),
            "lists_detected": len(lists),
            "structure_type": "structured" if titles or lists else "plain_text"
        }
    
    async def _save_ocr_result(
        self,
        class_session_id: UUID,
        file_key: str,
        content_type: TipoContenidoDetectado,
        ocr_data: Dict[str, Any],
        config: ConfiguracionOCR,
        processing_time: float
    ) -> OCRResult:
        """Guarda el resultado OCR en la base de datos."""
        try:
            # Obtener información del archivo
            filename = file_key.split('/')[-1]
            file_size = len(ocr_data.get("metadata", {}).get("file_data", b""))
            
            # Crear registro OCR
            ocr_result = OCRResult(
                class_session_id=class_session_id,
                source_file_id=file_key,
                source_filename=filename,
                source_type=filename.split('.')[-1].lower(),
                file_size=file_size,
                mime_type=self._get_mime_type(filename),
                file_hash=hashlib.md5(file_key.encode()).hexdigest(),
                
                # Configuración OCR
                ocr_engine=config.engine,
                languages=config.languages,
                confidence_threshold=config.confidence_threshold,
                processing_dpi=config.dpi,
                
                # Resultados
                extracted_text=ocr_data["extracted_text"],
                corrected_text=ocr_data["corrected_text"],
                confidence_score=ocr_data["confidence_score"],
                quality_score=ocr_data["quality_score"],
                
                # Análisis
                detected_language="ita",  # Por defecto
                content_type=content_type.tipo,
                is_medical_content=ocr_data["is_medical_content"],
                medical_terms_detected=ocr_data["medical_terms_detected"],
                document_structure=ocr_data.get("document_structure", {}),
                
                # Control de calidad
                status="completed",
                requires_review=ocr_data["requires_review"],
                
                # Métricas
                processing_time=processing_time,
                pages_processed=len(ocr_data.get("pages_data", [])),
                words_extracted=len(ocr_data["extracted_text"].split()),
                characters_extracted=len(ocr_data["extracted_text"]),
                
                # Metadatos
                raw_ocr_data=ocr_data.get("pages_data", []),
                metadata=ocr_data.get("metadata", {})
            )
            
            # Guardar en BD (esto requeriría una sesión de BD)
            # Por ahora retornamos el objeto para ser guardado externamente
            
            return ocr_result
            
        except Exception as e:
            logger.error(f"Error guardando resultado OCR: {str(e)}")
            raise
    
    def _get_mime_type(self, filename: str) -> str:
        """Obtiene el tipo MIME basado en la extensión del archivo."""
        ext_to_mime = {
            'pdf': 'application/pdf',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'tiff': 'image/tiff',
            'bmp': 'image/bmp'
        }
        
        ext = filename.lower().split('.')[-1]
        return ext_to_mime.get(ext, 'application/octet-stream')


# Instancia global del servicio
ocr_service = OCRService()
