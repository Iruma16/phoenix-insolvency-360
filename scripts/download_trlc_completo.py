"""
Script para descargar el TRLC (Texto Refundido Ley Concursal) COMPLETO desde el BOE.

Real Decreto Legislativo 1/2020, de 5 de mayo
URL: https://www.boe.es/buscar/act.php?id=BOE-A-2020-4859

ESTE SCRIPT DESCARGA EL TEXTO CONSOLIDADO COMPLETO (~700 artículos)
NO es un corpus curado ni selección manual.
"""
import requests
from pathlib import Path
from datetime import datetime
import json
import re
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).parent.parent
LEGAL_DIR = BASE_DIR / "clients_data" / "legal" / "ley_concursal"
DOCS_DIR = LEGAL_DIR / "documents"
METADATA_FILE = LEGAL_DIR / "metadata.json"

# URL correcta del TRLC consolidado
TRLC_URL = "https://www.boe.es/buscar/act.php?id=BOE-A-2020-4859"


def download_trlc_completo():
    """Descarga el TRLC consolidado completo del BOE."""
    
    print("="*80)
    print("DESCARGA TRLC CONSOLIDADO COMPLETO - BOE")
    print("Real Decreto Legislativo 1/2020, de 5 de mayo")
    print("="*80)
    
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"\n📥 Descargando desde BOE...")
    print(f"   URL: {TRLC_URL}")
    print(f"   Esto puede tardar varios minutos...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    try:
        response = requests.get(TRLC_URL, headers=headers, timeout=120)
        response.raise_for_status()
        response.encoding = 'utf-8'
        
        html_content = response.text
        
        # Validar que recibimos HTML válido
        if len(html_content) < 50000:
            raise ValueError(f"HTML descargado muy corto ({len(html_content)} chars). Probablemente error del BOE.")
        
        print(f"   ✅ Descargado: {len(html_content):,} caracteres de HTML")
        
        # Guardar HTML completo con timestamp
        timestamp = datetime.now().strftime("%Y%m%d")
        html_filename = f"ley_concursal_boe_consolidado_trlc_{timestamp}.html"
        html_path = DOCS_DIR / html_filename
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"\n💾 HTML guardado: {html_path}")
        
        # Parsear y extraer texto completo
        print(f"\n📝 Extrayendo texto completo...")
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Eliminar elementos no deseados
        for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            tag.decompose()
        
        # Estrategia: extraer TODO el contenido del body
        body = soup.find('body')
        if not body:
            raise ValueError("No se encontró el tag <body> en el HTML")
        
        texto_completo = body.get_text(separator='\n', strip=True)
        
        # Limpiar texto
        texto_completo = re.sub(r'\n\s*\n\s*\n+', '\n\n', texto_completo)
        texto_completo = re.sub(r'[ \t]+', ' ', texto_completo)
        texto_completo = texto_completo.strip()
        
        # Validaciones críticas
        articulos_count = len(re.findall(r'Artículo \d+\.', texto_completo))
        
        print(f"\n📊 Validación preliminar:")
        print(f"   - Caracteres extraídos: {len(texto_completo):,}")
        print(f"   - Artículos detectados: {articulos_count}")
        
        if articulos_count < 650:
            raise ValueError(
                f"⚠️  ERROR CRÍTICO: Solo se detectaron {articulos_count} artículos.\n"
                f"   Se esperaban al menos 650 para el TRLC completo.\n"
                f"   El scraping del BOE no extrajo el texto completo.\n"
                f"   ABORTANDO ingesta."
            )
        
        if len(texto_completo) < 500000:
            print(f"   ⚠️  ADVERTENCIA: Texto corto ({len(texto_completo)} chars)")
            print(f"   El TRLC completo suele tener >1.000.000 caracteres")
        
        # Guardar texto extraído
        txt_filename = f"ley_concursal_boe_consolidado_trlc_{timestamp}.txt"
        txt_path = DOCS_DIR / txt_filename
        
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(texto_completo)
        
        print(f"\n💾 Texto extraído guardado: {txt_path}")
        
        # Actualizar metadata
        metadata = {
            "source": "BOE",
            "source_url": TRLC_URL,
            "type": "TRLC_completo",
            "law": "Real Decreto Legislativo 1/2020",
            "retrieved_at": datetime.now().isoformat(),
            "format": "html",
            "description": "TRLC consolidado completo desde BOE",
            "notes": "Texto consolidado completo sin recortes ni selección manual",
            "files": {
                "html": html_filename,
                "txt": txt_filename,
            },
            "stats": {
                "html_chars": len(html_content),
                "text_chars": len(texto_completo),
                "articles_detected": articulos_count,
            },
            "version_label": f"TRLC BOE consolidado {timestamp}",
        }
        
        with open(METADATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Metadata actualizada: {METADATA_FILE}")
        
        print("\n" + "="*80)
        print("✅ DESCARGA COMPLETADA")
        print("="*80)
        print(f"\nArchivos creados:")
        print(f"  - {html_path}")
        print(f"  - {txt_path}")
        print(f"  - {METADATA_FILE}")
        print(f"\n📊 Estadísticas:")
        print(f"  - HTML: {len(html_content):,} caracteres")
        print(f"  - Texto: {len(texto_completo):,} caracteres")
        print(f"  - Artículos: {articulos_count}")
        
        if articulos_count >= 650:
            print(f"\n✅ VALIDACIÓN EXITOSA: {articulos_count} artículos (>= 650)")
            print(f"\n🎯 Siguiente paso:")
            print(f"   python -m app.rag.legal_rag.ingest_legal --ley --overwrite")
            return txt_path
        else:
            raise ValueError(f"Validación falló: {articulos_count} < 650")
        
    except requests.RequestException as e:
        print(f"\n❌ Error de red: {e}")
        print(f"\n⚠️  El BOE puede estar bloqueando el scraping o la URL cambió.")
        print(f"\n📋 ALTERNATIVA MANUAL:")
        print(f"   1. Visitar: {TRLC_URL}")
        print(f"   2. Guardar la página completa como HTML")
        print(f"   3. Copiar a: {DOCS_DIR}/")
        print(f"   4. Ejecutar ingesta")
        raise
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    try:
        txt_path = download_trlc_completo()
        print(f"\n🎉 ¡Descarga exitosa!")
    except Exception as e:
        print(f"\n💥 Descarga falló: {e}")
        exit(1)

