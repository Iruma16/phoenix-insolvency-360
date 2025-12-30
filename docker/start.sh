#!/bin/bash
# Script para iniciar Phoenix Legal con Docker

set -e

echo "🚀 Iniciando Phoenix Legal..."
echo ""

# Verificar que estamos en la carpeta docker/
if [ ! -f "docker-compose.yml" ]; then
    echo "❌ Error: Este script debe ejecutarse desde la carpeta docker/"
    echo "   Ejecuta: cd docker && bash start.sh"
    exit 1
fi

# Verificar si la imagen existe
if ! docker images | grep -q "phoenix-legal"; then
    echo "⚠️  Imagen no encontrada. Construyendo..."
    docker compose build
fi

# Iniciar servicios
echo "🐳 Iniciando servicios..."
docker compose up -d

echo ""
echo "✅ Phoenix Legal iniciado"
echo ""
echo "Acceso: http://localhost:8000"
echo ""
echo "Ver logs:"
echo "  docker compose logs -f"
echo ""
echo "Detener:"
echo "  docker compose down"
echo ""

