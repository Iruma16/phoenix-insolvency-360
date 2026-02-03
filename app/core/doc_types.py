"""
Catálogo de tipos documentales (abogado-friendly) + clasificación determinista.

Objetivo:
- Persistir `Document.doc_type` dentro de un catálogo útil para un concursalista.
- Clasificar con reglas (keywords + prioridades) SIN inventar: si no hay señal suficiente → OTRO.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional

# =========================================================
# CATÁLOGO (ESTRATEGIA B: `documents.doc_type` usa estos valores)
# =========================================================

DOC_TYPES: tuple[str, ...] = (
    # Núcleo legal / concursal
    "ESCRITURA_CONSTITUCION",
    "PODERES_REPRESENTACION",
    "CONTRATO_ARRENDAMIENTO",
    "CONTRATO_FINANCIACION",
    "GARANTIAS",
    "COMUNICACION_ACREEDOR",
    "RECLAMACION_JUDICIAL",
    "RESOLUCION_JUDICIAL",
    "EMBARGO",
    "CONCURSAL",
    # Deuda pública
    "AEAT",
    "TGSS",
    "MODELOS_TRIBUTARIOS",
    "APLAZAMIENTO_FRACCIONAMIENTO",
    "PROVIDENCIA_APREMIO",
    # Económico-financiero
    "FACTURA",
    "EXTRACTO_BANCARIO",
    "CUENTA_BANCARIA",
    "BALANCE",
    "PYG",
    "MAYOR_CONTABLE",
    "NOMINAS_SEGUROS_SOCIALES",
    # Activos / patrimonio
    "INMUEBLE",
    "VEHICULO",
    "MAQUINARIA_EQUIPO",
    "TASACION",
    # Otros útiles
    "CORREO",
    "OTRO",
)

DOC_TYPES_SET = set(DOC_TYPES)


# =========================================================
# UI: categorías abogado-friendly → doc_types
# =========================================================

UI_CATEGORIES: dict[str, list[str]] = {
    "JUZGADO": ["RECLAMACION_JUDICIAL", "RESOLUCION_JUDICIAL", "EMBARGO"],
    "FACTURAS": ["FACTURA"],
    "BANCOS": ["EXTRACTO_BANCARIO", "CUENTA_BANCARIA"],
    "AEAT": ["AEAT", "MODELOS_TRIBUTARIOS", "APLAZAMIENTO_FRACCIONAMIENTO", "PROVIDENCIA_APREMIO"],
    "TGSS": ["TGSS", "APLAZAMIENTO_FRACCIONAMIENTO", "PROVIDENCIA_APREMIO"],
    "CONTABILIDAD": ["BALANCE", "PYG", "MAYOR_CONTABLE"],
    "ACTIVOS": ["INMUEBLE", "VEHICULO", "MAQUINARIA_EQUIPO", "TASACION", "GARANTIAS"],
    "CONCURSAL": ["CONCURSAL"],
    "OTROS": ["CORREO", "OTRO", "COMUNICACION_ACREEDOR"],
}


# =========================================================
# Clasificación: reglas + prioridades
# =========================================================


@dataclass(frozen=True)
class DocTypeInference:
    doc_type: str
    confidence: float  # 0..1
    best_score: float
    second_score: float


def _strip_accents(s: str) -> str:
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _normalize(s: str) -> str:
    s = (s or "").strip().lower()
    s = _strip_accents(s)
    s = s.replace("\n", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(n in text for n in needles)


# Keywords prácticas (MVP): cada match suma 1; algunas frases suman 2.
# Nota: se aplica sobre texto normalizado (lower + sin acentos).
DOC_TYPE_RULES: dict[str, list[str]] = {
    "ESCRITURA_CONSTITUCION": [
        "escritura de constitucion",
        "constitucion sociedad",
        "registro mercantil",
        "notario",
        "protocolo",
    ],
    "PODERES_REPRESENTACION": [
        "poder",
        "apoderamiento",
        "representacion",
        "facultades",
        "notario",
    ],
    "CONTRATO_ARRENDAMIENTO": [
        "contrato arrendamiento",
        "arrendatario",
        "arrendador",
        "renta mensual",
        "fianza",
    ],
    "CONTRATO_FINANCIACION": [
        "poliza",
        "prestamo",
        "credito",
        "leasing",
        "renting",
        "cuadro de amortizacion",
        "interes",
        "carencia",
    ],
    "GARANTIAS": [
        "hipoteca",
        "prenda",
        "aval",
        "fianza",
        "garantia",
    ],
    "COMUNICACION_ACREEDOR": [
        "burofax",
        "requerimiento",
        "reclamacion",
        "recordatorio de pago",
        "impago",
    ],
    "AEAT": [
        "agencia tributaria",
        "aeat",
        "hacienda",
        "iva",
        "irpf",
        "delegacion de hacienda",
    ],
    "MODELOS_TRIBUTARIOS": [
        "modelo 303",
        "modelo 111",
        "modelo 190",
        "modelo 200",
        "modelo 390",
        "modelo 347",
    ],
    "TGSS": [
        "tgss",
        "seguridad social",
        "tesoreria general",
        "liquidacion de cuotas",
        "rnt",
        "rc",
    ],
    "APLAZAMIENTO_FRACCIONAMIENTO": [
        "aplazamiento",
        "fraccionamiento",
        "concesion",
        "denegacion",
        "resolucion de aplazamiento",
    ],
    "PROVIDENCIA_APREMIO": [
        "providencia de apremio",
        "apremio",
        "recaudacion ejecutiva",
    ],
    "EMBARGO": [
        "embargo",
        "diligencia de embargo",
        "traba",
        "orden de embargo",
    ],
    "RECLAMACION_JUDICIAL": [
        "demanda",
        "monitorio",
        "ejecucion",
        "reclamacion de cantidad",
        "procedimiento",
    ],
    "RESOLUCION_JUDICIAL": [
        "sentencia",
        "auto",
        "decreto",
        "diligencia",
        "providencia",
        "juzgado",
        "autos",
    ],
    "CONCURSAL": [
        "concurso",
        "administracion concursal",
        "lista de acreedores",
        "informe de la administracion concursal",
        "masa activa",
        "masa pasiva",
    ],
    "FACTURA": [
        "factura",
        "invoice",
        "base imponible",
        "tipo iva",
        "total factura",
    ],
    "EXTRACTO_BANCARIO": [
        "extracto",
        "movimientos",
        "saldo",
        "iban",
        "banco",
        "entidad",
        "fecha valor",
    ],
    "CUENTA_BANCARIA": [
        "certificado de saldo",
        "certificado bancario",
        "titular",
        "iban",
    ],
    "BALANCE": [
        "balance",
        "activo",
        "pasivo",
        "patrimonio neto",
        "situacion",
    ],
    "PYG": [
        "perdidas y ganancias",
        "cuenta de resultados",
        "resultado del ejercicio",
        "p&g",
    ],
    "MAYOR_CONTABLE": [
        "mayor",
        "asiento",
        "contabilidad",
        "subcuenta",
        "sumas y saldos",
    ],
    "NOMINAS_SEGUROS_SOCIALES": [
        "nomina",
        "recibo de salarios",
        "seguro social",
        "seguros sociales",
        "tc",
        "cotizacion",
    ],
    "INMUEBLE": [
        "nota simple",
        "inmueble",
        "catastro",
        "ibi",
        "finca registral",
        "registro de la propiedad",
    ],
    "VEHICULO": [
        "matricula",
        "permiso de circulacion",
        "itv",
        "vehiculo",
    ],
    "MAQUINARIA_EQUIPO": [
        "maquinaria",
        "equipo",
        "activo fijo",
        "inmovilizado",
    ],
    "TASACION": [
        "tasacion",
        "valoracion",
        "perito",
        "informe pericial",
    ],
    "CORREO": [
        ".eml",
        ".msg",
        "email",
        "correo",
        "re:",
        "fw:",
        "from:",
        "to:",
        "subject:",
        "asunto:",
    ],
}


def infer_doc_type(
    *,
    filename: str,
    title: Optional[str] = None,
    source: Optional[str] = None,
    raw_text_preview: Optional[str] = None,
) -> DocTypeInference:
    """
    Inferencia determinista de doc_type.

    Regla de oro: si la señal es débil → OTRO.
    """

    filename_n = _normalize(filename or "")
    haystack = " ".join(
        [filename or "", title or "", source or "", (raw_text_preview or "")[:4000]]
    )
    text = _normalize(haystack)

    # -----------------------------------------
    # Prioridades duras (evitar errores típicos)
    # -----------------------------------------

    # 1) AEAT/TGSS mandan
    if _contains_any(text, [" aeat", "agencia tributaria", "hacienda"]):
        return DocTypeInference(doc_type="AEAT", confidence=0.95, best_score=10.0, second_score=0.0)
    if _contains_any(text, [" tgss", "seguridad social", "tesoreria general"]):
        return DocTypeInference(doc_type="TGSS", confidence=0.95, best_score=10.0, second_score=0.0)

    # 2) Providencia de apremio (muy específica)
    if "providencia" in text and "apremio" in text:
        return DocTypeInference(
            doc_type="PROVIDENCIA_APREMIO", confidence=0.95, best_score=9.0, second_score=0.0
        )

    # 3) Judicial: reclamación vs resolución
    if _contains_any(text, ["demanda", "monitorio", "ejecucion"]):
        return DocTypeInference(
            doc_type="RECLAMACION_JUDICIAL", confidence=0.9, best_score=8.0, second_score=0.0
        )
    if _contains_any(text, ["sentencia", "auto", "decreto", "diligencia"]) and _contains_any(
        text, ["juzgado", "procedimiento", "autos"]
    ):
        return DocTypeInference(
            doc_type="RESOLUCION_JUDICIAL", confidence=0.9, best_score=8.0, second_score=0.0
        )

    # 4) Embargo (si no es AEAT/TGSS)
    if _contains_any(text, ["embargo", "diligencia de embargo", "traba"]):
        return DocTypeInference(
            doc_type="EMBARGO", confidence=0.85, best_score=7.0, second_score=0.0
        )

    # 5) Extracto bancario manda sobre factura si hay señales de banco
    if _contains_any(text, ["extracto", "iban", "saldo", "movimientos", "fecha valor"]):
        return DocTypeInference(
            doc_type="EXTRACTO_BANCARIO", confidence=0.8, best_score=6.0, second_score=0.0
        )

    # -----------------------------------------
    # Scoring general
    # -----------------------------------------
    scores: dict[str, float] = {k: 0.0 for k in DOC_TYPE_RULES.keys()}
    for doc_type, keywords in DOC_TYPE_RULES.items():
        for kw in keywords:
            kw_n = _normalize(kw)
            if kw_n and kw_n in text:
                # Frases largas pesan más (reduce falsos positivos)
                weight = 2.0 if len(kw_n.split()) >= 2 else 1.0
                # En filename, un match simple suele ser muy informativo
                if kw_n in filename_n:
                    weight = max(weight, 2.0)
                scores[doc_type] += weight

    # Mejor y segundo mejor
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_type, best = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0

    # Umbral conservador
    if best < 2.0:
        return DocTypeInference(
            doc_type="OTRO", confidence=0.0, best_score=best, second_score=second
        )

    # Confianza (0..1) basada en separación de scores
    confidence = (best / (best + second + 1e-6)) if best > 0 else 0.0
    confidence = max(0.0, min(1.0, float(confidence)))

    if confidence < 0.55:
        return DocTypeInference(
            doc_type="OTRO", confidence=confidence, best_score=best, second_score=second
        )

    # Normalizar a catálogo
    if best_type not in DOC_TYPES_SET:
        return DocTypeInference(
            doc_type="OTRO", confidence=0.0, best_score=best, second_score=second
        )

    return DocTypeInference(
        doc_type=best_type, confidence=confidence, best_score=best, second_score=second
    )


def expand_category_to_doc_types(category: Optional[str]) -> Optional[list[str]]:
    if not category:
        return None
    key = (category or "").strip().upper()
    return UI_CATEGORIES.get(key)
