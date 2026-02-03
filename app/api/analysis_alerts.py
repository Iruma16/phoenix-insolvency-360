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
import re
from collections import defaultdict
from datetime import datetime, timedelta

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


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _contains_any(haystack: str, needles: list[str]) -> bool:
    h = _norm(haystack)
    return any(n in h for n in needles)


def _make_alert_id(*, case_id: str, alert_type: str, fingerprint: str) -> str:
    """
    ID determinista.

    Importante:
    - NO usar datetime/aleatoriedad → reproducibilidad.
    - fingerprint debe ser estable y derivado de evidencia/valores detectados.
    """
    raw = f"{case_id}|{alert_type}|{fingerprint}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _build_evidence_list(
    *,
    chunks: list[DocumentChunk],
    db: Session,
    limit: int = 3,
) -> list[AlertEvidence]:
    out: list[AlertEvidence] = []
    for c in chunks:
        if len(out) >= limit:
            break
        try:
            out.append(_build_alert_evidence(c, db))
        except ValueError:
            continue
    return out


def _score_internal(alert: AnalysisAlert) -> int:
    """
    Scoring interno (0-100) para ordenar alertas.
    NO se expone por API (el contrato AnalysisAlert es técnico y `extra=forbid`).
    """
    # Base por tipo técnico
    base = {
        AlertType.SUSPICIOUS_PATTERN: 70,
        AlertType.TEMPORAL_INCONSISTENCY: 55,
        AlertType.INCONSISTENT_DATA: 50,
        AlertType.DUPLICATED_DATA: 35,
        AlertType.MISSING_DATA: 30,
    }.get(alert.alert_type, 40)

    # Ajustes por nº evidencias y “señales fuertes” en description
    ev = len(alert.evidence or [])
    bonus = min(20, ev * 4)

    d = (alert.description or "").lower()
    if "tgss" in d or "providencia" in d or "apremio" in d:
        bonus += 6
    if "vinculad" in d or "grupo" in d:
        bonus += 6
    if "efectivo" in d or "cajero" in d or "reintegro" in d:
        bonus += 6
    if "iva" in d:
        bonus += 4
    if "periodo" in d and "consecutiv" in d:
        bonus += 6

    return max(0, min(100, base + bonus))


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
            fp = "|".join(sorted({e.chunk_id for e in evidence_list}))
            alert_id = _make_alert_id(
                case_id=case_id,
                alert_type=AlertType.MISSING_DATA.value,
                fingerprint=f"pdf_pages_missing|{fp}",
            )

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
                content_fp = hashlib.sha256(content.encode()).hexdigest()[:12]
                fp = "|".join(sorted({e.chunk_id for e in evidence_list}))
                alert_id = _make_alert_id(
                    case_id=case_id,
                    alert_type=AlertType.DUPLICATED_DATA.value,
                    fingerprint=f"chunk_literal|{content_fp}|{fp}",
                )

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
            fp = "|".join(sorted({e.chunk_id for e in evidence_list}))
            alert_id = _make_alert_id(
                case_id=case_id,
                alert_type=AlertType.INCONSISTENT_DATA.value,
                fingerprint=f"invalid_offsets|{fp}",
            )

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
            fp = "|".join(sorted({e.chunk_id for e in evidence_list}))
            alert_id = _make_alert_id(
                case_id=case_id,
                alert_type=AlertType.INCONSISTENT_DATA.value,
                fingerprint=f"invalid_pages|{fp}",
            )

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
    - Duplicidades raras: mismo SHA256 subido muchas veces
    - Chunks repetidos en muchos documentos (contenido idéntico, multi-doc)
    - Señales de manipulación / OCR sin texto útil
    - Inconsistencias temporales (fechas imposibles / futuras)
    - Patrones financieros básicos (importes repetidos)
    - Patrimonial: ventas de activos cercanas a embargos (si se detecta por timeline)
    - Chunks muy largos (>10000 caracteres) que podrían indicar mal chunking
    - Chunks muy cortos (<10 caracteres) que podrían ser ruido
    """
    alerts = []

    # =====================================================
    # 0) Duplicidades raras por SHA256 (mismo binario subido muchas veces)
    # =====================================================
    try:
        docs = (
            db.query(Document)
            .filter(Document.case_id == case_id, Document.deleted_at.is_(None))
            .all()
        )
        sha_map: dict[str, list[Document]] = defaultdict(list)
        for d in docs:
            if d.sha256_hash:
                sha_map[d.sha256_hash].append(d)

        rare_binary_duplicates = [(sha, ds) for sha, ds in sha_map.items() if len(ds) >= 3]
        for sha, ds in rare_binary_duplicates[:3]:
            # Tomar 1 chunk de cualquier doc como evidencia
            any_doc = ds[0]
            chunk = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == any_doc.document_id)
                .order_by(DocumentChunk.chunk_index.asc())
                .first()
            )
            if not chunk:
                continue
            evidence = _build_alert_evidence(chunk, db)
            alert_id = _make_alert_id(
                case_id=case_id,
                alert_type=AlertType.SUSPICIOUS_PATTERN.value,
                fingerprint=f"sha256_rare|{sha}|{evidence.chunk_id}",
            )
            filenames = ", ".join(sorted({d.filename for d in ds})[:5])
            alerts.append(
                AnalysisAlert(
                    alert_id=alert_id,
                    case_id=case_id,
                    alert_type=AlertType.SUSPICIOUS_PATTERN,
                    description=(
                        f"Duplicidad rara: el mismo archivo (SHA256) aparece {len(ds)} veces. "
                        f"Ficheros: {filenames}"
                    ),
                    evidence=[evidence],
                    created_at=datetime.utcnow(),
                )
            )
    except Exception:
        # No bloquear el resto de alertas por esto
        pass

    # =====================================================
    # 1) Chunks repetidos en muchos documentos (multi-doc)
    # =====================================================
    content_map: dict[str, list[DocumentChunk]] = defaultdict(list)
    for chunk in chunks:
        if chunk.content and len(chunk.content.strip()) > 80:
            content_map[chunk.content.strip()].append(chunk)

    for content, dup_chunks in content_map.items():
        doc_ids = {c.document_id for c in dup_chunks}
        if len(doc_ids) >= 4:  # multi-doc fuerte
            evidence_list = []
            for c in dup_chunks[:3]:
                try:
                    evidence_list.append(_build_alert_evidence(c, db))
                except ValueError:
                    continue
            if not evidence_list:
                continue
            content_fp = hashlib.sha256(content.encode()).hexdigest()[:12]
            fp = "|".join(sorted({e.chunk_id for e in evidence_list}))
            alert_id = _make_alert_id(
                case_id=case_id,
                alert_type=AlertType.SUSPICIOUS_PATTERN.value,
                fingerprint=f"crossdoc|{content_fp}|{fp}",
            )
            alerts.append(
                AnalysisAlert(
                    alert_id=alert_id,
                    case_id=case_id,
                    alert_type=AlertType.SUSPICIOUS_PATTERN,
                    description=(
                        f"Chunks repetidos en múltiples documentos: mismo contenido aparece en "
                        f"{len(doc_ids)} documentos ({len(dup_chunks)} ocurrencias)."
                    ),
                    evidence=evidence_list,
                    created_at=datetime.utcnow(),
                )
            )
            break  # evitar spamear muchas alertas

    # =====================================================
    # 2) Señales de manipulación / OCR sin texto útil
    # =====================================================
    try:
        suspicious_ocr_chunks = [
            c
            for c in chunks
            if (c.extraction_method == "ocr")
            and c.content
            and (
                "tesseract" in c.content.lower()
                or "error" in c.content.lower()
                or len(c.content.strip()) < 80
            )
        ]
        if len(suspicious_ocr_chunks) >= 2:
            evidence_list = []
            for c in suspicious_ocr_chunks[:3]:
                try:
                    evidence_list.append(_build_alert_evidence(c, db))
                except ValueError:
                    continue
            if evidence_list:
                fp = "|".join(sorted({e.chunk_id for e in evidence_list}))
                alert_id = _make_alert_id(
                    case_id=case_id,
                    alert_type=AlertType.SUSPICIOUS_PATTERN.value,
                    fingerprint=f"ocr_quality|{fp}",
                )
                alerts.append(
                    AnalysisAlert(
                        alert_id=alert_id,
                        case_id=case_id,
                        alert_type=AlertType.SUSPICIOUS_PATTERN,
                        description=(
                            "Señal de manipulación/calidad: varios documentos OCR con poco texto útil "
                            "o mensajes de error (posible OCR fallido / documentos escaneados sin texto)."
                        ),
                        evidence=evidence_list,
                        created_at=datetime.utcnow(),
                    )
                )
    except Exception:
        pass

    # =====================================================
    # 3) Inconsistencias temporales (fechas imposibles / futuras)
    # =====================================================
    date_pattern = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})")
    today = datetime.utcnow().date()
    future_cutoff = today + timedelta(days=30)
    ancient_cutoff_year = 1900

    temporal_evidence = []
    for chunk in chunks:
        if not chunk.content:
            continue
        m = date_pattern.search(chunk.content)
        if not m:
            continue
        day, month, year = m.groups()
        try:
            dt = datetime(int(year), int(month), int(day)).date()
        except Exception:
            continue
        if dt > future_cutoff or dt.year < ancient_cutoff_year:
            try:
                temporal_evidence.append(_build_alert_evidence(chunk, db))
            except ValueError:
                pass
        if len(temporal_evidence) >= 3:
            break

    if temporal_evidence:
        fp = "|".join(sorted({e.chunk_id for e in temporal_evidence}))
        alert_id = _make_alert_id(
            case_id=case_id,
            alert_type=AlertType.TEMPORAL_INCONSISTENCY.value,
            fingerprint=f"temporal|{fp}",
        )
        alerts.append(
            AnalysisAlert(
                alert_id=alert_id,
                case_id=case_id,
                alert_type=AlertType.TEMPORAL_INCONSISTENCY,
                description=(
                    "Inconsistencia temporal: se detectaron fechas improbables (muy antiguas o futuras) "
                    "en el contenido de algunos documentos."
                ),
                evidence=temporal_evidence,
                created_at=datetime.utcnow(),
            )
        )

    # =====================================================
    # 4) Patrones financieros básicos (importes repetidos)
    # =====================================================
    amount_pattern = re.compile(r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*€")
    amount_counts: dict[str, int] = defaultdict(int)
    amount_chunk: dict[str, DocumentChunk] = {}

    for chunk in chunks:
        if not chunk.content:
            continue
        for m in amount_pattern.findall(chunk.content):
            norm = m.replace(".", "").replace(",", ".")
            amount_counts[norm] += 1
            amount_chunk.setdefault(norm, chunk)

    repeated_amounts = [(a, c) for a, c in amount_counts.items() if c >= 5]
    if repeated_amounts:
        repeated_amounts.sort(key=lambda x: x[1], reverse=True)
        a, c = repeated_amounts[0]
        try:
            evidence = _build_alert_evidence(amount_chunk[a], db)
            alert_id = _make_alert_id(
                case_id=case_id,
                alert_type=AlertType.SUSPICIOUS_PATTERN.value,
                fingerprint=f"repeated_amount|{a}|{evidence.chunk_id}",
            )
            alerts.append(
                AnalysisAlert(
                    alert_id=alert_id,
                    case_id=case_id,
                    alert_type=AlertType.SUSPICIOUS_PATTERN,
                    description=(
                        f"Patrón financiero: importe repetido {c} veces (≈ {a} €). "
                        "Puede indicar duplicidad, redondeos sistemáticos o registro irregular."
                    ),
                    evidence=[evidence],
                    created_at=datetime.utcnow(),
                )
            )
        except Exception:
            pass

    # =====================================================
    # 5) Patrimonial: ventas de activos cercanas a embargo (heurística via timeline_builder)
    # =====================================================
    try:
        from app.services.timeline_builder import EventType, build_timeline

        tl = build_timeline(db, case_id, concurso_date=None)
        embargo_dates = [
            e.date for e in tl.events if getattr(e, "event_type", None) == EventType.EMBARGO
        ]
        venta_events = [
            e for e in tl.events if getattr(e, "event_type", None) == EventType.VENTA_ACTIVO
        ]
        if embargo_dates and venta_events:
            embargo_date = sorted(embargo_dates)[0]
            window_start = embargo_date - timedelta(days=120)
            candidates = [e for e in venta_events if window_start <= e.date <= embargo_date]
            if candidates:
                # Evidencia: usar chunk_id del evidence del evento si existe
                ev = candidates[0]
                chunk_id = getattr(getattr(ev, "evidence", None), "chunk_id", None)
                chunk = None
                if chunk_id:
                    chunk = (
                        db.query(DocumentChunk).filter(DocumentChunk.chunk_id == chunk_id).first()
                    )
                if not chunk:
                    # fallback: primer chunk del doc
                    doc_id = getattr(getattr(ev, "evidence", None), "document_id", None)
                    if doc_id:
                        chunk = (
                            db.query(DocumentChunk)
                            .filter(DocumentChunk.document_id == doc_id)
                            .order_by(DocumentChunk.chunk_index.asc())
                            .first()
                        )
                if chunk:
                    evidence = _build_alert_evidence(chunk, db)
                    alert_id = _make_alert_id(
                        case_id=case_id,
                        alert_type=AlertType.SUSPICIOUS_PATTERN.value,
                        fingerprint=f"patrimonial_window|{evidence.chunk_id}",
                    )
                    alerts.append(
                        AnalysisAlert(
                            alert_id=alert_id,
                            case_id=case_id,
                            alert_type=AlertType.SUSPICIOUS_PATTERN,
                            description=(
                                "Patrimonial: se detecta posible venta/enajenación de activo cercana a un embargo "
                                "(ventana ≤120 días). Revisar trazabilidad."
                            ),
                            evidence=[evidence],
                            created_at=datetime.utcnow(),
                        )
                    )
    except Exception:
        pass

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
            fp = "|".join(sorted({e.chunk_id for e in evidence_list}))
            alert_id = _make_alert_id(
                case_id=case_id,
                alert_type=AlertType.SUSPICIOUS_PATTERN.value,
                fingerprint=f"very_long_chunks|{fp}",
            )

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
            fp = "|".join(sorted({e.chunk_id for e in evidence_list}))
            alert_id = _make_alert_id(
                case_id=case_id,
                alert_type=AlertType.SUSPICIOUS_PATTERN.value,
                fingerprint=f"very_short_chunks|{fp}",
            )

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


def _detect_duplicate_documents_sha256(
    case_id: str, chunks: list[DocumentChunk], db: Session
) -> list[AnalysisAlert]:
    """
    Contabilidad / higiene documental:
    - Duplicados exactos por SHA256 (mismo binario) con umbral >=2.

    Nota: esto NO es “sospechoso”, es un problema técnico de duplicidad.
    """
    alerts: list[AnalysisAlert] = []
    docs = (
        db.query(Document).filter(Document.case_id == case_id, Document.deleted_at.is_(None)).all()
    )
    sha_map: dict[str, list[Document]] = defaultdict(list)
    for d in docs:
        if d.sha256_hash:
            sha_map[d.sha256_hash].append(d)

    duplicates = [(sha, ds) for sha, ds in sha_map.items() if len(ds) >= 2]
    for sha, ds in duplicates[:5]:
        # Evidencia: 1-2 chunks de esos documentos
        ev_chunks: list[DocumentChunk] = []
        for d in ds[:2]:
            c = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == d.document_id)
                .order_by(DocumentChunk.chunk_index.asc())
                .first()
            )
            if c:
                ev_chunks.append(c)
        evidence = _build_evidence_list(chunks=ev_chunks, db=db, limit=2)
        if not evidence:
            continue
        filenames = ", ".join(sorted({d.filename for d in ds})[:6])
        alert_id = _make_alert_id(
            case_id=case_id,
            alert_type=AlertType.DUPLICATED_DATA.value,
            fingerprint=f"sha256_exact|{sha}",
        )
        alerts.append(
            AnalysisAlert(
                alert_id=alert_id,
                case_id=case_id,
                alert_type=AlertType.DUPLICATED_DATA,
                description=(
                    f"Duplicado exacto (SHA256): se detectaron {len(ds)} documentos con el mismo binario. "
                    f"Ficheros: {filenames}"
                ),
                evidence=evidence,
                created_at=datetime.utcnow(),
            )
        )
    return alerts


def _detect_tgss_alerts(
    case_id: str, chunks: list[DocumentChunk], db: Session
) -> list[AnalysisAlert]:
    """
    TGSS (determinista, técnico):
    - Detecta providencia/apremio/embargo por keywords.
    - Extrae periodos YYYY-MM y detecta consecutividad básica.
    - Extrae importes € cuando estén presentes (aprox).
    - Genera alerta adicional de “faltan RNT/RLC” anclada a evidencia TGSS si aplica.
    """
    alerts: list[AnalysisAlert] = []

    # Map doc_id -> Document (para filename/doc_type)
    docs = (
        db.query(Document).filter(Document.case_id == case_id, Document.deleted_at.is_(None)).all()
    )
    doc_map: dict[str, Document] = {d.document_id: d for d in docs}

    tgss_needles = [
        "tgss",
        "tesorería general de la seguridad social",
        "tesoreria general de la seguridad social",
        "providencia",
        "apremio",
        "embargo",
        "expediente",
        "recargo",
        "cuotas no ingresadas",
    ]

    tgss_chunks: list[DocumentChunk] = []
    for c in chunks:
        if not c.content:
            continue
        doc = doc_map.get(c.document_id)
        fname = (doc.filename if doc else "") or ""
        dtype = (getattr(doc, "doc_type", None) or "") if doc else ""
        if dtype in ("TGSS", "PROVIDENCIA_APREMIO"):
            tgss_chunks.append(c)
            continue
        if _contains_any(fname, ["tgss", "apremio", "providencia"]) or _contains_any(
            c.content, tgss_needles
        ):
            tgss_chunks.append(c)

    if tgss_chunks:
        # Periodos YYYY-MM
        period_pat = re.compile(r"\b(20\d{2})[-/](0[1-9]|1[0-2])\b")
        periods: set[str] = set()
        for c in tgss_chunks:
            for y, m in period_pat.findall(c.content or ""):
                periods.add(f"{y}-{m}")
        periods_sorted = sorted(periods)

        # Consecutividad: medir longitud máxima de run
        def _to_int(p: str) -> int:
            y, m = p.split("-")
            return int(y) * 12 + (int(m) - 1)

        max_run = 0
        run = 1
        for i in range(1, len(periods_sorted)):
            if _to_int(periods_sorted[i]) == _to_int(periods_sorted[i - 1]) + 1:
                run += 1
            else:
                max_run = max(max_run, run)
                run = 1
        max_run = max(max_run, run) if periods_sorted else 0

        # Importe principal (heurística: “Importe principal reclamado: X €”)
        euro_pat = re.compile(r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*€")
        principal_amount = None
        for c in tgss_chunks:
            txt = c.content or ""
            if "importe principal" in txt.lower():
                m = euro_pat.search(txt)
                if m:
                    raw = m.group(1).replace(".", "").replace(",", ".")
                    try:
                        principal_amount = float(raw)
                        break
                    except Exception:
                        pass

        # Evidencia: chunks TGSS más “densos” (mencionan TGSS/apremio/periodo)
        densos = []
        for c in tgss_chunks:
            t = (c.content or "").lower()
            score = 0
            score += 2 if "tgss" in t else 0
            score += 2 if "apremio" in t or "providencia" in t else 0
            score += 1 if "periodo" in t or "periodo reclamado" in t else 0
            score += 1 if "€" in t else 0
            densos.append((score, c))
        densos.sort(key=lambda x: x[0], reverse=True)
        ev_chunks = [c for _, c in densos[:3]]
        evidence = _build_evidence_list(chunks=ev_chunks, db=db, limit=3)
        if evidence:
            parts = []
            parts.append(
                "TGSS: se detecta referencia a providencia/apremio/embargo en documentación."
            )
            if principal_amount is not None:
                parts.append(
                    f"Importe principal aproximado: {principal_amount:,.2f} €".replace(",", "X")
                    .replace(".", ",")
                    .replace("X", ".")
                )
            if periods_sorted:
                if max_run >= 2:
                    parts.append(
                        f"Periodos detectados: {periods_sorted[0]}…{periods_sorted[-1]} (máx. consecutivos: {max_run})."
                    )
                else:
                    parts.append(
                        f"Periodos detectados: {', '.join(periods_sorted[:8])}{'…' if len(periods_sorted) > 8 else ''}."
                    )

            desc = " ".join(parts)
            fp = hashlib.sha256(
                ("|".join(sorted({e.chunk_id for e in evidence})) + "|" + desc).encode()
            ).hexdigest()[:16]
            alert_id = _make_alert_id(
                case_id=case_id,
                alert_type=AlertType.SUSPICIOUS_PATTERN.value,
                fingerprint=f"tgss|{fp}",
            )
            alerts.append(
                AnalysisAlert(
                    alert_id=alert_id,
                    case_id=case_id,
                    alert_type=AlertType.SUSPICIOUS_PATTERN,
                    description=desc,
                    evidence=evidence,
                    created_at=datetime.utcnow(),
                )
            )

        # Faltantes asociados: RNT/RLC
        # Regla técnica: si hay señal TGSS, y no hay documentos que parezcan RNT/RLC, alertar.
        have_rnt_rlc = False
        for d in docs:
            fn = (d.filename or "").lower()
            if "rnt" in fn or "rlc" in fn:
                have_rnt_rlc = True
                break
        if not have_rnt_rlc:
            # Evidencia: anclar al mismo soporte TGSS (no inventar “ausencia” sin ancla)
            if evidence:
                fp = "|".join(sorted({e.chunk_id for e in evidence}))
                miss_id = _make_alert_id(
                    case_id=case_id,
                    alert_type=AlertType.MISSING_DATA.value,
                    fingerprint=f"missing_rnt_rlc|{fp}",
                )
                alerts.append(
                    AnalysisAlert(
                        alert_id=miss_id,
                        case_id=case_id,
                        alert_type=AlertType.MISSING_DATA,
                        description=(
                            "Documentación faltante (asociada a TGSS): no se localizaron RNT/RLC en el expediente "
                            "para contrastar cuotas/devengos del periodo afectado."
                        ),
                        evidence=evidence[:1],
                        created_at=datetime.utcnow(),
                    )
                )

        # Faltantes asociados: soporte de aplazamiento/fraccionamiento (si aplica)
        have_aplazamiento = False
        for d in docs:
            fn = (d.filename or "").lower()
            dtype = getattr(d, "doc_type", None) or ""
            if dtype == "APLAZAMIENTO_FRACCIONAMIENTO":
                have_aplazamiento = True
                break
            if "aplaz" in fn or "fraccion" in fn:
                have_aplazamiento = True
                break
        if not have_aplazamiento and evidence:
            fp = "|".join(sorted({e.chunk_id for e in evidence}))
            miss_id = _make_alert_id(
                case_id=case_id,
                alert_type=AlertType.MISSING_DATA.value,
                fingerprint=f"missing_aplazamiento|{fp}",
            )
            alerts.append(
                AnalysisAlert(
                    alert_id=miss_id,
                    case_id=case_id,
                    alert_type=AlertType.MISSING_DATA,
                    description=(
                        "TGSS (soporte asociado): no se localiza documentación de aplazamiento/fraccionamiento vinculada "
                        "al expediente (si existe, incorporarla para contextualizar el estado de la deuda)."
                    ),
                    evidence=evidence[:1],
                    created_at=datetime.utcnow(),
                )
            )

    return alerts


def _detect_bank_alerts(
    case_id: str, chunks: list[DocumentChunk], db: Session
) -> list[AnalysisAlert]:
    """
    Banco (determinista, técnico):
    - Pagos a vinculadas (matching por nombre/CIF)
    - Conceptos genéricos
    - Retiradas de efectivo
    - Fraccionamientos repetidos (heurística simple)
    - Ventana TGSS ↔ Banco (60–180 días) como patrón adicional si aplica
    """
    alerts: list[AnalysisAlert] = []

    docs = (
        db.query(Document).filter(Document.case_id == case_id, Document.deleted_at.is_(None)).all()
    )
    doc_map: dict[str, Document] = {d.document_id: d for d in docs}

    bank_docs = set()
    for d in docs:
        if getattr(d, "doc_type", None) in ("EXTRACTO_BANCARIO", "CUENTA_BANCARIA"):
            bank_docs.add(d.document_id)
        if _contains_any(d.filename, ["extracto", "bancario", "iban"]):
            bank_docs.add(d.document_id)

    if not bank_docs:
        return alerts

    linked_needles = ["grupo xyz", "grupo xyz sl", "b-99112233", "b 99112233"]
    generic_concepts = [
        "servicios",
        "varios",
        "consultoría",
        "consultoria",
        "préstamo socio",
        "prestamo socio",
        "gestión",
        "gestion",
        "soporte",
        "anticipo",
    ]
    cash_needles = ["reintegro", "cajero", "efectivo"]

    # Intentar obtener una fecha “ancla” TGSS para correlación temporal (60–180 días)
    tgss_anchor_date = None
    tgss_chunks = [
        c
        for c in chunks
        if c.content
        and (
            _contains_any(
                c.content,
                [
                    "tesorería general de la seguridad social",
                    "tesoreria general de la seguridad social",
                    "tgss",
                ],
            )
            or _contains_any(
                (doc_map.get(c.document_id).filename if doc_map.get(c.document_id) else ""),
                ["tgss", "apremio", "providencia"],
            )
        )
    ]
    dmy_pat = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")
    for c in tgss_chunks[:50]:
        for m in dmy_pat.findall(c.content or ""):
            dd, mm, yyyy = m
            try:
                dt = datetime(int(yyyy), int(mm), int(dd)).date()
            except Exception:
                continue
            tgss_anchor_date = dt
            break
        if tgss_anchor_date:
            break

    ev_candidates: list[DocumentChunk] = []
    hits_linked = 0
    hits_generic = 0
    hits_cash = 0

    # Recoger chunks relevantes y contar señales
    for c in chunks:
        if c.document_id not in bank_docs:
            continue
        txt = c.content or ""
        t = txt.lower()
        if any(n in t for n in linked_needles):
            hits_linked += 1
            ev_candidates.append(c)
        if any(n in t for n in generic_concepts):
            hits_generic += 1
            ev_candidates.append(c)
        if any(n in t for n in cash_needles):
            hits_cash += 1
            ev_candidates.append(c)

    # Dedup candidates manteniendo orden
    seen = set()
    uniq: list[DocumentChunk] = []
    for c in ev_candidates:
        if c.chunk_id in seen:
            continue
        seen.add(c.chunk_id)
        uniq.append(c)
    evidence = _build_evidence_list(chunks=uniq, db=db, limit=3)
    if not evidence:
        return alerts

    # Ventana TGSS ↔ Banco (60–180 días desde TGSS): heurística por fechas en extracto
    # Nota: si el extractor no conserva fechas, esta parte no dispara (no inventamos).
    iso_pat = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
    window_hits = 0
    if tgss_anchor_date:
        for c in uniq[:40]:
            txt = c.content or ""
            for y, m, d in iso_pat.findall(txt):
                try:
                    dt = datetime(int(y), int(m), int(d)).date()
                except Exception:
                    continue
                delta = (dt - tgss_anchor_date).days
                if 60 <= abs(delta) <= 180:
                    # Solo contamos si además es pago a vinculada o efectivo (para no inflar)
                    tl = txt.lower()
                    if any(n in tl for n in linked_needles) or any(n in tl for n in cash_needles):
                        window_hits += 1
                        break
            if window_hits:
                break

    # Fraccionamientos: si hay varias menciones a la misma contraparte + importes repetidos
    amount_pat = re.compile(r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*€")
    amount_counts: dict[str, int] = defaultdict(int)
    for c in uniq[:15]:
        for m in amount_pat.findall(c.content or ""):
            norm = m.replace(".", "").replace(",", ".")
            amount_counts[norm] += 1
    repeated_amounts = [(a, c) for a, c in amount_counts.items() if c >= 2]
    repeated_amounts.sort(key=lambda x: x[1], reverse=True)

    parts = []
    parts.append("Banco: se detectan movimientos con señales técnicas a revisar.")
    if hits_linked:
        # Usar 'vinculadas' explícito para facilitar correlación/UX en capa despacho.
        parts.append(f"Pagos a vinculadas (matching nombre/CIF): {hits_linked} mención(es).")
    if hits_generic:
        parts.append(f"Conceptos genéricos (p.ej. 'servicios'): {hits_generic} mención(es).")
    if hits_cash:
        parts.append(f"Retiradas de efectivo/cajero: {hits_cash} mención(es).")
    if repeated_amounts:
        a, ccount = repeated_amounts[0]
        parts.append(
            f"Importe repetido (heurística fraccionamiento): {ccount} ocurrencias (≈ {a} €)."
        )
    if window_hits:
        parts.append(
            "Correlación temporal TGSS↔Banco: se detectan movimientos en ventana 60–180 días desde una fecha TGSS localizada."
        )

    desc = " ".join(parts)
    fp = "|".join(sorted({e.chunk_id for e in evidence}))
    alert_id = _make_alert_id(
        case_id=case_id, alert_type=AlertType.SUSPICIOUS_PATTERN.value, fingerprint=f"bank|{fp}"
    )
    alerts.append(
        AnalysisAlert(
            alert_id=alert_id,
            case_id=case_id,
            alert_type=AlertType.SUSPICIOUS_PATTERN,
            description=desc,
            evidence=evidence,
            created_at=datetime.utcnow(),
        )
    )
    return alerts


def _detect_accounting_alerts(
    case_id: str, chunks: list[DocumentChunk], db: Session
) -> list[AnalysisAlert]:
    """
    Contabilidad (determinista, técnico):
    - Factura mal pagada (total factura != importe pagado) cuando hay soporte
    - Descuadres/IVA soportado incoherente (heurística)
    """
    alerts: list[AnalysisAlert] = []

    # Buscar por invoice_no y totales/pagos en chunks
    inv_no_pat = re.compile(r"\b([A-Z]{1,3}-\d{4}-\d{2,6})\b")
    euro_pat = re.compile(r"(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*€")

    inv_total: dict[str, float] = {}
    inv_total_chunk: dict[str, DocumentChunk] = {}
    inv_paid: dict[str, float] = {}
    inv_paid_chunk: dict[str, DocumentChunk] = {}

    # Para casi-duplicados: invoice_no -> set(document_id)
    inv_docs: dict[str, set[str]] = defaultdict(set)
    inv_doc_sample_chunk: dict[str, DocumentChunk] = {}

    for c in chunks:
        txt = c.content or ""
        if len(txt) < 20:
            continue
        m = inv_no_pat.search(txt)
        if not m:
            continue
        inv = m.group(1)
        inv_docs[inv].add(c.document_id)
        inv_doc_sample_chunk.setdefault(inv, c)
        tl = txt.lower()
        if "total" in tl and inv not in inv_total:
            # intentar capturar “TOTAL: X €”
            # (si hay múltiples €, tomamos el último del bloque como heurística)
            ms = euro_pat.findall(txt)
            if ms:
                raw = ms[-1].replace(".", "").replace(",", ".")
                try:
                    inv_total[inv] = float(raw)
                    inv_total_chunk[inv] = c
                except Exception:
                    pass
        if ("importe pagado" in tl or "abonado" in tl) and inv not in inv_paid:
            ms = euro_pat.findall(txt)
            if ms:
                raw = ms[0].replace(".", "").replace(",", ".")
                try:
                    inv_paid[inv] = float(raw)
                    inv_paid_chunk[inv] = c
                except Exception:
                    pass

    # Detectar discrepancias (mal pagada / pago parcial)
    for inv, total in inv_total.items():
        paid = inv_paid.get(inv)
        if paid is None:
            continue
        if abs(total - paid) < 0.01:
            continue
        ev_chunks = [inv_total_chunk.get(inv), inv_paid_chunk.get(inv)]
        ev_chunks = [c for c in ev_chunks if c is not None]
        evidence = _build_evidence_list(chunks=ev_chunks, db=db, limit=2)
        if not evidence:
            continue
        desc = (
            (
                f"Contabilidad: discrepancia de pago detectada para {inv}. "
                f"TOTAL factura ≈ {total:,.2f} € vs importe pagado ≈ {paid:,.2f} €."
            )
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
        fp = "|".join(sorted({e.chunk_id for e in evidence}))
        alert_id = _make_alert_id(
            case_id=case_id,
            alert_type=AlertType.INCONSISTENT_DATA.value,
            fingerprint=f"mispaid|{inv}|{fp}",
        )
        alerts.append(
            AnalysisAlert(
                alert_id=alert_id,
                case_id=case_id,
                alert_type=AlertType.INCONSISTENT_DATA,
                description=desc,
                evidence=evidence,
                created_at=datetime.utcnow(),
            )
        )
        break  # evitar spam

    # Casi-duplicados (heurística mínima): mismo número de factura en >=2 documentos distintos,
    # excluyendo el caso factura+justificante (si el justificante también incluye el número).
    for inv, doc_ids in inv_docs.items():
        if len(doc_ids) < 2:
            continue
        # Heurística de filtro: exigir que al menos uno de los documentos parezca factura
        # (por filename o por presencia de "Factura" / "Nº factura" en el chunk).
        sample_chunk = inv_doc_sample_chunk.get(inv)
        if not sample_chunk:
            continue
        if not _contains_any(
            sample_chunk.content or "",
            ["factura", "nº factura", "número factura", "numero factura"],
        ):
            continue
        # Evitar false positive con justificante: si aparece “justificante” en chunk, saltar
        if _contains_any(sample_chunk.content or "", ["justificante"]):
            continue
        evidence = _build_evidence_list(chunks=[sample_chunk], db=db, limit=1)
        if not evidence:
            continue
        fp = f"{inv}|{'|'.join(sorted(doc_ids))}"
        alert_id = _make_alert_id(
            case_id=case_id,
            alert_type=AlertType.DUPLICATED_DATA.value,
            fingerprint=f"invoice_no_dup|{fp}",
        )
        alerts.append(
            AnalysisAlert(
                alert_id=alert_id,
                case_id=case_id,
                alert_type=AlertType.DUPLICATED_DATA,
                description=(
                    f"Contabilidad: posible duplicidad por número de factura ({inv}) detectada en múltiples documentos "
                    f"({len(doc_ids)} documentos)."
                ),
                evidence=evidence,
                created_at=datetime.utcnow(),
            )
        )
        break

    # Heurística IVA soportado incoherente (CSV / texto)
    iva_chunks = []
    for c in chunks:
        txt = (c.content or "").lower()
        if "iva soportado" in txt and ("472000" in txt or "472" in txt):
            iva_chunks.append(c)
        # también: “472000” y “haber”/“debe” en la misma línea (según extractor)
        if "472000" in txt and ("debe" in txt or "haber" in txt):
            iva_chunks.append(c)
    # Dedup
    seen = set()
    iva_unique = []
    for c in iva_chunks:
        if c.chunk_id in seen:
            continue
        seen.add(c.chunk_id)
        iva_unique.append(c)
    if iva_unique:
        evidence = _build_evidence_list(chunks=iva_unique, db=db, limit=2)
        if evidence:
            fp = "|".join(sorted({e.chunk_id for e in evidence}))
            alert_id = _make_alert_id(
                case_id=case_id,
                alert_type=AlertType.INCONSISTENT_DATA.value,
                fingerprint=f"iva|{fp}",
            )
            alerts.append(
                AnalysisAlert(
                    alert_id=alert_id,
                    case_id=case_id,
                    alert_type=AlertType.INCONSISTENT_DATA,
                    description=(
                        "Contabilidad: posible incoherencia en IVA soportado detectada en apuntes/tabla "
                        "(heurística: revisar debe/haber y soporte documental)."
                    ),
                    evidence=evidence,
                    created_at=datetime.utcnow(),
                )
            )

    # Asientos sin tercero / sin CIF (heurística mínima)
    no_third_party = []
    for c in chunks:
        txt = c.content or ""
        tl = txt.lower()
        # CSV típico: "... ,CAJERO,,2000.00,0.00"
        if ",," in txt and ("cajero" in tl or "tercero_cif" in tl):
            no_third_party.append(c)
    # Dedup + evidencia
    seen = set()
    uniq_ntp = []
    for c in no_third_party:
        if c.chunk_id in seen:
            continue
        seen.add(c.chunk_id)
        uniq_ntp.append(c)
    if uniq_ntp:
        evidence = _build_evidence_list(chunks=uniq_ntp, db=db, limit=2)
        if evidence:
            fp = "|".join(sorted({e.chunk_id for e in evidence}))
            alert_id = _make_alert_id(
                case_id=case_id,
                alert_type=AlertType.MISSING_DATA.value,
                fingerprint=f"missing_third_party|{fp}",
            )
            alerts.append(
                AnalysisAlert(
                    alert_id=alert_id,
                    case_id=case_id,
                    alert_type=AlertType.MISSING_DATA,
                    description=(
                        "Contabilidad: se detectan apuntes/asientos sin tercero identificable (CIF/NIF vacío o no informado). "
                        "Puede impedir trazabilidad si no se completa el soporte."
                    ),
                    evidence=evidence,
                    created_at=datetime.utcnow(),
                )
            )

    return alerts


def _detect_core_docs_missing_alerts(
    case_id: str, chunks: list[DocumentChunk], db: Session
) -> list[AnalysisAlert]:
    """
    Documentación faltante (catálogo core) — sin acusar.

    Importante:
    - El contrato exige evidencia física.
    - Por tanto, anclamos la alerta a un documento “relacionado” (p.ej. extracto bancario)
      cuando el faltante es complementario (p.ej. conciliación bancaria).
    """
    alerts: list[AnalysisAlert] = []
    docs = (
        db.query(Document).filter(Document.case_id == case_id, Document.deleted_at.is_(None)).all()
    )
    filenames = [d.filename.lower() for d in docs]

    def _have_any(pats: list[str]) -> bool:
        return any(any(p in fn for p in pats) for fn in filenames)

    # Catálogo mínimo (heurístico por filename/doc_type)
    missing: list[tuple[str, list[str], list[str]]] = []
    # (label, required filename needles, anchor filename needles for evidence)
    if not _have_any(["conciliacion", "conciliación"]):
        missing.append(
            ("conciliación bancaria", ["conciliacion", "conciliación"], ["extracto", "bancario"])
        )
    if not _have_any(["balance", "sumas", "saldos"]):
        missing.append(
            (
                "balance / sumas y saldos",
                ["balance", "sumas", "saldos"],
                ["factura", "extracto", "bancario"],
            )
        )
    if not _have_any(["pyg", "p&g", "p y g", "pérdidas", "ganancias"]):
        missing.append(
            (
                "cuenta de pérdidas y ganancias (PyG)",
                ["pyg", "p&g", "perdidas", "ganancias"],
                ["balance", "sumas", "saldos"],
            )
        )

    if not missing:
        return alerts

    # Buscar evidencia ancla: primer chunk de un doc que encaje con anchors
    # (si no hay evidencia, no se genera la alerta: no se inventa).
    for label, _req, anchors in missing[:3]:
        anchor_docs = [d for d in docs if _contains_any(d.filename, anchors)]
        if not anchor_docs:
            continue
        d0 = anchor_docs[0]
        c0 = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == d0.document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .first()
        )
        if not c0:
            continue
        evidence = _build_evidence_list(chunks=[c0], db=db, limit=1)
        if not evidence:
            continue
        fp = evidence[0].chunk_id
        alert_id = _make_alert_id(
            case_id=case_id,
            alert_type=AlertType.MISSING_DATA.value,
            fingerprint=f"core_missing|{label}|{fp}",
        )
        alerts.append(
            AnalysisAlert(
                alert_id=alert_id,
                case_id=case_id,
                alert_type=AlertType.MISSING_DATA,
                description=(
                    f"Documentación faltante (core): no se localiza {label} en el expediente. "
                    "Recomendación técnica: incorporar o confirmar si existe en otra carpeta/versión."
                ),
                evidence=evidence,
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

    # =====================================================
    # FASE 2 — Detectores por categoría (técnicos, deterministas)
    # =====================================================
    all_alerts.extend(_detect_duplicate_documents_sha256(case_id, chunks, db))
    all_alerts.extend(_detect_tgss_alerts(case_id, chunks, db))
    all_alerts.extend(_detect_bank_alerts(case_id, chunks, db))
    all_alerts.extend(_detect_accounting_alerts(case_id, chunks, db))
    all_alerts.extend(_detect_core_docs_missing_alerts(case_id, chunks, db))

    # Orden por scoring interno (no expuesto)
    # Si scores empatan, mantener orden determinista por alert_id.
    all_alerts.sort(key=lambda a: (_score_internal(a), a.alert_id), reverse=True)

    return all_alerts


# =========================================================
# ENDPOINTS PROHIBIDOS (NO IMPLEMENTADOS)
# =========================================================

# POST /cases/{case_id}/analysis/alerts → PROHIBIDO (no se crean alertas manualmente)
# PUT /cases/{case_id}/analysis/alerts/{alert_id} → PROHIBIDO (no se editan alertas)
# DELETE /cases/{case_id}/analysis/alerts/{alert_id} → PROHIBIDO (no se borran alertas)
# POST /cases/{case_id}/analysis/interpret → PROHIBIDO (no interpretación legal)
# POST /cases/{case_id}/analysis/llm → PROHIBIDO (no LLM)
