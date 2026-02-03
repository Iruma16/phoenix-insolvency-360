"""create_suspicious_patterns_table

Revision ID: a1b2c3d4e5f6
Revises: g2h3i4j5k6l7
Create Date: 2026-01-12 20:00:00.000000

Contrato formal de patrones sospechosos:
- Detector auditable con versión
- Criterios técnicos explícitos
- Base legal referenciada
- Trazabilidad completa
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260112_2000_suspicious'
down_revision = '20260112_1900_invalidation'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Crear tabla suspicious_patterns
    op.create_table(
        'suspicious_patterns',
        sa.Column('pattern_id', sa.String(length=100), nullable=False, comment='ID único del patrón'),
        sa.Column('case_id', sa.String(length=100), nullable=False, comment='ID del caso'),
        sa.Column('pattern_type', sa.String(length=100), nullable=False, comment='Tipo de patrón'),
        
        # Detector (auditable)
        sa.Column('detector_id', sa.String(length=100), nullable=False, comment='ID del detector'),
        sa.Column('detector_version', sa.String(length=20), nullable=False, comment='Versión del detector'),
        sa.Column('detector_criteria', sa.JSON(), nullable=False, comment='Criterios técnicos usados'),
        sa.Column('legal_basis', sa.Text(), nullable=False, comment='Base legal que justifica'),
        
        # Clasificación
        sa.Column('severity', sa.String(length=20), nullable=False, comment='critical/high/medium/low'),
        sa.Column('severity_score', sa.Float(), nullable=False, comment='Score 0-100'),
        sa.Column('confidence', sa.Float(), nullable=False, comment='Confianza 0.0-1.0'),
        sa.Column('category', sa.String(length=100), nullable=False, comment='Categoría del patrón'),
        
        # Explicación
        sa.Column('explanation', sa.Text(), nullable=False, comment='Explicación detallada'),
        sa.Column('recommendation', sa.Text(), nullable=True, comment='Recomendación'),
        
        # Evidencias
        sa.Column('evidence_ids', sa.JSON(), nullable=False, comment='IDs de evidencias'),
        
        # Auditoría
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False, comment='Fecha detección UTC'),
        
        # Metadata adicional (renombrado para evitar colisión con SQLAlchemy)
        sa.Column('extra_metadata', sa.JSON(), nullable=True, comment='Metadata específica'),
        
        sa.PrimaryKeyConstraint('pattern_id')
    )
    
    # Índices para búsquedas eficientes
    op.create_index('ix_suspicious_patterns_case_id', 'suspicious_patterns', ['case_id'])
    op.create_index('ix_suspicious_patterns_pattern_type', 'suspicious_patterns', ['pattern_type'])
    op.create_index('ix_suspicious_patterns_detector_id', 'suspicious_patterns', ['detector_id'])
    op.create_index('ix_suspicious_patterns_severity', 'suspicious_patterns', ['severity'])
    op.create_index('ix_suspicious_patterns_category', 'suspicious_patterns', ['category'])
    op.create_index('ix_suspicious_patterns_detected_at', 'suspicious_patterns', ['detected_at'])


def downgrade() -> None:
    # Eliminar índices
    op.drop_index('ix_suspicious_patterns_detected_at', table_name='suspicious_patterns')
    op.drop_index('ix_suspicious_patterns_category', table_name='suspicious_patterns')
    op.drop_index('ix_suspicious_patterns_severity', table_name='suspicious_patterns')
    op.drop_index('ix_suspicious_patterns_detector_id', table_name='suspicious_patterns')
    op.drop_index('ix_suspicious_patterns_pattern_type', table_name='suspicious_patterns')
    op.drop_index('ix_suspicious_patterns_case_id', table_name='suspicious_patterns')
    
    # Eliminar tabla
    op.drop_table('suspicious_patterns')
