from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.economic_report import EconomicReportBundle

from .canvas import NumberedCanvas
from .styles import COLOR_DANGER, COLOR_GRAY, COLOR_PRIMARY


def generate_economic_report_pdf(bundle: EconomicReportBundle) -> bytes:
    """
    Genera un PDF “para cliente” desde EconomicReportBundle.

    Nota: el bundle ya contiene datos fríos, alertas, roadmap y (opcional) narrativa LLM.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "EcoTitle",
        parent=styles["Heading1"],
        fontSize=22,
        textColor=COLOR_PRIMARY,
        spaceAfter=24,
        alignment=TA_CENTER,
    )
    heading_style = ParagraphStyle(
        "EcoHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=COLOR_PRIMARY,
        spaceAfter=10,
    )
    small_gray = ParagraphStyle(
        "EcoSmall",
        parent=styles["Normal"],
        fontSize=9,
        textColor=COLOR_GRAY,
    )

    def _safe(s: object) -> str:
        return ("" if s is None else str(s)).strip()

    def _cap(s: str, max_len: int = 240) -> str:
        s = _safe(s)
        return s if len(s) <= max_len else s[: max_len - 20] + " …[truncado]"

    def _mk_table(data: list[list[str]], col_widths: list[float]) -> Table:
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3D91")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("TOPPADDING", (0, 0), (-1, 0), 6),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ]
            )
        )
        return t

    story = []

    # =========================
    # PORTADA
    # =========================
    story.append(Spacer(1, 2.5 * cm))
    story.append(Paragraph("<b>INFORME DE SITUACIÓN ECONÓMICA</b>", title_style))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(f"<b>Caso:</b> {bundle.case_name}", styles["Normal"]))
    story.append(Paragraph(f"<b>ID Caso:</b> {bundle.case_id}", styles["Normal"]))
    story.append(
        Paragraph(
            f"<b>Generado:</b> {bundle.generated_at.strftime('%d/%m/%Y %H:%M')} UTC",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 1.2 * cm))

    disclaimer = Paragraph(
        "<b>AVISO:</b> Este informe es un análisis automatizado (reglas + RAG + LLM). "
        "No constituye asesoramiento profesional. Requiere revisión por profesional cualificado "
        "antes de tomar decisiones. Si faltan datos, el informe indicará explícitamente 'no hay' o 'no determinable'.",
        ParagraphStyle("EcoDisclaimer", parent=styles["Normal"], textColor=COLOR_DANGER, fontSize=10),
    )
    story.append(disclaimer)
    story.append(PageBreak())

    # =========================
    # 1) RESUMEN EJECUTIVO
    # =========================
    story.append(Paragraph("<b>1. RESUMEN EJECUTIVO</b>", heading_style))
    story.append(Paragraph(bundle.client_summary.headline, styles["Normal"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(
        Paragraph(
            f"<b>Situación:</b> {bundle.client_summary.situation.upper()}",
            styles["Normal"],
        )
    )
    if bundle.client_summary.key_points:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("<b>Puntos clave</b>", styles["Normal"]))
        for p in bundle.client_summary.key_points[:6]:
            story.append(Paragraph(f"• {p}", styles["Normal"]))
    if bundle.client_summary.next_7_days:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("<b>Qué hacer en 7 días</b>", styles["Normal"]))
        for p in bundle.client_summary.next_7_days[:6]:
            story.append(Paragraph(f"• {p}", styles["Normal"]))
    if bundle.client_summary.warnings:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("<b>Avisos</b>", styles["Normal"]))
        for w in bundle.client_summary.warnings[:6]:
            story.append(Paragraph(f"• {w}", small_gray))

    story.append(PageBreak())

    # =========================
    # 2) SITUACIÓN ECONÓMICA (TRADUCIDA)
    # =========================
    story.append(Paragraph("<b>2. SITUACIÓN ECONÓMICA (DATOS + INTERPRETACIÓN)</b>", heading_style))

    fin = bundle.financial_analysis
    story.append(Paragraph(f"<b>Fecha análisis:</b> {fin.analysis_date.isoformat()}", small_gray))

    # Ratios
    if fin.ratios:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("<b>Ratios financieros</b>", styles["Normal"]))
        ratios_rows = [["Ratio", "Valor", "Estado", "Interpretación"]]
        for r in fin.ratios[:8]:
            val = "N/A" if r.value is None else f"{r.value:.2f}"
            ratios_rows.append(
                [
                    _cap(r.name, 32),
                    val,
                    _cap(getattr(getattr(r, "status", None), "value", None) or r.status, 24),
                    _cap(r.interpretation, 110),
                ]
            )
        story.append(_mk_table(ratios_rows, [5.2 * cm, 2.4 * cm, 2.6 * cm, 7.3 * cm]))
    else:
        story.append(Paragraph("No hay ratios calculables con la documentación actual.", styles["Normal"]))

    # Insolvencia
    if fin.insolvency:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("<b>Señales de insolvencia</b>", styles["Normal"]))
        story.append(Paragraph(fin.insolvency.overall_assessment, styles["Normal"]))
        story.append(Paragraph(f"Confianza: {fin.insolvency.confidence_level.value}", small_gray))
        signals_rows = [["Tipo", "Descripción"]]

        def _iter_signals(label: str, items: list) -> None:
            for s in (items or [])[:4]:
                desc = _safe(getattr(s, "description", None) or s)
                if not desc or desc.lower().startswith("metadata:"):
                    continue
                signals_rows.append([label, _cap(desc, 200)])

        _iter_signals("Impago", fin.insolvency.signals_impago)
        _iter_signals("Contable", fin.insolvency.signals_contables)
        _iter_signals("Exigibilidad", fin.insolvency.signals_exigibilidad)

        if len(signals_rows) > 1:
            story.append(Spacer(1, 0.15 * cm))
            story.append(_mk_table(signals_rows, [3.2 * cm, 14.3 * cm]))
        if fin.insolvency.critical_missing_docs:
            story.append(Spacer(1, 0.1 * cm))
            story.append(
                Paragraph(
                    "Faltan documentos críticos: " + ", ".join(fin.insolvency.critical_missing_docs[:8]),
                    small_gray,
                )
            )
    else:
        story.append(Paragraph("No hay datos suficientes para evaluar insolvencia con trazabilidad.", styles["Normal"]))

    story.append(PageBreak())

    # =========================
    # 3) ALERTAS (TÉCNICAS + PATRONES)
    # =========================
    story.append(Paragraph("<b>3. ALERTAS DEL EXPEDIENTE</b>", heading_style))
    if not bundle.alerts:
        story.append(Paragraph("No hay alertas detectadas.", styles["Normal"]))
    else:
        story.append(Paragraph(f"Total alertas: {len(bundle.alerts)}", small_gray))
        rows = [["Tipo", "Descripción", "Documentos (evidencia)"]]
        for a in bundle.alerts[:14]:
            atype = a.alert_type.value if hasattr(a.alert_type, "value") else str(a.alert_type)
            desc = _cap(getattr(a, "description", None), 220)

            docs = []
            try:
                for ev in (getattr(a, "evidence", None) or [])[:3]:
                    fn = None
                    if isinstance(ev, dict):
                        fn = ev.get("filename")
                    else:
                        fn = getattr(ev, "filename", None)
                    if fn:
                        docs.append(str(fn))
            except Exception:
                docs = []
            rows.append([_cap(atype, 28), desc, _cap(", ".join(docs) if docs else "—", 80)])

        story.append(Spacer(1, 0.15 * cm))
        story.append(_mk_table(rows, [3.6 * cm, 9.8 * cm, 4.1 * cm]))

    story.append(PageBreak())

    # =========================
    # 4) OPCIONES (INCLUYE AEAT/TGSS) + BASE LEGAL
    # =========================
    story.append(Paragraph("<b>4. OPCIONES Y BASE LEGAL (RAG)</b>", heading_style))
    story.append(
        Paragraph(
            "Este bloque presenta opciones típicas condicionadas por los datos. "
            "Si no hay evidencia suficiente, se indicará explícitamente.",
            styles["Normal"],
        )
    )

    # Opciones (solo automáticas)
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("<b>Opciones para el cliente</b>", styles["Normal"]))
    recs = (bundle.legal_synthesis or {}).get("strategic_recommendations") or []
    if recs:
        rec_rows = [["Acción", "Fundamento"]]
        for r in recs[:10]:
            action = _cap(r.get("action") or "Opción", 80)
            rationale = _cap(r.get("rationale") or "", 220) or "—"
            rec_rows.append([action, rationale])
        story.append(_mk_table(rec_rows, [6.2 * cm, 11.2 * cm]))
    else:
        story.append(Paragraph("No hay opciones determinables con la evidencia actual.", styles["Normal"]))

    # Crédito público + opciones de pago (si hay citas)
    credito = bundle.legal_citations.get("credito_publico") or []
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("<b>Hacienda (AEAT) y Seguridad Social (TGSS)</b>", styles["Normal"]))
    story.append(
        Paragraph(
            "Opciones típicas: aplazamiento/fraccionamiento, planes de pago, y gestión de recargos. "
            "La aplicabilidad concreta requiere normativa específica y los documentos de deuda aportados.",
            styles["Normal"],
        )
    )
    if credito:
        story.append(Spacer(1, 0.15 * cm))
        story.append(Paragraph("<b>Citas (crédito público)</b>", styles["Normal"]))
        seen = set()
        cite_rows = [["Cita", "Extracto"]]
        for c in credito:
            citation = _safe(getattr(c, "citation", None))
            if not citation or citation in seen:
                continue
            seen.add(citation)
            excerpt = _cap(getattr(c, "excerpt", None) or "", 220) or "—"
            cite_rows.append([_cap(citation, 120), excerpt])
            if len(cite_rows) >= 7:
                break
        story.append(_mk_table(cite_rows, [8.2 * cm, 9.2 * cm]))
    else:
        story.append(Paragraph("No hay citas legales disponibles para crédito público.", small_gray))

    # Exoneración
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("<b>Exoneración</b>", styles["Normal"]))
    if bundle.debtor_type == "company":
        story.append(
            Paragraph(
                "El deudor parece ser una empresa. La exoneración suele aplicarse a personas físicas; "
                "este bloque se muestra solo a nivel informativo.",
                styles["Normal"],
            )
        )
    exo = bundle.legal_citations.get("exoneracion") or []
    if exo:
        seen = set()
        cite_rows = [["Cita", "Extracto"]]
        for c in exo:
            citation = _safe(getattr(c, "citation", None))
            if not citation or citation in seen:
                continue
            seen.add(citation)
            excerpt = _cap(getattr(c, "excerpt", None) or "", 220) or "—"
            cite_rows.append([_cap(citation, 120), excerpt])
            if len(cite_rows) >= 7:
                break
        story.append(_mk_table(cite_rows, [8.2 * cm, 9.2 * cm]))
    else:
        story.append(Paragraph("No hay citas legales disponibles para exoneración.", small_gray))

    story.append(PageBreak())

    # =========================
    # 5) HOJA DE RUTA
    # =========================
    story.append(Paragraph("<b>5. HOJA DE RUTA (PASOS)</b>", heading_style))
    if not bundle.roadmap:
        story.append(Paragraph("No hay hoja de ruta generada.", styles["Normal"]))
    else:
        roadmap_rows = [["Fase", "Paso", "Prioridad", "Estado"]]
        for s in bundle.roadmap[:15]:
            roadmap_rows.append(
                [
                    _cap(s.phase, 24),
                    _cap(s.step, 120),
                    _cap(s.priority, 12),
                    _cap(s.status, 18),
                ]
            )
        story.append(_mk_table(roadmap_rows, [2.8 * cm, 10.0 * cm, 2.2 * cm, 2.5 * cm]))

    # =========================
    # FOOTER
    # =========================
    story.append(PageBreak())
    story.append(Paragraph("<b>FIN DEL INFORME</b>", heading_style))
    story.append(
        Paragraph(
            f"Sistema: {bundle.source_system} | Generado: {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S UTC')}",
            ParagraphStyle(
                "EcoFooter",
                parent=styles["Normal"],
                fontSize=8,
                textColor=COLOR_GRAY,
                alignment=TA_CENTER,
            ),
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

