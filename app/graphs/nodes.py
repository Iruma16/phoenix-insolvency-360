from __future__ import annotations

from app.graphs.state import AuditState
from app.legal.legal_mapping import LEGAL_MAP


def ingest_documents(state: AuditState) -> AuditState:
    """
    Nodo: Ingesta / preparación de documentos.
    """
    return state


def analyze_timeline(state: AuditState) -> AuditState:
    """
    Nodo: Análisis temporal (Digger).
    Extrae eventos temporales de los documentos y los ordena cronológicamente.
    """
    from datetime import datetime
    
    events = []
    documents = state.get("documents", [])
    
    for doc in documents:
        doc_id = doc.get("doc_id")
        doc_type = doc.get("doc_type", "")
        content = doc.get("content", "")
        date = doc.get("date")
        
        if not date:
            continue
        
        description = _generate_event_description(doc_type, content)
        
        if description:
            events.append({
                "date": date,
                "description": description,
                "source_doc_id": doc_id
            })
    
    events_sorted = sorted(events, key=lambda e: e["date"])
    
    state["timeline"] = events_sorted
    return state


def _generate_event_description(doc_type: str, content: str) -> str:
    """
    Genera una descripción de evento basada en el tipo de documento y su contenido.
    """
    doc_type_lower = doc_type.lower()
    content_lower = content.lower()
    
    if "balance" in doc_type_lower or "pyg" in doc_type_lower:
        if "pérdida" in content_lower or "perdida" in content_lower:
            return "Inicio de pérdidas detectado"
        return "Presentación de estados contables"
    
    elif "acta" in doc_type_lower or "junta" in doc_type_lower:
        if "deterioro" in content_lower or "reestructuración" in content_lower:
            return "Decisión societaria relevante (deterioro reconocido)"
        return "Decisión societaria"
    
    elif "email" in doc_type_lower or "proveedor" in doc_type_lower:
        if "negoci" in content_lower or "plazo" in content_lower:
            return "Negociación con proveedores"
        return "Comunicación con proveedores"
    
    elif "tesoreria" in doc_type_lower or "tesorería" in doc_type_lower:
        if "insolvencia" in content_lower:
            return "Constatación de insolvencia"
        return "Informe de tesorería"
    
    return "Evento documentado"


def detect_risks(state: AuditState) -> AuditState:
    """
    Nodo: Detección de riesgos (Prosecutor).
    Analiza documentos y timeline para detectar riesgos concursales mediante heurísticas.
    """
    documents = state.get("documents", [])
    timeline = state.get("timeline", [])
    
    risks = []
    
    risks.append(_detect_delay_filing(documents, timeline))
    risks.append(_detect_document_inconsistency(documents))
    risks.append(_detect_documentation_gap(documents))
    risks.append(_detect_accounting_red_flags(documents))
    
    state["risks"] = risks
    
    return state


def _detect_delay_filing(documents: list, timeline: list) -> dict:
    """
    Detecta retraso en la solicitud de concurso.
    """
    has_insolvency_mention = False
    insolvency_date = None
    has_filing_mention = False
    has_unresolved_negotiations = False
    has_severe_delay_indicators = False
    evidence = []
    distress_docs = []
    
    for doc in documents:
        content_lower = doc.get("content", "").lower()
        doc_id = doc.get("doc_id")
        
        if "insolvencia" in content_lower:
            has_insolvency_mention = True
            if not insolvency_date:
                insolvency_date = doc.get("date")
            evidence.append(doc_id)
            
            if any(phrase in content_lower for phrase in ["insolvencia grave", "desde al menos", "imposibilidad de atender"]):
                has_severe_delay_indicators = True
        
        if any(phrase in content_lower for phrase in ["no se alcanza acuerdo", "no se cierra", "sin acuerdo", "patrimonio neto negativo", "no alcanza"]):
            has_unresolved_negotiations = True
            distress_docs.append(doc_id)
        
        if doc.get("doc_type", "").lower() in ["emails_proveedores", "emails_banco"]:
            if any(phrase in content_lower for phrase in ["no se alcanza", "no se cierra", "sin acuerdo", "no se cierra operación", "amenaza", "acciones legales"]):
                has_unresolved_negotiations = True
                if doc_id not in distress_docs:
                    distress_docs.append(doc_id)
    
    for doc in documents:
        content_lower = doc.get("content", "").lower()
        if "solicitud" in content_lower or "concurso" in content_lower:
            has_filing_mention = True
    
    if not has_insolvency_mention:
        return {
            "risk_type": "delay_filing",
            "severity": "indeterminate",
            "explanation": "No se puede determinar si hay retraso sin evidencia clara de insolvencia.",
            "evidence": []
        }
    
    if has_insolvency_mention and has_severe_delay_indicators and not has_filing_mention:
        all_evidence = list(set(evidence + distress_docs))
        return {
            "risk_type": "delay_filing",
            "severity": "high",
            "explanation": "Se detecta insolvencia grave prolongada sin presentación del concurso. Riesgo elevado de responsabilidad.",
            "evidence": all_evidence
        }
    
    if has_insolvency_mention and has_unresolved_negotiations and not has_filing_mention:
        all_evidence = list(set(evidence + distress_docs))
        return {
            "risk_type": "delay_filing",
            "severity": "medium",
            "explanation": "Se detecta insolvencia actual con indicios previos de dificultades financieras sin presentación de concurso.",
            "evidence": all_evidence
        }
    
    if has_insolvency_mention and not has_filing_mention:
        return {
            "risk_type": "delay_filing",
            "severity": "low",
            "explanation": "Se detecta insolvencia pero no hay mención explícita de solicitud en documentos.",
            "evidence": evidence
        }
    
    return {
        "risk_type": "delay_filing",
        "severity": "low",
        "explanation": "No se detectan indicios claros de retraso significativo en la solicitud.",
        "evidence": evidence
    }


def _detect_document_inconsistency(documents: list) -> dict:
    """
    Detecta inconsistencias entre documentos.
    """
    has_losses = False
    has_severe_losses = False
    has_viability_claim = False
    has_strong_viability_claim = False
    loss_docs = []
    viability_docs = []
    
    for doc in documents:
        content_lower = doc.get("content", "").lower()
        doc_id = doc.get("doc_id")
        
        if "pérdida" in content_lower or "perdida" in content_lower:
            has_losses = True
            loss_docs.append(doc_id)
            
            if any(phrase in content_lower for phrase in ["pérdidas severas", "pérdidas acumuladas", "patrimonio neto negativo", "fondos propios inexistentes"]):
                has_severe_losses = True
        
        if any(word in content_lower for word in ["controlada", "viable", "viabilidad", "recuperación"]):
            has_viability_claim = True
            viability_docs.append(doc_id)
            
            if any(phrase in content_lower for phrase in ["empresa es viable", "rechaza propuesta de disolución"]):
                has_strong_viability_claim = True
    
    if has_severe_losses and has_strong_viability_claim:
        return {
            "risk_type": "document_inconsistency",
            "severity": "high",
            "explanation": "Contradicción grave: pérdidas severas y patrimonio negativo vs declaración de viabilidad empresarial.",
            "evidence": list(set(loss_docs + viability_docs))
        }
    
    if has_losses and has_viability_claim:
        return {
            "risk_type": "document_inconsistency",
            "severity": "medium",
            "explanation": "Se detectan pérdidas en documentos contables pero referencias a viabilidad en actas.",
            "evidence": loss_docs + viability_docs
        }
    
    for doc in documents:
        content_lower = doc.get("content", "").lower()
        if "contradicción" in content_lower or "inconsistencia" in content_lower:
            return {
                "risk_type": "document_inconsistency",
                "severity": "high",
                "explanation": "Se detectan contradicciones explícitas en la documentación.",
                "evidence": [doc.get("doc_id")]
            }
    
    return {
        "risk_type": "document_inconsistency",
        "severity": "low",
        "explanation": "No se detectan inconsistencias significativas entre documentos.",
        "evidence": []
    }


def _detect_documentation_gap(documents: list) -> dict:
    """
    Detecta lagunas documentales críticas.
    """
    doc_types_present = set(doc.get("doc_type", "") for doc in documents)
    
    critical_doc_types = {
        "balance_pyg": "Estados contables",
        "acta_junta": "Actas de junta",
        "informe_tesoreria": "Informes de tesorería"
    }
    
    missing = []
    for doc_type, name in critical_doc_types.items():
        if doc_type not in doc_types_present:
            missing.append(name)
    
    has_deposit_issues = False
    for doc in documents:
        content_lower = doc.get("content", "").lower()
        if any(phrase in content_lower for phrase in ["no se han depositado cuentas", "no consta contabilidad", "no depositado"]):
            has_deposit_issues = True
    
    if len(missing) >= 2:
        return {
            "risk_type": "documentation_gap",
            "severity": "high",
            "explanation": f"Faltan tipos documentales críticos: {', '.join(missing)}.",
            "evidence": []
        }
    
    if has_deposit_issues:
        return {
            "risk_type": "documentation_gap",
            "severity": "high",
            "explanation": "Grave deficiencia documental: cuentas no depositadas o contabilidad no ordenada.",
            "evidence": []
        }
    
    if len(missing) == 1:
        return {
            "risk_type": "documentation_gap",
            "severity": "medium",
            "explanation": f"Falta documentación crítica: {missing[0]}.",
            "evidence": []
        }
    
    if len(documents) < 3:
        return {
            "risk_type": "documentation_gap",
            "severity": "medium",
            "explanation": "Documentación muy limitada para análisis completo.",
            "evidence": []
        }
    
    return {
        "risk_type": "documentation_gap",
        "severity": "low",
        "explanation": "La documentación aportada cubre los tipos documentales críticos.",
        "evidence": []
    }


def _detect_accounting_red_flags(documents: list) -> dict:
    """
    Detecta señales de alerta en la contabilidad.
    """
    red_flag_keywords = [
        "no consta",
        "doble contabilidad",
        "sin depositar",
        "irregularidades",
        "no depositada",
        "contabilidad irregular",
        "ocultación",
        "manipulación"
    ]
    
    flagged_docs = []
    flags_found = []
    
    for doc in documents:
        content_lower = doc.get("content", "").lower()
        doc_id = doc.get("doc_id")
        
        for keyword in red_flag_keywords:
            if keyword in content_lower:
                flagged_docs.append(doc_id)
                flags_found.append(keyword)
                break
    
    if flagged_docs:
        return {
            "risk_type": "accounting_red_flags",
            "severity": "high",
            "explanation": f"Se detectan señales de alerta contable: {', '.join(set(flags_found))}.",
            "evidence": flagged_docs
        }
    
    for doc in documents:
        content_lower = doc.get("content", "").lower()
        doc_type = doc.get("doc_type", "")
        
        if "balance" in doc_type.lower():
            if "pérdida" in content_lower and "progresiva" in content_lower:
                return {
                    "risk_type": "accounting_red_flags",
                    "severity": "low",
                    "explanation": "Se detectan pérdidas progresivas, lo que requiere monitoreo.",
                    "evidence": [doc.get("doc_id")]
                }
    
    return {
        "risk_type": "accounting_red_flags",
        "severity": "low",
        "explanation": "No se detectan señales de alerta contable significativas.",
        "evidence": []
    }


def legal_article_mapper(state: AuditState) -> AuditState:
    """
    Nodo: Mapeo de artículos legales (Legal Article Mapper).
    Vincula los legal_findings con artículos concretos de la Ley Concursal
    y clasifica el tipo de riesgo jurídico de forma declarativa.
    """
    legal_findings = state.get("legal_findings", [])
    
    enriched_findings = []
    for finding in legal_findings:
        finding_type = finding.get("finding_type")
        
        mapping = LEGAL_MAP.get(finding_type)
        
        if mapping:
            legal_basis = mapping.get("articles", [])
            risk_classification = mapping.get("risk_types", [])
        else:
            legal_basis = []
            risk_classification = []
        
        enriched_finding = {
            **finding,
            "legal_basis": legal_basis,
            "risk_classification": risk_classification
        }
        enriched_findings.append(enriched_finding)
    
    state["legal_findings"] = enriched_findings
    return state


def build_report(state: AuditState) -> AuditState:
    """
    Nodo: Construcción de salida (Shield / Report).
    Genera un reporte estructurado con análisis de riesgos y recomendaciones.
    """
    case_id = state.get("case_id", "UNKNOWN")
    company_profile = state.get("company_profile", {})
    timeline = state.get("timeline", [])
    risks = state.get("risks", [])
    legal_findings = state.get("legal_findings", [])
    
    overall_risk = _calculate_overall_risk(risks, legal_findings)
    timeline_summary = _build_timeline_summary(timeline)
    risk_summary = _build_risk_summary(risks)
    next_steps = _generate_next_steps(overall_risk)
    
    report = {
        "case_id": case_id,
        "overall_risk": overall_risk,
        "timeline_summary": timeline_summary,
        "risk_summary": risk_summary,
        "legal_findings": legal_findings,
        "next_steps": next_steps
    }
    
    state["report"] = report
    
    # Generar PDF del informe
    try:
        from app.reports.pdf_report import generate_report_for_case
        pdf_path = generate_report_for_case(state["case_id"], state)
        report["pdf_path"] = pdf_path
        print(f"✅ Informe PDF generado: {pdf_path}")
    except Exception as e:
        print(f"⚠️  Error generando PDF: {e}")
        import traceback
        traceback.print_exc()
        report["pdf_path"] = None
    
    return state


def _calculate_overall_risk(risks: list, legal_findings: list = None) -> str:
    """
    Calcula el riesgo global basado en la severidad de los riesgos individuales y legal findings.
    Los legal findings tienen precedencia por su peso.
    """
    if legal_findings is None:
        legal_findings = []
    
    if not risks and not legal_findings:
        return "indeterminate"
    
    finding_severities = [finding.get("severity") for finding in legal_findings if finding.get("severity")]
    
    if any(s == "high" for s in finding_severities):
        return "high"
    
    severities = [risk.get("severity", "indeterminate") for risk in risks]
    
    if "high" in severities:
        return "high"
    elif any(s == "medium" for s in finding_severities) or "medium" in severities:
        return "medium"
    elif any(s == "low" for s in severities) or any(s == "low" for s in finding_severities):
        return "low"
    else:
        return "indeterminate"


def _build_timeline_summary(timeline: list) -> str:
    """
    Construye un resumen breve del timeline.
    """
    if not timeline:
        return "No se pudo construir timeline por falta de documentación fechada."
    
    num_events = len(timeline)
    first_date = timeline[0].get("date", "fecha desconocida") if timeline else "fecha desconocida"
    last_date = timeline[-1].get("date", "fecha desconocida") if timeline else "fecha desconocida"
    
    summary_parts = [
        f"Timeline de {num_events} eventos desde {first_date} hasta {last_date}."
    ]
    
    key_events = []
    for event in timeline:
        desc = event.get("description", "")
        if any(keyword in desc.lower() for keyword in ["insolvencia", "pérdida", "deterioro", "negociación"]):
            key_events.append(desc)
    
    if key_events:
        summary_parts.append(f"Eventos clave: {'; '.join(key_events[:3])}.")
    
    return " ".join(summary_parts)


def _build_risk_summary(risks: list) -> list:
    """
    Construye un resumen de los riesgos detectados.
    """
    risk_summary = []
    
    for risk in risks:
        risk_summary.append({
            "risk_type": risk.get("risk_type", "unknown"),
            "severity": risk.get("severity", "indeterminate"),
            "explanation": risk.get("explanation", "Sin explicación disponible")
        })
    
    return risk_summary


def _generate_next_steps(overall_risk: str) -> list:
    """
    Genera recomendaciones basadas en el riesgo global.
    """
    if overall_risk == "low":
        return [
            "Mantener documentación actualizada",
            "Preparar presentación del concurso con soporte documental"
        ]
    elif overall_risk == "medium":
        return [
            "Revisar incoherencias documentales",
            "Completar documentación crítica antes de presentar"
        ]
    elif overall_risk == "high":
        return [
            "No presentar concurso sin revisión jurídica exhaustiva",
            "Analizar posibles riesgos de responsabilidad personal"
        ]
    else:
        return [
            "Completar documentación para análisis definitivo",
            "Solicitar asesoramiento legal especializado"
        ]


def legal_hardening(state: AuditState) -> AuditState:
    """
    Nodo: Hardening jurídico (Legal Hardening).
    Analiza los riesgos detectados y genera findings legales con precedencia y resolución de conflictos.
    """
    risks = state.get("risks", [])
    documents = state.get("documents", [])
    timeline = state.get("timeline", [])
    
    legal_findings = []
    
    for risk in risks:
        risk_type = risk.get("risk_type")
        severity = risk.get("severity")
        evidence = risk.get("evidence", [])
        
        if risk_type == "accounting_red_flags" and severity == "high":
            finding = _build_accounting_irregularities_finding(risk, documents, evidence)
            legal_findings.append(finding)
        
        elif risk_type == "delay_filing":
            finding = _build_delay_filing_finding(risk, documents, evidence)
            legal_findings.append(finding)
        
        elif risk_type == "documentation_gap":
            finding = _build_documentation_gap_finding(risk, documents, evidence)
            legal_findings.append(finding)
        
        elif risk_type == "document_inconsistency":
            finding = _build_document_inconsistency_finding(risk, documents, evidence)
            legal_findings.append(finding)
    
    state["legal_findings"] = legal_findings
    return state


def _build_accounting_irregularities_finding(risk: dict, documents: list, evidence: list) -> dict:
    """
    Construye un finding de irregularidades contables con alta precedencia.
    """
    mitigation = []
    counter_evidence = []
    
    for doc in documents:
        content_lower = doc.get("content", "").lower()
        if "auditoría externa" in content_lower or "informe pericial" in content_lower:
            counter_evidence.append(doc.get("doc_id"))
            mitigation.append("Existe auditoría o informe pericial que puede validar la contabilidad")
    
    return {
        "finding_type": "accounting_irregularities",
        "severity": "high",
        "weight": 100,
        "explanation": risk.get("explanation", "Irregularidades contables detectadas"),
        "evidence": evidence,
        "counter_evidence": counter_evidence,
        "mitigation": mitigation if mitigation else ["Solicitar auditoría externa independiente"]
    }


def _build_delay_filing_finding(risk: dict, documents: list, evidence: list) -> dict:
    """
    Construye un finding de retraso en presentación con ajuste por negociaciones.
    """
    severity = risk.get("severity")
    counter_evidence = []
    mitigation = []
    
    has_negotiation = False
    for doc in documents:
        doc_type = doc.get("doc_type", "").lower()
        content_lower = doc.get("content", "").lower()
        
        if doc_type in ["emails_proveedores", "emails_banco"]:
            if any(keyword in content_lower for keyword in ["negociación", "acuerdo en proceso", "propuesta de pago", "plan de pagos"]):
                has_negotiation = True
                counter_evidence.append(doc.get("doc_id"))
    
    if has_negotiation and severity in ["medium", "high"]:
        mitigation.append("Existen evidencias de negociaciones activas con acreedores")
        mitigation.append("Documentar formalmente el estado de las negociaciones")
    else:
        mitigation.append("Presentar solicitud de concurso sin mayor dilación")
        mitigation.append("Documentar fecha exacta en que se conoció la insolvencia")
    
    weight = 80 if severity == "high" else 50 if severity == "medium" else 30
    
    return {
        "finding_type": "delay_filing",
        "severity": severity,
        "weight": weight,
        "explanation": risk.get("explanation", "Posible retraso en presentación de concurso"),
        "evidence": evidence,
        "counter_evidence": counter_evidence,
        "mitigation": mitigation
    }


def _build_documentation_gap_finding(risk: dict, documents: list, evidence: list) -> dict:
    """
    Construye un finding de laguna documental con validación estricta.
    """
    severity = risk.get("severity")
    required_doc_types = {"balance_pyg", "acta_junta", "informe_tesoreria"}
    present_doc_types = {doc.get("doc_type") for doc in documents if doc.get("doc_type")}
    missing = required_doc_types - present_doc_types
    
    has_serious_gap_phrase = False
    for doc in documents:
        content_lower = doc.get("content", "").lower()
        if "no consta" in content_lower or "no depositadas" in content_lower or "no se han depositado" in content_lower:
            has_serious_gap_phrase = True
            break
    
    adjusted_severity = severity
    if len(missing) >= 2 or has_serious_gap_phrase:
        adjusted_severity = "high"
    elif len(missing) == 1:
        adjusted_severity = "medium"
    else:
        adjusted_severity = "low"
    
    mitigation = []
    if missing:
        mitigation.append(f"Obtener documentos faltantes: {', '.join(missing)}")
    if has_serious_gap_phrase:
        mitigation.append("Regularizar situación registral y contable antes de presentación")
    else:
        mitigation.append("Mantener documentación completa y ordenada")
    
    weight = 70 if adjusted_severity == "high" else 40 if adjusted_severity == "medium" else 20
    
    return {
        "finding_type": "documentation_gap",
        "severity": adjusted_severity,
        "weight": weight,
        "explanation": risk.get("explanation", "Laguna documental detectada"),
        "evidence": evidence,
        "counter_evidence": [],
        "mitigation": mitigation
    }


def _build_document_inconsistency_finding(risk: dict, documents: list, evidence: list) -> dict:
    """
    Construye un finding de inconsistencia documental con ajuste por contradicciones graves.
    """
    severity = risk.get("severity")
    
    has_negative_equity = False
    has_viability_claim = False
    
    for doc in documents:
        content_lower = doc.get("content", "").lower()
        doc_type = doc.get("doc_type", "").lower()
        
        if "balance" in doc_type:
            if "patrimonio neto negativo" in content_lower or "fondos propios inexistentes" in content_lower:
                has_negative_equity = True
        
        if "acta" in doc_type:
            if "viable" in content_lower or "situación controlada" in content_lower:
                has_viability_claim = True
    
    adjusted_severity = severity
    if has_negative_equity and has_viability_claim:
        adjusted_severity = "high"
    
    mitigation = []
    if adjusted_severity == "high":
        mitigation.append("Aclarar contradicciones mediante informe pericial independiente")
        mitigation.append("Documentar razones que justifiquen las aparentes contradicciones")
    else:
        mitigation.append("Revisar coherencia entre documentos contables y societarios")
    
    weight = 90 if adjusted_severity == "high" else 60 if adjusted_severity == "medium" else 25
    
    return {
        "finding_type": "document_inconsistency",
        "severity": adjusted_severity,
        "weight": weight,
        "explanation": risk.get("explanation", "Inconsistencia entre documentos detectada"),
        "evidence": evidence,
        "counter_evidence": [],
        "mitigation": mitigation
    }
