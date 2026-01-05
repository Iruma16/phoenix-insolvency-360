"""
Chunker consciente del documento con trazabilidad completa.

REGLA 2: Offsets reales en texto original.
REGLA 3: Estrategias diferenciadas según tipo de documento.
REGLA 4: Section hints controlados (NULL si no se puede inferir).
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import re


@dataclass
class ChunkWithMetadata:
    """
    Chunk con metadata completa de trazabilidad.
    
    REGLA 1: Metadata obligatoria.
    """
    content: str
    start_char: int  # Offset real en texto original
    end_char: int    # Offset real en texto original
    page: Optional[int] = None  # NULL si no aplica
    section_hint: Optional[str] = None  # NULL si no se puede inferir
    chunking_strategy: str = "default"


# REGLA 3: Estrategias diferenciadas por tipo de documento
CHUNKING_STRATEGIES = {
    "pdf": {
        "name": "legal_document",
        "max_chars": 2000,
        "overlap": 300,
        "detect_sections": True,
    },
    "docx": {
        "name": "structured_text",
        "max_chars": 1500,
        "overlap": 250,
        "detect_sections": True,
    },
    "txt": {
        "name": "plain_text",
        "max_chars": 1000,
        "overlap": 200,
        "detect_sections": False,
    },
    "doc": {
        "name": "structured_text",
        "max_chars": 1500,
        "overlap": 250,
        "detect_sections": True,
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
    lines = preceding_text.split('\n')
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


def _get_chunking_strategy(tipo_documento: str, text_length: int) -> Dict[str, Any]:
    """
    Selecciona estrategia de chunking según tipo de documento.
    
    REGLA 3: Estrategias diferenciadas.
    """
    # Obtener estrategia base según tipo
    base_strategy = CHUNKING_STRATEGIES.get(
        tipo_documento,
        CHUNKING_STRATEGIES["txt"]  # Default
    )
    
    strategy = base_strategy.copy()
    
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


def chunk_text_with_metadata(
    text: str,
    tipo_documento: str = "txt",
    page_mapping: Optional[Dict[int, tuple[int, int]]] = None,
) -> List[ChunkWithMetadata]:
    """
    Divide texto en chunks con metadata completa de trazabilidad.
    
    REGLA 2: Offsets reales en texto original.
    REGLA 3: Chunking consciente del documento.
    REGLA 4: Section hints controlados.
    
    Args:
        text: Texto original a chunkear
        tipo_documento: Tipo de documento (pdf, docx, txt, etc.)
        page_mapping: Mapeo opcional de {page_num: (start_char, end_char)}
        
    Returns:
        Lista de ChunkWithMetadata con offsets reales
    """
    if not text or not text.strip():
        return []
    
    # REGLA 3: Seleccionar estrategia según tipo y longitud
    strategy = _get_chunking_strategy(tipo_documento, len(text))
    
    max_chars = strategy["max_chars"]
    overlap = strategy["overlap"]
    detect_sections = strategy["detect_sections"]
    strategy_name = strategy["name"]
    
    chunks: List[ChunkWithMetadata] = []
    start = 0
    length = len(text)
    
    while start < length:
        end = min(start + max_chars, length)
        
        # REGLA 2: Offsets reales en texto original
        chunk_content = text[start:end]
        
        # REGLA 4: Inferir section_hint SOLO si hay evidencia
        section_hint = None
        if detect_sections:
            section_hint = _infer_section_hint(chunk_content, start, text)
        
        # Determinar página si hay mapeo
        page = None
        if page_mapping:
            for page_num, (page_start, page_end) in page_mapping.items():
                if start >= page_start and start < page_end:
                    page = page_num
                    break
        
        # REGLA 1: Crear chunk con metadata completa OBLIGATORIA
        chunks.append(
            ChunkWithMetadata(
                content=chunk_content,
                start_char=start,
                end_char=end,
                page=page,
                section_hint=section_hint,
                chunking_strategy=strategy_name,
            )
        )
        
        # Avanzar con overlap
        start = end - overlap
        if start >= length:
            break
    
    return chunks


# ELIMINADO: Función legacy chunk_text() - NO se debe usar
# El pipeline DEBE usar chunk_text_with_metadata() siempre.
# Si existe código que llama a chunk_text(), debe migrar a chunk_text_with_metadata().
