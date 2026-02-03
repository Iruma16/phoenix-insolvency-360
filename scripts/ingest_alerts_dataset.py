#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ingesta automática del dataset sintético de alertas por API.

Uso:
  python scripts/ingest_alerts_dataset.py --base-url http://localhost:8000

Qué hace:
- Crea un caso nuevo (o usa uno existente)
- Sube todos los archivos de data/synthetic/alerts_dataset/
- (Opcional) fuerza subida de duplicados binarios
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Iterable

import requests


def _find_repo_root(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").exists() or (p / ".git").exists():
            return p
    return start


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
DEFAULT_DATASET_DIR = REPO_ROOT / "clients_data" / "data" / "synthetic" / "alerts_dataset"


def iter_files(root: Path) -> Iterable[Path]:
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.startswith("."):
            yield p


def mime_for(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".eml": "message/rfc822",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(ext, "application/octet-stream")


def create_case(base_url: str, *, name: str) -> str:
    r = requests.post(f"{base_url}/api/cases", json={"name": name}, timeout=30)
    r.raise_for_status()
    return r.json()["case_id"]


def upload_file(base_url: str, *, case_id: str, path: Path, force_upload: bool) -> None:
    files = [("files", (path.name, path.read_bytes(), mime_for(path)))]
    params = {"force_upload": "true"} if force_upload else {}
    r = requests.post(
        f"{base_url}/api/cases/{case_id}/documents",
        params=params,
        files=files,
        timeout=120,
    )
    r.raise_for_status()


def main() -> None:
    ap = argparse.ArgumentParser(description="Ingesta dataset sintético de alertas por API.")
    ap.add_argument("--base-url", required=True, help="Ej: http://localhost:8000")
    ap.add_argument(
        "--dataset-dir",
        default=str(DEFAULT_DATASET_DIR),
        help="Ruta al dataset (default: clients_data/data/synthetic/alerts_dataset).",
    )
    ap.add_argument("--case-id", default="", help="Si se indica, no crea caso, usa este case_id.")
    ap.add_argument(
        "--case-name",
        default="ALERTAS_DATASET_SMOKE",
        help="Nombre del caso si se crea uno nuevo.",
    )
    ap.add_argument(
        "--force-upload-duplicates",
        action="store_true",
        help="Si se activa, sube duplicados binarios creando docs nuevos (force_upload=True).",
    )
    args = ap.parse_args()

    base_url = args.base_url.rstrip("/")
    dataset_dir = Path(args.dataset_dir).resolve()
    if not dataset_dir.exists():
        raise SystemExit(f"Dataset no encontrado: {dataset_dir}")

    case_id = args.case_id.strip() or create_case(base_url, name=args.case_name)
    print("📁 case_id:", case_id)
    print("📦 dataset:", dataset_dir)

    files = list(iter_files(dataset_dir))
    # ignorar manifest
    files = [p for p in files if p.name != "MANIFEST_ALERTAS_DATASET.txt"]
    print("📄 archivos:", len(files))

    for i, p in enumerate(files, 1):
        rel = p.relative_to(dataset_dir)
        print(f"[{i:02d}/{len(files):02d}] Subiendo:", rel)
        upload_file(
            base_url,
            case_id=case_id,
            path=p,
            force_upload=bool(args.force_upload_duplicates),
        )

    print("✅ Ingesta completada")
    print("Siguiente:")
    print(
        f"  python scripts/validate_ingested_alerts_dataset.py --base-url {base_url} --case-id {case_id}"
    )


if __name__ == "__main__":
    # Evitar que requests use proxies raros en entornos locales
    os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
    main()
