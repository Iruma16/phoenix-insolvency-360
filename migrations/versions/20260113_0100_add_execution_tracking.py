"""add_execution_tracking_for_legal_reproducibility

Revision ID: 20260113_0100_tracking
Revises: 20260112_2100_timeline
Create Date: 2026-01-13 01:00:00.000000

CRÍTICO LEGAL: Agregar trazabilidad de ejecución

Cambios:
1. suspicious_patterns.pipeline_run_id - ID del pipeline que detectó el patrón
2. timeline_events.analysis_run_id - ID del análisis que generó el evento  
3. Tabla analysis_executions - Registro completo de cada ejecución

Permite:
- Reproducir auditorías temporales
- Explicar divergencias entre ejecuciones
- Defensa legal sólida
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260113_0100_tracking'
down_revision = '20260112_2100_timeline'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================
    # 1. CREAR TABLA analysis_executions
    # =========================================================
    op.create_table(
        'analysis_executions',
        
        # Identificación
        sa.Column('run_id', sa.String(length=100), nullable=False, comment='UUID único de ejecución'),
        sa.Column('case_id', sa.String(length=100), nullable=False, comment='ID del caso'),
        
        # Timestamps
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False, comment='Inicio análisis (UTC)'),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True, comment='Fin análisis (UTC)'),
        
        # Versionado
        sa.Column('model_versions', sa.JSON(), nullable=False, comment='Versiones de modelos/detectores'),
        
        # Documentos
        sa.Column('document_ids', sa.JSON(), nullable=False, comment='IDs de documentos analizados'),
        sa.Column('document_count', sa.Integer(), nullable=False, comment='Total de documentos'),
        
        # Estado
        sa.Column('status', sa.String(length=20), nullable=False, comment='running/completed/failed'),
        sa.Column('result_summary', sa.JSON(), nullable=True, comment='Resumen de resultados'),
        
        # Errores
        sa.Column('error_message', sa.Text(), nullable=True, comment='Mensaje de error'),
        sa.Column('error_traceback', sa.Text(), nullable=True, comment='Traceback completo'),
        
        # Metadata
        sa.Column('triggered_by', sa.String(length=100), nullable=True, comment='Usuario/sistema'),
        sa.Column('trigger_reason', sa.String(length=200), nullable=True, comment='Razón del análisis'),
        sa.Column('execution_time_seconds', sa.Float(), nullable=True, comment='Tiempo en segundos'),
        sa.Column('extra_metadata', sa.JSON(), nullable=True, comment='Metadata adicional'),
        
        sa.PrimaryKeyConstraint('run_id')
    )
    
    # Índices para analysis_executions
    op.create_index('ix_analysis_executions_case_id', 'analysis_executions', ['case_id'])
    op.create_index('ix_analysis_executions_started_at', 'analysis_executions', ['started_at'])
    op.create_index('ix_analysis_executions_status', 'analysis_executions', ['status'])
    
    # =========================================================
    # 2. AGREGAR pipeline_run_id a suspicious_patterns
    # =========================================================
    op.add_column(
        'suspicious_patterns',
        sa.Column(
            'pipeline_run_id',
            sa.String(length=100),
            nullable=True,  # Inicialmente nullable para datos existentes
            comment='ID de ejecución que detectó este patrón'
        )
    )
    
    # Índice para pipeline_run_id
    op.create_index(
        'ix_suspicious_patterns_pipeline_run_id',
        'suspicious_patterns',
        ['pipeline_run_id']
    )
    
    # =========================================================
    # 3. AGREGAR analysis_run_id a timeline_events
    # =========================================================
    op.add_column(
        'timeline_events',
        sa.Column(
            'analysis_run_id',
            sa.String(length=100),
            nullable=True,  # Inicialmente nullable para datos existentes
            comment='ID de análisis que generó este evento'
        )
    )
    
    # Índice para analysis_run_id
    op.create_index(
        'ix_timeline_events_analysis_run_id',
        'timeline_events',
        ['analysis_run_id']
    )
    
    # =========================================================
    # 4. MIGRAR DATOS EXISTENTES (si existen)
    # =========================================================
    # Para datos existentes, crear un run_id "legacy" que agrupe todo
    # Esto permite que datos antiguos sigan siendo queryables
    
    # Nota: En producción real, ejecutar script que:
    # 1. Crea un AnalysisExecution "legacy" para el caso
    # 2. Actualiza todos los patrones/eventos con ese run_id
    # 3. Luego hace NOT NULL los campos


def downgrade() -> None:
    # =========================================================
    # ELIMINAR CAMPOS AGREGADOS
    # =========================================================
    
    # Eliminar índice y columna de timeline_events
    op.drop_index('ix_timeline_events_analysis_run_id', table_name='timeline_events')
    op.drop_column('timeline_events', 'analysis_run_id')
    
    # Eliminar índice y columna de suspicious_patterns
    op.drop_index('ix_suspicious_patterns_pipeline_run_id', table_name='suspicious_patterns')
    op.drop_column('suspicious_patterns', 'pipeline_run_id')
    
    # =========================================================
    # ELIMINAR TABLA analysis_executions
    # =========================================================
    op.drop_index('ix_analysis_executions_status', table_name='analysis_executions')
    op.drop_index('ix_analysis_executions_started_at', table_name='analysis_executions')
    op.drop_index('ix_analysis_executions_case_id', table_name='analysis_executions')
    op.drop_table('analysis_executions')
