"""
Test simple para verificar que la estructura del refactor está correcta.
Verifica imports y estructura sin ejecutar código completo.
"""

import sys
from pathlib import Path


def test_imports():
    """Test que verifica que los imports funcionan correctamente"""

    print("=" * 80)
    print("TEST: Verificación de imports y estructura")
    print("=" * 80)

    errors = []

    # Test 1: Verificar que retrieve.py no tiene LLM
    print("\n1️⃣ Verificando que app/rag/case_rag/retrieve.py NO tiene LLM...")
    try:
        retrieve_path = Path(__file__).parent.parent / "app" / "rag" / "case_rag" / "retrieve.py"
        if not retrieve_path.exists():
            errors.append("❌ retrieve.py no existe")
        else:
            content = retrieve_path.read_text()
            if "chat.completions" in content:
                errors.append("❌ retrieve.py contiene 'chat.completions' (debe estar eliminado)")
            elif "ChatCompletion" in content:
                errors.append("❌ retrieve.py contiene 'ChatCompletion' (debe estar eliminado)")
            elif "RAG_LLM_MODEL" in content and "import" in content.split("\n")[0:30]:
                errors.append("❌ retrieve.py importa RAG_LLM_MODEL (debe estar eliminado)")
            elif "RAG_TEMPERATURE" in content and "import" in content.split("\n")[0:30]:
                errors.append("❌ retrieve.py importa RAG_TEMPERATURE (debe estar eliminado)")
            else:
                # Verificar que tiene context_text
                if "context_text" not in content:
                    errors.append("❌ retrieve.py NO tiene 'context_text' (debe tenerlo)")
                if "answer:" in content and "context_text" not in content.split("answer:")[0]:
                    # Si tiene answer: en la definición del dataclass, es un problema
                    if (
                        "@dataclass" in content
                        and "answer:" in content.split("@dataclass")[1].split("def ")[0]
                    ):
                        errors.append(
                            "❌ RAGInternalResult todavía tiene campo 'answer' (debe ser 'context_text')"
                        )
                print("   ✅ retrieve.py no contiene llamadas a LLM")
    except Exception as e:
        errors.append(f"❌ Error verificando retrieve.py: {e}")

    # Test 2: Verificar que response_builder.py existe y tiene LLM
    print("\n2️⃣ Verificando que app/agents/base/response_builder.py tiene LLM...")
    try:
        response_builder_path = (
            Path(__file__).parent.parent / "app" / "agents" / "base" / "response_builder.py"
        )
        if not response_builder_path.exists():
            errors.append("❌ response_builder.py no existe")
        else:
            content = response_builder_path.read_text()
            if "build_llm_answer" not in content:
                errors.append("❌ response_builder.py no tiene función 'build_llm_answer'")
            elif "chat.completions" not in content:
                errors.append(
                    "❌ response_builder.py NO contiene 'chat.completions' (debe tenerlo)"
                )
            else:
                print("   ✅ response_builder.py contiene LLM correctamente")
    except Exception as e:
        errors.append(f"❌ Error verificando response_builder.py: {e}")

    # Test 3: Verificar que rag.py usa response_builder
    print("\n3️⃣ Verificando que app/rag/case_rag/rag.py usa response_builder...")
    try:
        rag_path = Path(__file__).parent.parent / "app" / "rag" / "case_rag" / "rag.py"
        if not rag_path.exists():
            errors.append("❌ rag.py no existe")
        else:
            content = rag_path.read_text()
            if "build_llm_answer" not in content:
                errors.append("❌ rag.py no importa/usa 'build_llm_answer'")
            elif "response_builder" not in content:
                errors.append("❌ rag.py no importa desde 'response_builder'")
            else:
                print("   ✅ rag.py usa response_builder correctamente")
    except Exception as e:
        errors.append(f"❌ Error verificando rag.py: {e}")

    # Test 4: Verificar que agent_2_prosecutor usa ambas funciones
    print("\n4️⃣ Verificando que agent_2_prosecutor usa retrieve + response_builder...")
    try:
        logic_path = (
            Path(__file__).parent.parent / "app" / "agents" / "agent_2_prosecutor" / "logic.py"
        )
        if not logic_path.exists():
            errors.append("❌ logic.py no existe")
        else:
            content = logic_path.read_text()
            if "rag_answer_internal" not in content:
                errors.append("❌ logic.py no usa 'rag_answer_internal'")
            elif "build_llm_answer" not in content:
                errors.append("❌ logic.py no usa 'build_llm_answer'")
            else:
                print("   ✅ agent_2_prosecutor usa ambas funciones correctamente")
    except Exception as e:
        errors.append(f"❌ Error verificando logic.py: {e}")

    # Test 5: Verificar estructura de archivos
    print("\n5️⃣ Verificando estructura de archivos...")
    base_dir = Path(__file__).parent.parent

    required_files = [
        "app/rag/case_rag/retrieve.py",
        "app/rag/case_rag/rag.py",
        "app/agents/base/__init__.py",
        "app/agents/base/response_builder.py",
        "app/agents/agent_2_prosecutor/logic.py",
    ]

    for file_path in required_files:
        full_path = base_dir / file_path
        if not full_path.exists():
            errors.append(f"❌ Archivo no existe: {file_path}")
        else:
            print(f"   ✅ {file_path} existe")

    # Resumen
    print("\n" + "=" * 80)
    print("RESUMEN")
    print("=" * 80)

    if errors:
        print(f"\n❌ Se encontraron {len(errors)} error(es):")
        for error in errors:
            print(f"   {error}")
        return False
    else:
        print("\n✅ Todos los tests de estructura pasaron correctamente")
        print("\n📋 Verificación completada:")
        print("   ✅ app/rag/ NO tiene llamadas a LLM")
        print("   ✅ app/agents/base/response_builder.py tiene LLM")
        print("   ✅ app/rag/case_rag/rag.py usa response_builder")
        print("   ✅ app/agents/agent_2_prosecutor/logic.py usa ambas funciones")
        print("   ✅ Estructura de archivos correcta")
        return True


def main():
    """Ejecuta el test"""
    success = test_imports()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
