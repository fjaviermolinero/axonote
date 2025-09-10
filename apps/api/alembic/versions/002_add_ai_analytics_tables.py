"""Add AI analytics tables for Sprint 3

Revision ID: 002
Revises: 001
Create Date: 2025-09-10 15:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None

def upgrade():
    # Learning Sessions table
    op.create_table('learning_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('class_session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('class_sessions.id')),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('ended_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('duration_seconds', sa.Integer),
        sa.Column('session_type', sa.String(50), nullable=False),
        sa.Column('effectiveness_score', sa.Float),
        sa.Column('engagement_score', sa.Float),
        sa.Column('attention_score', sa.Float),
        sa.Column('metadata', postgresql.JSONB, default={}),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now())
    )
    
    # User Interactions table
    op.create_table('user_interactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('learning_session_id', postgresql.UUID(as_uuid=True), 
                 sa.ForeignKey('learning_sessions.id'), nullable=False),
        sa.Column('interaction_type', sa.String(50), nullable=False),
        sa.Column('element_type', sa.String(50)),
        sa.Column('element_id', sa.String(100)),
        sa.Column('timestamp_offset', sa.Integer, nullable=False),
        sa.Column('duration_seconds', sa.Integer),
        sa.Column('properties', postgresql.JSONB, default={}),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now())
    )
    
    # Knowledge Concepts table
    op.create_table('knowledge_concepts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(200), nullable=False, unique=True),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('difficulty_base', sa.Float, nullable=False, default=0.5),
        sa.Column('medical_specialty', sa.String(100)),
        sa.Column('prerequisites', postgresql.JSONB, default=[]),
        sa.Column('learning_objectives', postgresql.ARRAY(sa.Text)),
        sa.Column('metadata', postgresql.JSONB, default={}),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now())
    )
    
    # Concept Mastery table
    op.create_table('concept_mastery',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('concept_id', postgresql.UUID(as_uuid=True), 
                 sa.ForeignKey('knowledge_concepts.id'), nullable=False),
        sa.Column('mastery_level', sa.Float, nullable=False, default=0.0),
        sa.Column('confidence_score', sa.Float, nullable=False, default=0.0),
        sa.Column('last_studied_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('study_count', sa.Integer, default=0),
        sa.Column('correct_responses', sa.Integer, default=0),
        sa.Column('total_responses', sa.Integer, default=0),
        sa.Column('retention_probability', sa.Float),
        sa.Column('next_review_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('forgetting_rate', sa.Float, default=0.3),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'concept_id')
    )
    
    # Study Patterns table
    op.create_table('study_patterns',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('pattern_type', sa.String(50), nullable=False),
        sa.Column('pattern_name', sa.String(100), nullable=False),
        sa.Column('pattern_data', postgresql.JSONB, nullable=False),
        sa.Column('confidence_score', sa.Float, nullable=False),
        sa.Column('impact_score', sa.Float),
        sa.Column('discovered_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column('last_observed_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now())
    )
    
    # Performance Metrics table
    op.create_table('performance_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('metric_type', sa.String(50), nullable=False),
        sa.Column('time_period_start', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('time_period_end', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('metrics', postgresql.JSONB, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now())
    )
    
    # AI Recommendations table
    op.create_table('ai_recommendations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('recommendation_type', sa.String(50), nullable=False),
        sa.Column('content_id', postgresql.UUID(as_uuid=True)),
        sa.Column('priority_score', sa.Float, nullable=False),
        sa.Column('reasoning', sa.Text),
        sa.Column('recommendation_data', postgresql.JSONB, nullable=False),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now())
    )
    
    # Voice Profiles table for voice cloning
    op.create_table('voice_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('voice_id', sa.String(100), nullable=False, unique=True),
        sa.Column('professor_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('voice_name', sa.String(100), nullable=False),
        sa.Column('language', sa.String(10), nullable=False),
        sa.Column('speaker_embedding', postgresql.JSONB, nullable=False),
        sa.Column('model_path', sa.String(500)),
        sa.Column('quality_metrics', postgresql.JSONB, default={}),
        sa.Column('capabilities', postgresql.JSONB, default={}),
        sa.Column('training_data', postgresql.JSONB, default={}),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now())
    )
    
    # Conversations table for conversational AI
    op.create_table('conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('topic', sa.String(200), nullable=False),
        sa.Column('conversation_type', sa.String(50), nullable=False),
        sa.Column('professor_voice_id', sa.String(100), sa.ForeignKey('voice_profiles.voice_id')),
        sa.Column('conversation_state', postgresql.JSONB, default={}),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column('ended_at', sa.TIMESTAMP(timezone=True)),
        sa.Column('metadata', postgresql.JSONB, default={})
    )
    
    # Create indexes for performance
    op.create_index('idx_learning_sessions_user_started', 'learning_sessions', 
                   ['user_id', 'started_at'])
    op.create_index('idx_user_interactions_session', 'user_interactions', 
                   ['learning_session_id'])
    op.create_index('idx_concept_mastery_user', 'concept_mastery', ['user_id'])
    op.create_index('idx_concept_mastery_next_review', 'concept_mastery', 
                   ['next_review_at'], postgresql_where=sa.text('next_review_at IS NOT NULL'))
    op.create_index('idx_study_patterns_user', 'study_patterns', ['user_id'])
    op.create_index('idx_ai_recommendations_user_status', 'ai_recommendations', 
                   ['user_id', 'status'])
    op.create_index('idx_conversations_user', 'conversations', ['user_id'])

def downgrade():
    op.drop_index('idx_conversations_user')
    op.drop_index('idx_ai_recommendations_user_status')
    op.drop_index('idx_study_patterns_user')
    op.drop_index('idx_concept_mastery_next_review')
    op.drop_index('idx_concept_mastery_user')
    op.drop_index('idx_user_interactions_session')
    op.drop_index('idx_learning_sessions_user_started')
    
    op.drop_table('conversations')
    op.drop_table('voice_profiles')
    op.drop_table('ai_recommendations')
    op.drop_table('performance_metrics')
    op.drop_table('study_patterns')
    op.drop_table('concept_mastery')
    op.drop_table('knowledge_concepts')
    op.drop_table('user_interactions')
    op.drop_table('learning_sessions')
