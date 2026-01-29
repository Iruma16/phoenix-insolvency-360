from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

from app.models.economic_report import EconomicReportBundle


Audience = Literal["internal", "client"]
Severity = Literal["PASS", "FAIL_BLANDO", "FAIL_DURO"]
Action = Literal["ACCEPT", "RETRY_NARRATIVE", "DROP_NARRATIVE", "BLOCK_CLIENT_OUTPUT"]


@dataclass(frozen=True)
class ExportCheckViolation:
    rule_id: str
    severity: Severity
    message: str
    action: Action
    section: str
    fragment: Optional[str] = None


@dataclass(frozen=True)
class ExportCheckReport:
    ok: bool
    audience: Audience
    violations: list[ExportCheckViolation]


_TECH_TERMS = re.compile(
    r"("
    r"\b(metadata|chunk|embedding|rag|llm|ocr|offset|suspicious_pattern|temporal_inconsistency|duplicated_data|inconsistent_data|missing_data)\b"
    r"|alertas?\s+t[eé]cnicas"
    r"|\bconfianza\b"
    r")",
    re.IGNORECASE,
)
_EPOCH = re.compile(r"\b1970-01-01\b")
_MICROSECONDS_WEIRD = re.compile(r"\.\d{6,}\b")
_DASHBOARD_HEADINGS = re.compile(r"\b(puntos\s+clave|qu[eé]\s+hacer\s+en\s+7\s+d[ií]as)\b", re.IGNORECASE)
_DASHBOARD_COUNTS = re.compile(r"\b\d+\s+(indicadores|alertas)\b", re.IGNORECASE)
_AI_TERMS = re.compile(r"\b(ia|inteligencia\s+artificial|automatizad[oa]|llm|rag)\b", re.IGNORECASE)
_TRLC_ART_RE = re.compile(
    r"\bTRLC\s*(?:art\.|arts\.|art|arts|Art\.|Arts\.|artículo|articulos|artículos)\s*\d+\b",
    re.IGNORECASE,
)
_PENAL_TERMS = re.compile(r"\b(delito|penal|fraude|culpable|criminal)\b", re.IGNORECASE)
_CONDITIONALS = re.compile(r"\b(podr[ií]a|posible|a\s+valorar|a\s+confirmar|en\s+su\s+caso)\b", re.IGNORECASE)
_RECOMMENDATION_CUE = re.compile(
    # Importante: NO incluir "debe/debería" aquí, porque aparece en enunciados jurídicos
    # (p.ej., "esta deuda debe clasificarse...") y generaría falsos positivos.
    r"\b(se\s+recomienda|recomendamos|se\s+aconseja|conviene|es\s+necesario)\b",
    re.IGNORECASE,
)
_WARNING_CUE = re.compile(r"\b(evitar|no\s+realizar|no\s+efectuar|no\s+proceder)\b", re.IGNORECASE)
_TABLE_HEADERS = re.compile(r"\b(Hecho\s*\|\s*Base\s+legal|Hecho\s*/\s*Base\s+legal)\b", re.IGNORECASE)
_TABLE_INTRO = re.compile(r"\b(a\s+continuaci[oó]n|seguidamente|con\s+car[aá]cter\s+orientativo)\b", re.IGNORECASE)

# Números visibles (euros / porcentajes) para R6-R7
# Importes en euros:
# - Formato ES: 1.234,56 € / 1234,56 €
# - Formato EN: 1,234.56 € / 1234.56 €
# Regla: evitar matches parciales tipo "...00 €" dentro de "3,000.00 €"
_MONEY_RE = re.compile(
    r"(?<![\d\.,])"
    r"([+\-−]?\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})|[+\-−]?\d+(?:,\d{2})?|[+\-−]?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)"
    r"\s*€(?!\w)"
)
_PERCENT_RE = re.compile(r"(?<!\w)(\d{1,3}(?:[.,]\d+)?)\s*%")


def _year_ok(dt: datetime) -> bool:
    return 1990 <= dt.year <= 2100


def _norm_trlc_ref(s: str) -> Optional[str]:
    """
    Normaliza referencias TRLC para comparación robusta.
    Ejemplos:
    - "TRLC art. 280" -> "trlc art 280"
    - "TRLC art 280"  -> "trlc art 280"
    - "TRLC arts. 270 y ss." -> "trlc art 270"
    """
    try:
        s = (s or "").strip().lower()
        if "trlc" not in s:
            return None
        m = re.search(r"\btrlc\b.*?\b(\d{1,4})\b", s)
        if not m:
            return None
        return f"trlc art {int(m.group(1))}"
    except Exception:
        return None


def _allowed_recommendation_patterns(bundle: EconomicReportBundle) -> list[re.Pattern]:
    """
    Mapea option_code permitidos a patrones lingüísticos aceptables en recomendaciones.
    Esto fuerza que, si aparece una recomendación explícita, esté alineada con legal_options.
    """
    allowed_codes: set[str] = set()
    try:
        contract = getattr(bundle, "narrative_contract", None)
        apps = list(getattr(contract, "debt_legal_applications", None) or []) if contract else []
        for d in apps:
            for o in (getattr(d, "legal_options", None) or []):
                oc = str(getattr(o, "option_code", "") or "").strip()
                if oc:
                    allowed_codes.add(oc)
    except Exception:
        pass

    # Fallback: si no hay debt apps, permitir nada (bloquear recomendaciones explícitas).
    patterns: list[re.Pattern] = []
    code_to_patterns: dict[str, list[str]] = {
        "include_in_concurso": [r"\bincluir\b.*\bconcurso\b", r"\bpresentar\b.*\bconcurso\b"],
        "negotiate_payment_plan": [r"\bnegociar\b", r"\bplan\s+de\s+pagos\b"],
        "seek_deferral": [r"\baplazamiento\b", r"\bfraccionamiento\b"],
        "secure_financing": [r"\bfinanciaci[oó]n\b", r"\bliquidez\b"],
        "challenge_claim": [r"\bimpugnar\b", r"\boposici[oó]n\b.*\bcr[eé]dito\b"],
        "verify_collateral": [r"\bverificar\b.*\bgarant[ií]a\b", r"\bhipoteca\b", r"\bprenda\b"],
        "gather_docs": [r"\brecopilar\b.*\bdocumentaci[oó]n\b", r"\bobtener\b.*\bcertificad", r"\bcompletar\b.*\bexpediente\b"],
    }

    for code in sorted(allowed_codes):
        for pat in code_to_patterns.get(code, []):
            patterns.append(re.compile(pat, re.IGNORECASE))
    return patterns


def _norm_money(s: str) -> Optional[float]:
    try:
        s = s.strip().replace(" ", "")
        sign = 1.0
        if s.startswith(("-", "−")):
            sign = -1.0
            s = s[1:]
        elif s.startswith("+"):
            s = s[1:]
        # 1.234,56 -> 1234.56
        # 1,234.56 -> 1234.56
        if "," in s and "." in s:
            # Heurística: si termina en .dd => formato EN; si termina en ,dd => formato ES
            if re.search(r"\.\d{2}$", s):
                s = s.replace(",", "")
            else:
                s = s.replace(".", "").replace(",", ".")
        elif "," in s and "." not in s:
            # 1234,56
            s = s.replace(",", ".")
        elif "." in s and "," not in s:
            # 1234.56 o 1.234 (sin decimales)
            # si hay exactamente 2 decimales, dejar; si no, tratar como separador miles
            if not re.search(r"\.\d{2}$", s):
                s = s.replace(".", "")
        return sign * float(s)
    except Exception:
        return None


def _norm_percent(s: str) -> Optional[float]:
    try:
        s = s.strip().replace(",", ".")
        return float(s)
    except Exception:
        return None


def _visible_texts(bundle: EconomicReportBundle) -> list[tuple[str, str]]:
    """
    Textos que pueden acabar visibles al cliente (para chequeo R4-R15).
    """
    texts: list[tuple[str, str]] = []
    cs = bundle.client_summary
    texts.append(("summary", cs.headline))
    texts.extend(("summary", x) for x in (cs.key_points or []))
    texts.extend(("summary", x) for x in (cs.next_7_days or []))
    texts.extend(("summary", x) for x in (cs.warnings or []))

    try:
        ins = bundle.financial_analysis.insolvency
        if ins:
            texts.append(("insolvency", ins.overall_assessment))
            for s in (ins.signals_impago or []) + (ins.signals_contables or []) + (ins.signals_exigibilidad or []):
                texts.append(("insolvency", getattr(s, "description", "") or ""))
    except Exception:
        pass

    # debt applications (resúmenes + bases)
    try:
        contract = getattr(bundle, "narrative_contract", None)
        apps = list(getattr(contract, "debt_legal_applications", None) or []) if contract else []
        for d in apps:
            texts.append(("debt", str(getattr(d, "client_ready_summary", "") or "")))
            texts.append(("debt", str(getattr(d, "classification_basis", "") or "")))
            for a in (getattr(d, "trlc_articles", None) or []):
                texts.append(("debt", str(getattr(a, "article_ref", "") or "")))
    except Exception:
        pass

    # narrativa libre (si existiera)
    if getattr(bundle, "narrative_md", None):
        texts.append(("narrative", str(bundle.narrative_md or "")))

    # alertas (no se imprimen en client, pero pueden colarse)
    for a in bundle.alerts or []:
        texts.append(("alerts", getattr(a, "description", "") or ""))
        atype = getattr(getattr(a, "alert_type", None), "value", None) or str(getattr(a, "alert_type", "") or "")
        texts.append(("alerts", atype))

    return [(sec, t) for sec, t in texts if t]


def check_export(bundle: EconomicReportBundle, *, audience: Audience) -> ExportCheckReport:
    v: list[ExportCheckViolation] = []

    def _sig_field(obj: object, name: str) -> str:
        if obj is None:
            return ""
        if isinstance(obj, dict):
            return str(obj.get(name) or "")
        return str(getattr(obj, name, "") or "")

    # R3 Firma (client: obligatoria, con despacho)
    sig = bundle.lawyer_signature
    if audience == "client":
        lawyer_name = _sig_field(sig, "lawyer_name")
        collegiate_number = _sig_field(sig, "collegiate_number")
        law_firm = _sig_field(sig, "law_firm")
        signature_date = _sig_field(sig, "signature_date")
        if not sig or not lawyer_name or not collegiate_number or collegiate_number.strip().upper() in (
            "PENDIENTE",
            "NO CONFIGURADO",
        ):
            v.append(
                ExportCheckViolation(
                    rule_id="R3",
                    severity="FAIL_DURO",
                    message="Firma no válida para entrega (falta nombre o nº colegiado)",
                    action="BLOCK_CLIENT_OUTPUT",
                    section="signature",
                )
            )
        elif not law_firm.strip():
            v.append(
                ExportCheckViolation(
                    rule_id="R3",
                    severity="FAIL_DURO",
                    message="Firma no válida para entrega (falta despacho)",
                    action="BLOCK_CLIENT_OUTPUT",
                    section="signature",
                )
            )
        elif not signature_date.strip():
            v.append(
                ExportCheckViolation(
                    rule_id="R3",
                    severity="FAIL_DURO",
                    message="Firma no válida para entrega (falta fecha de firma)",
                    action="BLOCK_CLIENT_OUTPUT",
                    section="signature",
                )
            )
    else:
        lawyer_name = _sig_field(sig, "lawyer_name")
        collegiate_number = _sig_field(sig, "collegiate_number")
        if not sig or not lawyer_name or not collegiate_number or collegiate_number.strip().upper() in (
            "PENDIENTE",
            "NO CONFIGURADO",
        ):
            v.append(
                ExportCheckViolation(
                    rule_id="R3",
                    severity="FAIL_BLANDO",
                    message="Firma incompleta (borrador interno)",
                    action="ACCEPT",
                    section="signature",
                )
            )

    # R1/R2 Timeline
    for ev in bundle.financial_analysis.timeline or []:
        d = getattr(ev, "date", None)
        desc = (getattr(ev, "description", None) or "").strip()
        # PRD: se permite "Fecha no determinada" (d=None), pero se bloquea si hay fecha epoch/out-of-range.
        if isinstance(d, datetime) and not _year_ok(d):
            if audience == "client":
                v.append(
                    ExportCheckViolation(
                        rule_id="R1",
                        severity="FAIL_DURO",
                        message="Timeline con fecha inválida/epoch",
                        action="BLOCK_CLIENT_OUTPUT",
                        section="timeline",
                        fragment=str(d),
                    )
                )
            else:
                v.append(
                    ExportCheckViolation(
                        rule_id="R1",
                        severity="FAIL_DURO",
                        message="Timeline con fecha inválida/epoch",
                        action="DROP_NARRATIVE",
                        section="timeline",
                        fragment=str(d),
                    )
                )

        if not desc or desc.lower() == "none":
            v.append(
                ExportCheckViolation(
                    rule_id="R2",
                    severity="FAIL_DURO",
                    message="Timeline sin descripción legible",
                    action="BLOCK_CLIENT_OUTPUT" if audience == "client" else "DROP_NARRATIVE",
                    section="timeline",
                    fragment=desc,
                )
            )

        if _EPOCH.search(desc) or _MICROSECONDS_WEIRD.search(desc):
            v.append(
                ExportCheckViolation(
                    rule_id="R1",
                    severity="FAIL_DURO",
                    message="Timeline contiene epoch/microsegundos raros",
                    action="BLOCK_CLIENT_OUTPUT" if audience == "client" else "DROP_NARRATIVE",
                    section="timeline",
                    fragment=desc,
                )
            )

    # R4 tecnicismos visibles en campos cliente (resumen/alertas/señales)
    texts = _visible_texts(bundle)
    allowed_rec_pats = _allowed_recommendation_patterns(bundle) if audience == "client" else []
    for section, t in texts:
        if not t:
            continue
        if _TECH_TERMS.search(t):
            v.append(
                ExportCheckViolation(
                    rule_id="R4",
                    severity="FAIL_DURO" if audience == "client" else "FAIL_BLANDO",
                    message="Lenguaje técnico interno visible",
                    action="BLOCK_CLIENT_OUTPUT" if audience == "client" else "RETRY_NARRATIVE",
                    section=section,
                    fragment=t[:160],
                )
            )
        # R14: IA/automatización visible
        if _AI_TERMS.search(t):
            v.append(
                ExportCheckViolation(
                    rule_id="R14",
                    severity="FAIL_DURO" if audience == "client" else "FAIL_BLANDO",
                    message="Referencia técnica/IA no permitida",
                    action="BLOCK_CLIENT_OUTPUT" if audience == "client" else "RETRY_NARRATIVE",
                    section=section,
                    fragment=t[:160],
                )
            )
        # Headings tipo dashboard (blando)
        if _DASHBOARD_HEADINGS.search(t):
            v.append(
                ExportCheckViolation(
                    rule_id="R5",
                    severity="FAIL_BLANDO",
                    message="Resumen con headings tipo ficha (dashboard)",
                    action="RETRY_NARRATIVE",
                    section=section,
                    fragment=t[:160],
                )
            )
        if _DASHBOARD_COUNTS.search(t):
            v.append(
                ExportCheckViolation(
                    rule_id="R5",
                    severity="FAIL_BLANDO",
                    message="Texto con contadores tipo dashboard (indicadores/alertas)",
                    action="RETRY_NARRATIVE",
                    section=section,
                    fragment=t[:160],
                )
            )

        # R10: lenguaje penal/acusatorio sin condicional
        if _PENAL_TERMS.search(t) and not _CONDITIONALS.search(t):
            v.append(
                ExportCheckViolation(
                    rule_id="R10",
                    severity="FAIL_DURO",
                    message="Lenguaje acusatorio/penal no permitido",
                    action="BLOCK_CLIENT_OUTPUT" if audience == "client" else "DROP_NARRATIVE",
                    section=section,
                    fragment=t[:160],
                )
            )

        # R11: tabla legal sin párrafo introductorio pedagógico (si aparece tabla en narrativa)
        if section in ("narrative",) and _TABLE_HEADERS.search(t):
            window = t[:500]
            if not _TABLE_INTRO.search(window):
                v.append(
                    ExportCheckViolation(
                        rule_id="R11",
                        severity="FAIL_BLANDO",
                        message="Tabla sin contexto cliente (falta introducción pedagógica)",
                        action="RETRY_NARRATIVE",
                        section=section,
                        fragment=t[:160],
                    )
                )

        # R13: recomendación fuera de legal_options permitidas (client: bloqueante)
        if audience == "client":
            # Se aplica por frases: si hay un cue de recomendación, debe contener una acción permitida,
            # salvo que sea un aviso tipo "evitar/no realizar".
            for sent in re.split(r"(?<=[\.\!\?])\s+", t):
                if not sent or len(sent) < 10:
                    continue
                if not _RECOMMENDATION_CUE.search(sent):
                    continue
                if _WARNING_CUE.search(sent):
                    continue
                if not allowed_rec_pats or not any(p.search(sent) for p in allowed_rec_pats):
                    v.append(
                        ExportCheckViolation(
                            rule_id="R13",
                            severity="FAIL_DURO",
                            message="Recomendación no autorizada",
                            action="BLOCK_CLIENT_OUTPUT",
                            section=section,
                            fragment=sent[:160],
                        )
                    )

    # R6/R7/R8/R9: coherencia de números y artículos en textos visibles (client)
    if audience == "client":
        # Allowed numbers
        allowed_money: set[float] = set()
        allowed_percent: set[float] = set()
        # money: total_debt, credit_classification amounts, debt apps amounts
        try:
            if bundle.financial_analysis.total_debt and float(bundle.financial_analysis.total_debt) > 0:
                allowed_money.add(float(bundle.financial_analysis.total_debt))
        except Exception:
            pass
        try:
            for c in (bundle.financial_analysis.credit_classification or [])[:50]:
                amt = float(getattr(c, "amount", 0) or 0)
                if amt > 0:
                    allowed_money.add(amt)
        except Exception:
            pass
        try:
            contract = getattr(bundle, "narrative_contract", None)
            apps = list(getattr(contract, "debt_legal_applications", None) or []) if contract else []
            for d in apps:
                amt = getattr(d, "amount_eur", None)
                if amt is not None:
                    fv = float(amt)
                    if fv > 0:
                        allowed_money.add(fv)
        except Exception:
            pass

        # money: insolvency signal amounts (incluye negativos)
        try:
            ins = bundle.financial_analysis.insolvency
            if ins:
                for s in (ins.signals_impago or []) + (ins.signals_contables or []) + (ins.signals_exigibilidad or []):
                    a = getattr(s, "amount", None)
                    if a is None:
                        continue
                    fv = float(a)
                    if fv != 0:
                        allowed_money.add(fv)
                        allowed_money.add(abs(fv))
        except Exception:
            pass

        # money: balance / P&L values (si existen). Añadimos tanto valor como abs(valor) para robustez.
        def _collect_values(obj: object) -> None:
            try:
                if obj is None:
                    return
                for _, v in getattr(obj, "__dict__", {}).items():
                    if v is None:
                        continue
                    # Campos tipo BalanceField/ProfitLossField tienen .value
                    if hasattr(v, "value"):
                        try:
                            fv = float(getattr(v, "value"))
                            if fv != 0:
                                allowed_money.add(fv)
                                allowed_money.add(abs(fv))
                        except Exception:
                            pass
            except Exception:
                return

        try:
            _collect_values(getattr(bundle.financial_analysis, "balance", None))
            _collect_values(getattr(bundle.financial_analysis, "profit_loss", None))
        except Exception:
            pass

        # Fallback robusto (opción A): si el propio bloque determinista de insolvencia
        # ya incluye importes en texto (p.ej. "déficit ... 115.000 €"), tratarlos como trazables.
        # Esto evita falsos positivos de R6 cuando esos importes no vienen poblados en `signal.amount`.
        try:
            for sec, t in texts:
                if sec != "insolvency":
                    continue
                for m in _MONEY_RE.finditer(t):
                    val = _norm_money(m.group(1))
                    if val is None or val == 0:
                        continue
                    allowed_money.add(val)
                    allowed_money.add(abs(val))
        except Exception:
            pass

        # percent: ratios values that look like ratios (0-1) or 0-100, allow both raw and *100
        try:
            for r in (bundle.financial_analysis.ratios or [])[:30]:
                v0 = getattr(r, "value", None)
                if v0 is None:
                    continue
                fv = float(v0)
                allowed_percent.add(fv)
                allowed_percent.add(fv * 100.0)
        except Exception:
            pass

        # Allowed TRLC refs: from debt apps trlc_articles + legal_citations
        allowed_trlc: set[str] = set()
        try:
            contract = getattr(bundle, "narrative_contract", None)
            apps = list(getattr(contract, "debt_legal_applications", None) or []) if contract else []
            for d in apps:
                for a in (getattr(d, "trlc_articles", None) or []):
                    ar = str(getattr(a, "article_ref", "") or "").strip()
                    if ar:
                        n = _norm_trlc_ref(ar)
                        if n:
                            allowed_trlc.add(n)
        except Exception:
            pass
        try:
            for _, cites in (bundle.legal_citations or {}).items():
                for c in cites[:50]:
                    ar = str(getattr(c, "citation", "") or "").strip()
                    if ar:
                        n = _norm_trlc_ref(ar)
                        if n:
                            allowed_trlc.add(n)
        except Exception:
            pass

        for section, t in texts:
            # R7: "aprox" requiere amount_confidence=approx en alguna deuda cuando se menciona cantidad
            if re.search(r"\b(aprox\.?|aproximad[oa])\b", t, re.IGNORECASE):
                # si aparece aprox, debe existir al menos una deuda con amount_confidence=approx
                ok_approx = False
                try:
                    contract = getattr(bundle, "narrative_contract", None)
                    apps = list(getattr(contract, "debt_legal_applications", None) or []) if contract else []
                    ok_approx = any(getattr(d, "amount_confidence", None) == "approx" for d in apps)
                except Exception:
                    ok_approx = False
                if not ok_approx:
                    v.append(
                        ExportCheckViolation(
                            rule_id="R7",
                            severity="FAIL_DURO",
                            message="Aproximación no soportada",
                            action="BLOCK_CLIENT_OUTPUT",
                            section=section,
                            fragment=t[:160],
                        )
                    )

            # R6: euros no trazables
            for m in _MONEY_RE.finditer(t):
                val = _norm_money(m.group(1))
                if val is None:
                    continue
                # tolerancia por redondeo (1€)
                if not any(abs(val - a) <= 1.0 for a in allowed_money):
                    v.append(
                        ExportCheckViolation(
                            rule_id="R6",
                            severity="FAIL_DURO",
                            message="Número no trazable a datos del caso (importe)",
                            action="BLOCK_CLIENT_OUTPUT",
                            section=section,
                            fragment=m.group(0),
                        )
                    )

            # R6: porcentajes no trazables
            for p in _PERCENT_RE.finditer(t):
                val = _norm_percent(p.group(1))
                if val is None:
                    continue
                if not any(abs(val - a) <= 0.1 for a in allowed_percent):
                    v.append(
                        ExportCheckViolation(
                            rule_id="R6",
                            severity="FAIL_DURO",
                            message="Número no trazable a datos del caso (porcentaje)",
                            action="BLOCK_CLIENT_OUTPUT",
                            section=section,
                            fragment=p.group(0),
                        )
                    )

            # R8: TRLC ref no permitido (si aparece texto con TRLC art)
            for m in _TRLC_ART_RE.finditer(t):
                ref = _norm_trlc_ref(m.group(0))
                if ref and allowed_trlc and ref not in allowed_trlc:
                    v.append(
                        ExportCheckViolation(
                            rule_id="R8",
                            severity="FAIL_DURO",
                            message="Cita legal no permitida/no listada",
                            action="BLOCK_CLIENT_OUTPUT",
                            section=section,
                            fragment=m.group(0),
                        )
                    )

            # R9: “Según la Ley Concursal / TRLC” con conclusión sin artículo
            if re.search(r"\b(seg[uú]n\s+la\s+ley\s+concursal|conforme\s+al\s+trlc)\b", t, re.IGNORECASE):
                if not _TRLC_ART_RE.search(t) and re.search(r"\b(debe|determina|establece|condiciona)\b", t, re.IGNORECASE):
                    v.append(
                        ExportCheckViolation(
                            rule_id="R9",
                            severity="FAIL_BLANDO",
                            message="Conclusión sin base legal referenciada",
                            action="RETRY_NARRATIVE",
                            section=section,
                            fragment=t[:160],
                        )
                    )

        # R15: exceso de señales sin jerarquía (blando en client)
        try:
            ins = bundle.financial_analysis.insolvency
            if ins:
                total = len(ins.signals_impago or []) + len(ins.signals_contables or []) + len(ins.signals_exigibilidad or [])
                if total > 18:
                    v.append(
                        ExportCheckViolation(
                            rule_id="R15",
                            severity="FAIL_BLANDO",
                            message="Señales no priorizadas",
                            action="RETRY_NARRATIVE",
                            section="insolvency",
                            fragment=f"signals_total={total}",
                        )
                    )
        except Exception:
            pass

    # R12 (PRD): no afirmar clasificación sin base/cautela suficiente (deuda por deuda)
    if audience == "client":
        try:
            contract = getattr(bundle, "narrative_contract", None)
            apps = list(getattr(contract, "debt_legal_applications", None) or []) if contract else []
            for d in apps:
                bucket = str(getattr(d, "proposed_trlc_bucket", "no_determinable") or "no_determinable")
                basis = str(getattr(d, "classification_basis", "") or "")
                conf = str(getattr(d, "classification_confidence", "low") or "low")
                if bucket != "no_determinable":
                    # Debe existir base y debe ser cautelosa si la confianza no es alta
                    if not basis.strip():
                        v.append(
                            ExportCheckViolation(
                                rule_id="R12",
                                severity="FAIL_DURO",
                                message="Clasificación sin base suficiente en una deuda",
                                action="BLOCK_CLIENT_OUTPUT",
                                section="debt_legal_applications",
                                fragment=str(getattr(d, "creditor_name", "") or "")[:160],
                            )
                        )
                    if conf in ("low", "medium"):
                        low_basis = basis.lower()
                        if not any(x in low_basis for x in ["a falta", "a confirmar", "puede variar", "podría", "a determinar"]):
                            v.append(
                                ExportCheckViolation(
                                    rule_id="R12",
                                    severity="FAIL_DURO",
                                    message="Clasificación concluyente sin cautela suficiente",
                                    action="BLOCK_CLIENT_OUTPUT",
                                    section="debt_legal_applications",
                                    fragment=(str(getattr(d, "creditor_name", "") or "") + " — " + basis)[:160],
                                )
                            )
        except Exception:
            pass

    ok = not any(x.action == "BLOCK_CLIENT_OUTPUT" for x in v) if audience == "client" else True
    return ExportCheckReport(ok=ok, audience=audience, violations=v)

