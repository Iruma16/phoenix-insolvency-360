from __future__ import annotations

import io
import json
import os
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Optional

from pypdf import PdfReader, PdfWriter

# =========================================================
# CourtPack (filesystem-only)
# =========================================================

CASE_ID = "case_retail_demo_sl_2026"
CASE_ROOT = Path("clients_data/cases") / CASE_ID
COURTPACK_DIR = CASE_ROOT / "courtpack"

DOC0_OFFICIAL_PATH = Path(
    "judicial_forms/concurso_voluntario/personas_juridicas/formulario_oficial_v2020_05_21.pdf"
)

DOC0_DIR = COURTPACK_DIR / "documento_0"
DOC0_IN_CASE = DOC0_DIR / "documento_0_oficial.pdf"
DOC0_STATE_JSON = DOC0_DIR / "state.json"
DOC0_AUDIT_NDJSON = DOC0_DIR / "audit.ndjson"
COURTPACK_CONFIG_JSON = COURTPACK_DIR / "config.json"

PRESENTACIONES_DIR = COURTPACK_DIR / "presentaciones"

RULES_VERSION = "courtpack_v1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(b: bytes) -> str:
    return sha256(b).hexdigest()


def _sha256_file(p: Path) -> str:
    h = sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_placeholders(*, case_root: Path = CASE_ROOT) -> dict[str, Any]:
    """
    Crea placeholders mínimos (sin bloquear) bajo el caso.
    - Si falta el case_root, lo crea vacío y devuelve missing_case=True.
    - Si falta config.json, crea {} y devuelve missing_config=True.
    """
    missing_case = False
    if not case_root.exists():
        case_root.mkdir(parents=True, exist_ok=True)
        missing_case = True

    courtpack_dir = case_root / "courtpack"
    courtpack_dir.mkdir(parents=True, exist_ok=True)

    config_path = courtpack_dir / "config.json"
    missing_config = False
    if not config_path.exists():
        config_path.write_text("{}", encoding="utf-8")
        missing_config = True

    return {
        "case_root": str(case_root),
        "missing_case": missing_case,
        "missing_config": missing_config,
        "config_path": str(config_path),
    }


def ensure_doc0_in_case(
    *,
    case_root: Path = CASE_ROOT,
    doc0_official_path: Path = DOC0_OFFICIAL_PATH,
) -> dict[str, Any]:
    """
    Copia el Documento 0 oficial a la carpeta del caso (sin modificar el original).
    """
    _ = ensure_placeholders(case_root=case_root)

    out_dir = case_root / "courtpack" / "documento_0"
    out_dir.mkdir(parents=True, exist_ok=True)

    missing_doc0_official = not doc0_official_path.exists()
    copied = False
    if not missing_doc0_official:
        dst = out_dir / "documento_0_oficial.pdf"
        if not dst.exists():
            dst.write_bytes(doc0_official_path.read_bytes())
            copied = True
    return {
        "missing_doc0_official": missing_doc0_official,
        "doc0_official_path": str(doc0_official_path),
        "doc0_in_case": str(out_dir / "documento_0_oficial.pdf"),
        "copied": copied,
    }


@dataclass(frozen=True)
class PdfFormField:
    name: str
    field_type: str


def read_pdf_form_fields(pdf_path: Path) -> list[PdfFormField]:
    """
    Lista campos AcroForm (determinista). No inventa campos.
    """
    reader = PdfReader(str(pdf_path))
    fields = reader.get_fields() or {}
    out: list[PdfFormField] = []
    for name in sorted(fields.keys()):
        f = fields.get(name) or {}
        ft = f.get("/FT")
        out.append(PdfFormField(name=str(name), field_type=str(ft) if ft is not None else ""))
    return out


def load_doc0_state(*, case_root: Path = CASE_ROOT) -> dict[str, Any]:
    """
    Carga state.json (si falta, devuelve estructura mínima).
    """
    p = case_root / "courtpack" / "documento_0" / "state.json"
    if not p.exists():
        return {"fields": {}, "updated_at": None}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        # No bloquear flujo: devolver mínimo.
        return {"fields": {}, "updated_at": None}


def _append_audit_line(audit_path: Path, payload: dict[str, Any]) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def save_doc0_state(
    patch: dict[str, Any],
    *,
    case_root: Path = CASE_ROOT,
    actor: str = "ui",
) -> dict[str, Any]:
    """
    Aplica un patch {field_name: value} y audita cambios en NDJSON.
    """
    _ = ensure_placeholders(case_root=case_root)
    doc0_dir = case_root / "courtpack" / "documento_0"
    doc0_dir.mkdir(parents=True, exist_ok=True)

    state_path = doc0_dir / "state.json"
    audit_path = doc0_dir / "audit.ndjson"

    state = load_doc0_state(case_root=case_root)
    fields: dict[str, Any] = dict(state.get("fields") or {})

    changed: list[dict[str, Any]] = []
    now = _utc_now_iso()
    for k in sorted(patch.keys()):
        new_v = patch.get(k)
        old_v = fields.get(k)
        if old_v != new_v:
            fields[k] = new_v
            changed.append({"field": k, "old": old_v, "new": new_v})
            _append_audit_line(
                audit_path,
                {
                    "ts": now,
                    "actor": actor,
                    "action": "field_update",
                    "field": k,
                    "old": old_v,
                    "new": new_v,
                },
            )

    new_state = {"fields": fields, "updated_at": now}
    state_path.write_text(json.dumps(new_state, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saved": True, "changed": changed, "state_path": str(state_path), "audit_path": str(audit_path)}


def render_filled_doc0_pdf_bytes(
    *,
    case_root: Path = CASE_ROOT,
    doc0_pdf_path: Optional[Path] = None,
) -> tuple[Optional[bytes], Optional[str]]:
    """
    Genera un PDF rellenado (bytes) aplicando el state.json.
    Si no se puede, devuelve (None, motivo).
    """
    doc0_path = doc0_pdf_path or (case_root / "courtpack" / "documento_0" / "documento_0_oficial.pdf")
    if not doc0_path.exists():
        return None, "missing_doc0_in_case"

    try:
        reader = PdfReader(str(doc0_path))
    except Exception:
        return None, "invalid_pdf"
    try:
        if not (reader.get_fields() or {}):
            return None, "no_acroform_fields"
    except Exception:
        return None, "no_acroform_fields"

    state = load_doc0_state(case_root=case_root)
    values: dict[str, Any] = dict(state.get("fields") or {})

    writer = PdfWriter()
    try:
        for page in reader.pages:
            writer.add_page(page)
    except Exception:
        return None, "read_pages_failed"

    # Aplicar valores a todos los campos que existan.
    # (No inventa campos: pypdf ignora claves no existentes.)
    for i in range(len(writer.pages)):
        try:
            writer.update_page_form_field_values(writer.pages[i], values)
        except Exception:
            # No bloquear flujo: continuar.
            continue

    out = io.BytesIO()
    try:
        writer.write(out)
        return out.getvalue(), None
    except Exception:
        return None, "write_failed"


def build_zip_bytes(*, case_root: Path = CASE_ROOT) -> tuple[bytes, dict[str, Any]]:
    """
    Construye el ZIP del expediente (bytes) + manifest dict.
    No bloquea si faltan piezas; el manifest reflejará lo presente.
    """
    placeholders = ensure_placeholders(case_root=case_root)
    doc0_status = ensure_doc0_in_case(case_root=case_root)

    entries: list[dict[str, Any]] = []
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Documento 0 oficial (en caso)
        doc0_in_case = Path(doc0_status["doc0_in_case"])
        if doc0_in_case.exists():
            b = doc0_in_case.read_bytes()
            arc = "Documento_0/Formulario_oficial.pdf"
            zf.writestr(arc, b)
            entries.append({"path": arc, "sha256": _sha256_bytes(b), "size_bytes": len(b), "role": "documento_0_oficial"})

        # Documento 0 rellenado
        filled_bytes, filled_err = render_filled_doc0_pdf_bytes(case_root=case_root)
        if filled_bytes:
            arc = "Documento_0/Formulario_rellenado.pdf"
            zf.writestr(arc, filled_bytes)
            entries.append({"path": arc, "sha256": _sha256_bytes(filled_bytes), "size_bytes": len(filled_bytes), "role": "documento_0_rellenado"})
        elif filled_err:
            entries.append({"path": "Documento_0/Formulario_rellenado.pdf", "error": filled_err, "role": "documento_0_rellenado"})

        # State + audit
        state_path = case_root / "courtpack" / "documento_0" / "state.json"
        if state_path.exists():
            b = state_path.read_bytes()
            arc = "Documento_0/state.json"
            zf.writestr(arc, b)
            entries.append({"path": arc, "sha256": _sha256_bytes(b), "size_bytes": len(b), "role": "state"})

        audit_path = case_root / "courtpack" / "documento_0" / "audit.ndjson"
        if audit_path.exists():
            b = audit_path.read_bytes()
            arc = "Documento_0/audit.ndjson"
            zf.writestr(arc, b)
            entries.append({"path": arc, "sha256": _sha256_bytes(b), "size_bytes": len(b), "role": "audit"})

        manifest = {
            "rules_version": RULES_VERSION,
            "generated_at": _utc_now_iso(),
            "case_id": CASE_ID,
            "case_root": str(case_root),
            "placeholders": placeholders,
            "doc0": doc0_status,
            "entries": entries,
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        zf.writestr("MANIFEST.json", manifest_bytes)
        entries.append(
            {"path": "MANIFEST.json", "sha256": _sha256_bytes(manifest_bytes), "size_bytes": len(manifest_bytes), "role": "manifest"}
        )

    # Recalcular manifest final (incluyendo su propio hash ya incluido como entry).
    return zip_buf.getvalue(), manifest


def present_simulated(*, case_root: Path = CASE_ROOT) -> dict[str, Any]:
    """
    Simula la presentación: genera ZIP + escribe acuse JSON con hashes en el caso.
    """
    _ = ensure_placeholders(case_root=case_root)
    zip_bytes, manifest = build_zip_bytes(case_root=case_root)
    zip_hash = _sha256_bytes(zip_bytes)

    PRESENTACIONES_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    out_path = PRESENTACIONES_DIR / f"{ts}.json"
    payload = {
        "presentado_simulado": True,
        "presented_at": _utc_now_iso(),
        "zip_sha256": zip_hash,
        "zip_size_bytes": len(zip_bytes),
        "manifest": manifest,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "acuse_path": str(out_path), "zip_sha256": zip_hash, "zip_size_bytes": len(zip_bytes)}

