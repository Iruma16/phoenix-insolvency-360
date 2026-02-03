"""backfill_doc_type_inference

Revision ID: 20260130_1245_doc_type_backfill
Revises: 20260130_1230_situation
Create Date: 2026-01-30 12:45:00

Backfill adicional (post-migración doc_types_v2):
- Para documentos que quedaron como OTRO por mapping legacy, inferir doc_type por
  señales simples en filename/raw_text para que el buscador sea útil “día 1”.

Nota:
- Heurística conservadora (solo cuando hay match claro).
"""

from alembic import op
import sqlalchemy as sa


revision = "20260130_1245_doc_type_backfill"
down_revision = "20260130_1230_situation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    def _exec(sql: str) -> None:
        bind.execute(sa.text(sql))

    # Normalizar a minúsculas para matching
    # SQLite: usar || para concatenación y COALESCE para raw_text
    base = "lower(documents.filename || ' ' || coalesce(documents.raw_text,''))"

    # AEAT / modelos tributarios
    _exec(
        f"""
        UPDATE documents
        SET doc_type='AEAT', doc_type_source='inferred', doc_type_confidence=0.85
        WHERE doc_type='OTRO'
          AND ({base} LIKE '% aeat%' OR {base} LIKE '%agencia tributaria%' OR {base} LIKE '%hacienda%')
        """
    )
    _exec(
        f"""
        UPDATE documents
        SET doc_type='MODELOS_TRIBUTARIOS', doc_type_source='inferred', doc_type_confidence=0.80
        WHERE doc_type='OTRO'
          AND ({base} LIKE '%modelo 303%' OR {base} LIKE '%modelo 111%' OR {base} LIKE '%modelo 190%'
               OR {base} LIKE '%modelo 200%' OR {base} LIKE '%modelo 390%' OR {base} LIKE '%modelo 347%')
        """
    )

    # TGSS
    _exec(
        f"""
        UPDATE documents
        SET doc_type='TGSS', doc_type_source='inferred', doc_type_confidence=0.85
        WHERE doc_type='OTRO'
          AND ({base} LIKE '% tgss%' OR {base} LIKE '%seguridad social%' OR {base} LIKE '%tesoreria general%')
        """
    )

    # Providencia apremio / aplazamiento
    _exec(
        f"""
        UPDATE documents
        SET doc_type='PROVIDENCIA_APREMIO', doc_type_source='inferred', doc_type_confidence=0.85
        WHERE doc_type='OTRO'
          AND ({base} LIKE '%providencia%' AND {base} LIKE '%apremio%')
        """
    )
    _exec(
        f"""
        UPDATE documents
        SET doc_type='APLAZAMIENTO_FRACCIONAMIENTO', doc_type_source='inferred', doc_type_confidence=0.80
        WHERE doc_type='OTRO'
          AND ({base} LIKE '%aplazamiento%' OR {base} LIKE '%fraccionamiento%')
        """
    )

    # Embargo / judicial
    _exec(
        f"""
        UPDATE documents
        SET doc_type='EMBARGO', doc_type_source='inferred', doc_type_confidence=0.80
        WHERE doc_type='OTRO'
          AND ({base} LIKE '%embargo%' OR {base} LIKE '%diligencia de embargo%')
        """
    )
    _exec(
        f"""
        UPDATE documents
        SET doc_type='RECLAMACION_JUDICIAL', doc_type_source='inferred', doc_type_confidence=0.75
        WHERE doc_type='OTRO'
          AND ({base} LIKE '%demanda%' OR {base} LIKE '%monitorio%' OR {base} LIKE '%ejecucion%')
        """
    )
    _exec(
        f"""
        UPDATE documents
        SET doc_type='RESOLUCION_JUDICIAL', doc_type_source='inferred', doc_type_confidence=0.75
        WHERE doc_type='OTRO'
          AND ({base} LIKE '%sentencia%' OR {base} LIKE '%auto%' OR {base} LIKE '%decreto%' OR {base} LIKE '%juzgado%')
        """
    )

    # Facturas / extractos (preferir extracto si hay señales claras de banco)
    _exec(
        f"""
        UPDATE documents
        SET doc_type='EXTRACTO_BANCARIO', doc_type_source='inferred', doc_type_confidence=0.75
        WHERE doc_type='OTRO'
          AND ({base} LIKE '%extracto%' OR {base} LIKE '%iban%' OR {base} LIKE '%saldo%' OR {base} LIKE '%movimientos%')
        """
    )
    _exec(
        f"""
        UPDATE documents
        SET doc_type='FACTURA', doc_type_source='inferred', doc_type_confidence=0.70
        WHERE doc_type='OTRO'
          AND ({base} LIKE '%factura%' OR {base} LIKE '%invoice%')
          AND ({base} NOT LIKE '%extracto%' AND {base} NOT LIKE '%iban%' AND {base} NOT LIKE '%saldo%')
        """
    )

    # Correos
    _exec(
        f"""
        UPDATE documents
        SET doc_type='CORREO', doc_type_source='inferred', doc_type_confidence=0.70
        WHERE doc_type='OTRO'
          AND ({base} LIKE '%.eml%' OR {base} LIKE '%.msg%' OR {base} LIKE '%from:%' OR {base} LIKE '%subject:%'
               OR {base} LIKE '%asunto:%' OR {base} LIKE '%correo%' OR {base} LIKE '%email%')
        """
    )


def downgrade() -> None:
    # Downgrade no intenta “desinferir” (sería destructivo). No-op.
    pass

