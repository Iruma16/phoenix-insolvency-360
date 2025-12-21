import os
from dotenv import load_dotenv
from openai import OpenAI

# 1. Cargar las claves del archivo .env que acabas de crear
load_dotenv()

# 2. Configurar el cliente de OpenAI con tu clave
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

print("🤖 PHOENIX LEGAL: Conectando con el cerebro...")

# 3. Hacer una llamada de prueba a la IA
try:
    completion = client.chat.completions.create(
        model="gpt-4o-mini",  # Usamos el modelo rápido y barato
        messages=[
            {"role": "system", "content": "Eres un asistente legal experto y eficiente."},
            {"role": "user", "content": "Saluda a mi jefa, Iruma, y confirma que el sistema Backend está operativo."}
        ]
    )

    # 4. Imprimir la respuesta
    respuesta = completion.choices[0].message.content
    print("\n✅ ÉXITO. La IA dice:\n")
    print(respuesta)
    print("\n-----------------------------------")

except Exception as e:
    print(f"\n❌ ERROR de conexión: {e}")
    print("Consejo: Revisa que tengas saldo en OpenAI y que la clave en .env sea correcta.")