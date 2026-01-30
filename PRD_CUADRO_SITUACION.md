# PRD técnico — 📚 Cuadro de situación (SQL) + Buscador documental

## Objetivo (abogado-first)
Permitir que un abogado concursalista:

- **Encuentre** rápidamente documentos relevantes (escrituras, contratos, AEAT/TGSS, juzgado, etc.) sin “PDF-hunting”.
- **Registre** manualmente información estructurada (facturas, créditos, bienes, deuda pública, juzgado) con:
  - **Evidencia obligatoria** al crear **y** al editar.
  - **Auditoría append-only** (quién/cambio/motivo, antes→después).
  - **Versionado “vigente”** (cada edición crea una nueva versión; la anterior deja de ser vigente).
- **Exporte** un Excel operativo del caso para trabajo interno (con pestañas por entidad y evidencia resumida).

## Principios no negociables (legal)
- **Evidencia obligatoria** en alta y edición:
  - mínimo 1 evidencia
  - `note` mínimo 10 caracteres (justificación probatoria)
  - `document_id` debe pertenecer al caso y no estar excluido
- **Append-only**:
  - no se edita ni se borra evidencia (salvo mantenimiento DBA)
  - auditoría append-only siempre
  - edición de registros = nueva versión (“vigente”)
- **Trazabilidad**:
  - cada cambio debe poder responder: “¿quién lo puso?”, “¿con qué documento se soporta?”, “¿cuándo cambió?”.

## Entidades (tablas SQL)
Nota: en el código actual se implementan con prefijo `situation_…` (equivalente al prefijo “case_…” del roadmap).

### 1) Facturas (`situation_invoices`)
Campos mínimos (abogado):
- **supplier** (proveedor/acreedor) — obligatorio
- **amount_total** — obligatorio (≥ 0)
Campos útiles:
- `invoice_number`, `issue_date`, `due_date` (YYYY-MM-DD, opcional)
- `status` (pendiente/pagada/impagada, opcional)
- `notes` (prudentes)
Metacampos:
- `logical_id`, `record_id`, `version`, `is_current`, `created_by`, `created_at`

### 2) Créditos (`situation_credits`)
Campos mínimos:
- **creditor** — obligatorio
- **amount_total** — obligatorio (≥ 0)
Campos útiles:
- `contract_ref`, `secured` (bool), `guarantee_details`, `maturity_date`, `notes`
Metacampos: idem.

### 3) Bienes / activos (`situation_assets`)
Campos mínimos:
- **asset_type** (INMUEBLE/VEHICULO/MAQUINARIA_EQUIPO) — obligatorio
- **description** — obligatorio
Campos útiles:
- `valuation_admin_concursal` (≥ 0), `valuation_external` (≥ 0), `valuation_date`
- `liens` (cargas), `notes`
Metacampos: idem.

### 4) Deuda pública (`situation_public_debts`)
Campos mínimos:
- **authority** (AEAT/TGSS/OTRO) — obligatorio
- **amount_total** — obligatorio (≥ 0)
Campos útiles:
- `concept`, `period_start`, `period_end`
- `deferred` (aplazada/fraccionada), `notes`
Metacampos: idem.

### 5) Juzgado / actuaciones (`situation_court_records`)
Campos mínimos:
- **action_type** (demanda/monitorio/ejecucion/embargo/resolucion/otro) — obligatorio
Campos útiles:
- `court`, `procedure_number`, `action_date`
- `amount_claimed` (≥ 0, opcional), `status`, `notes`
Metacampos: idem.

## Evidencia (`situation_evidence`)
Evidencia polimórfica por (entity, record_id):
- `entity`: INVOICE/CREDIT/ASSET/PUBLIC_DEBT/COURT
- `record_id`: versión concreta (append-only por versión)
- `document_id`: documento del caso
- `page` / `chunk_id` (opcionales)
- `note`: justificación probatoria (obligatorio)
- `created_by`, `created_at`

## Auditoría (`situation_audit_log`)
Auditoría append-only por cambio:
- `entity`, `logical_id`, `record_id`
- `action`: CREATE/UPDATE/ADD_EVIDENCE (mínimo)
- `actor`, `reason`
- `before` (JSON), `after` (JSON)
- `created_at`

## API (contrato)
Prefijo: `/api/cases/{case_id}/situation`

### Listados (con filtros + paginación)
Patrón:
- `GET /invoices`, `GET /assets`, `GET /credits`, `GET /public-debts`, `GET /court-records`
- Query params comunes:
  - `page` (1..N)
  - `page_size` (1..100)
  - `include_history` (bool): si true devuelve todas las versiones; si false solo `is_current=true`
  - filtros por entidad (ej. `supplier`, `min_amount`, `max_amount`, `due_from`, etc.)
Respuesta:
```json
{
  "items": [ ... ],
  "page": 1,
  "page_size": 20,
  "total": 123
}
```

### CRUD (versionado “vigente”)
- Crear: `POST /{entity}`
  - requiere `created_by`, `reason`, `evidence[]` + campos de entidad
- Editar: `POST /{entity}/update`
  - requiere `logical_id`, `expected_version`
  - requiere `created_by`, `reason`, `evidence[]`
  - crea nueva versión y marca anterior como no vigente

### Evidencia (consultable y ampliable)
- `GET /{entity}/{record_id}/evidence`
  - lista evidencias de una versión concreta
- `POST /{entity}/{record_id}/evidence`
  - añade evidencia adicional (append-only) sin crear versión nueva
  - crea auditoría `ADD_EVIDENCE`

### Auditoría (consultable por registro lógico)
- `GET /{entity}/{logical_id}/audit`
  - lista auditoría (CREATE/UPDATE/ADD_EVIDENCE) de todas las versiones de ese `logical_id`

### Export único a Excel (5 pestañas)
- `GET /export.xlsx`
  - genera 1 Excel con pestañas:
    - Facturas, Créditos, Bienes, Deuda pública, Juzgado
  - incluye `case_id` y `exported_at`
  - incluye columna “evidencia” (resumen `document_id` + página)

## UI Streamlit
Pestaña: `📚 Cuadro de situación`

### Subtab “🔎 Buscador documental”
- búsqueda por texto + filtros por categorías doc_type
- resultados: tabla + snippet/preview

### Subtab “🗃️ Base de datos”
Por entidad:
- filtros + paginación
- toggle **“Solo vigentes / Historial (todas las versiones)”**
- acciones por registro:
  - ver evidencia (lista)
  - añadir evidencia
  - ver auditoría/historial
- botón **Export único (Excel)** del caso (5 pestañas)

## Migraciones / DB (índices y constraints)
- Índices por `case_id` + campos de filtro frecuente:
  - invoices: (case_id, supplier), (case_id, due_date), (case_id, amount_total), (case_id, status)
  - assets: (case_id, asset_type), (case_id, valuation_admin_concursal), (case_id, valuation_external)
  - credits/public_debts/court_records: índices equivalentes por campos principales
- Constraints:
  - checks `amount_total >= 0` / `amount_claimed >= 0` y valoraciones >= 0

