#!/bin/bash
# Script para construir la imagen Docker de Phoenix Legal

set -e

echo "🐳 Construyendo imagen Docker de Phoenix Legal..."
echo ""

# Verificar que estamos en la carpeta docker/
if [ ! -f "Dockerfile" ]; then
    echo "❌ Error: Este script debe ejecutarse desde la carpeta docker/"
    echo "   Ejecuta: cd docker && bash build.sh"
    exit 1
fi

# Build
echo "📦 Construyendo imagen..."
docker compose build

echo ""
echo "✅ Imagen construida exitosamente"
echo ""
echo "Para iniciar el servicio:"
echo "  docker compose up -d"
echo ""

