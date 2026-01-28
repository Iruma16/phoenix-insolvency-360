#!/usr/bin/env python3
"""Test que simula exactamente el flujo de Streamlit."""

import os
from pathlib import Path

import pytest

from app.ui.api_client import PhoenixLegalClient

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="E2E/manual: requiere API corriendo y ficheros locales de demo.",
)


def test_streamlit_flow():
    """Simula exactamente lo que hace Streamlit."""
    print("=" * 60)
    print("TEST: Simulando flujo de Streamlit")
    print("=" * 60)

    # 1. Inicializar cliente (igual que Streamlit)
    print("\n1️⃣ Inicializando cliente...")
    client = PhoenixLegalClient(base_url="http://localhost:8000")
    print("✅ Cliente inicializado")

    # 2. Verificar health check
    print("\n2️⃣ Health check...")
    try:
        health = client.health_check()
        print(f"✅ API responde: {health['status']}")
    except Exception as e:
        print(f"❌ ERROR en health check: {e}")
        return

    # 3. Listar casos
    print("\n3️⃣ Listando casos...")
    try:
        cases = client.list_cases()
        print(f"✅ Encontrados {len(cases)} casos")
        if cases:
            case_id = cases[0]["case_id"]
            print(f"   Usando caso: {cases[0]['name']} ({case_id})")
        else:
            print("❌ No hay casos disponibles")
            return
    except Exception as e:
        print(f"❌ ERROR listando casos: {e}")
        return

    # 4. Preparar archivo (simular st.file_uploader)
    print("\n4️⃣ Preparando archivo...")
    test_file = Path("data/casos_prueba/RETAIL_DEMO_SL/03_Factura_Proveedor_Alpha_45000.pdf")

    if not test_file.exists():
        print(f"❌ Archivo no encontrado: {test_file}")
        return

    # Leer archivo (igual que file.getvalue() en Streamlit)
    with open(test_file, "rb") as f:
        file_content = f.read()

    print(f"✅ Archivo leído: {test_file.name}")
    print(f"   Tamaño: {len(file_content)} bytes")

    # 5. Preparar lista de archivos (igual que Streamlit)
    print("\n5️⃣ Preparando lista de archivos...")
    files = [(test_file.name, file_content)]
    print(f"✅ Lista preparada: {len(files)} archivo(s)")

    # 6. Subir documentos (llamada EXACTA que hace Streamlit)
    print("\n6️⃣ Subiendo documentos...")
    print("   (Observa los logs [DEBUG] arriba)")
    try:
        results = client.upload_documents(case_id, files)
        print("\n✅ ÉXITO: Subida completada")
        print(f"   Documentos procesados: {len(results)}")

        for result in results:
            print(f"\n   📄 {result['filename']}")
            print(f"      Status: {result['status']}")
            print(f"      Document ID: {result['document_id']}")
            print(f"      Chunks: {result['chunks_count']}")
            if result.get("error_message"):
                print(f"      ⚠️  Error: {result['error_message']}")

    except Exception as e:
        print("\n❌ ERROR en upload_documents:")
        print(f"   Tipo: {type(e).__name__}")
        print(f"   Mensaje: {e}")

        # Mostrar más detalles si es un error HTTP
        if hasattr(e, "response"):
            print(f"   Status Code: {e.response.status_code}")
            print(f"   Response: {e.response.text[:500]}")

        import traceback

        print("\n   Traceback completo:")
        traceback.print_exc()


if __name__ == "__main__":
    test_streamlit_flow()
