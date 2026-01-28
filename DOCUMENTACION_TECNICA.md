# Phoenix Legal (curso) — Documentación técnica

## 1. Visión General del Sistema

Phoenix Legal es un sistema de análisis preliminar de documentación asociada a un caso concursal. Integra extracción/normalización de documentos, heurísticas deterministas, recuperación semántica (RAG) y componentes LLM opcionales para producir salidas auditables (hallazgos, trazas y reportes).

### Problema que resuelve

- **Ingesta y normalización**: Recepción de ficheros heterogéneos (PDF, Office, texto, email) y persistencia de su contenido y metadatos para poder analizarlos de forma homogénea.
- **Evaluación preliminar**: Generación de señales (riesgos, timeline, inconsistencias) y de un artefacto de salida (informe/report) que consolida resultados en un formato legible.
- **Consulta contextual**: Capacidad de responder a una pregunta sobre un caso usando recuperación semántica sobre chunks del propio caso (RAG de caso) y, opcionalmente, sobre un corpus legal (RAG legal).

### Alcance funcional (qué hace / qué no hace)

- **Hace**:
  - Gestión de casos y documentos vía API (`app/main.py`, routers en `app/api/`).
  - UI Streamlit conectada a API para operación de demo (`app/ui/streamlit_mvp.py`).
  - Pipeline de chunking y embeddings para RAG con persistencia (SQL + ChromaDB).
  - RAG legal sobre Ley Concursal (y soporte para jurisprudencia si existe corpus preparado).
  - Ejecución de “agentes” (Auditor, Prosecutor, Legal) que consumen RAG y generan outputs estructurados.
  - Generación de reportes (Markdown/PDF) desde resultados del análisis.
  - Validaciones/contratos (p. ej. contrato de chunks y ubicación) y tests automatizados.

- **No hace** (por diseño del contexto de curso):
  - No elimina la necesidad de revisión humana: el sistema genera análisis preliminar, no dictamen.
  - No garantiza disponibilidad de LLM: puede operar en modo degradado por política o ausencia de API key.
  - No versiona ni publica datos reales: `clients_data/` es runtime local y se ignora en git.

### Por qué UI + API + services

Separar UI (Streamlit) y API (FastAPI) permite:

- **Separación de responsabilidades**: la UI gestiona interacción y render; la API expone operaciones y orquesta servicios; la lógica de negocio vive en `app/services/` y `app/agents/`.
- **Testabilidad**: la API y servicios pueden probarse sin UI (tests de endpoints y unit tests).
- **Evolución**: la UI puede cambiar sin modificar contratos internos (endpoints); la API puede evolucionar con versionado de routers y contratos.

### Qué se demuestra a nivel de ingeniería

- **Orquestación de análisis**: grafo de ejecución (LangGraph) para pipeline de auditoría (`app/graphs/`).
- **RAG con controles**: umbrales, evidencia, políticas de no-respuesta y versionado del vectorstore.
- **Operación con costes (FinOps)**: entry points obligatorios para operaciones con coste y control de presupuesto/cache (`app/core/finops/`).
- **Degradación controlada**: ejecución LLM centralizada que nunca rompe el sistema por fallos externos (`app/services/llm_executor.py`).

## 2. Arquitectura Técnica

### Diagrama lógico (descrito en texto)

Flujo lógico de runtime:

```
UI (Streamlit) -> API (FastAPI) -> Services -> Models/DB/Vectorstores -> Outputs
        |               |             |              |                 |
        |               |             |              |                 +-> PDF/Report endpoints
        |               |             |              +-> SQLite/PostgreSQL (SQLAlchemy)
        |               |             +-> Chunking/Embeddings/RAG/Analysis
        |               +-> Routers /api/* (cases, documents, reports, timeline, auth, etc.)
        +-> Cliente HTTP (PhoenixLegalClient) y componentes de render
```

Flujo de “agentes”:

```
Auditor (agent_1) --handoff--> Prosecutor (agent_2)
            \
             +-> Legal agent (agent_legal) con RAG legal
```

### Capas y responsabilidades

- **UI (`app/ui/`)**:
  - Cliente HTTP hacia la API (`app/ui/api_client.py`).
  - Composición de pantallas y componentes (`app/ui/components*.py`, `app/ui/components_modules/`).
  - Validación de precondiciones de demo (por ejemplo, `PHOENIX_API_BASE_URL`).

- **API (`app/main.py`, `app/api/`)**:
  - Enrutado HTTP y contratos de entrada/salida.
  - Coordinación de servicios (por ejemplo: crear/listar casos, subir documentos, generar reportes, timeline).
  - Exposición de endpoints de agentes (`/auditor/run`, `/prosecutor/run-from-auditor`, `/legal/analyze`).

- **Services (`app/services/`)**:
  - Lógica de negocio reutilizable y testable.
  - Ingesta, parsing, validación, chunking, embeddings, duplicados, timeline, report building, etc.
  - “Puertas” de ejecución para dependencias externas (LLM executor, FinOps entrypoints).

- **Models (`app/models/`)**:
  - Persistencia y contratos (SQLAlchemy) para casos, documentos, chunks, riesgos, timeline, etc.
  - Contratos duros (p. ej. `DocumentChunk` con ubicación obligatoria: offsets y método de extracción).

- **Graphs (`app/graphs/`)**:
  - Definición del grafo de auditoría (LangGraph) y sus nodos.
  - Separación entre estado legacy y validaciones/normalización (módulos `state*`, `validated_nodes.py`).

- **RAG (`app/rag/`)**:
  - RAG de casos (`app/rag/case_rag/`) con gates de calidad, evidencia y versionado de embeddings.
  - RAG legal (`app/rag/legal_rag/`) con vectorstore persistente y normalización de resultados.

- **Reports (`app/reports/`)**:
  - Construcción de payload, render y artefactos PDF (módulos `app/reports/pdf/*`).
  - Generación de reportes desde outputs de agentes (`app/reports/report_generator.py`).

### Flujo de datos end-to-end (UI → API → services → modelos → salida)

Camino típico de demo (simplificado):

1. **UI** solicita `GET /` para validar disponibilidad del backend (`PhoenixLegalClient.health_check()`).
2. **UI** crea/lista casos y selecciona `case_id`.
3. **UI** sube documentos → **API** recibe multipart y delega en servicios de ingesta.
4. **Services** persisten:
   - **Documento** (metadatos + `storage_path`).
   - **Chunks** (SQL) con contrato de ubicación.
   - **Vectorstore** (Chroma) con embeddings versionados y puntero ACTIVE.
5. **UI** solicita análisis (financiero, alertas, timeline, duplicados, reportes) y renderiza.
6. **API** expone descarga de PDF y endpoints de reporte.

Beneficio principal: cada etapa es invocable vía API y verificable con tests de endpoint/contrato.

### Runtime end-to-end (flujo real “abriendo el capó”)

Este apartado describe el camino **real** de ejecución para el caso más representativo en la demo: **crear caso → subir documentos → materializar chunks/embeddings → ejecutar consulta RAG / agentes → generar informe/PDF**. Se documenta en términos de **inputs, decisiones, side effects (DB/FS/vectorstore), invariantes y fallos**.

#### Paso 0 — Arranque y precondiciones

- **API**: `uvicorn app.main:app --reload --port 8000` (`make run-api`)
  - **Side effects**:
    - DB: inicializa engine y session factory (lazy) (`app/core/database.py`), con WAL/pragmas en SQLite.
  - **Invariantes**:
    - `DATABASE_URL` resoluble.
- **UI**: `streamlit run app/ui/streamlit_mvp.py` (`make run-ui`)
  - **Inputs**:
    - `PHOENIX_API_BASE_URL` (obligatorio) leído desde env (`app/ui/streamlit_mvp.py`).
  - **Fallos**:
    - Error inmediato en UI si falta `PHOENIX_API_BASE_URL`.

#### Paso 1 — Health check

- **Endpoints**:
  - `GET /` (root; usado por la UI como “health check lógico” y discovery de endpoints).
  - `GET /health` (healthcheck simple para Docker/CI).
- **Objetivo**: disponibilidad del backend (liveness) y descubrimiento rápido.
- **Outputs esperados**:
  - `/` → incluye `status: "running"` y `endpoints: {...}`.
  - `/health` → `{"status":"healthy"}`.

#### Paso 2 — Crear caso

- **Endpoint**: `POST /api/cases` (router `app/api/cases.py`, prefix `/api` en `app/main.py`)
- **Input (modelo)**: `CreateCaseRequest` (Pydantic; `app/models/case_summary.py`).
- **Código**:
  - Router crea `Case(name, client_ref, status, created_at, updated_at)` y hace `db.commit()` (`app/api/cases.py`).
- **Side effects**:
  - DB: inserta fila en `cases` (PK `case_id` UUID v4 autogenerado en modelo `Case`).
  - FS: no crea estructura de caso aquí (la estructura de almacenamiento se materializa en ingesta).
- **Invariantes**:
  - `Case.case_id` es UUID (string 36); `Case.name` no nulo.
- **Errores**:
  - `422` si el payload no cumple el schema Pydantic.

#### Paso 3 — Listar/seleccionar caso

- **Endpoint**: `GET /api/cases` y `GET /api/cases/{case_id}` (`app/api/cases.py`)
- **Decisiones**:
  - `analysis_status` se calcula **sin inventar** a partir de counts en DB: `documents`, `facts`, `risks` (`_calculate_analysis_status`).
- **Side effects**: ninguno (solo lectura).
- **Errores**:
  - `404` si `case_id` no existe.

#### Paso 4 — Subir documentos (ingesta)

- **Endpoint**: `POST /api/cases/{case_id}/documents` (router `app/api/documents.py`)
- **Inputs**:
  - `case_id` path param.
  - `files: list[UploadFile]` (multipart).
  - Flags de validación (p. ej. `ValidationMode` usado en fail-fast).
- **Decisiones relevantes (documentos duplicados / calidad)**:
  - Se calcula `sha256_hash` del binario (`calculate_file_hash`) y se persiste como parte del contrato de cadena de custodia (`Document.sha256_hash`, `file_size_bytes`, `mime_type` son **NOT NULL**).
  - Existe deduplicación (hash de contenido normalizado + embedding de documento completo para similaridad; ver `calculate_content_hash`, `generate_document_embedding`, `find_semantic_duplicates`).
  - Se crean/invalidan pares de duplicados y su auditoría (modelos `DuplicatePair`, `duplicate_action`).
- **Side effects**:
  - FS: persistencia del binario en `clients_data/cases/<case_id>/documents/` (vía `store_document_file` / pipeline de ingesta).
  - DB: inserta `documents` (y metadatos de deduplicación si aplica).
  - DB: puede crear `document_chunks` para el documento (chunking single doc: `build_document_chunks_for_single_document`).
- **Invariantes (modelo Document)**:
  - `sha256_hash`, `file_size_bytes`, `mime_type` no nulos.
  - `(case_id, sha256_hash)` es unique (constraint `uq_case_sha256`) → evita duplicados exactos por caso.
  - Soft-delete existe (`deleted_at`, `deleted_by`, `deletion_reason`) para exclusión sin borrado físico.
- **Errores**:
  - `404` si el caso no existe.
  - `422`/`400` si falla validación de ingesta (`DocumentValidationError`, contract violations).

#### Paso 5 — Construcción de chunks a nivel caso

Este paso puede ocurrir explícitamente en pipelines o implícitamente en retrieval.

- **Servicio**: `build_document_chunks_for_case(db, case_id, overwrite=...)` (`app/services/document_chunk_pipeline.py`, usado por RAG).
- **Side effects**:
  - DB: inserta `document_chunks` para documentos del caso.
- **Invariantes (modelo DocumentChunk)**:
  - `chunk_id` determinista.
  - `start_char < end_char` (si no, `ChunkContractViolationError`).
  - `extraction_method` no nulo.
  - `page_start/page_end` opcionales pero deben respetar `page_start <= page_end` si existen.
  - Compatibilidad legacy: `DocumentChunk.page` expone `page_start`.

#### Paso 6 — Construcción de embeddings y vectorstore (versionado estricto)

- **Servicio**: `build_embeddings_for_case(db, case_id)` (`app/services/embeddings_pipeline.py`)
- **Precondición**:
  - `OPENAI_API_KEY` debe existir si se ejecuta este pipeline directamente (en caso contrario lanza `RuntimeError`).
- **Side effects**:
  - FS: crea estructura versionada en `clients_data/_vectorstore/cases/<case_id>/<version>/index/` (Chroma PersistentClient).
  - FS: escribe `status.json` y `manifest.json` en la versión (`app/services/vectorstore_versioning.py`).
  - FS: actualiza puntero `ACTIVE` (symlink relativo o archivo de texto) apuntando a la versión válida.
  - DB: no crea tablas nuevas; consume `document_chunks` y `documents` para manifest/validaciones.
- **Invariantes y validación (bloqueante)**:
  - Si no hay chunks: la versión se marca FAILED y no se activa.
  - Se valida integridad (incluye consistencia de `case_id`, `embedding_model`, coherencia manifest vs metadatos de chunks). Solo si pasa: `status=READY` y se actualiza `ACTIVE`.
  - Si falla: `status=FAILED` y se preserva el `ACTIVE` anterior.

#### Paso 7 — Consultar RAG de caso (API)

- **Endpoint**: `POST /rag/ask` (router `app/rag/case_rag/rag.py`)
- **Input**: `RAGRequest(case_id, question, top_k, doc_types?, date_from?, date_to?)`.
- **Ejecución interna**:
  1. Retrieval: `rag_answer_internal` (`app/rag/case_rag/retrieve.py`)
  2. Capa de producto: scoring/políticas/phrasing (`app/services/confidence_scoring.py`, `app/services/response_policy.py`, `app/services/legal_phrasing.py`)
  3. Respuesta LLM: `build_llm_answer(...)` (si aplica) + wrapping con aviso de evidencia.
- **Decisiones y gates (hard + soft)**:
  - Gate 0: **calidad documental** (bloqueo si `quality_score < LEGAL_QUALITY_SCORE_BLOCK_THRESHOLD`).
  - Gate chunks: si no hay chunks, puede auto-generarlos.
  - Gate embeddings: exige versión `ACTIVE`; si no existe y `RAG_AUTO_BUILD_EMBEDDINGS=True`, intenta construir embeddings automáticamente.
  - Evidence enforcement: `validate_chunk_has_location` y `validate_retrieval_result` (fail-hard en FASE 4).
  - Política de respuesta: puede devolver “EVIDENCIA_INSUFICIENTE” aunque haya contexto si no se cumple la política configurada.
- **Side effects**:
  - DB/FS: potencialmente crea chunks/embeddings si el modo AUTO_BUILD está activo y faltan.
- **Errores y salidas controladas**:
  - En ausencia de contexto: devuelve `RAGResponse` con respuesta controlada (no lanza excepción HTTP en el endpoint, salvo fallos no controlados).

#### Paso 8 — Ejecutar agentes (endpoints dedicados)

- **Auditor**:
  - **Endpoint**: `POST /auditor/run` (`app/main.py`)
  - **Input**: `AuditorInput(case_id, question)`
  - **Ejecución**: `run_auditor(case_id, question, db)` (`app/agents/agent_1_auditor/runner.py`) → consume `query_case_rag` → ejecuta `audit_logic(...)`.
  - **Salida**: `AuditorResult` estructurado + flag `auditor_fallback` si el contexto es corto.

- **Prosecutor desde handoff**:
  - **Endpoint**: `POST /prosecutor/run-from-auditor` (`app/main.py`)
  - **Input**: `HandoffPayload` validado (incluye `case_id`, `summary`, `risks`, etc.).
  - **Ejecución**: `run_prosecutor_from_auditor(handoff_payload)` (`app/agents/agent_2_prosecutor/runner.py`) → `ejecutar_analisis_prosecutor(...)`.

- **Agente legal**:
  - **Endpoint**: `POST /legal/analyze` (`app/main.py`)
  - **Input**: `LegalAgentInput(case_id, question, auditor_summary?, auditor_risks?)`
  - **Ejecución**: `run_legal_agent(...)` (`app/agents/agent_legal/runner.py`) → consulta `query_legal_rag(...)` y ejecuta `legal_agent_logic(...)`.
  - **Degradación**: si falla RAG legal o falta API key, el contexto legal puede quedar vacío sin romper la ejecución (se registra warning).

#### Paso 9 — Alertas técnicas (evidencia verificable)

- **Endpoint**: `GET /api/cases/{case_id}/analysis/alerts` (router `app/api/analysis_alerts.py`)
- **Input**: `case_id`
- **Decisiones**:
  - No interpreta legalmente; construye alertas deterministas y adjunta evidencia directa desde `DocumentChunk`.
  - Si un chunk no cumple contrato (offsets, extraction_method, contenido), se rechaza como evidencia.
- **Side effects**: ninguno (lectura + computación).
- **Salida**: `AnalysisAlert[]` con `AlertEvidence` (incluye `location` con offsets/páginas/método).

#### Paso 10 — Informe legal simplificado y PDF (descarga)

- **Informe legal simplificado**:
  - **Endpoint**: `POST /api/cases/{case_id}/legal-report` (`app/api/legal_report.py`)
  - **Fuente**: deriva hallazgos desde alertas técnicas (`get_analysis_alerts`) y las convierte a `LegalFinding`.
  - **Decisión**: si no hay evidencias válidas, se inyecta evidencia “dummy” (esto es **degradación**: útil para UX, pero no equivale a evidencia forense).

- **PDF**:
  - **Endpoint**: `GET /api/cases/{case_id}/legal-report/pdf` (`app/api/pdf_report.py`)
  - **Ejecución**:
    1. genera `LegalReport` (optimizado, sin ejecutar agentes pesados)
    2. renderiza PDF (`generate_legal_report_pdf`)
  - **Salida**: streaming PDF.
  - **Nota crítica (estado real)**:
    - Aunque el endpoint se describe como “certificado”, hoy **NO** existe persistencia/validación de `ExecutionTrace` + `HardManifest` en BD.
    - Si necesitas certificación real: persiste trace/manifest y valida hashes antes de servir el PDF.

#### Paso 11 — Timeline paginado (UI escalable)

- **Endpoint**: `GET /api/cases/{case_id}/timeline`
- **Auth**: requiere `X-User-ID` (dependency `get_current_user`).
- **Side effects**: ninguno.
- **Decisión**: filtros/orden/paginación se aplican en SQL (no en memoria).

## 3. Organización del Repositorio

### Estructura principal (alto nivel)

- `app/`: código de aplicación (paquete Python instalable).
  - `app/main.py`: entrypoint ASGI (FastAPI).
  - `app/ui/streamlit_mvp.py`: UI oficial (Streamlit).
  - `app/api/`: routers FastAPI (casos, documentos, chunks, reportes, timeline, auth, trace, etc.).
  - `app/core/`: configuración, DB, logger, exceptions, seguridad, observabilidad y FinOps.
  - `app/services/`: lógica de negocio (ingesta/parsing, chunking, embeddings, RAG support, duplicados, timeline, etc.).
  - `app/models/`: modelos SQLAlchemy y contratos de datos.
  - `app/rag/`: RAG de casos y RAG legal + evidencia y políticas.
  - `app/graphs/`: orquestación de pipeline (LangGraph) + schemas de estado.
  - `app/agents/`: agentes “deterministas/mixtos” (Auditor, Prosecutor, Legal + handoff).
  - `app/agents_llm/`: agentes LLM (auditor_llm/prosecutor_llm) usados como nodos del grafo.
  - `app/reports/`: generación/render de reportes y PDF.

- `tests/`: batería de tests (unit, integration, api, rag, e2e, smoke). Configuración por markers en `pytest.ini`.
- `clients_data/`: datos runtime locales (ignorados por `.gitignore` en lo referente a casos y derivados).
- `data/sample/`: dataset pequeño para demo (copiable a `data/demo_ready/` vía `make demo-data`).
- `migrations/`: migraciones Alembic (si se usa DB persistente y esquema evoluciona).
- `docker/`: artefactos Docker (opcional para ejecución en contenedor).
- `legacy/`: material archivado/no oficial (si existe en tu rama; no forma parte del camino de ejecución).

### Qué debe vivir en cada capa (regla de localización)

- **UI**: composición de pantallas, UX, llamadas a API, cacheado UI (Streamlit cache). No contiene lógica de negocio.
- **API**: validación de payloads, respuesta HTTP, orquestación de servicios. No contiene parsing/heurísticas complejas.
- **Services**: parsing, pipelines, reglas operativas, validaciones “hard”, acceso a vectorstore/DB. Es el núcleo testable.
- **Models**: contratos de persistencia y modelos de datos. No contiene IO ni llamadas a servicios externos.
- **RAG**: retrieval/answering, gates de evidencia, integración con embeddings/vectorstore.
- **Graphs**: orquestación; nodos finos que llaman a services/agents y devuelven cambios de estado.

### Fuera del scope explícito

- Datos reales (no versionados).
- Ejecución productiva multi-tenant.
- Garantías jurídicas (el output es asistencial).

### Modelo de datos y contratos (núcleo operativo)

Este apartado define los contratos que gobiernan el runtime. No documenta “todas” las tablas, sino las que condicionan integridad y trazabilidad.

#### `Case` (`cases`)

- **Clave**: `case_id` UUID v4 (string 36).
- **Campos relevantes**: `name` (no nulo), `client_ref` opcional, `status`, `created_at/updated_at`.
- **Invariante**: un caso es el contenedor transaccional: toda entidad persistente crítica cuelga de `case_id`.

#### `Document` (`documents`) — cadena de custodia + deduplicación

- **Clave**: `document_id` UUID v4.
- **FK**: `case_id -> cases.case_id`.
- **Cadena de custodia (NOT NULL)**: `sha256_hash`, `file_size_bytes`, `mime_type`, `uploaded_at`.
- **Dedupe**:
  - unique `(case_id, sha256_hash)` (archivo binario idéntico por caso).
  - `content_hash` (texto normalizado) + `document_embedding` (embedding de documento completo) para deduplicación semántica.
  - `duplicate_action*` + auditoría de decisión.
- **Soft-delete**: `deleted_at`, `deleted_by`, `deletion_reason` y snapshot.
- **Motivo técnico**: preservar evidencia (input) y registrar decisiones (dedupe/exclusión) sin borrado físico inmediato.

#### `DocumentChunk` (`document_chunks`) — contrato de ubicación (Endurecimiento 3.x)

- **Clave**: `chunk_id` determinista (no UUID aleatorio).
- **FK**: `document_id`, `case_id`.
- **Contrato duro**:
  - `start_char` y `end_char` no nulos y `start_char < end_char`.
  - `extraction_method` no nulo.
  - `page_start/page_end` opcionales pero con invariante `page_start <= page_end` si existen.
- **Compatibilidad**:
  - `page` es alias legacy de `page_start` (consumido por RAG/timeline en algunos puntos).

#### Contratos de salida (API/RAG)

- **RAGResponse** (`app/rag/case_rag/rag.py`):
  - `sources[]` deben incluir metadata suficiente para citación (`chunk_id`, offsets, filename si disponible).
  - `response_type` y `confidence_score` explicitados por capa de producto.
- **AlertEvidence** (`app/api/analysis_alerts.py`):
  - evidencia solo se emite si el chunk cumple contrato (offsets/método/contenido).


## 4. Entrada y Ejecución del Sistema

### Entrypoints oficiales

- **API**: `uvicorn app.main:app` (Makefile: `make run-api`).
- **UI**: `streamlit run app/ui/streamlit_mvp.py` (Makefile: `make run-ui`).

### Quickstart para developers (clone → run en local)

Objetivo: que un developer ejecute el proyecto sin contexto previo.

1. Instala deps (idealmente en venv):
   - `make install-dev`
2. Configura entorno:
   - `cp .env.example .env`
   - `PHOENIX_API_BASE_URL` debe apuntar al backend (por defecto: `http://localhost:8000`).
3. Inicializa base de datos:
   - `make init-db` (crea tablas en `DATABASE_URL`; por defecto `sqlite:///./runtime/db/phoenix_legal.db`)
4. Arranca en 2 terminales:
   - `make run-api`
   - `make run-ui`
5. (Opcional) prepara ficheros demo:
   - `make demo-data` (copia `data/sample/*` a `data/demo_ready/`)

Verificación rápida:

- API root: `GET /` devuelve `status: "running"` (esto es lo que usa la UI como health check).
- Swagger: `/docs`.
- Health CI: `GET /health` devuelve `{"status":"healthy"}`.

### Ejemplos reproducibles con `curl` (end-to-end mínimo)

Estos comandos son para un developer que quiera ejecutar el flujo **sin UI** y comprobar resultados.

Convenciones:

- `BASE_URL` apunta al backend.
- `CASE_ID` es el caso sobre el que operas.
- Los ejemplos asumen que la API está en `http://localhost:8000`.

```bash
export BASE_URL="http://localhost:8000"
```

#### 1) Descubrimiento + health

```bash
curl -sS "$BASE_URL/" | python -m json.tool
curl -sS "$BASE_URL/health" | python -m json.tool
```

#### 2) Crear caso y capturar `CASE_ID`

```bash
CASE_ID="$(curl -sS -X POST "$BASE_URL/api/cases" \
  -H "Content-Type: application/json" \
  -d '{"name":"Demo Case - Phoenix","client_ref":"DEMO-001"}' | python -c 'import sys,json; print(json.load(sys.stdin)["case_id"])')"
echo "CASE_ID=$CASE_ID"
```

#### 3) Listar casos / ver detalle

```bash
curl -sS "$BASE_URL/api/cases" | python -m json.tool
curl -sS "$BASE_URL/api/cases/$CASE_ID" | python -m json.tool
```

#### 4) Subir documentos (multipart)

Usa ficheros pequeños (por ejemplo `data/demo_ready/` si corriste `make demo-data`):

```bash
curl -sS -X POST "$BASE_URL/api/cases/$CASE_ID/documents" \
  -F "files=@data/demo_ready/README.md" \
  | python -m json.tool
```

Puedes añadir más `-F "files=@ruta/al/fichero.ext"` en la misma llamada.

#### 5) Alertas técnicas (evidencia verificable)

```bash
curl -sS "$BASE_URL/api/cases/$CASE_ID/analysis/alerts" | python -m json.tool
```

#### 6) Informe legal simplificado

```bash
curl -sS -X POST "$BASE_URL/api/cases/$CASE_ID/legal-report" | python -m json.tool
```

#### 7) Descargar PDF (streaming)

```bash
curl -sS "$BASE_URL/api/cases/$CASE_ID/legal-report/pdf" -o "informe_legal_${CASE_ID}.pdf"
ls -lh "informe_legal_${CASE_ID}.pdf"
```

#### 8) RAG de caso (requiere embeddings/ACTIVE; puede responder con degradación)

```bash
curl -sS -X POST "$BASE_URL/rag/ask" \
  -H "Content-Type: application/json" \
  -d "$(cat <<'EOF'
{
  "case_id": "__CASE_ID__",
  "question": "Resume los hechos principales del caso basándote solo en evidencia."
}
EOF
)" | python -c 'import sys; s=sys.stdin.read().replace("__CASE_ID__", "'"$CASE_ID"'"); print(s)' \
  | curl -sS -X POST "$BASE_URL/rag/ask" -H "Content-Type: application/json" -d @- \
  | python -m json.tool
```

Nota: si no existe `ACTIVE` del vectorstore del caso, el sistema puede devolver `NO_EMBEDDINGS` o intentar auto-build dependiendo de flags y de si hay `OPENAI_API_KEY`.

#### 9) Duplicados (si hay documentos con similitud)

```bash
curl -sS "$BASE_URL/api/cases/$CASE_ID/documents/duplicates" | python -m json.tool
```

#### 10) Timeline paginado (requiere header `X-User-ID`)

Este endpoint requiere un usuario autenticado a nivel “header” (`X-User-ID`) en el MVP:

```bash
curl -sS "$BASE_URL/api/cases/$CASE_ID/timeline?page=1&page_size=20" \
  -H "X-User-ID: demo_user" \
  | python -m json.tool
```

#### 11) Análisis financiero (requiere header `X-User-ID`)

```bash
curl -sS "$BASE_URL/api/cases/$CASE_ID/financial-analysis" \
  -H "X-User-ID: demo_user" \
  | python -m json.tool
```

#### 12) Reports (router sin `/api`, no usados por la UI MVP)

```bash
curl -sS -X POST "$BASE_URL/reports/generate" \
  -H "Content-Type: application/json" \
  -d "{\"case_id\":\"$CASE_ID\"}" \
  | python -m json.tool
```

El JSON devuelve `markdown_path` y opcionalmente `pdf_path` si se generó. Para descargar, usa:

```bash
# Sustituye <filename> por el nombre real dentro de ./reports/<case_id>/
curl -sS "$BASE_URL/reports/download/$CASE_ID/<filename>" -o "<filename>"
```

### Superficie API (routers/endpoints) — mapa para handoff de devs

Esta sección documenta la **superficie HTTP** “real” (routers y endpoints), con el objetivo de que un developer pueda:

- entender **qué endpoint llama la UI** y qué responde,
- localizar el **router → función → service** responsable,
- saber qué **side effects** ocurren (DB/FS/vectorstore),
- conocer **precondiciones** (auth/config) y errores (HTTP).

> Fuente de verdad: `app/main.py` (cómo se montan los routers y sus prefijos).

#### Endpoints del camino principal (UI)

- **Root / discovery (usado por la UI como “health check”)**
  - `GET /` → devuelve `service`, `version`, `status` y un mapa de endpoints.
- **Health (CI/Docker)**
  - `GET /health` → `{"status":"healthy"}`

- **Casos** (`app/api/cases.py`, montado bajo `/api`)
  - `POST /api/cases` → crea `Case` en DB.
  - `GET /api/cases` → lista casos y calcula `analysis_status`.
  - `GET /api/cases/{case_id}` → detalle de caso.

- **Documentos + deduplicación** (`app/api/documents.py`, montado bajo `/api`)
  - `POST /api/cases/{case_id}/documents`
    - **Entrada**: multipart `files[]`.
    - **Side effects**:
      - FS: persiste binarios en `clients_data/cases/<case_id>/documents/...`
      - DB: crea `Document` con cadena de custodia (`sha256_hash`, `file_size_bytes`, `mime_type`, `storage_path`)
      - DB: crea `DocumentChunk` vía pipeline (según tipo de documento y parser)
      - DB: dedupe binario (por hash) y, si aplica, dedupe semántico/pares
    - **Errores típicos**: `404` caso inexistente; `400` sin ficheros; `422` validación.
  - `POST /api/cases/{case_id}/documents/check-duplicates`
    - **Objetivo**: “preflight” antes de subir (duplicado binario garantizado; semántico opcional).
  - `GET /api/cases/{case_id}/documents/duplicates`
    - **Salida**: `DuplicatePairSummary[]` desde tabla persistente `duplicate_pairs` (no se recalcula “al vuelo”).
    - **Nota**: por defecto excluye pares invalidados por cascade.
  - `PATCH /api/cases/{case_id}/documents/{document_id}/duplicate-action?expected_version=...`
    - **Contrato**: resolución con **lock optimista** (`decision_version`).
    - **Side effects**: actualiza `DuplicatePair`, registra auditoría append-only y puede ejecutar cascade/invalidaciones.
    - **Errores**: `409` (concurrencia); `422` (validación dura); `404` (par no encontrado).

- **Chunks (inspección literal, sin análisis)** (`app/api/chunks.py`, montado bajo `/api`)
  - `GET /api/cases/{case_id}/chunks` → listado con filtros **literales**.
  - `GET /api/cases/{case_id}/chunks/{chunk_id}` → chunk exacto.
  - **Contrato**: si un chunk rompe `location` (offsets/método/contenido) el endpoint puede devolver `500`.

- **Alertas técnicas (evidencia verificable)** (`app/api/analysis_alerts.py`, montado bajo `/api`)
  - `GET /api/cases/{case_id}/analysis/alerts` → `AnalysisAlert[]` con `AlertEvidence` (offsets/páginas/método).

- **RAG de caso** (`app/rag/case_rag/rag.py`, router `/rag`)
  - `POST /rag/ask` → respuesta con `answer` + `sources[]` citables.
  - **Gates**: puede devolver `NO_EMBEDDINGS`/warnings si falta `ACTIVE` o si el índice está vacío.

- **Informe legal simplificado** (`app/api/legal_report.py`, montado bajo `/api`)
  - `POST /api/cases/{case_id}/legal-report` → `LegalFinding[]` (derivado de alertas/evidencia).

- **PDF** (`app/api/pdf_report.py`, montado bajo `/api`)
  - `GET /api/cases/{case_id}/legal-report/pdf` → descarga PDF (streaming).
  - **Nota crítica (estado real)**: la implementación actual genera el PDF desde `LegalReport` simplificado y **no** valida trace/manifest (aunque el docstring lo mencione).

- **Timeline** (`app/api/timeline.py`, montado bajo `/api`)
  - `GET /api/cases/{case_id}/timeline` → timeline paginado.

#### Endpoints de análisis financiero / balance concursal

- **Análisis financiero** (`app/api/financial_analysis.py`, montado bajo `/api`)
  - `GET /api/cases/{case_id}/financial-analysis`
  - **Auth**: requiere `X-User-ID` (dependency `get_current_user`).
  - **Side effects**: auditoría de acceso (DB) + cálculo por bloques (balance/PyG/créditos/ratios/insolvencia/timeline).

- **Balance concursal** (`app/api/balance_concursal.py`, montado bajo `/api`)
  - `POST /api/cases/{case_id}/balance-concursal` → analiza y **persiste** `BalanceConcursalOutput`.
  - `GET /api/cases/{case_id}/balance-concursal` → balance activo.
  - `GET /api/cases/{case_id}/balance-concursal/history` → histórico.

#### Autenticación (JWT)

- **Auth** (`app/api/auth.py`, montado bajo `/api`)
  - `POST /api/auth/login`
  - `POST /api/auth/register` (solo admin)
  - `GET /api/auth/me`

#### Routers v2 (servicios + permisos + rate limit)

- **Auditor v2** (`app/api/v2_auditor.py`)
  - `POST /v2/auditor/analyze`
  - **Permiso**: `analysis:run`
  - **Rate limit**: `60/minute`
  - **Ejecución**: `AuditService.analyze_case(...)`

- **Prosecutor v2** (`app/api/v2_prosecutor.py`)
  - `POST /v2/prosecutor/analyze`
  - **Salida**: plantilla formal (secciones I/II/III) + hashes + fuentes verificables (cuando hay evidencia suficiente).

#### Endpoints declarados pero NO implementados (estado real)

Estos endpoints existen como contrato, pero hoy devuelven `404` porque la persistencia del trace/manifest en BD no está implementada:

- `GET /api/cases/{case_id}/trace` (`app/api/trace.py`)
- `POST /api/cases/{case_id}/manifest` (`app/api/manifest.py`)

#### Reports (router sin `/api`, no usado por la UI MVP)

Router: `app/api/reports.py` (montado en `app/main.py` sin `prefix="/api"`):

- `POST /reports/generate` → genera informe (Markdown) y devuelve paths; puede generar PDF si existe soporte.
- `GET /reports/download/{case_id}/{filename}` → descarga `*.md` o `*.pdf` desde `./reports/<case_id>/`.

### Configuración por entorno (`.env.example`)

`.env.example` define el mínimo para ejecución reproducible:

- `PHOENIX_API_BASE_URL` (UI → API; obligatorio para UI).
- `DATABASE_URL` (por defecto SQLite en `runtime/`).
- `OPENAI_API_KEY` (opcional).
- `LLM_ENABLED` (feature flag).
- `LOG_LEVEL`, `LOG_FORMAT`.

La API carga settings con Pydantic Settings (`app/core/config.py`) y permite variables extra en `.env` (`extra="ignore"`). Esto evita fallos al compartir `.env` entre UI y API y reduce acoplamiento.

### Por qué se evita hardcoding

- **Portabilidad**: URLs, rutas de DB y configuración LLM varían por entorno (local/CI).
- **Reproducibilidad**: `.env.example` captura el contrato de configuración requerido.
- **Seguridad**: secrets no se versionan (`.env` está en `.gitignore`).

### Reproducibilidad de ejecución

`Makefile` define comandos canónicos:

- `make install-dev`: instala deps dev y el paquete en modo editable.
- `make run-api`, `make run-ui`: entrypoints oficiales.
- `make check`: formateo + lint + tests “smoke” deterministas.

Empaquetado: `pyproject.toml` configura setuptools para incluir `app*` y Ruff target `py39`.

## 5. Servicios y Lógica de Negocio

### Qué son los services en este proyecto

Los services son unidades de lógica operativa con interfaz Python directa y dependencias explícitas (DB session, paths, etc.). Se diseñan para:

- ser invocados desde API y/o grafos,
- encapsular reglas operativas y validaciones,
- ser testeables sin UI.

Ejemplo de servicio: `AuditService.analyze_case()` (`app/services/audit_service.py`) valida caso y documentación y ejecuta el grafo de auditoría.

### Por qué la lógica no vive en UI ni en API

- **UI**: es un consumidor; su ciclo de ejecución (Streamlit reruns) no es adecuado para invariantes de datos.
- **API**: debe ser thin; mezclar parsing/heurística en routers complica tests y genera acoplamiento a HTTP.

### Ejemplos de responsabilidades

- **Ingesta y parsing**: `app/services/folder_ingestion.py` soporta múltiples extensiones, valida pre-ingesta y calidad de parsing, calcula hash/tamaño/mime, copia a almacenamiento (`clients_data/cases/<case_id>/documents`).
- **Chunking**: `app/services/document_chunk_pipeline.py` construye chunks persistidos en DB con contrato de offsets.
- **Embeddings + vectorstore**: `app/services/embeddings_pipeline.py` crea embeddings y persiste en ChromaDB con versionado estricto.
- **Versionado**: `app/services/vectorstore_versioning.py` implementa versiones inmutables y puntero ACTIVE.
- **LLM executor**: `app/services/llm_executor.py` centraliza ejecución LLM con degradación y retry.

### Ventajas para testing y escalabilidad

- Los servicios se prueban aislando la UI y evitando dependencias de red por defecto (tests con markers).
- El versionado del vectorstore reduce riesgos de corrupción y permite rollback/validación antes de activar una versión.

## 6. Agentes de IA y RAG

### Rol de los agentes

Los agentes encapsulan una lógica de análisis orientada a preguntas y síntesis:

- **Auditor** (`app/agents/agent_1_auditor/runner.py`): consulta RAG de caso y ejecuta lógica de auditoría; detecta fallback si el contexto es insuficiente.
- **Prosecutor** (`app/agents/agent_2_prosecutor/runner.py`): ejecuta análisis a partir de `case_id` o desde un payload de handoff.
- **Legal agent** (`app/agents/agent_legal/runner.py`): consume RAG legal para construir contexto normativo/jurisprudencial y generar salida estructurada.

### Handoff (Auditor → Prosecutor) — contrato, validación y ciclo de vida

El handoff es el mecanismo explícito para transportar resultados del Agente 1 al Agente 2 sin acoplar esquemas internos.

#### Contrato (`HandoffPayload`)

Definido en `app/agents/handoff.py` (Pydantic):

- **Obligatorios**: `case_id`, `question`, `summary` (no vacíos).
- **Listas**: `risks`, `next_actions`.
- **Control**: `auditor_fallback` (marca degradación por falta de contexto).
- **Opcionales**: `source_metadata`, `full_text` (si la ingesta los aporta).

Regla operativa: el payload del handoff debe ser **validable** (mismo schema) tanto si viene de:

- un resultado del Auditor (`AuditorResult`), como
- una ejecución orquestada desde API/UI.

#### Construcción del payload

Función: `build_agent2_payload(...)` en `app/agents/handoff.py`.

- **Input**: `auditor_result`, `case_id`, `question`, `auditor_fallback`, `ingesta_result?`.
- **Output**: `dict[str, Any]` con shape de `HandoffPayload`.

El diseño separa:

- “construcción” (dict) y
- “validación” (Pydantic),

para permitir que la API valide automáticamente cuando el payload viaja por HTTP.

#### Consumo (dos caminos)

- **API**: `POST /prosecutor/run-from-auditor` en `app/main.py`
  - Request body: `HandoffPayload` (validación automática).
- **Runner directo**: `run_prosecutor_from_auditor(handoff_payload)` (`app/agents/agent_2_prosecutor/runner.py`)
  - Extrae campos y delega en `ejecutar_analisis_prosecutor(...)`.

#### Ejemplo de payload (HTTP)

Este es el shape mínimo esperado por `POST /prosecutor/run-from-auditor`:

```json
{
  "case_id": "CASE_RETAIL_001",
  "question": "¿Existe riesgo de retraso en solicitud de concurso?",
  "summary": "Resumen del Auditor...",
  "risks": ["delay_filing", "missing_docs"],
  "next_actions": ["Revisar fechas de insolvencia", "Solicitar balances faltantes"],
  "auditor_fallback": false
}
```

Campos opcionales (`source_metadata`, `full_text`) solo deberían enviarse si realmente existen; no son necesarios para ejecutar el Prosecutor.

#### Checklist de handoff (debugging rápido)

- **Validación**: si falta `case_id/question/summary` o vienen vacíos, FastAPI devuelve `422` antes de ejecutar nada (Pydantic).
- **Compatibilidad**: `app/main.py` hace `payload.dict()` y lo pasa a `run_prosecutor_from_auditor(...)`; el runner solo lee keys (`case_id`, `summary`, `risks`, `auditor_fallback`).
- **Observabilidad**: el runner loguea `stage="handoff"`, `has_auditor_context` y `auditor_fallback` (útil para detectar degradación).

#### Qué “resulta” del handoff (y qué no)

- **No es persistencia**: el handoff no crea tablas ni archivos por sí mismo.
- **Es transición**: el valor es garantizar que el Prosecutor recibe un input coherente y auditable.

### Integración con lógica tradicional

El sistema combina:

- **Heurísticas deterministas** en nodos del grafo (`app/graphs/nodes.py`).
- **RAG** para recuperar contexto verificable (caso y legal).
- **LLM** como componente opcional, con degradación controlada y sin dependencia dura para que el sistema siga operando.

### RAG de casos (case RAG)

Componentes relevantes:

- `app/rag/case_rag/retrieve.py`: “cerebro” de retrieval; aplica gates de calidad y evidencia; puede auto-construir embeddings si no existen (`RAG_AUTO_BUILD_EMBEDDINGS` en `app/core/variables.py`).
- `app/rag/case_rag/service.py`: interfaz simplificada (devuelve `context_text`).
- `app/services/embeddings_pipeline.py` + `app/services/vectorstore_versioning.py`: persistencia y versionado de embeddings.

Aspectos operativos:

- Los embeddings se guardan en `clients_data/_vectorstore/cases/<case_id>/<version>/index` con un puntero `ACTIVE` a una versión válida.
- La activación de versiones es bloqueante: solo se activa si la validación de integridad pasa.

### RAG legal

Componentes relevantes:

- `app/rag/legal_rag/ingest_legal.py`: ingesta del corpus legal (ley concursal y, si existe corpus, jurisprudencia).
- `app/rag/legal_rag/service.py`: consulta y normalización de resultados; cache en memoria; modo degradado si falta `OPENAI_API_KEY` (devuelve resultados vacíos).

Notas:

- El vectorstore legal se almacena bajo `clients_data/_vectorstore/legal/ley_concursal` (y `jurisprudencia` si aplica).
- Los resultados se normalizan a un dict con `citation`, `text`, `source`, `authority_level`, `relevance`, etc.

### Control de uso: inputs/outputs y trazabilidad

- **Feature flags**: `LLM_ENABLED` y presencia de `OPENAI_API_KEY` determinan disponibilidad (`Settings.llm_available`).
- **Executor único**: `execute_llm()` centraliza reintentos, timeouts y degradación, devolviendo siempre un `LLMExecutionResult`.
- **FinOps**: para operaciones con coste (embeddings, retrieve, llamadas LLM) existe un marco de “entry points” y gates (`app/core/finops/entry_points.py`) que formaliza la política de uso.

### Vectorstore versionado (casos) y estructura de integridad

Phoenix implementa versionado estricto del vectorstore de **casos** (no del legal) para evitar sobreescrituras y permitir validación antes de activar.

#### Estructura de directorios (casos)

- **Raíz**: `clients_data/_vectorstore/cases/<case_id>/`
- **Versiones**: `v_YYYYMMDD_HHMMSS/`
  - `index/` (ChromaDB PersistentClient)
  - `manifest.json` (metadatos técnicos)
  - `status.json` (`BUILDING|READY|FAILED`)
- **Puntero activo**: `ACTIVE`
  - Preferente: **symlink relativo** a `<version>/`
  - Fallback: **archivo de texto** cuyo contenido es el `version_id`

#### Qué es una “versión”

Una versión es un snapshot del índice vectorial generado desde `document_chunks` existentes para un `case_id` en un momento dado. Es inmutable: no se sobrescribe; si se re-genera, se crea una nueva versión.

#### Manifest y condiciones de activación

- **Generación**: en `build_embeddings_for_case` se construye `ManifestData` y se escribe `manifest.json`.
- **Validación** (`validate_version_integrity`, bloqueante):
  - coherencia `case_id` en metadatos
  - modelo de embeddings coincide con `EMBEDDING_MODEL`
  - documentos del manifest tienen chunks correspondientes
  - otros checks de integridad interna
- **Activación**:
  - solo si `status=READY` se actualiza `ACTIVE`.
  - si algo falla, se marca `FAILED` y **no** se toca el `ACTIVE` anterior.

#### Failure modes (y cómo se manifiestan)

- **ACTIVE inexistente**:
  - `get_active_version(...)` devuelve `None` y el RAG puede:
    - devolver `NO_EMBEDDINGS` (si `RAG_AUTO_BUILD_EMBEDDINGS=False`), o
    - disparar auto-build (si está habilitado).
- **ACTIVE roto / symlink absoluto inválido**:
  - si el symlink no es resoluble, `Path.exists()` puede devolver `False` y el sistema lo trata como “no existe ACTIVE”.
  - el diseño actual fuerza symlink relativo para evitar depender del cwd y minimizar este fallo.
- **Versión READY con index vacío**:
  - retrieval detecta `collection.count()==0` y lo trata como vectorstore vacío.
- **DB vs vectorstore incoherentes**:
  - la validación de versión intenta bloquear activación; en runtime, evidencia/umbrales pueden frenar respuesta.

### Quality gates y degradación (reglas operativas exactas)

Este apartado describe decisiones binarias (bloquear / permitir) implementadas en el runtime.

#### Gates de RAG de caso

- **Gate por calidad documental** (`retrieve.py`):
  - si `quality_score < LEGAL_QUALITY_SCORE_BLOCK_THRESHOLD` → el sistema bloquea conclusiones (devuelve sin contexto y marca `hallucination_risk=True`).
  - si `quality_score < LEGAL_QUALITY_SCORE_WARNING_THRESHOLD` → warning explícito (no bloqueante).
- **Chunks**:
  - si no hay chunks, puede auto-generarlos (`build_document_chunks_for_case`) y reintentar.
- **Embeddings (ACTIVE)**:
  - si no existe `ACTIVE` y `RAG_AUTO_BUILD_EMBEDDINGS=True` → auto-build de embeddings/versionado.
  - si `RAG_AUTO_BUILD_EMBEDDINGS=False` → `NO_EMBEDDINGS`.
- **Evidencia mínima (Endurecimiento 4)**:
  - `validate_chunk_has_location` y `validate_retrieval_result` fallan si la evidencia no cumple contrato.
  - umbral duro en `evidence_enforcer.py`: `MIN_CHUNKS_FOR_RESPONSE = 2` para permitir respuesta con evidencia suficiente.

#### Degradación de LLM

- **LLM deshabilitado**: `execute_llm` retorna `LLMExecutionResult(success=False, error_type="disabled", degraded=True)` sin lanzar excepción.
- **Fallo proveedor/timeouts**: se reintenta y, si persiste, se cae a fallback; si todo falla, devuelve degradado.

#### RAG legal sin API key

- `query_legal_rag` depende de embeddings de consulta. Si `_get_openai_client()` devuelve `None`, retorna lista vacía (modo degradado).


## 7. Gestión de Configuración y Dependencias

### Settings (Pydantic Settings)

- `app/core/config.py` define `Settings` con variables para DB, LLM, embeddings, RAG, paths, seguridad y observabilidad.
- `model_config` carga `.env` y permite variables extra (evita que la API falle por variables usadas solo por UI).

### Dependencias runtime vs dev

- `requirements.txt`: runtime (FastAPI, SQLAlchemy, ChromaDB, OpenAI, parsing, reportes, observabilidad, Streamlit).
- `requirements-dev.txt`: incluye runtime + pytest/tooling (ruff, mypy, bandit, etc.).

### Decisiones de versionado

- `pyproject.toml` fija `requires-python = ">=3.9"` y configura `ruff` target `py39`.
- Dependencias pinneadas en `requirements*.txt` para reproducibilidad.

### Evitar dependencias implícitas

Reglas visibles en el diseño:

- `.env` no se versiona; se distribuye `.env.example`.
- Los paths runtime (`clients_data/`, `runtime/`) se excluyen en `.gitignore`.
- El sistema tolera ausencia de LLM (no fuerza un proveedor online para ejecutar tests por defecto).

## 8. Testing y Quality Gates

### Estrategia de testing

Se usa clasificación por markers (`pytest.ini`):

- `smoke`: pruebas rápidas y deterministas (default en `make test`).
- `api`, `db`, `rag`, `integration`, `e2e`: niveles de integración.
- `llm` y `slow`: excluidas por defecto para evitar flakiness y coste.

### Qué se testea y qué no (y por qué)

- **Sí**:
  - Contratos de modelos/chunks y validaciones.
  - Endpoints esenciales (health, cases, documents, reports, etc.).
  - Integraciones RAG deterministas (cuando hay vectorstore local).

- **No por defecto**:
  - Tests que requieren `OPENAI_API_KEY` y llamadas reales (`-m llm`).
  - Tests lentos (`-m slow`).

Motivo técnico: asegurar que `make check` sea ejecutable en CI/local sin credenciales ni red.

### Evitar flakiness

Mecanismos presentes:

- **Modo degradado**: RAG legal devuelve vacío sin API key; LLM executor devuelve resultado degradado sin romper ejecución.
- **Markers**: segregación explícita de tests costosos/no deterministas.
- **Vectorstore versionado**: reduce estados corruptos por ejecuciones anteriores.

### Quality gates (herramientas)

Definidos en `Makefile` / configuración:

- **Formato**: `ruff format`.
- **Lint**: `ruff check` (select: E/F/I; con per-file-ignores para tests).
- **Typecheck**: `mypy app` (en Makefile está con `|| true`, por lo que actúa como señal pero no bloquea el pipeline).
- **Tests**: `pytest -m "smoke and not llm and not slow"` (vía Makefile).

Nota: `bandit` está en `requirements-dev.txt`, pero no forma parte del `make check` actual.

### Testing map (qué cubre qué)

#### Markers (contrato de ejecución)

Definidos en `pytest.ini`:

- `smoke`: núcleo determinista (lo que se ejecuta por defecto en `make test`).
- `api`: endpoints.
- `db`: persistencia.
- `rag`: retrieval/evidencia/políticas.
- `integration`, `e2e`: cadenas completas (pueden tocar filesystem y vectorstores).
- `llm`: requiere proveedor real y `OPENAI_API_KEY`.
- `slow`: excluido por defecto.

#### Comandos canónicos

- `make test` → `pytest -m "smoke and not llm and not slow"`
- `make test-all` → `pytest -m "not llm and not slow"`
- E2E completo (con red/LLM): ejecutar explícitamente los tests `test_e2e_*` habilitando entorno con API key y vectorstores poblados.

#### Invariantes garantizados por E2E

- Vectorstore legal de ley concursal no vacío (ingesta previa o regeneración).
- Vectorstore de caso versionado con `ACTIVE` resoluble y colección con embeddings.
- Contrato de chunk (offsets/extraction_method) y evidencia en retrieval.


## 9. Datos de Demo y Seguridad

### Separación de datos

- **`clients_data/`**: datos locales (casos, documentos, vectorstores, logs, exportaciones). Se ignora en git para evitar subida accidental de información sensible.
- **`data/sample/`**: dataset pequeño y controlado para demo.
- **`data/demo_ready/`**: copia generada para facilitar subida desde UI (`make demo-data`), también ignorada.

### Artefactos del runtime (qué se crea y dónde mirar)

Checklist de “qué comprobar” cuando algo falla:

- **DB (por defecto SQLite)**:
  - `DATABASE_URL` por defecto: `sqlite:///./runtime/db/phoenix_legal.db` (ver `.env.example` y `app/core/config.py`).
  - Creación de tablas: `make init-db` (ejecuta `python -m app.core.init_db`).
- **FS de casos**:
  - Raíz: `clients_data/` (configurable con `DATA_DIR`).
  - En ingesta se crean subcarpetas bajo `clients_data/cases/<case_id>/...` (documentos y derivados).
- **Vectorstore de caso (versionado)**:
  - Raíz: `clients_data/_vectorstore/cases/<case_id>/`
  - `ACTIVE` debe apuntar a una versión válida con `index/`.
- **Vectorstore legal**:
  - `clients_data/_vectorstore/legal/ley_concursal` (y `jurisprudencia` si existe corpus).
- **Reportes (router `/reports/*`)**:
  - Se guardan bajo `./reports/<case_id>/` (descarga con `GET /reports/download/...`).

### Consideraciones de seguridad y privacidad

- `.env` y variantes se ignoran (`.gitignore`), solo se versiona `.env.example`.
- El hash SHA-256, tamaño y MIME se calculan y persistentean en ingesta para integridad/cadena de custodia a nivel técnico (`folder_ingestion.py`).

## 10. Decisiones Técnicas Clave

1. **Entrypoints únicos (UI/API)**:
   - **Decisión**: `app/main.py` y `app/ui/streamlit_mvp.py` son los caminos oficiales.
   - **Justificación**: reduce ambigüedad de evaluación y simplifica reproducibilidad.

2. **Configuración centralizada con Pydantic Settings**:
   - **Decisión**: `app/core/config.py` como contrato de configuración.
   - **Justificación**: tipado/validación de env vars y defaults consistentes; evita hardcoding.

3. **RAG con gates y evidencia**:
   - **Decisión**: retrieval no es “free text”: se aplican umbrales, mínimo de chunks y controles.
   - **Justificación**: en un sistema jurídico, respuestas sin evidencia elevan el riesgo de alucinación y reducen auditabilidad.

4. **Vectorstore versionado con ACTIVE**:
   - **Decisión**: embeddings se generan en versiones inmutables con manifest/status y puntero ACTIVE.
   - **Justificación**: evita sobreescrituras y permite validación de integridad antes de activar; reduce inconsistencias entre DB y vectorstore.

5. **LLM executor único con degradación**:
   - **Decisión**: prohibir llamadas directas al proveedor; centralizar en `execute_llm()`.
   - **Justificación**: los fallos de red/proveedor no deben comprometer la ejecución del pipeline; se retorna un resultado estructurado siempre.

6. **FinOps como contrato técnico**:
   - **Decisión**: entry points para operaciones con coste (`run_embeddings`, `run_retrieve`, `run_llm_call`).
   - **Justificación**: control explícito de presupuesto y caching; evita bypass accidental de políticas y facilita auditoría de coste/latencia.

### Alternativas consideradas (implícitas en el diseño) y trade-offs

- **Monolito UI+API**:
  - Rechazado por reducir testabilidad y acoplar la demo a Streamlit.
- **Embeddings sin versionado**:
  - Rechazado por riesgo de corrupción y falta de trazabilidad.
- **Tests siempre con LLM**:
  - Rechazado por no determinismo, coste y dependencia de credenciales; se segregan con markers.

## 11. Limitaciones Conocidas

- **Dependencia opcional de OpenAI**:
  - El modo completo (RAG legal con embeddings, tests `llm`) requiere `OPENAI_API_KEY` y vectorstores poblados.
  - En ausencia, el sistema opera con degradación y/o tests excluidos por markers.

- **Mypy no bloqueante**:
  - `make typecheck` no falla el pipeline (por el `|| true`). Es una decisión deliberada para no bloquear la entrega del curso con deuda de tipado heredada.

- **`app/core/variables.py` marcado como legacy**:
  - Existe una migración en progreso hacia `Settings`; conviven constantes legacy por compatibilidad.

- **Salida y persistencia**:
  - `clients_data/` y `runtime/` son runtime locales; la demo asume filesystem accesible.

### Siguiente paso en un entorno productivo (no curso)

- Endurecer `make check` para que `mypy` y `bandit` sean bloqueantes.
- Formalizar gestión de secrets (vault/secrets manager) y rotación de credenciales.
- Sustituir prints residuales por logging estructurado unificado.
- Aislamiento multi-tenant y control de acceso por usuario/rol en toda la UI (no solo API).

### Troubleshooting técnico (fallos típicos de runtime)

- **UI falla al arrancar**:
  - causa: falta `PHOENIX_API_BASE_URL` → la UI levanta `RuntimeError` de precondición.
- **RAG de caso devuelve “índice no disponible”**:
  - causa: `ACTIVE` inexistente y `RAG_AUTO_BUILD_EMBEDDINGS=False`, o `OPENAI_API_KEY` ausente para build.
  - acción: habilitar `RAG_AUTO_BUILD_EMBEDDINGS` o ejecutar pipeline de embeddings con API key.
- **Vectorstore legal existe pero no devuelve resultados**:
  - causa: `OPENAI_API_KEY` ausente (no se puede embedder la query) o colección sin embeddings.
  - acción: cargar key y ejecutar `app/rag/legal_rag/ingest_legal.py`.
- **Alertas sin evidencia útil**:
  - causa: chunks que no cumplen contrato (p. ej. offsets/páginas no disponibles para PDFs) → se descartan evidencias.
  - acción: revisar pipeline de parsing/chunking para que `page_start/page_end` se poblen cuando `extraction_method=pdf_text`.

