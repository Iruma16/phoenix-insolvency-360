#!/bin/bash
# Script de instalación para Fase 2 de Phoenix Legal

set -e

echo "🔧 Instalando dependencias de Fase 2..."
echo ""

# Activar entorno virtual
if [ -d ".venv" ]; then
    echo "✅ Activando entorno virtual..."
    source .venv/bin/activate
else
    echo "❌ Error: No se encontró .venv"
    echo "   Ejecuta primero: python -m venv .venv"
    exit 1
fi

# Instalar dependencias
echo ""
echo "📦 Instalando paquetes..."
pip install --upgrade pip -q
pip install streamlit -q
pip install 'passlib[bcrypt]' -q
pip install 'python-jose[cryptography]' -q
pip install PyJWT -q

echo ""
echo "✅ Dependencias instaladas"
echo ""

# Verificar instalación
echo "🧪 Verificando instalación..."
python -c "
import streamlit
import passlib
import jose
import jwt
print('✅ streamlit:', streamlit.__version__)
print('✅ passlib: OK')
print('✅ python-jose: OK')
print('✅ PyJWT:', jwt.__version__)
"

echo ""
echo "🎉 Instalación completada"
echo ""
echo "Para iniciar la UI web:"
echo "  streamlit run app/ui/streamlit_app.py"
echo ""

