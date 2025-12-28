"""
Smoke test ligero para el flujo completo Auditor → Handoff → Prosecutor.

Mockea RAG y BD para evitar dependencias pesadas.
"""
from unittest.mock import patch, MagicMock

from app.agents.agent_1_auditor.runner import run_auditor
from app.agents.agent_1_auditor.schema import AuditorResult
from app.agents.handoff import build_agent2_payload
from app.agents.agent_2_prosecutor.runner import run_prosecutor_from_auditor
import json


def test_handoff_flow():
    """Test básico que verifica el flujo completo Auditor → Handoff → Prosecutor."""
    print("🧪 Ejecutando smoke test del flujo Auditor → Handoff → Prosecutor...")
    
    # Mock de la sesión de BD
    mock_db = MagicMock()
    
    # Mock del RAG para devolver contexto simulado
    with patch('app.agents.agent_1_auditor.runner.query_case_rag') as mock_rag:
        mock_rag.return_value = "Este es un contexto simulado recuperado del RAG. Contiene información sobre documentos del caso."
        
        # PASO 1: Ejecutar Agente 1 (Auditor)
        print("\n📋 PASO 1: Ejecutando Agente 1 (Auditor)...")
        auditor_result, auditor_fallback = run_auditor(
            case_id="test-case-123",
            question="¿Hay riesgos legales detectables?",
            db=mock_db,
        )
        
        assert isinstance(auditor_result, AuditorResult)
        assert isinstance(auditor_fallback, bool)
        print(f"✅ Agente 1 completado: summary ({len(auditor_result.summary)} chars), fallback={auditor_fallback}")
        
        # PASO 2: Construir payload del handoff
        print("\n📋 PASO 2: Construyendo payload del handoff...")
        handoff_payload = build_agent2_payload(
            auditor_result=auditor_result,
            case_id="test-case-123",
            question="¿Hay riesgos legales detectables?",
            auditor_fallback=auditor_fallback,
        )
        
        # Validar estructura del payload
        required_keys = ["case_id", "question", "summary", "risks", "next_actions"]
        for key in required_keys:
            assert key in handoff_payload, f"Falta clave requerida: {key}"
        print(f"✅ Handoff payload construido: {list(handoff_payload.keys())}")
        
        # PASO 3: Ejecutar Agente 2 (Prosecutor) desde handoff
        print("\n📋 PASO 3: Ejecutando Agente 2 (Prosecutor) desde handoff...")
        
        # Mock del Prosecutor para evitar RAG pesado
        with patch('app.agents.agent_2_prosecutor.runner.ejecutar_analisis_prosecutor') as mock_prosecutor:
            from app.agents.agent_2_prosecutor.schema import ProsecutorResult, RiskLevel
            
            # Crear resultado simulado
            mock_result = ProsecutorResult(
                case_id="test-case-123",
                overall_risk_level="medio",
                accusations=[],
                critical_findings_count=0,
                summary_for_lawyer="Análisis completado",
                blocking_recommendation=False,
            )
            mock_prosecutor.return_value = mock_result
            
            prosecutor_result = run_prosecutor_from_auditor(handoff_payload)
            
            assert prosecutor_result.case_id == "test-case-123"
            print(f"✅ Agente 2 completado: risk_level = {prosecutor_result.overall_risk_level}")
            
            # Verificar que se llamó con el case_id correcto
            mock_prosecutor.assert_called_once()
            call_kwargs = mock_prosecutor.call_args.kwargs
            assert call_kwargs["case_id"] == "test-case-123"
        
        print("\n" + "="*80)
        print("✅ FLUJO COMPLETO VALIDADO")
        print("="*80)
        print("✅ Agente 1 → Handoff → Agente 2 conectado correctamente")
        print("✅ Payload del handoff tiene estructura correcta")
        print("✅ Agente 2 puede ejecutarse desde el handoff")
        print("\n✅ Smoke test completado")


if __name__ == "__main__":
    try:
        test_handoff_flow()
    except ImportError as e:
        print(f"⚠️  Error de importación (puede necesitar pytest): {e}")
        print("Ejecuta con: python -m pytest tests/manual/test_handoff_flow.py -v")
    except Exception as e:
        print(f"❌ Error durante el test: {e}")
        import traceback
        traceback.print_exc()

