"""add_invalidation_to_duplicate_pairs

Revision ID: 20260112_1900_invalidation
Revises: 20260112_1830_soft_delete
Create Date: 2026-01-12 19:00:00

CRÍTICO: Añade campos de invalidación en cascada a duplicate_pairs.
Cuando se elimina un documento, los pares relacionados se invalidan automáticamente.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20260112_1900_invalidation'
down_revision = '20260112_1830_soft_delete'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Añade campos de invalidación en cascada."""
    
    # Campo: cuándo se invalidó
    op.add_column(
        'duplicate_pairs',
        sa.Column(
            'invalidated_at',
            sa.DateTime(),
            nullable=True,
            comment='Cuándo se invalidó este par (si aplica)'
        )
    )
    
    # Índice para filtrar pares invalidados rápidamente
    op.create_index(
        'ix_duplicate_pairs_invalidated_at',
        'duplicate_pairs',
        ['invalidated_at']
    )
    
    # Campo: por qué se invalidó
    op.add_column(
        'duplicate_pairs',
        sa.Column(
            'invalidation_reason',
            sa.Text(),
            nullable=True,
            comment='Por qué se invalidó (ej: documento excluido)'
        )
    )


def downgrade() -> None:
    """Elimina campos de invalidación."""
    
    op.drop_column('duplicate_pairs', 'invalidation_reason')
    op.drop_index('ix_duplicate_pairs_invalidated_at', 'duplicate_pairs')
    op.drop_column('duplicate_pairs', 'invalidated_at')
