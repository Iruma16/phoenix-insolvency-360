"""
Test para validar el nodo analyze_timeline del grafo de auditoría.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.graphs.audit_graph import build_audit_graph
from app.fixtures.audit_cases import CASE_RETAIL_001


def test_timeline_is_created():
    """Test que verifica que el timeline se crea en el grafo."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    assert "timeline" in result, "El resultado no contiene la clave 'timeline'"
    assert result["timeline"] is not None, "El timeline es None"


def test_timeline_is_not_empty():
    """Test que verifica que el timeline contiene eventos."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    assert len(result["timeline"]) > 0, "El timeline está vacío"


def test_timeline_events_have_required_keys():
    """Test que verifica que cada evento tiene las claves requeridas."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    for event in result["timeline"]:
        assert "date" in event, f"Evento sin clave 'date': {event}"
        assert "description" in event, f"Evento sin clave 'description': {event}"
        assert "source_doc_id" in event, f"Evento sin clave 'source_doc_id': {event}"


def test_timeline_events_are_ordered_by_date():
    """Test que verifica que los eventos están ordenados por fecha ascendente."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    timeline = result["timeline"]
    dates = [event["date"] for event in timeline]
    
    assert dates == sorted(dates), f"Las fechas no están ordenadas: {dates}"


def test_timeline_matches_document_count():
    """Test que verifica que el número de eventos coincide con los documentos con fecha."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    docs_with_date = [doc for doc in CASE_RETAIL_001["documents"] if doc.get("date")]
    timeline = result["timeline"]
    
    assert len(timeline) == len(docs_with_date), \
        f"Se esperaban {len(docs_with_date)} eventos, se obtuvieron {len(timeline)}"


def test_timeline_events_have_descriptions():
    """Test que verifica que cada evento tiene una descripción no vacía."""
    graph = build_audit_graph()
    result = graph.invoke(CASE_RETAIL_001)
    
    for event in result["timeline"]:
        assert event["description"], f"Evento sin descripción: {event}"
        assert len(event["description"]) > 0, f"Descripción vacía en evento: {event}"


if __name__ == "__main__":
    print("=" * 70)
    print("Test: Análisis de Timeline")
    print("=" * 70)
    
    try:
        print("\n1. Construyendo y ejecutando grafo...")
        graph = build_audit_graph()
        result = graph.invoke(CASE_RETAIL_001)
        print("   ✅ Grafo ejecutado exitosamente")
        
        print("\n2. Validando timeline...")
        assert "timeline" in result
        print(f"   ✅ Timeline existe")
        
        timeline = result["timeline"]
        assert len(timeline) > 0
        print(f"   ✅ Timeline contiene {len(timeline)} eventos")
        
        print("\n3. Eventos encontrados:")
        for i, event in enumerate(timeline, 1):
            print(f"   {i}. {event['date']}: {event['description']}")
            print(f"      (fuente: {event['source_doc_id']})")
        
        print("\n4. Validando estructura de eventos...")
        for event in timeline:
            assert "date" in event
            assert "description" in event
            assert "source_doc_id" in event
        print("   ✅ Todos los eventos tienen la estructura correcta")
        
        print("\n5. Validando orden cronológico...")
        dates = [event["date"] for event in timeline]
        assert dates == sorted(dates)
        print("   ✅ Eventos ordenados cronológicamente")
        
        print("\n" + "=" * 70)
        print("✅ TODOS LOS TESTS PASARON")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

