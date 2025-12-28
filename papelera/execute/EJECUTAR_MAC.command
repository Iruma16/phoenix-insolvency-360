#!/bin/bash

# 1. Vamos a la carpeta donde está este archivo (execute)
cd "$(dirname "$0")"

# 2. IMPORTANTE: Subimos un nivel hacia arriba (al proyecto principal)
cd ..

echo "🦅 Iniciando Phoenix Legal..."

# Ahora ya podemos buscar venv y app.py normalmente
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "⚠️ Creando entorno virtual..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
fi

streamlit run app.py