# Sistema de Versionado del Vectorstore

## Descripción General

El sistema de versionado del vectorstore garantiza **consistencia, auditabilidad y fallo seguro** para los embeddings de casos en PHOENIX.

**Principio fundamental**: NUNCA sobrescribir un vectorstore existente. Cada ingesta crea una versión nueva inmutable.

---

## Arquitectura

### Estructura de Directorios

```
clients_data/_vectorstore/cases/{case_id}/
├── v_20260105_143052/          # Versión 1
│   ├── index/                  # ChromaDB vectorstore
│   ├── manifest.json           # Metadatos técnicos
│   └── status.json             # Estado de la versión
├── v_20260105_150230/          # Versión 2
│   ├── index/
│   ├── manifest.json
│   └── status.json
├── v_20260105_152010/          # Versión 3 (más reciente)
│   ├── index/
│   ├── manifest.json
│   └── status.json
└── ACTIVE                      # Puntero a versión activa (symlink o archivo)
```

### Componentes Clave

1. **Versión**: Directorio inmutable con formato `v_YYYYMMDD_HHMMSS`
2. **index/**: Directorio de ChromaDB con los embeddings
3. **manifest.json**: Metadatos técnicos (documentos, chunks, SHA256, modelo)
4. **status.json**: Estado de la versión (BUILDING | READY | FAILED)
5. **ACTIVE**: Puntero lógico a la versión activa (solo apunta a versiones READY)

---

## Flujo de Ingesta

### Estados de una Versión

```
BUILDING  →  READY    (validación OK)
         ↘  FAILED   (validación KO)
```

### Pipeline Completo

```
1. create_new_version()
   ↓
   status = BUILDING
   
2. Ejecutar ingesta y embeddings
   ↓
   - Leer documentos
   - Generar chunks
   - Crear embeddings
   - Insertar en ChromaDB
   
3. Generar manifest.json
   ↓
   - SHA256 de documentos
   - Metadatos de chunks
   - Modelo de embeddings
   
4. validate_version_integrity()
   ↓
   BLOQUEANTE: Si falla → status=FAILED + abort
   
5. status = READY
   
6. update_active_pointer()
   ↓
   ACTIVE → nueva versión
   
7. cleanup_old_versions()
   ↓
   Eliminar versiones antiguas (mantener N)
```

---

## Validaciones de Integridad (BLOQUEANTES)

Antes de marcar una versión como READY, se ejecutan las siguientes validaciones:

1. ✅ **Número de chunks**: `chunks_reales == manifest.total_chunks`
2. ✅ **Documentos completos**: Todos los `doc_id` del manifest existen en ChromaDB
3. ✅ **case_id consistente**: Todos los chunks tienen el `case_id` correcto en metadata
4. ✅ **Índice accesible**: El directorio `index/` existe y ChromaDB puede leerlo
5. ✅ **Modelo correcto**: `manifest.embedding_model == EMBEDDING_MODEL`

**Si falla CUALQUIER validación** → `status=FAILED` + excepción + NO se actualiza ACTIVE.

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
      "filename": "contrato_alquiler.pdf",
      "sha256": "a3f8b2c1d4e5f6...",
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
  "status": "READY",
  "updated_at": "2026-01-05T14:31:10.987654"
}
```

---

## Gestión de Versiones

### Housekeeping Automático

El sistema mantiene automáticamente un número configurable de versiones (default: 3).

**Reglas**:
- Mantener las N versiones READY más recientes
- NUNCA eliminar la versión ACTIVE
- Log obligatorio de todas las eliminaciones

**Ejecución**:
```python
from app.services.vectorstore_versioning import cleanup_old_versions

# Mantener últimas 5 versiones
cleanup_old_versions(case_id="case_001", keep_last=5)
```

### CLI de Gestión

```bash
# Listar versiones de un caso
python scripts/manage_vectorstore_versions.py list case_001

# Ver información detallada de una versión
python scripts/manage_vectorstore_versions.py info case_001 v_20260105_143052

# Activar una versión específica
python scripts/manage_vectorstore_versions.py activate case_001 v_20260105_143052

# Validar integridad de una versión
python scripts/manage_vectorstore_versions.py validate case_001 v_20260105_143052

# Limpiar versiones antiguas (mantener 3)
python scripts/manage_vectorstore_versions.py cleanup case_001 --keep 3

# Reconstruir embeddings (crea nueva versión)
python scripts/manage_vectorstore_versions.py rebuild case_001
```

---

## Uso Programático

### Crear Nueva Versión

```python
from sqlalchemy.orm import Session
from app.services.embeddings_pipeline import build_embeddings_for_case

def rebuild_case_embeddings(db: Session, case_id: str):
    """Crea una nueva versión del vectorstore."""
    try:
        version_id = build_embeddings_for_case(
            db=db,
            case_id=case_id,
            keep_versions=3,  # Mantener últimas 3 versiones
        )
        print(f"✅ Nueva versión creada: {version_id}")
        return version_id
    except Exception as e:
        print(f"❌ Error: {e}")
        raise
```

### Consultar Versión Activa

```python
from app.services.vectorstore_versioning import (
    get_active_version,
    get_active_version_path,
)

# Obtener ID de versión activa
version = get_active_version("case_001")
print(f"Versión activa: {version}")

# Obtener ruta completa
path = get_active_version_path("case_001")
print(f"Ruta: {path}")
```

### Listar y Filtrar Versiones

```python
from app.services.vectorstore_versioning import list_versions

# Listar todas las versiones
versions = list_versions("case_001")

# Filtrar solo versiones READY
ready_versions = [v for v in versions if v.is_ready()]

# Versión más reciente
latest = versions[0] if versions else None
```

### Activar Versión Manualmente

```python
from app.services.vectorstore_versioning import update_active_pointer

# Activar una versión específica (debe estar en estado READY)
try:
    update_active_pointer("case_001", "v_20260105_143052")
    print("✅ Versión activada")
except RuntimeError as e:
    print(f"❌ Error: {e}")
```

---

## Logs Técnicos

Todos los eventos críticos se registran en el logger de la aplicación:

```
[VERSIONADO] Creando nueva versión: v_20260105_143052 para case_id=case_001
[VERSIONADO] Versión creada: /path/to/v_20260105_143052
[VERSIONADO] Status actualizado: case_id=case_001, version=v_20260105_143052, status=BUILDING
[EMBEDDINGS] Modelo: text-embedding-3-large, Dimensión: 3072
[EMBEDDINGS] Procesando batch 1
[EMBEDDINGS] ✅ Batch insertado
[VERSIONADO] Manifest creado: case_id=case_001, version=v_20260105_143052, total_chunks=47
[VALIDACIÓN] ✅ Versión válida: case_id=case_001, version=v_20260105_143052
[VERSIONADO] ✅ Versión marcada como READY
[VERSIONADO] ✅ Puntero ACTIVE actualizado
[HOUSEKEEPING] ✅ Versión eliminada: v_20260103_120000 (status=READY, created_at=2026-01-03T12:00:00)
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

## Recuperación ante Fallos

### Escenario 1: Fallo durante ingesta

```
Estado inicial:
  ACTIVE → v_20260105_100000 (READY)

Nueva ingesta:
  1. Crear v_20260105_143052 (BUILDING)
  2. ❌ Error en embeddings
  3. status = FAILED
  4. ACTIVE sigue apuntando a v_20260105_100000

Resultado: Sistema sigue funcionando con la versión anterior.
```

### Escenario 2: Validación falla

```
Estado inicial:
  ACTIVE → v_20260105_100000 (READY)

Nueva ingesta:
  1. Crear v_20260105_143052 (BUILDING)
  2. Embeddings OK
  3. Manifest OK
  4. ❌ Validación falla (chunks no coinciden)
  5. status = FAILED
  6. ACTIVE sigue apuntando a v_20260105_100000

Resultado: Sistema sigue funcionando con la versión anterior.
```

### Escenario 3: Rollback manual

```bash
# Listar versiones
python scripts/manage_vectorstore_versions.py list case_001

# Salida:
# ✅ Versión ACTIVE: v_20260105_143052
# v_20260105_143052  ✅ READY     2026-01-05 14:30:52  ✅
# v_20260105_100000  ✅ READY     2026-01-05 10:00:00

# Rollback a versión anterior
python scripts/manage_vectorstore_versions.py activate case_001 v_20260105_100000

# ✅ Versión v_20260105_100000 activada correctamente
```

---

## Migración desde Sistema Anterior

El sistema anterior usaba:
```
clients_data/cases/{case_id}/vectorstore/
```

El nuevo sistema usa:
```
clients_data/_vectorstore/cases/{case_id}/
├── v_YYYYMMDD_HHMMSS/
└── ACTIVE
```

**No hay migración automática**. El primer `build_embeddings_for_case()` creará la estructura nueva.

El sistema anterior seguirá funcionando hasta que se regeneren los embeddings.

---

## FAQ

### ¿Qué pasa si elimino ACTIVE por error?

El sistema intentará regenerar embeddings automáticamente si `RAG_AUTO_BUILD_EMBEDDINGS=True`.

Alternativamente, puedes activar manualmente una versión READY:
```bash
python scripts/manage_vectorstore_versions.py activate case_001 v_20260105_143052
```

### ¿Puedo tener múltiples versiones ACTIVE?

No. Solo puede haber un puntero ACTIVE por caso.

### ¿Las versiones FAILED ocupan espacio?

Sí. El housekeeping NO elimina automáticamente versiones FAILED (por seguridad).

Puedes eliminarlas manualmente:
```bash
rm -rf clients_data/_vectorstore/cases/case_001/v_20260105_143052
```

### ¿Puedo cambiar el modelo de embeddings?

Sí, pero generará una versión nueva con un modelo diferente.

**IMPORTANTE**: Las versiones con diferentes modelos NO son compatibles.

### ¿Cómo sé qué versión está usando el RAG?

```python
from app.services.vectorstore_versioning import get_active_version

version = get_active_version("case_001")
print(f"RAG usa versión: {version}")
```

---

## Referencias Técnicas

- **Módulo principal**: `app/services/vectorstore_versioning.py`
- **Pipeline de embeddings**: `app/services/embeddings_pipeline.py`
- **RAG con versionado**: `app/rag/case_rag/retrieve.py`
- **CLI de gestión**: `scripts/manage_vectorstore_versions.py`

