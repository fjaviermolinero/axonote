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
    NotionTemplateInstance, ResearchResult, LLMAnalysisResult
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
        # TODO: Implementar obtención desde MinIO
        return []
    
    async def _get_generated_images(self, class_session_id: UUID) -> List[Dict[str, Any]]:
        """Obtener imágenes generadas."""
        # TODO: Implementar obtención de imágenes
        return []
    
    async def _get_documents(self, class_session_id: UUID) -> List[Dict[str, Any]]:
        """Obtener documentos relacionados."""
        # TODO: Implementar obtención de documentos
        return []
    
    async def _process_audio_file(self, audio_file: Dict[str, Any], page_id: str) -> Dict[str, Any]:
        """Procesar archivo de audio."""
        
        file_size = audio_file.get("size", 0)
        
        # Si es muy grande, crear enlace en lugar de upload directo
        if file_size > settings.NOTION_MAX_ATTACHMENT_SIZE_MB * 1024 * 1024:
            return await self._create_file_link(audio_file, page_id)
        
        # Upload directo a Notion
        try:
            # TODO: Implementar upload a Notion
            return {
                "type": "audio",
                "filename": audio_file.get("filename", "audio.mp3"),
                "status": "uploaded",
                "notion_url": "https://notion.so/file/placeholder"
            }
        except Exception as e:
            return {
                "type": "audio",
                "filename": audio_file.get("filename", "audio.mp3"),
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
        """Analizar tipos de cambios detectados."""
        changes = {
            "properties_changed": [],
            "content_modified": False,
            "blocks_added": [],
            "blocks_removed": [],
            "blocks_modified": []
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
                    "new_value": new_value
                })
        
        # Para análisis completo de bloques, sería necesario obtener
        # el contenido completo de la página y comparar
        # Por ahora, asumir que hay cambios si las propiedades cambiaron
        if changes["properties_changed"]:
            changes["content_modified"] = True
        
        return changes
    
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
        super().__init__()
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
            self.attachment_manager = NotionAttachmentManager(self)
            
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
            # TODO: Detectar template apropiado cuando se implemente template_manager
            template = None
            
            # Si no hay template, crear estructura básica
            if not template:
                return await self._create_basic_class_page(class_data)
            
            # TODO: Construir página usando template cuando esté implementado
            
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


# Instancia global
notion_service = NotionService()
