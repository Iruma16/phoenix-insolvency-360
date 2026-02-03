"""
Utilidades de visualización para Timeline (Fase B2).

Funciones para generar:
1. Timeline HTML/Markdown para reportes PDF
2. JSON estructurado para Streamlit
3. Análisis estadístico del timeline
4. Detección de patrones sospechosos
"""
from __future__ import annotations

from collections import Counter

from app.services.timeline_builder import EventCategory, EventSeverity, Timeline

# =========================================================
# ANÁLISIS ESTADÍSTICO
# =========================================================


def analyze_timeline_statistics(timeline: Timeline) -> dict:
    """
    Genera estadísticas del timeline.

    Returns:
        Dict con métricas clave
    """
    if not timeline.events:
        return {
            "total_events": 0,
            "date_range_days": 0,
            "by_category": {},
            "by_severity": {},
            "critical_events_count": 0,
            "suspect_period_events": 0,
            "gaps_count": 0,
        }

    # Contadores por categoría y severidad
    by_category = Counter(event.category.value for event in timeline.events)
    by_severity = Counter(event.severity.value for event in timeline.events)

    # Eventos críticos
    critical_events = [e for e in timeline.events if e.severity == EventSeverity.CRITICAL]

    # Eventos en periodo sospechoso
    suspect_events = [e for e in timeline.events if e.is_within_suspect_period]

    # Rango temporal
    date_range_days = 0
    if timeline.start_date and timeline.end_date:
        date_range_days = (timeline.end_date - timeline.start_date).days

    return {
        "total_events": timeline.total_events,
        "date_range_days": date_range_days,
        "start_date": timeline.start_date.strftime("%Y-%m-%d") if timeline.start_date else None,
        "end_date": timeline.end_date.strftime("%Y-%m-%d") if timeline.end_date else None,
        "by_category": dict(by_category),
        "by_severity": dict(by_severity),
        "critical_events_count": len(critical_events),
        "suspect_period_events": len(suspect_events),
        "gaps_count": len(timeline.gaps),
    }


# =========================================================
# DETECCIÓN DE PATRONES SOSPECHOSOS
# =========================================================


def detect_suspicious_patterns(timeline: Timeline) -> list[dict]:
    """
    Detecta patrones sospechosos en el timeline.

    Returns:
        Lista de alertas de patrones sospechosos
    """
    alerts = []

    # Patrón 1: Múltiples ventas de activos en periodo sospechoso
    asset_sales = [
        e
        for e in timeline.events
        if e.event_type.value in ["venta_activo", "transmision_participaciones"]
        and e.is_within_suspect_period
    ]

    if len(asset_sales) >= 2:
        total_amount = sum(e.amount for e in asset_sales if e.amount)
        alerts.append(
            {
                "code": "MULTIPLE_ASSET_SALES_SUSPECT_PERIOD",
                "severity": "high",
                "title": f"Múltiples ventas de activos en periodo sospechoso ({len(asset_sales)})",
                "description": (
                    f"Se detectaron {len(asset_sales)} ventas de activos en el periodo sospechoso "
                    f"(2 años antes de concurso). Importe total: {total_amount:,.2f} € si conocido. "
                    f"Requiere análisis de precios y justificación."
                ),
                "events": [e.title for e in asset_sales],
            }
        )

    # Patrón 2: Embargos múltiples en corto periodo
    embargos = [e for e in timeline.events if e.event_type.value == "embargo"]
    if len(embargos) >= 2:  # Cambiado de 3 a 2 para más sensibilidad
        # Calcular concentración temporal
        if len(embargos) > 1:
            first_embargo = min(embargos, key=lambda e: e.date)
            last_embargo = max(embargos, key=lambda e: e.date)
            days_span = (last_embargo.date - first_embargo.date).days

            if days_span <= 365:  # Cambiado de 180 a 365 días (1 año)
                alerts.append(
                    {
                        "code": "MULTIPLE_EMBARGOS_SHORT_PERIOD",
                        "severity": "critical",
                        "title": f"Múltiples embargos en periodo corto ({len(embargos)} en {days_span} días)",
                        "description": (
                            f"Se detectaron {len(embargos)} embargos en un periodo de {days_span} días "
                            f"({days_span // 30} meses). Indica crisis de liquidez grave."
                        ),
                        "events": [e.title for e in embargos],
                    }
                )

    # Patrón 3: Gap temporal largo sin actividad
    significant_gaps = [g for g in timeline.gaps if g["gap_days"] > 365]
    for gap in significant_gaps:
        alerts.append(
            {
                "code": "SIGNIFICANT_DOCUMENTATION_GAP",
                "severity": "medium",
                "title": f"Gap documental significativo ({gap['gap_days'] // 30} meses)",
                "description": (
                    f"Periodo sin documentación entre {gap['start_date'].strftime('%Y-%m-%d')} "
                    f"y {gap['end_date'].strftime('%Y-%m-%d')}. Puede indicar documentación faltante."
                ),
                "gap_info": gap,
            }
        )

    # Patrón 4: Cambios de administrador cerca de crisis
    admin_changes = [
        e
        for e in timeline.events
        if e.event_type.value in ["nombramiento_administrador", "cese_administrador"]
    ]
    crisis_events = [e for e in timeline.events if e.category == EventCategory.CRISIS]

    if admin_changes and crisis_events:
        # Verificar si hay cambios cercanos a eventos de crisis
        for crisis in crisis_events:
            nearby_changes = [
                a
                for a in admin_changes
                if abs((a.date - crisis.date).days) <= 90  # 3 meses
            ]
            if nearby_changes:
                alerts.append(
                    {
                        "code": "ADMIN_CHANGE_NEAR_CRISIS",
                        "severity": "medium",
                        "title": "Cambio de administrador cerca de evento de crisis",
                        "description": (
                            f"Detectado cambio de administrador cerca de {crisis.title} "
                            f"(fecha crisis: {crisis.date.strftime('%Y-%m-%d')})"
                        ),
                        "events": [a.title for a in nearby_changes] + [crisis.title],
                    }
                )

    return alerts


# =========================================================
# GENERACIÓN DE HTML PARA REPORTES
# =========================================================


def generate_timeline_html(timeline: Timeline, include_styles: bool = True) -> str:
    """
    Genera HTML del timeline para incluir en reportes PDF.

    Args:
        timeline: Timeline a renderizar
        include_styles: Incluir estilos CSS inline

    Returns:
        HTML string
    """
    if not timeline.events:
        return "<p>No se encontraron eventos documentados en el timeline.</p>"

    html_parts = []

    # Estilos
    if include_styles:
        html_parts.append(
            """
        <style>
            .timeline { margin: 20px 0; }
            .timeline-event { 
                margin: 10px 0; 
                padding: 10px; 
                border-left: 3px solid #ccc;
                background: #f9f9f9;
            }
            .timeline-event.critical { border-left-color: #d32f2f; }
            .timeline-event.high { border-left-color: #f57c00; }
            .timeline-event.medium { border-left-color: #fbc02d; }
            .timeline-event.low { border-left-color: #388e3c; }
            .event-date { font-weight: bold; color: #333; }
            .event-title { font-size: 1.1em; margin: 5px 0; }
            .event-meta { font-size: 0.9em; color: #666; }
            .suspect-period { background: #fff3cd; }
        </style>
        """
        )

    html_parts.append('<div class="timeline">')

    # Estadísticas resumen
    stats = analyze_timeline_statistics(timeline)
    html_parts.append(
        f"""
    <div class="timeline-summary">
        <p><strong>Periodo analizado:</strong> {stats['start_date']} a {stats['end_date']} ({stats['date_range_days']} días)</p>
        <p><strong>Total de eventos:</strong> {stats['total_events']}</p>
        <p><strong>Eventos críticos:</strong> {stats['critical_events_count']}</p>
        {f"<p><strong>Eventos en periodo sospechoso:</strong> {stats['suspect_period_events']}</p>" if timeline.suspect_period_start else ""}
    </div>
    <hr/>
    """
    )

    # Eventos
    for event in timeline.events:
        suspect_class = "suspect-period" if event.is_within_suspect_period else ""
        severity_class = event.severity.value

        html_parts.append(
            f"""
        <div class="timeline-event {severity_class} {suspect_class}">
            <div class="event-date">{event.date.strftime('%d/%m/%Y')}</div>
            <div class="event-title">{event.title}</div>
            <div class="event-meta">
                <span>Tipo: {event.event_type.value.replace('_', ' ').title()}</span> | 
                <span>Categoría: {event.category.value.title()}</span> | 
                <span>Severidad: {event.severity.value.title()}</span>
                {f" | <span>Importe: {event.amount:,.2f} €</span>" if event.amount else ""}
            </div>
            <p>{event.description[:200]}...</p>
            <div class="event-evidence" style="font-size: 0.85em; color: #888;">
                📄 {event.evidence.filename} 
                {f"(pág. {event.evidence.page})" if event.evidence.page else ""}
            </div>
        </div>
        """
        )

    html_parts.append("</div>")

    # Patrones sospechosos
    alerts = detect_suspicious_patterns(timeline)
    if alerts:
        html_parts.append("<hr/><h3>⚠️ Patrones Sospechosos Detectados</h3>")
        for alert in alerts:
            html_parts.append(
                f"""
            <div class="alert alert-{alert['severity']}" style="margin: 10px 0; padding: 10px; border: 1px solid #ddd;">
                <strong>{alert['title']}</strong>
                <p>{alert['description']}</p>
            </div>
            """
            )

    return "\n".join(html_parts)


# =========================================================
# EXPORTACIÓN PARA STREAMLIT
# =========================================================


def timeline_to_streamlit_format(timeline: Timeline) -> dict:
    """
    Convierte timeline a formato optimizado para Streamlit.

    Returns:
        Dict con datos listos para visualizar en Streamlit
    """
    return {
        "events": [
            {
                "date": event.date.strftime("%Y-%m-%d"),
                "title": event.title,
                "description": event.description,
                "type": event.event_type.value,
                "category": event.category.value,
                "severity": event.severity.value,
                "amount": event.amount,
                "parties": event.parties,
                "document": event.evidence.filename,
                "page": event.evidence.page,
                "confidence": event.confidence,
                "is_suspect_period": event.is_within_suspect_period,
            }
            for event in timeline.events
        ],
        "statistics": analyze_timeline_statistics(timeline),
        "patterns": detect_suspicious_patterns(timeline),
        "gaps": timeline.gaps,
    }
