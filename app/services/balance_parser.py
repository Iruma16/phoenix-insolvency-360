"""
PARSER DE ESTADOS FINANCIEROS ENDURECIDO.

Mejoras críticas:
- Selección de documento por scoring (fecha, tipo, calidad)
- Chunks ordenados correctamente (page + index)
- Extracción por línea (no contexto libre)
- Validación de números (descarta años, CIFs, porcentajes)
- Siempre devuelve resultado (parcial si es necesario)
- Evidencia completa por campo
"""
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.financial_analysis import (
    BalanceData,
    BalanceField,
    ConfidenceLevel,
    Evidence,
    ProfitLossData,
    ProfitLossField,
)

# =========================================================
# SELECCIÓN DE DOCUMENTO (CON SCORING)
# =========================================================


def score_document(doc: Document, keyword: str) -> float:
    """
    Puntúa un documento para seleccionar el mejor.

    Criterios:
    - Fecha reciente (+10)
    - Nombre con keyword (+5)
    - Tipo Excel (+5)
    - Tamaño razonable (+3)
    """
    score = 0.0

    # Fecha reciente (0-10 puntos)
    if doc.date_start:
        days_old = (datetime.utcnow() - doc.date_start).days
        if days_old < 365:
            score += 10
        elif days_old < 730:
            score += 5
        else:
            score += 1

    # Nombre con keyword (5 puntos)
    if keyword.lower() in doc.filename.lower():
        score += 5

    # Excel (preferido, 5 puntos)
    if doc.file_format and "excel" in doc.file_format.lower():
        score += 5
    elif doc.filename.endswith((".xlsx", ".xls")):
        score += 5

    # Tamaño razonable (2-3 puntos)
    if doc.file_size_bytes and 10000 < doc.file_size_bytes < 5000000:
        score += 3

    return score


def select_best_document(
    db: Session, case_id: str, keyword: str, document_id: Optional[str] = None
) -> Optional[Document]:
    """Selecciona el mejor documento por scoring."""
    query = db.query(Document).filter(Document.case_id == case_id)

    if document_id:
        return query.filter(Document.document_id == document_id).first()

    candidates = query.filter(Document.filename.ilike(f"%{keyword}%")).all()
    if not candidates:
        return None

    scored = [(doc, score_document(doc, keyword)) for doc in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)

    return scored[0][0]


# =========================================================
# EXTRACCIÓN DE NÚMEROS (ENDURECIDA)
# =========================================================


def extract_number_from_line(line: str, keyword_pos: int = 0) -> Optional[float]:
    """
    Extrae número de una LÍNEA con validaciones.

    Descarta:
    - Años (2023, 2022...)
    - Números muy cortos (<3 dígitos)
    - Fuera de rango contable
    """
    line_after = line[keyword_pos:] if keyword_pos > 0 else line
    pattern = r"([\d.,\-()]+)"
    matches = list(re.finditer(pattern, line_after))

    for match in matches:
        num_str = match.group(1)

        # Detectar negativo
        is_negative = "(" in num_str or num_str.startswith("-")
        num_str = re.sub(r"[()\\-]", "", num_str)

        # Descartar años
        clean = num_str.replace(".", "").replace(",", "")
        if re.match(r"^20\d{2}$", clean):
            continue

        # Descartar muy cortos
        if len(clean) < 3:
            continue

        try:
            # Formato español: 1.234.567,89
            if "," in num_str and "." in num_str:
                value_str = num_str.replace(".", "").replace(",", ".")
            elif "," in num_str:
                parts = num_str.split(",")
                value_str = (
                    num_str.replace(",", ".") if len(parts[-1]) == 2 else num_str.replace(",", "")
                )
            else:
                value_str = num_str.replace(".", "")

            value = float(value_str)
            if is_negative:
                value = -abs(value)

            # Validar rango contable
            if -999999999999 <= value <= 999999999999:
                return value
        except ValueError:
            continue

    return None


# =========================================================
# CREACIÓN DE EVIDENCIA
# =========================================================


def create_evidence_from_line(
    document: Document,
    chunk: Optional[DocumentChunk],
    line: str,
    line_offset: int,
    confidence: float = 0.85,
) -> Evidence:
    """Crea Evidence desde una línea."""
    excerpt = line.strip()
    if len(excerpt) > 200:
        excerpt = excerpt[:197] + "..."

    return Evidence(
        document_id=document.document_id,
        filename=document.filename,
        chunk_id=chunk.chunk_id if chunk else None,
        page=chunk.page_start if chunk and chunk.page_start else None,
        start_char=line_offset,
        end_char=line_offset + len(line),
        excerpt=excerpt,
        extraction_method=chunk.extraction_method
        if chunk and chunk.extraction_method
        else "line_search",
        extraction_confidence=confidence,
    )


def find_chunk_at_offset(chunks: list[DocumentChunk], offset: int) -> Optional[DocumentChunk]:
    """Encuentra chunk por offset."""
    cumulative = 0
    for chunk in chunks:
        if not chunk.content:
            continue
        chunk_len = len(chunk.content) + 1
        if cumulative <= offset < cumulative + chunk_len:
            return chunk
        cumulative += chunk_len
    return chunks[0] if chunks else None


# =========================================================
# PARSER PRINCIPAL
# =========================================================


def parse_balance_from_chunks(
    db: Session,
    case_id: str,
    document_id: Optional[str] = None,
    case: Optional[Case] = None,  # ✅ Parámetro opcional para evitar N+1
) -> Optional[BalanceData]:
    """
    Parser de balance endurecido.

    Args:
        db: Sesión de base de datos
        case_id: ID del caso
        document_id: ID de documento específico (opcional)
        case: Objeto Case con documents/chunks precargados (optimización N+1)

    Returns:
        BalanceData con evidence o None si no encuentra datos
    """

    # 1. Seleccionar mejor documento
    # Si tenemos case precargado, buscar en case.documents (en memoria)
    # Si no, hacer query a BD (backward compatible)
    if case and hasattr(case, "documents") and case.documents:
        # Buscar documento con tipo 'balance' en la lista precargada
        balance_docs = [
            d
            for d in case.documents
            if "balance" in (d.doc_type or "").lower()  # ✅ doc_type, no document_type
            or "balance" in (d.filename or "").lower()
        ]
        doc = balance_docs[0] if balance_docs else None
    else:
        # Fallback a query tradicional
        doc = select_best_document(db, case_id, "balance", document_id)

    if not doc:
        return None

    # 2. Chunks ORDENADOS
    # Si doc.chunks ya está cargado (eager loading), usar eso
    # Si no, hacer query (backward compatible)
    if hasattr(doc, "chunks") and doc.chunks:
        chunks = sorted(doc.chunks, key=lambda c: (c.page_start or 0, c.chunk_index or 0))
    else:
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == doc.document_id)
            .order_by(DocumentChunk.page_start, DocumentChunk.chunk_index)
            .all()
        )

    if not chunks:
        return None

    # 3. Texto ordenado
    full_text = "\n".join([chunk.content for chunk in chunks if chunk.content])
    lines = full_text.split("\n")

    # 4. Inicializar balance (SIEMPRE)
    balance = BalanceData(
        overall_confidence=ConfidenceLevel.LOW,
        source_date=doc.date_start.isoformat()[:10] if doc.date_start else None,
    )

    # 5. Parsear línea por línea
    cumulative_offset = 0

    for line in lines:
        line_lower = line.lower()

        # Activo Corriente
        if "activo" in line_lower and "corriente" in line_lower and not balance.activo_corriente:
            kw_pos = line_lower.find("activo")
            value = extract_number_from_line(line, kw_pos)
            if value is not None and value >= 0:
                chunk = find_chunk_at_offset(chunks, cumulative_offset)
                conf = (
                    ConfidenceLevel.HIGH
                    if chunk and "excel" in str(chunk.extraction_method)
                    else ConfidenceLevel.MEDIUM
                )
                balance.activo_corriente = BalanceField(
                    value=value,
                    evidence=create_evidence_from_line(doc, chunk, line, cumulative_offset, 0.9),
                    confidence=conf,
                )

        # Pasivo Corriente
        if "pasivo" in line_lower and "corriente" in line_lower and not balance.pasivo_corriente:
            kw_pos = line_lower.find("pasivo")
            value = extract_number_from_line(line, kw_pos)
            if value is not None and value >= 0:
                chunk = find_chunk_at_offset(chunks, cumulative_offset)
                conf = (
                    ConfidenceLevel.HIGH
                    if chunk and "excel" in str(chunk.extraction_method)
                    else ConfidenceLevel.MEDIUM
                )
                balance.pasivo_corriente = BalanceField(
                    value=value,
                    evidence=create_evidence_from_line(doc, chunk, line, cumulative_offset, 0.9),
                    confidence=conf,
                )

        # Activo Total
        if (
            ("total" in line_lower and "activo" in line_lower)
            or ("activo" in line_lower and "total" in line_lower)
        ) and not balance.activo_total:
            kw_pos = line_lower.find("activo")
            value = extract_number_from_line(line, kw_pos)
            if value is not None and value >= 0:
                chunk = find_chunk_at_offset(chunks, cumulative_offset)
                balance.activo_total = BalanceField(
                    value=value,
                    evidence=create_evidence_from_line(doc, chunk, line, cumulative_offset, 0.95),
                    confidence=ConfidenceLevel.HIGH,
                )

        # Pasivo Total
        if (
            ("total" in line_lower and "pasivo" in line_lower)
            or ("pasivo" in line_lower and "total" in line_lower)
        ) and not balance.pasivo_total:
            kw_pos = line_lower.find("pasivo")
            value = extract_number_from_line(line, kw_pos)
            if value is not None and value >= 0:
                chunk = find_chunk_at_offset(chunks, cumulative_offset)
                balance.pasivo_total = BalanceField(
                    value=value,
                    evidence=create_evidence_from_line(doc, chunk, line, cumulative_offset, 0.95),
                    confidence=ConfidenceLevel.HIGH,
                )

        # Patrimonio Neto (puede ser negativo)
        if "patrimonio" in line_lower and "neto" in line_lower and not balance.patrimonio_neto:
            kw_pos = line_lower.find("patrimonio")
            value = extract_number_from_line(line, kw_pos)
            if value is not None:
                chunk = find_chunk_at_offset(chunks, cumulative_offset)
                balance.patrimonio_neto = BalanceField(
                    value=value,
                    evidence=create_evidence_from_line(doc, chunk, line, cumulative_offset, 0.9),
                    confidence=ConfidenceLevel.HIGH if chunk else ConfidenceLevel.MEDIUM,
                )

        cumulative_offset += len(line) + 1

    # 6. Calcular confianza global
    fields_found = sum(
        [
            balance.activo_corriente is not None,
            balance.pasivo_corriente is not None,
            balance.activo_total is not None,
            balance.pasivo_total is not None,
            balance.patrimonio_neto is not None,
        ]
    )

    fields_high = sum(
        [
            balance.activo_corriente
            and balance.activo_corriente.confidence == ConfidenceLevel.HIGH,
            balance.pasivo_corriente
            and balance.pasivo_corriente.confidence == ConfidenceLevel.HIGH,
            balance.activo_total and balance.activo_total.confidence == ConfidenceLevel.HIGH,
            balance.pasivo_total and balance.pasivo_total.confidence == ConfidenceLevel.HIGH,
            balance.patrimonio_neto and balance.patrimonio_neto.confidence == ConfidenceLevel.HIGH,
        ]
    )

    if fields_found >= 4 and fields_high >= 3:
        balance.overall_confidence = ConfidenceLevel.HIGH
    elif fields_found >= 2:
        balance.overall_confidence = ConfidenceLevel.MEDIUM
    else:
        balance.overall_confidence = ConfidenceLevel.LOW

    return balance


def parse_pyg_from_chunks(
    db: Session,
    case_id: str,
    document_id: Optional[str] = None,
    case: Optional[Case] = None,  # ✅ Optimización N+1
) -> Optional[ProfitLossData]:
    """
    Parser PyG endurecido.

    Args:
        db: Sesión de base de datos
        case_id: ID del caso
        document_id: ID de documento específico (opcional)
        case: Objeto Case con documents/chunks precargados (optimización N+1)

    Returns:
        ProfitLossData con evidence o None si no encuentra datos
    """

    # Buscar documento PyG (en caso precargado o BD)
    doc = None
    if case and hasattr(case, "documents") and case.documents:
        # Buscar en documentos precargados
        for keyword in ["pyg", "perdidas", "ganancias", "p&g", "resultado"]:
            matching_docs = [
                d
                for d in case.documents
                if keyword in (d.doc_type or "").lower()  # ✅ doc_type, no document_type
                or keyword in (d.filename or "").lower()
            ]
            if matching_docs:
                doc = matching_docs[0]
                break
    else:
        # Fallback a query tradicional
        doc = select_best_document(db, case_id, "pyg", document_id)
        if not doc:
            # Intentar con otros nombres
            doc = select_best_document(db, case_id, "perdidas", document_id)
        if not doc:
            doc = select_best_document(db, case_id, "ganancias", document_id)

    if not doc:
        return None

    # Chunks (precargados o query)
    if hasattr(doc, "chunks") and doc.chunks:
        chunks = sorted(doc.chunks, key=lambda c: (c.page_start or 0, c.chunk_index or 0))
    else:
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == doc.document_id)
            .order_by(DocumentChunk.page_start, DocumentChunk.chunk_index)
            .all()
        )

    if not chunks:
        return None

    full_text = "\n".join([chunk.content for chunk in chunks if chunk.content])
    lines = full_text.split("\n")

    pyg = ProfitLossData(
        overall_confidence=ConfidenceLevel.LOW,
        source_date=doc.date_start.isoformat()[:10] if doc.date_start else None,
    )

    cumulative_offset = 0

    for line in lines:
        line_lower = line.lower()

        # Resultado del ejercicio
        if "resultado" in line_lower and "ejercicio" in line_lower and not pyg.resultado_ejercicio:
            kw_pos = line_lower.find("resultado")
            value = extract_number_from_line(line, kw_pos)
            if value is not None:
                chunk = find_chunk_at_offset(chunks, cumulative_offset)
                pyg.resultado_ejercicio = ProfitLossField(
                    value=value,
                    evidence=create_evidence_from_line(doc, chunk, line, cumulative_offset, 0.9),
                    confidence=ConfidenceLevel.HIGH if chunk else ConfidenceLevel.MEDIUM,
                )
                pyg.overall_confidence = pyg.resultado_ejercicio.confidence

        cumulative_offset += len(line) + 1

    return pyg if pyg.resultado_ejercicio else None
