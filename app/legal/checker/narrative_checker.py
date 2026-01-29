from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional

from app.legal.checker.models import CheckError, CheckResult
from app.legal.checker.patterns import (
    CONDITIONAL_MARKERS_RE,
    DATE_DMY_RE,
    DATE_ISO_RE,
    DASHBOARD_COUNTS_RE,
    FORBIDDEN_TECH_WORDS_RE,
    INTERNAL_LABELS_RE,
    MONEY_RE,
    PENAL_ASSERTION_RE,
    PENAL_TERMS_RE,
    PERCENT_RE,
    TRLC_ARTICLE_RE,
)
from app.legal.trlc_corpus import get_trlc_article
from app.models.economic_report import EconomicReportBundle


def _to_iso(d: object) -> Optional[str]:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date().isoformat()
    if isinstance(d, date):
        return d.isoformat()
    s = str(d).strip()
    if not s:
        return None
    # aceptar ISO ya
    if DATE_ISO_RE.search(s):
        return s[:10]
    # intentar dd/mm/yyyy -> yyyy-mm-dd
    m = DATE_DMY_RE.search(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}"
    return None


def _norm_num(s: str) -> str:
    """
    Normaliza números para comparación:
    - quita espacios
    - convierte coma decimal a punto cuando aplique
    - elimina separadores de miles comunes
    """
    s = (s or "").strip()
    s = s.replace(" ", "")
    # si tiene coma y punto, asumir separador miles + decimal -> quitar miles
    if "," in s and "." in s:
        # caso 1.234,56 -> quitar puntos, coma->punto
        s = s.replace(".", "").replace(",", ".")
        return s
    # caso 1 234,56 o 1234,56
    if "," in s and "." not in s:
        return s.replace(",", ".")
    return s


def _extract_allowed_articles(bundle: EconomicReportBundle) -> set[int]:
    allowed: set[int] = set()
    for _sec, cites in (bundle.legal_citations or {}).items():
        for c in cites or []:
            # preferir campo article si existe
            try:
                if getattr(c, "article", None):
                    allowed.add(int(str(getattr(c, "article")).strip()))
                    continue
            except Exception:
                pass
            # intentar parsear de citation "TRLC Art. 245"
            cit = (getattr(c, "citation", None) or "").strip()
            for m in TRLC_ARTICLE_RE.finditer(cit):
                try:
                    allowed.add(int(m.group(1)))
                except Exception:
                    continue
    return allowed


def _extract_allowed_dates(bundle: EconomicReportBundle) -> set[str]:
    allowed: set[str] = set()
    iso = _to_iso(bundle.financial_analysis.analysis_date)
    if iso:
        allowed.add(iso)
    iso = _to_iso(bundle.generated_at)
    if iso:
        allowed.add(iso)
    for ev in bundle.financial_analysis.timeline or []:
        iso = _to_iso(getattr(ev, "date", None) or getattr(ev, "event_date", None))
        if iso:
            allowed.add(iso)
    return allowed


def _extract_allowed_numbers(bundle: EconomicReportBundle) -> set[str]:
    """
    Conjunto de números permitidos (normalizados).
    Incluye:
    - total_debt
    - ratios.value
    - contadores simples (alertas, documentos, eventos)
    """
    allowed: set[str] = set()

    # floats
    def _add_float(x: Optional[float]) -> None:
        if x is None:
            return
        # normalizar con dos decimales (lo más común en informes)
        allowed.add(_norm_num(f"{float(x):.2f}"))

    # ints
    def _add_int(x: int) -> None:
        allowed.add(str(int(x)))

    _add_float(bundle.financial_analysis.total_debt)
    for r in bundle.financial_analysis.ratios or []:
        _add_float(getattr(r, "value", None))

    # Nº colegiado / firma (si existe)
    try:
        if bundle.lawyer_signature and bundle.lawyer_signature.collegiate_number:
            cn = str(bundle.lawyer_signature.collegiate_number).strip()
            if cn.isdigit():
                allowed.add(cn)
    except Exception:
        pass

    # contadores
    _add_int(len(bundle.alerts or []))
    _add_int(len(bundle.documents_presented or []))
    _add_int(len(bundle.financial_analysis.timeline or []))

    return allowed


def check_narrative(text: str, *, bundle: EconomicReportBundle) -> CheckResult:
    """
    Checker jurídico determinista.

    Regla: valida o rechaza; NO reescribe.
    """
    res = CheckResult(status="PASS", severity="SOFT", errors=[], action="ACCEPT")
    t = (text or "").strip()
    if not t:
        # narrativa vacía -> OK (se puede descartar arriba)
        return res

    # 1) Lenguaje prohibido (bloqueante)
    if FORBIDDEN_TECH_WORDS_RE.search(t):
        res.status = "FAIL"
        res.severity = "BLOCKING"
        res.action = "DROP_NARRATIVE"
        res.errors.append(
            CheckError(type="FORBIDDEN_TECH_WORD", detail="Aparecen referencias técnicas prohibidas (IA/LLM/RAG/etc.)")
        )

    # 1b) Etiquetas internas (bloqueante)
    if INTERNAL_LABELS_RE.search(t):
        res.status = "FAIL"
        res.severity = "BLOCKING"
        res.action = "DROP_NARRATIVE"
        res.errors.append(
            CheckError(type="INTERNAL_LABEL", detail="Aparecen etiquetas internas (alertas técnicas) en texto cliente")
        )

    # 1c) Conteos tipo dashboard (soft: pedir re-redacción)
    if DASHBOARD_COUNTS_RE.search(t):
        if res.status != "FAIL":
            res.status = "FAIL"
        if res.severity != "BLOCKING":
            res.severity = "SOFT"
        if res.action == "ACCEPT":
            res.action = "RETRY"
        res.errors.append(
            CheckError(type="DASHBOARD_COUNT", detail="Aparecen conteos tipo 'X indicadores/alertas' en lenguaje de dashboard")
        )

    # 2) Artículos TRLC (bloqueante)
    allowed_articles = _extract_allowed_articles(bundle)
    for m in TRLC_ARTICLE_RE.finditer(t):
        try:
            n = int(m.group(1))
        except Exception:
            continue
        if n not in allowed_articles:
            res.status = "FAIL"
            res.severity = "BLOCKING"
            res.action = "DROP_NARRATIVE"
            res.errors.append(
                CheckError(type="ILLEGAL_ARTICLE", detail=f"TRLC art. {n} no está en articulos_citados del bundle")
            )
        else:
            # comprobar existencia en corpus local
            if not get_trlc_article(n):
                res.status = "FAIL"
                res.severity = "BLOCKING"
                res.action = "DROP_NARRATIVE"
                res.errors.append(
                    CheckError(type="ARTICLE_NOT_IN_CORPUS", detail=f"TRLC art. {n} no existe en corpus local")
                )

    # 3) Fechas (bloqueante si nuevas)
    allowed_dates = _extract_allowed_dates(bundle)
    # ISO
    for m in DATE_ISO_RE.finditer(t):
        iso = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        # FAIL duro: epoch/default o fuera de rango razonable
        try:
            yyyy = int(m.group(1))
            if yyyy < 2000 or yyyy > 2100:
                res.status = "FAIL"
                res.severity = "BLOCKING"
                res.action = "DROP_NARRATIVE"
                res.errors.append(CheckError(type="BAD_DATE_RANGE", detail=f"Fecha fuera de rango razonable: {iso}"))
                continue
        except Exception:
            pass
        if iso not in allowed_dates:
            res.status = "FAIL"
            res.severity = "BLOCKING"
            res.action = "DROP_NARRATIVE"
            res.errors.append(CheckError(type="NEW_DATE", detail=f"Aparece fecha no permitida: {iso}"))
    # DD/MM/YYYY
    for m in DATE_DMY_RE.finditer(t):
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        iso = f"{yyyy}-{mm}-{dd}"
        try:
            y = int(yyyy)
            if y < 2000 or y > 2100:
                res.status = "FAIL"
                res.severity = "BLOCKING"
                res.action = "DROP_NARRATIVE"
                res.errors.append(
                    CheckError(type="BAD_DATE_RANGE", detail=f"Fecha fuera de rango razonable: {dd}/{mm}/{yyyy}")
                )
                continue
        except Exception:
            pass
        if iso not in allowed_dates:
            res.status = "FAIL"
            res.severity = "BLOCKING"
            res.action = "DROP_NARRATIVE"
            res.errors.append(CheckError(type="NEW_DATE", detail=f"Aparece fecha no permitida: {dd}/{mm}/{yyyy}"))

    # 4) Penal/fraude: afirmaciones categóricas (bloqueante) y falta de prudencia (soft)
    if PENAL_ASSERTION_RE.search(t):
        res.status = "FAIL"
        res.severity = "BLOCKING"
        res.action = "DROP_NARRATIVE"
        res.errors.append(
            CheckError(type="PENAL_ASSERTION", detail="Lenguaje penal categórico (delito/fraude afirmado)")
        )
    if PENAL_TERMS_RE.search(t) and not CONDITIONAL_MARKERS_RE.search(t):
        # menciona penal/fraude sin marcadores prudentes
        if res.status != "FAIL":
            res.status = "FAIL"
        if res.severity != "BLOCKING":
            res.severity = "SOFT"
        if res.action == "ACCEPT":
            res.action = "RETRY"
        res.errors.append(
            CheckError(
                type="PENAL_WITHOUT_CONDITIONAL",
                detail="Se mencionan términos sensibles (fraude/delito) sin lenguaje condicional/prudente",
            )
        )

    # 5) Cifras (bloqueante para €/%; soft para otros números)
    allowed_nums = _extract_allowed_numbers(bundle)

    for m in MONEY_RE.finditer(t):
        raw = m.group(1)
        n = _norm_num(raw)
        if n not in allowed_nums:
            res.status = "FAIL"
            res.severity = "BLOCKING"
            res.action = "DROP_NARRATIVE"
            res.errors.append(CheckError(type="NEW_AMOUNT", detail=f"Importe no permitido: {m.group(0).strip()}"))

    for m in PERCENT_RE.finditer(t):
        raw = m.group(1)
        n = _norm_num(raw)
        if n not in allowed_nums:
            res.status = "FAIL"
            res.severity = "BLOCKING"
            res.action = "DROP_NARRATIVE"
            res.errors.append(
                CheckError(type="NEW_PERCENT", detail=f"Porcentaje no permitido: {m.group(0).strip()}")
            )

    # Normalizar estado final
    if res.status == "PASS":
        res.severity = "SOFT"
        res.action = "ACCEPT"
    else:
        # si hay blocking, priorizar DROP
        if any(e.type in ("FORBIDDEN_TECH_WORD", "ILLEGAL_ARTICLE", "ARTICLE_NOT_IN_CORPUS", "NEW_DATE", "NEW_AMOUNT", "NEW_PERCENT", "PENAL_ASSERTION") for e in res.errors):
            res.severity = "BLOCKING"
            res.action = "DROP_NARRATIVE"
        elif res.action == "RETRY":
            res.severity = "SOFT"

    return res

