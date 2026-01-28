"""
Script para generar informe completo de un caso mediante el grafo de auditoría.

Ejecuta el flujo completo:
- Análisis de documentos
- Timeline
- Detección de riesgos
- Hardening legal
- Mapeo de artículos
- Generación de PDF

Uso:
    python scripts/generate_case_report.py <case_id>
"""
import sys
from pathlib import Path

# Añadir el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.graphs.audit_graph import build_audit_graph
from app.fixtures.audit_cases import CASE_RETAIL_001, CASE_RETAIL_002, CASE_RETAIL_003

# Construir el grafo
graph = build_audit_graph()


def load_case_from_filesystem(case_id: str):
    """
    Carga un caso desde el sistema de archivos.
    
    Para casos sintéticos, construye el estado inicial básico.
    """
    from app.core.variables import DATA
    
    case_dir = DATA / "cases" / case_id
    
    if not case_dir.exists():
        raise FileNotFoundError(f"El caso {case_id} no existe en {case_dir}")
    
    docs_dir = case_dir / "documents"
    
    if not docs_dir.exists():
        raise FileNotFoundError(f"No hay documentos para el caso {case_id} en {docs_dir}")
    
    # Leer documentos del sistema de archivos
    documents = []
    
    for doc_file in docs_dir.glob("*.txt"):
        with open(doc_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Inferir doc_type del nombre del archivo
        filename = doc_file.name.lower()
        if "factura" in filename:
            doc_type = "factura"
        elif "email" in filename or "correo" in filename:
            doc_type = "email"
        elif "contable" in filename or "balance" in filename:
            doc_type = "contabilidad"
        elif "descripcion" in filename or "empresa" in filename:
            doc_type = "descripcion"
        elif "nota" in filename:
            doc_type = "nota_interna"
        else:
            doc_type = "documento"
        
        documents.append({
            "doc_id": doc_file.stem,
            "doc_type": doc_type,
            "content": content,
            "date": "2024-12-01",  # Fecha por defecto
            "filename": doc_file.name,
        })
    
    # Construir estado inicial
    initial_state = {
        "case_id": case_id,
        "company_profile": {
            "name": "Empresa Sintética",
            "sector": "Servicios",
            "size": "microempresa",
        },
        "documents": documents,
        "timeline": [],
        "risks": [],
        "legal_findings": [],
        "missing_documents": [],
        "notes": None,
        "report": None,
    }
    
    return initial_state


def generate_case_report(case_id: str):
    """
    Genera el informe completo para un caso.
    
    Args:
        case_id: ID del caso a analizar
    
    Returns:
        Resultado del análisis con ruta del PDF
    """
    print("="*80)
    print(f"GENERACIÓN DE INFORME - CASO: {case_id}")
    print("="*80)
    
    # Casos pre-definidos
    predefined_cases = {
        "CASE_RETAIL_001": CASE_RETAIL_001,
        "CASE_RETAIL_002": CASE_RETAIL_002,
        "CASE_RETAIL_003": CASE_RETAIL_003,
    }
    
    # Cargar caso
    if case_id in predefined_cases:
        print(f"\n📋 Cargando caso pre-definido: {case_id}")
        initial_state = predefined_cases[case_id]
    else:
        print(f"\n📋 Cargando caso desde sistema de archivos: {case_id}")
        initial_state = load_case_from_filesystem(case_id)
    
    print(f"   - Documentos: {len(initial_state['documents'])}")
    
    # Ejecutar grafo
    print(f"\n🔄 Ejecutando análisis completo...")
    result = graph.invoke(initial_state)
    
    # Extraer información del resultado
    print(f"\n📊 RESULTADOS DEL ANÁLISIS:")
    print(f"   - Timeline: {len(result.get('timeline', []))} eventos")
    print(f"   - Riesgos: {len(result.get('risks', []))} identificados")
    print(f"   - Legal findings: {len(result.get('legal_findings', []))} hallazgos")
    
    report = result.get('report', {})
    if report:
        print(f"   - Riesgo global: {report.get('overall_risk', 'N/A')}")
        pdf_path = report.get('pdf_path')
        if pdf_path:
            print(f"\n✅ PDF GENERADO: {pdf_path}")
        else:
            print(f"\n⚠️  No se generó PDF")
    
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/generate_case_report.py <case_id>")
        print("\nEjemplos:")
        print("  python scripts/generate_case_report.py CASE_RETAIL_001")
        print("  python scripts/generate_case_report.py case_sintetico_microempresa_libro_iii")
        sys.exit(1)
    
    case_id = sys.argv[1]
    
    try:
        result = generate_case_report(case_id)
        
        # Mostrar ruta del PDF
        pdf_path = result.get('report', {}).get('pdf_path')
        if pdf_path:
            print("\n" + "="*80)
            print("INFORME COMPLETADO")
            print("="*80)
            print(f"\n📄 Abrir PDF con:")
            print(f"   open {pdf_path}")
            print(f"\n   o navegar a:")
            print(f"   {pdf_path}")
        
        sys.exit(0)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

