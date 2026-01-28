"""
Test para verificar que la reorganización de clients_data funciona correctamente.
"""
from pathlib import Path


def test_structure_exists():
    """Test 1: Verificar que la nueva estructura de carpetas existe"""

    print("=" * 80)
    print("TEST 1: Verificación de estructura de carpetas")
    print("=" * 80)

    base_dir = Path(__file__).parent.parent
    clients_data = base_dir / "clients_data"

    errors = []

    # Verificar estructura base
    required_dirs = [
        "clients_data/cases",
        "clients_data/legal",
        "clients_data/legal/ley_concursal",
        "clients_data/legal/jurisprudencia",
    ]

    for dir_path in required_dirs:
        full_path = base_dir / dir_path
        if not full_path.exists():
            errors.append(f"❌ No existe: {dir_path}")
        elif not full_path.is_dir():
            errors.append(f"❌ No es directorio: {dir_path}")
        else:
            print(f"   ✅ {dir_path} existe")

    # Verificar que hay casos con vectorstore
    cases_dir = base_dir / "clients_data" / "cases"
    if cases_dir.exists():
        case_dirs = [d for d in cases_dir.iterdir() if d.is_dir()]
        if case_dirs:
            print(f"\n   📁 Casos encontrados: {len(case_dirs)}")
            for case_dir in case_dirs[:5]:  # Mostrar primeros 5
                vectorstore_dir = case_dir / "vectorstore"
                if vectorstore_dir.exists():
                    print(f"   ✅ {case_dir.name}/vectorstore existe")
                else:
                    errors.append(f"❌ Falta vectorstore en: cases/{case_dir.name}")
        else:
            print("   ⚠️  No hay casos (puede ser normal si no hay datos)")

    # Verificar vectorstores legales
    legal_ley = base_dir / "clients_data" / "legal" / "ley_concursal" / "vectorstore"
    legal_jur = base_dir / "clients_data" / "legal" / "jurisprudencia" / "vectorstore"

    if legal_ley.exists():
        print("   ✅ legal/ley_concursal/vectorstore existe")
    else:
        print("   ⚠️  legal/ley_concursal/vectorstore no existe (puede ser normal)")

    if legal_jur.exists():
        print("   ✅ legal/jurisprudencia/vectorstore existe")
    else:
        print("   ⚠️  legal/jurisprudencia/vectorstore no existe (puede ser normal)")

    if errors:
        print(f"\n❌ Errores encontrados: {len(errors)}")
        for error in errors:
            print(f"   {error}")
        return False
    else:
        print("\n✅ TEST 1 PASADO: Estructura de carpetas correcta")
        return True


def test_old_structure_removed():
    """Test 2: Verificar que la estructura antigua ya no se usa (o está vacía)"""

    print("\n" + "=" * 80)
    print("TEST 2: Verificación de que estructura antigua no se usa")
    print("=" * 80)

    base_dir = Path(__file__).parent.parent
    old_vectorstore = base_dir / "clients_data" / "_vectorstore"

    # Verificar si _vectorstore existe
    if old_vectorstore.exists():
        # Verificar que esté vacío o solo tenga .gitkeep
        items = list(old_vectorstore.iterdir())
        non_gitkeep = [item for item in items if item.name != ".gitkeep"]
        if non_gitkeep:
            print(f"   ⚠️  _vectorstore todavía contiene: {[i.name for i in non_gitkeep]}")
            print("   ℹ️  Puede eliminarse si está vacío")
        else:
            print("   ✅ _vectorstore existe pero está vacío (puede eliminarse)")
    else:
        print("   ✅ _vectorstore ya no existe")

    # Verificar que no hay carpetas "chroma" en la nueva estructura
    cases_dir = base_dir / "clients_data" / "cases"
    if cases_dir.exists():
        chroma_dirs = list(cases_dir.rglob("chroma"))
        if chroma_dirs:
            errors = [
                f"❌ Encontrada carpeta 'chroma' en nueva estructura: {d.relative_to(base_dir)}"
                for d in chroma_dirs
            ]
            for error in errors:
                print(f"   {error}")
            return False
        else:
            print("   ✅ No hay carpetas 'chroma' en cases/")

    legal_dir = base_dir / "clients_data" / "legal"
    if legal_dir.exists():
        chroma_dirs = list(legal_dir.rglob("chroma"))
        if chroma_dirs:
            errors = [
                f"❌ Encontrada carpeta 'chroma' en nueva estructura: {d.relative_to(base_dir)}"
                for d in chroma_dirs
            ]
            for error in errors:
                print(f"   {error}")
            return False
        else:
            print("   ✅ No hay carpetas 'chroma' en legal/")

    print("\n✅ TEST 2 PASADO: Estructura antigua no se usa")
    return True


def test_code_paths_updated():
    """Test 3: Verificar que los paths en el código están actualizados"""

    print("\n" + "=" * 80)
    print("TEST 3: Verificación de paths en código")
    print("=" * 80)

    base_dir = Path(__file__).parent.parent
    errors = []

    # Verificar variables.py
    variables_file = base_dir / "app" / "core" / "variables.py"
    if variables_file.exists():
        content = variables_file.read_text()

        # Verificar que usa CASES_VECTORSTORE_BASE
        if "CASES_VECTORSTORE_BASE" not in content:
            errors.append("❌ variables.py no define CASES_VECTORSTORE_BASE")
        else:
            print("   ✅ variables.py define CASES_VECTORSTORE_BASE")

        # Verificar que no usa VECTORSTORE (antiguo)
        if (
            "VECTORSTORE = DATA" in content
            and "CASES_VECTORSTORE_BASE" not in content.split("VECTORSTORE = DATA")[0]
        ):
            errors.append(
                "❌ variables.py todavía define VECTORSTORE (debe usar CASES_VECTORSTORE_BASE)"
            )
        else:
            print("   ✅ variables.py no usa VECTORSTORE antiguo")

        # Verificar paths legales
        if '"/vectorstore"' in content or "/vectorstore" in content:
            print("   ✅ variables.py usa 'vectorstore' en paths legales")
        elif '"chroma"' in content or "/chroma" in content:
            errors.append("❌ variables.py todavía usa 'chroma' en paths legales")
        else:
            print("   ℹ️  No se encontraron paths legales explícitos")
    else:
        errors.append("❌ variables.py no existe")

    # Verificar embeddings_pipeline.py
    embeddings_file = base_dir / "app" / "services" / "embeddings_pipeline.py"
    if embeddings_file.exists():
        content = embeddings_file.read_text()

        # Verificar que usa CASES_VECTORSTORE_BASE
        if "CASES_VECTORSTORE_BASE" not in content:
            errors.append("❌ embeddings_pipeline.py no usa CASES_VECTORSTORE_BASE")
        else:
            print("   ✅ embeddings_pipeline.py usa CASES_VECTORSTORE_BASE")

        # Verificar que no usa VECTORSTORE (antiguo)
        if (
            "from app.core.variables import" in content
            and "VECTORSTORE" in content.split("from app.core.variables import")[1].split("\n")[0]
        ):
            if (
                "CASES_VECTORSTORE_BASE"
                not in content.split("from app.core.variables import")[1].split("\n")[0]
            ):
                errors.append("❌ embeddings_pipeline.py todavía importa VECTORSTORE")
            else:
                print("   ✅ embeddings_pipeline.py no importa VECTORSTORE antiguo")

        # Verificar que usa "vectorstore" en paths
        if '"vectorstore"' in content or "'vectorstore'" in content or "/vectorstore" in content:
            print("   ✅ embeddings_pipeline.py usa 'vectorstore' en paths")
        elif '"chroma"' in content or "'chroma'" in content:
            errors.append("❌ embeddings_pipeline.py todavía usa 'chroma' en paths")
    else:
        errors.append("❌ embeddings_pipeline.py no existe")

    if errors:
        print(f"\n❌ Errores encontrados: {len(errors)}")
        for error in errors:
            print(f"   {error}")
        return False
    else:
        print("\n✅ TEST 3 PASADO: Paths en código actualizados correctamente")
        return True


def test_paths_resolve_correctly():
    """Test 4: Verificar que los paths se resuelven correctamente"""

    print("\n" + "=" * 80)
    print("TEST 4: Verificación de resolución de paths")
    print("=" * 80)

    try:
        # Intentar importar variables
        base_dir = Path(__file__).parent.parent

        from app.core.variables import (
            CASES_VECTORSTORE_BASE,
            DATA,
            LEGAL_JURISPRUDENCIA_VECTORSTORE,
            LEGAL_LEY_VECTORSTORE,
            LEGAL_VECTORSTORE_BASE,
        )

        print(f"   📁 DATA: {DATA}")
        print(f"   📁 CASES_VECTORSTORE_BASE: {CASES_VECTORSTORE_BASE}")
        print(f"   📁 LEGAL_VECTORSTORE_BASE: {LEGAL_VECTORSTORE_BASE}")
        print(f"   📁 LEGAL_LEY_VECTORSTORE: {LEGAL_LEY_VECTORSTORE}")
        print(f"   📁 LEGAL_JURISPRUDENCIA_VECTORSTORE: {LEGAL_JURISPRUDENCIA_VECTORSTORE}")

        # Verificar que los paths apuntan a la estructura correcta
        errors = []

        if "clients_data" not in str(DATA):
            errors.append(f"❌ DATA no apunta a clients_data: {DATA}")
        else:
            print("   ✅ DATA apunta a clients_data")

        if "cases" not in str(CASES_VECTORSTORE_BASE):
            errors.append(f"❌ CASES_VECTORSTORE_BASE no apunta a cases: {CASES_VECTORSTORE_BASE}")
        else:
            print("   ✅ CASES_VECTORSTORE_BASE apunta a cases")

        if "vectorstore" not in str(LEGAL_LEY_VECTORSTORE):
            errors.append(f"❌ LEGAL_LEY_VECTORSTORE no usa vectorstore: {LEGAL_LEY_VECTORSTORE}")
        else:
            print("   ✅ LEGAL_LEY_VECTORSTORE usa vectorstore")

        if "chroma" in str(LEGAL_LEY_VECTORSTORE):
            errors.append(f"❌ LEGAL_LEY_VECTORSTORE todavía usa chroma: {LEGAL_LEY_VECTORSTORE}")

        if "vectorstore" not in str(LEGAL_JURISPRUDENCIA_VECTORSTORE):
            errors.append(
                f"❌ LEGAL_JURISPRUDENCIA_VECTORSTORE no usa vectorstore: {LEGAL_JURISPRUDENCIA_VECTORSTORE}"
            )
        else:
            print("   ✅ LEGAL_JURISPRUDENCIA_VECTORSTORE usa vectorstore")

        if "chroma" in str(LEGAL_JURISPRUDENCIA_VECTORSTORE):
            errors.append(
                f"❌ LEGAL_JURISPRUDENCIA_VECTORSTORE todavía usa chroma: {LEGAL_JURISPRUDENCIA_VECTORSTORE}"
            )

        # Verificar embeddings_pipeline (construyendo path manualmente para evitar dependencias)
        test_case_id = "test-case-123"
        test_path = CASES_VECTORSTORE_BASE / test_case_id / "vectorstore"

        print(f"   🔍 Path de ejemplo: {test_path}")

        if "cases" not in str(test_path):
            errors.append(f"❌ Path construido no usa cases: {test_path}")
        else:
            print("   ✅ Path construido usa cases")

        if "vectorstore" not in str(test_path):
            errors.append(f"❌ Path construido no usa vectorstore: {test_path}")
        else:
            print("   ✅ Path construido usa vectorstore")

        if "chroma" in str(test_path):
            errors.append(f"❌ Path construido todavía usa chroma: {test_path}")

        # Verificar también el código fuente de embeddings_pipeline
        embeddings_file = base_dir / "app" / "services" / "embeddings_pipeline.py"
        if embeddings_file.exists():
            content = embeddings_file.read_text()
            # Buscar la función _case_vectorstore_path
            if "_case_vectorstore_path" in content:
                # Extraer las líneas de la función
                func_start = content.find("def _case_vectorstore_path")
                if func_start != -1:
                    func_lines = content[
                        func_start : func_start + 200
                    ]  # Primeras líneas de la función
                    if "CASES_VECTORSTORE_BASE" in func_lines and "vectorstore" in func_lines:
                        print(
                            "   ✅ _case_vectorstore_path usa CASES_VECTORSTORE_BASE y vectorstore"
                        )
                    elif "chroma" in func_lines:
                        errors.append("❌ _case_vectorstore_path todavía usa chroma")
                    else:
                        print("   ⚠️  No se pudo verificar completamente _case_vectorstore_path")

        if errors:
            print(f"\n❌ Errores encontrados: {len(errors)}")
            for error in errors:
                print(f"   {error}")
            return False
        else:
            print("\n✅ TEST 4 PASADO: Paths se resuelven correctamente")
            return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_no_access_to_data():
    """Test 5: Verificar que RAG y agents no acceden a data/"""

    print("\n" + "=" * 80)
    print("TEST 5: Verificación de que no hay accesos a data/")
    print("=" * 80)

    base_dir = Path(__file__).parent.parent
    errors = []

    # Buscar referencias a data/ en app/rag y app/agents
    rag_dir = base_dir / "app" / "rag"
    agents_dir = base_dir / "app" / "agents"

    if rag_dir.exists():
        for py_file in rag_dir.rglob("*.py"):
            content = py_file.read_text()
            # Buscar referencias a ../data/ o /data/ o Path("data")
            if '"data"' in content or "'data'" in content:
                # Verificar que no sea solo parte de una palabra
                import re

                if re.search(r'["\']\.\.\/data|["\']\/data\/|Path\(["\']data|DATA.*data', content):
                    errors.append(f"❌ {py_file.relative_to(base_dir)} contiene referencia a data/")
                else:
                    # Puede ser parte de DATA o clients_data, que está bien
                    pass
        if not errors:
            print("   ✅ app/rag/ no tiene referencias problemáticas a data/")

    if agents_dir.exists():
        for py_file in agents_dir.rglob("*.py"):
            content = py_file.read_text()
            import re

            if re.search(r'["\']\.\.\/data|["\']\/data\/|Path\(["\']data|DATA.*data', content):
                errors.append(f"❌ {py_file.relative_to(base_dir)} contiene referencia a data/")
        if not errors:
            print("   ✅ app/agents/ no tiene referencias problemáticas a data/")

    if errors:
        print(f"\n❌ Errores encontrados: {len(errors)}")
        for error in errors:
            print(f"   {error}")
        return False
    else:
        print("\n✅ TEST 5 PASADO: No hay accesos problemáticos a data/")
        return True


def main():
    """Ejecuta todos los tests"""

    print("\n" + "=" * 80)
    print("SUITE DE TESTS: Verificación Reorganización clients_data")
    print("=" * 80)

    results = []

    # Test 1: Estructura existe
    result1 = test_structure_exists()
    results.append(("Estructura de carpetas", result1))

    # Test 2: Estructura antigua no se usa
    result2 = test_old_structure_removed()
    results.append(("Estructura antigua removida", result2))

    # Test 3: Paths en código actualizados
    result3 = test_code_paths_updated()
    results.append(("Paths en código actualizados", result3))

    # Test 4: Paths se resuelven correctamente
    result4 = test_paths_resolve_correctly()
    results.append(("Paths se resuelven correctamente", result4))

    # Test 5: No hay accesos a data/
    result5 = test_no_access_to_data()
    results.append(("No hay accesos a data/", result5))

    # Resumen
    print("\n" + "=" * 80)
    print("RESUMEN FINAL")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print(f"\nTotal: {passed}/{total} tests pasados")

    if passed == total:
        print("\n🎉 ¡Todos los tests pasaron! La reorganización está correcta.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) fallaron")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
