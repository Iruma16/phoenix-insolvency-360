"""add_soft_delete_to_documents

Revision ID: 20260112_1830_soft_delete
Revises: 20260112_1800_create_duplicate_pairs
Create Date: 2026-01-12 18:30:00

CRÍTICO: Añade campos de soft-delete a documents.
NO BORRADO FÍSICO → legal defensible.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260112_1830_soft_delete'
down_revision = 'f9a8b7c6d5e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Añade campos de soft-delete a documents."""
    
    # Soft-delete timestamp
    op.add_column(
        'documents',
        sa.Column(
            'deleted_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Timestamp de soft-delete (null = activo)'
        )
    )
    op.create_index('ix_documents_deleted_at', 'documents', ['deleted_at'])
    
    # Quién lo borró
    op.add_column(
        'documents',
        sa.Column(
            'deleted_by',
            sa.String(100),
            nullable=True,
            comment='Usuario/email que excluyó el documento'
        )
    )
    
    # Por qué lo borró
    op.add_column(
        'documents',
        sa.Column(
            'deletion_reason',
            sa.String(500),
            nullable=True,
            comment='Razón de la exclusión (auditoría legal)'
        )
    )
    
    # Snapshot para rollback
    op.add_column(
        'documents',
        sa.Column(
            'snapshot_before_deletion',
            sa.JSON(),
            nullable=True,
            comment='Snapshot del Document antes de soft-delete (para recuperación/auditoría)'
        )
    )


def downgrade() -> None:
    """Elimina campos de soft-delete."""
    
    op.drop_index('ix_documents_deleted_at', 'documents')
    op.drop_column('documents', 'deleted_at')
    op.drop_column('documents', 'deleted_by')
    op.drop_column('documents', 'deletion_reason')
    op.drop_column('documents', 'snapshot_before_deletion')
