# agentes/auditor/analisis.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

from core.selectors import seleccionar_movimientos_sospechosos
from core.matcher import cruzar_banco_facturas
from core.ingesta import extraer_datos_con_ia

load_dotenv()
client = OpenAI()

MAX_FACTURAS_IA = 10
MAX_PROMPT_ROWS = 50
MAX_PDF_CHARS_PROMPT = 4000


def analizar_financiero(texto_facturas: str, df_banco: pd.DataFrame) -> Tuple[str, Dict[str, Any]]:
    if df_banco is None or df_banco.empty:
        return "⚠️ No hay datos bancarios suficientes para realizar la auditoría.", {}

    # Selector forense (base objetiva)
    datos_forenses = seleccionar_movimientos_sospechosos(df_banco)
    if datos_forenses.get("total_registros", 0) == 0:
        return "⚠️ No se han detectado movimientos relevantes para análisis forense.", {}

    # Facturas estructuradas (best-effort)
    facturas_estructuradas: List[Dict[str, Any]] = []
    if texto_facturas:
        bloques = [b.strip() for b in texto_facturas.split("\n\n") if b.strip()]
        for bloque in bloques[:MAX_FACTURAS_IA]:
            factura = extraer_datos_con_ia(bloque)
            if factura and isinstance(factura, dict):
                facturas_estructuradas.append(factura)

    # Matcher objetivo
    pruebas_forenses = cruzar_banco_facturas(df_banco=df_banco, facturas=facturas_estructuradas)

    # Muestra controlada del banco (evita prompt gigante)
    muestra_banco = df_banco.head(MAX_PROMPT_ROWS).to_dict(orient="records")
    ocr_trunc = (texto_facturas or "")[:MAX_PDF_CHARS_PROMPT]

    prompt = f"""
Eres un auditor forense experto en insolvencias y Ley Concursal española.

REGLAS:
- Analiza SOLO lo que está en las fuentes.
- NO inventes datos.
- Si falta evidencia, dilo.

============================
MUESTRA BANCO (hasta {MAX_PROMPT_ROWS})
============================
{json.dumps(muestra_banco, indent=2, default=str, ensure_ascii=False)}

============================
SELECTOR FORENSE (HECHOS)
============================
{json.dumps(datos_forenses, indent=2, default=str, ensure_ascii=False)}

============================
CRUCE BANCO ↔ FACTURAS (PRUEBA)
============================
{json.dumps(pruebas_forenses, indent=2, default=str, ensure_ascii=False)}

============================
OCR FACTURAS (TRUNCADO)
============================
{ocr_trunc}

DEVUELVE Markdown con:
- 🚩 Banderas rojas (solo con prueba)
- 🧾 Pagos sin factura (si existen)
- 💸 Facturas sin pago (si existen)
- 📉 Diagnóstico de liquidez (solo con datos disponibles)
- ⚖️ Implicaciones legales preliminares (prudente)
- ✅ Recomendaciones de actuación
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        informe = resp.choices[0].message.content
        return informe, pruebas_forenses
    except Exception as e:
        return f"❌ Error en el análisis forense: {e}", pruebas_forenses
