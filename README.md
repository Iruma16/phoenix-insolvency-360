# Phoenix Legal — Sistema de Análisis Legal Automatizado

**Versión**: 1.0.0  
**Estado**: MVP Funcional  
**Fecha**: 30 de diciembre de 2024

---

## ¿Qué es Phoenix Legal?

Phoenix Legal es un sistema automatizado de análisis legal para casos de insolvencia empresarial basado en el **TRLC (Texto Refundido de la Ley Concursal, RDL 1/2020)**.

Combina:
- **Heurísticas deterministas** para detección de riesgos
- **RAG (Retrieval Augmented Generation)** sobre corpus legal completo
- **Agentes LLM** (GPT-4) para razonamiento contextualizado
- **Rule Engine** con reglas legales automatizadas
- **Generación de informes PDF** profesionales con trazabilidad

---

## ¿Qué hace bien?

### ✅ Análisis Heurístico Robusto
- Detección de 4 tipos de riesgos core:
  - `delay_filing`: Retraso en solicitud de concurso
  - `document_inconsistency`: Inconsistencias documentales
  - `documentation_gap`: Falta de documentación crítica
  - `accounting_red_flags`: Irregularidades contables
- Extracción automática de timeline de eventos
- Asignación de severidad basada en keywords y tipos de documento

### ✅ RAG Legal Completo
- **TRLC completo**: ~700 artículos, 800+ chunks embedidos
- Vectorstore persistente (ChromaDB)
- Recuperación semántica por concepto legal
- Sin contaminación entre casos y corpus legal

### ✅ Agentes LLM Híbridos
- **Auditor LLM**: Analiza documentación y timeline con contexto RAG de casos
- **Prosecutor LLM**: Razona sobre riesgos con contexto RAG legal (TRLC)
- **Opcionales**: Funcionan sin API key (modo degradado)
- **No inventan**: Validación anti-alucinación integrada

### ✅ Rule Engine Legal
- Rulebook JSON con 5 reglas TRLC iniciales
- Evaluación segura de expresiones lógicas
- Mapeo automático a artículos del TRLC
- Extensible sin tocar código

### ✅ Generación de PDF Profesional
- Portada, resumen ejecutivo, hechos, hallazgos
- Artículos TRLC relevantes con trazabilidad
- Evidencias vinculadas a fuentes (caso + ley)
- Disclaimer legal
- Guardado automático en `clients_data/cases/{case_id}/reports/`

### ✅ API REST
- 5 endpoints funcionales:
  - `POST /cases`: Crear caso
  - `POST /cases/{case_id}/documents`: Subir documentos
  - `POST /cases/{case_id}/analyze`: Ejecutar análisis
  - `GET /cases/{case_id}/reports/latest`: Descargar PDF
  - `GET /health`: Health check
- Documentación: `README_API.md`

### ✅ Tests Robustos
- 70+ tests passing
- E2E para RAG de casos, RAG legal, integración
- Tests unitarios para agentes, rule engine, API
- Fixtures validados (`CASE_RETAIL_001`, `002`, `003`)

---

## ¿Qué NO hace?

### ⚠️ Limitaciones Actuales

1. **No es un sistema de gestión de casos**  
   No incluye UI, autenticación, ni gestión de usuarios.

2. **No sustituye criterio profesional**  
   Es una herramienta de apoyo, no un dictamen legal vinculante.

3. **No analiza jurisprudencia aún**  
   El RAG legal está preparado pero solo contiene TRLC (no sentencias).

4. **No calcula plazos automáticamente**  
   Detecta posibles retrasos pero no calcula fechas límite.

5. **No genera estrategias procesales**  
   Identifica riesgos y recomienda verificaciones, no estrategias completas.

6. **Dependiente de calidad de documentación**  
   Si faltan documentos críticos, el análisis será limitado.

---

## ¿Qué está listo para producción?

### ✅ Listo para Uso Interno

- **Análisis completo de casos** (heurísticas + LLM + rule engine)
- **Generación de PDF** profesional
- **RAG legal** (TRLC completo)
- **API REST** funcional
- **Tests E2E** validados

### ⚠️ Experimental / En Desarrollo

- **Agentes LLM**: Funcionales pero mejorables (prompts, RAG integration)
- **Rule Engine**: 5 reglas iniciales, requiere expansión
- **PDF con análisis LLM**: Estructura lista, falta integración visual

### ✅ Listo para Producción Externa (Fase 2)

- **Autenticación JWT** (admin/user roles)
- **Logging estructurado** (JSON para auditoría)
- **Monitoreo** y métricas en tiempo real
- **Docker** y deployment automatizado (`docker/`)
- **UI web** (Streamlit MVP)

### ⚠️ Pendiente para Escalabilidad

- **Caché de embeddings** (regeneración lenta para casos grandes)
- **Multi-tenant** (aislamiento de datos por cliente)
- **Queue de análisis** (procesamiento asíncrono)

---

## Instalación

### Requisitos

- Python 3.9+
- SQLite 3
- OpenAI API key (opcional, para LLM)

### Setup

```bash
# Clonar repositorio
git clone [...]
cd phoenix-legal

# Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env y añadir OPENAI_API_KEY (opcional)

# Inicializar base de datos
python -m app.core.init_db

# Verificar instalación
pytest tests/ -v
```

---

## Uso

### Opción 1: Línea de comandos

```bash
# Analizar caso existente
python scripts/generate_case_report.py CASE_RETAIL_001

# El PDF se genera en:
# clients_data/cases/CASE_RETAIL_001/reports/phoenix_legal_report_CASE_RETAIL_001_YYYYMMDD_HHMMSS.pdf
```

### Opción 2: API REST

```bash
# Iniciar servidor
python app/api/public.py

# En otra terminal:
# Crear caso
curl -X POST http://localhost:8000/cases \
  -H "Content-Type: application/json" \
  -d '{"case_id": "CASE_001", "company_name": "Empresa SL"}'

# Subir documentos
curl -X POST http://localhost:8000/cases/CASE_001/documents \
  -F "file=@balance.pdf"

# Analizar
curl -X POST http://localhost:8000/cases/CASE_001/analyze

# Descargar PDF
curl http://localhost:8000/cases/CASE_001/reports/latest \
  --output informe.pdf
```

Ver documentación completa en `README_API.md`.

---

## Arquitectura

```
phoenix-legal/
├── app/
│   ├── agents/          # Rule engine legal (reglas TRLC)
│   ├── agents_llm/      # Agentes LLM (Auditor, Prosecutor)
│   ├── api/             # API REST (FastAPI)
│   ├── core/            # Database, variables, init
│   ├── fixtures/        # Casos de prueba
│   ├── graphs/          # LangGraph (flujo de análisis)
│   ├── legal/           # Rulebook JSON, mapeo legal
│   ├── rag/             # RAG de casos y legal
│   └── reports/         # Generación de PDF
├── clients_data/
│   ├── cases/           # Datos de casos (por case_id)
│   ├── legal/           # Corpus legal (TRLC)
│   └── _vectorstore/    # Embeddings (ChromaDB)
├── scripts/             # Scripts de utilidad
└── tests/               # Tests (unitarios, E2E)
```

### Flujo de Análisis

```
ingest_documents
    ↓
analyze_timeline
    ↓
detect_risks (heurísticas)
    ↓
legal_hardening (findings con peso)
    ↓
auditor_llm (análisis documental con RAG casos)
    ↓
rule_engine (reglas TRLC automatizadas)
    ↓
prosecutor_llm (razonamiento legal con RAG TRLC)
    ↓
legal_article_mapper (mapeo a artículos)
    ↓
build_report (PDF final)
```

---

## Configuración

### Variables de Entorno (`.env`)

```bash
# Base de datos
DATABASE_URL=sqlite:///clients_data/phoenix_legal.db

# OpenAI (opcional, para LLM)
OPENAI_API_KEY=sk-...

# Embedding model
EMBEDDING_MODEL=text-embedding-3-small

# RAG
RAG_TOP_K_DEFAULT=10
```

### Rulebook JSON

Ubicación: `app/legal/rulebook/trlc_rules.json`

Estructura:
```json
{
  "metadata": {
    "version": "1.0.0",
    "source": "TRLC (RDL 1/2020)"
  },
  "rules": [
    {
      "rule_id": "TRLC_ART5_DELAY_FILING",
      "risk_type": "delay_filing",
      "article_refs": ["Art. 5 TRLC", "Art. 443 TRLC"],
      "trigger": {
        "condition": "detectado_delay_filing == true"
      },
      "severity_logic": {
        "high": "tiene_riesgo_alto == true",
        "medium": "tiene_riesgo_medio == true",
        "low": "true"
      },
      "confidence_logic": {
        "high": "tiene_acta == true AND tiene_balance == true",
        "medium": "tiene_acta == true OR tiene_balance == true",
        "low": "true"
      },
      "outputs": {
        "description_template": "...",
        "recommendation_template": "..."
      }
    }
  ]
}
```

---

## Testing

```bash
# Todos los tests
pytest tests/ -v

# Solo E2E
pytest tests/test_e2e*.py -v

# Solo agentes LLM (requiere API key)
pytest tests/test_*llm*.py -v

# Con reporte HTML
pytest tests/ --html=tests/report.html
```

---

## Extensión

### Añadir Nueva Regla Legal

1. Editar `app/legal/rulebook/trlc_rules.json`
2. Añadir nueva regla con estructura completa
3. Ejecutar tests: `pytest tests/test_rule_engine*.py -v`

### Añadir Nuevo Tipo de Riesgo

1. Modificar `app/graphs/nodes.py` (función `detect_risks`)
2. Añadir lógica heurística
3. Actualizar fixtures en `app/fixtures/audit_cases.py`
4. Crear tests en `tests/`

### Añadir Nuevo Agente LLM

1. Crear `app/agents_llm/nuevo_agente.py`
2. Implementar clase con método `analyze()`
3. Crear nodo en `app/graphs/nodes_llm.py`
4. Integrar en `app/graphs/audit_graph.py`
5. Crear tests en `tests/test_nuevo_agente.py`

---

## Troubleshooting

### Error: "OPENAI_API_KEY no definida"

**Solución**: El sistema funciona sin API key (modo degradado). Los agentes LLM se deshabilitarán automáticamente.

### Error: "Rulebook no encontrado"

**Solución**: Verificar que existe `app/legal/rulebook/trlc_rules.json`.

### Error: "No se pudo consultar RAG"

**Solución**: Verificar que existen embeddings en `clients_data/_vectorstore/`.

### PDF vacío o muy pequeño

**Solución**: Verificar que el análisis generó hallazgos. Revisar logs del grafo.

---

## Roadmap

### Corto Plazo (1-2 semanas)

- [ ] Integrar análisis LLM en PDF (secciones visibles)
- [ ] Expandir rulebook a 20-30 reglas TRLC
- [ ] Tests E2E con LLM real (marcados como `@slow`)
- [x] Docker y docker-compose (en `docker/`)

### Medio Plazo (1-2 meses)

- [ ] UI web (dashboard de casos)
- [ ] Autenticación (JWT)
- [ ] Logging estructurado (loguru)
- [ ] Monitoreo (métricas de uso)
- [ ] Caché de embeddings

### Largo Plazo (3-6 meses)

- [ ] Jurisprudencia en RAG legal
- [ ] Análisis de plazos procesales
- [ ] Generación de estrategias
- [ ] Integración con sistemas de gestión

---

## Contribución

Este es un proyecto interno. Para contribuir:

1. Crear rama desde `main`
2. Implementar cambios con tests
3. Ejecutar `pytest tests/ -v` (todos deben pasar)
4. Pull request con descripción clara

---

## Licencia

Propietario: [Tu Organización]  
Uso interno exclusivo.

---

## Contacto

Para soporte técnico o consultas:
- Email: [...]
- Slack: [...]

---

## Changelog

### v1.0.0 (2024-12-30)

**Añadido**:
- Agentes LLM (Auditor, Prosecutor) con RAG
- Rule Engine con rulebook JSON
- API REST (5 endpoints)
- Generación de PDF con trazabilidad
- RAG legal completo (TRLC ~700 arts)
- 70+ tests E2E y unitarios

**Mejorado**:
- Heurísticas de detección de riesgos
- Legal hardening con pesos y contra-evidencia
- Mapeo de artículos TRLC

**Corregido**:
- Error en rule engine (validación de tipos)
- Fixtures actualizados con campos nuevos
- Requirements.txt completo

---

**Phoenix Legal** — Análisis legal automatizado con IA para casos de insolvencia.
