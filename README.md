# Phoenix Legal (curso)

Phoenix Legal es un proyecto de curso para **análisis preliminar** de documentación concursal (TRLC). **No sustituye** el criterio profesional.

## Documentación (punto de entrada)

- **Deep dive técnico / handoff**: `DOCUMENTACION_TECNICA.md` (incluye flujo runtime “abriendo el capó”, mapa de endpoints y ejemplos `curl` end-to-end).
- **API (mini guía)**: `README_API.md`
- **UI (mini guía)**: `README_UI.md`
- **Docker (opcional)**: `docker/README.md`

## Camino oficial

- **API (FastAPI)**: `app/main.py` → `make run-api` (o `uvicorn app.main:app`)
- **UI (Streamlit)**: `app/ui/streamlit_mvp.py` → `make run-ui` (o `streamlit run app/ui/streamlit_mvp.py`)

## Requisitos

- Python **3.9+**

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
make install-dev
cp .env.example .env
```

## Ejecutar

```bash
# terminal 1
make run-api

# terminal 2
make run-ui
```

Comprobación rápida:

```bash
curl http://localhost:8000/
curl http://localhost:8000/health
```

## Orden recomendado para evaluación (revisor)

```bash
# 1) Quality gates (rápido y determinista)
make check

# 2) Runtime
make init-db
make run-api
make run-ui

# 3) Smoke por API (sin UI)
curl http://localhost:8000/
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/cases -H "Content-Type: application/json" -d '{"name":"Demo Case - Phoenix","client_ref":"DEMO-001"}'
```

## Configuración (`.env`)

- **Obligatorio**: `PHOENIX_API_BASE_URL` (por defecto `http://localhost:8000`)
- **Opcional**: `OPENAI_API_KEY` (si está vacío, el sistema funciona en modo degradado)

SQLite por defecto:

```bash
DATABASE_URL=sqlite:///./runtime/db/phoenix_legal.db
```

## Calidad

```bash
make check
```

## Datos

- `clients_data/legal/`: corpus legal versionado.
- `clients_data/cases/` y vectorstores: datos locales (no se versionan).
- `data/sample/`: archivos pequeños para demo (`make demo-data` prepara una copia en `data/demo_ready/`).

## Troubleshooting (rápido)

Si algo falla, la guía operativa completa está en `DOCUMENTACION_TECNICA.md` (sección “Troubleshooting técnico” y “Artefactos del runtime”).
