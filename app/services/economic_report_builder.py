"""
Builder determinista del Informe de Situación Económica (bundle).

Reglas:
- NO inventar datos: si falta, marcar "no_determinable"
- Evidencia siempre que se pueda (reutiliza Evidence de financial_analysis y evidence de alertas)
- Citas legales: corpus local TRLC (determinista)
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.api.analysis_alerts import get_analysis_alerts
from app.legal.trlc_corpus import get_trlc_article
from app.models.case import Case
from app.models.economic_report import (
    ClientSummary,
    DebtEvidenceRef,
    DebtLegalApplication,
    DebtLegalOption,
    DebtRisk,
    DebtTrlcArticleRef,
    DocumentItem,
    EconomicReportBundle,
    EvidenceRef,
    FactLawConsequence,
    LawyerSignature,
    LegalCitation,
    NarrativeContract,
    RisksByInaction,
    RoadmapItem,
)
from app.services.financial_analysis import FinancialAnalysisResult
from app.services.legal_synthesis import synthesize_legal_position


def _guess_debtor_type(case_name: str) -> str:
    n = (case_name or "").upper()
    if any(x in n for x in [" S.L", " SL", " S.A", " SA", " SOCIEDAD", " SLP", " S.L.P"]):
        return "company"
    if any(x in n for x in ["DNI", "AUTÓNOMO", "AUTONOMO", "PERSONA FÍSICA", "PERSONA FISICA"]):
        return "person"
    return "unknown"


def _mk_report_id(case_id: str) -> str:
    return hashlib.sha256(f"{case_id}:{datetime.utcnow().isoformat()}".encode()).hexdigest()[:16]


def _evidence_from_financial(e) -> EvidenceRef:
    return EvidenceRef(
        document_id=e.document_id,
        filename=e.filename,
        chunk_id=e.chunk_id,
        page=e.page,
        start_char=e.start_char,
        end_char=e.end_char,
        excerpt=e.excerpt,
        extraction_method=e.extraction_method,
    )


def _pick_any_evidence(financial: FinancialAnalysisResult) -> list[EvidenceRef]:
    evs: list[EvidenceRef] = []
    try:
        if financial.insolvency:
            for s in (financial.insolvency.signals_impago or [])[:1]:
                evs.append(_evidence_from_financial(s.evidence))
            for s in (financial.insolvency.signals_contables or [])[:1]:
                evs.append(_evidence_from_financial(s.evidence))
    except Exception:
        pass
    return evs


def _sanitize_timeline(financial: FinancialAnalysisResult) -> None:
    """
    Saneado de timeline para salida a cliente:
    - Fechas epoch o fuera de rango (1990–2100) -> None (se renderiza como "Fecha no determinada")
    - Elimina eventos sin descripción humana mínima / serializaciones crudas
    """
    try:
        tl = list(financial.timeline or [])
    except Exception:
        return

    cleaned = []
    for ev in tl:
        try:
            d = getattr(ev, "date", None)
            desc = (getattr(ev, "description", None) or "").strip()
            low = desc.lower()
            if (
                not desc
                or low == "none"
                or low.startswith("metadata:")
                or low.startswith("{")
                or low.startswith("[")
            ):
                continue

            if d is not None:
                try:
                    y = int(getattr(d, "year", 0) or 0)
                    if y < 1990 or y > 2100:
                        setattr(ev, "date", None)
                    if str(d).startswith("1970-01-01"):
                        setattr(ev, "date", None)
                except Exception:
                    setattr(ev, "date", None)

            cleaned.append(ev)
        except Exception:
            continue

    financial.timeline = cleaned  # type: ignore[assignment]


def _build_client_summary(financial: FinancialAnalysisResult, alerts_count: int) -> ClientSummary:
    # Situación base por señales de insolvencia/ratios (determinista y conservador)
    situation = "no_determinable"
    key_points: list[str] = []
    next_7_days: list[str] = []
    warnings: list[str] = []

    if financial.insolvency:
        impagos = len(financial.insolvency.signals_impago or [])
        contables = len(financial.insolvency.signals_contables or [])
        exig = len(financial.insolvency.signals_exigibilidad or [])
        key_points.append(financial.insolvency.overall_assessment)
        if impagos > 0:
            situation = "critica"
            next_7_days.append("Revisar de inmediato embargos/requerimientos y su calendario.")
        elif contables > 0 and exig > 0:
            situation = "preocupante"
            next_7_days.append(
                "Preparar relación de acreedores y vencimientos (facturas >90 días)."
            )
        elif contables > 0:
            situation = "preocupante"
            next_7_days.append(
                "Completar documentación contable para confirmar diagnóstico (balance/PyG)."
            )

        if financial.insolvency.critical_missing_docs:
            warnings.append(
                "Faltan documentos críticos: "
                + ", ".join(financial.insolvency.critical_missing_docs[:5])
            )

    if alerts_count > 0:
        key_points.append(
            "Se han detectado elementos del expediente que conviene revisar y depurar."
        )
        next_7_days.append(
            "Revisar inconsistencias, duplicidades y hechos a verificar en la documentación."
        )

    if not key_points:
        key_points.append(
            "No hay datos suficientes para concluir una situación económica con seguridad."
        )

    headline = {
        "critica": "Situación económica: requiere actuación inmediata.",
        "preocupante": "Situación económica: existen señales relevantes a confirmar.",
        "estable": "Situación económica: estable con la documentación disponible.",
        "no_determinable": "Situación económica: no determinable con la documentación actual.",
    }[situation]

    return ClientSummary(
        headline=headline,
        situation=situation,  # type: ignore[arg-type]
        key_points=key_points[:6],
        next_7_days=next_7_days[:6],
        warnings=warnings[:6],
    )


def _build_documents_inventory(
    case: Case, financial: FinancialAnalysisResult, legal_synthesis: dict
) -> tuple[list[DocumentItem], list[str], list[str]]:
    """
    Inventario documental para el cliente.

    Reglas:
    - Presentados: lo que consta en BD (Case.documents)
    - Faltantes: lo que el análisis marca como crítico + gaps legales (si existen)
    - Recomendados: checklist conservadora (sin inventar que son obligatorios)
    """

    presented: list[DocumentItem] = []
    try:
        for d in (case.documents or [])[:500]:
            presented.append(
                DocumentItem(
                    document_id=d.document_id,
                    filename=d.filename,
                    doc_type=getattr(d, "doc_type", None),
                    created_at=d.created_at.isoformat() if getattr(d, "created_at", None) else None,
                    status=getattr(d, "status", None),
                )
            )
    except Exception:
        presented = []

    missing: list[str] = []
    # Críticos desde insolvencia
    try:
        if financial.insolvency and financial.insolvency.critical_missing_docs:
            missing.extend(list(financial.insolvency.critical_missing_docs))
    except Exception:
        pass

    # Gaps de síntesis jurídica (si existen)
    try:
        gaps = (legal_synthesis or {}).get("documentary_gaps") or []
        for g in gaps:
            md = (g or {}).get("missing_document")
            if md:
                missing.append(str(md))
    except Exception:
        pass

    # Deduplicar manteniendo orden
    seen = set()
    missing = [x for x in missing if x and (x not in seen and not seen.add(x))]

    # Checklist recomendada (orientativa; el informe debe decir “recomendado”)
    recommended = [
        # Contabilidad / tesorería
        "Balance y cuenta de pérdidas y ganancias (últimos ejercicios disponibles)",
        "Libro mayor / diario y libros contables legalizados (si aplica)",
        "Extractos bancarios y posiciones de tesorería (últimos 6–12 meses)",
        "Relación de facturas vencidas y calendario de pagos/cobros",
        # Acreedores / deuda pública
        "Listado de acreedores (importe, vencimiento, garantías, contacto)",
        "Certificados/relación de deuda con AEAT y TGSS (si existe)",
        # Laboral
        "Relación de trabajadores, nóminas y seguros sociales (si aplica)",
        # Societario / decisiones
        "Actas de junta / decisiones societarias relevantes",
        # Activos
        "Inventario de bienes y derechos (activos) con cargas/gravámenes (si aplica)",
    ]

    return presented, missing, recommended


def _build_lawyer_signature_from_settings() -> Optional[LawyerSignature]:
    """
    Construye firma del abogado desde configuración/env.

    Nota: `Settings` ignora extra env vars, pero aquí lo mantenemos simple y robusto
    leyendo variables de entorno a través de `settings` si existen o directamente del entorno.
    """
    # Preferir variables de entorno directas (Settings no define estos campos aún).
    # Importante: pydantic-settings puede leer `.env` sin volcarlo a os.environ.
    # Para que esta función vea LAWYER_* aunque no se exporten en la shell,
    # cargamos `.env` de forma idempotente (sin override).
    import os
    from pathlib import Path

    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=str(Path(__file__).resolve().parents[2] / ".env"), override=False)
    except Exception:
        # Si dotenv no está disponible o falla, seguimos con os.getenv().
        pass

    name = (os.getenv("LAWYER_NAME") or "").strip()
    coleg = (os.getenv("LAWYER_COLLEGIATE_NUMBER") or "").strip()
    sig_date = (os.getenv("LAWYER_SIGNATURE_DATE") or "").strip() or None
    # Firma dummy (despacho) si no está configurada. Evita "NO CONFIGURADO" en salida cliente.
    if not name or not coleg:
        firm = (os.getenv("LAW_FIRM") or "").strip() or "Despacho"
        # Firma dummy: evita duplicar el nombre del despacho en el footer.
        return LawyerSignature(
            lawyer_name="Equipo jurídico",
            collegiate_number="PENDIENTE",
            bar_association=(os.getenv("LAWYER_BAR_ASSOCIATION") or "").strip() or None,
            law_firm=firm,
            office_city=(os.getenv("LAWYER_OFFICE_CITY") or "").strip() or None,
            signature_date=sig_date,
        )

    return LawyerSignature(
        lawyer_name=name,
        collegiate_number=coleg,
        bar_association=(os.getenv("LAWYER_BAR_ASSOCIATION") or "").strip() or None,
        law_firm=(os.getenv("LAW_FIRM") or "").strip() or None,
        office_city=(os.getenv("LAWYER_OFFICE_CITY") or "").strip() or None,
        signature_date=sig_date,
    )


def _get_legal_citations_bundle(debtor_type: str) -> dict[str, list[LegalCitation]]:
    """
    Recupera citas legales desde el corpus local del TRLC (determinista).

    Regla:
    - No se inventa: si no se encuentra un artículo, no se incluye.
    """
    sections: dict[str, list[LegalCitation]] = {}

    # Artículos base (TRLC): declaración, publicidad, crédito público/masa y pagos.
    # Nota: ajustables; si el corpus local cambia, simplemente no se incluirán.
    section_articles: dict[str, list[int]] = {
        # Inicio / declaración / publicidad (incluye intervención/suspensión en edicto)
        "concurso": [5, 32, 33, 35, 37],
        # Créditos contra la masa y pago (incluye salarios, tributarios y SS)
        "creditos_contra_masa": [242, 244, 245, 250],
        # Crédito público (puntos donde el TRLC menciona tributarios/SS en pago de masa)
        "credito_publico": [33, 245, 250],
        # Clasificación básica de créditos concursales (privilegio general / subordinados)
        "clasificacion_creditos": [280, 281, 287],
        # Orden de pago (concursales): ordinarios y subordinados
        "pago_creditos_concursales": [433, 434, 435],
        # Calificación del concurso (riesgos para administradores/afectados)
        "calificacion": [441, 442, 447, 448, 455],
    }

    # Exoneración (solo persona física)
    if debtor_type == "person":
        section_articles["exoneracion"] = [489, 490, 493, 495, 500]

    for section, nums in section_articles.items():
        out: list[LegalCitation] = []
        for n in nums:
            art = get_trlc_article(n, max_chars=1400)
            if not art:
                continue
            out.append(
                LegalCitation(
                    citation=f"TRLC Art. {art.number}",
                    text=art.text,
                    source="ley",
                    authority_level="norma",
                    relevance="alta",
                    article=str(art.number),
                    law="TRLC",
                )
            )
        if out:
            sections[section] = out

    return sections


def _build_fact_law_map(
    *,
    debtor_type: str,
    financial: FinancialAnalysisResult,
    legal_citations: dict[str, list[LegalCitation]],
    legal_synthesis: dict,
) -> list[FactLawConsequence]:
    """
    Construye el mapa visible hecho→artículo→consecuencia (conservador).
    """
    out: list[FactLawConsequence] = []

    def _add(fact: str, *, legal_keys: list[str], consequence: str, risk_if_inaction: str) -> None:
        cites: list[LegalCitation] = []
        for k in legal_keys:
            cites.extend(list(legal_citations.get(k, []))[:2])
        out.append(
            FactLawConsequence(
                fact=fact,
                legal_basis=cites,
                consequence=consequence,
                risk_if_inaction=risk_if_inaction,
                evidence=_pick_any_evidence(financial),
            )
        )

    # Hechos desde insolvencia
    if financial.insolvency:
        for s in (financial.insolvency.signals_impago or [])[:3]:
            _add(
                s.description,
                legal_keys=["concurso"],
                consequence="Puede requerir priorizar medidas de contención y preparar documentación para decisiones inmediatas.",
                risk_if_inaction="Riesgo de agravamiento de impagos y pérdida de capacidad de negociación con acreedores.",
            )
        for s in (financial.insolvency.signals_exigibilidad or [])[:2]:
            _add(
                s.description,
                legal_keys=["concurso"],
                consequence="Conviene ordenar vencimientos y acreditar la situación para elegir la vía (acuerdo/concurso).",
                risk_if_inaction="Riesgo de ejecuciones y tensión de tesorería continuada.",
            )
        for s in (financial.insolvency.signals_contables or [])[:2]:
            _add(
                s.description,
                legal_keys=["clasificacion_creditos"],
                consequence="Puede condicionar la estrategia (convenio/liquidación) y la presentación de cuentas fiables.",
                risk_if_inaction="Riesgo de decisiones con información incompleta o inconsistente.",
            )

    # Deuda pública (si se aprecia en clasificación de créditos o síntesis)
    try:
        cc = financial.credit_classification or []
        if any(
            ("AEAT" in (getattr(c, "creditor", "") or "").upper())
            or ("TGSS" in (getattr(c, "creditor", "") or "").upper())
            or ("HACIENDA" in (getattr(c, "creditor", "") or "").upper())
            or ("SEGURIDAD SOCIAL" in (getattr(c, "creditor", "") or "").upper())
            for c in cc
        ):
            _add(
                "Consta indicio de deuda pública (AEAT/TGSS) en la clasificación de créditos aportada.",
                legal_keys=["credito_publico", "creditos_contra_masa", "clasificacion_creditos"],
                consequence="La deuda pública puede condicionar el calendario de pagos y la viabilidad del plan.",
                risk_if_inaction="Riesgo de recargos/intereses y de que la deuda pública limite soluciones.",
            )
    except Exception:
        pass

    # Riesgo de calificación (si hay señales fuertes o recomendaciones)
    try:
        if (legal_synthesis or {}).get("strategic_recommendations"):
            _add(
                "Se han emitido recomendaciones preventivas sobre trazabilidad y decisiones societarias.",
                legal_keys=["calificacion"],
                consequence="Es recomendable reforzar la trazabilidad y la justificación documental de decisiones.",
                risk_if_inaction="Riesgo de mayor exposición en la fase de calificación (si se abre la sección).",
            )
    except Exception:
        pass

    # Exoneración (solo persona física) como mapa “si procede”
    if debtor_type == "person":
        _add(
            "El deudor es persona física (posible análisis de exoneración si concurren requisitos).",
            legal_keys=["exoneracion"],
            consequence="Puede evaluarse la exoneración del pasivo insatisfecho si se cumplen requisitos y hay documentación.",
            risk_if_inaction="Riesgo de perder oportunidades procesales o de presentar una solicitud incompleta.",
        )

    return out[:12]


def _build_risks_by_inaction(
    *,
    debtor_type: str,
    client_summary: ClientSummary,
    documents_missing: list[str],
) -> RisksByInaction:
    legal: list[str] = []
    economic: list[str] = []
    personal: list[str] = []

    if client_summary.situation in ("critica", "preocupante"):
        legal.append(
            "Riesgo de continuidad de ejecuciones y medidas de apremio si existen procedimientos abiertos."
        )
        economic.append("Riesgo de aumento de recargos/intereses y deterioro de la tesorería.")

    if documents_missing:
        legal.append(
            "Riesgo de decisiones procesales con expediente incompleto (puede afectar la estrategia)."
        )
        economic.append(
            "Riesgo de estimaciones erróneas por falta de balances/vencimientos completos."
        )

    if debtor_type == "company":
        personal.append(
            "Riesgo de exposición de administradores en la fase de calificación si la insolvencia se agrava (a valorar según hechos)."
        )
    elif debtor_type == "person":
        personal.append(
            "Riesgo de dificultades para acreditar requisitos de buena fe y documentación en caso de solicitar exoneración (si procede)."
        )

    return RisksByInaction(legal=legal[:6], economic=economic[:6], personal=personal[:6])


def _build_narrative_contract(
    *,
    bundle: EconomicReportBundle,
    allowed_recommendations: list[str],
    debt_legal_applications: list[DebtLegalApplication],
    fact_law_map: list[FactLawConsequence],
    risks_by_inaction: RisksByInaction,
) -> NarrativeContract:
    fin = bundle.financial_analysis
    return NarrativeContract(
        case={
            "case_id": bundle.case_id,
            "case_name": bundle.case_name,
            "debtor_type": bundle.debtor_type,
        },
        client_summary=bundle.client_summary.model_dump(),
        documents={
            "presented_count": len(bundle.documents_presented or []),
            "missing": list(bundle.documents_missing or []),
            "recommended": list(bundle.documents_recommended or []),
        },
        financial={
            "analysis_date": fin.analysis_date.isoformat(),
            "total_debt": fin.total_debt,
            "ratios": [r.model_dump() for r in (fin.ratios or [])][:12],
            "timeline": [e.model_dump() for e in (fin.timeline or [])][:20],
            "credit_classification": [c.model_dump() for c in (fin.credit_classification or [])][
                :30
            ],
        },
        insolvency_signals=[
            *(
                [s.description for s in (fin.insolvency.signals_impago or [])[:6]]
                if fin.insolvency
                else []
            ),
            *(
                [s.description for s in (fin.insolvency.signals_contables or [])[:6]]
                if fin.insolvency
                else []
            ),
            *(
                [s.description for s in (fin.insolvency.signals_exigibilidad or [])[:6]]
                if fin.insolvency
                else []
            ),
        ],
        alerts=[
            {
                "alert_type": (
                    a.alert_type.value if hasattr(a.alert_type, "value") else str(a.alert_type)
                ),
                "description": a.description,
                "evidence_count": len(a.evidence or []),
            }
            for a in (bundle.alerts or [])[:20]
        ],
        allowed_recommendations=allowed_recommendations[:20],
        legal_citations=bundle.legal_citations or {},
        debt_legal_applications=debt_legal_applications,
        fact_law_map=fact_law_map,
        risks_by_inaction=risks_by_inaction,
        lawyer_signature=bundle.lawyer_signature,
    )


def _creditor_type(creditor_name: str) -> str:
    n = (creditor_name or "").strip().upper()
    if any(
        x in n
        for x in [
            "AEAT",
            "AGENCIA TRIBUTARIA",
            "HACIENDA",
            "TGSS",
            "TESORERÍA",
            "TESORERIA",
            "SEGURIDAD SOCIAL",
            "TESORERIA GENERAL DE LA SEGURIDAD SOCIAL",
        ]
    ):
        return "public"
    if any(
        x in n
        for x in ["BANK", "BANCO", "CAIXA", "SANTANDER", "BBVA", "SABADELL", "UNICAJA", "ING"]
    ):
        return "bank"
    if any(x in n for x in ["SOCIO", "ADMINISTRADOR", "FAMILIAR", "PARIENTE", "AMIGO"]):
        return "related_party"
    return "other"


def _normalize_public_creditor_name(text: str) -> Optional[str]:
    n = (text or "").strip().upper()
    if not n:
        return None
    if any(x in n for x in ["AEAT", "AGENCIA TRIBUTARIA", "HACIENDA"]):
        return "AEAT"
    if any(
        x in n
        for x in [
            "TGSS",
            "TESORERÍA GENERAL",
            "TESORERIA GENERAL",
            "SEGURIDAD SOCIAL",
            "TESORERIA GENERAL DE LA SEGURIDAD SOCIAL",
        ]
    ):
        return "TGSS"
    return None


def _mk_debt_id(prefix: str, creditor: str, idx: int) -> str:
    slug = "".join([c.lower() if c.isalnum() else "_" for c in (creditor or "deuda")]).strip("_")
    slug = "_".join([x for x in slug.split("_") if x])[:40] or "deuda"
    return f"{prefix}_{slug}_{idx:03d}"


def _build_debt_legal_applications(
    *,
    financial: FinancialAnalysisResult,
    legal_citations: dict[str, list[LegalCitation]],
) -> list[DebtLegalApplication]:
    """
    Capa intermedia: aplicación jurídica “deuda por deuda”.
    Regla: conservador, trazable y sin inventar períodos/garantías.
    """
    out: list[DebtLegalApplication] = []

    # Selección de deudas: crédito público si existe (AEAT/TGSS priorizados) + top N por importe
    credits = list(financial.credit_classification or [])
    public: list = []
    for c in credits:
        ct = getattr(c, "creditor_type", None)
        if ct == "public":
            public.append(c)
        elif ct is None:
            if (
                _creditor_type(
                    (getattr(c, "creditor_name", "") or "")
                    + " "
                    + (getattr(c, "description", "") or "")
                )
                == "public"
            ):
                public.append(c)
    others = [c for c in credits if c not in public]
    others_sorted = sorted(others, key=lambda x: float(getattr(x, "amount", 0) or 0), reverse=True)

    def _pub_key(x) -> int:
        tag = _normalize_public_creditor_name(
            (getattr(x, "creditor_name", "") or "") + " " + (getattr(x, "description", "") or "")
        )
        return 0 if tag == "AEAT" else 1 if tag == "TGSS" else 2

    public_sorted = sorted(public, key=_pub_key)
    selected = public_sorted + others_sorted[:5]

    # Mapear bucket TRLC prudente desde credit_type
    bucket_map = {
        "privilegiado_especial": ("privilegio_especial", "high"),
        "privilegiado_general": ("privilegio_general", "medium"),
        "ordinario": ("ordinario", "medium"),
        "subordinado": ("subordinado", "medium"),
        "no_determinado": ("no_determinable", "low"),
    }

    for i, c in enumerate(selected, 1):

        def _infer_creditor_from_evidence(cand: object) -> str:
            """
            Si no consta acreedor, inferir etiqueta prudente desde evidencia/filename sin inventar.
            """
            try:
                ev0 = getattr(cand, "evidence", None)
                fn = (getattr(ev0, "filename", None) or "").strip()
                if not fn:
                    return "Acreedor"
                low = fn.lower()
                # Contratos de crédito: no consta entidad -> etiqueta genérica con referencia
                m = re.search(r"(crd-\d{4}-\d+)", low)
                if "contrato" in low and "credito" in low:
                    ref = m.group(1).upper() if m else None
                    return (
                        f"Entidad financiera (contrato {ref})"
                        if ref
                        else "Entidad financiera (contrato de crédito)"
                    )
                # Facturas: proveedor no identificado en el filename -> etiqueta genérica
                if "factura" in low:
                    return "Proveedor (según factura aportada)"
                # Reclamaciones: intentar extraer razón social del filename
                m2 = re.search(r"reclamacion[_\s\-]*pago[_\s\-]*([^\.]+)\.pdf", low)
                if m2:
                    name = m2.group(1).replace("_", " ").strip()
                    if name:
                        return name[:80].upper()
                return "Acreedor"
            except Exception:
                return "Acreedor"

        raw_creditor = (getattr(c, "creditor_name", None) or "").strip()
        creditor = (
            raw_creditor
            if raw_creditor and raw_creditor.upper() != "ACREEDOR"
            else _infer_creditor_from_evidence(c)
        )
        creditor_type = getattr(c, "creditor_type", None) or _creditor_type(
            creditor + " " + (getattr(c, "description", "") or "")
        )
        ct = getattr(c, "credit_type", None)
        ct_val = getattr(ct, "value", None) or str(ct)
        proposed_bucket, conf = bucket_map.get(str(ct_val), ("no_determinable", "low"))
        # PRD literal: NO afirmar subordinación por posible vinculación si falta base suficiente.
        # Mantener no_determinable y expresar la condición en la base.
        if creditor_type == "related_party" and proposed_bucket == "no_determinable":
            conf = "low"

        # Evidencia
        ev = getattr(c, "evidence", None)
        evidence_refs: list[DebtEvidenceRef] = []
        excerpt_for_scan = ""
        if ev:
            excerpt_for_scan = (getattr(ev, "excerpt", None) or "")[:300]
            evidence_refs.append(
                DebtEvidenceRef(
                    document_id=getattr(ev, "document_id", None),
                    document_name=getattr(ev, "filename", None) or creditor,
                    page=getattr(ev, "page", None),
                    excerpt=(getattr(ev, "excerpt", None) or "No consta extracto")[:300],
                )
            )
        # Evidencia adicional específica (período / garantía) si consta
        per_ex = (getattr(c, "period_excerpt", None) or "").strip()
        if per_ex:
            evidence_refs.append(
                DebtEvidenceRef(
                    document_id=getattr(ev, "document_id", None) if ev else None,
                    document_name=(getattr(ev, "filename", None) if ev else None) or creditor,
                    page=getattr(ev, "page", None) if ev else None,
                    excerpt=per_ex[:300],
                )
            )
        sec_ex = (getattr(c, "security_excerpt", None) or "").strip()
        if sec_ex:
            evidence_refs.append(
                DebtEvidenceRef(
                    document_id=getattr(ev, "document_id", None) if ev else None,
                    document_name=(getattr(ev, "filename", None) if ev else None) or creditor,
                    page=getattr(ev, "page", None) if ev else None,
                    excerpt=sec_ex[:300],
                )
            )

        # Base legal: escoger citas por tópico según tipo
        trlc_articles: list[DebtTrlcArticleRef] = []
        if creditor_type == "public":
            for cite in (
                legal_citations.get("clasificacion_creditos", [])[:2]
                + legal_citations.get("credito_publico", [])[:1]
            ):
                trlc_articles.append(
                    DebtTrlcArticleRef(
                        article_ref=str(getattr(cite, "citation", None) or "").replace(
                            "Art.", "art."
                        ),
                        topic="crédito público / clasificación",
                        relevance="Aplica al tratamiento concursal del crédito público identificado en el expediente.",
                    )
                )
        else:
            for cite in legal_citations.get("pago_creditos_concursales", [])[:2]:
                trlc_articles.append(
                    DebtTrlcArticleRef(
                        article_ref=str(getattr(cite, "citation", None) or "").replace(
                            "Art.", "art."
                        ),
                        topic="pago de créditos concursales",
                        relevance="Aplica al orden de pago de esta deuda conforme al TRLC.",
                    )
                )

        # Garantías: preferir campo estructurado; fallback heurístico (sin inventar)
        has_security = getattr(c, "has_security", None)
        security_type = getattr(c, "security_type", None)
        security_note = "No consta garantía real asociada en la documentación aportada"
        if has_security is True:
            if security_type == "mortgage":
                security_note = "Consta indicio de garantía hipotecaria (a verificar con documento de garantía)."
            elif security_type == "pledge":
                security_note = (
                    "Consta indicio de garantía prendaria (a verificar con documento de garantía)."
                )
            elif security_type == "reservation_of_title":
                security_note = "Consta indicio de reserva de dominio (a verificar con contrato)."
            else:
                security_note = (
                    "Consta indicio de garantía real (a verificar con documento de garantía)."
                )
        elif has_security is None:
            desc_scan = ((getattr(c, "description", None) or "") + " " + excerpt_for_scan).lower()
            if any(
                k in desc_scan for k in ["hipoteca", "garantía hipotecaria", "garantia hipotecaria"]
            ):
                has_security = True
                security_type = "mortgage"
                security_note = "Consta indicio de garantía hipotecaria (a verificar con documento de garantía)."
            elif any(
                k in desc_scan for k in ["prenda", "garantía prendaria", "garantia prendaria"]
            ):
                has_security = True
                security_type = "pledge"
                security_note = (
                    "Consta indicio de garantía prendaria (a verificar con documento de garantía)."
                )
            elif any(k in desc_scan for k in ["reserva de dominio", "reserva dominio"]):
                has_security = True
                security_type = "reservation_of_title"
                security_note = "Consta indicio de reserva de dominio (a verificar con contrato)."

        # Opciones legales (no recomendaciones absolutas)
        options: list[DebtLegalOption] = [
            DebtLegalOption(
                option_code="gather_docs",
                description="Completar documentación de la deuda (importe, período, recargos, garantías si existen).",
                prerequisites="Requiere certificados/extractos y detalle del acreedor (si aplica).",
                legal_basis_refs=[],
                warnings=[],
            )
        ]
        if creditor_type == "public":
            options.extend(
                [
                    DebtLegalOption(
                        option_code="include_in_concurso",
                        description="Valorar la inclusión de la deuda en el procedimiento concursal, asumiendo las limitaciones legales aplicables.",
                        prerequisites="Requiere identificación completa de la deuda y su calificación.",
                        legal_basis_refs=[a.article_ref for a in trlc_articles if a.article_ref],
                        warnings=[
                            "Evitar actuaciones no documentadas que puedan afectar el tratamiento de la deuda."
                        ],
                    ),
                    DebtLegalOption(
                        option_code="seek_deferral",
                        description="Valorar aplazamiento/fraccionamiento conforme a normativa específica (tributaria/Seguridad Social), si procede.",
                        prerequisites="Requiere documentación de deuda (períodos, recargos, sanciones) y requisitos específicos.",
                        legal_basis_refs=[],
                        warnings=[
                            "La solicitud y su calendario deben coordinarse con la estrategia concursal."
                        ],
                    ),
                ]
            )
        else:
            options.append(
                DebtLegalOption(
                    option_code="include_in_concurso",
                    description="Incluir la deuda en el concurso y determinar su clasificación (privilegio/ordinario/subordinado) en el informe de la Administración Concursal.",
                    prerequisites="Requiere relación de acreedores e identificación del crédito.",
                    legal_basis_refs=[a.article_ref for a in trlc_articles if a.article_ref],
                    warnings=[
                        "Si existe garantía real no documentada, la clasificación podría variar."
                    ],
                )
            )
        if creditor_type == "related_party":
            options.append(
                DebtLegalOption(
                    option_code="gather_docs",
                    description="Acreditar la relación con el acreedor (vinculación) y el origen de la deuda (préstamo, aportación, etc.).",
                    prerequisites="Requiere contratos, transferencias y soporte societario.",
                    legal_basis_refs=[],
                    warnings=[
                        "La calificación puede verse afectada si existe vinculación, conforme al TRLC."
                    ],
                )
            )

        # Consecuencias + riesgos (prudentes)
        consequences = [
            "El orden de pago dependerá de su clasificación (contra la masa / privilegiado / ordinario / subordinado).",
            "La satisfacción puede quedar condicionada a la existencia de masa suficiente tras atender créditos prioritarios.",
        ]
        risks = [
            DebtRisk(
                risk_level="medium",
                statement="Existe riesgo de recargos/intereses o deterioro de la posición negociadora si la deuda no se aborda de forma ordenada.",
                related_refs=[a.article_ref for a in trlc_articles if a.article_ref][:2],
            )
        ]

        period_start = getattr(c, "period_start", None)
        period_end = getattr(c, "period_end", None)
        period_note = (
            getattr(c, "period_note", None)
            or "No consta período exacto en la documentación aportada"
        )
        classification_basis = (
            f"Clasificación propuesta de forma prudente a partir del expediente (tipo: {ct_val}). "
            "Puede variar si se aporta documentación adicional (garantías, períodos, naturaleza exacta)."
        )
        if creditor_type == "related_party":
            classification_basis = (
                "La deuda figura a favor de un posible acreedor vinculado. A falta de acreditación completa de la vinculación y "
                "naturaleza del crédito, no es posible afirmar su calificación definitiva. Podría operar la subordinación si se "
                "acredita vinculación en los términos del TRLC, a confirmar con documentación."
            )

        amount_conf = getattr(c, "amount_confidence", None) or (
            "exact" if getattr(c, "amount", None) is not None else "unknown"
        )
        summary_amount = (
            "No consta importe exacto"
            if getattr(c, "amount", None) is None
            else f"{float(getattr(c,'amount')):,.2f} €"
        )
        if amount_conf == "approx" and getattr(c, "amount", None) is not None:
            amount_phrase = f" por importe aproximado de {summary_amount}"
        elif amount_conf == "exact" and getattr(c, "amount", None) is not None:
            amount_phrase = f" por importe de {summary_amount}"
        else:
            amount_phrase = ""
        client_ready_summary = (
            f"De la documentación analizada se desprende la existencia de una deuda con {creditor}"
            f"{amount_phrase}. "
            f"{period_note}. Conforme a la base legal indicada, esta deuda debe clasificarse y tratarse dentro del procedimiento "
            "según su naturaleza, pudiendo condicionar el orden de pagos y las opciones disponibles. "
            "Se recomienda completar el expediente de esta deuda antes de adoptar decisiones definitivas."
        )

        out.append(
            DebtLegalApplication(
                debt_id=_mk_debt_id("debt", creditor, i),
                creditor_name=creditor,
                creditor_type=creditor_type,  # type: ignore[arg-type]
                source_section="financial",
                amount_eur=float(getattr(c, "amount", None) or 0)
                if getattr(c, "amount", None) is not None
                else None,
                amount_confidence=amount_conf,  # type: ignore[arg-type]
                period_start=period_start,
                period_end=period_end,
                period_note=period_note,
                has_security=has_security,
                security_type=security_type,  # type: ignore[arg-type]
                security_note=security_note,
                proposed_trlc_bucket=proposed_bucket,  # type: ignore[arg-type]
                classification_basis=classification_basis,
                classification_confidence=conf,  # type: ignore[arg-type]
                trlc_articles=trlc_articles,
                legal_options=options,
                practical_consequences=consequences,
                risks=risks,
                evidence_refs=evidence_refs,
                client_ready_summary=client_ready_summary,
            )
        )

    # B) Añadir unidades desde ejecuciones/embargos (timeline), aunque no haya importe exacto
    try:
        tl = list(financial.timeline or [])
    except Exception:
        tl = []

    enforcement_types = {
        "embargo",
        "ejecucion",
        "ejecución",
        "apremio",
        "reclamacion",
        "reclamación",
    }
    extra_idx = 1
    for ev in tl:
        try:
            et = (getattr(ev, "event_type", None) or "").strip().lower()
            if et not in enforcement_types:
                continue
            desc = (
                getattr(ev, "description", None) or ""
            ).strip() or "Actuación de ejecución/embargo (a contextualizar)"
            d = getattr(ev, "date", None)
            ev_amount = getattr(ev, "amount", None)
            ev_evidence = getattr(ev, "evidence", None)

            # Acreedor derivado del evento (si es posible)
            cred_name = "Acreedor (procedimiento en curso)"
            cred_type = "other"
            tag = _normalize_public_creditor_name(desc)
            if tag == "AEAT":
                cred_name = "AEAT"
                cred_type = "public"
            elif tag == "TGSS":
                cred_name = "TGSS"
                cred_type = "public"

            evidence_refs: list[DebtEvidenceRef] = []
            if ev_evidence:
                evidence_refs.append(
                    DebtEvidenceRef(
                        document_id=getattr(ev_evidence, "document_id", None),
                        document_name=getattr(ev_evidence, "filename", None)
                        or "Evidencia timeline",
                        page=getattr(ev_evidence, "page", None),
                        excerpt=(getattr(ev_evidence, "excerpt", None) or "No consta extracto")[
                            :300
                        ],
                    )
                )

            period_note = "Fecha no determinada" if d is None else "Fecha indicada en el expediente"
            period_start = None
            period_end = None
            if d is not None:
                try:
                    period_start = d.date().isoformat()  # type: ignore[union-attr]
                    period_end = period_start
                except Exception:
                    period_start = None
                    period_end = None
                    period_note = "Fecha no determinada"

            trlc_articles: list[DebtTrlcArticleRef] = []
            for cite in (
                legal_citations.get("concurso", [])[:1]
                + legal_citations.get("credito_publico", [])[:1]
            ):
                trlc_articles.append(
                    DebtTrlcArticleRef(
                        article_ref=str(getattr(cite, "citation", None) or "").replace(
                            "Art.", "art."
                        ),
                        topic="actuaciones de ejecución / contexto concursal",
                        relevance="Se incorpora para contextualizar la actuación de embargo/ejecución reflejada en el expediente.",
                    )
                )

            legal_options: list[DebtLegalOption] = [
                DebtLegalOption(
                    option_code="gather_docs",
                    description="Identificar el procedimiento y obtener detalle (providencia, importe, concepto, períodos y estado).",
                    prerequisites="Requiere documentación del embargo/ejecución y, en su caso, certificados del organismo.",
                    legal_basis_refs=[],
                    warnings=[
                        "Evitar actuaciones sin coordinación con el despacho mientras se determina el alcance del procedimiento."
                    ],
                ),
                DebtLegalOption(
                    option_code="include_in_concurso",
                    description="Valorar el encaje de esta actuación en la estrategia concursal y su reflejo en el expediente.",
                    prerequisites="Requiere identificar acreedor y alcance del procedimiento.",
                    legal_basis_refs=[a.article_ref for a in trlc_articles if a.article_ref],
                    warnings=[],
                ),
            ]
            if cred_type == "public":
                legal_options.append(
                    DebtLegalOption(
                        option_code="seek_deferral",
                        description="Valorar aplazamiento/fraccionamiento conforme a normativa específica, si procede.",
                        prerequisites="Requiere detalle de deuda y requisitos del organismo.",
                        legal_basis_refs=[],
                        warnings=[
                            "Coordinar con la estrategia concursal y con la documentación aportada."
                        ],
                    )
                )

            amount_conf = "unknown" if ev_amount is None else "approx"
            amount_phrase = (
                "" if ev_amount is None else f" por importe aproximado de {float(ev_amount):,.2f} €"
            )
            client_ready_summary = (
                f"Consta una actuación de {et} en el expediente{amount_phrase}. {period_note}. "
                "Debe identificarse el procedimiento y su alcance (acreedor, concepto y estado) para valorar su tratamiento "
                "en el marco del procedimiento concursal y evitar actuaciones descoordinadas."
            )

            out.append(
                DebtLegalApplication(
                    debt_id=_mk_debt_id("debt_timeline", cred_name, extra_idx),
                    creditor_name=cred_name,
                    creditor_type=cred_type,  # type: ignore[arg-type]
                    source_section="timeline",
                    amount_eur=float(ev_amount) if ev_amount is not None else None,
                    amount_confidence=amount_conf,  # type: ignore[arg-type]
                    period_start=period_start,
                    period_end=period_end,
                    period_note=period_note,
                    has_security=None,
                    security_type=None,
                    security_note="No consta garantía real asociada (se trata de una actuación de ejecución/embargo).",
                    proposed_trlc_bucket="no_determinable",
                    classification_basis="A determinar tras identificar el procedimiento y su naturaleza. Este bloque se incorpora por constar en la línea temporal del expediente.",
                    classification_confidence="low",
                    trlc_articles=trlc_articles,
                    legal_options=legal_options,
                    practical_consequences=[
                        "Puede implicar restricciones operativas (cuentas/retenciones) y necesidad de coordinación inmediata.",
                        "Puede condicionar la estrategia de negociación y la urgencia de ordenar el expediente.",
                    ],
                    risks=[
                        DebtRisk(
                            risk_level="high",
                            statement="Existe riesgo de agravamiento del procedimiento de ejecución si no se identifica y gestiona de forma ordenada.",
                            related_refs=[a.article_ref for a in trlc_articles if a.article_ref][
                                :2
                            ],
                        )
                    ],
                    evidence_refs=evidence_refs,
                    client_ready_summary=client_ready_summary,
                )
            )
            extra_idx += 1
        except Exception:
            continue

    # B2) Añadir unidades desde señales de impago (insolvency.signals_impago) cuando representen embargo/ejecución/reclamación.
    try:
        ins = getattr(financial, "insolvency", None)
        signals = list(getattr(ins, "signals_impago", None) or []) if ins else []
    except Exception:
        signals = []

    sig_idx = 1
    for s in signals:
        try:
            desc = (getattr(s, "description", None) or "").strip()
            if not desc:
                continue
            low = desc.lower()
            if not any(k in low for k in ["embargo", "ejecuc", "apremio", "reclamaci"]):
                continue

            cred_name = "Acreedor (actuación a identificar)"
            cred_type = "other"
            tag = _normalize_public_creditor_name(desc)
            if tag == "AEAT":
                cred_name = "AEAT"
                cred_type = "public"
            elif tag == "TGSS":
                cred_name = "TGSS"
                cred_type = "public"

            sev_amount = getattr(s, "amount", None)
            sev_evidence = getattr(s, "evidence", None)
            evidence_refs: list[DebtEvidenceRef] = []
            if sev_evidence:
                evidence_refs.append(
                    DebtEvidenceRef(
                        document_id=getattr(sev_evidence, "document_id", None),
                        document_name=getattr(sev_evidence, "filename", None)
                        or "Evidencia señal de impago",
                        page=getattr(sev_evidence, "page", None),
                        excerpt=(getattr(sev_evidence, "excerpt", None) or "No consta extracto")[
                            :300
                        ],
                    )
                )

            trlc_articles: list[DebtTrlcArticleRef] = []
            for cite in (
                legal_citations.get("concurso", [])[:1]
                + legal_citations.get("credito_publico", [])[:1]
            ):
                trlc_articles.append(
                    DebtTrlcArticleRef(
                        article_ref=str(getattr(cite, "citation", None) or "").replace(
                            "Art.", "art."
                        ),
                        topic="señales de impago / ejecución",
                        relevance="Se incorpora por constar una señal de impago (embargo/ejecución/reclamación) en el expediente.",
                    )
                )

            legal_options: list[DebtLegalOption] = [
                DebtLegalOption(
                    option_code="gather_docs",
                    description="Obtener detalle de la actuación (procedimiento, acreedor, importe, concepto y estado).",
                    prerequisites="Requiere documentación asociada a la actuación y soporte del expediente.",
                    legal_basis_refs=[],
                    warnings=[
                        "Coordinar cualquier actuación con el despacho mientras se determina el alcance."
                    ],
                ),
                DebtLegalOption(
                    option_code="include_in_concurso",
                    description="Valorar su encaje en la estrategia concursal y su reflejo en el expediente.",
                    prerequisites="Requiere identificar acreedor y alcance.",
                    legal_basis_refs=[a.article_ref for a in trlc_articles if a.article_ref],
                    warnings=[],
                ),
            ]
            if cred_type == "public":
                legal_options.append(
                    DebtLegalOption(
                        option_code="seek_deferral",
                        description="Valorar aplazamiento/fraccionamiento conforme a normativa específica, si procede.",
                        prerequisites="Requiere identificación completa de la deuda subyacente.",
                        legal_basis_refs=[],
                        warnings=[
                            "Coordinar con la estrategia concursal y con la documentación aportada."
                        ],
                    )
                )

            out.append(
                DebtLegalApplication(
                    debt_id=_mk_debt_id("debt_alert", cred_name, sig_idx),
                    creditor_name=cred_name,
                    creditor_type=cred_type,  # type: ignore[arg-type]
                    source_section="alerts",
                    amount_eur=float(sev_amount) if sev_amount is not None else None,
                    amount_confidence="approx" if sev_amount is not None else "unknown",
                    period_start=None,
                    period_end=None,
                    period_note="No consta período exacto en la señal de impago (a completar con documentación).",
                    has_security=None,
                    security_type=None,
                    security_note="No consta garantía real asociada (se trata de una señal de impago/ejecución).",
                    proposed_trlc_bucket="no_determinable",
                    classification_basis="A determinar tras identificar la deuda subyacente y el procedimiento.",
                    classification_confidence="low",
                    trlc_articles=trlc_articles,
                    legal_options=legal_options,
                    practical_consequences=[
                        "Puede implicar restricciones operativas y necesidad de priorización inmediata.",
                        "Puede condicionar la estrategia de negociación y la urgencia de ordenar el expediente.",
                    ],
                    risks=[
                        DebtRisk(
                            risk_level="high",
                            statement="Existe riesgo de avance de la actuación si no se identifica y gestiona de forma ordenada.",
                            related_refs=[a.article_ref for a in trlc_articles if a.article_ref][
                                :2
                            ],
                        )
                    ],
                    evidence_refs=evidence_refs,
                    client_ready_summary=(
                        "Consta una señal de impago (embargo/ejecución/reclamación) en el expediente. "
                        "Debe identificarse la actuación y la deuda subyacente para valorar su tratamiento y coordinar la estrategia."
                    ),
                )
            )
            sig_idx += 1
        except Exception:
            continue

    return out


def _build_roadmap(
    *,
    debtor_type: str,
    financial: FinancialAnalysisResult,
    alerts_count: int,
    legal_citations: dict[str, list[LegalCitation]],
) -> list[RoadmapItem]:
    """
    Hoja de ruta determinista para iniciar y continuar el concurso.
    No sustituye asesoramiento profesional: es guía operativa condicionada por evidencias.
    """
    ev = _pick_any_evidence(financial)
    steps: list[RoadmapItem] = []

    missing = set(
        (financial.insolvency.critical_missing_docs or []) if financial.insolvency else []
    )

    # Fase 0-7 días
    steps.append(
        RoadmapItem(
            phase="0–7 días",
            step="Consolidar expediente documental (inventario, balance, PyG, acreedores, vencimientos).",
            actor="cliente",
            priority="INMEDIATA",
            status="pendiente" if missing else "en_curso",
            rationale=(
                "Sin documentación mínima no es posible una estrategia sólida. "
                "Si faltan documentos críticos, el análisis es no concluyente."
            ),
            evidence=ev,
            legal_basis=legal_citations.get("concurso", []),
        )
    )

    # Alertas / patrones
    steps.append(
        RoadmapItem(
            phase="0–7 días",
            step="Revisar incidencias del expediente (duplicidades, inconsistencias y elementos a verificar) y depurar evidencias.",
            actor="abogado",
            priority="ALTA" if alerts_count else "MEDIA",
            status="pendiente" if alerts_count else "no_determinable",
            rationale=(
                "Las alertas pueden afectar la calidad probatoria y la narrativa del expediente. "
                "Si no hay alertas, este paso no aplica."
            ),
            evidence=ev,
            legal_basis=[],
        )
    )

    # Crédito público / AEAT / TGSS (guía operativa, sin inventar normativa si no existe)
    steps.append(
        RoadmapItem(
            phase="7–15 días",
            step="Identificar deuda con Hacienda (AEAT) y Seguridad Social (TGSS) y preparar opciones (aplazamiento/fraccionamiento/plan).",
            actor="abogado",
            priority="ALTA",
            status="pendiente",
            rationale=(
                "Deuda pública suele condicionar el plan de pagos y la viabilidad. "
                "El sistema mostrará opciones típicas; la aplicabilidad depende de los documentos aportados."
            ),
            evidence=ev,
            legal_basis=legal_citations.get("credito_publico", []),
        )
    )

    # Presentación concurso (alto nivel)
    steps.append(
        RoadmapItem(
            phase="15–30 días",
            step="Preparar solicitud y anexos del concurso (lista de acreedores, inventario, cuentas, hechos relevantes).",
            actor="abogado",
            priority="ALTA",
            status="pendiente",
            rationale="Paso operativo estándar para iniciar el procedimiento; requiere revisión profesional.",
            evidence=ev,
            legal_basis=legal_citations.get("concurso", []),
        )
    )

    # Calificación culpable (prevención)
    steps.append(
        RoadmapItem(
            phase="1–3 meses",
            step="Preparar estrategia preventiva de calificación (trazabilidad, contabilidad, decisiones societarias).",
            actor="abogado",
            priority="MEDIA",
            status="pendiente",
            rationale=(
                "Mitiga riesgos de calificación: conservar evidencias y justificar decisiones. "
                "Depende de la documentación y del timeline."
            ),
            evidence=ev,
            legal_basis=legal_citations.get("calificacion", []),
        )
    )

    # Exoneración (solo si persona física)
    if debtor_type == "person":
        steps.append(
            RoadmapItem(
                phase="1–3 meses",
                step="Evaluar posible exoneración del pasivo insatisfecho (si procede) y requisitos documentales.",
                actor="abogado",
                priority="MEDIA",
                status="pendiente",
                rationale=(
                    "La exoneración solo se evalúa con datos completos y requisitos. "
                    "El informe aportará citas y dirá 'no hay' si faltan evidencias."
                ),
                evidence=ev,
                legal_basis=legal_citations.get("exoneracion", []),
            )
        )

    return steps


def build_economic_report_bundle(
    db: Session, *, case_id: str, financial_analysis: FinancialAnalysisResult
) -> EconomicReportBundle:
    case = (
        db.query(Case).options(joinedload(Case.documents)).filter(Case.case_id == case_id).first()
    )
    if not case:
        raise ValueError(f"Caso '{case_id}' no encontrado")

    debtor_type = _guess_debtor_type(case.name)
    _sanitize_timeline(financial_analysis)

    # Alertas técnicas / patrones
    alerts = get_analysis_alerts(case_id=case_id, db=db)

    # --------------------------------------------------
    # Síntesis jurídica determinista (recomendaciones “del abogado” vía reglas)
    # --------------------------------------------------
    risks: list[dict] = []

    # Riesgos a partir de insolvencia (datos fríos)
    if financial_analysis.insolvency:
        for s in (financial_analysis.insolvency.signals_impago or [])[:5]:
            risks.append(
                {
                    "risk_type": "impago_efectivo",
                    "severity": "high",
                    "explanation": s.description,
                }
            )
        for s in (financial_analysis.insolvency.signals_contables or [])[:5]:
            risks.append(
                {
                    "risk_type": "accounting_red_flags",
                    "severity": "high" if "Patrimonio neto negativo" in s.description else "medium",
                    "explanation": s.description,
                }
            )
        if financial_analysis.insolvency.critical_missing_docs:
            risks.append(
                {
                    "risk_type": "documentation_gap",
                    "severity": "high",
                    "explanation": "Faltan documentos críticos: "
                    + ", ".join(financial_analysis.insolvency.critical_missing_docs[:8]),
                }
            )

    # Riesgos por validaciones contables
    if financial_analysis.validation_result and isinstance(
        financial_analysis.validation_result, dict
    ):
        issues = financial_analysis.validation_result.get("issues") or []
        if issues:
            risks.append(
                {
                    "risk_type": "accounting_red_flags",
                    "severity": "medium",
                    "explanation": f"Validaciones contables con incidencias: {len(issues)} issue(s).",
                }
            )

    # Hallazgos técnicos (alertas) -> legal_findings "fríos"
    legal_findings: list[dict] = [
        {
            "type": (a.alert_type.value if hasattr(a.alert_type, "value") else str(a.alert_type)),
            "description": a.description,
        }
        for a in (alerts or [])
    ]

    # Timeline (convertido a dict)
    timeline_dicts: list[dict] = []
    try:
        for e in (financial_analysis.timeline or [])[:200]:
            if hasattr(e, "model_dump"):
                timeline_dicts.append(e.model_dump())
            else:
                timeline_dicts.append(dict(e))
    except Exception:
        timeline_dicts = []

    # Documentos (resumen para síntesis) + inventario cliente
    documents: list[dict] = []
    try:
        for d in (case.documents or [])[:500]:
            documents.append(
                {
                    "document_id": d.document_id,
                    "filename": d.filename,
                    "doc_type": getattr(d, "doc_type", None),
                    "created_at": d.created_at.isoformat()
                    if getattr(d, "created_at", None)
                    else None,
                }
            )
    except Exception:
        documents = []

    legal_synthesis: dict = {}
    try:
        legal_synthesis = synthesize_legal_position(
            risks=risks,
            legal_findings=legal_findings,
            timeline=timeline_dicts,
            documents=documents,
        )
    except Exception:
        # No bloquear el informe por síntesis: degradar
        legal_synthesis = {}

    # Citas legales (TRLC corpus local)
    legal_citations_raw = _get_legal_citations_bundle(debtor_type)

    # Roadmap determinista
    roadmap = _build_roadmap(
        debtor_type=debtor_type,
        financial=financial_analysis,
        alerts_count=len(alerts),
        legal_citations=legal_citations_raw,
    )

    # Añadir recomendaciones estratégicas (si existen) como pasos explícitos
    try:
        recs = (legal_synthesis or {}).get("strategic_recommendations") or []
        for r in recs[:8]:
            action = r.get("action") or "Acción recomendada"
            rationale = r.get("rationale") or ""
            priority = r.get("priority") or "MEDIA"
            roadmap.append(
                RoadmapItem(
                    phase="Plan de acción",
                    step=str(action),
                    priority=str(priority),  # type: ignore[arg-type]
                    status="pendiente",
                    rationale=str(rationale) if rationale else "Recomendación derivada de reglas.",
                    evidence=_pick_any_evidence(financial_analysis),
                    legal_basis=legal_citations_raw.get("concurso", []),
                )
            )
    except Exception:
        pass

    # Resumen cliente determinista
    client_summary = _build_client_summary(financial_analysis, alerts_count=len(alerts))

    # Inventario documental (cliente)
    documents_presented, documents_missing, documents_recommended = _build_documents_inventory(
        case, financial_analysis, legal_synthesis
    )

    # Firma (config)
    lawyer_signature = _build_lawyer_signature_from_settings()

    # Normalizar legal_citations a tipo correcto
    legal_citations: dict[str, list[LegalCitation]] = {}
    for k, v in (legal_citations_raw or {}).items():
        legal_citations[k] = v

    bundle = EconomicReportBundle(
        report_id=_mk_report_id(case_id),
        case_id=case_id,
        case_name=case.name,
        generated_at=datetime.utcnow(),
        debtor_type=debtor_type,  # type: ignore[arg-type]
        financial_analysis=financial_analysis,
        alerts=alerts,
        legal_synthesis=legal_synthesis,
        roadmap=roadmap,
        legal_citations=legal_citations,
        client_summary=client_summary,
        documents_presented=documents_presented,
        documents_missing=documents_missing,
        documents_recommended=documents_recommended,
        lawyer_signature=lawyer_signature,
        narrative_md=None,
        narrative_contract=None,
    )

    # --------------------------------------------------
    # Contrato narrativo + mapa hecho→artículo→consecuencia + riesgos por inacción
    # --------------------------------------------------
    allowed_recommendations: list[str] = []
    try:
        for r in (legal_synthesis or {}).get("strategic_recommendations") or []:
            a = (r or {}).get("action")
            if a:
                allowed_recommendations.append(str(a))
    except Exception:
        pass
    # También permitir los pasos explícitos del roadmap (sin inventar nuevos)
    allowed_recommendations.extend([x.step for x in (roadmap or [])[:20]])

    fact_law_map = _build_fact_law_map(
        debtor_type=debtor_type,
        financial=financial_analysis,
        legal_citations=legal_citations,
        legal_synthesis=legal_synthesis,
    )
    debt_legal_applications = _build_debt_legal_applications(
        financial=financial_analysis,
        legal_citations=legal_citations,
    )
    risks_by_inaction = _build_risks_by_inaction(
        debtor_type=debtor_type,
        client_summary=client_summary,
        documents_missing=documents_missing,
    )
    bundle.narrative_contract = _build_narrative_contract(
        bundle=bundle,
        allowed_recommendations=allowed_recommendations,
        debt_legal_applications=debt_legal_applications,
        fact_law_map=fact_law_map,
        risks_by_inaction=risks_by_inaction,
    )

    # Validación final (fail fast)
    json.dumps(bundle.model_dump(), ensure_ascii=False, default=str)
    return bundle
