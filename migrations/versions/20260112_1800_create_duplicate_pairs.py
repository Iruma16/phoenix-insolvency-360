"""create_duplicate_pairs_table

Revision ID: f9a8b7c6d5e4
Revises: ef83ab6c54d1
Create Date: 2026-01-12 18:00:00.000000

Blindaje de detección de duplicados:
- Tabla duplicate_pairs como entidad persistente
- Lock optimista con decision_version
- Snapshot para rollback
- Metadata de similitud explicable
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f9a8b7c6d5e4'
down_revision = 'ef83ab6c54d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Crear tabla duplicate_pairs
    op.create_table(
        'duplicate_pairs',
        sa.Column('pair_id', sa.String(length=40), nullable=False, comment='Hash SHA256 del par ordenado'),
        sa.Column('case_id', sa.String(length=36), nullable=False, comment='Caso al que pertenecen'),
        sa.Column('doc_a_id', sa.String(length=36), nullable=False, comment='ID primer documento (menor)'),
        sa.Column('doc_b_id', sa.String(length=36), nullable=False, comment='ID segundo documento (mayor)'),
        
        # Metadata detección (inmutable)
        sa.Column('detected_at', sa.DateTime(), nullable=False, comment='Cuándo se detectó'),
        sa.Column('similarity', sa.Float(), nullable=False, comment='Score 0.0-1.0'),
        sa.Column('similarity_method', sa.String(length=50), nullable=False, comment='Método usado'),
        sa.Column('similarity_model', sa.String(length=100), nullable=True, comment='Modelo usado si aplica'),
        sa.Column('duplicate_type', sa.String(length=20), nullable=False, comment='exact o semantic'),
        
        # Decisión (mutable versionada)
        sa.Column('decision', sa.String(length=50), nullable=True, server_default='pending'),
        sa.Column('decision_version', sa.Integer(), nullable=False, server_default='0', comment='Lock optimista'),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('decided_by', sa.String(length=100), nullable=True),
        sa.Column('decision_reason', sa.Text(), nullable=True),
        
        # Snapshot para rollback
        sa.Column('snapshot_before_decision', sa.JSON(), nullable=True),
        
        # Soft-delete
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        
        sa.PrimaryKeyConstraint('pair_id')
    )
    
    # Índices
    op.create_index('ix_duplicate_pairs_case_id', 'duplicate_pairs', ['case_id'])
    op.create_index('ix_duplicate_pairs_doc_a_id', 'duplicate_pairs', ['doc_a_id'])
    op.create_index('ix_duplicate_pairs_doc_b_id', 'duplicate_pairs', ['doc_b_id'])
    op.create_index('ix_duplicate_pairs_decision', 'duplicate_pairs', ['decision'])


def downgrade() -> None:
    op.drop_index('ix_duplicate_pairs_decision', table_name='duplicate_pairs')
    op.drop_index('ix_duplicate_pairs_doc_b_id', table_name='duplicate_pairs')
    op.drop_index('ix_duplicate_pairs_doc_a_id', table_name='duplicate_pairs')
    op.create_index('ix_duplicate_pairs_case_id', table_name='duplicate_pairs')
    op.drop_table('duplicate_pairs')
