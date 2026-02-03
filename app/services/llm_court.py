from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Optional


def make_source_hash(payload: dict[str, Any]) -> str:
    """
    sha256(json canonical): JSON con claves ordenadas, sin espacios, UTF-8.
    """
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return sha256(raw).hexdigest()


def get_cache_path(
    case_root: Path,
    doc_type: str,
    operation: str,
    source_hash: str,
) -> Path:
    """
    Devuelve path dentro de:
      clients_data/cases/<case_id>/court_pack/cache/
    """
    # Evitar traversal accidental en subpaths (sin “inferir” nada).
    safe_doc_type = (doc_type or "").replace("/", "_").replace("\\", "_")
    safe_operation = (operation or "").replace("/", "_").replace("\\", "_")
    cache_dir = case_root / "court_pack" / "cache" / safe_doc_type / safe_operation
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{source_hash}.json"


def load_cache(
    case_root: Path,
    doc_type: str,
    operation: str,
    source_hash: str,
) -> Optional[dict[str, Any]]:
    p = get_cache_path(case_root, doc_type, operation, source_hash)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8") or "{}")
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def save_cache(
    case_root: Path,
    doc_type: str,
    operation: str,
    source_hash: str,
    data: dict[str, Any],
) -> Path:
    p = get_cache_path(case_root, doc_type, operation, source_hash)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# =========================================================
# LLM stubs (NO integración real)
# =========================================================


def generate_memoria(payload: dict[str, Any]) -> dict[str, Any]:
    raise NotImplementedError(
        "LLM disabled/stub: generate_memoria(payload) no implementado en app/services/llm_court.py"
    )


def review_document(payload: dict[str, Any]) -> dict[str, Any]:
    raise NotImplementedError(
        "LLM disabled/stub: review_document(payload) no implementado en app/services/llm_court.py"
    )


def review_diff(payload: dict[str, Any]) -> dict[str, Any]:
    raise NotImplementedError(
        "LLM disabled/stub: review_diff(payload) no implementado en app/services/llm_court.py"
    )
