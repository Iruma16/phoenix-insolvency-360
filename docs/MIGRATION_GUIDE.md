# Guía de Migración a Phoenix Legal 2.0

Esta guía te ayudará a migrar de Phoenix Legal 1.0 a 2.0 con todas las nuevas mejoras implementadas.

---

## 📋 Resumen de Cambios

Phoenix Legal 2.0 incluye mejoras significativas en:
- ✅ Configuración (Pydantic Settings)
- ✅ Seguridad (JWT, rate limiting)
- ✅ Observabilidad (métricas Prometheus)
- ✅ Arquitectura (servicios, caché)
- ✅ Base de datos (PostgreSQL, Alembic)
- ✅ Testing (cobertura 70%+)

---

## 🚀 Pasos de Migración

### 1. Backup

```bash
# Backup de base de datos
cp runtime/db/phoenix_legal.db runtime/db/phoenix_legal.db.backup

# Backup de vectorstores
cp -r clients_data/_vectorstore clients_data/_vectorstore.backup
```

### 2. Actualizar Dependencias

```bash
# Activar entorno virtual
source .venv/bin/activate

# Actualizar pip
pip install --upgrade pip

# Instalar nuevas dependencias
pip install -r requirements.txt

# Para desarrollo
pip install -r requirements-dev.txt
```

### 3. Configurar Variables de Entorno

```bash
# Copiar template
cp .env.example .env

# Editar .env con tus valores
nano .env
```

**Variables críticas a configurar**:
```bash
# Producción
ENVIRONMENT=production
DATABASE_URL=postgresql://user:pass@localhost:5432/phoenix_legal
JWT_SECRET_KEY=tu_clave_secreta_muy_segura_aqui
OPENAI_API_KEY=sk-tu-api-key

# Desarrollo
ENVIRONMENT=development
DATABASE_URL=sqlite:///./runtime/db/phoenix_legal.db
```

### 4. Migraciones de Base de Datos

```bash
# Inicializar Alembic (primera vez)
alembic upgrade head

# Si ya tienes datos, crear migración inicial
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```

### 5. Verificar Instalación

```bash
# Verificar configuración
python -c "from app.core.config import print_config; print_config()"

# Verificar base de datos
python -c "from app.core.database import check_database_health; print(check_database_health())"

# Ejecutar tests
pytest -m unit
```

### 6. Migrar a PostgreSQL (Producción)

Si estás migrando de SQLite a PostgreSQL:

```bash
# 1. Instalar PostgreSQL
# Ubuntu/Debian:
sudo apt install postgresql postgresql-contrib

# macOS:
brew install postgresql

# 2. Crear base de datos
sudo -u postgres psql
CREATE DATABASE phoenix_legal;
CREATE USER phoenix_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE phoenix_legal TO phoenix_user;
\q

# 3. Exportar datos de SQLite
sqlite3 runtime/db/phoenix_legal.db .dump > export.sql

# 4. Adaptar dump para PostgreSQL (manual)
# Editar export.sql para compatibilidad

# 5. Importar a PostgreSQL
psql -U phoenix_user -d phoenix_legal -f export.sql

# 6. Actualizar .env
DATABASE_URL=postgresql://phoenix_user:your_password@localhost:5432/phoenix_legal
```

### 7. Iniciar Servidor

```bash
# Desarrollo
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Producción (con Gunicorn)
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 8. Verificar Funcionamiento

```bash
# Health check
curl http://localhost:8000/health

# Métricas
curl http://localhost:8000/metrics

# Documentación API
open http://localhost:8000/docs
```

---

## 🔄 Cambios en el Código

### Configuración

**Antes (v1.0)**:
```python
from app.core.variables import EMBEDDING_MODEL, RAG_TOP_K_DEFAULT

model = EMBEDDING_MODEL
top_k = RAG_TOP_K_DEFAULT
```

**Después (v2.0)**:
```python
from app.core.config import settings

model = settings.embedding_model
top_k = settings.rag_top_k
```

### Excepciones

**Antes (v1.0)**:
```python
if not case:
    raise Exception("Case not found")
```

**Después (v2.0)**:
```python
from app.core.exceptions import CaseNotFoundException

if not case:
    raise CaseNotFoundException(case_id=case_id)
```

### Servicios

**Antes (v1.0)**:
```python
# Lógica en endpoint
@app.post("/analyze")
def analyze(case_id: str, db: Session = Depends(get_db)):
    # ... 50 líneas de lógica ...
    return result
```

**Después (v2.0)**:
```python
# Lógica en servicio
from app.services.audit_service import AuditService

@app.post("/analyze")
def analyze(case_id: str, db: Session = Depends(get_db)):
    service = AuditService(db=db)
    return service.analyze_case(case_id)
```

### Seguridad

**Nuevo en v2.0**:
```python
from app.core.security import get_current_user, require_permission, Permission

@app.post("/analyze", dependencies=[Depends(require_permission(Permission.ANALYSIS_RUN))])
async def analyze(
    payload: AnalysisRequest,
    user = Depends(get_current_user)
):
    # Endpoint protegido
    pass
```

### Métricas

**Nuevo en v2.0**:
```python
from app.core.telemetry import track_analysis, track_llm_usage

with track_analysis("auditor"):
    result = run_auditor(case_id)

track_llm_usage("gpt-4o-mini", prompt_tokens=500, completion_tokens=200)
```

---

## 🧪 Testing

### Ejecutar Tests

```bash
# Todos los tests
pytest

# Solo tests rápidos
pytest -m unit

# Tests de integración
pytest -m integration

# Con cobertura
pytest --cov-report=html
open tests/coverage_html/index.html

# Tests en paralelo
pytest -n auto
```

### Escribir Nuevos Tests

**Ejemplo con fixtures**:
```python
import pytest
from app.core.database import get_db
from app.services.audit_service import AuditService

@pytest.fixture
def audit_service(db_session):
    return AuditService(db=db_session)

def test_analyze_case(audit_service):
    result = audit_service.analyze_case("CASE_001")
    assert result["status"] == "completed"
```

---

## 📊 Monitoreo

### Configurar Prometheus

**1. Crear `prometheus.yml`**:
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'phoenix-legal'
    static_configs:
      - targets: ['localhost:8000']
```

**2. Iniciar Prometheus**:
```bash
prometheus --config.file=prometheus.yml
```

**3. Acceder a UI**:
```
http://localhost:9090
```

### Configurar Grafana

**1. Instalar Grafana**:
```bash
# Docker
docker run -d -p 3000:3000 grafana/grafana

# macOS
brew install grafana
```

**2. Añadir Prometheus como datasource**:
- URL: `http://localhost:9090`

**3. Importar dashboards predefinidos**:
- Buscar "FastAPI" o "Python" en Grafana dashboards

---

## 🔐 Seguridad

### Generar JWT Secret

```python
import secrets
print(secrets.token_urlsafe(32))
# Copiar resultado a JWT_SECRET_KEY en .env
```

### Crear Usuario Admin

```python
from app.core.security import hash_password, create_access_token, UserRole

# En Python REPL
hashed = hash_password("admin_password")
print(hashed)

# Guardar en BD
# INSERT INTO users (username, password, role) VALUES ('admin', hashed, 'admin');

# Generar token
token = create_access_token("admin", UserRole.ADMIN)
print(token)
```

### Uso de Tokens

```bash
# Obtener token
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin_password"}'

# Usar token en requests
curl http://localhost:8000/v2/auditor/analyze \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"case_id": "CASE_001"}'
```

---

## 🐳 Docker (Opcional)

### Actualizar Docker Compose

El archivo `docker/docker-compose.yml` ya está actualizado con las nuevas variables.

```bash
cd docker
./build.sh
./start.sh
```

---

## ⚠️ Problemas Comunes

### Error: "Validation error for Settings"

**Causa**: Variable de entorno faltante

**Solución**:
```bash
python -c "from app.core.config import print_config; print_config()"
# Verificar qué variable falta
```

### Error: "No module named 'alembic'"

**Causa**: Dependencias no instaladas

**Solución**:
```bash
pip install -r requirements.txt
```

### Error: "Could not connect to database"

**Causa**: PostgreSQL no está corriendo o credenciales incorrectas

**Solución**:
```bash
# Verificar PostgreSQL
sudo systemctl status postgresql

# Verificar credenciales
psql -U phoenix_user -d phoenix_legal
```

### Error: "Rate limit exceeded"

**Causa**: Demasiados requests

**Solución temporal (desarrollo)**:
```bash
# En .env
RATE_LIMIT_ENABLED=false
```

### Error: "Token invalid"

**Causa**: Token expirado o secreto incorrecto

**Solución**:
```bash
# Generar nuevo token
python -c "from app.core.security import create_access_token, UserRole; print(create_access_token('user', UserRole.ANALYST))"
```

---

## 📈 Rollback (Si es necesario)

Si algo sale mal:

```bash
# 1. Restaurar base de datos
cp runtime/db/phoenix_legal.db.backup runtime/db/phoenix_legal.db

# 2. Restaurar vectorstores
cp -r clients_data/_vectorstore.backup clients_data/_vectorstore

# 3. Volver a v1.0
git checkout v1.0

# 4. Reinstalar dependencias
pip install -r requirements.txt
```

---

## ✅ Checklist de Migración

- [ ] Backup realizado
- [ ] Dependencias actualizadas
- [ ] Variables de entorno configuradas
- [ ] Migraciones de BD aplicadas
- [ ] Tests pasando
- [ ] Servidor inicia correctamente
- [ ] Health check OK
- [ ] Métricas accesibles
- [ ] Documentación API accesible
- [ ] PostgreSQL configurado (producción)
- [ ] JWT secret cambiado (producción)
- [ ] Monitoreo configurado

---

## 📞 Soporte

Si tienes problemas durante la migración:

1. Revisa logs: `clients_data/logs/phoenix_legal.log`
2. Ejecuta tests: `pytest -v`
3. Verifica configuración: `python -c "from app.core.config import print_config; print_config()"`
4. Contacta al equipo de desarrollo

---

**Éxito en la migración!** 🚀

