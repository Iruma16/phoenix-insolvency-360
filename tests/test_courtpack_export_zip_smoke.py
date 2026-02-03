from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from app.services import courtpack_fs


def test_courtpack_export_zip_contains_manifest_and_doc0(tmp_path: Path):
    case_root = tmp_path / "clients_data" / "cases" / "case_retail_demo_sl_2026"
    courtpack_fs.ensure_placeholders(case_root=case_root)

    # Seed: Documento 0 dentro del caso (dummy PDF bytes, no inferencia)
    doc0_dir = case_root / "courtpack" / "documento_0"
    doc0_dir.mkdir(parents=True, exist_ok=True)
    (doc0_dir / "documento_0_oficial.pdf").write_bytes(b"%PDF-1.4\n%dummy\n")

    # Seed: state + audit
    (doc0_dir / "state.json").write_text(json.dumps({"fields": {"a": "b"}, "updated_at": "t"}, indent=2), encoding="utf-8")
    (doc0_dir / "audit.ndjson").write_text('{"ts":"t","actor":"ui","action":"field_update","field":"a","old":null,"new":"b"}\n', encoding="utf-8")

    zip_bytes, manifest = courtpack_fs.build_zip_bytes(case_root=case_root)
    assert isinstance(zip_bytes, (bytes, bytearray))
    assert "entries" in manifest

    zf = zipfile.ZipFile(io.BytesIO(zip_bytes), "r")
    names = set(zf.namelist())
    assert "MANIFEST.json" in names
    assert "Documento_0/Formulario_oficial.pdf" in names
    assert "Documento_0/state.json" in names
    assert "Documento_0/audit.ndjson" in names
