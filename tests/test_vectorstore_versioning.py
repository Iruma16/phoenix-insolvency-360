"""
Tests de integración para el sistema de versionado del vectorstore.

IMPORTANTE: Estos tests validan el comportamiento crítico del sistema.
"""

import shutil
from datetime import datetime

import pytest

from app.core.database import SessionLocal
from app.core.variables import EMBEDDING_MODEL
from app.models.case import Case
from app.models.document_chunk import DocumentChunk
from app.services.document_chunk_pipeline import build_document_chunks_for_case
from app.services.embeddings_pipeline import (
    build_embeddings_for_case,
    get_case_collection,
)
from app.services.folder_ingestion import ingest_file_from_path
from app.services.vectorstore_versioning import (
    ManifestData,
    _get_case_vectorstore_root,
    cleanup_old_versions,
    create_new_version,
    get_active_version,
    list_versions,
    read_manifest,
    read_status,
    update_active_pointer,
    validate_version_integrity,
    write_manifest,
    write_status,
)


@pytest.fixture
def test_case_id():
    """Genera un case_id único para tests."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"test_versioning_{timestamp}"


@pytest.fixture
def db_session():
    """Crea una sesión de BD para tests."""
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture
def cleanup_test_case(test_case_id):
    """Limpia el vectorstore de test después de cada test."""
    yield
    # Cleanup
    root = _get_case_vectorstore_root(test_case_id)
    if root.exists():
        shutil.rmtree(root)


def test_create_new_version(test_case_id, cleanup_test_case):
    """Test: Crear una nueva versión genera estructura correcta."""
    version_id, version_path = create_new_version(test_case_id)

    # Validar que se creó la versión
    assert version_id.startswith("v_")
    assert version_path.exists()
    assert version_path.is_dir()

    # Validar que existe el directorio index
    index_path = version_path / "index"
    assert index_path.exists()
    assert index_path.is_dir()

    # Validar que existe status.json con estado BUILDING
    status = read_status(test_case_id, version_id)
    assert status["case_id"] == test_case_id
    assert status["version"] == version_id
    assert status["status"] == "BUILDING"
    assert "updated_at" in status


def test_version_uniqueness(test_case_id, cleanup_test_case):
    """Test: Dos versiones consecutivas tienen IDs únicos."""
    version_id_1, _ = create_new_version(test_case_id)
    version_id_2, _ = create_new_version(test_case_id)

    assert version_id_1 != version_id_2


def test_status_lifecycle(test_case_id, cleanup_test_case):
    """Test: Ciclo de vida de estados BUILDING → READY."""
    version_id, _ = create_new_version(test_case_id)

    # Estado inicial: BUILDING
    status = read_status(test_case_id, version_id)
    assert status["status"] == "BUILDING"

    # Cambiar a READY
    write_status(test_case_id, version_id, "READY")
    status = read_status(test_case_id, version_id)
    assert status["status"] == "READY"

    # Cambiar a FAILED
    write_status(test_case_id, version_id, "FAILED")
    status = read_status(test_case_id, version_id)
    assert status["status"] == "FAILED"


def test_manifest_generation(test_case_id, cleanup_test_case):
    """Test: Generar y leer manifest.json."""
    version_id, _ = create_new_version(test_case_id)

    manifest_data = ManifestData(
        case_id=test_case_id,
        version=version_id,
        embedding_model=EMBEDDING_MODEL,
        embedding_dim=3072,
        chunking={
            "strategy": "recursive_text_splitter",
            "chunk_size": 2000,
            "overlap": 200,
        },
        documents=[
            {
                "doc_id": "doc_test_001",
                "filename": "test.pdf",
                "sha256": "abc123",
                "num_chunks": 10,
            }
        ],
        total_chunks=10,
        created_at=datetime.now().isoformat(),
    )

    write_manifest(test_case_id, version_id, manifest_data)

    # Leer y validar
    manifest = read_manifest(test_case_id, version_id)
    assert manifest["case_id"] == test_case_id
    assert manifest["version"] == version_id
    assert manifest["embedding_model"] == EMBEDDING_MODEL
    assert manifest["total_chunks"] == 10
    assert len(manifest["documents"]) == 1


def test_active_pointer_lifecycle(test_case_id, cleanup_test_case):
    """Test: Puntero ACTIVE funciona correctamente."""
    # Crear versión 1
    version_id_1, _ = create_new_version(test_case_id)
    write_status(test_case_id, version_id_1, "READY")

    # No debería haber ACTIVE todavía
    active = get_active_version(test_case_id)
    assert active is None

    # Activar versión 1
    update_active_pointer(test_case_id, version_id_1)
    active = get_active_version(test_case_id)
    assert active == version_id_1

    # Crear versión 2 y activarla
    version_id_2, _ = create_new_version(test_case_id)
    write_status(test_case_id, version_id_2, "READY")
    update_active_pointer(test_case_id, version_id_2)

    active = get_active_version(test_case_id)
    assert active == version_id_2


def test_cannot_activate_non_ready_version(test_case_id, cleanup_test_case):
    """Test: No se puede activar una versión que no está READY."""
    version_id, _ = create_new_version(test_case_id)

    # Status es BUILDING por defecto
    with pytest.raises(RuntimeError, match="status=BUILDING"):
        update_active_pointer(test_case_id, version_id)

    # Cambiar a FAILED
    write_status(test_case_id, version_id, "FAILED")
    with pytest.raises(RuntimeError, match="status=FAILED"):
        update_active_pointer(test_case_id, version_id)


def test_list_versions(test_case_id, cleanup_test_case):
    """Test: Listar versiones funciona correctamente."""
    # Sin versiones
    versions = list_versions(test_case_id)
    assert len(versions) == 0

    # Crear 3 versiones
    version_ids = []
    for _ in range(3):
        version_id, _ = create_new_version(test_case_id)
        write_status(test_case_id, version_id, "READY")
        version_ids.append(version_id)

    # Listar
    versions = list_versions(test_case_id)
    assert len(versions) == 3

    # Verificar orden (más reciente primero)
    assert versions[0].version == version_ids[-1]
    assert versions[-1].version == version_ids[0]

    # Verificar que todas están READY
    for v in versions:
        assert v.is_ready()


def test_cleanup_old_versions(test_case_id, cleanup_test_case):
    """Test: Limpieza de versiones antiguas mantiene las N más recientes."""
    # Crear 5 versiones READY
    version_ids = []
    for _ in range(5):
        version_id, _ = create_new_version(test_case_id)
        write_status(test_case_id, version_id, "READY")
        version_ids.append(version_id)

    # Activar la última
    update_active_pointer(test_case_id, version_ids[-1])

    # Limpiar manteniendo solo 3
    deleted_count = cleanup_old_versions(test_case_id, keep_last=3)

    # Deberían haberse eliminado 2 versiones
    assert deleted_count == 2

    # Verificar que quedan 3
    versions = list_versions(test_case_id)
    assert len(versions) == 3

    # Verificar que ACTIVE sigue intacto
    active = get_active_version(test_case_id)
    assert active == version_ids[-1]


def test_cleanup_never_deletes_active(test_case_id, cleanup_test_case):
    """Test: Limpieza NUNCA elimina la versión ACTIVE."""
    # Crear 5 versiones
    version_ids = []
    for _ in range(5):
        version_id, _ = create_new_version(test_case_id)
        write_status(test_case_id, version_id, "READY")
        version_ids.append(version_id)

    # Activar la PRIMERA versión (antigua)
    update_active_pointer(test_case_id, version_ids[0])

    # Limpiar manteniendo solo 2
    deleted_count = cleanup_old_versions(test_case_id, keep_last=2)

    # Verificar que ACTIVE sigue existiendo
    active = get_active_version(test_case_id)
    assert active == version_ids[0]

    # Verificar que la versión ACTIVE existe
    versions = list_versions(test_case_id)
    active_exists = any(v.version == version_ids[0] for v in versions)
    assert active_exists


def test_case_id_validation_in_status(test_case_id, cleanup_test_case):
    """Test: Validación de case_id en status.json."""
    version_id, _ = create_new_version(test_case_id)

    # Escribir status con case_id diferente (corromper datos)
    wrong_case_id = "wrong_case_id"
    status_path = _get_case_vectorstore_root(test_case_id) / version_id / "status.json"

    import json

    with open(status_path, "w") as f:
        json.dump(
            {
                "case_id": wrong_case_id,
                "version": version_id,
                "status": "READY",
                "updated_at": datetime.now().isoformat(),
            },
            f,
        )

    # Intentar leer debería fallar
    with pytest.raises(ValueError, match="case_id no coincide"):
        read_status(test_case_id, version_id)


def test_case_id_validation_in_manifest(test_case_id, cleanup_test_case):
    """Test: Validación de case_id en manifest.json."""
    version_id, _ = create_new_version(test_case_id)

    # Intentar escribir manifest con case_id diferente
    wrong_manifest = ManifestData(
        case_id="wrong_case_id",  # ❌ case_id incorrecto
        version=version_id,
        embedding_model=EMBEDDING_MODEL,
        embedding_dim=3072,
        chunking={},
        documents=[],
        total_chunks=0,
        created_at=datetime.now().isoformat(),
    )

    with pytest.raises(ValueError, match="case_id no coincide"):
        write_manifest(test_case_id, version_id, wrong_manifest)


@pytest.mark.integration
def test_full_pipeline_with_real_document(db_session, test_case_id, cleanup_test_case, tmp_path):
    """
    Test de integración completo: ingesta → chunks → embeddings → versionado.

    NOTA: Requiere API key de OpenAI configurada.
    """
    # 1. Crear caso en BD
    case = Case(case_id=test_case_id, case_name="Test Versioning")
    db_session.add(case)
    db_session.commit()

    # 2. Crear un documento de prueba
    test_file = tmp_path / "test_document.txt"
    test_file.write_text(
        "Este es un documento de prueba para el sistema de versionado del vectorstore."
    )

    # 3. Ingerir documento
    document, warnings = ingest_file_from_path(
        db=db_session,
        file_path=test_file,
        case_id=test_case_id,
        doc_type="contrato",
        source="test",
    )

    assert document is not None
    assert document.case_id == test_case_id

    # 4. Generar chunks
    build_document_chunks_for_case(db=db_session, case_id=test_case_id, overwrite=False)

    chunks = db_session.query(DocumentChunk).filter(DocumentChunk.case_id == test_case_id).all()
    assert len(chunks) > 0

    # 5. Generar embeddings (crea versión automáticamente)
    version_id = build_embeddings_for_case(db=db_session, case_id=test_case_id)

    # Validar que se creó la versión
    assert version_id.startswith("v_")

    # Validar que la versión está READY
    status = read_status(test_case_id, version_id)
    assert status["status"] == "READY"

    # Validar que ACTIVE apunta a la nueva versión
    active = get_active_version(test_case_id)
    assert active == version_id

    # Validar que existe el manifest
    manifest = read_manifest(test_case_id, version_id)
    assert manifest["case_id"] == test_case_id
    assert manifest["total_chunks"] == len(chunks)
    assert manifest["embedding_model"] == EMBEDDING_MODEL

    # Validar que el vectorstore es accesible
    collection = get_case_collection(test_case_id, version=None)  # None = usar ACTIVE
    assert collection.count() == len(chunks)

    # 6. Crear segunda versión (rebuild)
    version_id_2 = build_embeddings_for_case(db=db_session, case_id=test_case_id)

    assert version_id_2 != version_id
    assert version_id_2.startswith("v_")

    # Validar que ACTIVE cambió
    active = get_active_version(test_case_id)
    assert active == version_id_2

    # Validar que ambas versiones existen
    versions = list_versions(test_case_id)
    assert len(versions) == 2

    # 7. Limpieza final
    db_session.delete(case)
    db_session.commit()


@pytest.mark.integration
def test_validation_detects_corrupted_data(db_session, test_case_id, cleanup_test_case, tmp_path):
    """
    Test: Las validaciones detectan datos corruptos.

    NOTA: Requiere API key de OpenAI configurada.
    """
    # 1. Crear caso y documento
    case = Case(case_id=test_case_id, case_name="Test Validation")
    db_session.add(case)
    db_session.commit()

    test_file = tmp_path / "test.txt"
    test_file.write_text("Contenido de prueba para validación.")

    document, _ = ingest_file_from_path(
        db=db_session,
        file_path=test_file,
        case_id=test_case_id,
        doc_type="contrato",
    )

    # 2. Generar chunks
    build_document_chunks_for_case(db=db_session, case_id=test_case_id)

    chunks = db_session.query(DocumentChunk).filter(DocumentChunk.case_id == test_case_id).all()

    # 3. Crear versión y generar embeddings
    version_id = build_embeddings_for_case(db=db_session, case_id=test_case_id)

    # 4. Corromper el manifest (cambiar total_chunks)
    manifest = read_manifest(test_case_id, version_id)
    manifest["total_chunks"] = 9999  # ❌ Valor incorrecto

    manifest_path = _get_case_vectorstore_root(test_case_id) / version_id / "manifest.json"
    import json

    with open(manifest_path, "w") as f:
        json.dump(manifest, f)

    # 5. Validar integridad (debería fallar)
    collection = get_case_collection(test_case_id, version=version_id)
    is_valid, errors = validate_version_integrity(test_case_id, version_id, collection)

    assert not is_valid
    assert len(errors) > 0
    assert any("no coincide" in error for error in errors)

    # Limpieza
    db_session.delete(case)
    db_session.commit()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
