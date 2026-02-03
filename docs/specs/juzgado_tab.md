# Juzgado Tab (CourtPack) — Source of Truth

## 1) Objetivo
Implementar la pestaña **“Juzgado”** para preparar un **expediente de solicitud de concurso** a partir de los **ficheros del caso en filesystem**, de forma **determinista y auditable**.

## 2) Reglas globales (obligatorias)
- **NO base de datos.**
- **NO RAG.**
- **NO scraping.**
- **NO inferencias / NO heurísticas / NO inventar campos.**
- **Fuente única de datos**: filesystem del caso en:
  - `clients_data/cases/case_retail_demo_sl_2026/`
- Los datos **ya existen**; el sistema **solo los organiza**.
- **Documento nº 0** (formulario oficial) es **inmutable en origen**.
- La edición es **campo-a-campo** y **auditable**.
- Gestión de faltantes:
  - Si falta algún recurso técnico (p. ej. `courtpack/config.json`) se crea un **placeholder mínimo** y se muestra `st.error` **sin bloquear** el flujo.

## 3) Inputs (filesystem)
### 3.1 Caso
- Caso de trabajo: `clients_data/cases/case_retail_demo_sl_2026/`
- El tab **solo** lee y escribe bajo ese directorio (y subdirectorios CourtPack).

### 3.2 Documento 0 (PDF oficial)
- Ruta obligatoria del PDF oficial:
  - `judicial_forms/concurso_voluntario/personas_juridicas/formulario_oficial_v2020_05_21.pdf`
- El Documento 0 se **copia dentro del caso** para trazabilidad y para cumplir “documentos desde el caso”:
  - `clients_data/cases/case_retail_demo_sl_2026/courtpack/documento_0/documento_0_oficial.pdf`

## 4) Outputs (CourtPack)
Todo output se escribe bajo:
- `clients_data/cases/case_retail_demo_sl_2026/courtpack/`

### 4.1 Config (placeholder si falta)
- `courtpack/config.json`
  - Si no existe, se crea con contenido mínimo: `{}`.

### 4.2 Estado del Documento 0
- `courtpack/documento_0/state.json`
  - Contiene únicamente valores editados por campo (sin inventar campos).
  - Estructura mínima:
    - `fields`: objeto `{ <field_name>: <value> }`
    - `updated_at`: ISO-8601 UTC o `null`

### 4.3 Auditoría append-only del Documento 0
- `courtpack/documento_0/audit.ndjson`
  - NDJSON (una línea JSON por evento), append-only.
  - Cada cambio de campo registra:
    - `ts` (ISO-8601 UTC)
    - `actor` (p. ej. `"ui"`)
    - `action` (p. ej. `"field_update"`)
    - `field` (nombre exacto del campo del PDF)
    - `old` / `new`

### 4.4 PDF “rellenado” (derivado)
- El original **no se modifica**.
- Para exportación se genera un PDF “rellenado” (derivado) aplicando `state.json` a los campos AcroForm:
  - Dentro del ZIP: `Documento_0/Formulario_rellenado.pdf`
  - Si el PDF no tiene AcroForm o es inválido, **no bloquea**: se omite o se marca el error en el manifest.

### 4.5 Presentar (simulado)
- La acción “Presentar (simulado)” escribe un acuse en:
  - `courtpack/presentaciones/<timestamp>.json`
- El acuse incluye:
  - `presentado_simulado: true`
  - `presented_at`
  - hash y tamaño del ZIP (`zip_sha256`, `zip_size_bytes`)
  - manifest del ZIP (ver sección 5)

## 5) Exportación ZIP + MANIFEST (auditable)
### 5.1 Contenido mínimo del ZIP
- `Documento_0/Formulario_oficial.pdf` (copia en el caso)
- `Documento_0/state.json` (si existe)
- `Documento_0/audit.ndjson` (si existe)
- `MANIFEST.json` (siempre)
- Opcional:
  - `Documento_0/Formulario_rellenado.pdf` (si se pudo generar)

### 5.2 MANIFEST.json
El ZIP incluye un `MANIFEST.json` con:
- `rules_version` (p. ej. `"courtpack_v1"`)
- `generated_at` (ISO-8601 UTC)
- `case_id` (fijo: `"case_retail_demo_sl_2026"`)
- `case_root` (ruta del caso)
- `placeholders` (resultado de placeholders)
- `doc0` (estado de copia del Documento 0)
- `entries`: lista de entradas del ZIP con:
  - `path` (ruta dentro del ZIP)
  - `sha256` (si la entrada existe como bytes)
  - `size_bytes` (si aplica)
  - `role` (p. ej. `documento_0_oficial`, `documento_0_rellenado`, `state`, `audit`, `manifest`)
  - Si una entrada no se pudo generar, se registra `error` en su lugar.

## 6) UI (Streamlit)
Archivo objetivo:
- `app/ui/streamlit_mvp.py`

La pestaña “Juzgado” debe:
- Mostrar estado de faltantes con `st.error` **sin bloquear**:
  - Falta `clients_data/cases/case_retail_demo_sl_2026/` (se crea placeholder)
  - Falta `courtpack/config.json` (se crea `{}`)
  - Falta PDF oficial en `judicial_forms/.../formulario_oficial_v2020_05_21.pdf`
- Documento 0:
  - Leer campos AcroForm **reales** del PDF.
  - Permitir edición campo-a-campo:
    - texto para `/Tx`
    - booleano para `/Btn` (checkbox)
  - Guardar en `state.json` y auditar en `audit.ndjson`.
  - Si no hay campos AcroForm: `st.error` y seguir permitiendo export.
- Exportar ZIP:
  - `st.download_button` para descargar `courtpack_expediente.zip`.
- Presentar (simulado):
  - botón que genera el ZIP y escribe el acuse en `courtpack/presentaciones/`.

## 7) Tests (EXACTAMENTE 3 smoke tests)
En `tests/` y **sin DB, sin API, sin red**:
1. `tests/test_courtpack_placeholders_smoke.py`
2. `tests/test_courtpack_doc0_fields_smoke.py`
3. `tests/test_courtpack_export_zip_smoke.py`

## 8) No-goals (explícitos)
- No autocompletar datos del formulario (sin inferencia).
- No extraer datos estructurados del contenido de documentos (sin RAG/IA salvo donde se indique explícitamente; aquí no aplica).
- No depender de endpoints ni persistencia en base de datos.

