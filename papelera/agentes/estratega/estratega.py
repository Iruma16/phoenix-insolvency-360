import os
from openai import OpenAI
from dotenv import load_dotenv

# Cargar entorno y cliente
load_dotenv()
client = OpenAI()

def generar_plan_viabilidad(datos_financieros, total_deuda, total_activos):
    """
    Agente 2: Estratega. 
    Analiza la solvencia y redacta una Hoja de Ruta Legal.
    """
    
    # Lógica básica de pre-análisis (para guiar a la IA)
    ratio_solvencia = total_activos / total_deuda if total_deuda > 0 else 0
    situacion = "INSOLVENCIA INMINENTE" if ratio_solvencia < 1 else "TENSION DE TESORERIA"
    
    prompt = f"""
    Eres el Agente Estratega de 'Phoenix Legal', un abogado experto en Derecho Concursal y Reestructuraciones.
    
    DATOS DEL CASO:
    - Situación Detectada: {situacion} (Cobertura de deuda: {ratio_solvencia:.2%})
    - Deuda Total Detectada: {total_deuda} EUR
    - Activos Líquidos (Aprox): {total_activos} EUR
    - Resumen de Irregularidades: {datos_financieros}
    
    TU MISIÓN:
    Redacta un INFORME DE ESTRATEGIA LEGAL (formato Markdown profesional).
    
    ESTRUCTURA OBLIGATORIA:
    ## 1. Diagnóstico Jurídico 🩺
    Explica claramente si el cliente cumple los requisitos para la Ley de Segunda Oportunidad o Concurso de Acreedores.
    
    ## 2. La Estrategia Recomendada 🛡️
    Elige UNA opción y arguméntala:
    A) PLAN DE REESTRUCTURACIÓN (Si ves viabilidad). Propón quitas y esperas.
    B) LIQUIDACIÓN CON SOLICITUD DE BEPI (Si no hay activos). Explica cómo pedir el perdón de las deudas.
    
    ## 3. Hoja de Ruta Inmediata 📅
    - Paso 1: (Ej: Solicitar preconcurso).
    - Paso 2: (Ej: Negociación con acreedores clave).
    - Paso 3: (Ej: Presentación en Juzgado Mercantil).
    
    ## 4. Conclusión para el Cliente
    Un mensaje final de tranquilidad y profesionalidad.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Eres un abogado senior, preciso y empático."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3 # Baja temperatura para ser riguroso
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"❌ Error en el Estratega: {e}"