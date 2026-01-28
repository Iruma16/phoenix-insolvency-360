# Changelog: Sistema de Versionado del Vectorstore

**Fecha**: 2026-01-05  
**Módulo**: Sistema RAG - Control de Vectorstore  
**Tipo**: Feature crítica + Hardening  

---

## Resumen Ejecutivo

Se ha implementado un **sistema de versionado estricto** para el vectorstore de casos, garantizando:

✅ **Consistencia**: case_id validado en todos los niveles  
✅ **Auditabilidad**: Logs completos + manifest técnico con SHA256  
✅ **Fallo seguro**: Validaciones bloqueantes antes de activar  
✅ **Trazabilidad**: Historial completo de versiones inmutables  

**Principio fundamental**: NUNCA sobrescribir un vectorstore existente.

---

## Problema Resuelto

### Antes (Sistema Anterior)

```
❌ Sin control de versión del vectorstore
❌ Sin control de integridad
❌ Sin trazabilidad técnica
❌ Sobrescritura directa del vectorstore
❌ Sin posibilidad de rollback
❌ case_id no validado estrictamente
```

### Después (Sistema Nuevo)

```
✅ Versionado explícito del vectorstore
✅ Validaciones de integridad BLOQUEANTES
✅ Trazabilidad completa (manifest + status + logs)
✅ Versiones inmutables con timestamps
✅ Rollback a versiones anteriores
✅ case_id validado en todos los niveles
✅ Activación segura solo de versiones válidas
✅ Housekeeping automático de versiones antiguas
```

---

## Cambios Técnicos

### Nuevos Módulos

#### 1. `app/services/vectorstore_versioning.py` (NUEVO)

Módulo central del sistema de versionado.

**Funciones principales**:
- `create_new_version()`: Crea versión nueva con estructura completa
- `write_status()` / `read_status()`: Gestión de status.json
- `write_manifest()` / `read_manifest()`: Gestión de manifest.json
- `validate_version_integrity()`: Validaciones bloqueantes de integridad
- `update_active_pointer()`: Actualiza puntero ACTIVE (solo versiones READY)
- `get_active_version()`: Obtiene versión activa
- `list_versions()`: Lista todas las versiones de un caso
- `cleanup_old_versions()`: Housekeeping automático

**Dataclasses**:
- `VersionInfo`: Información de una versión
- `ManifestData`: Datos del manifest técnico

### Módulos Modificados

#### 2. `app/services/embeddings_pipeline.py` (MODIFICADO)

**Cambios críticos**:
- ❌ **Eliminado**: Creación automática de estructura en `get_case_collection()`
- ✅ **Nuevo**: Pipeline completo con versionado estricto
- ✅ **Nuevo**: Validaciones de case_id en chunks y documentos
- ✅ **Nuevo**: Generación de manifest.json con SHA256
- ✅ **Nuevo**: Validación de integridad bloqueante
- ✅ **Nuevo**: Gestión de estados (BUILDING → READY | FAILED)
- ✅ **Nuevo**: Housekeeping automático al finalizar

**Nueva firma**:
```python
def build_embeddings_for_case(
    db: Session,
    *,
    case_id: str,
    openai_client: Optional[OpenAI] = None,
    keep_versions: int = 3,  # ← NUEVO parámetro
) -> str:  # ← Retorna version_id
```

**Flujo nuevo**:
```
1. create_new_version() → status=BUILDING
2. Cargar chunks + validar case_id
3. Generar embeddings por batches
4. Generar manifest.json
5. validate_version_integrity() → BLOQUEANTE
6. status=READY
7. update_active_pointer()
8. cleanup_old_versions()
```

#### 3. `app/rag/case_rag/retrieve.py` (MODIFICADO)

**Cambios**:
- ✅ **Nuevo**: Verifica existencia de versión ACTIVE antes de consultar
- ✅ **Nuevo**: Usa `get_active_version()` para obtener versión activa
- ✅ **Nuevo**: Manejo de errores mejorado con warnings
- ✅ **Nuevo**: Regeneración automática si ACTIVE no existe

**Antes**:
```python
collection = get_case_collection(case_id)  # Crea automáticamente si no existe
```

**Después**:
```python
active_version = get_active_version(case_id)
if not active_version:
    # Regenerar embeddings o retornar error
    ...
collection = get_case_collection(case_id, version=None)  # None = usar ACTIVE
```

### Nuevas Herramientas

#### 4. `scripts/manage_vectorstore_versions.py` (NUEVO)

CLI para gestión manual de versiones.

**Comandos**:
```bash
# Listar versiones
python scripts/manage_vectorstore_versions.py list case_001

# Ver info detallada
python scripts/manage_vectorstore_versions.py info case_001 v_20260105_143052 -v

# Activar versión específica
python scripts/manage_vectorstore_versions.py activate case_001 v_20260105_143052

# Validar integridad
python scripts/manage_vectorstore_versions.py validate case_001 v_20260105_143052

# Limpiar versiones antiguas
python scripts/manage_vectorstore_versions.py cleanup case_001 --keep 3

# Reconstruir embeddings
python scripts/manage_vectorstore_versions.py rebuild case_001
```

### Documentación

#### 5. `docs/VECTORSTORE_VERSIONING.md` (NUEVO)

Documentación técnica completa del sistema de versionado.

**Contenido**:
- Arquitectura del sistema
- Flujo de ingesta con estados
- Validaciones de integridad
- Gestión de versiones
- CLI de gestión
- Uso programático
- Logs técnicos
- Garantías del sistema
- Recuperación ante fallos
- FAQ

#### 6. `tests/test_vectorstore_versioning.py` (NUEVO)

Suite completa de tests de integración.

**Tests incluidos**:
- ✅ Creación de versiones
- ✅ Unicidad de versiones
- ✅ Ciclo de vida de estados
- ✅ Generación y lectura de manifest
- ✅ Puntero ACTIVE
- ✅ Restricción de activación (solo READY)
- ✅ Listado de versiones
- ✅ Limpieza de versiones antiguas
- ✅ Protección de versión ACTIVE
- ✅ Validaciones de case_id
- ✅ Pipeline completo con documento real
- ✅ Detección de datos corruptos

---

## Estructura de Directorios

### Antes

```
clients_data/
├── cases/{case_id}/
│   ├── documents/          # Documentos originales
│   └── vectorstore/        # ❌ Sobrescrito en cada ingesta
```

### Después

```
clients_data/
├── cases/{case_id}/
│   └── documents/          # Documentos originales (sin cambios)
└── _vectorstore/
    └── cases/{case_id}/
        ├── v_20260105_143052/      # Versión 1 (inmutable)
        │   ├── index/              # ChromaDB
        │   ├── manifest.json       # Metadatos
        │   └── status.json         # Estado
        ├── v_20260105_150230/      # Versión 2 (inmutable)
        │   ├── index/
        │   ├── manifest.json
        │   └── status.json
        └── ACTIVE                  # ← Puntero a versión activa
```

---

## Archivos de Control

### manifest.json

```json
{
  "case_id": "case_001",
  "version": "v_20260105_143052",
  "embedding_model": "text-embedding-3-large",
  "embedding_dim": 3072,
  "chunking": {
    "strategy": "recursive_text_splitter",
    "chunk_size": 2000,
    "overlap": 200
  },
  "documents": [
    {
      "doc_id": "doc_12345",
      "filename": "contrato.pdf",
      "sha256": "a3f8b2c1d4e5f6...",  # ← SHA256 del documento original
      "num_chunks": 15
    }
  ],
  "total_chunks": 47,
  "created_at": "2026-01-05T14:30:52.123456",
  "generator": "phoenix-ingestion"
}
```

### status.json

```json
{
  "case_id": "case_001",
  "version": "v_20260105_143052",
  "status": "READY",              # BUILDING | READY | FAILED
  "updated_at": "2026-01-05T14:31:10.987654"
}
```

---

## Reglas Críticas (NO NEGOCIABLES)

### REGLA 1 — case_id como clave dura

```
case_id DEBE estar presente y coincidir en:
- doc_id
- chunk_id
- metadata de embeddings
- vectorstore_path
- logs
- manifest.json
- status.json

Si falta o no coincide → EXCEPCIÓN + ABORTAR ingesta
```

### REGLA 2 — Versionado explícito del vectorstore

```
NUNCA sobrescribir un vectorstore existente.
Cada ejecución de ingesta crea una versión nueva.
```

### REGLA 3 — Flujo de estados obligatorio

```
BUILDING  →  READY    (validación OK)
         ↘  FAILED   (validación KO)

ACTIVE SOLO se actualiza cuando una versión es válida (READY).
```

### REGLA 4 — Manifest técnico obligatorio

```
Cada versión DEBE generar un manifest.json ANTES de activarse:
- SHA256 del documento (obligatorio)
- total_chunks debe coincidir con chunks reales
- embedding_model debe coincidir con el usado
```

### REGLA 5 — Validaciones de integridad (BLOQUEANTES)

```
Antes de marcar READY:
1. nº de chunks reales == total_chunks del manifest
2. todos los doc_id del manifest existen
3. todos los chunks contienen case_id correcto
4. el índice vectorial existe y es accesible
5. el modelo de embeddings coincide

Si falla CUALQUIERA → status=FAILED + excepción
```

### REGLA 6 — Política mínima de housekeeping

```
Implementar función explícita de limpieza:
- mantener N versiones (configurable, default=3)
- NO borrar la versión ACTIVE
- Log obligatorio de eliminaciones
```

### REGLA 7 — Logs técnicos obligatorios

```
Cada ejecución debe loggear:
- case_id
- version
- nº documentos
- nº chunks
- embedding_model
- estado final (READY / FAILED)
- motivo del fallo si aplica
```

---

## Impacto en APIs Públicas

### APIs que NO cambian (retrocompatibles)

✅ `query_case_rag()` - Usa ACTIVE automáticamente  
✅ `build_document_chunks_for_case()` - Sin cambios  
✅ `ingest_file_from_path()` - Sin cambios  
✅ `ingest_folder()` - Sin cambios  

### APIs con cambios internos

⚠️ `build_embeddings_for_case()`:
- **Antes**: No retornaba nada
- **Ahora**: Retorna `version_id: str`
- **Impacto**: Bajo (return value opcional)

⚠️ `get_case_collection()`:
- **Antes**: Creaba automáticamente si no existía
- **Ahora**: Requiere versión existente o levanta excepción
- **Impacto**: Bajo (el sistema RAG maneja esto automáticamente)

---

## Migración

### ¿Necesito migrar datos existentes?

**NO**. El sistema es retrocompatible.

El primer `build_embeddings_for_case()` creará la estructura nueva automáticamente.

### Estructura antigua

```
clients_data/cases/{case_id}/vectorstore/
```

Esta estructura **seguirá funcionando** hasta que se regeneren los embeddings.

### Regenerar embeddings para un caso

```python
from app.core.database import SessionLocal
from app.services.embeddings_pipeline import build_embeddings_for_case

db = SessionLocal()
try:
    version_id = build_embeddings_for_case(db=db, case_id="case_001")
    print(f"✅ Nueva versión: {version_id}")
finally:
    db.close()
```

O desde CLI:

```bash
python scripts/manage_vectorstore_versions.py rebuild case_001
```

---

## Tests

### Ejecutar tests unitarios

```bash
pytest tests/test_vectorstore_versioning.py -v
```

### Ejecutar tests de integración (requiere OpenAI API key)

```bash
pytest tests/test_vectorstore_versioning.py -v -m integration
```

### Salida esperada

```
tests/test_vectorstore_versioning.py::test_create_new_version PASSED
tests/test_vectorstore_versioning.py::test_version_uniqueness PASSED
tests/test_vectorstore_versioning.py::test_status_lifecycle PASSED
tests/test_vectorstore_versioning.py::test_manifest_generation PASSED
tests/test_vectorstore_versioning.py::test_active_pointer_lifecycle PASSED
tests/test_vectorstore_versioning.py::test_cannot_activate_non_ready_version PASSED
tests/test_vectorstore_versioning.py::test_list_versions PASSED
tests/test_vectorstore_versioning.py::test_cleanup_old_versions PASSED
tests/test_vectorstore_versioning.py::test_cleanup_never_deletes_active PASSED
tests/test_vectorstore_versioning.py::test_case_id_validation_in_status PASSED
tests/test_vectorstore_versioning.py::test_case_id_validation_in_manifest PASSED
tests/test_vectorstore_versioning.py::test_full_pipeline_with_real_document PASSED
tests/test_vectorstore_versioning.py::test_validation_detects_corrupted_data PASSED
```

---

## Logs Esperados

### Ingesta exitosa

```
[VERSIONADO] Creando nueva versión: v_20260105_143052 para case_id=case_001
[VERSIONADO] Versión creada: /path/to/v_20260105_143052
[EMBEDDINGS] Modelo: text-embedding-3-large, Dimensión: 3072
[EMBEDDINGS] Chunks encontrados: 47
[EMBEDDINGS] Procesando batch 1
[EMBEDDINGS] ✅ Batch insertado
[VERSIONADO] Manifest creado: case_id=case_001, version=v_20260105_143052, total_chunks=47
[VALIDACIÓN] ✅ Versión válida: case_id=case_001, version=v_20260105_143052
[VERSIONADO] Status actualizado: case_id=case_001, version=v_20260105_143052, status=READY
[VERSIONADO] Puntero ACTIVE actualizado
[HOUSEKEEPING] ✅ Versión eliminada: v_20260103_120000 (status=READY, created_at=2026-01-03T12:00:00)
[EMBEDDINGS] ✅ Pipeline completado exitosamente
```

### Ingesta fallida (validación)

```
[VERSIONADO] Creando nueva versión: v_20260105_143052 para case_id=case_001
[EMBEDDINGS] Procesando batch 1
[VALIDACIÓN] ❌ Versión INVÁLIDA: case_id=case_001, version=v_20260105_143052
[VALIDACIÓN]   - Número de chunks no coincide. Manifest: 50, ChromaDB: 47
[VERSIONADO] Status actualizado: case_id=case_001, version=v_20260105_143052, status=FAILED
[EMBEDDINGS] ❌ Pipeline falló. Versión marcada como FAILED: v_20260105_143052
```

---

## Garantías del Sistema

### ✅ Consistencia

- case_id presente y consistente en todos los niveles
- Validaciones bloqueantes antes de activar
- Estados determinísticos (BUILDING → READY | FAILED)

### ✅ Auditabilidad

- Logs técnicos obligatorios de todas las operaciones
- Manifest con SHA256 de documentos originales
- Historial completo de versiones

### ✅ Fallo Seguro

- Si falla la validación → status=FAILED + NO actualiza ACTIVE
- Versión ACTIVE siempre apunta a una versión válida (READY)
- Sistema anterior sigue funcionando si falla la nueva versión

### ✅ Inmutabilidad

- Versiones NUNCA se sobrescriben
- Cada ingesta crea una versión nueva con timestamp único
- Rollback posible activando una versión anterior

---

## Próximos Pasos (Futuro)

1. **Monitoreo**: Dashboard de versiones por caso
2. **Alertas**: Notificaciones si falla una ingesta
3. **Métricas**: Tamaño de versiones, tiempo de generación
4. **Compresión**: Archivar versiones antiguas pero no eliminarlas
5. **Diff**: Comparar manifests entre versiones

---

## Referencias

- **Documentación completa**: `docs/VECTORSTORE_VERSIONING.md`
- **Módulo principal**: `app/services/vectorstore_versioning.py`
- **Pipeline de embeddings**: `app/services/embeddings_pipeline.py`
- **Tests**: `tests/test_vectorstore_versioning.py`
- **CLI**: `scripts/manage_vectorstore_versions.py`

