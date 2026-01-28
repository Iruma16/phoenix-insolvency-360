"""
Script de ejemplo para probar la ingesta de carpetas.
"""

import sys
from pathlib import Path

from app.core.database import get_db
from app.services.folder_ingestion import ingest_file_from_path, ingest_folder


def test_ingest_file():
    """Ejemplo de ingesta de un archivo individual"""

    if len(sys.argv) < 4:
        print("Uso: python test_folder_ingestion.py file <file_path> <case_id> [doc_type]")
        print("\nEjemplo:")
        print("  python test_folder_ingestion.py file /ruta/al/archivo.pdf case-id-123 contrato")
        return

    file_path = Path(sys.argv[2])
    case_id = sys.argv[3]
    doc_type = sys.argv[4] if len(sys.argv) > 4 else None

    print("=" * 60)
    print("TEST: Ingesta de archivo individual")
    print("=" * 60)
    print(f"Archivo: {file_path}")
    print(f"Case ID: {case_id}")
    print(f"Tipo: {doc_type or 'auto'}")
    print()

    db = next(get_db())

    try:
        document, warnings = ingest_file_from_path(
            db=db,
            file_path=file_path,
            case_id=case_id,
            doc_type=doc_type,
            source="test_script",
        )

        if document:
            print("✅ Documento creado exitosamente")
            print(f"   Document ID: {document.document_id}")
            print(f"   Filename: {document.filename}")
            print(f"   Storage path: {document.storage_path}")
            if warnings:
                print(f"   ⚠️  Warnings: {len(warnings)}")
                for warning in warnings:
                    print(f"      - {warning}")
        else:
            print("❌ No se pudo crear el documento")
            if warnings:
                print(f"   ⚠️  Warnings: {len(warnings)}")
                for warning in warnings:
                    print(f"      - {warning}")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


def test_ingest_folder():
    """Ejemplo de ingesta de una carpeta completa"""

    if len(sys.argv) < 4:
        print(
            "Uso: python test_folder_ingestion.py folder <folder_path> <case_id> [doc_type] [recursive]"
        )
        print("\nEjemplo:")
        print("  python test_folder_ingestion.py folder /ruta/a/carpeta case-id-123 contrato true")
        return

    folder_path = Path(sys.argv[2])
    case_id = sys.argv[3]
    doc_type = sys.argv[4] if len(sys.argv) > 4 else None
    recursive = sys.argv[5].lower() == "true" if len(sys.argv) > 5 else True

    print("=" * 60)
    print("TEST: Ingesta de carpeta completa")
    print("=" * 60)
    print(f"Carpeta: {folder_path}")
    print(f"Case ID: {case_id}")
    print(f"Tipo: {doc_type or 'auto'}")
    print(f"Recursivo: {recursive}")
    print()

    db = next(get_db())

    try:
        stats = ingest_folder(
            db=db,
            folder_path=folder_path,
            case_id=case_id,
            doc_type=doc_type,
            source="test_script",
            recursive=recursive,
        )

        print()
        print("=" * 60)
        print("RESULTADOS")
        print("=" * 60)
        print(f"Total archivos encontrados: {stats['total_files']}")
        print(f"✅ Procesados: {stats['processed']}")
        print(f"⏭️  Omitidos (ya existían): {stats['skipped']}")
        print(f"❌ Errores: {stats['errors']}")
        print()

        if stats["documents"]:
            print("Documentos creados:")
            for doc in stats["documents"]:
                print(f"  - {doc.filename} ({doc.document_id})")

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python test_folder_ingestion.py <command> [args...]")
        print("\nComandos disponibles:")
        print("  file   - Ingesta un archivo individual")
        print("  folder - Ingesta una carpeta completa")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "file":
        test_ingest_file()
    elif command == "folder":
        test_ingest_folder()
    else:
        print(f"❌ Comando desconocido: {command}")
        print("Comandos disponibles: file, folder")
        sys.exit(1)
