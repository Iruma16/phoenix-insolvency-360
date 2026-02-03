#!/bin/bash
# Script para detener Phoenix Legal

set -e

echo "🛑 Deteniendo Phoenix Legal..."
echo ""

# Verificar que estamos en la carpeta docker/
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Error: Este script debe ejecutarse desde la carpeta docker/"
    echo "   Ejecuta: cd docker && bash stop.sh"
    exit 1
fi

# Detener servicios
docker compose down

echo ""
echo "✅ Phoenix Legal detenido"
echo ""

