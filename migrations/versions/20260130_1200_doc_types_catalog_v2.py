"""doc_types_catalog_v2

Revision ID: 20260130_1200_doc_types_v2
Revises: 20260113_0100_tracking
Create Date: 2026-01-30 12:00:00

OBJETIVO (Estrategia B):
- Migrar `documents.doc_type` al catálogo abogado-friendly (DOC_TYPES v2).
- Añadir trazabilidad de clasificación: doc_type_confidence + doc_type_source.

NOTA:
- Se elimina el CHECK constraint legacy, se hace backfill, y se crea el CHECK nuevo.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260130_1200_doc_types_v2"
down_revision = "20260113_0100_tracking"
branch_labels = None
depends_on = None


_DOC_TYPE_CHECK_V2 = (
    "doc_type IN ("
    "'ESCRITURA_CONSTITUCION',"
    "'PODERES_REPRESENTACION',"
    "'CONTRATO_ARRENDAMIENTO',"
    "'CONTRATO_FINANCIACION',"
    "'GARANTIAS',"
    "'COMUNICACION_ACREEDOR',"
    "'RECLAMACION_JUDICIAL',"
    "'RESOLUCION_JUDICIAL',"
    "'EMBARGO',"
    "'CONCURSAL',"
    "'AEAT',"
    "'TGSS',"
    "'MODELOS_TRIBUTARIOS',"
    "'APLAZAMIENTO_FRACCIONAMIENTO',"
    "'PROVIDENCIA_APREMIO',"
    "'FACTURA',"
    "'EXTRACTO_BANCARIO',"
    "'CUENTA_BANCARIA',"
    "'BALANCE',"
    "'PYG',"
    "'MAYOR_CONTABLE',"
    "'NOMINAS_SEGUROS_SOCIALES',"
    "'INMUEBLE',"
    "'VEHICULO',"
    "'MAQUINARIA_EQUIPO',"
    "'TASACION',"
    "'CORREO',"
    "'OTRO'"
    ")"
)


_DOC_TYPE_CHECK_LEGACY = (
    "doc_type IN ("
    "'balance','pyg','mayor','sumas_saldos','extracto_bancario',"
    "'acta','acuerdo_societario','poder',"
    "'email_direccion','email_banco','email_asesoria',"
    "'contrato','venta_activo','prestamo','nomina'"
    ")"
)


def upgrade() -> None:
    # 1) Quitar constraint legacy + añadir columnas auxiliares
    with op.batch_alter_table("documents", schema=None) as batch_op:
        # Columnas de trazabilidad de clasificación
        batch_op.add_column(
            sa.Column(
                "doc_type_confidence",
                sa.Float(),
                nullable=True,
                comment="Confianza de clasificación doc_type (0-1). NULL si no aplica.",
            )
        )
        batch_op.add_column(
            sa.Column(
                "doc_type_source",
                sa.String(length=20),
                nullable=True,
                comment="Origen doc_type: inferred|mapped|manual",
            )
        )

        # Quitar constraint viejo para permitir backfill a valores nuevos
        batch_op.drop_constraint("ck_documents_doc_type", type_="check")

    # 2) Backfill legacy → v2 (conservador)
    op.execute(
        sa.text(
            """
            UPDATE documents
            SET
              doc_type =
                CASE doc_type
                  WHEN 'balance' THEN 'BALANCE'
                  WHEN 'pyg' THEN 'PYG'
                  WHEN 'mayor' THEN 'MAYOR_CONTABLE'
                  WHEN 'sumas_saldos' THEN 'MAYOR_CONTABLE'
                  WHEN 'extracto_bancario' THEN 'EXTRACTO_BANCARIO'
                  WHEN 'poder' THEN 'PODERES_REPRESENTACION'
                  WHEN 'prestamo' THEN 'CONTRATO_FINANCIACION'
                  WHEN 'nomina' THEN 'NOMINAS_SEGUROS_SOCIALES'
                  WHEN 'email_direccion' THEN 'CORREO'
                  WHEN 'email_banco' THEN 'CORREO'
                  WHEN 'email_asesoria' THEN 'CORREO'
                  WHEN 'acta' THEN 'OTRO'
                  WHEN 'acuerdo_societario' THEN 'OTRO'
                  WHEN 'contrato' THEN 'OTRO'
                  WHEN 'venta_activo' THEN 'OTRO'
                  ELSE 'OTRO'
                END,
              doc_type_source = 'mapped',
              doc_type_confidence =
                CASE doc_type
                  WHEN 'balance' THEN 1.0
                  WHEN 'pyg' THEN 1.0
                  WHEN 'mayor' THEN 1.0
                  WHEN 'sumas_saldos' THEN 1.0
                  WHEN 'extracto_bancario' THEN 1.0
                  WHEN 'poder' THEN 1.0
                  WHEN 'prestamo' THEN 1.0
                  WHEN 'nomina' THEN 1.0
                  WHEN 'email_direccion' THEN 1.0
                  WHEN 'email_banco' THEN 1.0
                  WHEN 'email_asesoria' THEN 1.0
                  ELSE 0.0
                END
            """
        )
    )

    # 3) Crear constraint nuevo (catálogo abogado-friendly)
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.create_check_constraint("ck_documents_doc_type", _DOC_TYPE_CHECK_V2)


def downgrade() -> None:
    # Downgrade conservador: convertir a tipos legacy y restaurar constraint
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_constraint("ck_documents_doc_type", type_="check")

    # Mapear v2 → legacy (fallback a 'contrato')
    op.execute(
        sa.text(
            """
            UPDATE documents
            SET
              doc_type =
                CASE doc_type
                  WHEN 'BALANCE' THEN 'balance'
                  WHEN 'PYG' THEN 'pyg'
                  WHEN 'MAYOR_CONTABLE' THEN 'mayor'
                  WHEN 'EXTRACTO_BANCARIO' THEN 'extracto_bancario'
                  WHEN 'PODERES_REPRESENTACION' THEN 'poder'
                  WHEN 'CONTRATO_FINANCIACION' THEN 'prestamo'
                  WHEN 'NOMINAS_SEGUROS_SOCIALES' THEN 'nomina'
                  WHEN 'CORREO' THEN 'email_direccion'
                  ELSE 'contrato'
                END
            """
        )
    )

    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.create_check_constraint("ck_documents_doc_type", _DOC_TYPE_CHECK_LEGACY)
        batch_op.drop_column("doc_type_source")
        batch_op.drop_column("doc_type_confidence")

