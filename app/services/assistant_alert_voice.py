"""
FASE 3 — Voz del asistente (alertas) — Phoenix Legal

Objetivo:
- Generar texto humano (estilo despacho) a partir de señales objetivas (findings + evidences + checklist).
- Sin LLM, determinista, con guardarraíles de lenguaje (anti-robot y anti-conclusiones).

Importante:
- Este módulo NO modifica `AnalysisAlert.description` (que es técnico).
- Este módulo NO crea endpoints, tablas ni UI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional


class AlertDomain(str, Enum):
    TGSS = "TGSS"
    BANCO = "BANCO"
    CONTABILIDAD = "CONTABILIDAD"
    VINCULADAS = "VINCULADAS"
    DOCS = "DOCS"


class Relevance(str, Enum):
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAJA = "BAJA"


@dataclass(frozen=True)
class EvidenceRef:
    filename: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    snippet: str = ""


@dataclass(frozen=True)
class VoiceInput:
    domain: AlertDomain
    findings: list[str]
    evidences: list[EvidenceRef]
    to_clarify: list[str]
    temporal_window_note: Optional[str] = None
    relevance: Optional[Relevance] = None


@dataclass(frozen=True)
class VoiceOutput:
    title_human: str
    summary_human: str
    to_clarify: list[str]
    disclaimer_detail: str


# =========================================================
# Guardarraíles de lenguaje (hard rules)
# =========================================================


_BANNED_TERMS = [
    # intención / culpabilidad / penal (prohibido)
    "intención",
    "intencion",
    "dolo",
    "fraude cometido",
    "se demuestra",
    "demuestra que",
    "culpable",
    "inocente",
    "delito",
    "crimen",
    "culpabilidad",
    "responsabilidad penal",
    "condena",
]

# Anti-robot (prohibido)
_BANNED_ROBOT_PHRASES = [
    "se detecta",
    "el sistema ha identificado",
    "el sistema ha detectado",
    "existe indicio de",
    "se ha identificado",
]

# Preferidas (para reescritura o como guía)
_PREFERRED_STARTERS = [
    "Revisando la documentación,",
    "Por fechas e importes,",
    "No está claro si es un error o otra cosa, pero",
    "Esto no es concluyente por sí solo, pero",
    "Conviene aclarar",
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def find_language_violations(text: str) -> list[str]:
    """
    Devuelve lista de violaciones encontradas (strings descriptivos).
    """
    violations: list[str] = []
    t = _norm(text)

    for term in _BANNED_TERMS:
        if _norm(term) in t:
            violations.append(f"término prohibido: '{term}'")

    for phrase in _BANNED_ROBOT_PHRASES:
        if _norm(phrase) in t:
            violations.append(f"frase robótica prohibida: '{phrase}'")

    return violations


def sanitize_language(text: str, *, strict: bool = True) -> str:
    """
    Guardarraíl configurable:
    - strict=True: lanza ValueError si hay violaciones.
    - strict=False: intenta reescribir de forma conservadora.
    """
    violations = find_language_violations(text)
    if not violations:
        return text

    if strict:
        raise ValueError("Violación de guardarraíl de lenguaje: " + "; ".join(violations))

    # Reescrituras mínimas (no creativas): sustituir frases robóticas por fórmulas de despacho.
    out = text
    rewrites = [
        (r"\bSe detecta\b", "Revisando la documentación, aparece"),
        (r"\bse detecta\b", "revisando la documentación, aparece"),
        (r"el sistema ha identificado", "revisando la documentación, aparece"),
        (r"el sistema ha detectado", "revisando la documentación, aparece"),
        (r"existe indicio de", "no está claro si, pero llama la atención que"),
        (r"se ha identificado", "revisando la documentación, aparece"),
    ]
    for pat, rep in rewrites:
        out = re.sub(pat, rep, out, flags=re.IGNORECASE)

    # Borrado conservador de términos legales “duros”
    for term in _BANNED_TERMS:
        out = re.sub(re.escape(term), "punto a revisar", out, flags=re.IGNORECASE)

    # Si aún hay violaciones, en modo no estricto dejamos el texto igualmente,
    # pero intentamos que al menos no contenga frases robóticas.
    return out


def _ensure_max_3_paragraphs(text: str) -> str:
    # Normalizar separadores
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(parts) <= 3:
        return "\n\n".join(parts)
    # Compactar: unir exceso en el 3er párrafo
    head = parts[:2]
    tail = " ".join(parts[2:])
    return "\n\n".join([*head, tail])


def _ensure_max_length(text: str, *, max_chars: int = 900) -> str:
    """
    Limita longitud del cuerpo para mantener lectura rápida en UI.

    Regla:
    - Mantener la estructura de párrafos (máx 3) ya normalizada.
    - Preservar el último párrafo (incluye 'yo revisaría…') en la medida de lo posible.
    """
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t

    parts = [p.strip() for p in t.split("\n\n") if p.strip()]
    if not parts:
        return _shorten(t, max_chars)

    last = parts[-1]
    head = parts[:-1]

    # Reservar espacio para el cierre (último párrafo) si cabe.
    reserved = min(len(last) + 2, max_chars)
    remaining = max_chars - reserved

    if remaining <= 0:
        # Caso extremo: recortar solo el último, pero conservar “yo revisaría” si está.
        if "yo revisaría" in last.lower():
            prefix = "Para tenerlo bien atado, yo revisaría: "
            return _shorten(prefix + _shorten(last, max(0, max_chars - len(prefix))), max_chars)
        return _shorten(last, max_chars)

    # Recortar head para que quepa + mantener last completo.
    if head:
        head_join = "\n\n".join(head)
        head_trim = _shorten(head_join, remaining)
        out = (head_trim + "\n\n" + last).strip()
        return out if len(out) <= max_chars else _shorten(out, max_chars)

    # Sin head, solo recortar last
    return _shorten(last, max_chars)


def _render_doc_hint(ev: EvidenceRef) -> str:
    fn = (ev.filename or "").strip() or "un documento"
    if ev.page_start is not None:
        if ev.page_end and ev.page_end != ev.page_start:
            return f"`{fn}` (pág. {ev.page_start}-{ev.page_end})"
        return f"`{fn}` (pág. {ev.page_start})"
    return f"`{fn}`"


def _shorten(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


def _choose_tone(relevance: Optional[Relevance]) -> dict[str, str]:
    """
    Devuelve piezas de tono según relevancia humana (ALTA/MEDIA/BAJA).
    """
    if relevance == Relevance.ALTA:
        return {
            "title_prefix": "Ojo con",
            "body_hint": "Conviene revisar esto con cuidado.",
        }
    if relevance == Relevance.BAJA:
        return {
            "title_prefix": "Detalle a tener en cuenta:",
            "body_hint": "Probablemente sea algo menor, pero conviene tenerlo ordenado.",
        }
    # MEDIA por defecto
    return {
        "title_prefix": "Esto llama la atención en",
        "body_hint": "Conviene mirarlo con calma y dejarlo bien explicado.",
    }


# =========================================================
# Plantillas por dominio (3.1) + generador (3.2)
# =========================================================


def generate_voice(
    payload: VoiceInput,
    *,
    strict_language: bool = True,
) -> VoiceOutput:
    """
    Genera title_human + summary_human + disclaimer (para desplegable).
    Determinista: no usa hora, aleatoriedad ni IO.
    """
    # Reordenar checklist: primero lo que suena “bloqueante”
    to_clarify = _reorder_checklist(payload.to_clarify)

    tone = _choose_tone(payload.relevance)
    title = _build_title(payload, tone=tone)
    summary = _build_summary(payload, tone=tone, to_clarify=to_clarify)

    # Guardarraíles
    # Hardening: si el input técnico trae fórmulas tipo "se detecta" (o si el template las arrastra),
    # no queremos tumbar la generación de alertas. En modo estricto, hacemos una reescritura mínima
    # (no creativa) y revalidamos.
    try:
        title = sanitize_language(title, strict=strict_language)
        summary = sanitize_language(summary, strict=strict_language)
    except ValueError:
        title = sanitize_language(title, strict=False)
        summary = sanitize_language(summary, strict=False)
        # Revalidar con strict para evitar colar términos prohibidos duros.
        title = sanitize_language(title, strict=True)
        summary = sanitize_language(summary, strict=True)
    summary = _ensure_max_3_paragraphs(summary)
    summary = _ensure_max_length(summary, max_chars=900)

    # Disclaimer para “detalle”
    disclaimer = (
        "Nota: esto se apoya en hechos objetivos y patrones habituales de revisión de expediente. "
        "La valoración jurídica corresponde al abogado."
    )

    return VoiceOutput(
        title_human=title,
        summary_human=summary,
        to_clarify=to_clarify,
        disclaimer_detail=disclaimer,
    )


def _reorder_checklist(items: list[str]) -> list[str]:
    """
    Heurística simple: subir arriba lo “bloqueante” (certificados, RNT/RLC, conciliación, contrato).
    """
    if not items:
        return []
    scored = []
    for it in items:
        t = _norm(it)
        score = 0
        if any(k in t for k in ["certificado", "rnt", "rlc", "conciliacion", "conciliación"]):
            score += 3
        if any(k in t for k in ["contrato", "soporte", "justificante"]):
            score += 2
        if any(k in t for k in ["extracto", "bancari"]):
            score += 1
        scored.append((score, it.strip()))
    scored.sort(key=lambda x: x[0], reverse=True)
    # dedup conservador
    out: list[str] = []
    seen = set()
    for _, it in scored:
        key = _norm(it)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out[:8]  # mantenerlo usable


def _build_title(payload: VoiceInput, *, tone: dict[str, str]) -> str:
    d = payload.domain
    prefix = tone["title_prefix"]
    if d == AlertDomain.TGSS:
        return f"{prefix} TGSS (apremio/periodos)"
    if d == AlertDomain.BANCO:
        return f"{prefix} movimientos bancarios"
    if d == AlertDomain.CONTABILIDAD:
        return f"{prefix} contabilidad (pagos/IVA/duplicados)"
    if d == AlertDomain.VINCULADAS:
        return f"{prefix} operaciones con vinculadas"
    return f"{prefix} documentación del expediente"


def _build_summary(payload: VoiceInput, *, tone: dict[str, str], to_clarify: list[str]) -> str:
    """
    2–3 párrafos:
    - contexto + hecho objetivo (con 1 evidencia referenciada)
    - qué llama la atención + matiz prudente (+ ventana temporal si aplica)
    - cierre “yo revisaría…” + 2–4 items checklist
    """
    ev0 = payload.evidences[0] if payload.evidences else None
    doc_hint = _render_doc_hint(ev0) if ev0 else "la documentación aportada"

    # Findings: convertir lista a frase humana objetiva (sin tecnicismos)
    facts = "; ".join([_shorten(f, 160) for f in (payload.findings or []) if f.strip()])
    facts = facts or "aparece un punto que conviene revisar con más detalle."

    p1 = (
        f"Revisando la documentación, en {doc_hint} {facts} "
        f"{tone['body_hint']}"
    )

    # Matiz prudente (obligatorio)
    matiz = "Esto no es concluyente por sí solo, pero es de esos puntos que suele pedir una explicación bien documentada."

    window = ""
    if payload.temporal_window_note:
        window = f" {payload.temporal_window_note.strip()}"

    # Señalar “qué llama la atención” por dominio, sin acusar
    if payload.domain == AlertDomain.TGSS:
        attention = "Lo que llama la atención es el encaje por fechas/periodos y la falta de soporte asociado si no está en el expediente."
    elif payload.domain == AlertDomain.BANCO:
        attention = "Por conceptos y repetición, sería bueno aclarar el soporte de estos movimientos."
    elif payload.domain == AlertDomain.CONTABILIDAD:
        attention = "Parece más un tema de gestión/registro, pero conviene cuadrarlo para que no contamine el análisis."
    elif payload.domain == AlertDomain.VINCULADAS:
        attention = "En estos casos, lo importante es dejar claro qué se prestó y con qué entregables, para evitar dudas posteriores."
    else:
        attention = "No está claro si es una ausencia real o un tema de archivo, pero conviene dejarlo atado."

    p2 = f"{attention}{window} {matiz}"

    # Cierre con “yo revisaría…” (obligatorio)
    if to_clarify:
        items = to_clarify[:4]
        checklist_inline = "; ".join([_shorten(i, 120) for i in items])
        p3 = f"Para tenerlo bien atado, yo revisaría: {checklist_inline}."
    else:
        p3 = "Para tenerlo bien atado, yo revisaría la evidencia y completaría el soporte que falte en el expediente."

    return "\n\n".join([p1, p2, p3])


# =========================================================
# Helpers opcionales para validación manual (sin tests)
# =========================================================


def demo_payloads_from_dataset() -> list[VoiceInput]:
    """
    Construye 4 payloads de ejemplo (TGSS/BANCO/CONTABILIDAD/VINCULADAS)
    usando nombres del dataset sintético (sin leer archivos).
    """
    return [
        VoiceInput(
            domain=AlertDomain.TGSS,
            findings=[
                "aparece una providencia de apremio con periodos 2023-01 a 2023-08 e importe principal aproximado",
            ],
            evidences=[
                EvidenceRef(
                    filename="TGSS_Providencia_Apremio_Exp123.pdf",
                    page_start=1,
                    page_end=1,
                    snippet="Providencia de apremio … Importe principal reclamado … Periodo reclamado …",
                )
            ],
            to_clarify=[
                "RNT/RLC de los meses afectados",
                "Certificado TGSS actualizado",
                "Conciliación bancaria completa del periodo",
            ],
            temporal_window_note=None,
            relevance=Relevance.ALTA,
        ),
        VoiceInput(
            domain=AlertDomain.BANCO,
            findings=[
                "hay transferencias recurrentes a GRUPO XYZ SL con concepto genérico 'Servicios' y una retirada de efectivo",
            ],
            evidences=[
                EvidenceRef(
                    filename="Extracto_Bancario_Sep2023.pdf",
                    page_start=1,
                    page_end=2,
                    snippet="… Transferencia … GRUPO XYZ SL … Servicios … Reintegro cajero …",
                )
            ],
            to_clarify=[
                "Contrato o soporte de esos 'servicios'",
                "Conciliación bancaria del mes",
                "Detalle de contrapartes y entregables",
            ],
            temporal_window_note="Por fechas e importes, merece la pena cruzarlo con el hito TGSS si aplica.",
            relevance=Relevance.MEDIA,
        ),
        VoiceInput(
            domain=AlertDomain.CONTABILIDAD,
            findings=[
                "una factura parece pagada parcialmente (importe pagado distinto del total) y hay apuntes de IVA a revisar",
            ],
            evidences=[
                EvidenceRef(
                    filename="Factura_FA-2023-077_PROV_ALPHA.pdf",
                    page_start=1,
                    page_end=1,
                    snippet="TOTAL: 5.445,00 €",
                ),
                EvidenceRef(
                    filename="Justificante_Pago_FA-2023-077.pdf",
                    page_start=1,
                    page_end=1,
                    snippet="Importe pagado: 4.500,00 €",
                ),
            ],
            to_clarify=[
                "Conciliar la factura con el justificante y el extracto bancario",
                "Revisar tratamiento del IVA (soporte y asiento)",
                "Confirmar si hay rectificativa o pago posterior",
            ],
            temporal_window_note=None,
            relevance=Relevance.MEDIA,
        ),
        VoiceInput(
            domain=AlertDomain.VINCULADAS,
            findings=[
                "hay un contrato de servicios con entregables poco concretos y pagos asociados con concepto genérico",
            ],
            evidences=[
                EvidenceRef(
                    filename="Contrato_Servicios_GrupoXYZ_2023-08-25.docx",
                    page_start=None,
                    page_end=None,
                    snippet="Entregables: no se detallan entregables concretos. Se indica 'soporte general'.",
                )
            ],
            to_clarify=[
                "Soporte/entregables de los servicios prestados",
                "Criterio de precios y relación con el grupo",
                "Conciliación bancaria de los pagos",
            ],
            temporal_window_note=None,
            relevance=Relevance.MEDIA,
        ),
    ]

