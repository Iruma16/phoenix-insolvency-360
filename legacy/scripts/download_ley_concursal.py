"""
Script para descargar la Ley Concursal consolidada del BOE.

Descarga el texto completo oficial desde la fuente BOE y lo guarda
en clients_data/legal/ley_concursal/documents/
"""
import json
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Configuración
BOE_URL = "https://www.boe.es/buscar/act.php?id=BOE-A-2003-14086"
BASE_DIR = Path(__file__).parent.parent
LEGAL_DIR = BASE_DIR / "clients_data" / "legal" / "ley_concursal"
DOCS_DIR = LEGAL_DIR / "documents"
METADATA_FILE = LEGAL_DIR / "metadata.json"


def download_ley_concursal():
    """Descarga la Ley Concursal consolidada COMPLETA del BOE."""

    print("=" * 70)
    print("DESCARGA LEY CONCURSAL CONSOLIDADA COMPLETA - BOE")
    print("=" * 70)

    # Crear directorios
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # URL para obtener el texto consolidado completo
    BOE_CONSOLIDATED_URL = "https://www.boe.es/buscar/act.php?id=BOE-A-2003-14086&tn=1&p=20241230"

    print("\n📥 Descargando texto consolidado completo desde BOE...")
    print(f"   URL: {BOE_CONSOLIDATED_URL}")

    # Descargar HTML
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        response = requests.get(BOE_CONSOLIDATED_URL, headers=headers, timeout=60)
        response.raise_for_status()
        response.encoding = "utf-8"

        html_content = response.text

        # Parsear con BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")

        # Estrategia: buscar TODOS los contenedores de texto legal
        texto_completo = []

        # 1. Buscar divs con clase "texto" o similares
        texto_divs = soup.find_all(
            "div", class_=re.compile(r"(texto|articulo|apartado|parrafo)", re.I)
        )

        # 2. Buscar por estructura típica del BOE
        for div in texto_divs:
            texto_div = div.get_text(separator="\n", strip=True)
            if len(texto_div) > 50:  # Filtrar divs vacíos
                texto_completo.append(texto_div)

        # 3. Si no hay suficiente contenido, intentar con el body completo
        if len(texto_completo) < 10:
            print("   ⚠️  Pocos elementos encontrados, extrayendo body completo...")
            body = soup.find("body")
            if body:
                # Eliminar scripts, styles, nav, footer
                for tag in body.find_all(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                texto = body.get_text(separator="\n", strip=True)
                texto_completo = [texto]

        # Unir todo el texto
        texto = "\n\n".join(texto_completo)

        # Limpiar texto
        texto = re.sub(r"\n\s*\n\s*\n+", "\n\n", texto)  # Múltiples líneas vacías -> 2
        texto = re.sub(r"[ \t]+", " ", texto)  # Múltiples espacios -> 1
        texto = texto.strip()

        # Validar que tenemos contenido legal COMPLETO
        if len(texto) < 50000:
            print(f"   ⚠️  ADVERTENCIA: Texto corto ({len(texto)} chars)")
            print("   Esto podría indicar que no se descargó el texto completo.")
            print("   Se continuará pero verifica el resultado.")

        if "Artículo" not in texto and "Art." not in texto and "TÍTULO" not in texto:
            raise ValueError("El texto descargado no parece contener artículos legales.")

        print(f"   ✅ Descargado: {len(texto):,} caracteres")
        print("   ✅ Validación: contiene artículos legales")

        # Guardar HTML completo
        timestamp = datetime.now().strftime("%Y%m%d")
        html_filename = f"ley_concursal_boe_consolidado_{timestamp}.html"
        html_path = DOCS_DIR / html_filename

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"\n💾 Guardado HTML completo: {html_path}")

        # Guardar texto extraído
        txt_filename = f"ley_concursal_boe_consolidado_{timestamp}.txt"
        txt_path = DOCS_DIR / txt_filename

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(texto)

        print(f"💾 Guardado texto extraído: {txt_path}")

        # Contar artículos aproximadamente
        num_articulos = texto.count("Artículo") + texto.count("Art.")
        print("\n📊 Estadísticas:")
        print(f"   - Caracteres: {len(texto):,}")
        print(f"   - Líneas: {texto.count(chr(10)):,}")
        print(f"   - Artículos (aprox): {num_articulos}")

        # Crear/actualizar metadata
        metadata = {
            "source": "BOE",
            "source_url": BOE_URL,
            "retrieved_at": datetime.now().isoformat(),
            "format": "html",
            "description": "Ley Concursal consolidada completa",
            "notes": "Ingesta completa desde BOE",
            "files": {
                "html": html_filename,
                "txt": txt_filename,
            },
            "stats": {
                "characters": len(texto),
                "lines": texto.count("\n"),
                "articles_approx": num_articulos,
            },
            "version_label": f"LC consolidada BOE {timestamp}",
        }

        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Metadata guardada: {METADATA_FILE}")

        print("\n" + "=" * 70)
        print("✅ DESCARGA COMPLETADA")
        print("=" * 70)
        print("\nArchivos creados:")
        print(f"  - {html_path}")
        print(f"  - {txt_path}")
        print(f"  - {METADATA_FILE}")

        return txt_path

    except requests.RequestException as e:
        print(f"\n❌ Error de red: {e}")
        raise
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    try:
        txt_path = download_ley_concursal()
        print("\n🎯 Siguiente paso: Ejecutar ingesta con:")
        print("   python scripts/ingest_ley_completa.py")
    except Exception as e:
        print(f"\n💥 Falló la descarga: {e}")
        exit(1)
