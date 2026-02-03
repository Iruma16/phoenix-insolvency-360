#!/usr/bin/env python3
"""Script simple para subir documentos sin Streamlit."""

import sys
from pathlib import Path

import requests

API_URL = "http://localhost:8000"


def list_cases():
    """Lista todos los casos."""
    response = requests.get(f"{API_URL}/api/cases")
    cases = response.json()
    print("\n📁 CASOS DISPONIBLES:")
    for i, case in enumerate(cases, 1):
        print(f"{i}. {case['name']} (ID: {case['case_id']})")
    return cases


def upload_file(case_id, file_path):
    """Sube un archivo a un caso."""
    path = Path(file_path)
    if not path.exists():
        print(f"❌ Archivo no encontrado: {file_path}")
        return

    print(f"\n📤 Subiendo: {path.name}")
    print(f"   Tamaño: {path.stat().st_size / 1024:.1f} KB")

    with open(path, "rb") as f:
        files = {"files": (path.name, f, "application/pdf")}
        response = requests.post(f"{API_URL}/api/cases/{case_id}/documents", files=files)

    if response.status_code == 201:
        result = response.json()[0]
        print(f"✅ ÉXITO: {result['status']}")
        print(f"   Document ID: {result['document_id']}")
        print(f"   Chunks: {result['chunks_count']}")
    else:
        print(f"❌ ERROR {response.status_code}: {response.text}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python upload_simple.py <case_id> <archivo.pdf>")
        print("\nEjemplo:")
        print(
            "  python upload_simple.py 140a476d-0325-43e7-93bd-616635997907 data/casos_prueba/RETAIL_DEMO_SL/01_Balance_Situacion_2023.pdf"
        )
        print("\n" + "=" * 60)
        list_cases()
        sys.exit(1)

    case_id = sys.argv[1]
    file_path = sys.argv[2]

    upload_file(case_id, file_path)
