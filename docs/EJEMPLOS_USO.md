# Ejemplos de Uso: Sistema de Versionado del Vectorstore

Guía práctica con ejemplos reales de uso del sistema de versionado.

---

## 📋 Índice

1. [Uso Básico](#uso-básico)
2. [Gestión de Versiones](#gestión-de-versiones)
3. [Validación y Troubleshooting](#validación-y-troubleshooting)
4. [Escenarios Avanzados](#escenarios-avanzados)
5. [Integración en Workflows](#integración-en-workflows)

---

## Uso Básico

### Ejemplo 1: Crear Primera Versión de un Caso

```python
from app.core.database import SessionLocal
from app.services.embeddings_pipeline import build_embeddings_for_case

# Crear sesión de BD
db = SessionLocal()

try:
    # Generar embeddings para un caso
    # Esto crea automáticamente la primera versión
    version_id = build_embeddings_for_case(
        db=db,
        case_id="case_001",
    )
    
    print(f"✅ Primera versión creada: {version_id}")
    # Salida: ✅ Primera versión creada: v_20260105_143052
    
finally:
    db.close()
```

### Ejemplo 2: Regenerar Embeddings (Crear Nueva Versión)

```python
from app.core.database import SessionLocal
from app.services.embeddings_pipeline import build_embeddings_for_case

db = SessionLocal()

try:
    # Esto crea una NUEVA versión (no sobrescribe la anterior)
    version_id = build_embeddings_for_case(
        db=db,
        case_id="case_001",
        keep_versions=5,  # Mantener últimas 5 versiones
    )
    
    print(f"✅ Nueva versión creada: {version_id}")
    # La versión anterior sigue existiendo
    # ACTIVE ahora apunta a la nueva versión
    
finally:
    db.close()
```

### Ejemplo 3: Consultar RAG (Usa Versión ACTIVE Automáticamente)

```python
from app.core.database import SessionLocal
from app.rag.case_rag.service import query_case_rag

db = SessionLocal()

try:
    # El RAG usa automáticamente la versión ACTIVE
    # No necesitas especificar la versión
    contexto = query_case_rag(
        db=db,
        case_id="case_001",
        query="¿Cuál es el importe de la deuda principal?",
    )
    
    print(f"Contexto recuperado: {contexto[:200]}...")
    
finally:
    db.close()
```

---

## Gestión de Versiones

### Ejemplo 4: Listar Versiones desde Python

```python
from app.services.vectorstore_versioning import (
    list_versions,
    get_active_version,
)

# Listar todas las versiones
versions = list_versions("case_001")

print(f"Total versiones: {len(versions)}")
print()

# Obtener versión activa
active = get_active_version("case_001")
print(f"Versión ACTIVE: {active}")
print()

# Mostrar información de cada versión
for v in versions:
    is_active = "✅ ACTIVE" if v.version == active else ""
    print(f"{v.version} | {v.status} | {v.created_at.strftime('%Y-%m-%d %H:%M')} {is_active}")
```

**Salida esperada**:
```
Total versiones: 3

Versión ACTIVE: v_20260105_152010

v_20260105_152010 | READY | 2026-01-05 15:20 ✅ ACTIVE
v_20260105_150230 | READY | 2026-01-05 15:02
v_20260105_143052 | READY | 2026-01-05 14:30
```

### Ejemplo 5: Listar Versiones desde CLI

```bash
# Listar versiones
python scripts/manage_vectorstore_versions.py list case_001
```

**Salida esperada**:
```
================================================================================
VERSIONES DEL VECTORSTORE - case_id: case_001
================================================================================

✅ Versión ACTIVE: v_20260105_152010

Total versiones: 3

VERSION                   STATUS       CREATED AT                ACTIVE
--------------------------------------------------------------------------------
v_20260105_152010         ✅ READY     2026-01-05 15:20:10       ✅
v_20260105_150230         ✅ READY     2026-01-05 15:02:30
v_20260105_143052         ✅ READY     2026-01-05 14:30:52
```

### Ejemplo 6: Ver Información Detallada de una Versión

```bash
# Ver info detallada con manifest
python scripts/manage_vectorstore_versions.py info case_001 v_20260105_143052 -v
```

**Salida esperada**:
```
================================================================================
INFORMACIÓN DE VERSIÓN
================================================================================
case_id: case_001
version: v_20260105_143052

STATUS:
{
  "case_id": "case_001",
  "version": "v_20260105_143052",
  "status": "READY",
  "updated_at": "2026-01-05T14:31:10.987654"
}

MANIFEST:
  Embedding model: text-embedding-3-large
  Embedding dim: 3072
  Total chunks: 47
  Documentos: 5
  Creado: 2026-01-05T14:30:52.123456

DOCUMENTOS:
  - contrato_alquiler.pdf
    doc_id: doc_12345
    SHA256: a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5
    Chunks: 15
  - balance_2024.xlsx
    doc_id: doc_12346
    SHA256: b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9
    Chunks: 8
  ...
```

---

## Validación y Troubleshooting

### Ejemplo 7: Validar Integridad de una Versión

```python
from app.services.vectorstore_versioning import validate_version_integrity
from app.services.embeddings_pipeline import get_case_collection

case_id = "case_001"
version = "v_20260105_143052"

# Obtener colección
collection = get_case_collection(case_id, version=version)

# Validar integridad
is_valid, errors = validate_version_integrity(case_id, version, collection)

if is_valid:
    print("✅ Versión VÁLIDA - Todas las validaciones pasaron")
else:
    print("❌ Versión INVÁLIDA - Errores encontrados:")
    for error in errors:
        print(f"  - {error}")
```

**Salida si hay errores**:
```
❌ Versión INVÁLIDA - Errores encontrados:
  - Número de chunks no coincide. Manifest: 50, ChromaDB: 47
  - Chunk 15 con case_id incorrecto. Esperado: case_001, Encontrado: case_002
  - Modelo de embeddings no coincide. Manifest: text-embedding-3-large, Sistema: text-embedding-ada-002
```

### Ejemplo 8: Validar desde CLI

```bash
# Validar integridad de una versión
python scripts/manage_vectorstore_versions.py validate case_001 v_20260105_143052
```

### Ejemplo 9: Detectar y Recuperar de Errores

```python
from app.core.database import SessionLocal
from app.services.embeddings_pipeline import build_embeddings_for_case
from app.services.vectorstore_versioning import get_active_version, list_versions

db = SessionLocal()

try:
    # Intentar regenerar embeddings
    try:
        version_id = build_embeddings_for_case(db=db, case_id="case_001")
        print(f"✅ Nueva versión creada: {version_id}")
    except Exception as e:
        print(f"❌ Error creando nueva versión: {e}")
        
        # Ver si existe versión ACTIVE válida anterior
        active = get_active_version("case_001")
        if active:
            print(f"✅ Versión ACTIVE anterior sigue funcionando: {active}")
            print("El sistema RAG seguirá usando la versión anterior.")
        else:
            print("⚠️  No existe versión ACTIVE. Se requiere intervención manual.")
            
            # Listar versiones disponibles
            versions = list_versions("case_001")
            ready_versions = [v for v in versions if v.is_ready()]
            
            if ready_versions:
                print(f"Versiones READY disponibles: {len(ready_versions)}")
                print("Puedes activar una manualmente con:")
                print(f"  python scripts/manage_vectorstore_versions.py activate case_001 {ready_versions[0].version}")
            else:
                print("No hay versiones READY disponibles. Se debe reconstruir desde cero.")
        
finally:
    db.close()
```

---

## Escenarios Avanzados

### Ejemplo 10: Rollback a Versión Anterior

```python
from app.services.vectorstore_versioning import (
    list_versions,
    update_active_pointer,
    read_status,
)

case_id = "case_001"

# Listar versiones READY
versions = list_versions(case_id)
ready_versions = [v for v in versions if v.is_ready()]

print(f"Versiones READY disponibles: {len(ready_versions)}")

# Seleccionar segunda versión más reciente (rollback)
if len(ready_versions) >= 2:
    target_version = ready_versions[1].version
    
    print(f"Activando versión anterior: {target_version}")
    
    try:
        update_active_pointer(case_id, target_version)
        print(f"✅ Rollback completado. ACTIVE → {target_version}")
    except Exception as e:
        print(f"❌ Error en rollback: {e}")
else:
    print("No hay versiones suficientes para rollback")
```

**Desde CLI**:
```bash
# Ver versiones disponibles
python scripts/manage_vectorstore_versions.py list case_001

# Activar versión anterior
python scripts/manage_vectorstore_versions.py activate case_001 v_20260105_143052

# Verificar que cambió
python scripts/manage_vectorstore_versions.py list case_001
```

### Ejemplo 11: Limpieza Manual de Versiones

```python
from app.services.vectorstore_versioning import (
    cleanup_old_versions,
    list_versions,
)

case_id = "case_001"

print("Versiones ANTES de limpieza:")
versions_before = list_versions(case_id)
print(f"  Total: {len(versions_before)}")

# Limpiar manteniendo solo las 2 más recientes
deleted_count = cleanup_old_versions(case_id, keep_last=2)

print(f"\nVersiones eliminadas: {deleted_count}")

print("\nVersiones DESPUÉS de limpieza:")
versions_after = list_versions(case_id)
print(f"  Total: {len(versions_after)}")
```

**Desde CLI**:
```bash
# Limpiar manteniendo últimas 3 versiones
python scripts/manage_vectorstore_versions.py cleanup case_001 --keep 3

# Con confirmación automática (para scripts)
python scripts/manage_vectorstore_versions.py cleanup case_001 --keep 3 --yes
```

### Ejemplo 12: Comparar Versiones (Manifest)

```python
from app.services.vectorstore_versioning import read_manifest

case_id = "case_001"
version_1 = "v_20260105_143052"
version_2 = "v_20260105_150230"

# Leer manifests
manifest_1 = read_manifest(case_id, version_1)
manifest_2 = read_manifest(case_id, version_2)

# Comparar
print(f"COMPARACIÓN DE VERSIONES")
print(f"=" * 60)
print(f"\n{'Campo':<25} {version_1:<25} {version_2:<25}")
print("-" * 60)

# Total chunks
print(f"{'Total chunks':<25} {manifest_1['total_chunks']:<25} {manifest_2['total_chunks']:<25}")

# Número de documentos
print(f"{'Nº documentos':<25} {len(manifest_1['documents']):<25} {len(manifest_2['documents']):<25}")

# Modelo
print(f"{'Embedding model':<25} {manifest_1['embedding_model']:<25} {manifest_2['embedding_model']:<25}")

# Documentos añadidos/eliminados
docs_1 = set(d['doc_id'] for d in manifest_1['documents'])
docs_2 = set(d['doc_id'] for d in manifest_2['documents'])

added = docs_2 - docs_1
removed = docs_1 - docs_2

if added:
    print(f"\nDocumentos AÑADIDOS en {version_2}:")
    for doc_id in added:
        doc = next(d for d in manifest_2['documents'] if d['doc_id'] == doc_id)
        print(f"  + {doc['filename']} ({doc['num_chunks']} chunks)")

if removed:
    print(f"\nDocumentos ELIMINADOS en {version_2}:")
    for doc_id in removed:
        doc = next(d for d in manifest_1['documents'] if d['doc_id'] == doc_id)
        print(f"  - {doc['filename']} ({doc['num_chunks']} chunks)")
```

---

## Integración en Workflows

### Ejemplo 13: Workflow Completo de Ingesta

```python
from app.core.database import SessionLocal
from app.models.case import Case
from app.services.folder_ingestion import ingest_folder
from app.services.document_chunk_pipeline import build_document_chunks_for_case
from app.services.embeddings_pipeline import build_embeddings_for_case
from pathlib import Path

# Configuración
case_id = "case_new_001"
case_name = "Caso: Empresa XYZ - Concurso"
documents_folder = Path("/ruta/a/documentos")

db = SessionLocal()

try:
    # 1. Crear caso en BD
    case = Case(case_id=case_id, case_name=case_name)
    db.add(case)
    db.commit()
    print(f"✅ Caso creado: {case_id}")
    
    # 2. Ingerir documentos
    print("\n📥 Ingiriendo documentos...")
    stats = ingest_folder(
        db=db,
        folder_path=documents_folder,
        case_id=case_id,
        recursive=True,
    )
    print(f"✅ Documentos procesados: {stats['processed']}")
    print(f"   Omitidos: {stats['skipped']}")
    print(f"   Errores: {stats['errors']}")
    
    # 3. Generar chunks
    print("\n🔪 Generando chunks...")
    build_document_chunks_for_case(db=db, case_id=case_id, overwrite=False)
    print("✅ Chunks generados")
    
    # 4. Generar embeddings (crea versión automáticamente)
    print("\n🧠 Generando embeddings...")
    version_id = build_embeddings_for_case(
        db=db,
        case_id=case_id,
        keep_versions=3,
    )
    print(f"✅ Embeddings generados: {version_id}")
    
    print(f"\n✅ Workflow completado para {case_id}")
    print(f"   Versión: {version_id}")
    print(f"   El RAG ya está disponible para consultas.")
    
except Exception as e:
    print(f"❌ Error en workflow: {e}")
    import traceback
    traceback.print_exc()
    db.rollback()
    
finally:
    db.close()
```

### Ejemplo 14: Workflow de Actualización de Documentos

```python
from app.core.database import SessionLocal
from app.services.folder_ingestion import ingest_folder
from app.services.document_chunk_pipeline import build_document_chunks_for_case
from app.services.embeddings_pipeline import build_embeddings_for_case
from app.services.vectorstore_versioning import get_active_version
from pathlib import Path

case_id = "case_001"
new_documents_folder = Path("/ruta/a/nuevos/documentos")

db = SessionLocal()

try:
    # 1. Obtener versión actual
    current_version = get_active_version(case_id)
    print(f"Versión actual: {current_version}")
    
    # 2. Ingerir nuevos documentos
    print("\n📥 Ingiriendo nuevos documentos...")
    stats = ingest_folder(
        db=db,
        folder_path=new_documents_folder,
        case_id=case_id,
        recursive=True,
    )
    
    if stats['processed'] == 0:
        print("⚠️  No se procesaron documentos nuevos. Abortando actualización.")
    else:
        print(f"✅ Documentos nuevos: {stats['processed']}")
        
        # 3. Regenerar chunks (solo para docs nuevos)
        print("\n🔪 Generando chunks para documentos nuevos...")
        build_document_chunks_for_case(db=db, case_id=case_id, overwrite=False)
        
        # 4. Regenerar embeddings (CREA NUEVA VERSIÓN)
        print("\n🧠 Generando nueva versión del vectorstore...")
        new_version = build_embeddings_for_case(db=db, case_id=case_id)
        
        print(f"\n✅ Actualización completada")
        print(f"   Versión anterior: {current_version}")
        print(f"   Versión nueva: {new_version}")
        print(f"   ACTIVE actualizado automáticamente")
        
        # La versión anterior sigue existiendo por si necesitas rollback
        
except Exception as e:
    print(f"❌ Error en actualización: {e}")
    import traceback
    traceback.print_exc()
    
    # Si falla, ACTIVE sigue apuntando a la versión anterior
    print(f"\n✅ ACTIVE sigue apuntando a versión anterior: {current_version}")
    print("El sistema RAG sigue funcionando normalmente.")
    
finally:
    db.close()
```

### Ejemplo 15: Script de Mantenimiento Nocturno

```python
"""
Script de mantenimiento nocturno.
Limpia versiones antiguas de todos los casos.
"""

from app.services.vectorstore_versioning import (
    cleanup_old_versions,
    _get_case_vectorstore_root,
)
from pathlib import Path

# Obtener todos los casos con vectorstore
vectorstore_root = Path("/ruta/a/clients_data/_vectorstore/cases")

if vectorstore_root.exists():
    case_dirs = [d for d in vectorstore_root.iterdir() if d.is_dir()]
    
    print(f"🧹 Mantenimiento nocturno: {len(case_dirs)} casos")
    print("=" * 60)
    
    total_deleted = 0
    
    for case_dir in case_dirs:
        case_id = case_dir.name
        
        try:
            deleted = cleanup_old_versions(case_id, keep_last=3)
            if deleted > 0:
                print(f"✅ {case_id}: {deleted} versiones eliminadas")
                total_deleted += deleted
        except Exception as e:
            print(f"❌ {case_id}: Error - {e}")
    
    print("=" * 60)
    print(f"✅ Mantenimiento completado")
    print(f"   Total versiones eliminadas: {total_deleted}")
else:
    print("⚠️  No existe directorio de vectorstore")
```

---

## Tips y Buenas Prácticas

### ✅ Tip 1: Mantener Logs Centralizados

```python
from app.core.logger import logger

# El sistema ya loggea automáticamente, pero puedes añadir logs adicionales
logger.info(f"[WORKFLOW] Iniciando ingesta para case_id={case_id}")
logger.info(f"[WORKFLOW] Usuario: {user_id}")
logger.info(f"[WORKFLOW] Origen: {source}")
```

### ✅ Tip 2: Verificar ACTIVE Antes de Consultas Críticas

```python
from app.services.vectorstore_versioning import get_active_version, read_status

case_id = "case_001"

# Verificar que existe ACTIVE
active = get_active_version(case_id)

if not active:
    raise RuntimeError(f"No existe versión ACTIVE para {case_id}")

# Verificar que está READY (debería serlo siempre)
status = read_status(case_id, active)
if status["status"] != "READY":
    raise RuntimeError(f"Versión ACTIVE tiene status={status['status']}")

# Ahora es seguro hacer consultas RAG
```

### ✅ Tip 3: Automatizar Regeneración Post-Ingesta

```python
# En tu endpoint de ingesta de documentos
from app.api.documents import router
from app.services.embeddings_pipeline import build_embeddings_for_case

@router.post("/cases/{case_id}/documents")
async def upload_documents(case_id: str, ...):
    # ... lógica de ingesta ...
    
    # Regenerar embeddings automáticamente después de ingestar
    try:
        version_id = build_embeddings_for_case(db=db, case_id=case_id)
        return {
            "status": "success",
            "documents_uploaded": uploaded_count,
            "vectorstore_version": version_id,
        }
    except Exception as e:
        # Si falla, los documentos están guardados pero sin embeddings
        # El usuario puede regenerar manualmente
        return {
            "status": "warning",
            "documents_uploaded": uploaded_count,
            "vectorstore_version": None,
            "error": str(e),
        }
```

---

## Resumen de Comandos CLI

```bash
# Listar versiones
python scripts/manage_vectorstore_versions.py list <case_id>

# Info detallada
python scripts/manage_vectorstore_versions.py info <case_id> <version> [-v]

# Activar versión
python scripts/manage_vectorstore_versions.py activate <case_id> <version>

# Validar integridad
python scripts/manage_vectorstore_versions.py validate <case_id> <version>

# Limpiar versiones antiguas
python scripts/manage_vectorstore_versions.py cleanup <case_id> [--keep N] [--yes]

# Reconstruir embeddings
python scripts/manage_vectorstore_versions.py rebuild <case_id> [--yes]
```

---

Para más información, consulta:
- **Documentación completa**: `docs/VECTORSTORE_VERSIONING.md`
- **Changelog**: `docs/CHANGELOG_VERSIONING.md`
- **Resumen ejecutivo**: `docs/RESUMEN_IMPLEMENTACION.md`

