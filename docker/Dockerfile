# Dockerfile para Phoenix Legal
FROM python:3.9-slim

# Metadata
LABEL maintainer="Phoenix Legal Team"
LABEL description="Sistema de análisis legal automatizado para casos de insolvencia"

# Variables de entorno
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements desde raíz del proyecto
COPY requirements.txt .

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación desde raíz
COPY app/ ./app/

# Crear directorios necesarios
RUN mkdir -p runtime/db

# Exponer puerto para API
EXPOSE 8000

# Comando por defecto: iniciar API
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

