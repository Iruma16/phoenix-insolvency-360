"""
FASE 2.3 — Preparación: regeneración sin machacar trabajo del abogado.

Este módulo NO crea tablas ni endpoints.
Solo define:
- fingerprint estable de alertas (para detectar "mismo hecho" entre regeneraciones)
- política de merge editorial (preservar trabajo humano)

Uso previsto (FASE 4):
- persistir alertas de despacho (status, nota, marcar para informe)
- regenerar motor determinista y fusionar sin perder anotaciones
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Optional


def compute_fingerprint(*, kind: str, key_parts: list[str]) -> str:
    """
    Fingerprint estable y reproducible (sha256 truncado).

    Reglas:
    - key_parts deben estar normalizados (strings estables)
    - NO incluir timestamps
    - Ordenar cuando no importe el orden (ej. ids de evidencia)
    """
    material = kind + "|" + "|".join(key_parts)
    return hashlib.sha256(material.encode()).hexdigest()[:32]


@dataclass
class EditorialState:
    """
    Campos editoriales (trabajo del abogado) que NUNCA deben perderse al regenerar.
    (Se persistirán en FASE 4).
    """

    status: str = "pendiente"  # pendiente/revisada/descartada/para_informe
    lawyer_note: str = ""
    para_informe: bool = False
    updated_by: Optional[str] = None


def merge_regenerated_alert(
    *,
    existing: dict[str, Any],
    regenerated: dict[str, Any],
    preserve_fields: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    Merge "editorial-safe":
    - preserva campos humanos (status/nota/marcas)
    - permite actualizar evidencias/checklists/acciones/summary cuando cambia el soporte
    - marca `changed_since_last_review` cuando el fingerprint cambia o hay cambios materiales

    Nota: aquí trabajamos con dicts (API/persistencia futura).
    """
    preserve_fields = preserve_fields or [
        "status",
        "lawyer_note",
        "para_informe",
        "updated_by",
    ]

    out = dict(regenerated)

    # Preservar trabajo humano si existe
    for f in preserve_fields:
        if f in existing:
            out[f] = existing.get(f)

    # Señal de cambio (para UI)
    old_fp = existing.get("fingerprint")
    new_fp = regenerated.get("fingerprint")

    # Cambios materiales mínimos: evidencia o checklist
    old_ev = existing.get("evidences") or []
    new_ev = regenerated.get("evidences") or []
    old_cl = existing.get("to_clarify") or []
    new_cl = regenerated.get("to_clarify") or []

    material_change = False
    if old_fp and new_fp and old_fp != new_fp:
        material_change = True
    if old_ev != new_ev:
        material_change = True
    if old_cl != new_cl:
        material_change = True

    # Si ya estaba revisada, y cambia algo material → marcar para revisión
    if material_change:
        out["changed_since_last_review"] = True
    else:
        out["changed_since_last_review"] = bool(existing.get("changed_since_last_review", False))

    return out

