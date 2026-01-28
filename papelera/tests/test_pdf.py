import pdfplumber
import os
import sys

# Añadir la raíz del proyecto al path para importar módulos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Ruta absoluta al archivo PDF desde la raíz del proyecto
ruta_pdf = os.path.join(BASE_DIR, "data", "facturas.pdf")

print(f"📂 Intentando abrir: {ruta_pdf}...")

try:
    with pdfplumber.open(ruta_pdf) as pdf:
        # Leemos la primera página
        pagina = pdf.pages[0]
        texto = pagina.extract_text()
        
        print("\n--- 📄 TEXTO ENCONTRADO ---")
        print(texto)
        print("---------------------------\n")

except Exception as e:
    print(f"❌ Error: {e}")

