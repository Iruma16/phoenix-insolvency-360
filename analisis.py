import sqlite3
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def analizar_fraude(facturas, asientos):
    prompt = f"""
    Eres un auditor forense experto en insolvencias (Ley Concursal).
    DATOS FACTURAS: {json.dumps(facturas)}
    DATOS CONTABILIDAD: {json.dumps(asientos)}
    
    TU MISIÓN:
    1. Busca coincidencias.
    2. ALERTA si hay facturas sin asiento contable.
    3. Analiza solvencia (Activo vs Pasivo).
    Devuelve un INFORME EJECUTIVO breve en Markdown.
    """
    respuesta = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return respuesta.choices[0].message.content