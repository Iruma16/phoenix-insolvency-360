"""create_timeline_events_table_with_pagination

Revision ID: t1m3l1n3ev3n
Revises: a1b2c3d4e5f6
Create Date: 2026-01-12 21:00:00.000000

Tabla de eventos del timeline con paginación optimizada:
- Índices compuestos para queries eficientes
- Filtros por tipo, severidad, categoría, fecha
- Búsqueda en descripción
- Trazabilidad completa con evidencias
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260112_2100_timeline'
down_revision = '20260112_2000_suspicious'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Crear tabla timeline_events
    op.create_table(
        'timeline_events',
        
        # =========================================================
        # IDENTIFICACIÓN
        # =========================================================
        sa.Column('event_id', sa.String(length=100), nullable=False, comment='ID único del evento (UUID)'),
        sa.Column('case_id', sa.String(length=100), nullable=False, comment='ID del caso'),
        
        # =========================================================
        # DATOS DEL EVENTO
        # =========================================================
        sa.Column('date', sa.DateTime(timezone=True), nullable=False, comment='Fecha del evento (UTC)'),
        sa.Column('event_type', sa.String(length=50), nullable=False, comment='Tipo: embargo, factura_vencida, etc.'),
        sa.Column('category', sa.String(length=50), nullable=True, comment='Categoría: financiero, legal, operativo'),
        sa.Column('description', sa.Text(), nullable=False, comment='Descripción del evento'),
        sa.Column('title', sa.String(length=200), nullable=True, comment='Título corto (opcional)'),
        sa.Column('amount', sa.Float(), nullable=True, comment='Importe en euros (si aplica)'),
        sa.Column('severity', sa.String(length=20), nullable=True, comment='Severidad: critical/high/medium/low'),
        
        # =========================================================
        # EVIDENCIA Y TRAZABILIDAD
        # =========================================================
        sa.Column('document_id', sa.String(length=100), nullable=True, comment='ID del documento fuente'),
        sa.Column('chunk_id', sa.String(length=100), nullable=True, comment='ID del chunk fuente'),
        sa.Column('page', sa.Integer(), nullable=True, comment='Número de página'),
        sa.Column('evidence', sa.JSON(), nullable=True, comment='Evidencia probatoria completa (JSON)'),
        
        # =========================================================
        # METADATA Y CALIDAD
        # =========================================================
        sa.Column('extraction_method', sa.String(length=50), nullable=True, comment='Método: pdf_text, excel_cell, llm'),
        sa.Column('extraction_confidence', sa.Float(), nullable=True, comment='Confianza 0.0-1.0'),
        sa.Column('source_reliability', sa.String(length=20), nullable=True, comment='Fiabilidad: official/reliable/uncertain'),
        sa.Column('extra_metadata', sa.JSON(), nullable=True, comment='Metadata adicional'),
        
        # =========================================================
        # AUDITORÍA TEMPORAL
        # =========================================================
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='Fecha creación en BD (UTC)'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='Fecha última actualización (UTC)'),
        
        sa.PrimaryKeyConstraint('event_id')
    )
    
    # =========================================================
    # ÍNDICES SIMPLES (para filtros individuales)
    # =========================================================
    op.create_index('ix_timeline_events_case_id', 'timeline_events', ['case_id'])
    op.create_index('ix_timeline_events_date', 'timeline_events', ['date'])
    op.create_index('ix_timeline_events_event_type', 'timeline_events', ['event_type'])
    op.create_index('ix_timeline_events_category', 'timeline_events', ['category'])
    op.create_index('ix_timeline_events_severity', 'timeline_events', ['severity'])
    op.create_index('ix_timeline_events_document_id', 'timeline_events', ['document_id'])
    
    # =========================================================
    # ÍNDICES COMPUESTOS (para queries paginadas optimizadas)
    # =========================================================
    # Índice principal para paginación ordenada por fecha DESC
    op.create_index(
        'ix_timeline_case_date_desc',
        'timeline_events',
        ['case_id', sa.text('date DESC')],
        postgresql_using='btree'
    )
    
    # Índice para filtro por tipo + fecha
    op.create_index(
        'ix_timeline_case_type_date',
        'timeline_events',
        ['case_id', 'event_type', 'date']
    )
    
    # Índice para filtro por severidad + fecha
    op.create_index(
        'ix_timeline_case_severity_date',
        'timeline_events',
        ['case_id', 'severity', 'date']
    )
    
    # Índice para filtro por categoría + fecha
    op.create_index(
        'ix_timeline_case_category_date',
        'timeline_events',
        ['case_id', 'category', 'date']
    )


def downgrade() -> None:
    # =========================================================
    # ELIMINAR ÍNDICES COMPUESTOS
    # =========================================================
    op.drop_index('ix_timeline_case_category_date', table_name='timeline_events')
    op.drop_index('ix_timeline_case_severity_date', table_name='timeline_events')
    op.drop_index('ix_timeline_case_type_date', table_name='timeline_events')
    op.drop_index('ix_timeline_case_date_desc', table_name='timeline_events')
    
    # =========================================================
    # ELIMINAR ÍNDICES SIMPLES
    # =========================================================
    op.drop_index('ix_timeline_events_document_id', table_name='timeline_events')
    op.drop_index('ix_timeline_events_severity', table_name='timeline_events')
    op.drop_index('ix_timeline_events_category', table_name='timeline_events')
    op.drop_index('ix_timeline_events_event_type', table_name='timeline_events')
    op.drop_index('ix_timeline_events_date', table_name='timeline_events')
    op.drop_index('ix_timeline_events_case_id', table_name='timeline_events')
    
    # =========================================================
    # ELIMINAR TABLA
    # =========================================================
    op.drop_table('timeline_events')
