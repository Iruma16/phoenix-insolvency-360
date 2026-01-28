"""
CLASIFICADOR DE CRÉDITOS Y TIMELINE CON EVIDENCE (ENDURECIDO).

Mejoras críticas:
- Extracción de importes cerca de keywords TRLC (no cualquier número)
- Clasificación con confidence score (no absoluta)
- Extracción de fechas con mapeo de meses español
- NUNCA inventa fechas (skip si no hay fecha)
- Evidence completa por crédito/evento
"""
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.financial_analysis import (
    CreditClassification,
    CreditType,
    Evidence,
    TimelineEvent,
)

# =========================================================
# HELPERS DE EVIDENCE
# =========================================================


def create_evidence_from_document(
    document: Document, chunk: Optional[DocumentChunk], excerpt: str, confidence: float = 0.8
) -> Evidence:
    """Crea Evidence desde documento."""
    if len(excerpt) > 200:
        excerpt = excerpt[:197] + "..."

    return Evidence(
        document_id=document.document_id,
        filename=document.filename,
        chunk_id=chunk.chunk_id if chunk else None,
        page=chunk.page_start if chunk and chunk.page_start else None,
        start_char=chunk.start_char if chunk and chunk.start_char else None,
        end_char=chunk.end_char if chunk and chunk.end_char else None,
        excerpt=excerpt,
        extraction_method=chunk.extraction_method
        if chunk and chunk.extraction_method
        else "keyword_proximity",
        extraction_confidence=confidence,
    )


# =========================================================
# EXTRACCIÓN DE IMPORTES (ENDURECIDA)
# =========================================================


def extract_amount_near_keyword(text: str) -> Optional[tuple[float, str, int]]:
    """
    Extrae importe cerca de keywords TRLC.

    Returns:
        (value, excerpt, confidence_score) o None
    """
    keywords = [
        r"importe\s*(?:total|reclamado|adeudado)?",
        r"total\s*(?:adeudado|deuda|débito)?",
        r"deuda\s*(?:total|pendiente)?",
        r"principal\s*(?:adeudado)?",
        r"cantidad\s*(?:reclamada)?",
        r"débito\s*(?:total)?",
    ]

    best_match = None
    best_score = 0

    for kw_pattern in keywords:
        # Buscar keyword + número en contexto cercano (máx 50 chars)
        pattern = kw_pattern + r"[\s:]*([€$]?\s*[\d.,]+)\s*€?"
        matches = re.finditer(pattern, text, re.IGNORECASE)

        for match in matches:
            amount_str = match.group(1)
            # Limpiar
            amount_str = re.sub(r"[€$\s]", "", amount_str)

            try:
                # Formato español: 1.234.567,89
                if "," in amount_str and "." in amount_str:
                    value_str = amount_str.replace(".", "").replace(",", ".")
                elif "," in amount_str:
                    parts = amount_str.split(",")
                    value_str = (
                        amount_str.replace(",", ".")
                        if len(parts[-1]) == 2
                        else amount_str.replace(",", "")
                    )
                else:
                    value_str = amount_str.replace(".", "")

                value = float(value_str)

                # Validar rango contable
                if not (100 <= value <= 999_999_999):
                    continue

                # Calcular score (keyword más específica = mayor score)
                score = len(kw_pattern)
                if score > best_score:
                    best_score = score
                    excerpt = text[max(0, match.start() - 50) : min(len(text), match.end() + 50)]
                    confidence = 85 if score > 20 else 70
                    best_match = (value, excerpt.strip(), confidence)

            except ValueError:
                continue

    return best_match


def extract_amount(text: str) -> Optional[float]:
    """Wrapper para mantener compatibilidad."""
    result = extract_amount_near_keyword(text)
    return result[0] if result else None


# =========================================================
# CLASIFICACIÓN TRLC (CON CONFIDENCE)
# =========================================================


def classify_credit_type(text: str, filename: str) -> tuple[CreditType, int]:
    """
    Clasifica tipo de crédito según TRLC.

    Returns:
        (credit_type, confidence_score)
    """
    text_lower = text.lower()
    filename_lower = filename.lower()

    # Privilegiados especiales (Art. 90 LC)
    # Solo si hay mención EXPLÍCITA de garantía real
    if any(
        kw in text_lower
        for kw in ["garantía real", "garantia real", "hipoteca inscrita", "prenda inscrita"]
    ):
        return (CreditType.PRIVILEGED_SPECIAL, 80)
    elif any(kw in filename_lower for kw in ["hipoteca", "garantia", "prenda"]):
        # Solo por filename = menor confianza
        return (CreditType.PRIVILEGED_SPECIAL, 50)

    # Privilegiados generales (Art. 91 LC)
    # AEAT y SS son los más claros
    if any(kw in text_lower or kw in filename_lower for kw in ["aeat", "agencia tributaria"]):
        return (CreditType.PRIVILEGED_GENERAL, 90)
    if any(
        kw in text_lower or kw in filename_lower
        for kw in ["tesorería general", "tesoreria general", "tgss", "seguridad social"]
    ):
        return (CreditType.PRIVILEGED_GENERAL, 90)
    if "hacienda" in filename_lower and ("embargo" in text_lower or "deuda" in text_lower):
        return (CreditType.PRIVILEGED_GENERAL, 80)
    elif "hacienda" in filename_lower:
        return (CreditType.PRIVILEGED_GENERAL, 70)

    # Ordinarios (por defecto)
    return (CreditType.ORDINARY, 60)


# =========================================================
# EXTRACCIÓN DE FECHAS (ENDURECIDA)
# =========================================================


def extract_date_from_document(text: str, filename: str) -> Optional[tuple[datetime, int]]:
    """
    Extrae fecha del documento.

    Returns:
        (datetime, confidence) o None
    """
    # Mapeo meses español
    meses_es = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }

    patterns = [
        # dd/mm/yyyy o dd-mm-yyyy
        (r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", "dmy", 80),
        # yyyy-mm-dd
        (r"(\d{4})-(\d{1,2})-(\d{1,2})", "ymd", 85),
        # 1 de enero de 2024
        (r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", "dmy_text", 75),
    ]

    for pattern, date_format, confidence in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                if date_format == "dmy":
                    day, month, year = match.groups()
                    dt = datetime(int(year), int(month), int(day))
                elif date_format == "ymd":
                    year, month, day = match.groups()
                    dt = datetime(int(year), int(month), int(day))
                elif date_format == "dmy_text":
                    day, month_text, year = match.groups()
                    month = meses_es.get(month_text.lower())
                    if not month:
                        continue
                    dt = datetime(int(year), int(month), int(day))
                else:
                    continue

                # Validar fecha razonable (2000-2030)
                if 2000 <= dt.year <= 2030:
                    return (dt, confidence)
            except (ValueError, TypeError):
                continue

    return None


# =========================================================
# CLASIFICACIÓN DE CRÉDITOS
# =========================================================


def classify_credits_from_documents(
    db: Session,
    case_id: str,
    case: Optional[Case] = None,  # ✅ Optimización N+1
) -> list[CreditClassification]:
    """
    Clasifica créditos con Evidence y confidence.

    Args:
        db: Sesión de base de datos
        case_id: ID del caso
        case: Objeto Case con documents/chunks precargados (optimización N+1)

    Returns:
        Lista de CreditClassification con evidence
    """
    classifications = []

    # Obtener documentos (precargados o query)
    if case and hasattr(case, "documents") and case.documents:
        documents = case.documents
    else:
        documents = db.query(Document).filter(Document.case_id == case_id).all()

    for doc in documents:
        # Obtener chunks (precargados o query)
        if hasattr(doc, "chunks") and doc.chunks:
            chunks = doc.chunks
        else:
            chunks = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == doc.document_id)
                .order_by(DocumentChunk.chunk_index)
                .all()
            )

        if not chunks:
            continue

        full_text = "\n".join([chunk.content for chunk in chunks if chunk.content])[:1000]

        # Extraer importe (con confidence)
        amount_result = extract_amount_near_keyword(full_text)
        if not amount_result:
            continue

        amount, amount_excerpt, amount_confidence = amount_result

        # Clasificar (con confidence)
        credit_type, classification_confidence = classify_credit_type(full_text, doc.filename)

        # Generar descripción
        if credit_type == CreditType.PRIVILEGED_SPECIAL:
            description = f"Posible crédito con garantía real (conf: {classification_confidence}%)"
        elif credit_type == CreditType.PRIVILEGED_GENERAL:
            if "hacienda" in doc.filename.lower() or "aeat" in full_text.lower():
                description = "Deuda tributaria (AEAT)"
            elif "ss" in doc.filename.lower() or "seguridad" in full_text.lower():
                description = "Deuda con Seguridad Social"
            else:
                description = (
                    f"Posible crédito privilegiado general (conf: {classification_confidence}%)"
                )
        else:
            if "factura" in doc.filename.lower():
                description = "Factura impagada (crédito ordinario)"
            else:
                description = "Crédito ordinario"

        # Nombre acreedor
        creditor = None
        if "hacienda" in doc.filename.lower() or "aeat" in full_text.lower():
            creditor = "AEAT"
        elif "ss" in doc.filename.lower() or "seguridad" in doc.filename.lower():
            creditor = "Seguridad Social / TGSS"

        # Crear Evidence con excerpt real del importe
        chunk = chunks[0] if chunks else None
        overall_confidence = min(amount_confidence, classification_confidence) / 100.0

        evidence = create_evidence_from_document(doc, chunk, amount_excerpt, overall_confidence)

        classifications.append(
            CreditClassification(
                credit_type=credit_type,
                amount=amount,
                creditor_name=creditor,
                description=description,
                evidence=evidence,
            )
        )

    return classifications


# =========================================================
# EXTRACCIÓN DE TIMELINE
# =========================================================


def extract_timeline_from_documents(
    db: Session,
    case_id: str,
    case: Optional[Case] = None,  # ✅ Optimización N+1
) -> list[TimelineEvent]:
    """
    Extrae timeline con Evidence (NUNCA inventa fechas).

    Args:
        db: Sesión de base de datos
        case_id: ID del caso
        case: Objeto Case con documents/chunks precargados (optimización N+1)

    Returns:
        Lista de TimelineEvent con evidence
    """
    events = []

    # Obtener documentos (precargados o query)
    if case and hasattr(case, "documents") and case.documents:
        documents = case.documents
    else:
        documents = db.query(Document).filter(Document.case_id == case_id).all()

    for doc in documents:
        # Obtener chunks (precargados o query)
        if hasattr(doc, "chunks") and doc.chunks:
            chunks = doc.chunks
        else:
            chunks = (
                db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.document_id).all()
            )

        if not chunks:
            continue

        full_text = "\n".join([chunk.content for chunk in chunks if chunk.content])[:500]

        # Detectar tipo de evento
        event_type = None
        description = doc.filename

        if "embargo" in doc.filename.lower() or "embargo" in full_text.lower():
            event_type = "embargo"
            if "hacienda" in full_text.lower():
                description = "Embargo Hacienda"
            elif "seguridad" in full_text.lower():
                description = "Embargo Seguridad Social"
            else:
                description = "Embargo"
        elif "factura" in doc.filename.lower():
            event_type = "factura_vencida"
            description = f"Factura: {doc.filename}"
        elif "reclamaci" in full_text.lower():
            event_type = "reclamacion"
            description = "Reclamación de acreedor"

        if event_type:
            amount_result = extract_amount_near_keyword(full_text)
            amount = amount_result[0] if amount_result else None

            # Intentar extraer fecha del texto
            date_result = extract_date_from_document(full_text, doc.filename)

            # Si no hay fecha en texto, usar doc.date_start
            # Si tampoco existe, SKIP este evento (no inventar fechas)
            if date_result:
                event_date, date_confidence = date_result
            elif doc.date_start:
                event_date = doc.date_start
                date_confidence = 50  # Baja confianza (viene del metadato)
            else:
                # ❌ NO crear evento sin fecha
                continue

            chunk = chunks[0] if chunks else None
            excerpt = full_text[:200] if full_text else doc.filename

            events.append(
                TimelineEvent(
                    date=event_date,
                    event_type=event_type,
                    description=description,
                    amount=amount,
                    evidence=create_evidence_from_document(
                        doc, chunk, excerpt, date_confidence / 100.0
                    ),
                )
            )

    # Ordenar cronológicamente
    events.sort(key=lambda e: e.date)

    return events


# ==============================================================================
# COMPATIBILIDAD CON CÓDIGO ANTIGUO
# ==============================================================================

# Para mantener compatibilidad con balance_concursal_service.py
TRLC_RULESET_VERSION = "2.0"


class TRLCCreditClassifier:
    """
    Clase stub para compatibilidad con código antiguo.

    El nuevo sistema usa funciones directamente (classify_credits_from_documents).
    Esta clase se mantiene solo para no romper imports existentes.
    """

    def __init__(self, concurso_date: Optional[datetime] = None):
        self.concurso_date = concurso_date
        self.version = TRLC_RULESET_VERSION

    def classify_from_documents(self, db, case_id: str, case=None):
        """
        Wrapper para la función classify_credits_from_documents.

        Mantiene compatibilidad con código que use la clase.
        """
        return classify_credits_from_documents(db, case_id, case=case)

    # -------------------------------------------------------------------------
    # API usada por FASE 1.3 (Balance Concursal)
    # -------------------------------------------------------------------------
    def classify_credit(self, credit):
        """
        Clasifica un `Credit` (FASE 1.3) según reglas TRLC mínimas.

        Este método existe para compatibilidad con tests/servicios que esperan una
        interfaz OO, aunque la versión "RAG" usa funciones sobre documentos.
        """
        from datetime import date as date_type

        from app.models.credit import CreditClassificationTRLC, CreditNature

        classification = CreditClassificationTRLC.ORDINARIO
        reasoning = "Clasificación por defecto: crédito ordinario (sin indicios de privilegio/subordinación)."
        confidence = 0.65

        # Contra la masa: devengo posterior al concurso (simplificación)
        if self.concurso_date and getattr(credit, "devengo_date", None):
            concurso = self.concurso_date
            if isinstance(concurso, date_type):
                concurso_date = concurso
            else:
                concurso_date = concurso.date()
            if credit.devengo_date > concurso_date:
                classification = CreditClassificationTRLC.CONTRA_LA_MASA
                reasoning = (
                    "Devengo posterior a la declaración de concurso → crédito contra la masa."
                )
                confidence = 0.75

        nature = getattr(credit, "nature", None)
        if nature == CreditNature.SALARIO:
            classification = CreditClassificationTRLC.PRIVILEGIADO_GENERAL
            reasoning = "Crédito de naturaleza salarial → privilegiado general (TRLC)."
            confidence = 0.85
        elif nature in (CreditNature.SEGURIDAD_SOCIAL, CreditNature.AEAT):
            classification = CreditClassificationTRLC.PRIVILEGIADO_GENERAL
            reasoning = "Crédito frente a AEAT/Seguridad Social → privilegiado general (TRLC)."
            confidence = 0.9
        elif nature in (CreditNature.MULTA, CreditNature.SANCION, CreditNature.INTERESES):
            classification = CreditClassificationTRLC.SUBORDINADO
            reasoning = "Sanciones/multas/intereses → subordinado (regla simplificada TRLC)."
            confidence = 0.8
        elif nature == CreditNature.PERSONA_VINCULADA:
            classification = CreditClassificationTRLC.SUBORDINADO
            reasoning = "Crédito de persona vinculada → subordinado (TRLC)."
            confidence = 0.85
        elif nature == CreditNature.FINANCIERO:
            if (
                getattr(credit, "secured", False)
                or getattr(credit, "guarantee_type", None) == "real"
            ):
                classification = CreditClassificationTRLC.PRIVILEGIADO_ESPECIAL
                reasoning = "Crédito financiero con garantía real → privilegiado especial (TRLC)."
                confidence = 0.8
            else:
                classification = CreditClassificationTRLC.ORDINARIO
                reasoning = "Crédito financiero sin garantía real → ordinario (TRLC)."
                confidence = 0.7

        credit.trlc_classification = classification
        credit.classification_reasoning = reasoning
        credit.confidence = max(float(getattr(credit, "confidence", 0.5)), confidence)
        return credit

    def classify_credits_batch(self, creditos: list):
        """Clasifica una lista de `Credit`."""
        return [self.classify_credit(c) for c in creditos]
