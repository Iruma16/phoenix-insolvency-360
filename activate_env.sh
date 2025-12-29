#!/bin/bash
# Script para activar el entorno virtual .venv

cd "$(dirname "$0")"
source .venv/bin/activate
echo "✅ Entorno virtual .venv activado"
echo "   Python: $(which python)"
echo "   Versión: $(python --version)"

