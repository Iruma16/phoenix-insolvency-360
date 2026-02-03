"""
Nodo del grafo que ejecuta el Rule Engine Legal.

Conecta el rule engine existente (app/agents/agent_legal/rule_engine.py)
como un paso real del grafo de análisis.
"""
from app.agents.agent_legal.rule_engine import RuleEngine
from app.agents.agent_legal.rule_loader import load_default_rulebook
from app.graphs.state import AuditState


def apply_rule_engine(state: AuditState) -> AuditState:
    """
    Nodo: Aplicación del Rule Engine Legal.

    Ejecuta el motor de reglas legal sobre el estado actual del caso,
    generando findings basados en reglas deterministas del TRLC.

    Los resultados se añaden como 'rule_based_findings' sin sobrescribir
    los findings generados por heurísticas.
    """
    case_id = state.get("case_id", "UNKNOWN")

    print(f"📜 Ejecutando Rule Engine Legal para caso {case_id}...")

    try:
        # Cargar rulebook
        rulebook = load_default_rulebook()

        if not rulebook or not rulebook.rules:
            print("   ⚠️  No hay rulebook disponible, saltando rule engine")
            state["rule_based_findings"] = []
            return state

        # Construir variables del caso para el rule engine
        case_variables = _build_case_variables(state)

        # Inicializar y ejecutar rule engine
        engine = RuleEngine(rulebook, case_variables)

        # Evaluar reglas
        risks = engine.evaluate_rules(case_variables)

        # Extraer findings de las reglas
        rule_findings = []
        for risk in risks:
            rule_findings.append(
                {
                    "finding_type": risk.risk_type,
                    "severity": risk.severity,
                    "weight": 50,  # Peso por defecto
                    "explanation": risk.description,
                    "legal_basis": [{"article": art, "law": "TRLC"} for art in risk.legal_articles],
                    "evidence": [],
                    "counter_evidence": [],
                    "mitigation": risk.recommendation if hasattr(risk, "recommendation") else None,
                    "source": "rule_engine",
                }
            )

        state["rule_based_findings"] = rule_findings

        print(f"   ✅ Rule Engine: {len(rule_findings)} findings generados")

        # Log de las reglas aplicadas
        for finding in rule_findings[:3]:  # Mostrar primeros 3
            print(f"      - {finding['finding_type']}: {finding['severity']}")

    except FileNotFoundError:
        print("   ℹ️  Rulebook no encontrado, saltando rule engine")
        state["rule_based_findings"] = []

    except Exception as e:
        import traceback

        print(f"   ⚠️  Error en rule engine: {e}")
        print("   Traceback completo:")
        traceback.print_exc()
        state["rule_based_findings"] = []

    return state


def _build_case_variables(state: AuditState) -> dict:
    """
    Construye el diccionario de variables para el rule engine.

    Extrae información del estado y la estructura en el formato
    que espera el rule engine.
    """
    documents = state.get("documents", [])
    timeline = state.get("timeline", [])
    risks = state.get("risks", [])
    company_profile = state.get("company_profile", {})

    # Variables básicas
    variables = {
        "num_documentos": len(documents),
        "num_eventos": len(timeline),
        "num_riesgos_heuristicos": len(risks),
        "empresa_nombre": company_profile.get("name", "Desconocida"),
        "empresa_sector": company_profile.get("sector", "Desconocido"),
    }

    # Detectar tipos de documentos presentes (conversión defensiva a string)
    doc_types = set()
    for doc in documents:
        dt = doc.get("doc_type")
        if dt:
            doc_types.add(str(dt).lower())

    variables["tiene_balance"] = any("balance" in dt or "contabilidad" in dt for dt in doc_types)
    variables["tiene_acta"] = any("acta" in dt for dt in doc_types)
    variables["tiene_facturas"] = any("factura" in dt for dt in doc_types)
    variables["tiene_emails"] = any("email" in dt for dt in doc_types)

    # Detectar riesgos por tipo (conversión defensiva a string)
    risk_types = set()
    for risk in risks:
        rt = risk.get("risk_type")
        if rt:
            risk_types.add(str(rt).lower())

    variables["detectado_delay_filing"] = "delay_filing" in risk_types
    variables["detectado_inconsistencias"] = "document_inconsistency" in risk_types
    variables["detectado_gaps"] = "documentation_gap" in risk_types
    variables["detectado_accounting_flags"] = "accounting_red_flags" in risk_types

    # Severidades (conversión defensiva a string)
    severities = set()
    for risk in risks:
        sev = risk.get("severity")
        if sev:
            severities.add(str(sev).lower())

    variables["tiene_riesgo_alto"] = "high" in severities
    variables["tiene_riesgo_medio"] = "medium" in severities

    # Variables temporales (si se pueden extraer)
    # TODO: Mejorar extracción de fechas
    variables["dias_desde_declaracion"] = None  # Requiere parseo de fechas

    return variables
