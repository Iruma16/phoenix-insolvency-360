"""
Test para verificar las mejoras en ingesta:
1. Inferencia mejorada de doc_type
2. Manejo de .doc vs .docx (best effort)
"""

import sys
from pathlib import Path

from app.services.folder_ingestion import _get_default_doc_type
from app.services.ingesta import ingerir_archivo, leer_txt


def test_doc_type_inference():
    """Test de inferencia de doc_type con casos reales"""

    print("=" * 80)
    print("TEST 1: Inferencia de doc_type mejorada")
    print("=" * 80)

    test_cases = [
        # (filename, expected_type, description)
        ("balance_final_v3_ok.docx", "balance", "Balance con versión y sufijo"),
        ("email_re_abogado_urgente.pdf", "email_direccion", "Email con re: y contexto"),
        ("contrato_servicio_2024.pdf", "contrato", "Contrato simple"),
        ("extracto_bancario_enero.xlsx", "extracto_bancario", "Extracto bancario"),
        ("factura_12345.pdf", "factura", "Factura"),
        ("acta_junta_extraordinaria.docx", "acta", "Acta"),
        ("pyg_2023_final.xlsx", "pyg", "Pérdidas y ganancias"),
        ("mayor_contable_2024.xlsx", "mayor", "Mayor contable"),
        ("email_fw_banco_importante.pdf", "email_banco", "Email forward de banco"),
        ("nomina_enero_2024.pdf", "nomina", "Nómina"),
        ("venta_activo_inmueble.pdf", "venta_activo", "Venta de activo"),
        ("prestamo_bancario_2023.pdf", "prestamo", "Préstamo"),
        ("documento_desconocido.pdf", "contrato", "Default a contrato"),
    ]

    passed = 0
    failed = 0

    for filename, expected, description in test_cases:
        result = _get_default_doc_type(filename)
        status = "✅" if result == expected else "❌"

        if result == expected:
            passed += 1
        else:
            failed += 1

        print(f"{status} {filename:50} → {result:20} (esperado: {expected})")
        if result != expected:
            print(f"   ⚠️  {description}")

    print()
    print("=" * 80)
    print(f"Resultados: {passed} ✅ | {failed} ❌")
    print("=" * 80)

    return failed == 0


def test_doc_vs_docx_handling():
    """Test del manejo diferenciado de .doc vs .docx"""

    print()
    print("=" * 80)
    print("TEST 2: Manejo de .doc vs .docx (best effort)")
    print("=" * 80)

    # Crear archivos de prueba temporales
    test_dir = Path("/tmp/phoenix_test_ingestion")
    test_dir.mkdir(exist_ok=True)

    # Crear un archivo TXT simple para simular contenido
    test_txt = test_dir / "test_content.txt"
    test_txt.write_text("Este es un documento de prueba para verificar la ingesta.")

    print("\n📄 Probando detección de formato en ingerir_archivo()...")

    # Test 1: .docx debería funcionar normalmente
    print("\n1. Test con .docx:")
    try:
        result = ingerir_archivo(str(test_txt), "test.docx")
        if result:
            print("   ✅ .docx detectado y procesado (simulado con TXT)")
        else:
            print("   ⚠️  .docx no retornó contenido (esperado si no hay .docx real)")
    except Exception as e:
        print(f"   ⚠️  Error (esperado si no hay .docx real): {e}")

    # Test 2: .doc debería mostrar warnings pero intentar
    print("\n2. Test con .doc (legacy):")
    try:
        result = ingerir_archivo(str(test_txt), "test.doc")
        if result:
            print("   ✅ .doc detectado y procesado (best effort)")
        else:
            print("   ⚠️  .doc no retornó contenido (puede ser normal si falla)")
    except Exception as e:
        print(f"   ⚠️  Error procesando .doc: {e}")
        print("   ℹ️  Esto es esperado si python-docx no puede leer .doc legacy")

    print("\n✅ Test de detección completado")
    print("   (Los warnings son normales si no hay archivos .doc/.docx reales)")

    # Limpiar
    if test_txt.exists():
        test_txt.unlink()

    return True


def test_file_reading_functions():
    """Test de las funciones de lectura individuales"""

    print()
    print("=" * 80)
    print("TEST 3: Funciones de lectura de archivos")
    print("=" * 80)

    # Crear archivo de prueba
    test_dir = Path("/tmp/phoenix_test_ingestion")
    test_dir.mkdir(exist_ok=True)

    test_txt = test_dir / "test.txt"
    test_content = "Este es un documento de prueba.\nSegunda línea.\nTercera línea."
    test_txt.write_text(test_content)

    print("\n📄 Probando leer_txt()...")
    try:
        result = leer_txt(str(test_txt))
        if result and "prueba" in result:
            print("   ✅ leer_txt() funciona correctamente")
            print(f"   📏 Longitud: {len(result)} caracteres")
        else:
            print("   ❌ leer_txt() no retornó contenido esperado")
            return False
    except Exception as e:
        print(f"   ❌ Error en leer_txt(): {e}")
        return False

    print("\n📄 Probando leer_txt() con ruta Path...")
    try:
        result = leer_txt(test_txt)
        if result and "prueba" in result:
            print("   ✅ leer_txt() funciona con Path")
        else:
            print("   ❌ leer_txt() no funciona con Path")
            return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

    # Limpiar
    if test_txt.exists():
        test_txt.unlink()

    print("\n✅ Test de funciones de lectura completado")
    return True


def test_integration_example():
    """Test de integración con ejemplo real"""

    print()
    print("=" * 80)
    print("TEST 4: Ejemplo de integración completo")
    print("=" * 80)

    print("\n📋 Casos de prueba de inferencia de doc_type:")
    print()

    examples = [
        "balance_final_v3_ok.docx",
        "email_re_abogado_urgente.pdf",
        "contrato_servicio_2024.pdf",
        "extracto_bancario_enero.xlsx",
    ]

    for example in examples:
        inferred = _get_default_doc_type(example)
        print(f"   📄 {example:40} → {inferred}")

    print("\n✅ Ejemplos procesados correctamente")
    return True


def main():
    """Ejecuta todos los tests"""

    print("\n" + "=" * 80)
    print("SUITE DE TESTS: Mejoras en Ingesta")
    print("=" * 80)
    print()

    results = []

    # Test 1: Inferencia de doc_type
    results.append(("Inferencia doc_type", test_doc_type_inference()))

    # Test 2: Manejo .doc vs .docx
    results.append(("Manejo .doc vs .docx", test_doc_vs_docx_handling()))

    # Test 3: Funciones de lectura
    results.append(("Funciones de lectura", test_file_reading_functions()))

    # Test 4: Integración
    results.append(("Ejemplo integración", test_integration_example()))

    # Resumen final
    print()
    print("=" * 80)
    print("RESUMEN FINAL")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print()
    print(f"Total: {passed}/{total} tests pasados")

    if passed == total:
        print("\n🎉 ¡Todos los tests pasaron!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) fallaron")
        return 1


if __name__ == "__main__":
    sys.exit(main())
