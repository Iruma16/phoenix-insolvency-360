# core/ingesta.py
import pdfplumber
from openai import OpenAI
from dotenv import load_dotenv
import json
from datetime import datetime
from typing import Optional, Dict, Any

load_dotenv()
client = OpenAI()


def extraer_texto_pdf(archivo_stream) -> str:
    """
    Lee texto de un PDF subido via Streamlit (UploadedFile).
    """
    texto_completo = ""
    try:
        # Streamlit UploadedFile funciona directo con pdfplumber
        with pdfplumber.open(archivo_stream) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    texto_completo += t + "\n"
        return texto_completo
    except Exception as e:
        print(f"❌ Error leyendo PDF: {e}")
        return ""


def normalizar_fecha(fecha_str: str) -> Optional[str]:
    if not fecha_str:
        return None

    formatos = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"]
    for fmt in formatos:
        try:
            return datetime.strptime(fecha_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return fecha_str


def validar_datos(datos: Dict[str, Any]) -> Dict[str, Any]:
    # números
    for campo in ["total_factura", "base_imponible", "iva_total"]:
        v = datos.get(campo, 0)
        if isinstance(v, str):
            s = v.replace("€", "").replace(" ", "").replace(".", "").replace(",", ".")
            try:
                datos[campo] = float(s)
            except Exception:
                datos[campo] = 0.0
        else:
            try:
                datos[campo] = float(v)
            except Exception:
                datos[campo] = 0.0

    # fecha
    datos["fecha_emision"] = normalizar_fecha(str(datos.get("fecha_emision", "")).strip()) or None
    return datos


def extraer_datos_con_ia(texto_factura: str) -> Optional[Dict[str, Any]]:
    """
    GPT-4o -> JSON estructurado.
    Best-effort: si no puede, devuelve None.
    """
    if not texto_factura or len(texto_factura.strip()) < 20:
        return None

    prompt_sistema = (
        "Eres un experto contable. Extrae datos clave de una factura y devuelve SOLO un JSON válido.\n"
        "CAMPOS REQUERIDOS:\n"
        "- numero_factura (string)\n"
        "- fecha_emision (string, formato YYYY-MM-DD)\n"
        "- proveedor (string)\n"
        "- cif_proveedor (string)\n"
        "- base_imponible (float)\n"
        "- iva_total (float)\n"
        "- total_factura (float)\n"
        "- concepto_principal (string)\n"
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=0,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": f"Texto de la factura:\n{texto_factura}"},
            ],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        data = json.loads(content)
        return validar_datos(data) if isinstance(data, dict) else None
    except Exception as e:
        print(f"❌ Error IA Ingesta: {e}")
        return None
