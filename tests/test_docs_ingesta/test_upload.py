#!/usr/bin/env python3
"""Script de prueba para verificar el endpoint de subida de documentos."""

import requests
from pathlib import Path

# Configuración
API_URL = "http://localhost:8000"
CASE_ID = "0ac6c71f-f0d6-4ed5-9b47-4a4e73905102"
TEST_FILE = "data/casos_prueba/RETAIL_DEMO_SL/05_Factura_Proveedor_Gamma_28000.pdf"

def test_upload():
    """Prueba de subida de documento."""
    print("=" * 60)
    print("TEST: Subida de documento")
    print("=" * 60)
    
    # Verificar que el archivo existe
    file_path = Path(TEST_FILE)
    if not file_path.exists():
        print(f"❌ ERROR: Archivo no encontrado: {file_path}")
        return
    
    print(f"✅ Archivo encontrado: {file_path}")
    print(f"✅ Tamaño: {file_path.stat().st_size} bytes")
    
    # Preparar la petición
    url = f"{API_URL}/api/cases/{CASE_ID}/documents"
    print(f"\n📤 URL: {url}")
    
    # Leer el archivo
    with open(file_path, "rb") as f:
        file_content = f.read()
    
    # Método 1: Con files (correcto para FastAPI)
    print("\n--- Método 1: files=(filename, content, mime_type) ---")
    files = {
        "files": (file_path.name, file_content, "application/pdf")
    }
    
    try:
        response = requests.post(url, files=files)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 201:
            print("✅ SUCCESS!")
            result = response.json()
            print(f"Resultado: {result}")
        else:
            print(f"❌ ERROR: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
    
    # Método 2: Con múltiples archivos
    print("\n--- Método 2: Múltiples archivos ---")
    files_list = [
        ("files", (file_path.name, file_content, "application/pdf"))
    ]
    
    try:
        response = requests.post(url, files=files_list)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 201:
            print("✅ SUCCESS!")
            result = response.json()
            print(f"Resultado: {result}")
        else:
            print(f"❌ ERROR: {response.status_code}")
            print(f"Response: {response.text}")
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")

if __name__ == "__main__":
    test_upload()
