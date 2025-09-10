"""Agregar modelos de metricas para dashboard

Revision ID: 001_metricas
Revises: 
Create Date: 2024-09-10 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_metricas'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Crear tabla sesiones_metricas ###
    op.create_table('sesiones_metricas',
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False, comment='ID único de la sesión de métricas'),
        sa.Column('nombre_sesion', sa.String(length=255), nullable=False, comment='Nombre descriptivo de la sesión'),
        sa.Column('tipo_sesion', sa.String(length=50), nullable=False, comment='Tipo de sesión'),
        sa.Column('tiempo_inicio', sa.DateTime(timezone=True), nullable=False, comment='Inicio de la sesión'),
        sa.Column('tiempo_fin', sa.DateTime(timezone=True), nullable=True, comment='Fin de la sesión'),
        sa.Column('duracion_segundos', sa.Integer(), nullable=True, comment='Duración en segundos'),
        sa.Column('estado', sa.String(length=20), nullable=False, comment='Estado de la sesión'),
        sa.Column('es_activa', sa.Boolean(), nullable=False, comment='Si está activa'),
        sa.Column('id_sesion_clase', postgresql.UUID(as_uuid=True), nullable=True, comment='ID de sesión de clase'),
        sa.Column('id_profesor', postgresql.UUID(as_uuid=True), nullable=True, comment='ID del profesor'),
        sa.Column('total_metricas_recolectadas', sa.Integer(), nullable=False, comment='Total métricas'),
        sa.Column('contador_alertas_criticas', sa.Integer(), nullable=False, comment='Alertas críticas'),
        sa.Column('contador_alertas_warning', sa.Integer(), nullable=False, comment='Alertas warning'),
        sa.Column('etiquetas', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='Tags'),
        sa.Column('datos_contexto', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='Datos contexto'),
        sa.Column('notas', sa.Text(), nullable=True, comment='Notas adicionales'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('session_id')
    )
    
    # ### Crear tabla metricas_procesamiento ###
    op.create_table('metricas_procesamiento',
        sa.Column('metrica_id', postgresql.UUID(as_uuid=True), nullable=False, comment='ID único de métrica'),
        sa.Column('id_sesion_metrica', postgresql.UUID(as_uuid=True), nullable=False, comment='ID sesión métrica'),
        sa.Column('tipo_metrica', sa.String(length=50), nullable=False, comment='Tipo procesamiento'),
        sa.Column('nombre_componente', sa.String(length=100), nullable=False, comment='Nombre componente'),
        sa.Column('tiempo_inicio', sa.DateTime(timezone=True), nullable=False, comment='Inicio procesamiento'),
        sa.Column('tiempo_fin', sa.DateTime(timezone=True), nullable=False, comment='Fin procesamiento'),
        sa.Column('duracion_ms', sa.Integer(), nullable=False, comment='Duración en ms'),
        sa.Column('tamano_entrada_bytes', sa.BigInteger(), nullable=True, comment='Tamaño entrada'),
        sa.Column('tamano_salida_bytes', sa.BigInteger(), nullable=True, comment='Tamaño salida'),
        sa.Column('puntuacion_calidad', sa.Float(), nullable=True, comment='Puntuación calidad'),
        sa.Column('puntuacion_confianza', sa.Float(), nullable=True, comment='Puntuación confianza'),
        sa.Column('uso_cpu_porcentaje', sa.Float(), nullable=True, comment='Uso CPU'),
        sa.Column('uso_memoria_mb', sa.Float(), nullable=True, comment='Uso memoria'),
        sa.Column('uso_gpu_porcentaje', sa.Float(), nullable=True, comment='Uso GPU'),
        sa.Column('memoria_gpu_mb', sa.Float(), nullable=True, comment='Memoria GPU'),
        sa.Column('metadatos', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='Metadatos'),
        sa.Column('detalles_error', sa.Text(), nullable=True, comment='Detalles error'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('metrica_id'),
        sa.ForeignKeyConstraint(['id_sesion_metrica'], ['sesiones_metricas.session_id'], )
    )
    
    # ### Crear tabla metricas_calidad ###
    op.create_table('metricas_calidad',
        sa.Column('metrica_id', postgresql.UUID(as_uuid=True), nullable=False, comment='ID único métrica calidad'),
        sa.Column('id_sesion_metrica', postgresql.UUID(as_uuid=True), nullable=False, comment='ID sesión'),
        sa.Column('puntuacion_wer', sa.Float(), nullable=True, comment='Word Error Rate'),
        sa.Column('confianza_promedio', sa.Float(), nullable=True, comment='Confianza promedio ASR'),
        sa.Column('palabras_por_minuto', sa.Float(), nullable=True, comment='Velocidad habla'),
        sa.Column('puntuacion_der', sa.Float(), nullable=True, comment='Diarization Error Rate'),
        sa.Column('precision_separacion_hablantes', sa.Float(), nullable=True, comment='Precisión separación'),
        sa.Column('tasa_validez_json', sa.Float(), nullable=True, comment='Validez JSON LLM'),
        sa.Column('precision_terminos_medicos', sa.Float(), nullable=True, comment='Precisión términos'),
        sa.Column('puntuacion_relevancia_investigacion', sa.Float(), nullable=True, comment='Relevancia research'),
        sa.Column('completitud_contenido', sa.Float(), nullable=True, comment='Completitud contenido'),
        sa.Column('consistencia_idioma', sa.Float(), nullable=True, comment='Consistencia idioma'),
        sa.Column('nivel_academico_puntuacion', sa.Float(), nullable=True, comment='Nivel académico'),
        sa.Column('cantidad_terminos_extraidos', sa.Float(), nullable=True, comment='Términos extraídos'),
        sa.Column('precision_definiciones', sa.Float(), nullable=True, comment='Precisión definiciones'),
        sa.Column('cobertura_glosario', sa.Float(), nullable=True, comment='Cobertura glosario'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('metrica_id'),
        sa.ForeignKeyConstraint(['id_sesion_metrica'], ['sesiones_metricas.session_id'], )
    )
    
    # ### Crear tabla metricas_sistema ###
    op.create_table('metricas_sistema',
        sa.Column('metrica_id', postgresql.UUID(as_uuid=True), nullable=False, comment='ID métrica sistema'),
        sa.Column('id_sesion_metrica', postgresql.UUID(as_uuid=True), nullable=True, comment='ID sesión opcional'),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, comment='Timestamp métrica'),
        sa.Column('nombre_metrica', sa.String(length=100), nullable=False, comment='Nombre métrica'),
        sa.Column('categoria_metrica', sa.String(length=50), nullable=False, comment='Categoría métrica'),
        sa.Column('valor', sa.Float(), nullable=False, comment='Valor métrica'),
        sa.Column('unidad', sa.String(length=20), nullable=False, comment='Unidad medida'),
        sa.Column('nodo_servidor', sa.String(length=50), nullable=True, comment='Nodo servidor'),
        sa.Column('componente', sa.String(length=100), nullable=True, comment='Componente'),
        sa.Column('etiquetas', postgresql.JSON(astext_type=sa.Text()), nullable=True, comment='Etiquetas'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('metrica_id'),
        sa.ForeignKeyConstraint(['id_sesion_metrica'], ['sesiones_metricas.session_id'], )
    )
    
    # ### Crear índices para optimización ###
    op.create_index(op.f('ix_sesiones_metricas_tiempo_inicio'), 'sesiones_metricas', ['tiempo_inicio'], unique=False)
    op.create_index(op.f('ix_sesiones_metricas_estado'), 'sesiones_metricas', ['estado'], unique=False)
    op.create_index(op.f('ix_sesiones_metricas_tipo_sesion'), 'sesiones_metricas', ['tipo_sesion'], unique=False)
    
    op.create_index(op.f('ix_metricas_procesamiento_id_sesion'), 'metricas_procesamiento', ['id_sesion_metrica'], unique=False)
    op.create_index(op.f('ix_metricas_procesamiento_tipo'), 'metricas_procesamiento', ['tipo_metrica'], unique=False)
    op.create_index(op.f('ix_metricas_procesamiento_tiempo'), 'metricas_procesamiento', ['tiempo_inicio'], unique=False)
    
    op.create_index(op.f('ix_metricas_calidad_id_sesion'), 'metricas_calidad', ['id_sesion_metrica'], unique=False)
    op.create_index(op.f('ix_metricas_calidad_created'), 'metricas_calidad', ['created_at'], unique=False)
    
    op.create_index(op.f('ix_metricas_sistema_timestamp'), 'metricas_sistema', ['timestamp'], unique=False)
    op.create_index(op.f('ix_metricas_sistema_categoria'), 'metricas_sistema', ['categoria_metrica'], unique=False)
    op.create_index(op.f('ix_metricas_sistema_nombre'), 'metricas_sistema', ['nombre_metrica'], unique=False)


def downgrade() -> None:
    # ### Eliminar índices ###
    op.drop_index(op.f('ix_metricas_sistema_nombre'), table_name='metricas_sistema')
    op.drop_index(op.f('ix_metricas_sistema_categoria'), table_name='metricas_sistema')
    op.drop_index(op.f('ix_metricas_sistema_timestamp'), table_name='metricas_sistema')
    op.drop_index(op.f('ix_metricas_calidad_created'), table_name='metricas_calidad')
    op.drop_index(op.f('ix_metricas_calidad_id_sesion'), table_name='metricas_calidad')
    op.drop_index(op.f('ix_metricas_procesamiento_tiempo'), table_name='metricas_procesamiento')
    op.drop_index(op.f('ix_metricas_procesamiento_tipo'), table_name='metricas_procesamiento')
    op.drop_index(op.f('ix_metricas_procesamiento_id_sesion'), table_name='metricas_procesamiento')
    op.drop_index(op.f('ix_sesiones_metricas_tipo_sesion'), table_name='sesiones_metricas')
    op.drop_index(op.f('ix_sesiones_metricas_estado'), table_name='sesiones_metricas')
    op.drop_index(op.f('ix_sesiones_metricas_tiempo_inicio'), table_name='sesiones_metricas')
    
    # ### Eliminar tablas ###
    op.drop_table('metricas_sistema')
    op.drop_table('metricas_calidad')
    op.drop_table('metricas_procesamiento')
    op.drop_table('sesiones_metricas')
