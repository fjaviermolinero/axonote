"""
Modelo ClassSession con campos cifrados para datos sensibles.
Extiende el modelo base con capacidades de cifrado automático.
"""

from datetime import date, datetime
from typing import Optional
from sqlalchemy import Column, String, Text, Integer, Float, Date, Enum, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property

from app.models.base import BaseModel
from app.models.class_session import EstadoPipeline
from app.services.encryption_service import CamposCifrados, obtener_servicio_cifrado


class ClassSessionSegura(BaseModel, CamposCifrados):
    """
    Versión segura de ClassSession con cifrado de datos sensibles.
    
    Los campos sensibles se cifran automáticamente antes de almacenar
    y se descifran al acceder a ellos.
    """
    
    __tablename__ = "class_sessions_seguras"
    
    # ==============================================
    # INFORMACIÓN BÁSICA DE LA CLASE
    # ==============================================
    
    fecha = Column(Date, nullable=False, index=True)
    asignatura = Column(String(200), nullable=False, index=True)
    tema = Column(String(500), nullable=False)
    profesor_text = Column(String(200), nullable=False)
    
    # Relaciones
    profesor_id = Column(UUID(as_uuid=True), ForeignKey("professors.id"), nullable=True)
    usuario_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    
    # ==============================================
    # INFORMACIÓN DEL AUDIO
    # ==============================================
    
    audio_url = Column(String(1000), nullable=True)
    duracion_sec = Column(Integer, nullable=True)
    
    # ==============================================
    # CAMPOS CIFRADOS - DATOS SENSIBLES
    # ==============================================
    
    # Estos campos almacenan datos cifrados
    transcripcion_cifrada = Column(Text, nullable=True)
    resumen_cifrado = Column(Text, nullable=True)
    ampliacion_cifrada = Column(Text, nullable=True)
    glosario_cifrado = Column(Text, nullable=True)
    preguntas_cifradas = Column(Text, nullable=True)
    tarjetas_cifradas = Column(Text, nullable=True)
    notas_privadas_cifradas = Column(Text, nullable=True)
    
    # ==============================================
    # CAMPOS NO SENSIBLES
    # ==============================================
    
    # Diarización (no contiene texto sensible, solo metadatos)
    diarizacion_json = Column(JSON, nullable=True)
    
    # Métricas de calidad
    confianza_asr = Column(Float, nullable=True)
    confianza_llm = Column(Float, nullable=True)
    
    # Estado y control
    estado_pipeline = Column(
        Enum(EstadoPipeline),
        nullable=False,
        default=EstadoPipeline.UPLOADED,
        index=True
    )
    
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    
    # Integración Notion
    notion_page_id = Column(String(100), nullable=True, index=True)
    notion_synced_at = Column(DateTime, nullable=True)
    
    # Metadatos adicionales
    idioma_detectado = Column(String(10), nullable=True)
    palabra_count = Column(Integer, nullable=True)
    tiempo_procesamiento_sec = Column(Integer, nullable=True)
    costo_openai_eur = Column(Float, nullable=True)
    tokens_utilizados = Column(Integer, nullable=True)
    
    # ==============================================
    # METADATOS DE CIFRADO
    # ==============================================
    
    # Información sobre el cifrado para auditoría
    cifrado_version = Column(String(10), default="1.0")
    cifrado_timestamp = Column(DateTime, nullable=True)
    
    # ==============================================
    # RELACIONES
    # ==============================================
    
    profesor = relationship("Professor", back_populates="class_sessions_seguras")
    usuario = relationship("Usuario", back_populates="class_sessions_seguras")
    
    # ==============================================
    # ÍNDICES PARA OPTIMIZACIÓN
    # ==============================================
    
    __table_args__ = (
        Index('idx_class_session_segura_usuario_fecha', 'usuario_id', 'fecha'),
        Index('idx_class_session_segura_estado', 'estado_pipeline'),
        Index('idx_class_session_segura_asignatura', 'asignatura'),
    )
    
    # ==============================================
    # PROPIEDADES CIFRADAS AUTOMÁTICAS
    # ==============================================
    
    @hybrid_property
    def transcripcion_md(self) -> Optional[str]:
        """Propiedad que descifra automáticamente la transcripción."""
        return self.descifrar_campo(self.transcripcion_cifrada)
    
    @transcripcion_md.setter
    def transcripcion_md(self, valor: Optional[str]):
        """Setter que cifra automáticamente la transcripción."""
        self.transcripcion_cifrada = self.cifrar_campo(valor) if valor else None
        if valor:
            self.cifrado_timestamp = datetime.utcnow()
    
    @hybrid_property
    def resumen_md(self) -> Optional[str]:
        """Propiedad que descifra automáticamente el resumen."""
        return self.descifrar_campo(self.resumen_cifrado)
    
    @resumen_md.setter
    def resumen_md(self, valor: Optional[str]):
        """Setter que cifra automáticamente el resumen."""
        self.resumen_cifrado = self.cifrar_campo(valor) if valor else None
        if valor:
            self.cifrado_timestamp = datetime.utcnow()
    
    @hybrid_property
    def ampliacion_md(self) -> Optional[str]:
        """Propiedad que descifra automáticamente la ampliación."""
        return self.descifrar_campo(self.ampliacion_cifrada)
    
    @ampliacion_md.setter
    def ampliacion_md(self, valor: Optional[str]):
        """Setter que cifra automáticamente la ampliación."""
        self.ampliacion_cifrada = self.cifrar_campo(valor) if valor else None
        if valor:
            self.cifrado_timestamp = datetime.utcnow()
    
    @hybrid_property
    def glosario_json(self) -> Optional[dict]:
        """Propiedad que descifra automáticamente el glosario."""
        valor_descifrado = self.descifrar_campo(self.glosario_cifrado)
        if valor_descifrado:
            import json
            try:
                return json.loads(valor_descifrado)
            except json.JSONDecodeError:
                return None
        return None
    
    @glosario_json.setter
    def glosario_json(self, valor: Optional[dict]):
        """Setter que cifra automáticamente el glosario."""
        if valor:
            import json
            valor_json = json.dumps(valor, ensure_ascii=False)
            self.glosario_cifrado = self.cifrar_campo(valor_json)
            self.cifrado_timestamp = datetime.utcnow()
        else:
            self.glosario_cifrado = None
    
    @hybrid_property
    def preguntas_json(self) -> Optional[dict]:
        """Propiedad que descifra automáticamente las preguntas."""
        valor_descifrado = self.descifrar_campo(self.preguntas_cifradas)
        if valor_descifrado:
            import json
            try:
                return json.loads(valor_descifrado)
            except json.JSONDecodeError:
                return None
        return None
    
    @preguntas_json.setter
    def preguntas_json(self, valor: Optional[dict]):
        """Setter que cifra automáticamente las preguntas."""
        if valor:
            import json
            valor_json = json.dumps(valor, ensure_ascii=False)
            self.preguntas_cifradas = self.cifrar_campo(valor_json)
            self.cifrado_timestamp = datetime.utcnow()
        else:
            self.preguntas_cifradas = None
    
    @hybrid_property
    def tarjetas_json(self) -> Optional[dict]:
        """Propiedad que descifra automáticamente las tarjetas."""
        valor_descifrado = self.descifrar_campo(self.tarjetas_cifradas)
        if valor_descifrado:
            import json
            try:
                return json.loads(valor_descifrado)
            except json.JSONDecodeError:
                return None
        return None
    
    @tarjetas_json.setter
    def tarjetas_json(self, valor: Optional[dict]):
        """Setter que cifra automáticamente las tarjetas."""
        if valor:
            import json
            valor_json = json.dumps(valor, ensure_ascii=False)
            self.tarjetas_cifradas = self.cifrar_campo(valor_json)
            self.cifrado_timestamp = datetime.utcnow()
        else:
            self.tarjetas_cifradas = None
    
    @hybrid_property
    def notas_privadas(self) -> Optional[str]:
        """Propiedad que descifra automáticamente las notas privadas."""
        return self.descifrar_campo(self.notas_privadas_cifradas)
    
    @notas_privadas.setter
    def notas_privadas(self, valor: Optional[str]):
        """Setter que cifra automáticamente las notas privadas."""
        self.notas_privadas_cifradas = self.cifrar_campo(valor) if valor else None
        if valor:
            self.cifrado_timestamp = datetime.utcnow()
    
    # ==============================================
    # MÉTODOS DE UTILIDAD
    # ==============================================
    
    @property
    def duracion_minutos(self) -> Optional[int]:
        """Duración en minutos (calculada)."""
        return round(self.duracion_sec / 60) if self.duracion_sec else None
    
    @property
    def is_completed(self) -> bool:
        """True si el procesamiento está completado."""
        return self.estado_pipeline == EstadoPipeline.DONE
    
    @property
    def has_error(self) -> bool:
        """True si hay error en el procesamiento."""
        return self.estado_pipeline == EstadoPipeline.ERROR
    
    @property
    def progress_percentage(self) -> int:
        """Porcentaje de progreso del pipeline (0-100)."""
        pipeline_steps = list(EstadoPipeline)
        if self.estado_pipeline == EstadoPipeline.ERROR:
            return 0
        
        try:
            current_index = pipeline_steps.index(self.estado_pipeline)
            total_steps = len(pipeline_steps) - 2
            if self.estado_pipeline == EstadoPipeline.DONE:
                return 100
            return int((current_index / total_steps) * 100)
        except ValueError:
            return 0
    
    @property
    def tiene_datos_sensibles(self) -> bool:
        """Verifica si la sesión contiene datos sensibles cifrados."""
        campos_sensibles = [
            self.transcripcion_cifrada,
            self.resumen_cifrado,
            self.ampliacion_cifrada,
            self.glosario_cifrado,
            self.preguntas_cifradas,
            self.tarjetas_cifradas,
            self.notas_privadas_cifradas
        ]
        return any(campo is not None for campo in campos_sensibles)
    
    def exportar_datos_anonimizados(self) -> dict:
        """Exporta datos de la sesión sin información sensible."""
        return {
            "id": str(self.id),
            "fecha": self.fecha.isoformat(),
            "asignatura": self.asignatura,
            "tema": self.tema,
            "duracion_minutos": self.duracion_minutos,
            "estado_pipeline": self.estado_pipeline.value,
            "idioma_detectado": self.idioma_detectado,
            "palabra_count": self.palabra_count,
            "confianza_asr": self.confianza_asr,
            "confianza_llm": self.confianza_llm,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "tiene_datos_sensibles": self.tiene_datos_sensibles
        }
    
    def limpiar_datos_sensibles(self):
        """Elimina todos los datos sensibles cifrados (para GDPR)."""
        self.transcripcion_cifrada = None
        self.resumen_cifrado = None
        self.ampliacion_cifrada = None
        self.glosario_cifrado = None
        self.preguntas_cifradas = None
        self.tarjetas_cifradas = None
        self.notas_privadas_cifradas = None
        self.cifrado_timestamp = None
    
    def rotar_cifrado(self, nuevo_servicio_cifrado):
        """Rota el cifrado de todos los campos sensibles con una nueva clave."""
        servicio_actual = obtener_servicio_cifrado()
        
        # Lista de campos cifrados
        campos_cifrados = [
            ('transcripcion_cifrada', 'transcripcion_md'),
            ('resumen_cifrado', 'resumen_md'),
            ('ampliacion_cifrada', 'ampliacion_md'),
            ('glosario_cifrado', 'glosario_json'),
            ('preguntas_cifradas', 'preguntas_json'),
            ('tarjetas_cifradas', 'tarjetas_json'),
            ('notas_privadas_cifradas', 'notas_privadas')
        ]
        
        for campo_cifrado, propiedad in campos_cifrados:
            valor_cifrado = getattr(self, campo_cifrado)
            if valor_cifrado:
                try:
                    # Descifrar con clave actual
                    valor_plano = servicio_actual.descifrar_datos(valor_cifrado)
                    
                    # Re-cifrar con nueva clave
                    nuevo_valor_cifrado = nuevo_servicio_cifrado.cifrar_datos(valor_plano)
                    
                    # Actualizar campo
                    setattr(self, campo_cifrado, nuevo_valor_cifrado)
                    
                except Exception as e:
                    # Log del error pero continuar con otros campos
                    print(f"Error rotando cifrado del campo {campo_cifrado}: {str(e)}")
        
        self.cifrado_timestamp = datetime.utcnow()
    
    def __repr__(self) -> str:
        return (
            f"<ClassSessionSegura("
            f"id={self.id}, "
            f"fecha={self.fecha}, "
            f"asignatura='{self.asignatura}', "
            f"usuario_id={self.usuario_id}, "
            f"estado='{self.estado_pipeline}', "
            f"cifrado={self.tiene_datos_sensibles}"
            f")>"
        )
