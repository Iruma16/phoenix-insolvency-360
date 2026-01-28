"""
Test de completitud del corpus legal del TRLC.

Valida que el RAG legal contiene el texto consolidado COMPLETO
de la Ley Concursal (TRLC), con todos sus artículos, libros y disposiciones.
"""

import pytest

from app.core.variables import LEGAL_LEY_VECTORSTORE
from app.rag.legal_rag.service import _get_legal_collection, query_legal_rag

# Umbral mínimo para el TRLC completo
UMBRAL_MINIMO_CHUNKS_TRLC = 800

# Conceptos que deben aparecer en TODO el TRLC
CONCEPTOS_TRANSVERSALES = [
    "presupuesto objetivo del concurso",
    "masa activa",
    "masa pasiva",
    "créditos privilegiados",
    "convenio concursal",
    "liquidación",
    "calificación culpable",
    "exoneración del pasivo insatisfecho",
    "microempresas",
    "conclusión del concurso",
]

# Términos que indican diferentes libros/secciones del TRLC
INDICADORES_DIVERSIDAD = {
    "LIBRO PRIMERO": ["masa activa", "declaración de concurso"],
    "LIBRO SEGUNDO": ["calificación", "culpable", "fortuito"],
    "LIBRO TERCERO": ["exoneración", "pasivo insatisfecho"],
    "DISPOSICIONES": ["disposición adicional", "disposición transitoria"],
}


def test_legal_corpus_exists():
    """Verifica que el vectorstore legal existe."""
    print("\n[TEST] Verificando que el vectorstore legal existe...")

    assert (
        LEGAL_LEY_VECTORSTORE.exists()
    ), f"El vectorstore legal no existe en: {LEGAL_LEY_VECTORSTORE}"

    assert (
        LEGAL_LEY_VECTORSTORE.is_dir()
    ), f"El vectorstore legal debe ser un directorio: {LEGAL_LEY_VECTORSTORE}"

    print(f"   ✅ Vectorstore legal existe en: {LEGAL_LEY_VECTORSTORE}")


def test_legal_corpus_minimum_chunks():
    """Verifica que el corpus legal tiene suficientes chunks para el TRLC completo."""
    print(f"\n[TEST] Verificando cantidad de chunks (umbral: {UMBRAL_MINIMO_CHUNKS_TRLC})...")

    collection = _get_legal_collection(LEGAL_LEY_VECTORSTORE, "chunks")
    count = collection.count()

    print(f"   Chunks encontrados: {count}")

    assert (
        count >= UMBRAL_MINIMO_CHUNKS_TRLC
    ), f"Chunks insuficientes para TRLC completo: {count} < {UMBRAL_MINIMO_CHUNKS_TRLC}"

    print(f"   ✅ Corpus completo: {count} chunks (>= {UMBRAL_MINIMO_CHUNKS_TRLC})")


def test_legal_corpus_transversal_coverage():
    """Verifica que se pueden recuperar conceptos de todo el TRLC."""
    print("\n[TEST] Verificando cobertura transversal de conceptos...")

    failures = []

    for concepto in CONCEPTOS_TRANSVERSALES:
        try:
            results = query_legal_rag(
                query=concepto, top_k=3, include_ley=True, include_jurisprudencia=False
            )

            if len(results) == 0:
                failures.append(f"'{concepto}': 0 resultados")
                print(f"   ❌ '{concepto}': 0 resultados")
            else:
                print(f"   ✅ '{concepto}': {len(results)} resultados")
        except Exception as e:
            failures.append(f"'{concepto}': ERROR - {e}")
            print(f"   ❌ '{concepto}': ERROR - {e}")

    assert len(failures) == 0, "Fallos en cobertura transversal:\n" + "\n".join(failures)

    print("   ✅ Todos los conceptos transversales recuperables")


def test_legal_corpus_diversity():
    """Verifica diversidad de contenido en el corpus legal."""
    print("\n[TEST] Verificando diversidad de contenido (libros diferentes)...")

    collection = _get_legal_collection(LEGAL_LEY_VECTORSTORE, "chunks")
    sample = collection.get(limit=200, include=["documents"])

    libros_encontrados = {}

    for libro, terminos in INDICADORES_DIVERSIDAD.items():
        count = 0
        for doc in sample["documents"]:
            doc_lower = doc.lower()
            if any(term.lower() in doc_lower for term in terminos):
                count += 1

        libros_encontrados[libro] = count

        if count > 0:
            print(f"   ✅ {libro}: {count} chunks")
        else:
            print(f"   ⚠️  {libro}: 0 chunks")

    libros_con_contenido = sum(1 for count in libros_encontrados.values() if count > 0)

    assert libros_con_contenido >= 3, (
        f"Baja diversidad: solo {libros_con_contenido}/4 secciones detectadas. "
        f"Detalles: {libros_encontrados}"
    )

    print(f"   ✅ Diversidad adecuada: {libros_con_contenido}/4 secciones detectadas")


def test_legal_corpus_no_contamination():
    """Verifica que no hay contaminación con datos de casos."""
    print("\n[TEST] Verificando no contaminación con casos...")

    # Términos específicos de casos de prueba que NO deben aparecer
    forbidden_terms = [
        "contrato de prestamo mercantil",
        "50.000 eur",
        "acreedor sa",
        "deudor sl",
        "e2e_case_rag_test",
    ]

    collection = _get_legal_collection(LEGAL_LEY_VECTORSTORE, "chunks")
    sample = collection.get(limit=100, include=["documents"])

    contamination_found = []

    for doc in sample["documents"]:
        doc_lower = doc.lower()
        for term in forbidden_terms:
            if term in doc_lower:
                contamination_found.append(term)
                print(f"   ❌ Contaminación detectada: '{term}'")

    assert len(contamination_found) == 0, f"Contaminación detectada: {contamination_found}"

    print("   ✅ Sin contaminación detectada")


def test_legal_corpus_article_density():
    """Verifica que la densidad de artículos es alta (texto completo, no selección)."""
    print("\n[TEST] Verificando densidad de artículos...")

    collection = _get_legal_collection(LEGAL_LEY_VECTORSTORE, "chunks")
    sample = collection.get(limit=200, include=["documents"])

    chunks_with_articles = 0
    total_chunks = len(sample["documents"])

    for doc in sample["documents"]:
        # Buscar referencias a artículos
        if "artículo" in doc.lower() or "art." in doc.lower():
            chunks_with_articles += 1

    density = chunks_with_articles / total_chunks if total_chunks > 0 else 0

    print(f"   Chunks con artículos: {chunks_with_articles}/{total_chunks} ({density:.1%})")

    # Para el TRLC completo, esperamos alta densidad de artículos
    assert density >= 0.5, (
        f"Densidad de artículos muy baja ({density:.1%}). "
        f"Puede indicar corpus incompleto o con mucho contenido no legal."
    )

    print(f"   ✅ Densidad adecuada: {density:.1%}")


def test_legal_corpus_metadata_completeness():
    """Verifica que los metadatos de los chunks son completos."""
    print("\n[TEST] Verificando metadatos de chunks...")

    collection = _get_legal_collection(LEGAL_LEY_VECTORSTORE, "chunks")
    sample = collection.get(limit=50, include=["metadatas"])

    required_fields = ["law", "type", "chunk_id"]

    incomplete_chunks = []

    for i, metadata in enumerate(sample["metadatas"]):
        missing_fields = [field for field in required_fields if field not in metadata]
        if missing_fields:
            incomplete_chunks.append(f"Chunk {i}: falta {missing_fields}")

    assert len(incomplete_chunks) == 0, "Chunks con metadatos incompletos:\n" + "\n".join(
        incomplete_chunks
    )

    print("   ✅ Metadatos completos en todos los chunks verificados")


def test_legal_corpus_chunk_quality():
    """Verifica la calidad de los chunks (tamaño, contenido)."""
    print("\n[TEST] Verificando calidad de chunks...")

    collection = _get_legal_collection(LEGAL_LEY_VECTORSTORE, "chunks")
    sample = collection.get(limit=100, include=["documents"])

    too_short = 0
    too_long = 0
    empty = 0

    MIN_CHUNK_SIZE = 200
    MAX_CHUNK_SIZE = 5000

    for doc in sample["documents"]:
        length = len(doc)

        if length == 0:
            empty += 1
        elif length < MIN_CHUNK_SIZE:
            too_short += 1
        elif length > MAX_CHUNK_SIZE:
            too_long += 1

    print(f"   - Chunks vacíos: {empty}")
    print(f"   - Chunks muy cortos (<{MIN_CHUNK_SIZE}): {too_short}")
    print(f"   - Chunks muy largos (>{MAX_CHUNK_SIZE}): {too_long}")

    assert empty == 0, f"Se encontraron {empty} chunks vacíos"
    assert (
        too_short / len(sample["documents"]) < 0.1
    ), f"Demasiados chunks cortos: {too_short}/{len(sample['documents'])}"

    print("   ✅ Calidad de chunks adecuada")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
