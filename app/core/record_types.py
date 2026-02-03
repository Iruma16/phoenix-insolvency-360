"""
Catálogo canónico de record_type/entity para la BD central del caso.

Objetivo:
- Una sola fuente de verdad para CAPA 2/3/4/5 (hechos, evidencia, auditoría, snapshots).
- Mantener compatibilidad con la UI/API existente del Cuadro de situación (entity: INVOICE/CREDIT/...).
"""

from __future__ import annotations

from typing import Final

# record_type canónico (persistido en tablas CAPA 3/4/5)
RECORD_INVOICE: Final[str] = "invoice"
RECORD_LOAN: Final[str] = "loan"
RECORD_ASSET: Final[str] = "asset"
RECORD_PUBLIC_DEBT: Final[str] = "public_debt"
RECORD_COURT_CLAIM: Final[str] = "court_claim"
RECORD_FORM_FIELD: Final[str] = "form_field"
RECORD_OTHER: Final[str] = "other"

CANONICAL_RECORD_TYPES: Final[set[str]] = {
    RECORD_INVOICE,
    RECORD_LOAN,
    RECORD_ASSET,
    RECORD_PUBLIC_DEBT,
    RECORD_COURT_CLAIM,
    RECORD_FORM_FIELD,
    RECORD_OTHER,
}

# entity legacy (Cuadro de situación / endpoints)
ENTITY_INVOICE: Final[str] = "INVOICE"
ENTITY_CREDIT: Final[str] = "CREDIT"
ENTITY_ASSET: Final[str] = "ASSET"
ENTITY_PUBLIC_DEBT: Final[str] = "PUBLIC_DEBT"
ENTITY_COURT: Final[str] = "COURT"

ENTITY_ALLOWED: Final[set[str]] = {
    ENTITY_INVOICE,
    ENTITY_CREDIT,
    ENTITY_ASSET,
    ENTITY_PUBLIC_DEBT,
    ENTITY_COURT,
}

ENTITY_TO_RECORD_TYPE: Final[dict[str, str]] = {
    ENTITY_INVOICE: RECORD_INVOICE,
    ENTITY_CREDIT: RECORD_LOAN,
    ENTITY_ASSET: RECORD_ASSET,
    ENTITY_PUBLIC_DEBT: RECORD_PUBLIC_DEBT,
    ENTITY_COURT: RECORD_COURT_CLAIM,
}

RECORD_TYPE_TO_ENTITY: Final[dict[str, str]] = {v: k for k, v in ENTITY_TO_RECORD_TYPE.items()}


def record_type_from_entity(entity: str) -> str:
    return ENTITY_TO_RECORD_TYPE.get((entity or "").strip().upper(), RECORD_OTHER)


def entity_from_record_type(record_type: str) -> str:
    rt = (record_type or "").strip().lower()
    return RECORD_TYPE_TO_ENTITY.get(rt, "OTHER")
