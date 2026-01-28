"""
Sistema de Timeline Completo y Robusto (Fase B2).

OBJETIVO:
Reconstruir cronológicamente TODOS los eventos críticos del caso concursal
con trazabilidad probatoria completa y detección automática de tipos de evento.

MEJORAS sobre extract_timeline_from_documents():
1. Extracción avanzada de fechas (múltiples formatos, contexto temporal)
2. Detección automática de 15+ tipos de eventos críticos
3. Clasificación de importancia/severidad
4. Relaciones entre eventos (causalidad, precedencia)
5. Análisis de gaps temporales sospechosos
6. Validación de coherencia temporal

CASOS DE USO:
- Detectar "periodo sospechoso" (2 años antes de concurso)
- Identificar pagos preferentes cronológicamente
- Reconstruir secuencia de alzamiento de bienes
- Analizar timeline de incumplimientos
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.financial_analysis import Evidence

# =========================================================
# ENUMS Y TIPOS
# =========================================================


class EventType(str, Enum):
    """Tipos de eventos en el timeline concursal."""

    # Eventos financieros
    FACTURA_EMITIDA = "factura_emitida"
    FACTURA_RECIBIDA = "factura_recibida"
    FACTURA_VENCIDA = "factura_vencida"
    PAGO_REALIZADO = "pago_realizado"
    PAGO_RECIBIDO = "pago_recibido"

    # Eventos legales
    EMBARGO = "embargo"
    RECLAMACION = "reclamacion"
    DEMANDA = "demanda"
    SENTENCIA = "sentencia"
    REQUERIMIENTO = "requerimiento"

    # Eventos corporativos
    ACUERDO_JUNTA = "acuerdo_junta"
    NOMBRAMIENTO_ADMINISTRADOR = "nombramiento_administrador"
    CESE_ADMINISTRADOR = "cese_administrador"

    # Eventos patrimoniales
    VENTA_ACTIVO = "venta_activo"
    COMPRA_ACTIVO = "compra_activo"
    TRANSMISION_PARTICIPACIONES = "transmision_participaciones"
    CONSTITUCION_GARANTIA = "constitucion_garantia"

    # Eventos contables
    CIERRE_EJERCICIO = "cierre_ejercicio"
    APROBACION_CUENTAS = "aprobacion_cuentas"

    # Eventos de crisis
    IMPAGO = "impago"
    SUSPENSION_PAGOS = "suspension_pagos"
    SOLICITUD_CONCURSO = "solicitud_concurso"

    # Genérico
    OTRO = "otro"


class EventSeverity(str, Enum):
    """Severidad/importancia del evento."""

    CRITICAL = "critical"  # Evento crítico para el caso
    HIGH = "high"  # Muy relevante
    MEDIUM = "medium"  # Relevante
    LOW = "low"  # Informativo


class EventCategory(str, Enum):
    """Categoría del evento."""

    FINANCIAL = "financial"  # Financiero/económico
    LEGAL = "legal"  # Legal/procesal
    CORPORATE = "corporate"  # Corporativo/societario
    PATRIMONIAL = "patrimonial"  # Patrimonial
    ACCOUNTING = "accounting"  # Contable
    CRISIS = "crisis"  # De crisis/insolvencia


# =========================================================
# MODELOS MEJORADOS
# =========================================================


class TimelineEvent(BaseModel):
    """
    Evento en el timeline con metadata completo.
    """

    date: datetime = Field(..., description="Fecha del evento")
    event_type: EventType = Field(..., description="Tipo de evento")
    category: EventCategory = Field(..., description="Categoría del evento")
    severity: EventSeverity = Field(..., description="Severidad/importancia")
    title: str = Field(..., description="Título descriptivo corto")
    description: str = Field(..., description="Descripción detallada")
    amount: Optional[float] = Field(None, description="Importe asociado (si aplica)")
    parties: list[str] = Field(default_factory=list, description="Partes involucradas")
    evidence: Evidence = Field(..., description="Evidencia probatoria")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confianza 0-1")

    # Metadata adicional
    is_within_suspect_period: Optional[bool] = Field(
        None, description="¿Dentro de periodo sospechoso?"
    )
    related_event_ids: list[str] = Field(
        default_factory=list, description="IDs de eventos relacionados"
    )
    tags: list[str] = Field(default_factory=list, description="Tags para filtrado")

    class Config:
        extra = "forbid"


class Timeline(BaseModel):
    """Timeline completo del caso."""

    events: list[TimelineEvent] = Field(default_factory=list)
    start_date: Optional[datetime] = Field(None, description="Fecha más antigua")
    end_date: Optional[datetime] = Field(None, description="Fecha más reciente")
    total_events: int = Field(0, description="Total de eventos")
    suspect_period_start: Optional[datetime] = Field(None, description="Inicio periodo sospechoso")
    gaps: list[dict] = Field(default_factory=list, description="Gaps temporales detectados")

    class Config:
        extra = "forbid"


# =========================================================
# EXTRACCIÓN AVANZADA DE FECHAS
# =========================================================


def extract_dates_advanced(text: str, filename: str = "") -> list[tuple[datetime, float, str]]:
    """
    Extrae fechas del texto con múltiples formatos y contexto.

    Args:
        text: Texto donde buscar fechas
        filename: Nombre del archivo (puede contener fechas)

    Returns:
        Lista de (datetime, confidence, context_snippet)
    """
    dates = []

    # Patrón 1: DD/MM/YYYY o DD-MM-YYYY
    pattern1 = r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})"
    for match in re.finditer(pattern1, text):
        try:
            day, month, year = match.groups()
            date = datetime(int(year), int(month), int(day))
            context = text[max(0, match.start() - 30) : min(len(text), match.end() + 30)]
            dates.append((date, 0.9, context))
        except ValueError:
            continue

    # Patrón 2: YYYY-MM-DD (formato ISO)
    pattern2 = r"(\d{4})-(\d{1,2})-(\d{1,2})"
    for match in re.finditer(pattern2, text):
        try:
            year, month, day = match.groups()
            date = datetime(int(year), int(month), int(day))
            context = text[max(0, match.start() - 30) : min(len(text), match.end() + 30)]
            dates.append((date, 0.95, context))
        except ValueError:
            continue

    # Patrón 3: Texto largo (ej: "15 de enero de 2024")
    months_es = {
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

    pattern3 = r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})"
    for match in re.finditer(pattern3, text, re.IGNORECASE):
        try:
            day_str, month_str, year_str = match.groups()
            month = months_es.get(month_str.lower())
            if month:
                date = datetime(int(year_str), month, int(day_str))
                context = text[max(0, match.start() - 30) : min(len(text), match.end() + 30)]
                dates.append((date, 0.85, context))
        except (ValueError, KeyError):
            continue

    # Patrón 4: En el filename
    if filename:
        # Buscar patrones comunes en nombres de archivo
        filename_pattern = r"(\d{4})[_-](\d{2})[_-](\d{2})"
        match = re.search(filename_pattern, filename)
        if match:
            try:
                year, month, day = match.groups()
                date = datetime(int(year), int(month), int(day))
                dates.append((date, 0.7, f"Filename: {filename}"))
            except ValueError:
                pass

    # Ordenar por fecha y eliminar duplicados cercanos
    dates.sort(key=lambda x: x[0])

    # Filtrar duplicados (mismo día)
    filtered_dates = []
    seen_dates = set()
    for date, conf, ctx in dates:
        date_key = date.date()
        if date_key not in seen_dates:
            filtered_dates.append((date, conf, ctx))
            seen_dates.add(date_key)

    return filtered_dates


# =========================================================
# DETECCIÓN DE TIPO DE EVENTO
# =========================================================


def detect_event_type(text: str, filename: str) -> tuple[EventType, EventCategory, EventSeverity]:
    """
    Detecta tipo de evento basado en contenido y filename.

    Returns:
        (event_type, category, severity)
    """
    text_lower = text.lower()
    filename_lower = filename.lower()
    combined = text_lower + " " + filename_lower

    # EMBARGOS (crítico)
    if any(keyword in combined for keyword in ["embargo", "traba", "ejecutivo"]):
        return EventType.EMBARGO, EventCategory.LEGAL, EventSeverity.CRITICAL

    # RECLAMACIONES/DEMANDAS
    if any(keyword in combined for keyword in ["demanda", "reclamaci", "denuncia"]):
        if "demanda" in combined:
            return EventType.DEMANDA, EventCategory.LEGAL, EventSeverity.HIGH
        return EventType.RECLAMACION, EventCategory.LEGAL, EventSeverity.MEDIUM

    # SENTENCIAS
    if any(keyword in combined for keyword in ["sentencia", "resoluci", "auto judicial"]):
        return EventType.SENTENCIA, EventCategory.LEGAL, EventSeverity.HIGH

    # FACTURAS
    if "factura" in combined or "invoice" in combined:
        if "vencida" in combined or "impagada" in combined:
            return EventType.FACTURA_VENCIDA, EventCategory.FINANCIAL, EventSeverity.HIGH
        elif "emitida" in combined or "venta" in combined:
            return EventType.FACTURA_EMITIDA, EventCategory.FINANCIAL, EventSeverity.LOW
        return EventType.FACTURA_RECIBIDA, EventCategory.FINANCIAL, EventSeverity.LOW

    # PAGOS
    if any(keyword in combined for keyword in ["pago", "transferencia", "abono"]):
        if "impago" in combined or "no pago" in combined:
            return EventType.IMPAGO, EventCategory.CRISIS, EventSeverity.CRITICAL
        return EventType.PAGO_REALIZADO, EventCategory.FINANCIAL, EventSeverity.MEDIUM

    # VENTAS DE ACTIVOS
    if any(keyword in combined for keyword in ["venta", "enajenaci", "transmisi", "cesión"]):
        if any(keyword in combined for keyword in ["inmueble", "local", "terreno", "maquinaria"]):
            return EventType.VENTA_ACTIVO, EventCategory.PATRIMONIAL, EventSeverity.HIGH
        if "participaciones" in combined or "acciones" in combined:
            return (
                EventType.TRANSMISION_PARTICIPACIONES,
                EventCategory.PATRIMONIAL,
                EventSeverity.HIGH,
            )

    # EVENTOS SOCIETARIOS
    if any(keyword in combined for keyword in ["junta", "acuerdo social", "asamblea"]):
        return EventType.ACUERDO_JUNTA, EventCategory.CORPORATE, EventSeverity.MEDIUM

    if "nombramiento" in combined and "administrador" in combined:
        return EventType.NOMBRAMIENTO_ADMINISTRADOR, EventCategory.CORPORATE, EventSeverity.MEDIUM

    if "cese" in combined and "administrador" in combined:
        return EventType.CESE_ADMINISTRADOR, EventCategory.CORPORATE, EventSeverity.MEDIUM

    # CONTABLES
    if any(keyword in combined for keyword in ["balance", "cuentas anuales", "cierre ejercicio"]):
        return EventType.CIERRE_EJERCICIO, EventCategory.ACCOUNTING, EventSeverity.LOW

    # CONCURSO
    if any(keyword in combined for keyword in ["concurso", "insolvencia", "solicitud concursal"]):
        return EventType.SOLICITUD_CONCURSO, EventCategory.CRISIS, EventSeverity.CRITICAL

    # GARANTÍAS
    if any(keyword in combined for keyword in ["hipoteca", "prenda", "garantía", "aval"]):
        return EventType.CONSTITUCION_GARANTIA, EventCategory.PATRIMONIAL, EventSeverity.MEDIUM

    # Por defecto
    return EventType.OTRO, EventCategory.FINANCIAL, EventSeverity.LOW


# =========================================================
# EXTRACCIÓN DE PARTES INVOLUCRADAS
# =========================================================


def extract_parties(text: str) -> list[str]:
    """Extrae nombres de partes/entidades involucradas."""
    parties = []

    # Patrón 1: NIF/CIF seguido de nombre
    pattern_nif = r"([A-Z]\d{8}|[0-9]{8}[A-Z])\s*[-:]\s*([A-Z][A-Za-z\s]{3,40})"
    for match in re.finditer(pattern_nif, text):
        nif, name = match.groups()
        parties.append(f"{name.strip()} ({nif})")

    # Patrón 2: Palabras clave que preceden nombres
    keywords = ["acreedor", "deudor", "demandante", "demandado", "vendedor", "comprador"]
    for keyword in keywords:
        pattern = rf"{keyword}:\s*([A-Z][A-Za-z\s]{{3,40}})"
        matches = re.findall(pattern, text, re.IGNORECASE)
        for name in matches:
            parties.append(name.strip())

    # Eliminar duplicados
    return list(set(parties))


# =========================================================
# CONSTRUCCIÓN DE TIMELINE COMPLETO
# =========================================================


def build_timeline(db: Session, case_id: str, concurso_date: Optional[datetime] = None) -> Timeline:
    """
    Construye timeline completo del caso con análisis avanzado.

    Args:
        db: Sesión de BD
        case_id: ID del caso
        concurso_date: Fecha de solicitud de concurso (para calcular periodo sospechoso)

    Returns:
        Timeline completo
    """
    # Obtener documentos
    documents = db.query(Document).filter(Document.case_id == case_id).all()

    events = []

    for doc in documents:
        # Obtener chunks
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.document_id).all()

        if not chunks:
            continue

        # Texto completo (primeros 1000 chars para análisis)
        full_text = "\n".join([chunk.content for chunk in chunks if chunk.content])[:1000]

        # Extraer fechas
        dates = extract_dates_advanced(full_text, doc.filename)

        if not dates:
            # Si no hay fechas en texto, intentar usar metadatos
            if doc.date_start:
                dates = [(doc.date_start, 0.5, f"Metadata: {doc.filename}")]

        # Detectar tipo de evento
        event_type, category, severity = detect_event_type(full_text, doc.filename)

        # Extraer partes
        parties = extract_parties(full_text)

        # Extraer importe (básico)
        amount = None
        amount_pattern = r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*€"
        amount_match = re.search(amount_pattern, full_text)
        if amount_match:
            try:
                amount_str = amount_match.group(1).replace(".", "").replace(",", ".")
                amount = float(amount_str)
            except:
                pass

        # Crear evento por cada fecha encontrada
        for date, confidence, context in dates:
            # Evidencia
            chunk = chunks[0] if chunks else None
            evidence = Evidence(
                document_id=doc.document_id,
                filename=doc.filename,
                chunk_id=chunk.chunk_id if chunk else None,
                page=chunk.page if chunk else None,
                excerpt=context[:200],
                extraction_method="advanced_date_extraction",
                extraction_confidence=confidence,
            )

            # Título descriptivo
            title = f"{event_type.value.replace('_', ' ').title()}"
            if amount:
                title += f" - {amount:,.2f} €"

            event = TimelineEvent(
                date=date,
                event_type=event_type,
                category=category,
                severity=severity,
                title=title,
                description=context.strip(),
                amount=amount,
                parties=parties,
                evidence=evidence,
                confidence=confidence,
                tags=[event_type.value, category.value, severity.value],
            )

            events.append(event)

    # Ordenar eventos cronológicamente
    events.sort(key=lambda e: e.date)

    # Calcular periodo sospechoso (2 años antes de concurso)
    suspect_period_start = None
    if concurso_date:
        suspect_period_start = concurso_date - timedelta(days=730)  # 2 años

        # Marcar eventos dentro de periodo sospechoso
        for event in events:
            event.is_within_suspect_period = suspect_period_start <= event.date <= concurso_date

    # Detectar gaps temporales (más de 6 meses sin eventos)
    gaps = []
    for i in range(len(events) - 1):
        current_event = events[i]
        next_event = events[i + 1]
        gap_days = (next_event.date - current_event.date).days

        if gap_days > 180:  # Más de 6 meses
            gaps.append(
                {
                    "start_date": current_event.date,
                    "end_date": next_event.date,
                    "gap_days": gap_days,
                    "description": f"Gap de {gap_days // 30} meses sin eventos documentados",
                }
            )

    # Construir timeline
    timeline = Timeline(
        events=events,
        start_date=events[0].date if events else None,
        end_date=events[-1].date if events else None,
        total_events=len(events),
        suspect_period_start=suspect_period_start,
        gaps=gaps,
    )

    return timeline
