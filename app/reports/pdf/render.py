from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
)

from .canvas import NumberedCanvas
from .charts import create_timeline_chart
from .styles import COLOR_GRAY, COLOR_PRIMARY, create_professional_table_style


def render_pdf(report_payload: dict[str, Any], output_path: str) -> str:
    """
    Renderiza el informe en PDF usando ReportLab.

    Args:
        report_payload: Datos estructurados del informe
        output_path: Ruta donde guardar el PDF

    Returns:
        Ruta del archivo PDF generado
    """

    # Crear directorio si no existe
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Crear documento
    doc = SimpleDocTemplate(
        str(output_file),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    # Estilos
    styles = getSampleStyleSheet()

    style_title = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=COLOR_PRIMARY,
        spaceAfter=30,
        alignment=TA_CENTER,
    )

    style_heading = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=16,
        textColor=COLOR_PRIMARY,
        spaceAfter=12,
        spaceBefore=12,
    )

    style_body = ParagraphStyle(
        "CustomBody",
        parent=styles["BodyText"],
        fontSize=10,
        alignment=TA_JUSTIFY,
        spaceAfter=12,
    )

    style_small = ParagraphStyle(
        "CustomSmall",
        parent=styles["BodyText"],
        fontSize=8,
        textColor=COLOR_GRAY,
        alignment=TA_CENTER,
    )

    # Contenido
    story: list[Any] = []

    # PORTADA
    story.extend(_render_cover_page(report_payload, style_title, style_body, style_small))
    story.append(PageBreak())

    # RESUMEN EJECUTIVO
    story.append(Paragraph("<a name='sec_resumen'/>RESUMEN EJECUTIVO", style_heading))
    story.extend(_render_executive_summary(report_payload, style_body))
    story.append(Spacer(1, 0.5 * cm))

    # HECHOS DEL CASO
    story.append(Paragraph("<a name='sec_hechos'/>HECHOS EXTRAÍDOS DEL CASO", style_heading))
    story.extend(_render_case_facts(report_payload, style_body))
    story.append(PageBreak())

    # HALLAZGOS Y RIESGOS
    story.append(Paragraph("<a name='sec_hallazgos'/>HALLAZGOS Y RIESGOS", style_heading))
    story.extend(_render_findings(report_payload, style_body))
    story.append(PageBreak())

    # RECOMENDACIONES ESTRATÉGICAS (si existe síntesis)
    if report_payload.get("synthesis"):
        story.append(
            Paragraph("<a name='sec_recomendaciones'/>RECOMENDACIONES ESTRATÉGICAS", style_heading)
        )
        story.extend(_render_strategic_recommendations(report_payload, style_body))
        story.append(PageBreak())

    # ANÁLISIS LLM (si existe)
    auditor_llm = report_payload.get("auditor_llm", {})
    prosecutor_llm = report_payload.get("prosecutor_llm", {})
    if (auditor_llm and auditor_llm.get("llm_enabled")) or (
        prosecutor_llm and prosecutor_llm.get("llm_enabled")
    ):
        story.append(
            Paragraph("<a name='sec_llm'/>ANÁLISIS CON INTELIGENCIA ARTIFICIAL", style_heading)
        )
        story.extend(_render_llm_analysis(report_payload, style_body))
        story.append(PageBreak())

    # ARTÍCULOS TRLC RELEVANTES
    story.append(Paragraph("<a name='sec_trlc'/>ARTÍCULOS TRLC RELEVANTES", style_heading))
    story.extend(_render_legal_articles(report_payload, style_body))
    story.append(Spacer(1, 0.5 * cm))

    # TRAZABILIDAD
    story.append(Paragraph("<a name='sec_trazabilidad'/>EVIDENCIAS Y TRAZABILIDAD", style_heading))
    story.extend(_render_traceability(report_payload, style_body))
    story.append(PageBreak())

    # DISCLAIMER
    story.append(Paragraph("<a name='sec_disclaimer'/>AVISO LEGAL", style_heading))
    story.extend(_render_disclaimer(style_body, style_small))

    # Construir PDF con canvas personalizado (numeración de páginas)
    doc.build(story, canvasmaker=NumberedCanvas)

    return str(output_file)


def _render_cover_page(payload: dict, style_title, style_body, style_small) -> list:
    """Renderiza la portada."""

    elements: list[Any] = []

    elements.append(Spacer(1, 3 * cm))
    elements.append(Paragraph("PHOENIX LEGAL", style_title))
    elements.append(Paragraph("Informe de Análisis Concursal", style_body))
    elements.append(Spacer(1, 2 * cm))

    # Información del caso
    case_info = f"""
    <b>Caso:</b> {payload['case_id']}<br/>
    <b>Fecha de generación:</b> {datetime.fromisoformat(payload['generated_at']).strftime('%d/%m/%Y %H:%M')}<br/>
    <b>Riesgo global:</b> <font color="{'red' if payload['overall_risk'] == 'high' else 'orange' if payload['overall_risk'] == 'medium' else 'green'}">{payload['overall_risk'].upper()}</font><br/>
    <b>Sistema:</b> {payload['system_version']}
    """

    elements.append(Paragraph(case_info, style_body))
    elements.append(Spacer(1, 3 * cm))

    elements.append(
        Paragraph(
            "Este informe ha sido generado automáticamente por Phoenix Legal System", style_small
        )
    )

    return elements


def _render_executive_summary(payload: dict, style_body) -> list:
    """Renderiza el resumen ejecutivo con TESIS JURÍDICA."""

    elements: list[Any] = []
    summary = payload["executive_summary"]

    # ========================================
    # 1. TESIS JURÍDICA (si existe síntesis)
    # ========================================
    if "thesis_statement" in summary:
        # Estilo destacado para tesis
        thesis_style = ParagraphStyle(
            "ThesisStyle",
            parent=style_body,
            fontSize=12,
            leading=16,
            spaceAfter=12,
            textColor=COLOR_PRIMARY,
        )

        thesis_text = f"""
        <b><font size="13">DICTAMEN JURÍDICO</font></b><br/>
        <b>{summary['thesis_statement']}</b>
        """
        elements.append(Paragraph(thesis_text, thesis_style))
        elements.append(Spacer(1, 0.3 * cm))

        # Razonamiento
        reasoning_text = f"""
        <b>Fundamento:</b> {summary['thesis_reasoning']}
        """
        elements.append(Paragraph(reasoning_text, style_body))
        elements.append(Spacer(1, 0.3 * cm))

        # Alerta si no puede concluir
        if not summary.get("can_conclude", True):
            warning_text = f"""
            <font color="red"><b>⚠️  DICTAMEN NO CONCLUYENTE</b></font><br/>
            <b>Razón:</b> {summary.get('inconclusive_reason', 'Documentación insuficiente')}
            """
            elements.append(Paragraph(warning_text, style_body))
            elements.append(Spacer(1, 0.3 * cm))

    # ========================================
    # 2. ESTADÍSTICAS
    # ========================================
    risk_counts = summary["risk_counts"]

    # Adaptar etiquetas según si es síntesis o legacy
    if "thesis_statement" in summary:
        stats_text = f"""
        <b>Nivel de Riesgo:</b> {payload['overall_risk'].upper()}<br/>
        <b>Hallazgos legales:</b> {summary['legal_findings_count']}<br/>
        <b>Riesgos por peso legal:</b><br/>
        - Crítico: {risk_counts.get('critical', 0)}<br/>
        - Alto: {risk_counts.get('high', 0)}<br/>
        - Medio: {risk_counts.get('medium', 0)}<br/>
        - Bajo: {risk_counts.get('low', 0)}
        """
    else:
        stats_text = f"""
        <b>Riesgo Global:</b> {payload['overall_risk'].upper()}<br/>
        <b>Hallazgos legales:</b> {summary['legal_findings_count']}<br/>
        <b>Distribución de riesgos:</b><br/>
        - Alto: {risk_counts.get('high', 0)}<br/>
        - Medio: {risk_counts.get('medium', 0)}<br/>
        - Bajo: {risk_counts.get('low', 0)}
        """

    elements.append(Paragraph(stats_text, style_body))
    elements.append(Spacer(1, 0.3 * cm))

    # ========================================
    # 3. TOP RIESGOS JERARQUIZADOS
    # ========================================
    if summary["top_risks"]:
        if "thesis_statement" in summary:
            elements.append(
                Paragraph("<b>Riesgos determinantes (ordenados por peso legal):</b>", style_body)
            )
        else:
            elements.append(Paragraph("<b>Principales riesgos identificados:</b>", style_body))

        elements.append(Spacer(1, 0.2 * cm))

        for i, risk in enumerate(summary["top_risks"], 1):
            # Renderizado según síntesis o legacy
            if "legal_weight" in risk:
                # Síntesis: conecta hecho → artículo → consecuencia
                risk_text = f"""
                {i}. <b>{risk['type']}</b> [Peso legal: {risk['legal_weight']}]<br/>
                <b>Base legal:</b> {risk['article']}<br/>
                <b>Consecuencia:</b> {risk['consequence']}<br/>
                """
                if risk.get("defense"):
                    risk_text += f"<b>Defensa posible:</b> <i>{risk['defense']}</i><br/>"
            else:
                # Legacy: solo listado
                risk_text = f"""
                {i}. <b>{risk['type'].replace('_', ' ').title()}</b> (Severidad: {risk.get('severity', 'N/A')}, Confianza: {risk.get('confidence', 'N/A')})<br/>
                {risk.get('description', 'Sin descripción')}
                """

            elements.append(Paragraph(risk_text, style_body))
            elements.append(Spacer(1, 0.3 * cm))

    return elements


def _render_case_facts(payload: dict, style_body) -> list:
    """Renderiza los hechos del caso."""

    elements: list[Any] = []
    facts = payload["case_facts"]

    if not facts:
        elements.append(Paragraph("No se han extraído hechos específicos del caso.", style_body))
        return elements

    # Gráfico de timeline si hay eventos con fechas
    timeline_chart = create_timeline_chart(facts)
    if timeline_chart:
        img = Image(timeline_chart, width=16 * cm, height=6 * cm)
        elements.append(img)
        elements.append(Spacer(1, 0.5 * cm))

    # Tabla de hechos
    data = [["Fecha", "Descripción", "Fuente"]]

    for fact in facts:
        data.append(
            [
                fact.get("date", "N/A"),
                fact.get("description", "Sin descripción")[:80],
                fact.get("document", "N/A"),
            ]
        )

    table = Table(data, colWidths=[3 * cm, 10 * cm, 3 * cm])
    table.setStyle(create_professional_table_style())

    elements.append(table)

    return elements


def _render_findings(payload: dict, style_body) -> list:
    """Renderiza hallazgos y riesgos."""

    elements: list[Any] = []
    findings = payload["findings"]

    if not findings:
        elements.append(Paragraph("No se han identificado hallazgos específicos.", style_body))
        return elements

    for finding in findings:
        # Color según severidad
        severity_color = {
            "high": "red",
            "medium": "orange",
            "low": "green",
            "indeterminate": "gray",
        }.get(finding["severity"], "black")

        finding_text = f"""
        <b><font color="{severity_color}">{finding['type'].replace('_', ' ').title()}</font></b><br/>
        <b>Severidad:</b> {finding['severity']} | <b>Confianza:</b> {finding['confidence']}<br/>
        <b>Descripción:</b> {finding['description']}<br/>
        <b>Impacto:</b> {finding.get('impact', 'No especificado')}
        """

        if not finding.get("has_sufficient_evidence"):
            finding_text += "<br/><font color='red'><b>⚠️ SIN EVIDENCIA SUFICIENTE</b></font>"

        elements.append(KeepTogether([Paragraph(finding_text, style_body), Spacer(1, 0.3 * cm)]))

    return elements


def _render_strategic_recommendations(payload: dict, style_body) -> list:
    """Renderiza RECOMENDACIONES ESTRATÉGICAS desde síntesis jurídica."""

    elements: list[Any] = []
    synthesis = payload.get("synthesis")

    if not synthesis:
        return elements

    recommendations = synthesis.get("strategic_recommendations", [])
    documentary_gaps = synthesis.get("documentary_gaps", [])

    if not recommendations and not documentary_gaps:
        return elements

    # RECOMENDACIONES ACCIONABLES
    if recommendations:
        elements.append(Paragraph("<b>ACCIONES INMEDIATAS RECOMENDADAS</b>", style_body))
        elements.append(Spacer(1, 0.3 * cm))

        # Agrupar por prioridad
        immediate = [r for r in recommendations if r["priority"] == "INMEDIATA"]
        high = [r for r in recommendations if r["priority"] == "ALTA"]
        medium = [r for r in recommendations if r["priority"] == "MEDIA"]

        for priority_group, title, color in [
            (immediate, "URGENTE", "red"),
            (high, "Prioridad Alta", "orange"),
            (medium, "Prioridad Media", "blue"),
        ]:
            if priority_group:
                elements.append(
                    Paragraph(f"<b><font color='{color}'>{title}:</font></b>", style_body)
                )
                for rec in priority_group:
                    rec_text = f"""
                    • <b>{rec['action']}</b><br/>
                    <i>{rec['rationale']}</i>
                    """
                    elements.append(Paragraph(rec_text, style_body))
                    elements.append(Spacer(1, 0.2 * cm))

    # VACÍOS DOCUMENTALES PELIGROSOS
    if documentary_gaps:
        elements.append(Spacer(1, 0.5 * cm))
        elements.append(Paragraph("<b>VACÍOS DOCUMENTALES CRÍTICOS</b>", style_body))
        elements.append(Spacer(1, 0.3 * cm))

        for gap in documentary_gaps:
            severity_color = {
                "CRÍTICO": "red",
                "ALTO": "orange",
                "MEDIO": "blue",
                "BAJO": "green",
            }.get(str(gap.get("severity", "MEDIO")).upper(), "black")

            gap_text = f"""
            <font color='{severity_color}'>▪</font> <b>{gap['missing_document']}</b><br/>
            <i>Interpretación legal:</i> {gap['legal_interpretation']}<br/>
            <i>Base legal:</i> {gap['article_trlc']}
            """
            elements.append(Paragraph(gap_text, style_body))
            elements.append(Spacer(1, 0.3 * cm))

    return elements


def _render_llm_analysis(payload: dict, style_body) -> list:
    """Renderiza análisis LLM."""
    elements: list[Any] = []

    # Auditor LLM
    auditor_llm = payload.get("auditor_llm", {})
    if auditor_llm and auditor_llm.get("llm_enabled"):
        elements.append(Paragraph("<b>ANÁLISIS DOCUMENTAL (AUDITOR IA)</b>", style_body))
        elements.append(Spacer(1, 0.2 * cm))

        summary = auditor_llm.get("llm_summary", "No disponible")
        elements.append(Paragraph(f"<b>Resumen:</b> {summary}", style_body))
        elements.append(Spacer(1, 0.2 * cm))

        reasoning = auditor_llm.get("llm_reasoning", "No disponible")
        elements.append(Paragraph(f"<b>Razonamiento:</b> {reasoning}", style_body))
        elements.append(Spacer(1, 0.2 * cm))

        confidence = auditor_llm.get("llm_confidence", "No disponible")
        elements.append(Paragraph(f"<b>Confianza:</b> {confidence}", style_body))
        elements.append(Spacer(1, 0.4 * cm))

    # Prosecutor LLM
    prosecutor_llm = payload.get("prosecutor_llm", {})
    if prosecutor_llm and prosecutor_llm.get("llm_enabled"):
        elements.append(Paragraph("<b>ANÁLISIS LEGAL (PROSECUTOR IA)</b>", style_body))
        elements.append(Spacer(1, 0.2 * cm))

        legal_summary = prosecutor_llm.get(
            "llm_summary", prosecutor_llm.get("llm_legal_summary", "No disponible")
        )
        elements.append(Paragraph(f"<b>Resumen legal:</b> {legal_summary}", style_body))
        elements.append(Spacer(1, 0.2 * cm))

        legal_reasoning = prosecutor_llm.get(
            "llm_reasoning", prosecutor_llm.get("llm_legal_reasoning", "No disponible")
        )
        elements.append(Paragraph(f"<b>Razonamiento jurídico:</b> {legal_reasoning}", style_body))
        elements.append(Spacer(1, 0.2 * cm))

        recommendations = prosecutor_llm.get("llm_recommendations", "No disponible")
        if recommendations and recommendations != "No disponible":
            elements.append(Paragraph(f"<b>Recomendaciones:</b> {recommendations}", style_body))
            elements.append(Spacer(1, 0.2 * cm))

    # Nota
    note = "<i>Nota: Este análisis es complementario y debe ser validado por un profesional del derecho.</i>"
    elements.append(Paragraph(note, style_body))

    return elements


def _render_legal_articles(payload: dict, style_body) -> list:
    """Renderiza artículos del TRLC relevantes."""

    elements: list[Any] = []
    articles = payload["legal_articles"]

    if not articles:
        elements.append(
            Paragraph("No se han identificado artículos aplicables del TRLC.", style_body)
        )
        return elements

    # Tabla de artículos
    data = [["Artículo", "Descripción", "Relevancia"]]

    for article in articles[:10]:  # Limitar a 10
        data.append(
            [
                article.get("ref", "N/A"),
                article.get("description", "Sin descripción")[:150],
                article.get("relevance", "general"),
            ]
        )

    table = Table(data, colWidths=[4 * cm, 9 * cm, 3 * cm])
    table.setStyle(create_professional_table_style())

    elements.append(table)

    return elements


def _render_traceability(payload: dict, style_body) -> list:
    """Renderiza tabla de trazabilidad."""

    elements: list[Any] = []
    traceability = payload["traceability"]

    if not traceability:
        elements.append(Paragraph("No hay datos de trazabilidad disponibles.", style_body))
        return elements

    # Tabla de trazabilidad
    data = [["Hallazgo", "Evidencia Caso", "Base Legal", "Confianza"]]

    for trace in traceability[:8]:  # Limitar a 8
        data.append(
            [
                trace.get("claim", "N/A")[:60],
                trace.get("case_source", "N/A")[:60],
                trace.get("legal_source", "N/A")[:60],
                trace.get("confidence", "N/A"),
            ]
        )

    table = Table(data, colWidths=[4 * cm, 4 * cm, 5 * cm, 2 * cm])
    table.setStyle(create_professional_table_style())

    elements.append(table)

    return elements


def _render_disclaimer(style_body, style_small) -> list:
    """Renderiza el disclaimer legal."""

    elements: list[Any] = []

    disclaimer_text = """
    <b>AVISO IMPORTANTE:</b><br/><br/>
    Este informe ha sido generado automáticamente por Phoenix Legal System mediante
    análisis algorítmico de documentación aportada y consulta a bases de datos legales.
    <br/><br/>
    El presente informe tiene carácter orientativo y NO sustituye el criterio profesional
    de un abogado especializado en derecho concursal. Los hallazgos y recomendaciones aquí
    expuestos deben ser validados por un profesional cualificado antes de tomar cualquier
    decisión legal o empresarial.
    <br/><br/>
    Phoenix Legal System no asume responsabilidad por decisiones tomadas basándose
    exclusivamente en este informe sin la debida supervisión profesional.
    <br/><br/>
    Para más información o para una revisión profesional de este caso, consulte con
    un abogado especializado en derecho concursal.
    """

    elements.append(Paragraph(disclaimer_text, style_body))
    elements.append(Spacer(1, 1 * cm))

    elements.append(
        Paragraph(
            f"© {datetime.now(timezone.utc).year} Phoenix Legal System. Todos los derechos reservados.",
            style_small,
        )
    )

    return elements
