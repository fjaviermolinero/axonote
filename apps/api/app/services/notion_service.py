"""
Servicio Notion completo para sincronización e integración.
Fase 8: Implementación completa con templates, sync bidireccional y attachments.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID

import aiofiles
import httpx
from notion_client import Client, APIErrorCode, APIResponseError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_

from app.core import settings
from app.core.database import get_db
from app.models import (
    ClassSession, NotionSyncRecord, NotionWorkspace, NotionTemplate,
    NotionTemplateInstance, ResearchResult, LLMAnalysisResult,
    OCRResult, MicroMemo, MicroMemoCollection
)
from app.services.base import BaseService, ServiceNotAvailableError, ServiceConfigurationError
from app.services.minio_service import minio_service
from app.services.rate_limiter import RateLimiter


class NotionTemplateManager:
    """Gestor de templates para diferentes tipos de contenido."""
    
    def __init__(self, db: Session):
        self.db = db
        self._template_cache = {}
    
    async def get_template_for_content(self, content_data: Dict[str, Any]) -> Optional[NotionTemplate]:
        """Detectar automáticamente el template más apropiado."""
        
        # Si hay preferencia explícita, usarla
        if "template_preference" in content_data:
            return await self._get_template_by_name(content_data["template_preference"])
        
        # Auto-detección basada en contenido
        if not settings.NOTION_AUTO_DETECT_TEMPLATE:
            return await self._get_default_template()
        
        # Obtener todos los templates activos
        templates = await self._get_active_templates()
        
        best_template = None
        best_score = 0.0
        
        for template in templates:
            score = template.calculate_match_score(content_data)
            if score > best_score and score > 0.5:  # Umbral mínimo
                best_score = score
                best_template = template
        
        return best_template or await self._get_default_template()
    
    async def _get_template_by_name(self, template_name: str) -> Optional[NotionTemplate]:
        """Obtener template por nombre."""
        if template_name in self._template_cache:
            return self._template_cache[template_name]
        
        result = await self.db.execute(
            select(NotionTemplate).where(
                and_(
                    NotionTemplate.template_name == template_name,
                    NotionTemplate.is_active == True
                )
            )
        )
        template = result.scalar_one_or_none()
        
        if template:
            self._template_cache[template_name] = template
        
        return template
    
    async def _get_default_template(self) -> Optional[NotionTemplate]:
        """Obtener template por defecto."""
        return await self._get_template_by_name(settings.NOTION_DEFAULT_TEMPLATE)
    
    async def _get_active_templates(self) -> List[NotionTemplate]:
        """Obtener todos los templates activos."""
        result = await self.db.execute(
            select(NotionTemplate).where(NotionTemplate.is_active == True)
        )
        return result.scalars().all()


class NotionContentBuilder:
    """Constructor de contenido para páginas Notion."""
    
    def __init__(self, template: NotionTemplate):
        self.template = template
        self.content_mapping = template.content_mapping
        self.style_config = template.style_config
    
    def build_page_structure(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Construir estructura completa de página."""
        
        # Generar título
        title = self._generate_title(data)
        
        # Generar propiedades
        properties = self._generate_properties(data)
        
        # Generar bloques de contenido
        blocks = self._generate_blocks(data)
        
        return {
            "title": title,
            "properties": properties,
            "children": blocks
        }
    
    def _generate_title(self, data: Dict[str, Any]) -> str:
        """Generar título de la página."""
        template_config = self.template.template_config
        title_template = template_config.get("title_template", "{subject} - {topic}")
        
        # Extraer datos para el título
        subject = data.get("subject", "Clase")
        topic = data.get("topic", data.get("class_name", "Sin título"))
        professor = data.get("professor_name", "")
        date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
        
        # Aplicar template de título
        title = title_template.format(
            subject=subject,
            topic=topic,
            professor=professor,
            date=date
        )
        
        # Agregar emoji del template
        emoji = self.style_config.get("icons", {}).get("page_icon", "🎓")
        
        return f"{emoji} {title}"
    
    def _generate_properties(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generar propiedades de la página."""
        template_properties = self.template.template_config.get("page_properties", {})
        properties = {}
        
        for prop_name, prop_config in template_properties.items():
            prop_type = prop_config.get("type")
            
            if prop_type == "title":
                properties[prop_name] = {
                    "title": [{
                        "text": {
                            "content": self._get_property_value(prop_name, data, prop_config)
                        }
                    }]
                }
            elif prop_type == "select":
                value = self._get_property_value(prop_name, data, prop_config)
                if value:
                    properties[prop_name] = {
                        "select": {"name": str(value)}
                    }
            elif prop_type == "multi_select":
                values = self._get_property_value(prop_name, data, prop_config)
                if values and isinstance(values, list):
                    properties[prop_name] = {
                        "multi_select": [{"name": str(v)} for v in values]
                    }
            elif prop_type == "date":
                date_value = self._get_property_value(prop_name, data, prop_config)
                if date_value:
                    if isinstance(date_value, datetime):
                        date_str = date_value.isoformat()
                    else:
                        date_str = str(date_value)
                    properties[prop_name] = {
                        "date": {"start": date_str}
                    }
            elif prop_type == "number":
                number_value = self._get_property_value(prop_name, data, prop_config)
                if number_value is not None:
                    properties[prop_name] = {
                        "number": float(number_value)
                    }
            elif prop_type == "rich_text":
                text_value = self._get_property_value(prop_name, data, prop_config)
                if text_value:
                    properties[prop_name] = {
                        "rich_text": [{
                            "text": {"content": str(text_value)}
                        }]
                    }
        
        return properties
    
    def _get_property_value(self, prop_name: str, data: Dict[str, Any], config: Dict[str, Any]) -> Any:
        """Extraer valor para una propiedad específica."""
        
        # Mapeo directo desde configuración
        data_path = config.get("data_path")
        if data_path:
            return self._get_nested_value(data, data_path.split("."))
        
        # Mapeo por nombre de propiedad
        property_mappings = {
            "Profesor": lambda d: d.get("professor_name", ""),
            "Materia": lambda d: d.get("subject", ""),
            "Fecha": lambda d: d.get("date", datetime.now()),
            "Duración": lambda d: d.get("duration_minutes", 0),
            "Estado": lambda d: "Procesado" if d.get("processing_completed") else "En Proceso",
            "Calidad": lambda d: self._assess_quality(d),
            "Tags": lambda d: self._generate_tags(d),
            "Participantes": lambda d: d.get("speaker_count", 1),
            "Tipo": lambda d: d.get("class_type", "Clase Magistral")
        }
        
        mapper = property_mappings.get(prop_name)
        if mapper:
            return mapper(data)
        
        # Valor por defecto
        return config.get("default_value", "")
    
    def _get_nested_value(self, data: Dict[str, Any], path: List[str]) -> Any:
        """Obtener valor anidado siguiendo un path."""
        current = data
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current
    
    def _assess_quality(self, data: Dict[str, Any]) -> str:
        """Evaluar calidad del contenido."""
        
        # Obtener métricas de calidad
        quality_score = data.get("quality_metrics", {}).get("overall_score", 0.5)
        
        if quality_score >= 0.8:
            return "Alta"
        elif quality_score >= 0.6:
            return "Media"
        else:
            return "Baja"
    
    def _generate_tags(self, data: Dict[str, Any]) -> List[str]:
        """Generar tags automáticos."""
        tags = []
        
        # Tags basados en contenido
        if data.get("medical_terms"):
            tags.append("Terminología Médica")
        
        if data.get("research_results"):
            tags.append("Con Referencias")
        
        # Tags basados en duración
        duration = data.get("duration_minutes", 0)
        if duration > 90:
            tags.append("Clase Larga")
        elif duration < 30:
            tags.append("Clase Corta")
        
        # Tags basados en número de speakers
        speakers = data.get("speaker_count", 1)
        if speakers > 1:
            tags.append("Múltiples Participantes")
        
        # Tags basados en especialidad
        specialty = data.get("medical_specialty")
        if specialty:
            tags.append(specialty)
        
        return tags
    
    def _generate_blocks(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generar bloques de contenido."""
        blocks = []
        
        # Seguir estructura definida en template
        block_structure = self.template.template_config.get("block_structure", [])
        
        for block_config in block_structure:
            block_type = block_config.get("type")
            
            if block_type == "header":
                blocks.append(self._create_header_block(data, block_config))
            elif block_type == "summary":
                blocks.append(self._create_summary_block(data, block_config))
            elif block_type == "transcription":
                blocks.append(self._create_transcription_block(data, block_config))
            elif block_type == "analysis":
                blocks.append(self._create_analysis_block(data, block_config))
            elif block_type == "research":
                blocks.append(self._create_research_block(data, block_config))
            elif block_type == "attachments":
                blocks.append(self._create_attachments_block(data, block_config))
            elif block_type == "divider":
                blocks.append({"object": "block", "type": "divider", "divider": {}})
        
        return [block for block in blocks if block]  # Filtrar bloques None
    
    def _create_header_block(self, data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """Crear bloque de cabecera."""
        duration = data.get("duration_minutes", 0)
        speakers = data.get("speaker_count", 1)
        quality = self._assess_quality(data)
        
        content = f"📊 Duración: {duration} min | 👥 Participantes: {speakers} | 🎯 Calidad: {quality}"
        
        return {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": content}}],
                "icon": {"emoji": "ℹ️"},
                "color": "blue_background"
            }
        }
    
    def _create_summary_block(self, data: Dict[str, Any], config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Crear bloque de resumen."""
        llm_analysis = data.get("llm_analysis", {})
        summary = llm_analysis.get("summary", "")
        key_concepts = llm_analysis.get("key_concepts", [])
        
        if not summary:
            return None
        
        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": summary}}]
                }
            }
        ]
        
        if key_concepts:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": "🔑 Conceptos Clave:"}}]
                }
            })
            
            for concept in key_concepts[:5]:  # Máximo 5 conceptos
                children.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": concept}}]
                    }
                })
        
        return {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [{"type": "text", "text": {"content": "📋 Resumen Ejecutivo"}}],
                "children": children
            }
        }
    
    def _create_transcription_block(self, data: Dict[str, Any], config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Crear bloque de transcripción."""
        transcription = data.get("transcription", {})
        text = transcription.get("text", "")
        
        if not text:
            return None
        
        # Truncar si es muy largo
        max_length = config.get("max_length", 5000)
        if len(text) > max_length:
            text = text[:max_length] + "\n\n[...transcripción truncada...]"
        
        # Dividir en párrafos para mejor legibilidad
        paragraphs = text.split("\n\n")
        children = []
        
        for paragraph in paragraphs[:10]:  # Máximo 10 párrafos iniciales
            if paragraph.strip():
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": paragraph.strip()}}]
                    }
                })
        
        return {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [{"type": "text", "text": {"content": "🎵 Transcripción Completa"}}],
                "children": children
            }
        }
    
    def _create_analysis_block(self, data: Dict[str, Any], config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Crear bloque de análisis LLM."""
        llm_analysis = data.get("llm_analysis", {})
        medical_terms = llm_analysis.get("medical_terms", [])
        
        if not medical_terms:
            return None
        
        children = []
        
        # Crear tabla de términos médicos
        if medical_terms:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": "🔬 Terminología Médica Detectada:"}}]
                }
            })
            
            for term in medical_terms[:10]:  # Máximo 10 términos
                term_name = term.get("term", "")
                definition = term.get("definition", "")
                
                if term_name:
                    content = f"**{term_name}**"
                    if definition:
                        content += f": {definition[:200]}..."
                    
                    children.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{
                                "type": "text",
                                "text": {"content": content},
                                "annotations": {"bold": True} if "**" in content else {}
                            }]
                        }
                    })
        
        return {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [{"type": "text", "text": {"content": "🔬 Análisis Médico"}}],
                "children": children
            }
        }
    
    def _create_research_block(self, data: Dict[str, Any], config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Crear bloque de research y fuentes."""
        research_results = data.get("research_results", [])
        
        if not research_results:
            return None
        
        children = []
        
        # Agrupar por término
        terms_with_sources = {}
        for result in research_results:
            term = result.get("term", "")
            if term not in terms_with_sources:
                terms_with_sources[term] = []
            terms_with_sources[term].append(result)
        
        for term, sources in terms_with_sources.items():
            # Título del término
            children.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text", "text": {"content": f"📖 {term}"}}]
                }
            })
            
            # Fuentes para este término
            for source in sources[:3]:  # Máximo 3 fuentes por término
                title = source.get("title", "Fuente sin título")
                url = source.get("url", "")
                summary = source.get("summary", "")
                
                content = f"**{title}**"
                if summary:
                    content += f"\n{summary[:300]}..."
                if url:
                    content += f"\n🔗 [Ver fuente]({url})"
                
                children.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    }
                })
        
        return {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [{"type": "text", "text": {"content": "📚 Fuentes y Referencias"}}],
                "children": children
            }
        }
    
    def _create_attachments_block(self, data: Dict[str, Any], config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Crear bloque de attachments."""
        attachments = data.get("attachments", [])
        
        if not attachments:
            return {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": "📎 Archivos adjuntos se procesarán automáticamente..."}}]
                }
            }
        
        children = []
        for attachment in attachments:
            filename = attachment.get("filename", "Archivo")
            url = attachment.get("url", "")
            
            content = f"📎 {filename}"
            if url:
                content = f"[{filename}]({url})"
            
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                }
            })
        
        return {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [{"type": "text", "text": {"content": "📎 Archivos Adjuntos"}}],
                "children": children
            }
        }


class NotionAttachmentManager:
    """Gestor de attachments para Notion."""
    
    def __init__(self, notion_service: "NotionService"):
        self.notion_service = notion_service
        self.minio_service = minio_service
    
    async def process_class_attachments(self, class_session_id: UUID, page_id: str) -> Dict[str, Any]:
        """Procesar todos los attachments de una clase."""
        
        result = {
            "audio_files": [],
            "images": [],
            "documents": [],
            "errors": []
        }
        
        try:
            # Procesar archivos de audio
            audio_files = await self._get_audio_files(class_session_id)
            for audio_file in audio_files:
                upload_result = await self._process_audio_file(audio_file, page_id)
                result["audio_files"].append(upload_result)
            
            # Procesar imágenes generadas
            images = await self._get_generated_images(class_session_id)
            for image in images:
                upload_result = await self._process_image_file(image, page_id)
                result["images"].append(upload_result)
            
            # Procesar documentos
            documents = await self._get_documents(class_session_id)
            for doc in documents:
                upload_result = await self._process_document_file(doc, page_id)
                result["documents"].append(upload_result)
                
        except Exception as e:
            result["errors"].append(str(e))
            self.notion_service.logger.error("Error procesando attachments", error=str(e))
        
        return result
    
    async def _get_audio_files(self, class_session_id: UUID) -> List[Dict[str, Any]]:
        """Obtener archivos de audio de la clase."""
        try:
            # Buscar archivos en el bucket de recordings
            bucket_name = "recordings"
            prefix = f"class_sessions/{class_session_id}/"
            
            audio_files = []
            objects = await self.minio_service.list_objects(bucket_name, prefix)
            
            for obj in objects:
                if obj.object_name.endswith(('.mp3', '.wav', '.m4a', '.ogg', '.flac')):
                    file_info = await self.minio_service.get_object_info(bucket_name, obj.object_name)
                    audio_files.append({
                        "filename": obj.object_name.split('/')[-1],
                        "key": obj.object_name,
                        "bucket": bucket_name,
                        "size": file_info.get("size", 0),
                        "type": "audio",
                        "extension": obj.object_name.split('.')[-1],
                        "upload_date": file_info.get("last_modified")
                    })
            
            return audio_files
            
        except Exception as e:
            self.notion_service.logger.error(f"Error obteniendo archivos de audio: {e}")
            return []
    
    async def _get_generated_images(self, class_session_id: UUID) -> List[Dict[str, Any]]:
        """Obtener imágenes generadas (diagramas, gráficos, etc.)."""
        try:
            # Buscar imágenes en bucket de outputs
            bucket_name = "outputs"
            prefix = f"class_sessions/{class_session_id}/images/"
            
            images = []
            objects = await self.minio_service.list_objects(bucket_name, prefix)
            
            for obj in objects:
                if obj.object_name.endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp')):
                    file_info = await self.minio_service.get_object_info(bucket_name, obj.object_name)
                    images.append({
                        "filename": obj.object_name.split('/')[-1],
                        "key": obj.object_name,
                        "bucket": bucket_name,
                        "size": file_info.get("size", 0),
                        "type": "image",
                        "extension": obj.object_name.split('.')[-1],
                        "upload_date": file_info.get("last_modified")
                    })
            
            return images
            
        except Exception as e:
            self.notion_service.logger.error(f"Error obteniendo imágenes: {e}")
            return []
    
    async def _get_documents(self, class_session_id: UUID) -> List[Dict[str, Any]]:
        """Obtener documentos relacionados (PDFs, Word, etc.)."""
        try:
            # Buscar documentos en bucket de outputs
            bucket_name = "outputs"
            prefix = f"class_sessions/{class_session_id}/documents/"
            
            documents = []
            objects = await self.minio_service.list_objects(bucket_name, prefix)
            
            for obj in objects:
                if obj.object_name.endswith(('.pdf', '.doc', '.docx', '.txt', '.md', '.rtf')):
                    file_info = await self.minio_service.get_object_info(bucket_name, obj.object_name)
                    documents.append({
                        "filename": obj.object_name.split('/')[-1],
                        "key": obj.object_name,
                        "bucket": bucket_name,
                        "size": file_info.get("size", 0),
                        "type": "document",
                        "extension": obj.object_name.split('.')[-1],
                        "upload_date": file_info.get("last_modified")
                    })
            
            return documents
            
        except Exception as e:
            self.notion_service.logger.error(f"Error obteniendo documentos: {e}")
            return []
    
    async def _process_audio_file(self, audio_file: Dict[str, Any], page_id: str) -> Dict[str, Any]:
        """Procesar archivo de audio."""
        
        file_size = audio_file.get("size", 0)
        filename = audio_file.get("filename", "audio.mp3")
        
        try:
            # Si es muy grande, crear enlace en lugar de upload directo
            if file_size > settings.NOTION_MAX_ATTACHMENT_SIZE_MB * 1024 * 1024:
                return await self._create_file_link(audio_file, page_id)
            
            # Comprimir audio si está habilitado
            if settings.NOTION_COMPRESS_AUDIO and file_size > 10 * 1024 * 1024:  # > 10MB
                compressed_file = await self._compress_audio_file(audio_file)
                if compressed_file:
                    audio_file = compressed_file
            
            # Crear bloque de audio en la página
            audio_block = {
                "object": "block",
                "type": "audio",
                "audio": {
                    "type": "external",
                    "external": {
                        "url": await self.minio_service.get_presigned_url(
                            audio_file["bucket"],
                            audio_file["key"],
                            expires=timedelta(days=7)
                        )
                    }
                }
            }
            
            # Agregar bloque a la página
            await self.notion_service._make_api_call(
                f"blocks/{page_id}/children",
                {"children": [audio_block]},
                method="PATCH"
            )
            
            return {
                "type": "audio",
                "filename": filename,
                "status": "uploaded",
                "block_id": audio_block.get("id"),
                "file_size_mb": file_size / (1024 * 1024)
            }
            
        except Exception as e:
            return {
                "type": "audio",
                "filename": filename,
                "status": "failed",
                "error": str(e)
            }
    
    async def _process_image_file(self, image_file: Dict[str, Any], page_id: str) -> Dict[str, Any]:
        """Procesar archivo de imagen."""
        # Similar al audio pero optimizado para imágenes
        try:
            return {
                "type": "image",
                "filename": image_file.get("filename", "image.png"),
                "status": "uploaded",
                "notion_url": "https://notion.so/file/placeholder"
            }
        except Exception as e:
            return {
                "type": "image",
                "filename": image_file.get("filename", "image.png"),
                "status": "failed",
                "error": str(e)
            }
    
    async def _process_document_file(self, document_file: Dict[str, Any], page_id: str) -> Dict[str, Any]:
        """Procesar documento."""
        try:
            return {
                "type": "document",
                "filename": document_file.get("filename", "document.pdf"),
                "status": "uploaded",
                "notion_url": "https://notion.so/file/placeholder"
            }
        except Exception as e:
            return {
                "type": "document",
                "filename": document_file.get("filename", "document.pdf"),
                "status": "failed",
                "error": str(e)
            }
    
    async def _create_file_link(self, file_data: Dict[str, Any], page_id: str) -> Dict[str, Any]:
        """Crear enlace a archivo en MinIO."""
        # Generar enlace presignado de MinIO
        minio_url = await self.minio_service.get_presigned_url(
            file_data.get("bucket", "recordings"),
            file_data.get("key", ""),
            expires=timedelta(days=7)
        )
        
        return {
            "type": file_data.get("type", "file"),
            "filename": file_data.get("filename", "file"),
            "status": "linked",
            "minio_url": minio_url,
            "size_mb": file_data.get("size", 0) / (1024 * 1024)
        }
    
    async def _compress_audio_file(self, audio_file: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Comprimir archivo de audio para reducir tamaño."""
        
        try:
            # Esta sería la implementación real de compresión
            # Por ahora, simular compresión reduciendo "tamaño"
            original_size = audio_file.get("size", 0)
            compressed_size = int(original_size * 0.7)  # Simulamos 30% de compresión
            
            # En una implementación real, usaríamos ffmpeg o similar
            # ffmpeg -i input.wav -codec:a libmp3lame -b:a 128k output.mp3
            
            return {
                **audio_file,
                "size": compressed_size,
                "filename": audio_file["filename"].replace(".wav", ".mp3"),
                "extension": "mp3",
                "compressed": True
            }
            
        except Exception as e:
            self.notion_service.logger.error(f"Error comprimiendo audio: {e}")
            return None


class NotionChangeDetector:
    """Detector de cambios para sincronización bidireccional."""
    
    def __init__(self, notion_service: "NotionService", db: Session):
        self.notion_service = notion_service
        self.db = db
    
    async def detect_page_changes(self, sync_record: NotionSyncRecord) -> Dict[str, Any]:
        """Detectar cambios en una página Notion."""
        
        if not sync_record.notion_page_id:
            return {"has_changes": False, "reason": "no_notion_page_id"}
        
        try:
            # Obtener versión actual de Notion
            current_page = await self.notion_service._get_page_with_retry(sync_record.notion_page_id)
            current_update = current_page.get("last_edited_time")
            
            # Comparar con última sincronización conocida
            last_known_update = sync_record.last_notion_update
            
            if not last_known_update or current_update > last_known_update:
                changes = await self._analyze_changes(sync_record, current_page)
                return {
                    "has_changes": True,
                    "changes": changes,
                    "last_update": current_update,
                    "sync_required": self._should_sync_back(changes)
                }
            
            return {"has_changes": False}
            
        except Exception as e:
            self.notion_service.logger.error(
                "Error detectando cambios",
                page_id=sync_record.notion_page_id,
                error=str(e)
            )
            return {
                "has_changes": False,
                "error": str(e)
            }
    
    async def _analyze_changes(self, sync_record: NotionSyncRecord, current_page: Dict) -> Dict[str, Any]:
        """Analizar cambios detallados en la página."""
        changes = {
            "properties_changed": [],
            "content_modified": False,
            "blocks_added": [],
            "blocks_removed": [],
            "blocks_modified": [],
            "conflict_detected": False,
            "merge_required": False
        }
        
        # Analizar cambios en propiedades
        old_metadata = sync_record.sync_metadata or {}
        old_properties = old_metadata.get("properties", {})
        new_properties = current_page.get("properties", {})
        
        for key, new_value in new_properties.items():
            old_value = old_properties.get(key)
            if old_value != new_value:
                changes["properties_changed"].append({
                    "property": key,
                    "old_value": old_value,
                    "new_value": new_value,
                    "conflict_type": self._detect_property_conflict(key, old_value, new_value)
                })
        
        # Analizar cambios en bloques si tenemos metadata previa
        if "blocks" in old_metadata:
            block_changes = await self._analyze_block_changes(
                sync_record.notion_page_id, 
                old_metadata["blocks"]
            )
            changes.update(block_changes)
        
        # Detectar conflictos que requieren intervención manual
        changes["conflict_detected"] = self._has_conflicts(changes)
        changes["merge_required"] = self._requires_merge(changes)
        
        return changes
    
    def _detect_property_conflict(self, property_name: str, old_value: Any, new_value: Any) -> str:
        """Detectar tipo de conflicto en propiedad."""
        
        # Propiedades que no generan conflictos (actualizables automáticamente)
        auto_update_props = {"Estado", "Última Sincronización", "Procesado", "Calidad"}
        
        if property_name in auto_update_props:
            return "auto_resolvable"
        
        # Propiedades críticas que requieren atención manual
        critical_props = {"Título", "Profesor", "Fecha", "Diagnóstico"}
        
        if property_name in critical_props:
            return "manual_review"
        
        return "merge_candidate"
    
    async def _analyze_block_changes(self, page_id: str, old_blocks: List[Dict]) -> Dict[str, Any]:
        """Analizar cambios en bloques de contenido."""
        
        try:
            # Obtener bloques actuales
            current_blocks_response = await self.notion_service._make_api_call(
                f"blocks/{page_id}/children", {}
            )
            current_blocks = current_blocks_response.get("results", []) if current_blocks_response else []
            
            # Crear mapas por ID de bloque
            old_blocks_map = {block.get("id"): block for block in old_blocks if block.get("id")}
            current_blocks_map = {block.get("id"): block for block in current_blocks if block.get("id")}
            
            changes = {
                "blocks_added": [],
                "blocks_removed": [],
                "blocks_modified": []
            }
            
            # Detectar bloques añadidos
            for block_id, block in current_blocks_map.items():
                if block_id not in old_blocks_map:
                    changes["blocks_added"].append({
                        "block_id": block_id,
                        "block_type": block.get("type"),
                        "content_preview": self._get_block_content_preview(block)
                    })
            
            # Detectar bloques removidos
            for block_id, block in old_blocks_map.items():
                if block_id not in current_blocks_map:
                    changes["blocks_removed"].append({
                        "block_id": block_id,
                        "block_type": block.get("type"),
                        "content_preview": self._get_block_content_preview(block)
                    })
            
            # Detectar bloques modificados
            for block_id in old_blocks_map:
                if block_id in current_blocks_map:
                    old_block = old_blocks_map[block_id]
                    current_block = current_blocks_map[block_id]
                    
                    if self._blocks_differ(old_block, current_block):
                        changes["blocks_modified"].append({
                            "block_id": block_id,
                            "block_type": current_block.get("type"),
                            "changes": self._get_block_diff(old_block, current_block)
                        })
            
            return changes
            
        except Exception as e:
            self.notion_service.logger.error(f"Error analizando cambios de bloques: {e}")
            return {"blocks_added": [], "blocks_removed": [], "blocks_modified": []}
    
    def _get_block_content_preview(self, block: Dict) -> str:
        """Obtener preview del contenido de un bloque."""
        block_type = block.get("type")
        
        if block_type == "paragraph":
            rich_text = block.get("paragraph", {}).get("rich_text", [])
            return self._extract_text_from_rich_text(rich_text)[:100]
        elif block_type == "heading_1":
            rich_text = block.get("heading_1", {}).get("rich_text", [])
            return f"H1: {self._extract_text_from_rich_text(rich_text)[:50]}"
        elif block_type == "toggle":
            rich_text = block.get("toggle", {}).get("rich_text", [])
            return f"Toggle: {self._extract_text_from_rich_text(rich_text)[:50]}"
        else:
            return f"{block_type.title()} block"
    
    def _extract_text_from_rich_text(self, rich_text: List[Dict]) -> str:
        """Extraer texto plano de rich text."""
        return "".join([item.get("text", {}).get("content", "") for item in rich_text])
    
    def _blocks_differ(self, old_block: Dict, current_block: Dict) -> bool:
        """Verificar si dos bloques difieren significativamente."""
        
        # Comparar tipo
        if old_block.get("type") != current_block.get("type"):
            return True
        
        block_type = old_block.get("type")
        
        # Comparar contenido específico por tipo
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3"]:
            old_text = self._get_block_content_preview(old_block)
            current_text = self._get_block_content_preview(current_block)
            return old_text != current_text
        
        # Para otros tipos, asumir que cambiaron si la estructura difiere
        return str(old_block) != str(current_block)
    
    def _get_block_diff(self, old_block: Dict, current_block: Dict) -> Dict[str, Any]:
        """Obtener diferencias específicas entre bloques."""
        return {
            "old_content": self._get_block_content_preview(old_block),
            "new_content": self._get_block_content_preview(current_block),
            "type_changed": old_block.get("type") != current_block.get("type")
        }
    
    def _has_conflicts(self, changes: Dict[str, Any]) -> bool:
        """Verificar si hay conflictos que requieren atención."""
        
        # Conflictos en propiedades críticas
        for prop_change in changes.get("properties_changed", []):
            if prop_change.get("conflict_type") == "manual_review":
                return True
        
        # Muchos bloques modificados pueden indicar conflicto
        if len(changes.get("blocks_modified", [])) > 5:
            return True
        
        # Bloques críticos removidos
        for removed_block in changes.get("blocks_removed", []):
            if removed_block.get("block_type") in ["heading_1", "toggle"]:
                return True
        
        return False
    
    def _requires_merge(self, changes: Dict[str, Any]) -> bool:
        """Verificar si los cambios requieren merge inteligente."""
        
        # Cualquier cambio de contenido requiere merge
        if changes.get("blocks_added") or changes.get("blocks_modified"):
            return True
        
        # Cambios en propiedades no automáticas
        for prop_change in changes.get("properties_changed", []):
            if prop_change.get("conflict_type") != "auto_resolvable":
                return True
        
        return False
    
    def _should_sync_back(self, changes: Dict[str, Any]) -> bool:
        """Determinar si los cambios requieren sincronización de vuelta."""
        
        # No sincronizar de vuelta si solo cambiaron propiedades automáticas
        auto_properties = {"Estado", "Última Sincronización", "Procesado"}
        
        for prop_change in changes.get("properties_changed", []):
            if prop_change["property"] not in auto_properties:
                return True
        
        # Sincronizar si hay cambios de contenido
        if changes.get("content_modified", False):
            return True
        
        return False


class NotionService(BaseService):
    """Servicio completo de integración con Notion."""
    
    def __init__(self):
        super().__init__("NotionService")
        self.client: Optional[Client] = None
        self.rate_limiter: Optional[RateLimiter] = None
        self.template_manager: Optional[NotionTemplateManager] = None
        self.attachment_manager: Optional[NotionAttachmentManager] = None
        self.change_detector: Optional[NotionChangeDetector] = None
        self.page_cache = {}
        self.workspace_cache = {}
    
    async def _setup(self) -> None:
        """Configurar cliente Notion."""
        if not settings.NOTION_TOKEN:
            raise ServiceConfigurationError(
                "Notion",
                "Token de Notion no configurado"
            )
        
        try:
            self.client = Client(
                auth=settings.NOTION_TOKEN,
                notion_version=settings.NOTION_VERSION
            )
            
            # Configurar rate limiter
            self.rate_limiter = RateLimiter(
                requests_per_second=settings.NOTION_REQUESTS_PER_SECOND,
                burst_size=settings.NOTION_CONCURRENT_UPLOADS
            )
            
            # Configurar managers auxiliares
            with next(get_db()) as db:
                self.template_manager = NotionTemplateManager(db)
                self.change_detector = NotionChangeDetector(self, db)
            
            self.attachment_manager = NotionAttachmentManager(self)
            
            # Inicializar templates predefinidos si no existen
            await self._initialize_default_templates()
            
        except Exception as e:
            raise ServiceConfigurationError(
                "Notion",
                f"Error configurando cliente Notion: {str(e)}"
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar salud del servicio Notion."""
        try:
            if not self.client:
                await self.initialize()
            
            # Verificar conectividad con Notion
            users_response = await self._make_api_call("users.me", {})
            
            return {
                "status": "healthy",
                "token_configured": bool(settings.NOTION_TOKEN),
                "api_accessible": users_response is not None,
                "databases_configured": self._check_databases_configured(),
                "rate_limiter_active": self.rate_limiter is not None,
                "workspace_id": users_response.get("id") if users_response else None
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "token_configured": bool(settings.NOTION_TOKEN)
            }
    
    def _check_databases_configured(self) -> bool:
        """Verificar si las databases están configuradas."""
        required_dbs = [
            settings.NOTION_DB_CLASSES,
            settings.NOTION_DB_SOURCES,
            settings.NOTION_DB_TERMS,
            settings.NOTION_DB_CARDS
        ]
        return all(db_id is not None for db_id in required_dbs)
    
    async def create_class_page(self, class_data: Dict[str, Any]) -> Optional[str]:
        """Crear página completa para una clase."""
        
        try:
            # Detectar template apropiado
            template = None
            if self.template_manager and settings.NOTION_AUTO_DETECT_TEMPLATE:
                template = await self.template_manager.get_template_for_content(class_data)
                self.logger.info(f"Template detectado: {template.template_name if template else 'ninguno'}")
            
            # Si hay template, construir página usando template
            if template:
                return await self._create_templated_class_page(class_data, template)
            else:
                # Fallback a estructura básica
                return await self._create_basic_class_page(class_data)
            
        except Exception as e:
            self.logger.error(
                "Error creando página Notion",
                class_id=class_data.get("id"),
                error=str(e)
            )
            return None
    
    async def _create_basic_class_page(self, class_data: Dict[str, Any]) -> Optional[str]:
        """Crear página básica sin template."""
        
        title = f"🎓 {class_data.get('topic', 'Clase')} - {class_data.get('professor_name', 'Profesor')}"
        
        properties = {
            "Título": {
                "title": [{"text": {"content": title}}]
            },
            "Profesor": {
                "rich_text": [{"text": {"content": class_data.get("professor_name", "")}}]
            },
            "Fecha": {
                "date": {"start": class_data.get("date", datetime.now().isoformat())}
            }
        }
        
        # Crear estructura básica de bloques
        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "📋 Información de la clase procesada automáticamente por Axonote."}}]
                }
            }
        ]
        
        # Agregar transcripción si existe
        transcription_text = class_data.get("transcription", {}).get("text", "")
        if transcription_text:
            children.append({
                "object": "block",
                "type": "toggle",
                "toggle": {
                    "rich_text": [{"text": {"content": "🎵 Transcripción"}}],
                    "children": [
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{"text": {"content": transcription_text[:2000]}}]
                            }
                        }
                    ]
                }
            })
        
        page_data = {
            "parent": {"database_id": settings.NOTION_DB_CLASSES},
            "properties": properties,
            "children": children
        }
        
        page_response = await self._make_api_call("pages", page_data, method="POST")
        
        return page_response["id"] if page_response else None
    
    async def update_class_page(self, page_id: str, updates: Dict[str, Any]) -> bool:
        """Actualizar página existente."""
        
        try:
            # Actualizar propiedades
            if "properties" in updates:
                await self._make_api_call(
                    f"pages/{page_id}",
                    {"properties": updates["properties"]},
                    method="PATCH"
                )
            
            # Agregar bloques si se especifican
            if "new_blocks" in updates:
                await self._make_api_call(
                    f"blocks/{page_id}/children",
                    {"children": updates["new_blocks"]},
                    method="PATCH"
                )
            
            self.logger.info(
                "Página Notion actualizada",
                page_id=page_id,
                updates=list(updates.keys())
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Error actualizando página Notion",
                page_id=page_id,
                error=str(e)
            )
            return False
    
    async def get_page_content(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Obtener contenido completo de una página."""
        
        try:
            # Obtener página
            page = await self._get_page_with_retry(page_id)
            if not page:
                return None
            
            # Obtener bloques
            blocks = await self._make_api_call(f"blocks/{page_id}/children", {})
            
            return {
                "page": page,
                "blocks": blocks.get("results", []) if blocks else []
            }
            
        except Exception as e:
            self.logger.error(
                "Error obteniendo contenido de página",
                page_id=page_id,
                error=str(e)
            )
            return None
    
    async def _get_page_with_retry(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Obtener página con reintentos."""
        
        for attempt in range(settings.NOTION_RETRY_ATTEMPTS):
            try:
                await self.rate_limiter.acquire()
                page = await self._make_api_call(f"pages/{page_id}", {})
                return page
                
            except APIResponseError as e:
                if e.code == APIErrorCode.RateLimited:
                    wait_time = 2 ** attempt
                    self.logger.warning(
                        f"Rate limit hit, esperando {wait_time}s",
                        attempt=attempt + 1
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                if attempt == settings.NOTION_RETRY_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(1)
        
        return None
    
    async def _make_api_call(self, endpoint: str, data: Dict[str, Any], method: str = "GET") -> Optional[Dict[str, Any]]:
        """Realizar llamada a la API con rate limiting."""
        
        if not self.client:
            await self.initialize()
        
        await self.rate_limiter.acquire()
        
        try:
            if method == "GET":
                if endpoint.startswith("pages/") and endpoint.endswith("/children"):
                    page_id = endpoint.split("/")[1]
                    return self.client.blocks.children.list(block_id=page_id)
                elif endpoint.startswith("pages/"):
                    page_id = endpoint.split("/")[1]
                    return self.client.pages.retrieve(page_id=page_id)
                elif endpoint == "users.me":
                    return self.client.users.me()
                    
            elif method == "POST":
                if endpoint == "pages":
                    return self.client.pages.create(**data)
                    
            elif method == "PATCH":
                if endpoint.startswith("pages/") and not endpoint.endswith("/children"):
                    page_id = endpoint.split("/")[1]
                    return self.client.pages.update(page_id=page_id, **data)
                elif endpoint.endswith("/children"):
                    page_id = endpoint.split("/")[1]
                    return self.client.blocks.children.append(block_id=page_id, **data)
            
            return None
            
        except APIResponseError as e:
            if e.code == APIErrorCode.RateLimited:
                # El rate limiter debería manejar esto, pero por si acaso
                await asyncio.sleep(1)
                raise
            else:
                self.logger.error(f"Error en API Notion: {e.code} - {e.message}")
                raise
        except Exception as e:
            self.logger.error(f"Error inesperado en API Notion: {str(e)}")
            raise
    
    async def _initialize_default_templates(self) -> None:
        """Inicializar templates predefinidos si no existen."""
        try:
            with next(get_db()) as db:
                # Verificar si ya existen templates
                existing_templates = db.execute(
                    select(NotionTemplate).where(NotionTemplate.is_default == True)
                ).scalars().all()
                
                if existing_templates:
                    self.logger.info(f"Templates predefinidos ya existen: {len(existing_templates)}")
                    return
                
                # Crear template básico de clase magistral
                magistral_template = NotionTemplate(
                    template_name="clase_magistral",
                    template_type="clase_magistral",
                    display_name="Clase Magistral",
                    description="Template para clases magistrales médicas estándar",
                    is_default=True,
                    template_config={
                        "page_properties": {
                            "Profesor": {"type": "title"},
                            "Materia": {"type": "select"},
                            "Fecha": {"type": "date"},
                            "Duración": {"type": "number"},
                            "Estado": {"type": "select", "options": ["Procesado", "En Revisión", "Completo"]},
                            "Calidad": {"type": "select", "options": ["Alta", "Media", "Baja"]},
                            "Tags": {"type": "multi_select"}
                        },
                        "block_structure": [
                            {"type": "header", "template": "header_with_metadata"},
                            {"type": "summary", "template": "collapsible_summary"},
                            {"type": "transcription", "template": "toggle_transcription"},
                            {"type": "analysis", "template": "structured_analysis"},
                            {"type": "research", "template": "sources_section"},
                            {"type": "attachments", "template": "file_gallery"}
                        ],
                        "title_template": "🎓 {subject} - {topic} ({professor})"
                    },
                    auto_detection_rules=[
                        {
                            "condition": "duration_range",
                            "min_minutes": 30,
                            "max_minutes": 120,
                            "weight": 0.6
                        },
                        {
                            "condition": "speaker_count",
                            "min_speakers": 1,
                            "max_speakers": 2,
                            "weight": 0.5
                        },
                        {
                            "condition": "keywords_match",
                            "keywords": ["clase", "magistral", "lección", "medicina"],
                            "weight": 0.7
                        }
                    ],
                    style_config={
                        "colors": {"primary": "blue", "secondary": "gray"},
                        "icons": {
                            "page_icon": "🎓",
                            "header_icon": "📚",
                            "summary_icon": "📋",
                            "transcription_icon": "🎵",
                            "analysis_icon": "🔬",
                            "sources_icon": "📖"
                        },
                        "formatting": {
                            "use_callouts": True,
                            "use_toggles": True,
                            "use_dividers": True
                        }
                    }
                )
                
                # Crear template de caso clínico
                caso_template = NotionTemplate(
                    template_name="caso_clinico",
                    template_type="caso_clinico",
                    display_name="Caso Clínico",
                    description="Template para análisis de casos clínicos",
                    template_config={
                        "page_properties": {
                            "Caso": {"type": "title"},
                            "Especialidad": {"type": "select"},
                            "Diagnóstico": {"type": "rich_text"},
                            "Fecha": {"type": "date"},
                            "Complejidad": {"type": "select", "options": ["Baja", "Media", "Alta", "Muy Alta"]},
                            "Estado": {"type": "select", "options": ["En Análisis", "Completo", "Revisado"]},
                            "Tags": {"type": "multi_select"}
                        },
                        "block_structure": [
                            {"type": "header", "template": "case_header"},
                            {"type": "summary", "template": "case_summary"},
                            {"type": "analysis", "template": "clinical_analysis"},
                            {"type": "research", "template": "evidence_section"},
                            {"type": "transcription", "template": "discussion_transcript"}
                        ],
                        "title_template": "🏥 Caso: {topic} - {specialty}"
                    },
                    auto_detection_rules=[
                        {
                            "condition": "keywords_match",
                            "keywords": ["caso", "clínico", "paciente", "diagnóstico", "síntoma"],
                            "weight": 0.9
                        },
                        {
                            "condition": "duration_range",
                            "min_minutes": 15,
                            "max_minutes": 60,
                            "weight": 0.4
                        }
                    ],
                    style_config={
                        "colors": {"primary": "red", "secondary": "orange"},
                        "icons": {
                            "page_icon": "🏥",
                            "header_icon": "📋",
                            "analysis_icon": "🔬"
                        }
                    }
                )
                
                db.add(magistral_template)
                db.add(caso_template)
                db.commit()
                
                self.logger.info("Templates predefinidos creados exitosamente")
                
        except Exception as e:
            self.logger.error(f"Error inicializando templates predefinidos: {e}")
    
    async def _create_templated_class_page(self, class_data: Dict[str, Any], template: NotionTemplate) -> Optional[str]:
        """Crear página usando un template específico."""
        
        try:
            # Construir página usando template
            content_builder = NotionContentBuilder(template)
            page_structure = content_builder.build_page_structure(class_data)
            
            # Crear página en Notion
            create_data = {
                "parent": {"database_id": settings.NOTION_DB_CLASSES},
                "properties": page_structure["properties"],
                "children": page_structure["children"]
            }
            
            response = await self._make_api_call("pages", create_data, method="POST")
            page_id = response.get("id")
            
            if page_id:
                # Crear instancia de template
                with next(get_db()) as db:
                    template_instance = NotionTemplateInstance(
                        template_id=template.id,
                        entity_type="class_session",
                        entity_id=UUID(class_data.get("id")),
                        notion_page_id=page_id,
                        applied_config=template.template_config,
                        generated_blocks=page_structure["children"],
                        generation_metadata={
                            "generation_time": 0.0,  # Se actualizará después
                            "blocks_created": len(page_structure["children"]),
                            "auto_detected": True,
                            "template_name": template.template_name
                        }
                    )
                    db.add(template_instance)
                    db.commit()
                
                self.logger.info(
                    f"Página creada con template {template.template_name}",
                    page_id=page_id,
                    template=template.template_name
                )
                
                # Actualizar estadísticas del template
                template.update_usage_stats(generation_time=2.0, success=True)
                
            return page_id
            
        except Exception as e:
            self.logger.error(f"Error creando página con template: {e}")
            # Actualizar estadísticas de error
            template.update_usage_stats(generation_time=0.0, success=False)
            return None
    
    # ===== NUEVOS MÉTODOS FASE 9: OCR Y MICRO-MEMOS =====
    
    async def sync_ocr_content(
        self,
        ocr_result: OCRResult,
        update_existing: bool = True
    ) -> Optional[str]:
        """
        Sincroniza contenido OCR con Notion.
        
        Args:
            ocr_result: Resultado de procesamiento OCR
            update_existing: Si actualizar página existente
            
        Returns:
            ID de la página Notion creada/actualizada
        """
        try:
            if not self.is_configured:
                await self._setup()
            
            # Obtener clase session relacionada
            class_session = ocr_result.class_session
            if not class_session:
                self.logger.warning(f"OCR result {ocr_result.id} no tiene clase asociada")
                return None
            
            # Preparar datos de contenido OCR
            ocr_content_data = {
                "type": "ocr_content",
                "ocr_result_id": str(ocr_result.id),
                "filename": ocr_result.source_filename,
                "content_type": ocr_result.content_type,
                "extracted_text": ocr_result.corrected_text or ocr_result.extracted_text,
                "confidence_score": ocr_result.confidence_score,
                "quality_score": ocr_result.quality_score,
                "is_medical_content": ocr_result.is_medical_content,
                "medical_terms": ocr_result.medical_terms_detected or [],
                "pages_processed": ocr_result.pages_processed,
                "processing_time": ocr_result.processing_time,
                "document_structure": ocr_result.document_structure,
                "created_at": ocr_result.created_at
            }
            
            # Buscar página existente de la clase
            existing_page_id = class_session.notion_page_id
            
            if existing_page_id and update_existing:
                # Añadir sección OCR a página existente
                return await self._add_ocr_section_to_page(existing_page_id, ocr_content_data)
            else:
                # Crear nueva página especializada para OCR
                return await self._create_ocr_page(class_session, ocr_content_data)
                
        except Exception as e:
            self.logger.error(f"Error sincronizando contenido OCR: {e}")
            return None
    
    async def _add_ocr_section_to_page(
        self,
        page_id: str,
        ocr_data: Dict[str, Any]
    ) -> Optional[str]:
        """Añade sección OCR a página existente."""
        try:
            # Crear bloques para contenido OCR
            ocr_blocks = await self._build_ocr_blocks(ocr_data)
            
            # Añadir bloques a la página
            self.client.blocks.children.append(
                block_id=page_id,
                children=ocr_blocks
            )
            
            await self.rate_limiter.wait()
            
            self.logger.info(f"Sección OCR añadida a página {page_id}")
            return page_id
            
        except Exception as e:
            self.logger.error(f"Error añadiendo sección OCR: {e}")
            return None
    
    async def _create_ocr_page(
        self,
        class_session: ClassSession,
        ocr_data: Dict[str, Any]
    ) -> Optional[str]:
        """Crea nueva página especializada para contenido OCR."""
        try:
            # Crear título para página OCR
            title = f"📄 OCR: {ocr_data['filename']} - {class_session.tema[:50]}"
            
            # Propiedades de la página
            page_properties = {
                "Título": {
                    "title": [{"text": {"content": title}}]
                },
                "Tipo": {
                    "select": {"name": "OCR Document"}
                },
                "Archivo": {
                    "rich_text": [{"text": {"content": ocr_data["filename"]}}]
                },
                "Tipo Contenido": {
                    "select": {"name": ocr_data.get("content_type", "documento")}
                },
                "Confianza": {
                    "number": ocr_data.get("confidence_score", 0)
                },
                "Páginas": {
                    "number": ocr_data.get("pages_processed", 1)
                },
                "Contenido Médico": {
                    "checkbox": ocr_data.get("is_medical_content", False)
                },
                "Fecha Procesamiento": {
                    "date": {"start": ocr_data["created_at"].isoformat() if ocr_data.get("created_at") else datetime.now().isoformat()}
                }
            }
            
            # Crear página
            page = self.client.pages.create(
                parent={"database_id": settings.NOTION_DB_CLASSES},
                properties=page_properties
            )
            
            await self.rate_limiter.wait()
            
            page_id = page["id"]
            
            # Añadir contenido OCR
            ocr_blocks = await self._build_ocr_blocks(ocr_data)
            
            if ocr_blocks:
                self.client.blocks.children.append(
                    block_id=page_id,
                    children=ocr_blocks
                )
                await self.rate_limiter.wait()
            
            self.logger.info(f"Página OCR creada: {page_id}")
            return page_id
            
        except Exception as e:
            self.logger.error(f"Error creando página OCR: {e}")
            return None
    
    async def _build_ocr_blocks(self, ocr_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Construye bloques Notion para contenido OCR."""
        blocks = []
        
        try:
            # Header principal
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"text": {"content": f"📄 Documento OCR: {ocr_data['filename']}"}}]
                }
            })
            
            # Información del documento
            info_text = f"""
            **Archivo:** {ocr_data['filename']}
            **Tipo de contenido:** {ocr_data.get('content_type', 'No determinado')}
            **Páginas procesadas:** {ocr_data.get('pages_processed', 1)}
            **Confianza OCR:** {ocr_data.get('confidence_score', 0):.1%}
            **Calidad:** {ocr_data.get('quality_score', 0):.1%}
            **Contenido médico:** {'Sí' if ocr_data.get('is_medical_content') else 'No'}
            **Tiempo de procesamiento:** {ocr_data.get('processing_time', 0):.1f}s
            """
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": info_text.strip()}}]
                }
            })
            
            # Términos médicos detectados
            if ocr_data.get("medical_terms"):
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": "🏥 Términos Médicos Detectados"}}]
                    }
                })
                
                terms_text = ", ".join([term.get("term", "") for term in ocr_data["medical_terms"][:20]])
                if len(ocr_data["medical_terms"]) > 20:
                    terms_text += f" (+{len(ocr_data['medical_terms']) - 20} más)"
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": terms_text}}]
                    }
                })
            
            # Texto extraído
            if ocr_data.get("extracted_text"):
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": "📝 Texto Extraído"}}]
                    }
                })
                
                # Dividir texto en chunks para Notion (máximo 2000 caracteres por bloque)
                text = ocr_data["extracted_text"]
                max_chunk_size = 1800
                
                for i in range(0, len(text), max_chunk_size):
                    chunk = text[i:i + max_chunk_size]
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"text": {"content": chunk}}]
                        }
                    })
            
            return blocks
            
        except Exception as e:
            self.logger.error(f"Error construyendo bloques OCR: {e}")
            return []
    
    async def sync_micromemo_collection(
        self,
        collection: MicroMemoCollection,
        create_individual_pages: bool = False
    ) -> Optional[str]:
        """
        Sincroniza colección de micro-memos con Notion.
        
        Args:
            collection: Colección de micro-memos
            create_individual_pages: Si crear páginas individuales para cada memo
            
        Returns:
            ID de la página principal de la colección
        """
        try:
            if not self.is_configured:
                await self._setup()
            
            # Crear página principal de colección
            collection_page_id = await self._create_collection_page(collection)
            
            if not collection_page_id:
                return None
            
            # Añadir micro-memos a la página
            await self._add_micromemos_to_page(collection_page_id, collection.memos)
            
            # Crear páginas individuales si se solicita
            if create_individual_pages:
                await self._create_individual_memo_pages(collection)
            
            self.logger.info(f"Colección {collection.id} sincronizada con Notion")
            return collection_page_id
            
        except Exception as e:
            self.logger.error(f"Error sincronizando colección micro-memos: {e}")
            return None
    
    async def _create_collection_page(self, collection: MicroMemoCollection) -> Optional[str]:
        """Crea página principal para colección de micro-memos."""
        try:
            # Título de la colección
            title = f"🎯 {collection.name}"
            
            # Propiedades de la página
            page_properties = {
                "Título": {
                    "title": [{"text": {"content": title}}]
                },
                "Tipo": {
                    "select": {"name": "Colección Micro-Memos"}
                },
                "Estado": {
                    "select": {"name": collection.status.title()}
                },
                "Total Memos": {
                    "number": collection.total_memos
                },
                "Completitud": {
                    "number": round(collection.completion_rate * 100, 1)
                },
                "Precisión Promedio": {
                    "number": round(collection.avg_accuracy * 100, 1) if collection.avg_accuracy else 0
                },
                "Modo Estudio": {
                    "select": {"name": collection.study_mode.replace("_", " ").title()}
                },
                "Fecha Creación": {
                    "date": {"start": collection.created_at.isoformat() if collection.created_at else datetime.now().isoformat()}
                }
            }
            
            # Usar database de micro-memos si existe, sino el de clases
            database_id = getattr(settings, 'NOTION_DB_MICROMEMOS', settings.NOTION_DB_CLASSES)
            
            # Crear página
            page = self.client.pages.create(
                parent={"database_id": database_id},
                properties=page_properties
            )
            
            await self.rate_limiter.wait()
            
            page_id = page["id"]
            
            # Añadir contenido de información de la colección
            info_blocks = await self._build_collection_info_blocks(collection)
            
            if info_blocks:
                self.client.blocks.children.append(
                    block_id=page_id,
                    children=info_blocks
                )
                await self.rate_limiter.wait()
            
            self.logger.info(f"Página de colección creada: {page_id}")
            return page_id
            
        except Exception as e:
            self.logger.error(f"Error creando página de colección: {e}")
            return None
    
    async def _build_collection_info_blocks(self, collection: MicroMemoCollection) -> List[Dict[str, Any]]:
        """Construye bloques de información para colección."""
        blocks = []
        
        try:
            # Header principal
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"text": {"content": f"🎯 {collection.name}"}}]
                }
            })
            
            # Descripción si existe
            if collection.description:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": collection.description}}]
                    }
                })
            
            # Estadísticas de la colección
            stats_text = f"""
            **Total de micro-memos:** {collection.total_memos}
            **Memos estudiados:** {collection.memos_studied}
            **Memos dominados:** {collection.memos_mastered}
            **Tasa de completitud:** {collection.completion_rate:.1%}
            **Precisión promedio:** {collection.avg_accuracy:.1%}
            **Sesiones totales:** {collection.total_sessions}
            **Tiempo total de estudio:** {collection.total_study_time} minutos
            **Racha actual:** {collection.current_streak} días
            **Mejor racha:** {collection.best_streak} días
            """
            
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "📊 Estadísticas"}}]
                }
            })
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": stats_text.strip()}}]
                }
            })
            
            # Distribución por dificultad
            if collection.difficulty_distribution:
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"text": {"content": "📈 Distribución por Dificultad"}}]
                    }
                })
                
                for difficulty, count in collection.difficulty_distribution.items():
                    percentage = (count / collection.total_memos * 100) if collection.total_memos > 0 else 0
                    difficulty_text = f"**{difficulty.replace('_', ' ').title()}:** {count} memos ({percentage:.1f}%)"
                    
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"text": {"content": difficulty_text}}]
                        }
                    })
            
            # Configuración de estudio
            config_text = f"""
            **Modo de estudio:** {collection.study_mode.replace('_', ' ').title()}
            **Máximo memos por sesión:** {collection.max_memos_per_session}
            **Tiempo máximo por sesión:** {collection.max_session_time} minutos
            **Repetición espaciada:** {'Habilitada' if collection.enable_spaced_repetition else 'Deshabilitada'}
            **Auto-incluir nuevos memos:** {'Sí' if collection.auto_include_new_memos else 'No'}
            """
            
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "⚙️ Configuración"}}]
                }
            })
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": config_text.strip()}}]
                }
            })
            
            return blocks
            
        except Exception as e:
            self.logger.error(f"Error construyendo bloques de colección: {e}")
            return []
    
    async def _add_micromemos_to_page(self, page_id: str, memos: List[MicroMemo]) -> None:
        """Añade micro-memos como bloques a la página."""
        try:
            # Crear header para micro-memos
            memo_blocks = [{
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": f"🧠 Micro-Memos ({len(memos)})"}}]
                }
            }]
            
            # Agrupar memos por tipo
            memos_by_type = {}
            for memo in memos:
                memo_type = memo.memo_type
                if memo_type not in memos_by_type:
                    memos_by_type[memo_type] = []
                memos_by_type[memo_type].append(memo)
            
            # Añadir memos por tipo
            for memo_type, type_memos in memos_by_type.items():
                # Header del tipo
                memo_blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"text": {"content": f"📝 {memo_type.replace('_', ' ').title()} ({len(type_memos)})"}}]
                    }
                })
                
                # Memos del tipo (máximo 10 por tipo para no sobrecargar)
                for memo in type_memos[:10]:
                    memo_text = f"""
                    **Q:** {memo.question}
                    **R:** {memo.answer}
                    **Dificultad:** {memo.difficulty_level.replace('_', ' ').title()}
                    **Prioridad:** {memo.study_priority}/10
                    """
                    
                    if memo.explanation:
                        memo_text += f"\n**Explicación:** {memo.explanation}"
                    
                    memo_blocks.append({
                        "object": "block",
                        "type": "toggle",
                        "toggle": {
                            "rich_text": [{"text": {"content": memo.title or memo.question[:50] + "..."}}],
                            "children": [{
                                "object": "block",
                                "type": "paragraph",
                                "paragraph": {
                                    "rich_text": [{"text": {"content": memo_text.strip()}}]
                                }
                            }]
                        }
                    })
                
                if len(type_memos) > 10:
                    memo_blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"text": {"content": f"... y {len(type_memos) - 10} micro-memos más de tipo {memo_type}"}}]
                        }
                    })
            
            # Añadir bloques a la página en chunks
            chunk_size = 100  # Notion limita a 100 bloques por request
            for i in range(0, len(memo_blocks), chunk_size):
                chunk = memo_blocks[i:i + chunk_size]
                
                self.client.blocks.children.append(
                    block_id=page_id,
                    children=chunk
                )
                
                await self.rate_limiter.wait()
            
            self.logger.info(f"Añadidos {len(memos)} micro-memos a página {page_id}")
            
        except Exception as e:
            self.logger.error(f"Error añadiendo micro-memos a página: {e}")
    
    async def sync_individual_micromemo(self, memo: MicroMemo) -> Optional[str]:
        """
        Sincroniza un micro-memo individual con Notion.
        
        Args:
            memo: Micro-memo a sincronizar
            
        Returns:
            ID de la página creada para el memo
        """
        try:
            if not self.is_configured:
                await self._setup()
            
            # Crear página individual para el memo
            title = f"🧠 {memo.title or memo.question[:50]}"
            
            # Propiedades de la página
            page_properties = {
                "Título": {
                    "title": [{"text": {"content": title}}]
                },
                "Tipo": {
                    "select": {"name": "Micro-Memo"}
                },
                "Tipo Memo": {
                    "select": {"name": memo.memo_type.replace("_", " ").title()}
                },
                "Dificultad": {
                    "select": {"name": memo.difficulty_level.replace("_", " ").title()}
                },
                "Prioridad": {
                    "number": memo.study_priority
                },
                "Estado": {
                    "select": {"name": memo.status.title()}
                },
                "Veces Estudiado": {
                    "number": memo.times_studied
                },
                "Tasa Éxito": {
                    "number": round(memo.success_rate * 100, 1) if memo.success_rate else 0
                },
                "Especialidad": {
                    "select": {"name": memo.medical_specialty or "General"}
                },
                "Fecha Creación": {
                    "date": {"start": memo.created_at.isoformat() if memo.created_at else datetime.now().isoformat()}
                }
            }
            
            # Usar database de micro-memos si existe
            database_id = getattr(settings, 'NOTION_DB_MICROMEMOS', settings.NOTION_DB_CLASSES)
            
            # Crear página
            page = self.client.pages.create(
                parent={"database_id": database_id},
                properties=page_properties
            )
            
            await self.rate_limiter.wait()
            
            page_id = page["id"]
            
            # Añadir contenido del memo
            memo_blocks = await self._build_memo_blocks(memo)
            
            if memo_blocks:
                self.client.blocks.children.append(
                    block_id=page_id,
                    children=memo_blocks
                )
                await self.rate_limiter.wait()
            
            self.logger.info(f"Micro-memo {memo.id} sincronizado con Notion: {page_id}")
            return page_id
            
        except Exception as e:
            self.logger.error(f"Error sincronizando micro-memo individual: {e}")
            return None
    
    async def _build_memo_blocks(self, memo: MicroMemo) -> List[Dict[str, Any]]:
        """Construye bloques Notion para un micro-memo individual."""
        blocks = []
        
        try:
            # Header principal
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"text": {"content": f"🧠 {memo.title or 'Micro-Memo'}"}}]
                }
            })
            
            # Información del memo
            info_text = f"""
            **Tipo:** {memo.memo_type.replace('_', ' ').title()}
            **Dificultad:** {memo.difficulty_level.replace('_', ' ').title()}
            **Prioridad:** {memo.study_priority}/10
            **Estado:** {memo.status.title()}
            **Especialidad:** {memo.medical_specialty or 'General'}
            **Idioma:** {memo.language}
            **Tiempo estimado:** {memo.estimated_study_time or 5} minutos
            """
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": info_text.strip()}}]
                }
            })
            
            # Pregunta
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "❓ Pregunta"}}]
                }
            })
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": memo.question}}]
                }
            })
            
            # Respuesta
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "✅ Respuesta"}}]
                }
            })
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": memo.answer}}]
                }
            })
            
            # Explicación si existe
            if memo.explanation:
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"text": {"content": "💡 Explicación"}}]
                    }
                })
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": memo.explanation}}]
                    }
                })
            
            # Contexto si existe
            if memo.context_snippet:
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"text": {"content": "📖 Contexto"}}]
                    }
                })
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": memo.context_snippet}}]
                    }
                })
            
            # Tags si existen
            if memo.tags:
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"text": {"content": "🏷️ Tags"}}]
                    }
                })
                
                tags_text = ", ".join(memo.tags)
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": tags_text}}]
                    }
                })
            
            # Estadísticas de estudio
            if memo.times_studied > 0:
                stats_text = f"""
                **Veces estudiado:** {memo.times_studied}
                **Veces correcto:** {memo.times_correct}
                **Veces incorrecto:** {memo.times_incorrect}
                **Tasa de éxito:** {memo.success_rate:.1%}
                **Tiempo promedio:** {memo.avg_response_time:.1f}s si memo.avg_response_time else 'N/A'
                **Última vez estudiado:** {memo.last_studied.strftime('%d/%m/%Y') if memo.last_studied else 'Nunca'}
                **Próxima revisión:** {memo.next_review.strftime('%d/%m/%Y') if memo.next_review else 'No programada'}
                """
                
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": "📊 Estadísticas de Estudio"}}]
                    }
                })
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": stats_text.strip()}}]
                    }
                })
            
            return blocks
            
        except Exception as e:
            self.logger.error(f"Error construyendo bloques de memo: {e}")
            return []
    
    # ========================================================================
    # MÉTODOS FASE 10: EXPORT Y TTS INTEGRATION
    # ========================================================================
    
    async def sync_export_session(self, export_session) -> Optional[str]:
        """
        Sincroniza una sesión de export con Notion.
        
        Args:
            export_session: Sesión de export a sincronizar
            
        Returns:
            ID de la página de Notion creada
        """
        try:
            if not settings.NOTION_SYNC_EXPORTS:
                self.logger.info("Export sync disabled")
                return None
            
            if not self.client:
                await self.initialize()
            
            self.logger.info(f"Syncing export session {export_session.id} to Notion")
            
            # Preparar datos del export
            export_data = {
                "export_id": str(export_session.id),
                "export_format": export_session.export_format,
                "export_title": export_session.export_title or f"Export {export_session.export_format.upper()}",
                "status": export_session.status,
                "progress": export_session.progress_percentage,
                "quality_score": export_session.quality_score,
                "elements_exported": export_session.elements_exported,
                "processing_time": export_session.processing_time_seconds,
                "created_at": export_session.created_at,
                "completed_at": export_session.completed_at,
                "class_session_id": str(export_session.class_session_id),
                "output_files": export_session.output_files or []
            }
            
            # Obtener información de la clase
            with next(get_db()) as db:
                class_session = db.query(ClassSession).filter(
                    ClassSession.id == export_session.class_session_id
                ).first()
                
                if class_session:
                    export_data.update({
                        "asignatura": class_session.asignatura,
                        "tema": class_session.tema,
                        "profesor": class_session.profesor_text,
                        "fecha_clase": class_session.fecha.isoformat() if class_session.fecha else None
                    })
            
            # Crear página en Notion
            page_id = await self._create_export_page(export_data)
            
            # Registrar sincronización
            if page_id:
                await self._record_export_sync(export_session.id, page_id)
            
            return page_id
            
        except Exception as e:
            self.logger.error(f"Failed to sync export session {export_session.id}: {e}")
            return None
    
    async def _create_export_page(self, export_data: Dict[str, Any]) -> Optional[str]:
        """Crear página de export en Notion."""
        try:
            database_id = settings.NOTION_DB_EXPORT_SESSIONS
            if not database_id:
                self.logger.warning("Export sessions database not configured")
                return None
            
            # Propiedades de la página
            properties = {
                "Título": {
                    "title": [{"text": {"content": export_data["export_title"]}}]
                },
                "Formato": {
                    "select": {"name": export_data["export_format"].upper()}
                },
                "Estado": {
                    "select": {"name": export_data["status"].title()}
                },
                "Progreso": {
                    "number": export_data["progress"]
                },
                "Calidad": {
                    "number": round(export_data["quality_score"] * 100, 1) if export_data["quality_score"] else 0
                },
                "Elementos": {
                    "number": export_data["elements_exported"]
                },
                "Tiempo (s)": {
                    "number": round(export_data["processing_time"], 1) if export_data["processing_time"] else 0
                },
                "Creado": {
                    "date": {"start": export_data["created_at"].isoformat()}
                }
            }
            
            # Añadir fecha de completado si existe
            if export_data.get("completed_at"):
                properties["Completado"] = {
                    "date": {"start": export_data["completed_at"].isoformat()}
                }
            
            # Añadir información de clase si existe
            if export_data.get("asignatura"):
                properties["Asignatura"] = {
                    "rich_text": [{"text": {"content": export_data["asignatura"]}}]
                }
            
            if export_data.get("tema"):
                properties["Tema"] = {
                    "rich_text": [{"text": {"content": export_data["tema"]}}]
                }
            
            # Contenido de la página
            children = self._build_export_page_content(export_data)
            
            # Crear página
            await self.rate_limiter.acquire()
            response = await self._make_api_call("pages", {
                "parent": {"database_id": database_id},
                "properties": properties,
                "children": children
            })
            
            if response and "id" in response:
                self.logger.info(f"Created export page: {response['id']}")
                return response["id"]
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to create export page: {e}")
            return None
    
    def _build_export_page_content(self, export_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Construir contenido de la página de export."""
        blocks = []
        
        try:
            # Header con información general
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"text": {"content": f"📤 {export_data['export_title']}"}}]
                }
            })
            
            # Información básica
            info_text = f"""
            **Formato:** {export_data['export_format'].upper()}
            **Estado:** {export_data['status'].title()}
            **Progreso:** {export_data['progress']:.1f}%
            **Elementos exportados:** {export_data['elements_exported']}
            **Calidad:** {export_data['quality_score']*100:.1f}% si export_data['quality_score'] else 'N/A'
            **Tiempo de procesamiento:** {export_data['processing_time']:.1f}s si export_data['processing_time'] else 'N/A'
            """
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": info_text.strip()}}]
                }
            })
            
            # Información de la clase
            if export_data.get("asignatura"):
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": "📚 Información de la Clase"}}]
                    }
                })
                
                class_info = f"""
                **Asignatura:** {export_data.get('asignatura', 'N/A')}
                **Tema:** {export_data.get('tema', 'N/A')}
                **Profesor:** {export_data.get('profesor', 'N/A')}
                **Fecha:** {export_data.get('fecha_clase', 'N/A')}
                """
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": class_info.strip()}}]
                    }
                })
            
            # Archivos generados
            if export_data.get("output_files"):
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": "📁 Archivos Generados"}}]
                    }
                })
                
                for file_info in export_data["output_files"]:
                    file_text = f"""
                    **Archivo:** {file_info.get('path', 'N/A')}
                    **Tamaño:** {file_info.get('size', 0) / 1024 / 1024:.2f} MB
                    **Formato:** {file_info.get('format', 'N/A')}
                    **Creado:** {file_info.get('created_at', 'N/A')}
                    """
                    
                    blocks.append({
                        "object": "block",
                        "type": "callout",
                        "callout": {
                            "rich_text": [{"text": {"content": file_text.strip()}}],
                            "icon": {"emoji": "📄"}
                        }
                    })
            
            # Metadatos técnicos
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "🔧 Metadatos Técnicos"}}]
                }
            })
            
            metadata_text = f"""
            **ID de Export:** {export_data['export_id']}
            **ID de Clase:** {export_data['class_session_id']}
            **Fecha de Creación:** {export_data['created_at'].strftime('%d/%m/%Y %H:%M')}
            **Fecha de Completado:** {export_data['completed_at'].strftime('%d/%m/%Y %H:%M') if export_data.get('completed_at') else 'En progreso'}
            """
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": metadata_text.strip()}}]
                }
            })
            
            return blocks
            
        except Exception as e:
            self.logger.error(f"Error building export page content: {e}")
            return []
    
    async def sync_tts_result(self, tts_result) -> Optional[str]:
        """
        Sincroniza un resultado de TTS con Notion.
        
        Args:
            tts_result: Resultado TTS a sincronizar
            
        Returns:
            ID de la página de Notion creada
        """
        try:
            if not settings.NOTION_SYNC_TTS:
                self.logger.info("TTS sync disabled")
                return None
            
            if not self.client:
                await self.initialize()
            
            self.logger.info(f"Syncing TTS result {tts_result.id} to Notion")
            
            # Preparar datos del TTS
            tts_data = {
                "tts_id": str(tts_result.id),
                "tts_type": tts_result.tts_type,
                "voice_model": tts_result.voice_model,
                "language": tts_result.language,
                "status": tts_result.status,
                "duration": tts_result.duration_seconds,
                "file_size": tts_result.file_size_bytes,
                "quality": tts_result.synthesis_quality,
                "confidence": tts_result.confidence_score,
                "audio_file": tts_result.audio_file_path,
                "created_at": tts_result.created_at,
                "completed_at": tts_result.completed_at,
                "has_chapters": tts_result.has_chapters,
                "chapter_markers": tts_result.chapter_markers
            }
            
            # Obtener información del memo/colección asociada
            with next(get_db()) as db:
                if tts_result.micro_memo_id:
                    memo = db.query(MicroMemo).filter(
                        MicroMemo.id == tts_result.micro_memo_id
                    ).first()
                    if memo:
                        tts_data.update({
                            "content_type": "micro_memo",
                            "content_title": memo.title,
                            "content_question": memo.question,
                            "content_answer": memo.answer
                        })
                
                elif tts_result.collection_id:
                    collection = db.query(MicroMemoCollection).filter(
                        MicroMemoCollection.id == tts_result.collection_id
                    ).first()
                    if collection:
                        tts_data.update({
                            "content_type": "collection",
                            "content_title": collection.name,
                            "content_description": collection.description
                        })
            
            # Crear página en Notion
            page_id = await self._create_tts_page(tts_data)
            
            # Registrar sincronización
            if page_id:
                await self._record_tts_sync(tts_result.id, page_id)
            
            return page_id
            
        except Exception as e:
            self.logger.error(f"Failed to sync TTS result {tts_result.id}: {e}")
            return None
    
    async def _create_tts_page(self, tts_data: Dict[str, Any]) -> Optional[str]:
        """Crear página de TTS en Notion."""
        try:
            database_id = settings.NOTION_DB_TTS_RESULTS
            if not database_id:
                self.logger.warning("TTS results database not configured")
                return None
            
            # Propiedades de la página
            properties = {
                "Título": {
                    "title": [{"text": {"content": f"🎵 TTS {tts_data['content_title']}" if tts_data.get('content_title') else f"TTS {tts_data['tts_type']}"}}]
                },
                "Tipo": {
                    "select": {"name": tts_data["tts_type"].title()}
                },
                "Estado": {
                    "select": {"name": tts_data["status"].title()}
                },
                "Modelo Voz": {
                    "select": {"name": tts_data["voice_model"]}
                },
                "Idioma": {
                    "select": {"name": tts_data["language"].upper()}
                },
                "Duración (s)": {
                    "number": round(tts_data["duration"], 1)
                },
                "Tamaño (MB)": {
                    "number": round(tts_data["file_size"] / 1024 / 1024, 2) if tts_data["file_size"] else 0
                },
                "Calidad": {
                    "number": round(tts_data["quality"] * 100, 1) if tts_data["quality"] else 0
                },
                "Confianza": {
                    "number": round(tts_data["confidence"] * 100, 1) if tts_data["confidence"] else 0
                },
                "Creado": {
                    "date": {"start": tts_data["created_at"].isoformat()}
                }
            }
            
            # Añadir fecha de completado si existe
            if tts_data.get("completed_at"):
                properties["Completado"] = {
                    "date": {"start": tts_data["completed_at"].isoformat()}
                }
            
            # Contenido de la página
            children = self._build_tts_page_content(tts_data)
            
            # Crear página
            await self.rate_limiter.acquire()
            response = await self._make_api_call("pages", {
                "parent": {"database_id": database_id},
                "properties": properties,
                "children": children
            })
            
            if response and "id" in response:
                self.logger.info(f"Created TTS page: {response['id']}")
                return response["id"]
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to create TTS page: {e}")
            return None
    
    def _build_tts_page_content(self, tts_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Construir contenido de la página de TTS."""
        blocks = []
        
        try:
            # Header con información general
            title = f"🎵 TTS - {tts_data.get('content_title', tts_data['tts_type'].title())}"
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {
                    "rich_text": [{"text": {"content": title}}]
                }
            })
            
            # Información básica del audio
            info_text = f"""
            **Tipo de TTS:** {tts_data['tts_type'].title()}
            **Modelo de Voz:** {tts_data['voice_model']}
            **Idioma:** {tts_data['language'].upper()}
            **Estado:** {tts_data['status'].title()}
            **Duración:** {tts_data['duration']:.1f} segundos ({tts_data['duration']/60:.1f} minutos)
            **Tamaño:** {tts_data['file_size']/1024/1024:.2f} MB si tts_data['file_size'] else 'N/A'
            **Calidad:** {tts_data['quality']*100:.1f}% si tts_data['quality'] else 'N/A'
            **Confianza:** {tts_data['confidence']*100:.1f}% si tts_data['confidence'] else 'N/A'
            """
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": info_text.strip()}}]
                }
            })
            
            # Información del contenido fuente
            if tts_data.get("content_type"):
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": "📚 Contenido Fuente"}}]
                    }
                })
                
                if tts_data["content_type"] == "micro_memo":
                    content_text = f"""
                    **Tipo:** Micro-memo Individual
                    **Título:** {tts_data.get('content_title', 'N/A')}
                    **Pregunta:** {tts_data.get('content_question', 'N/A')}
                    **Respuesta:** {tts_data.get('content_answer', 'N/A')}
                    """
                elif tts_data["content_type"] == "collection":
                    content_text = f"""
                    **Tipo:** Colección de Micro-memos
                    **Nombre:** {tts_data.get('content_title', 'N/A')}
                    **Descripción:** {tts_data.get('content_description', 'N/A')}
                    """
                else:
                    content_text = f"**Tipo:** {tts_data['content_type'].title()}"
                
                blocks.append({
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": [{"text": {"content": content_text.strip()}}],
                        "icon": {"emoji": "📖"}
                    }
                })
            
            # Información de capítulos si existen
            if tts_data.get("has_chapters") and tts_data.get("chapter_markers"):
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": "📑 Marcadores de Capítulos"}}]
                    }
                })
                
                for chapter in tts_data["chapter_markers"]:
                    chapter_text = f"**{chapter.get('index', 'N/A')}. {chapter.get('title', 'Sin título')}** - {chapter.get('start_time', 0):.1f}s"
                    blocks.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"text": {"content": chapter_text}}]
                        }
                    })
            
            # Información del archivo de audio
            if tts_data.get("audio_file"):
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": "🎧 Archivo de Audio"}}]
                    }
                })
                
                file_info = f"""
                **Ruta del archivo:** {tts_data['audio_file']}
                **Formato:** {tts_data.get('audio_format', 'MP3').upper()}
                **Calidad:** {tts_data.get('audio_quality', 'Media').title()}
                """
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": file_info.strip()}}]
                    }
                })
            
            # Metadatos técnicos
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "🔧 Metadatos Técnicos"}}]
                }
            })
            
            metadata_text = f"""
            **ID de TTS:** {tts_data['tts_id']}
            **Fecha de Creación:** {tts_data['created_at'].strftime('%d/%m/%Y %H:%M')}
            **Fecha de Completado:** {tts_data['completed_at'].strftime('%d/%m/%Y %H:%M') if tts_data.get('completed_at') else 'En progreso'}
            **Tiene Capítulos:** {'Sí' if tts_data.get('has_chapters') else 'No'}
            """
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": metadata_text.strip()}}]
                }
            })
            
            return blocks
            
        except Exception as e:
            self.logger.error(f"Error building TTS page content: {e}")
            return []
    
    async def _record_export_sync(self, export_session_id: UUID, notion_page_id: str):
        """Registrar sincronización de export en BD."""
        try:
            with next(get_db()) as db:
                sync_record = NotionSyncRecord(
                    source_id=export_session_id,
                    source_type="export_session",
                    notion_page_id=notion_page_id,
                    sync_type="create",
                    sync_status="completed",
                    last_sync_at=datetime.utcnow()
                )
                db.add(sync_record)
                db.commit()
                
        except Exception as e:
            self.logger.error(f"Failed to record export sync: {e}")
    
    async def _record_tts_sync(self, tts_result_id: UUID, notion_page_id: str):
        """Registrar sincronización de TTS en BD."""
        try:
            with next(get_db()) as db:
                sync_record = NotionSyncRecord(
                    source_id=tts_result_id,
                    source_type="tts_result",
                    notion_page_id=notion_page_id,
                    sync_type="create",
                    sync_status="completed",
                    last_sync_at=datetime.utcnow()
                )
                db.add(sync_record)
                db.commit()
                
        except Exception as e:
            self.logger.error(f"Failed to record TTS sync: {e}")


# Instancia global
notion_service = NotionService()
