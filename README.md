# Phoenix Insolvency 360

Sistema de análisis legal para procedimientos concursales.

## Instalación

1. Crear entorno virtual:
```bash
python3 -m venv .venv
```

2. Activar entorno virtual:
```bash
source .venv/bin/activate
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

## Ejecución del Servidor

### Opción 1: Usando el script (recomendado)
```bash
./run_server.sh
```

### Opción 2: Comando manual
```bash
source .venv/bin/activate
uvicorn app.main:app --reload --reload-dir app
```

**Importante**: Usa `--reload-dir app` para monitorear solo el directorio `app/` y evitar recargas innecesarias cuando cambien archivos en `.venv/`.

El servidor estará disponible en: http://127.0.0.1:8000

## Estructura del Proyecto

```
app/
├── agents/          # Agentes de análisis
│   ├── agent_1_auditor/
│   └── agent_2_prosecutor/
├── api/             # Endpoints FastAPI
├── core/            # Configuración y base de datos
├── graphs/          # Grafos LangGraph
├── models/          # Modelos de datos
└── services/       # Servicios de negocio
```

