from __future__ import annotations

import re

# Artículos TRLC: "TRLC art. 245" o "TRLC Artículo 245"
TRLC_ARTICLE_RE = re.compile(r"\bTRLC\s*(?:art\.?|artículo)\s*(\d{1,4})\b", re.IGNORECASE)

# Fechas (dos formatos comunes). Se captura cualquier año de 4 dígitos para poder bloquear epoch/default.
DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DATE_DMY_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")

# Importes: 1.234,56 € | 1234€ | 1234.56 EUR | 1 234,56 euros
MONEY_RE = re.compile(
    r"(?<!\w)(\d[\d\.\,\s]{0,20}\d|\d)(?:\s?(?:€|eur|euros))(?=\W|$)",
    re.IGNORECASE,
)

# Porcentajes: 12% | 12,5 %
PERCENT_RE = re.compile(r"(?<!\w)(\d{1,3}(?:[\,\.]\d{1,4})?)\s?%(?=\W|$)")

# Cualquier número "visible" (para flags suaves)
ANY_NUMBER_RE = re.compile(r"(?<!\w)(\d{1,3}(?:[\,\.]\d{1,4})?|\d{4,})(?!\w)")

# Lenguaje prohibido (en outputs firmables)
FORBIDDEN_TECH_WORDS_RE = re.compile(
    r"\b(ia|inteligencia artificial|llm|rag|embeddings?|modelo|algoritmo|automatizad[oa]|sistema)\b",
    re.IGNORECASE,
)

# Etiquetas internas (no deben aparecer en informe cliente)
INTERNAL_LABELS_RE = re.compile(
    r"\b(SUSPICIOUS_PATTERN|TEMPORAL_INCONSISTENCY|DUPLICATED_DATA|INCONSISTENT_DATA|MISSING_DATA)\b",
    re.IGNORECASE,
)

# Conteos tipo dashboard (no deben aparecer en informe cliente)
DASHBOARD_COUNTS_RE = re.compile(r"\b\d+\s+(indicadores?|alertas?)\b", re.IGNORECASE)

# Penal / fraude (detectar y exigir prudencia)
PENAL_TERMS_RE = re.compile(
    r"\b(delito|penal|fraude|hacienda pública|hacienda publica|tgss|seguridad social)\b",
    re.IGNORECASE,
)

CONDITIONAL_MARKERS_RE = re.compile(
    r"\b(podr(?:ía|ia|ían|ian)|posible|riesgo|indicio|eventual|cabe|podría apreciarse|podrían apreciarse)\b",
    re.IGNORECASE,
)

# Afirmaciones categóricas peligrosas (bloqueante)
PENAL_ASSERTION_RE = re.compile(
    r"\b(es|ha\s+cometido|cometi[oó]|constituye|se\s+ha\s+cometido)\s+(?:un\s+)?(delito|fraude)\b",
    re.IGNORECASE,
)
