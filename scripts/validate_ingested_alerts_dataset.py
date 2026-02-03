#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validador post-ingesta del dataset sintético de alertas.

Comprueba Definition of Ready (mínimo):
- Cada documento tiene chunks
- En chunks: offsets y extraction_method siempre
- Para PDFs: page_start/page_end presentes cuando el extractor las aporta
- Duplicados: detectables por sha256 (comprobación en documents list)

Uso:
  python scripts/validate_ingested_alerts_dataset.py --base-url http://localhost:8000 --case-id <id>
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Any

import requests


def main() -> None:
    ap = argparse.ArgumentParser(description="Valida que el dataset está bien ingerido.")
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--limit", type=int, default=1000)
    args = ap.parse_args()

    base_url = args.base_url.rstrip("/")
    case_id = args.case_id

    docs = requests.get(f"{base_url}/api/cases/{case_id}/documents", timeout=30).json()
    chunks = requests.get(
        f"{base_url}/api/cases/{case_id}/chunks",
        params={"limit": int(args.limit)},
        timeout=60,
    ).json()

    doc_map: dict[str, dict[str, Any]] = {d["document_id"]: d for d in docs}
    chunks_by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in chunks:
        chunks_by_doc[str(c.get("document_id"))].append(c)

    errors: list[str] = []

    # 1) Cada doc debe tener chunks (si parsing completó)
    for doc_id, d in doc_map.items():
        if not chunks_by_doc.get(doc_id):
            errors.append(f"Documento sin chunks: {doc_id} ({d.get('filename')})")

    # 2) Contrato de chunks: offsets + extraction_method + content
    pdf_missing_pages = 0
    for c in chunks:
        loc = c.get("location") or {}
        if loc.get("start_char") is None or loc.get("end_char") is None:
            errors.append(f"Chunk sin offsets: {c.get('chunk_id')}")
        if not loc.get("extraction_method"):
            errors.append(f"Chunk sin extraction_method: {c.get('chunk_id')}")
        if not (c.get("content") or "").strip():
            errors.append(f"Chunk sin content: {c.get('chunk_id')}")

        # Pages check: solo como “ready” para PDFs cuando aplica
        if str(loc.get("extraction_method")) == "pdf_text":
            if loc.get("page_start") is None:
                pdf_missing_pages += 1

    # 3) Duplicados por sha256 (best-effort)
    sha_map: dict[str, list[str]] = defaultdict(list)
    for d in docs:
        sha = str(d.get("sha256_hash") or "")
        if sha:
            sha_map[sha].append(str(d.get("filename") or ""))
    dup_shas = {sha: ns for sha, ns in sha_map.items() if len(ns) > 1}

    print("case_id:", case_id)
    print("documents:", len(docs))
    print("chunks:", len(chunks))
    print("pdf_chunks_missing_pages:", pdf_missing_pages)
    print("duplicate_sha256_groups:", len(dup_shas))
    if dup_shas:
        for sha, names in list(dup_shas.items())[:5]:
            print(" -", sha[:12], "=>", ", ".join(names[:5]))

    if errors:
        print("❌ VALIDACIÓN FALLIDA")
        for e in errors[:50]:
            print(" -", e)
        raise SystemExit(1)

    print("✅ VALIDACIÓN OK")


if __name__ == "__main__":
    main()

