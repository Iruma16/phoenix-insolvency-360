"""
ENDPOINT OFICIAL DE ANÁLISIS TÉCNICO / ALERTAS (PANTALLA 3).

PRINCIPIO: Esta capa NO interpreta ni concluye legalmente.
Solo DETECTA y MUESTRA problemas técnicos en los datos.

PROHIBIDO:
- emitir conclusiones legales
- clasificar culpabilidad
- generar texto interpretativo
- usar LLMs o embeddings
- ocultar evidencia
- generar alertas sin soporte documental
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.analysis_alert import (
    AlertEvidence,
    AlertEvidenceLocation,
    AlertType,
    AnalysisAlert,
)
from app.models.case import Case
from app.models.document import Document
from app.models.document_chunk import DocumentChunk

router = APIRouter(
    prefix="/cases/{case_id}/analysis",
    tags=["analysis"],
)


def _build_alert_evidence(chunk: DocumentChunk, db: Session) -> AlertEvidence:
    """
    Construye AlertEvidence desde un DocumentChunk del core.

    NO inventa datos.
    NO oculta información.
    SOLO expone el estado EXACTO.

    Args:
        chunk: Chunk del core
        db: Sesión de base de datos

    Returns:
        AlertEvidence con datos exactos

    Raises:
        ValueError: Si el chunk no cumple el contrato
    """
    # Validar contrato: location obligatoria
    if chunk.start_char is None or chunk.end_char is None:
        raise ValueError(f"Chunk sin offsets obligatorios: {chunk.chunk_id}")

    if not chunk.extraction_method:
        raise ValueError(f"Chunk sin extraction_method: {chunk.chunk_id}")

    if not chunk.content or not chunk.content.strip():
        raise ValueError(f"Chunk con contenido vacío: {chunk.chunk_id}")

    # Obtener documento para filename
    document = db.query(Document).filter(Document.document_id == chunk.document_id).first()

    if not document:
        raise ValueError(f"Documento {chunk.document_id} no encontrado para chunk {chunk.chunk_id}")

    # Construir location
    location = AlertEvidenceLocation(
        start_char=chunk.start_char,
        end_char=chunk.end_char,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        extraction_method=chunk.extraction_method,
    )

    return AlertEvidence(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        filename=document.filename,
        location=location,
        content=chunk.content,  # Texto LITERAL, sin modificar
    )


def _detect_missing_data_alerts(
    case_id: str, chunks: list[DocumentChunk], db: Session
) -> list[AnalysisAlert]:
    """
    Detecta alertas de DATOS FALTANTES de forma determinista.

    Reglas:
    - Chunks sin page_start/page_end cuando extraction_method es PDF_TEXT
    - Documentos sin chunks
    """
    alerts = []

    # Regla 1: Chunks sin páginas cuando debería tenerlas
    chunks_without_pages = [
        chunk
        for chunk in chunks
        if chunk.extraction_method == "pdf_text" and chunk.page_start is None
    ]

    if chunks_without_pages:
        evidence_list = []
        for chunk in chunks_without_pages[:5]:  # Limitar a 5 evidencias
            try:
                evidence = _build_alert_evidence(chunk, db)
                evidence_list.append(evidence)
            except ValueError:
                continue

        if evidence_list:
            alert_id = hashlib.sha256(
                f"{case_id}_MISSING_DATA_pages_{datetime.utcnow().isoformat()}".encode()
            ).hexdigest()[:16]

            alerts.append(
                AnalysisAlert(
                    alert_id=alert_id,
                    case_id=case_id,
                    alert_type=AlertType.MISSING_DATA,
                    description=f"Detectados {len(chunks_without_pages)} chunks PDF sin información de página.",
                    evidence=evidence_list,
                    created_at=datetime.utcnow(),
                )
            )

    return alerts


def _detect_duplicated_data_alerts(
    case_id: str, chunks: list[DocumentChunk], db: Session
) -> list[AnalysisAlert]:
    """
    Detecta alertas de DATOS DUPLICADOS de forma determinista.

    Reglas:
    - Chunks con contenido idéntico (literalmente)
    - Solo alertar si hay más de 2 ocurrencias
    """
    alerts = []

    # Agrupar chunks por contenido exacto
    content_map: dict[str, list[DocumentChunk]] = defaultdict(list)
    for chunk in chunks:
        if chunk.content and len(chunk.content.strip()) > 50:  # Ignorar chunks muy cortos
            content_map[chunk.content.strip()].append(chunk)

    # Detectar duplicados (≥3 ocurrencias)
    for content, duplicate_chunks in content_map.items():
        if len(duplicate_chunks) >= 3:
            evidence_list = []
            for chunk in duplicate_chunks[:3]:  # Limitar a 3 evidencias
                try:
                    evidence = _build_alert_evidence(chunk, db)
                    evidence_list.append(evidence)
                except ValueError:
                    continue

            if evidence_list:
                alert_id = hashlib.sha256(
                    f"{case_id}_DUPLICATED_DATA_{content[:50]}_{datetime.utcnow().isoformat()}".encode()
                ).hexdigest()[:16]

                alerts.append(
                    AnalysisAlert(
                        alert_id=alert_id,
                        case_id=case_id,
                        alert_type=AlertType.DUPLICATED_DATA,
                        description=f"Detectadas {len(duplicate_chunks)} ocurrencias de contenido duplicado literalmente.",
                        evidence=evidence_list,
                        created_at=datetime.utcnow(),
                    )
                )

    return alerts


def _detect_inconsistent_data_alerts(
    case_id: str, chunks: list[DocumentChunk], db: Session
) -> list[AnalysisAlert]:
    """
    Detecta alertas de DATOS INCONSISTENTES de forma determinista.

    Reglas:
    - Chunks con offsets inválidos (start >= end)
    - Chunks con páginas inválidas (start > end)
    """
    alerts = []

    # Regla 1: Offsets inválidos (esto no debería ocurrir si el contrato funciona)
    invalid_offsets = [
        chunk
        for chunk in chunks
        if chunk.start_char is not None
        and chunk.end_char is not None
        and chunk.start_char >= chunk.end_char
    ]

    if invalid_offsets:
        evidence_list = []
        for chunk in invalid_offsets[:5]:
            try:
                evidence = _build_alert_evidence(chunk, db)
                evidence_list.append(evidence)
            except ValueError:
                continue

        if evidence_list:
            alert_id = hashlib.sha256(
                f"{case_id}_INCONSISTENT_DATA_offsets_{datetime.utcnow().isoformat()}".encode()
            ).hexdigest()[:16]

            alerts.append(
                AnalysisAlert(
                    alert_id=alert_id,
                    case_id=case_id,
                    alert_type=AlertType.INCONSISTENT_DATA,
                    description=f"Detectados {len(invalid_offsets)} chunks con offsets inválidos (start >= end).",
                    evidence=evidence_list,
                    created_at=datetime.utcnow(),
                )
            )

    # Regla 2: Páginas inválidas
    invalid_pages = [
        chunk
        for chunk in chunks
        if chunk.page_start is not None
        and chunk.page_end is not None
        and chunk.page_start > chunk.page_end
    ]

    if invalid_pages:
        evidence_list = []
        for chunk in invalid_pages[:5]:
            try:
                evidence = _build_alert_evidence(chunk, db)
                evidence_list.append(evidence)
            except ValueError:
                continue

        if evidence_list:
            alert_id = hashlib.sha256(
                f"{case_id}_INCONSISTENT_DATA_pages_{datetime.utcnow().isoformat()}".encode()
            ).hexdigest()[:16]

            alerts.append(
                AnalysisAlert(
                    alert_id=alert_id,
                    case_id=case_id,
                    alert_type=AlertType.INCONSISTENT_DATA,
                    description=f"Detectados {len(invalid_pages)} chunks con páginas inválidas (start > end).",
                    evidence=evidence_list,
                    created_at=datetime.utcnow(),
                )
            )

    return alerts


def _detect_suspicious_patterns(
    case_id: str, chunks: list[DocumentChunk], db: Session
) -> list[AnalysisAlert]:
    """
    Detecta patrones SOSPECHOSOS técnicamente de forma determinista.

    Reglas:
    - Chunks muy largos (>10000 caracteres) que podrían indicar mal chunking
    - Chunks muy cortos (<10 caracteres) que podrían ser ruido
    """
    alerts = []

    # Regla 1: Chunks anormalmente largos
    very_long_chunks = [chunk for chunk in chunks if chunk.content and len(chunk.content) > 10000]

    if very_long_chunks:
        evidence_list = []
        for chunk in very_long_chunks[:3]:
            try:
                evidence = _build_alert_evidence(chunk, db)
                evidence_list.append(evidence)
            except ValueError:
                continue

        if evidence_list:
            alert_id = hashlib.sha256(
                f"{case_id}_SUSPICIOUS_PATTERN_long_{datetime.utcnow().isoformat()}".encode()
            ).hexdigest()[:16]

            alerts.append(
                AnalysisAlert(
                    alert_id=alert_id,
                    case_id=case_id,
                    alert_type=AlertType.SUSPICIOUS_PATTERN,
                    description=f"Detectados {len(very_long_chunks)} chunks anormalmente largos (>10000 chars), posible error de chunking.",
                    evidence=evidence_list,
                    created_at=datetime.utcnow(),
                )
            )

    # Regla 2: Chunks anormalmente cortos
    very_short_chunks = [
        chunk for chunk in chunks if chunk.content and 0 < len(chunk.content.strip()) < 10
    ]

    if len(very_short_chunks) > 10:  # Solo alertar si hay muchos
        evidence_list = []
        for chunk in very_short_chunks[:3]:
            try:
                evidence = _build_alert_evidence(chunk, db)
                evidence_list.append(evidence)
            except ValueError:
                continue

        if evidence_list:
            alert_id = hashlib.sha256(
                f"{case_id}_SUSPICIOUS_PATTERN_short_{datetime.utcnow().isoformat()}".encode()
            ).hexdigest()[:16]

            alerts.append(
                AnalysisAlert(
                    alert_id=alert_id,
                    case_id=case_id,
                    alert_type=AlertType.SUSPICIOUS_PATTERN,
                    description=f"Detectados {len(very_short_chunks)} chunks anormalmente cortos (<10 chars), posible ruido.",
                    evidence=evidence_list,
                    created_at=datetime.utcnow(),
                )
            )

    return alerts


@router.get(
    "/alerts",
    response_model=list[AnalysisAlert],
    summary="Obtener alertas técnicas de un caso",
    description=(
        "Detecta y muestra problemas técnicos en los datos del caso. "
        "Alertas TÉCNICAS, NO legales. "
        "Reglas deterministas, reproducibles, sin LLM/ML. "
        "Cada alerta incluye evidencia física verificable."
    ),
)
def get_analysis_alerts(
    case_id: str,
    db: Session = Depends(get_db),
) -> list[AnalysisAlert]:
    """
    Obtiene alertas técnicas de un caso.

    Ejecuta reglas DETERMINISTAS (no ML, no LLM).
    Cada alerta incluye evidencia verificable.

    Args:
        case_id: ID del caso
        db: Sesión de base de datos

    Returns:
        Lista de AnalysisAlert (puede ser vacía)

    Raises:
        HTTPException 404: Si el caso no existe
    """
    # Verificar que el caso existe
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado"
        )

    # Obtener todos los chunks del caso
    chunks = db.query(DocumentChunk).filter(DocumentChunk.case_id == case_id).all()

    # Si no hay chunks, no hay alertas (no se inventa nada)
    if not chunks:
        return []

    # Ejecutar reglas deterministas
    all_alerts: list[AnalysisAlert] = []

    # Regla 1: Datos faltantes
    all_alerts.extend(_detect_missing_data_alerts(case_id, chunks, db))

    # Regla 2: Datos duplicados
    all_alerts.extend(_detect_duplicated_data_alerts(case_id, chunks, db))

    # Regla 3: Datos inconsistentes
    all_alerts.extend(_detect_inconsistent_data_alerts(case_id, chunks, db))

    # Regla 4: Patrones sospechosos
    all_alerts.extend(_detect_suspicious_patterns(case_id, chunks, db))

    return all_alerts


# =========================================================
# ENDPOINTS PROHIBIDOS (NO IMPLEMENTADOS)
# =========================================================

# POST /cases/{case_id}/analysis/alerts → PROHIBIDO (no se crean alertas manualmente)
# PUT /cases/{case_id}/analysis/alerts/{alert_id} → PROHIBIDO (no se editan alertas)
# DELETE /cases/{case_id}/analysis/alerts/{alert_id} → PROHIBIDO (no se borran alertas)
# POST /cases/{case_id}/analysis/interpret → PROHIBIDO (no interpretación legal)
# POST /cases/{case_id}/analysis/llm → PROHIBIDO (no LLM)
