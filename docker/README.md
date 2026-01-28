# Phoenix Legal - Docker

Deployment completo con Docker y Docker Compose.

---

## 📋 Requisitos

- **Docker:** 20.10+
- **Docker Compose:** 2.0+
- **RAM:** 2GB mínimo
- **Disco:** 5GB espacio disponible

---

## 🚀 Inicio Rápido

### 1. Configurar variables de entorno

```bash
# Desde la raíz del proyecto
cp .env.example .env

# Editar y añadir OPENAI_API_KEY (opcional pero recomendado)
nano .env
```

### 2. Construir imagen

```bash
# Desde la carpeta docker/
cd docker
docker compose build
```

### 3. Iniciar servicio

```bash
docker compose up -d
```

### 4. Verificar

```bash
# Verificar que el servicio está corriendo
docker compose ps

# Verificar health
curl http://localhost:8000/health
```

**Acceso:** http://localhost:8000

---

## 📁 Estructura Docker

```
docker/
├── Dockerfile              # Imagen de la aplicación
├── docker-compose.yml      # Orquestación de servicios
├── .dockerignore          # Archivos excluidos del build
└── README.md              # Esta guía
```

**Build context:** Raíz del proyecto (`..`)  
**Dockerfile:** `docker/Dockerfile`

---

## ⚙️ Configuración

### Variables de Entorno

Configurar en archivo `.env` en la raíz del proyecto:

```bash
# OpenAI (opcional, pero recomendado para análisis LLM)
OPENAI_API_KEY=sk-...

# JWT Secret (OBLIGATORIO cambiar en producción)
JWT_SECRET_KEY=your_secure_random_secret_key_here

# Base de datos (SQLite por defecto)
DATABASE_URL=sqlite:///clients_data/phoenix_legal.db

# Configuración RAG
EMBEDDING_MODEL=text-embedding-3-small
RAG_TOP_K_DEFAULT=10
```

### Volúmenes Persistentes

```yaml
volumes:
  - ../app:/app/app                    # Hot reload en desarrollo
  - ../runtime:/app/runtime            # BD SQLite (local)
```

**Importante:** La BD SQLite persiste en `runtime/` en el host.

---

## 🔧 Comandos Útiles

### Gestión de Servicios

```bash
# Iniciar servicios
docker compose up -d

# Detener servicios
docker compose down

# Ver logs
docker compose logs -f

# Ver logs de un servicio específico
docker compose logs -f phoenix-legal

# Reiniciar servicios
docker compose restart
```

### Build y Rebuild

```bash
# Build inicial
docker compose build

# Rebuild (tras cambios en código)
docker compose build --no-cache

# Rebuild y reiniciar
docker compose up -d --build
```

### Inspección

```bash
# Ver estado de servicios
docker compose ps

# Ejecutar comando dentro del contenedor
docker compose exec phoenix-legal bash

# Ver uso de recursos
docker stats phoenix-legal-app
```

---

## 🧪 Ejecutar Tests

### Opción 1: Dentro del contenedor

```bash
docker compose exec phoenix-legal pytest tests/ -v
```

### Opción 2: Contenedor temporal

```bash
docker compose run --rm phoenix-legal pytest tests/ -v
```

### Opción 3: Tests específicos

```bash
# Tests de logging
docker compose exec phoenix-legal pytest tests/test_logging.py -v

# Tests E2E
docker compose exec phoenix-legal pytest tests/test_e2e_*.py -v
```

---

## 📊 Generación de Informes

### Desde dentro del contenedor

```bash
# Ejecutar análisis de un caso
docker compose exec phoenix-legal python scripts/generate_case_report.py CASE_001

# Ver informes generados
docker compose exec phoenix-legal ls -lh clients_data/cases/CASE_001/reports/
```

### Acceder a PDFs generados

Los informes se descargan vía endpoint `GET /api/cases/{case_id}/legal-report/pdf`.

---

## 🔍 Troubleshooting

### Puerto 8000 en uso

```bash
# Cambiar puerto en docker-compose.yml
ports:
  - "8001:8000"  # Usar 8001 en host
```

### Contenedor no inicia

```bash
# Ver logs
docker compose logs phoenix-legal

# Verificar variables de entorno
docker compose config

# Rebuild sin caché
docker compose build --no-cache
```

### Error de permisos en clients_data

```bash
# Desde el host, ajustar permisos
chmod -R 777 clients_data/

# O ejecutar con usuario específico
docker compose run --user $(id -u):$(id -g) phoenix-legal [comando]
```

### Healthcheck falla

```bash
# Verificar que el servicio responde
docker compose exec phoenix-legal curl http://localhost:8000/health

# Si curl no está disponible, instalarlo
docker compose exec phoenix-legal apt-get update && apt-get install -y curl
```

---

## 🏗️ Arquitectura del Contenedor

### Imagen Base

- **Base:** `python:3.9-slim`
- **Tamaño:** ~800MB
- **Compiladores:** gcc, g++ (para dependencias nativas)

### Estructura Interna

```
/app/
├── app/                 # Código de la aplicación
├── scripts/             # Scripts auxiliares
├── clients_data/        # Datos persistentes (volumen)
├── requirements.txt     # Dependencias Python
└── [otros archivos]
```

### Puerto Expuesto

- **8000:** API REST (FastAPI)

### Healthcheck

```yaml
test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
interval: 30s
timeout: 10s
retries: 3
start_period: 40s
```

---

## 🌐 Networking

### Red por Defecto

```yaml
networks:
  default:
    name: phoenix-legal-network
```

Todos los servicios se comunican dentro de `phoenix-legal-network`.

### Acceso desde Otros Contenedores

```yaml
services:
  otro-servicio:
    networks:
      - phoenix-legal-network
```

---

## 🔒 Seguridad

### Buenas Prácticas

1. **NO commitear `.env`** con claves reales
2. **Cambiar `JWT_SECRET_KEY`** en producción
3. **Usar secrets de Docker** para claves sensibles
4. **Limitar recursos:**

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
```

### Secrets de Docker (Producción)

```bash
# Crear secret
echo "sk-real-api-key" | docker secret create openai_api_key -

# Usar en docker-compose.yml
secrets:
  - openai_api_key

environment:
  - OPENAI_API_KEY_FILE=/run/secrets/openai_api_key
```

---

## 📈 Producción

### Recomendaciones

1. **Base de datos externa** (PostgreSQL en lugar de SQLite)
2. **Proxy reverso** (nginx, Traefik)
3. **HTTPS** con certificados válidos
4. **Backup** de `clients_data/`
5. **Monitoreo** (Prometheus, Grafana)
6. **Logs centralizados** (ELK, Loki)

### Ejemplo con PostgreSQL

```yaml
services:
  db:
    image: postgres:14
    environment:
      POSTGRES_DB: phoenix_legal
      POSTGRES_USER: phoenix
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  phoenix-legal:
    depends_on:
      - db
    environment:
      - DATABASE_URL=postgresql://phoenix:${DB_PASSWORD}@db:5432/phoenix_legal

volumes:
  postgres_data:
```

---

## 🔄 Actualización

### Actualizar código

```bash
# Pull cambios
git pull origin main

# Rebuild
cd docker
docker compose build --no-cache

# Reiniciar
docker compose up -d
```

### Migración de datos

```bash
# Backup antes de actualizar
tar -czf clients_data_backup_$(date +%Y%m%d).tar.gz ../clients_data/

# Restaurar si es necesario
tar -xzf clients_data_backup_YYYYMMDD.tar.gz
```

---

## 📚 Recursos

### Documentación Relacionada

- **README principal:** `../README.md`
- **API REST:** `../README_API.md`
- **UI Web:** `../README_UI.md`
- **Fase 2:** `../README_FASE2.md`

### Comandos de Referencia

```bash
# Build
cd docker && docker compose build

# Iniciar
docker compose up -d

# Logs
docker compose logs -f

# Tests
docker compose exec phoenix-legal pytest tests/ -v

# Bash dentro del contenedor
docker compose exec phoenix-legal bash

# Detener
docker compose down
```

---

## ✅ Checklist de Deployment

### Pre-deployment

- [ ] Configurar `.env` con claves reales
- [ ] Cambiar `JWT_SECRET_KEY`
- [ ] Verificar `OPENAI_API_KEY` (si se usa LLM)
- [ ] Backup de datos existentes
- [ ] Verificar puertos disponibles

### Deployment

- [ ] `docker compose build`
- [ ] `docker compose up -d`
- [ ] Verificar `docker compose ps`
- [ ] Verificar healthcheck: `curl http://localhost:8000/health`
- [ ] Ejecutar tests: `docker compose exec phoenix-legal pytest tests/test_fixtures.py -v`

### Post-deployment

- [ ] Verificar logs: `docker compose logs -f`
- [ ] Probar análisis de caso
- [ ] Verificar generación de PDF
- [ ] Configurar backup automático
- [ ] Configurar monitoreo (opcional)

---

**Phoenix Legal** — Deployment con Docker  
© 2024 — Sistema de Análisis Legal Automatizado

