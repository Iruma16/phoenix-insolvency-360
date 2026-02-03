"""
Extractor determinista de artículos/extractos del TRLC desde el corpus local.

Objetivo:
- Citar párrafos exactos (extractos literales) SIN depender de RAG/LLM.
- Evitar "inventar" artículos o contenido: si no se encuentra un artículo, devolver None.

Fuente:
- `clients_data/legal/ley_concursal/documents/ley_concursal_boe_consolidado_trlc_YYYYMMDD.txt`

Nota:
El TXT proviene de BOE (consolidado). Incluye cabecera/menús, pero el cuerpo contiene
líneas de "Artículo X." que permiten segmentación robusta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

_ARTICLE_RE = re.compile(r"^Artículo\s+(?P<num>\d+)\.\s*(?P<title>.*)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class TrlcArticle:
    number: int
    title: str
    text: str


def _repo_root() -> Path:
    # app/legal/trlc_corpus.py -> parents[2] = repo root
    # (…/202512_phoenix-legal/app/legal/trlc_corpus.py)
    return Path(__file__).resolve().parents[2]


def _pick_latest_trlc_txt() -> Path:
    docs_dir = _repo_root() / "clients_data" / "legal" / "ley_concursal" / "documents"
    candidates = sorted(docs_dir.glob("ley_concursal_boe_consolidado_trlc_*.txt"))
    if not candidates:
        # fallback a cualquier consolidado disponible
        any_txt = sorted(docs_dir.glob("ley_concursal_boe_consolidado_*.txt"))
        if not any_txt:
            raise FileNotFoundError(f"No se encontró corpus TRLC en {docs_dir}")
        return any_txt[-1]
    return candidates[-1]


@lru_cache(maxsize=1)
def _load_trlc_lines() -> list[str]:
    path = _pick_latest_trlc_txt()
    raw = path.read_text(encoding="utf-8", errors="ignore")
    # Normalizar saltos para indexar por línea
    return raw.splitlines()


@lru_cache(maxsize=1)
def _index_articles() -> list[tuple[int, str, int]]:
    """
    Retorna lista de (article_number, title, start_line_idx) ordenada por aparición.
    """
    lines = _load_trlc_lines()
    idx: list[tuple[int, str, int]] = []
    for i, line in enumerate(lines):
        m = _ARTICLE_RE.match(line.strip())
        if not m:
            continue
        try:
            n = int(m.group("num"))
        except Exception:
            continue
        title = (m.group("title") or "").strip()
        idx.append((n, title, i))
    return idx


def get_trlc_article(article_number: int, *, max_chars: int = 1200) -> Optional[TrlcArticle]:
    """
    Devuelve un artículo del TRLC con un extracto literal (hasta max_chars).

    Args:
        article_number: Número de artículo (ej: 245)
        max_chars: Recorte máximo del texto del artículo (para PDF)
    """
    if article_number <= 0:
        return None

    lines = _load_trlc_lines()
    idx = _index_articles()

    positions = [p for p in idx if p[0] == article_number]
    if not positions:
        return None

    # Si hay duplicados (raro), escoger el que tenga título más informativo (con punto)
    number, title, start = sorted(positions, key=lambda x: (len(x[1]) == 0, -len(x[1])))[0]

    # buscar siguiente artículo posterior para delimitar
    next_start = None
    for n2, _t2, s2 in idx:
        if s2 > start:
            next_start = s2
            break
    end = next_start if next_start is not None else len(lines)

    # Construir texto literal del bloque (limpiar líneas vacías múltiples)
    block_lines = [ln.rstrip() for ln in lines[start:end]]
    # recortar encabezados de navegación si por alguna razón entran (defensivo)
    block_lines = [
        ln for ln in block_lines if ln.strip() != "" or (block_lines and ln.strip() == "")
    ]

    text = "\n".join(block_lines).strip()
    if max_chars and len(text) > max_chars:
        text = text[: max_chars - 40].rstrip() + "\n…[extracto truncado]"

    return TrlcArticle(number=number, title=title, text=text)


def get_trlc_excerpt_for_keywords(keywords: list[str], *, max_chars: int = 1200) -> Optional[str]:
    """
    Búsqueda simple por palabras clave dentro del corpus (extracto literal alrededor del match).

    Uso: cuando no sabemos el artículo exacto, pero queremos citar un fragmento literal.
    """
    if not keywords:
        return None
    kws = [k.lower().strip() for k in keywords if k and k.strip()]
    if not kws:
        return None

    lines = _load_trlc_lines()
    joined = "\n".join(lines)
    low = joined.lower()

    # Encontrar primera coincidencia de TODOS los keywords (en cualquier orden)
    first_pos = None
    for k in kws:
        p = low.find(k)
        if p < 0:
            return None
        first_pos = p if first_pos is None else min(first_pos, p)

    if first_pos is None:
        return None

    start = max(0, first_pos - 500)
    end = min(len(joined), first_pos + 700)
    excerpt = joined[start:end].strip()
    if len(excerpt) > max_chars:
        excerpt = excerpt[: max_chars - 40].rstrip() + "\n…[extracto truncado]"
    return excerpt
