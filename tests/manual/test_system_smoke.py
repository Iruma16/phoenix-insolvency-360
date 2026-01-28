"""
Smoke test de integración del sistema completo.

Este test verifica que:
- Auditor funciona
- Prosecutor funciona
- Generador de informes funciona
- No se crean archivos fuera de ubicaciones esperadas
"""
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Añadir raíz del proyecto al path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy.orm import Session
from app.core.database import get_session_factory
from app.agents.agent_1_auditor.runner import run_auditor
from app.agents.agent_2_prosecutor.runner import run_prosecutor_from_auditor
from app.agents.handoff import build_agent2_payload
from app.reports.report_generator import generate_case_report


def mock_openai_chat_completions(*args, **kwargs):
    """Mock para OpenAI chat completions."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = '{"summary": "Test summary", "risks": ["Test risk 1"], "next_actions": ["Test action 1"]}'
    return mock_response


def mock_openai_embeddings(*args, **kwargs):
    """Mock para OpenAI embeddings."""
    mock_response = MagicMock()
    mock_response.data = [MagicMock()]
    mock_response.data[0].embedding = [0.1] * 1536  # Dimensión típica de embeddings
    return mock_response


def test_system_smoke():
    """
    Smoke test de integración del sistema completo.
    """
    print("="*60)
    print("SMOKE TEST DEL SISTEMA")
    print("="*60)
    print()
    
    # Crear sesión de base de datos
    SessionLocal = get_session_factory()
    db = SessionLocal()
    
    case_id = "case_test"
    question = "Analiza los riesgos legales del caso"
    
    try:
        # Mockear OpenAI para evitar llamadas reales
        with patch('openai.OpenAI') as mock_openai_class:
            mock_client = MagicMock()
            mock_openai_class.return_value = mock_client
            
            # Configurar mocks
            mock_client.chat.completions.create = MagicMock(side_effect=mock_openai_chat_completions)
            mock_client.embeddings.create = MagicMock(side_effect=mock_openai_embeddings)
            
            # Mockear get_document_quality_summary primero para evitar consultas a BD
            with patch('app.services.document_quality.get_document_quality_summary') as mock_quality:
                mock_quality.return_value = {
                    "total_documents": 0,
                    "total_chunks": 0,
                    "avg_quality_score": 0,
                    "quality_summary": "Test quality summary"
                }
                
                # Mockear query_case_rag para devolver contexto simulado
                with patch('app.rag.case_rag.service.query_case_rag') as mock_rag:
                    mock_rag.return_value = "Contexto simulado para el test. Documentos relevantes del caso."
                    
                    # Mockear query_legal_rag si es necesario
                    with patch('app.rag.legal_rag.service.query_legal_rag') as mock_legal_rag:
                        mock_legal_rag.return_value = []
                        
                        print("1. Ejecutando Auditor...")
                        try:
                            auditor_result, auditor_fallback = run_auditor(
                                case_id=case_id,
                                question=question,
                                db=db,
                            )
                            print(f"   ✅ Auditor ejecutado correctamente")
                            print(f"   - Fallback: {auditor_fallback}")
                            print(f"   - Summary: {auditor_result.summary[:50]}...")
                            print(f"   - Risks: {len(auditor_result.risks)}")
                            print(f"   - Actions: {len(auditor_result.next_actions)}")
                        except Exception as e:
                            print(f"   ❌ Error en Auditor: {e}")
                            raise
                        
                        print()
                        print("2. Construyendo handoff...")
                        try:
                            handoff_payload = build_agent2_payload(
                                auditor_result=auditor_result,
                                case_id=case_id,
                                question=question,
                                auditor_fallback=auditor_fallback,
                            )
                            print(f"   ✅ Handoff construido correctamente")
                            print(f"   - Case ID: {handoff_payload.case_id}")
                        except Exception as e:
                            print(f"   ❌ Error construyendo handoff: {e}")
                            raise
                        
                        print()
                        print("3. Ejecutando Prosecutor...")
                        try:
                            prosecutor_result = run_prosecutor_from_auditor(
                                handoff_payload=handoff_payload.dict(),
                            )
                            print(f"   ✅ Prosecutor ejecutado correctamente")
                            print(f"   - Risk Level: {prosecutor_result.overall_risk_level}")
                            print(f"   - Accusations: {len(prosecutor_result.accusations)}")
                            print(f"   - Critical Findings: {prosecutor_result.critical_findings_count}")
                        except Exception as e:
                            print(f"   ❌ Error en Prosecutor: {e}")
                            raise
                        
                        print()
                        print("4. Generando informe...")
                        try:
                            # Limpiar informe previo si existe
                            reports_dir = Path("reports") / case_id
                            if reports_dir.exists():
                                import shutil
                                shutil.rmtree(reports_dir)
                                print(f"   Limpiado directorio previo: {reports_dir}")
                            
                            md_path = generate_case_report(
                                case_id=case_id,
                                db=db,
                            )
                            print(f"   ✅ Informe generado correctamente")
                            print(f"   - Path: {md_path}")
                            print(f"   - Existe: {md_path.exists()}")
                            
                            # Verificar que el PDF también se generó (si hay librerías)
                            pdf_path = md_path.with_suffix('.pdf')
                            if pdf_path.exists():
                                print(f"   - PDF generado: {pdf_path}")
                            else:
                                print(f"   - PDF no generado (puede requerir librerías)")
                        except Exception as e:
                            print(f"   ❌ Error generando informe: {e}")
                            raise
                        
                        print()
                        print("5. Verificando ubicaciones de archivos...")
                        root_path = Path(".")
                        
                        # Verificar que no hay archivos .db en la raíz
                        db_files_in_root = list(root_path.glob("*.db*"))
                        if db_files_in_root:
                            print(f"   ⚠️  Archivos .db en la raíz: {[f.name for f in db_files_in_root]}")
                        else:
                            print(f"   ✅ No hay archivos .db en la raíz")
                        
                        # Verificar que reports/ existe y tiene el caso
                        reports_dir = Path("reports") / case_id
                        if reports_dir.exists():
                            report_files = list(reports_dir.glob("*.md"))
                            print(f"   ✅ Reports generados en reports/{case_id}/")
                            print(f"   - Archivos: {[f.name for f in report_files]}")
                        else:
                            print(f"   ⚠️  No se encontró reports/{case_id}/")
                        
                        print()
                        print("="*60)
                        print("✅ SMOKE TEST COMPLETADO EXITOSAMENTE")
                        print("="*60)
        
    except Exception as e:
        print()
        print("="*60)
        print(f"❌ SMOKE TEST FALLÓ: {e}")
        print("="*60)
        import traceback
        traceback.print_exc()
        raise
    
    finally:
        db.close()
        # Limpiar artefactos generados
        print()
        print("Limpiando artefactos de test...")
        reports_dir = Path("reports") / case_id
        if reports_dir.exists():
            import shutil
            shutil.rmtree(reports_dir)
            print(f"   ✅ Eliminado: {reports_dir}")


if __name__ == "__main__":
    test_system_smoke()
