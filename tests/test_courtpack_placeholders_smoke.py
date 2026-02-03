from __future__ import annotations

from pathlib import Path

from app.services import courtpack_fs


def test_courtpack_placeholders_creates_config(tmp_path: Path):
    case_root = tmp_path / "clients_data" / "cases" / "case_retail_demo_sl_2026"
    assert not case_root.exists()
    res = courtpack_fs.ensure_placeholders(case_root=case_root)
    assert res["missing_case"] is True
    assert (case_root / "courtpack" / "config.json").exists()
