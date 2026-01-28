"""
Test para validar el fixture CASE_RETAIL_001.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.fixtures.audit_cases import CASE_RETAIL_001


def test_case_retail_001_import():
    """Test que verifica que el fixture CASE_RETAIL_001 se puede importar correctamente."""
    assert CASE_RETAIL_001 is not None, "CASE_RETAIL_001 no se pudo importar"


def test_case_retail_001_case_id():
    """Test que verifica que el case_id es correcto."""
    assert CASE_RETAIL_001["case_id"] == "CASE_RETAIL_001", f"case_id esperado: CASE_RETAIL_001, obtenido: {CASE_RETAIL_001['case_id']}"


def test_case_retail_001_documents_count():
    """Test que verifica que el número de documentos es 4."""
    num_docs = len(CASE_RETAIL_001["documents"])
    assert num_docs == 4, f"Número de documentos esperado: 4, obtenido: {num_docs}"


if __name__ == "__main__":
    print("=" * 60)
    print("Verificación del fixture CASE_RETAIL_001")
    print("=" * 60)
    
    try:
        from app.fixtures.audit_cases import CASE_RETAIL_001
        print(f"✅ Importación exitosa")
        print(f"Case ID: {CASE_RETAIL_001['case_id']}")
        print(f"Número de documentos: {len(CASE_RETAIL_001['documents'])}")
        print("=" * 60)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

