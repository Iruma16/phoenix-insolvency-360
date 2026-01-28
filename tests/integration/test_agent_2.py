#!/usr/bin/env python3
"""
Test del Agente 2: Prosecutor

Ejecuta el agente con un case_id de prueba para verificar que funciona.
"""

from app.agents.agent_2_prosecutor.runner import run_prosecutor


def test_agent_2():
    """Test básico del Agente Prosecutor"""

    # Usar un case_id que existe en los datos de prueba
    # Puedes cambiar este por uno que exista en tu base de datos
    test_case_id = "0fac46d4-f2cb-4257-9df1-e8aa34019a83"

    print(f"🧪 Probando Agente Prosecutor con case_id: {test_case_id}")
    print("=" * 60)

    try:
        result = run_prosecutor(case_id=test_case_id)

        print("✅ Agente ejecutado exitosamente")
        print("\n📊 Resultados:")
        print(f"  - Case ID: {result.case_id}")
        print(f"  - Nivel de riesgo global: {result.overall_risk_level}")
        print(f"  - Hallazgos críticos: {result.critical_findings_count}")
        print(f"  - Acusaciones detectadas: {len(result.accusations)}")
        print(f"  - Bloqueo recomendado: {result.blocking_recommendation}")

        print("\n📝 Resumen para abogado:")
        print(f"  {result.summary_for_lawyer}")

        if result.accusations:
            print("\n🔍 Acusaciones detectadas:")
            for i, acc in enumerate(result.accusations, 1):
                print(f"\n  {i}. {acc.title}")
                print(f"     - Base legal: {acc.legal_ground}")
                print(f"     - Nivel de riesgo: {acc.risk_level}")
                print(f"     - Probabilidad estimada: {acc.estimated_probability}")
                print(f"     - Evidencias: {len(acc.evidences)}")

        print("\n" + "=" * 60)
        print("✅ Test completado exitosamente")

        return True

    except Exception as e:
        print(f"❌ Error al ejecutar el agente: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    test_agent_2()
