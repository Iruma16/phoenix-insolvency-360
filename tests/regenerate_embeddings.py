"""
Script para regenerar embeddings de un caso.
Útil después de corregir bugs en el sistema de embeddings (ej: añadir documents=batch_texts).
"""

import sys

from app.core.database import get_db
from app.models.case import Case
from app.models.document import Document
from app.services.document_chunk_pipeline import build_document_chunks_for_case
from app.services.embeddings_pipeline import build_embeddings_for_case


def regenerate_embeddings_for_case(case_id: str, force_rebuild_chunks: bool = False):
    """
    Regenera los embeddings de un caso.

    Parámetros
    ----------
    case_id : str
        ID del caso
    force_rebuild_chunks : bool
        Si True, regenera también los chunks antes de los embeddings
    """
    print("=" * 80)
    print("REGENERACIÓN DE EMBEDDINGS")
    print("=" * 80)
    print(f"Case ID: {case_id}")
    print(f"Forzar rebuild de chunks: {force_rebuild_chunks}")
    print()

    db = next(get_db())

    try:
        # Verificar que el caso existe
        case = db.query(Case).filter(Case.case_id == case_id).first()
        if not case:
            print(f"❌ ERROR: Caso no encontrado: {case_id}")
            return False

        print(f"✅ Caso encontrado: {case.name}")

        # Contar documentos
        doc_count = db.query(Document).filter(Document.case_id == case_id).count()
        print(f"📄 Documentos en el caso: {doc_count}")

        if doc_count == 0:
            print("⚠️  No hay documentos para procesar")
            return False

        # Paso 1: Regenerar chunks si es necesario
        if force_rebuild_chunks:
            print()
            print("-" * 80)
            print("PASO 1: Regenerando chunks...")
            print("-" * 80)
            build_document_chunks_for_case(
                db=db,
                case_id=case_id,
                overwrite=True,  # Forzar regeneración
            )
            print("✅ Chunks regenerados")
        else:
            print()
            print(
                "ℹ️  Saltando regeneración de chunks (usar force_rebuild_chunks=True para regenerar)"
            )

        # Paso 2: Regenerar embeddings
        print()
        print("-" * 80)
        print("PASO 2: Regenerando embeddings...")
        print("-" * 80)

        # Eliminar vectorstore antiguo para forzar regeneración completa
        from app.core.variables import CASES_VECTORSTORE_BASE

        vectorstore_path = CASES_VECTORSTORE_BASE / case_id / "vectorstore"
        if vectorstore_path.exists():
            import shutil

            print(f"🗑️  Eliminando vectorstore antiguo: {vectorstore_path}")
            shutil.rmtree(vectorstore_path)
            print("✅ Vectorstore eliminado")

        # Generar nuevos embeddings
        build_embeddings_for_case(db=db, case_id=case_id)

        print()
        print("=" * 80)
        print("✅ REGENERACIÓN COMPLETADA")
        print("=" * 80)
        print(f"Case ID: {case_id}")
        print(f"Documentos procesados: {doc_count}")
        print()
        print("⚠️  IMPORTANTE: Los embeddings anteriores han sido eliminados y regenerados.")
        print("   Los nuevos embeddings ahora incluyen los documentos (textos) correctamente.")

        return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        db.close()


def main():
    if len(sys.argv) < 2:
        print("Uso: python regenerate_embeddings.py <case_id> [force_rebuild_chunks]")
        print("\nEjemplo:")
        print("  python regenerate_embeddings.py case-id-123")
        print("  python regenerate_embeddings.py case-id-123 true  # Regenera también chunks")
        sys.exit(1)

    case_id = sys.argv[1]
    force_rebuild_chunks = len(sys.argv) > 2 and sys.argv[2].lower() == "true"

    success = regenerate_embeddings_for_case(case_id, force_rebuild_chunks)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
