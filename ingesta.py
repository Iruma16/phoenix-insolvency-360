import pdfplumber
from openai import OpenAI
from dotenv import load_dotenv
import json
from datetime import datetime

load_dotenv()
client = OpenAI()

# --- ESTA ES LA FUNCIÓN QUE TE FALTABA ---
def leer_pdf(ruta_archivo):
    print(f"📄 Leyendo PDF: {ruta_archivo}...")
    texto_completo = ""
    try:
        with pdfplumber.open(ruta_archivo) as pdf:
            for pagina in pdf.pages:
                texto_extracto = pagina.extract_text()
                if texto_extracto:
                    texto_completo += texto_extracto + "\n"
        return texto_completo
    except Exception as e:
        print(f"❌ Error leyendo PDF: {e}")
        return None
# -----------------------------------------

def normalizar_fecha(fecha_str):
    """Convierte cualquier fecha a YYYY-MM-DD para la base de datos."""
    if not fecha_str:
        return None
        
    formatos_posibles = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d"]
    
    for fmt in formatos_posibles:
        try:
            return datetime.strptime(fecha_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
            
    print(f"⚠️ AVISO: No se pudo normalizar la fecha '{fecha_str}'.")
    return fecha_str

def validar_datos(datos):
    """Limpia números y fechas."""
    try:
        # Limpieza de Números
        datos['total_factura'] = float(datos.get('total_factura', 0))
        datos['base_imponible'] = float(datos.get('base_imponible', 0))
        datos['iva_total'] = float(datos.get('iva_total', 0))
        
        # Limpieza de Fechas
        fecha_sucia = datos.get('fecha_emision', '')
        datos['fecha_emision'] = normalizar_fecha(fecha_sucia)
        
        return datos
    except ValueError:
        print("❌ Error de Validación: Datos corruptos.")
        return None

def extraer_datos_con_ia(texto_factura):
    print("🧠 Analizando con IA (Modo Determinista)...")
    
    prompt_sistema = """
    Eres un experto contable. Extrae datos y devuelve JSON estricto.
    Intenta siempre devolver la fecha en formato YYYY-MM-DD.
    Si un número no es claro, pon 0.0.
    
    Campos requeridos:
    - numero_factura (string)
    - fecha_emision (string)
    - proveedor (string)
    - cif_proveedor (string)
    - base_imponible (float)
    - iva_total (float)
    - total_factura (float)
    - concepto (string)
    - estado_pago (string)
    """

    try:
        respuesta = client.chat.completions.create(
            model="gpt-4o",
            temperature=0, # Determinismo máximo
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": f"Analiza:\n{texto_factura}"}
            ],
            response_format={"type": "json_object"}
        )
        content = respuesta.choices[0].message.content
        datos_json = json.loads(content)
        
        # Validación final
        return validar_datos(datos_json)
        
    except Exception as e:
        print(f"❌ Error IA: {e}")
        return None