import pdfplumber

# Ruta de tu archivo
ruta_pdf = "data/facturas.pdf"

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