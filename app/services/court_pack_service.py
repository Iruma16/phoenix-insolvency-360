from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Optional, Tuple

from app.models.court_pack import (
    AttachmentState,
    CourtDocumentState,
    CourtPackState,
    DebtorFlags,
    DocumentStatus,
    PackStatus,
)

RULES_VERSION = "juzgado_tab_v1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def compute_sha256_file(path: Path) -> str:
    h = sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def append_audit_event(case_root: Path, event: dict[str, Any]) -> None:
    """
    Escribe 1 línea JSON por evento en:
      court_pack/audit/audit_log.jsonl

    AuditEvent obligatorio (no se autocompleta; no inventa datos):
    {
      "timestamp_utc": "...ISO...",
      "user_id": "string",
      "doc_type": "doc0_formulario",
      "field_id": "string",
      "old_value": "...",
      "new_value": "...",
      "source": "manual_edit",
      "hash_before": "sha256",
      "hash_after": "sha256"
    }
    """
    required = (
        "timestamp_utc",
        "user_id",
        "doc_type",
        "field_id",
        "old_value",
        "new_value",
        "source",
        "hash_before",
        "hash_after",
    )
    missing = [k for k in required if k not in event]
    if missing:
        raise ValueError(f"AuditEvent missing keys: {missing}")

    paths = ensure_court_pack_dirs(case_root)
    p = paths["audit_log_jsonl"]
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _sha256_bytes(b: bytes) -> str:
    return compute_sha256_bytes(b)


def _sha256_file(p: Path) -> str:
    return compute_sha256_file(p)


def _safe_filename(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return "file"
    # Keep it deterministic and filesystem-safe
    n = re.sub(r"[^A-Za-z0-9._ -]+", "_", n)
    n = n.replace("..", ".")
    return n[:200]


def ensure_court_pack_dirs(case_root: Path) -> dict[str, Path]:
    """
    Creates/ensures the exact directory structure under:
      clients_data/cases/<case_id>/court_pack/
    """
    court_pack = case_root / "court_pack"
    paths = {
        "court_pack": court_pack,
        "state_json": court_pack / "state.json",
        "inputs_dir": court_pack / "inputs",
        "generated_dir": court_pack / "generated",
        "attachments_dir": court_pack / "attachments",
        "submissions_dir": court_pack / "submissions",
        "cache_dir": court_pack / "cache",
        "logs_dir": court_pack / "logs",
        "audit_dir": court_pack / "audit",
        "audit_log_jsonl": court_pack / "audit" / "audit_log.jsonl",
        "inputs_formulario_auto": court_pack / "inputs" / "formulario_auto.json",
        "inputs_formulario_overrides": court_pack / "inputs" / "formulario_overrides.json",
        "inputs_formulario_final": court_pack / "inputs" / "formulario_final.json",
        "inputs_wizard": court_pack / "inputs" / "wizard.json",
        "inputs_wizard_answers": court_pack / "inputs" / "wizard_answers.json",
        "inputs_field_map_effective": court_pack / "inputs" / "field_map_effective.json",
        "generated_doc0": court_pack
        / "generated"
        / "Documento_0_Formulario_Solicitud_Concurso.pdf",
    }

    # Ensure dirs
    case_root.mkdir(parents=True, exist_ok=True)
    paths["court_pack"].mkdir(parents=True, exist_ok=True)
    paths["inputs_dir"].mkdir(parents=True, exist_ok=True)
    paths["generated_dir"].mkdir(parents=True, exist_ok=True)
    paths["attachments_dir"].mkdir(parents=True, exist_ok=True)
    paths["submissions_dir"].mkdir(parents=True, exist_ok=True)
    paths["cache_dir"].mkdir(parents=True, exist_ok=True)
    paths["logs_dir"].mkdir(parents=True, exist_ok=True)
    paths["audit_dir"].mkdir(parents=True, exist_ok=True)

    # Placeholders (do not invent values)
    for k in ("inputs_formulario_auto", "inputs_formulario_overrides", "inputs_formulario_final"):
        p = paths[k]
        if not p.exists():
            p.write_text("{}", encoding="utf-8")
    for k in ("inputs_wizard", "inputs_field_map_effective"):
        p = paths[k]
        if not p.exists():
            p.write_text("{}", encoding="utf-8")
    if not paths["inputs_wizard_answers"].exists():
        paths["inputs_wizard_answers"].write_text("{}", encoding="utf-8")
    if not paths["audit_log_jsonl"].exists():
        paths["audit_log_jsonl"].write_text("", encoding="utf-8")

    return paths


def _audit_append(case_root: Path, event: dict[str, Any]) -> None:
    paths = ensure_court_pack_dirs(case_root)
    p = paths["audit_log_jsonl"]
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def _read_flags_from_inputs(case_root: Path) -> Optional[DebtorFlags]:
    """
    Deterministic read: tries inputs/formulario_final.json, then overrides, then auto.
    Expected shapes:
      - {"debtor_flags": {...}}
      - {...} (direct DebtorFlags object)
    Returns None if missing/invalid.
    """
    paths = ensure_court_pack_dirs(case_root)
    candidates = [
        paths["inputs_formulario_final"],
        paths["inputs_formulario_overrides"],
        paths["inputs_formulario_auto"],
    ]
    for p in candidates:
        try:
            raw = json.loads(p.read_text(encoding="utf-8") or "{}")
        except Exception:
            continue
        if isinstance(raw, dict) and isinstance(raw.get("debtor_flags"), dict):
            try:
                return DebtorFlags.model_validate(raw["debtor_flags"])
            except Exception:
                return None
        if isinstance(raw, dict):
            try:
                return DebtorFlags.model_validate(raw)
            except Exception:
                continue
    return None


def compute_required_docs(flags: DebtorFlags) -> list[dict[str, Any]]:
    """
    Returns doc definitions with required flag computed from DebtorFlags.
    No inference: only direct boolean checks.
    """
    defs: list[dict[str, Any]] = [
        {
            "doc_type": "doc0_formulario",
            "display_name": "Formulario solicitud concurso voluntario (PJ)",
            "is_required": True,
        },
        {
            "doc_type": "memoria",
            "display_name": "Memoria económica y jurídica",
            "is_required": True,
        },
        {
            "doc_type": "inventario",
            "display_name": "Inventario de bienes y derechos",
            "is_required": True,
        },
        {"doc_type": "acreedores", "display_name": "Relación de acreedores", "is_required": True},
        {
            "doc_type": "trabajadores",
            "display_name": "Trabajadores",
            "is_required": bool(flags.has_workers),
        },
        {
            "doc_type": "cuentas_anuales",
            "display_name": "Cuentas anuales",
            "is_required": bool(flags.accounting_obligation),
        },
        {
            "doc_type": "auditoria",
            "display_name": "Auditoría",
            "is_required": bool(flags.requires_audit),
        },
        {
            "doc_type": "escritura_estatutos",
            "display_name": "Escritura / estatutos",
            "is_required": flags.debtor_type == "juridica",
        },
        {
            "doc_type": "poder_apud_acta",
            "display_name": "Poder apud acta",
            "is_required": bool(flags.has_procurador),
        },
    ]
    return defs


def init_state(case_root: Path, case_id: str, flags: DebtorFlags) -> CourtPackState:
    """
    Initializes CourtPackState. Documents are created with status=not_started.
    """
    ensure_court_pack_dirs(case_root)
    doc_defs = compute_required_docs(flags)

    flags_dump = flags.model_dump()
    flags_hash_seed = json.dumps(flags_dump, sort_keys=True, ensure_ascii=False).encode("utf-8")
    flags_hash = _sha256_bytes(flags_hash_seed)

    docs: list[CourtDocumentState] = []
    for d in doc_defs:
        doc_type = str(d["doc_type"])
        inputs_hash = _sha256_bytes(f"{case_id}|{doc_type}|{flags_hash}".encode("utf-8"))
        docs.append(
            CourtDocumentState(
                doc_type=doc_type,
                display_name=str(d["display_name"]),
                is_required=bool(d["is_required"]),
                status=DocumentStatus.not_started,
                inputs_hash=inputs_hash,
                generated_file_path=None,
                last_generated_at=None,
                ai_cache_key_generate=None,
                ai_cache_key_review=None,
                issues=[],
                warnings_count=0,
                errors_count=0,
            )
        )

    now = _utc_now_iso()
    return CourtPackState(
        case_id=case_id,
        debtor_flags=flags,
        documents=docs,
        attachments=[],
        pack_status=PackStatus.incomplete,
        created_at=now,
        updated_at=now,
        manual_overrides_count=0,
    )


def load_state(case_root: Path) -> CourtPackState:
    """
    Loads CourtPackState from state.json. If missing, initializes from inputs flags.
    """
    paths = ensure_court_pack_dirs(case_root)
    state_path = paths["state_json"]

    if state_path.exists():
        raw = json.loads(state_path.read_text(encoding="utf-8") or "{}")
        return CourtPackState.model_validate(raw)

    # Init path: case_id comes from the case_root folder name (deterministic)
    case_id = case_root.name
    flags = _read_flags_from_inputs(case_root)
    if flags is None:
        # Cannot invent DebtorFlags; keep placeholders and raise explicit error.
        raise ValueError(
            "Missing debtor_flags in inputs/*.json; cannot init CourtPackState without flags."
        )

    state = init_state(case_root, case_id, flags)
    save_state(case_root, state)
    return state


def save_state(case_root: Path, state: CourtPackState) -> None:
    paths = ensure_court_pack_dirs(case_root)
    p = paths["state_json"]
    # Update updated_at deterministically at save time
    d = state.model_dump()
    d["updated_at"] = _utc_now_iso()
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    _audit_append(
        case_root,
        {
            "ts": _utc_now_iso(),
            "actor": "service",
            "action": "save_state",
            "path": str(p.relative_to(case_root)),
        },
    )


def add_attachment(
    case_root: Path,
    file_bytes: bytes,
    filename: str,
    kind: str,
) -> AttachmentState:
    """
    Stores an attachment under attachments/ and updates state.json.
    """
    paths = ensure_court_pack_dirs(case_root)
    att_dir = paths["attachments_dir"]

    attachment_id = sha256(file_bytes).hexdigest()[:16]
    safe_name = _safe_filename(filename)
    out_name = f"{attachment_id}__{safe_name}"
    out_path = att_dir / out_name
    out_path.write_bytes(file_bytes)

    rel_path = str(out_path.relative_to(paths["court_pack"]))

    att = AttachmentState(
        attachment_id=attachment_id,
        filename=safe_name,
        rel_path=rel_path,
        kind=kind,  # validated by Pydantic Literal
        sha256=_sha256_bytes(file_bytes),
        size_bytes=len(file_bytes),
        created_at=_utc_now_iso(),
    )

    # Best-effort: si no existe state.json y no hay debtor_flags, no inventamos estado.
    try:
        st = load_state(case_root)
        st2 = CourtPackState(
            **{
                **st.model_dump(),
                "attachments": [*st.attachments, att],
            }
        )
        save_state(case_root, st2)
    except Exception:
        pass
    _audit_append(
        case_root,
        {
            "ts": _utc_now_iso(),
            "actor": "service",
            "action": "add_attachment",
            "attachment_id": attachment_id,
            "rel_path": rel_path,
        },
    )
    return att


def remove_attachment(case_root: Path, attachment_id: str) -> None:
    paths = ensure_court_pack_dirs(case_root)
    court_pack = paths["court_pack"]
    att_dir = paths["attachments_dir"]

    # Remove file(s) matching prefix
    for p in att_dir.glob(f"{attachment_id}__*"):
        try:
            p.unlink()
        except Exception:
            pass

    # Remove from state if present (best-effort; no inventar debtor_flags)
    try:
        st = load_state(case_root)
        kept = [a for a in st.attachments if a.attachment_id != attachment_id]
        if len(kept) != len(st.attachments):
            st2 = CourtPackState(**{**st.model_dump(), "attachments": kept})
            save_state(case_root, st2)
    except Exception:
        pass
    _audit_append(
        case_root,
        {
            "ts": _utc_now_iso(),
            "actor": "service",
            "action": "remove_attachment",
            "attachment_id": attachment_id,
            "court_pack": str(court_pack),
        },
    )


def export_expediente_zip(case_root: Path) -> Tuple[bytes, str]:
    """
    Exports a ZIP containing:
      - /generated/*
      - /attachments/*
      - /manifest.json
    NEVER includes /audit nor /logs.
    """
    paths = ensure_court_pack_dirs(case_root)
    court_pack = paths["court_pack"]
    generated_dir = paths["generated_dir"]
    attachments_dir = paths["attachments_dir"]

    case_id = case_root.name
    created_at = _utc_now_iso()

    items: list[dict[str, Any]] = []

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # generated/*
        for p in sorted(generated_dir.rglob("*")):
            if p.is_dir():
                continue
            rel = p.relative_to(court_pack)
            arc = str(rel)
            b = p.read_bytes()
            zf.writestr(arc, b)
            items.append(
                {
                    "role": "generated",
                    "rel_path": arc,
                    "sha256": _sha256_bytes(b),
                    "size_bytes": len(b),
                }
            )

        # attachments/*
        for p in sorted(attachments_dir.rglob("*")):
            if p.is_dir():
                continue
            rel = p.relative_to(court_pack)
            arc = str(rel)
            b = p.read_bytes()
            zf.writestr(arc, b)
            items.append(
                {
                    "role": "attachment",
                    "rel_path": arc,
                    "sha256": _sha256_bytes(b),
                    "size_bytes": len(b),
                }
            )

        manifest = {
            "created_at": created_at,
            "case_id": case_id,
            "rules_version": RULES_VERSION,
            "items": items,
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        zf.writestr("manifest.json", manifest_bytes)
        items.append(
            {
                "role": "manifest",
                "rel_path": "manifest.json",
                "sha256": _sha256_bytes(manifest_bytes),
                "size_bytes": len(manifest_bytes),
            }
        )

    zip_filename = f"court_pack_expediente_{case_id}.zip"
    _audit_append(
        case_root,
        {
            "ts": _utc_now_iso(),
            "actor": "service",
            "action": "export_expediente_zip",
            "zip_filename": zip_filename,
            "items_count": len(items),
        },
    )
    return zip_buf.getvalue(), zip_filename
