"""
Chunker consciente del documento con trazabilidad completa.

REGLA 2: Offsets reales en texto original.
REGLA 3: Estrategias diferenciadas según tipo de documento.
REGLA 4: Section hints controlados (NULL si no se puede inferir).
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Optional

# Import ExtractionMethod del modelo
from app.models.document_chunk import ExtractionMethod


@dataclass
class ChunkWithMetadata:
    """
    Chunk con metadata completa de trazabilidad.

    REGLA 1: Metadata obligatoria.
    """

    content: str
    start_char: int  # Offset real en texto original
    end_char: int  # Offset real en texto original
    extraction_method: ExtractionMethod  # Método de extracción
    content_hash: str  # SHA256 del contenido
    page_start: Optional[int] = None  # Página de inicio (1-indexed)
    page_end: Optional[int] = None  # Página de fin (1-indexed)
    section_hint: Optional[str] = None  # NULL si no se puede inferir
    chunking_strategy: str = "default"
    content_type: Optional[str] = None  # "table" | "text" | "list"


# REGLA 3: Estrategias diferenciadas por tipo de documento
CHUNKING_STRATEGIES = {
    "pdf": {
        "name": "legal_document",
        "max_chars": 3000,
        "overlap": 300,
        "detect_sections": False,
    },
    "docx": {
        "name": "structured_text",
        "max_chars": 3000,
        "overlap": 250,
        "detect_sections": False,
    },
    "txt": {
        "name": "plain_text",
        "max_chars": 3000,
        "overlap": 200,
        "detect_sections": False,
    },
    "doc": {
        "name": "structured_text",
        "max_chars": 3000,
        "overlap": 250,
        "detect_sections": False,
    },
    "excel": {
        "name": "table_structured",
        "max_chars": 5000,
        "overlap": 0,  # Sin overlap en tablas
        "detect_sections": False,
    },
    "xlsx": {
        "name": "table_structured",
        "max_chars": 5000,
        "overlap": 0,
        "detect_sections": False,
    },
    "xls": {
        "name": "table_structured",
        "max_chars": 5000,
        "overlap": 0,
        "detect_sections": False,
    },
    "csv": {
        "name": "table_structured",
        "max_chars": 5000,
        "overlap": 0,  # Sin overlap en tablas
        "detect_sections": False,
    },
    "email": {
        "name": "plain_text",
        "max_chars": 3000,
        "overlap": 150,
        "detect_sections": False,
    },
    "image": {
        "name": "plain_text",
        "max_chars": 3000,
        "overlap": 150,
        "detect_sections": False,
    },
}

# Patrones para detectar encabezados legales (REGLA 4)
LEGAL_SECTION_PATTERNS = [
    r"^\s*(ARTÍCULO|CAPÍTULO|SECCIÓN|TÍTULO)\s+[IVXLCDM\d]+",
    r"^\s*[IVX]+\.\s+[A-ZÁÉÍÓÚÑ]",
    r"^\s*\d+\.\s+[A-ZÁÉÍÓÚÑ]",
    r"^\s*(ANTECEDENTES|HECHOS|FUNDAMENTOS|PETITUM|SUPLICO)",
    r"^\s*(PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO)",
]


def _infer_section_hint(text: str, start_pos: int, full_text: str) -> Optional[str]:
    """
    Infiere section_hint SOLO cuando existe evidencia real.

    REGLA 4: Si no se puede inferir con certeza → NULL.
    PROHIBIDO inventar secciones.
    """
    # Buscar hacia atrás desde start_pos para encontrar el encabezado más cercano
    search_back = max(0, start_pos - 500)  # Buscar hasta 500 chars atrás
    preceding_text = full_text[search_back:start_pos]

    # Buscar el último encabezado antes de este chunk
    lines = preceding_text.split("\n")
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        if not line:
            continue

        # Verificar si coincide con algún patrón legal
        for pattern in LEGAL_SECTION_PATTERNS:
            if re.match(pattern, line, re.IGNORECASE):
                # Encontrado: retornar hasta 100 caracteres del encabezado
                return line[:100]

    # No se pudo inferir con certeza → NULL
    return None


def _get_chunking_strategy(
    tipo_documento: str, text_length: int, content_type: Optional[str] = None
) -> dict[str, Any]:
    """
    Selecciona estrategia de chunking según tipo de documento y contenido.

    REGLA 3: Estrategias diferenciadas y adaptativas.
    """
    # Obtener estrategia base según tipo
    base_strategy = CHUNKING_STRATEGIES.get(
        tipo_documento,
        CHUNKING_STRATEGIES["txt"],  # Default
    )

    strategy = base_strategy.copy()

    # Ajustar según tipo de contenido detectado
    if content_type == "table":
        strategy["max_chars"] = int(strategy["max_chars"] * 1.5)
        strategy["overlap"] = 0  # Sin overlap en tablas
        strategy["name"] += "_table"
    elif content_type == "list":
        strategy["overlap"] = int(strategy["overlap"] * 0.7)
        strategy["name"] += "_list"

    # Ajustar según longitud del documento
    if text_length > 100000:  # Documentos muy largos
        strategy["max_chars"] = int(strategy["max_chars"] * 1.5)
        strategy["overlap"] = int(strategy["overlap"] * 1.2)
        strategy["name"] += "_long"
    elif text_length < 5000:  # Documentos cortos
        strategy["max_chars"] = int(strategy["max_chars"] * 0.7)
        strategy["overlap"] = int(strategy["overlap"] * 0.8)
        strategy["name"] += "_short"

    return strategy


def _determine_extraction_method(tipo_documento: str) -> ExtractionMethod:
    """
    Determina extraction_method desde tipo de documento.

    Retorna UNKNOWN para tipos no mapeables.
    El rechazo de documentos por tipo no mapeable es responsabilidad de ingesta (FASE 3).
    """
    tipo_lower = tipo_documento.lower()

    if tipo_lower == "pdf":
        return ExtractionMethod.PDF_TEXT
    elif tipo_lower in ("docx", "doc", "word"):
        return ExtractionMethod.DOCX_TEXT
    elif tipo_lower == "txt":
        return ExtractionMethod.TXT
    elif tipo_lower in ("email", "eml", "msg"):
        # Emails se tratan como texto plano (no hay páginas)
        return ExtractionMethod.TXT
    elif tipo_lower in ("image", "jpg", "jpeg", "png", "tif", "tiff"):
        # Imágenes: texto proviene de OCR
        return ExtractionMethod.OCR
    elif tipo_lower in ("table", "excel", "xlsx", "xls", "csv"):
        return ExtractionMethod.TABLE
    else:
        # Tipo no mapeable → UNKNOWN (ingesta debe validar antes)
        return ExtractionMethod.UNKNOWN


def _detect_content_type(text: str) -> str:
    """
    Detecta tipo de contenido del texto.

    MEJORA: Metadata enriquecida para optimizar procesamiento.
    Returns: "table" | "list" | "text"
    """
    lines = text.strip().split("\n")[:50]  # Muestra de primeras 50 líneas

    if not lines:
        return "text"

    # Detectar tabla (delimitadores | o \t consistentes)
    tab_count = sum(1 for l in lines if "\t" in l or "|" in l)
    if tab_count > len(lines) * 0.6:
        return "table"

    # Detectar lista (bullets, numeración)
    list_count = sum(1 for l in lines if re.match(r"^\s*[-*•]\s|^\s*\d+[\.\)]\s", l))
    if list_count > len(lines) * 0.5:
        return "list"

    return "text"


def _find_best_split_point(text: str, ideal_pos: int, window: int = 200) -> int:
    """
    Busca mejor punto de corte respetando límites naturales.

    MEJORA: Chunking semántico que respeta párrafos/secciones.
    Prioridad: párrafo > línea > frase > espacio
    """
    # Buscar en ventana alrededor del punto ideal
    start = max(0, ideal_pos - window)
    end = min(len(text), ideal_pos + window)
    search_zone = text[start:end]

    # Prioridad: \n\n (párrafo) > \n (línea) > . (frase) > espacio
    for delimiter, offset in [("\n\n", 2), ("\n", 1), (". ", 2), (" ", 1)]:
        idx = search_zone.rfind(delimiter, 0, ideal_pos - start)
        if idx != -1:
            return start + idx + offset

    return ideal_pos  # Fallback


def _get_semantic_overlap(text: str, chunk_end: int, base_overlap: int) -> int:
    """
    Calcula overlap que preserve frases/párrafos completos.

    MEJORA: Overlap inteligente que respeta límites semánticos.
    """
    start_search = max(0, chunk_end - base_overlap - 100)
    overlap_zone = text[start_search:chunk_end]

    # Buscar inicio de párrafo/frase dentro del overlap
    for marker in ["\n\n", "\n", ". "]:
        idx = overlap_zone.rfind(marker)
        if idx != -1:
            actual_overlap = chunk_end - (start_search + idx + len(marker))
            # Limitar overlap a rango razonable
            if base_overlap * 0.5 <= actual_overlap <= base_overlap * 2:
                return actual_overlap

    return base_overlap  # Fallback


def _calculate_page_range(
    start_char: int, end_char: int, page_mapping: Optional[dict[int, tuple[int, int]]]
) -> tuple[Optional[int], Optional[int]]:
    """
    Calcula page_start y page_end para un chunk.

    FASE 2: Para PDFs (con page_mapping), page_start/page_end son OBLIGATORIOS.

    Returns:
        (page_start, page_end) o (None, None) si no hay mapeo
    """
    if not page_mapping:
        return None, None

    page_start = None
    page_end = None

    for page_num, (page_char_start, page_char_end) in page_mapping.items():
        # Chunk empieza en esta página
        if page_start is None and start_char >= page_char_start and start_char < page_char_end:
            page_start = page_num

        # Chunk termina en esta página
        if end_char > page_char_start and end_char <= page_char_end:
            page_end = page_num
            break

    # Si no se encontró page_end, usar la última página que toca el chunk
    if page_start is not None and page_end is None:
        for page_num, (page_char_start, page_char_end) in page_mapping.items():
            if end_char > page_char_start:
                page_end = page_num

    return page_start, page_end


def chunk_text_with_metadata(
    text: str,
    tipo_documento: str = "txt",
    page_mapping: Optional[dict[int, tuple[int, int]]] = None,
    max_chunks: int = 500,
) -> list[ChunkWithMetadata]:
    """
    Divide texto en chunks con metadata completa de trazabilidad.

    REGLA 2: Offsets reales en texto original.
    REGLA 3: Chunking consciente del documento.
    REGLA 4: Section hints controlados.
    FASE 2: extraction_method, page_start/page_end, content_hash OBLIGATORIOS.

    Args:
        text: Texto original a chunkear
        tipo_documento: Tipo de documento (pdf, docx, txt, etc.)
        page_mapping: Mapeo opcional de {page_num: (start_char, end_char)}
        max_chunks: Límite máximo de chunks (seguridad memoria)

    Returns:
        Lista de ChunkWithMetadata con offsets reales y verificables

    Raises:
        ValueError: Si extraction_method no se puede determinar
        ValueError: Si para PDFs no se pueden calcular páginas
    """
    if not text or not text.strip():
        return []

    # Determinar extraction_method
    extraction_method = _determine_extraction_method(tipo_documento)

    # VALIDACIÓN: Si es PDF y no hay page_mapping → EXCEPCIÓN
    if extraction_method == ExtractionMethod.PDF_TEXT and not page_mapping:
        raise ValueError("PDF sin page_mapping: no se pueden calcular page_start/page_end")

    # Detectar tipo de contenido global para estrategia adaptativa
    global_content_type = _detect_content_type(text)

    # REGLA 3: Seleccionar estrategia según tipo, longitud y contenido
    strategy = _get_chunking_strategy(tipo_documento, len(text), global_content_type)

    max_chars = strategy["max_chars"]
    overlap = strategy["overlap"]
    detect_sections = strategy["detect_sections"]
    strategy_name = strategy["name"]

    chunks: list[ChunkWithMetadata] = []
    start = 0
    length = len(text)

    while start < length:
        # Límite de seguridad para evitar picos de memoria
        if len(chunks) >= max_chunks:
            print(f"[WARN] Alcanzado límite de {max_chunks} chunks, deteniendo")
            break

        end = min(start + max_chars, length)

        # Ajustar a límite semántico natural (no en último chunk)
        if end < length:
            end = _find_best_split_point(text, end)

        # REGLA 2: Offsets reales en texto original
        chunk_content = text[start:end]

        # FASE 2: Calcular content_hash
        content_hash = hashlib.sha256(chunk_content.encode("utf-8")).hexdigest()

        # REGLA 4: Inferir section_hint SOLO si hay evidencia
        section_hint = None
        if detect_sections:
            section_hint = _infer_section_hint(chunk_content, start, text)

        # Calcular page_start y page_end
        page_start, page_end = _calculate_page_range(start, end, page_mapping)

        # VALIDACIÓN: Si es PDF y no hay páginas → EXCEPCIÓN
        if extraction_method == ExtractionMethod.PDF_TEXT:
            if page_start is None or page_end is None:
                raise ValueError(
                    f"Chunk de PDF sin páginas: "
                    f"start={start}, end={end}, page_start={page_start}, page_end={page_end}"
                )

        # Detectar tipo de contenido específico del chunk
        chunk_content_type = _detect_content_type(chunk_content)

        # Crear chunk con metadata completa
        chunks.append(
            ChunkWithMetadata(
                content=chunk_content,
                start_char=start,
                end_char=end,
                extraction_method=extraction_method,
                content_hash=content_hash,
                page_start=page_start,
                page_end=page_end,
                section_hint=section_hint,
                chunking_strategy=strategy_name,
                content_type=chunk_content_type,
            )
        )

        # Avanzar con overlap semántico
        start = end - _get_semantic_overlap(text, end, overlap)

        # Si ya alcanzamos el final, terminar
        if end >= length:
            break

        # Si el overlap nos dejó más allá del final, terminar
        if start >= length:
            break

    return chunks


# ELIMINADO: Función legacy chunk_text() - NO se debe usar
# El pipeline DEBE usar chunk_text_with_metadata() siempre.
# Si existe código que llama a chunk_text(), debe migrar a chunk_text_with_metadata().
