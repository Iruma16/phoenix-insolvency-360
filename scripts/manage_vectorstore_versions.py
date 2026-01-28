#!/usr/bin/env python3
"""
Script CLI para gestión manual de versiones del vectorstore.

Comandos disponibles:
- list: Listar todas las versiones de un caso
- info: Ver información detallada de una versión
- activate: Activar una versión específica
- cleanup: Limpiar versiones antiguas
- validate: Validar integridad de una versión
- rebuild: Reconstruir embeddings para un caso
"""

import sys
from pathlib import Path

# Agregar el directorio raíz al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import json
from datetime import datetime

from app.core.database import SessionLocal
from app.services.vectorstore_versioning import (
    list_versions,
    get_active_version,
    update_active_pointer,
    cleanup_old_versions,
    read_manifest,
    read_status,
    validate_version_integrity,
)
from app.services.embeddings_pipeline import (
    build_embeddings_for_case,
    get_case_collection,
)


def cmd_list(args):
    """Lista todas las versiones de un caso."""
    case_id = args.case_id
    
    print("=" * 80)
    print(f"VERSIONES DEL VECTORSTORE - case_id: {case_id}")
    print("=" * 80)
    
    # Obtener versión activa
    active_version = get_active_version(case_id)
    if active_version:
        print(f"\n✅ Versión ACTIVE: {active_version}\n")
    else:
        print(f"\n⚠️  No existe versión ACTIVE\n")
    
    # Listar todas las versiones
    versions = list_versions(case_id)
    
    if not versions:
        print("No se encontraron versiones.")
        return
    
    print(f"Total versiones: {len(versions)}\n")
    print(f"{'VERSION':<25} {'STATUS':<12} {'CREATED AT':<25} {'ACTIVE':<8}")
    print("-" * 80)
    
    for v in versions:
        is_active = "✅" if v.version == active_version else ""
        created_str = v.created_at.strftime("%Y-%m-%d %H:%M:%S")
        status_icon = {
            "READY": "✅",
            "BUILDING": "🔨",
            "FAILED": "❌",
        }.get(v.status, "❓")
        
        print(f"{v.version:<25} {status_icon} {v.status:<9} {created_str:<25} {is_active:<8}")
    
    print()


def cmd_info(args):
    """Muestra información detallada de una versión."""
    case_id = args.case_id
    version = args.version
    
    print("=" * 80)
    print(f"INFORMACIÓN DE VERSIÓN")
    print("=" * 80)
    print(f"case_id: {case_id}")
    print(f"version: {version}")
    print()
    
    # Leer status
    try:
        status = read_status(case_id, version)
        print("STATUS:")
        print(json.dumps(status, indent=2, ensure_ascii=False))
        print()
    except Exception as e:
        print(f"❌ Error leyendo status: {e}\n")
        return
    
    # Leer manifest
    try:
        manifest = read_manifest(case_id, version)
        print("MANIFEST:")
        print(f"  Embedding model: {manifest['embedding_model']}")
        print(f"  Embedding dim: {manifest['embedding_dim']}")
        print(f"  Total chunks: {manifest['total_chunks']}")
        print(f"  Documentos: {len(manifest['documents'])}")
        print(f"  Creado: {manifest['created_at']}")
        print()
        
        if args.verbose:
            print("DOCUMENTOS:")
            for doc in manifest['documents']:
                print(f"  - {doc['filename']}")
                print(f"    doc_id: {doc['doc_id']}")
                print(f"    SHA256: {doc['sha256']}")
                print(f"    Chunks: {doc['num_chunks']}")
            print()
    except Exception as e:
        print(f"❌ Error leyendo manifest: {e}\n")


def cmd_activate(args):
    """Activa una versión específica."""
    case_id = args.case_id
    version = args.version
    
    print("=" * 80)
    print(f"ACTIVANDO VERSIÓN")
    print("=" * 80)
    print(f"case_id: {case_id}")
    print(f"version: {version}")
    print()
    
    try:
        # Verificar que la versión está READY
        status = read_status(case_id, version)
        if status["status"] != "READY":
            print(f"❌ ERROR: La versión tiene status={status['status']}")
            print("Solo se pueden activar versiones con status=READY")
            return
        
        # Activar
        update_active_pointer(case_id, version)
        print(f"✅ Versión {version} activada correctamente")
        
    except Exception as e:
        print(f"❌ Error activando versión: {e}")


def cmd_cleanup(args):
    """Limpia versiones antiguas."""
    case_id = args.case_id
    keep = args.keep
    
    print("=" * 80)
    print(f"LIMPIEZA DE VERSIONES ANTIGUAS")
    print("=" * 80)
    print(f"case_id: {case_id}")
    print(f"Mantener últimas: {keep}")
    print()
    
    if not args.yes:
        response = input("¿Continuar? (s/N): ")
        if response.lower() not in ["s", "si", "sí", "yes", "y"]:
            print("Operación cancelada.")
            return
    
    try:
        deleted_count = cleanup_old_versions(case_id, keep_last=keep)
        print(f"\n✅ Limpieza completada: {deleted_count} versiones eliminadas")
    except Exception as e:
        print(f"❌ Error en limpieza: {e}")


def cmd_validate(args):
    """Valida la integridad de una versión."""
    case_id = args.case_id
    version = args.version
    
    print("=" * 80)
    print(f"VALIDACIÓN DE INTEGRIDAD")
    print("=" * 80)
    print(f"case_id: {case_id}")
    print(f"version: {version}")
    print()
    
    try:
        # Obtener colección
        collection = get_case_collection(case_id, version=version)
        
        # Validar
        is_valid, errors = validate_version_integrity(case_id, version, collection)
        
        if is_valid:
            print("✅ Versión VÁLIDA - Todas las validaciones pasaron correctamente")
        else:
            print("❌ Versión INVÁLIDA - Se encontraron los siguientes errores:")
            for error in errors:
                print(f"  - {error}")
        
    except Exception as e:
        print(f"❌ Error en validación: {e}")


def cmd_rebuild(args):
    """Reconstruye los embeddings para un caso."""
    case_id = args.case_id
    
    print("=" * 80)
    print(f"RECONSTRUIR EMBEDDINGS")
    print("=" * 80)
    print(f"case_id: {case_id}")
    print()
    
    if not args.yes:
        print("⚠️  ADVERTENCIA: Esto creará una nueva versión del vectorstore.")
        print("La versión ACTIVE se actualizará si la nueva versión es válida.")
        print()
        response = input("¿Continuar? (s/N): ")
        if response.lower() not in ["s", "si", "sí", "yes", "y"]:
            print("Operación cancelada.")
            return
    
    try:
        db = SessionLocal()
        try:
            version_id = build_embeddings_for_case(db=db, case_id=case_id)
            print(f"\n✅ Embeddings reconstruidos exitosamente")
            print(f"Nueva versión: {version_id}")
        finally:
            db.close()
    except Exception as e:
        print(f"❌ Error reconstruyendo embeddings: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(
        description="Gestión de versiones del vectorstore de casos"
    )
    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")
    
    # Comando: list
    parser_list = subparsers.add_parser("list", help="Listar versiones")
    parser_list.add_argument("case_id", help="ID del caso")
    
    # Comando: info
    parser_info = subparsers.add_parser("info", help="Info de una versión")
    parser_info.add_argument("case_id", help="ID del caso")
    parser_info.add_argument("version", help="ID de la versión")
    parser_info.add_argument("-v", "--verbose", action="store_true", help="Mostrar info detallada")
    
    # Comando: activate
    parser_activate = subparsers.add_parser("activate", help="Activar una versión")
    parser_activate.add_argument("case_id", help="ID del caso")
    parser_activate.add_argument("version", help="ID de la versión")
    
    # Comando: cleanup
    parser_cleanup = subparsers.add_parser("cleanup", help="Limpiar versiones antiguas")
    parser_cleanup.add_argument("case_id", help="ID del caso")
    parser_cleanup.add_argument("--keep", type=int, default=3, help="Versiones a mantener (default: 3)")
    parser_cleanup.add_argument("-y", "--yes", action="store_true", help="No pedir confirmación")
    
    # Comando: validate
    parser_validate = subparsers.add_parser("validate", help="Validar integridad")
    parser_validate.add_argument("case_id", help="ID del caso")
    parser_validate.add_argument("version", help="ID de la versión")
    
    # Comando: rebuild
    parser_rebuild = subparsers.add_parser("rebuild", help="Reconstruir embeddings")
    parser_rebuild.add_argument("case_id", help="ID del caso")
    parser_rebuild.add_argument("-y", "--yes", action="store_true", help="No pedir confirmación")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Ejecutar comando
    commands = {
        "list": cmd_list,
        "info": cmd_info,
        "activate": cmd_activate,
        "cleanup": cmd_cleanup,
        "validate": cmd_validate,
        "rebuild": cmd_rebuild,
    }
    
    commands[args.command](args)


if __name__ == "__main__":
    main()

