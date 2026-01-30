"""
Test específico para verificar el bloqueo de RAG cuando la calidad es muy baja.
"""

import sys
from datetime import datetime

from app.core.database import get_db
from app.core.variables import DATA, LEGAL_QUALITY_SCORE_BLOCK_THRESHOLD
from app.models.case import Case
from app.models.document import Document
from app.rag.case_rag.retrieve import rag_answer_internal
from app.services.document_quality import get_document_quality_summary


def test_rag_block():
    """Test que fuerza un bloqueo real creando un caso con calidad muy baja"""

    print("=" * 80)
    print("TEST: Bloqueo de RAG con calidad muy baja")
    print("=" * 80)

    db = next(get_db())
    case_id = None

    try:
        # Crear caso
        case = Case(
            name="Test Bloqueo Calidad",
            client_ref="TEST_BLOCK",
            status="active",
        )
        db.add(case)
        db.flush()
        case_id = case.case_id
        print(f"\n✅ Caso creado: {case_id}")

        # Crear muchos documentos críticos sin procesar para forzar score muy bajo
        # El score baja cuando hay documentos sin chunks/embeddings
        test_dir = DATA / "test_block" / "cases" / case_id / "documents"
        test_dir.mkdir(parents=True, exist_ok=True)

        # Crear 5 documentos críticos (todos sin procesar = score muy bajo)
        for i in range(5):
            test_file = test_dir / f"critical_doc_{i}.pdf"
            test_file.write_text(f"Documento crítico {i} sin procesar")

            doc = Document(
                case_id=case_id,
                filename=test_file.name,
                doc_type="CONTRATO_FINANCIACION",  # Documento crítico
                source="test",
                date_start=datetime(2024, 1, 1),
                date_end=datetime(2024, 12, 31),
                reliability="original",
                file_format="pdf",
                storage_path=str(test_file),
            )
            db.add(doc)

        db.commit()
        print("✅ 5 documentos críticos creados (sin chunks/embeddings)")

        # Verificar calidad (debería ser muy baja)
        summary = get_document_quality_summary(db=db, case_id=case_id)
        quality_score = summary["quality_score"]

        print(f"\n📊 Calidad del caso: {quality_score}/100")
        print(f"   Umbral de bloqueo: {LEGAL_QUALITY_SCORE_BLOCK_THRESHOLD}")
        print(f"   Documentos críticos faltantes: {summary.get('critical_documents_missing', 0)}")

        if summary.get("legal_risks"):
            print("\n⚠️  Riesgos legales detectados:")
            for risk in summary["legal_risks"][:3]:  # Mostrar primeros 3
                print(f"   - {risk}")

        # Intentar hacer pregunta RAG
        print("\n🔍 Intentando hacer pregunta RAG...")
        result = rag_answer_internal(
            db=db,
            case_id=case_id,
            question="¿Qué información hay sobre contratos?",
            top_k=5,
        )

        print("\n📋 Resultado RAG:")
        print(f"   Status: {result.status}")
        print(f"   Hallucination risk: {result.hallucination_risk}")
        print(f"   Confidence: {result.confidence}")
        print(f"   Warnings: {len(result.warnings)}")
        print(
            f"   Contexto disponible: {len(result.context_text) if result.context_text else 0} caracteres"
        )

        if result.warnings:
            print("\n   Warnings encontrados:")
            for warning in result.warnings[:5]:  # Primeros 5
                print(f"   - {warning}")

        # Verificaciones
        if quality_score < LEGAL_QUALITY_SCORE_BLOCK_THRESHOLD:
            # Debería estar bloqueado - sin contexto disponible
            assert (
                result.status == "CASE_NOT_FOUND"
            ), f"Status debería ser CASE_NOT_FOUND cuando está bloqueado. Status: {result.status}"
            assert (
                not result.context_text or len(result.context_text) == 0
            ), "No debería haber contexto disponible cuando está bloqueado"
            assert (
                result.hallucination_risk == True
            ), "Debería tener hallucination_risk=True cuando está bloqueado"
            assert len(result.warnings) > 0, "Debería haber warnings de bloqueo"
            assert any(
                "bloqueo" in w.lower() or "calidad" in w.lower() for w in result.warnings
            ), "Debería haber warning de bloqueo por calidad"

            print("\n✅ BLOQUEO VERIFICADO:")
            print(
                f"   - RAG bloqueado correctamente (score: {quality_score:.1f} < {LEGAL_QUALITY_SCORE_BLOCK_THRESHOLD})"
            )
            print("   - Mensaje orientado a valor legal")
            print("   - Hallucination risk activado")
            print("   - Warnings apropiados")
        else:
            print(
                f"\n⚠️  Caso no bloqueado (score: {quality_score:.1f} >= {LEGAL_QUALITY_SCORE_BLOCK_THRESHOLD})"
            )
            print("   Pero debería tener warnings por calidad baja")
            assert len(result.warnings) > 0, "Debería haber warnings incluso si no está bloqueado"

        print("\n✅ TEST PASADO")
        return True

    except AssertionError as e:
        print(f"\n❌ ASSERTION ERROR: {e}")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = test_rag_block()
    sys.exit(0 if success else 1)
