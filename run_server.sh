#!/bin/bash
# Script para ejecutar el servidor FastAPI con uvicorn
# Solo monitorea el directorio app/ para evitar recargas innecesarias

cd "$(dirname "$0")"
source .venv/bin/activate
uvicorn app.main:app --reload --reload-dir app

