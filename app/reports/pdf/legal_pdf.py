from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from .canvas import NumberedCanvas
from .styles import COLOR_DANGER, COLOR_GRAY, COLOR_PRIMARY


def generate_legal_report_pdf(legal_report, case) -> bytes:
    """
    Genera PDF simplificado desde LegalReport Pydantic (versión temporal).

    Args:
        legal_report: LegalReport Pydantic model
        case: Case SQLAlchemy model

    Returns:
        bytes: Contenido del PDF
    """
    buffer = BytesIO()

    # Crear documento
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    # Estilos
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=COLOR_PRIMARY,
        spaceAfter=30,
        alignment=TA_CENTER,
    )

    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=COLOR_PRIMARY,
        spaceAfter=12,
    )

    # Construir contenido
    story = []

    # ==========================================
    # PORTADA
    # ==========================================
    story.append(Spacer(1, 3 * cm))
    story.append(Paragraph("<b>INFORME LEGAL PRELIMINAR</b>", title_style))
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph(f"<b>Caso:</b> {case.name}", styles["Normal"]))
    story.append(Paragraph(f"<b>ID Caso:</b> {legal_report.case_id}", styles["Normal"]))
    # ✅ CORREGIDO: Usar source_system y schema_version en lugar de report_id (que no existe)
    story.append(
        Paragraph(
            f"<b>Sistema:</b> {legal_report.source_system} v{legal_report.schema_version}",
            styles["Normal"],
        )
    )
    story.append(
        Paragraph(
            f"<b>Generado:</b> {legal_report.generated_at.strftime('%d/%m/%Y %H:%M')}",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 2 * cm))

    # Firma del abogado (si está configurada en entorno)
    try:
        import os

        lawyer = (os.getenv("LAWYER_NAME") or "").strip()
        coleg = (os.getenv("LAWYER_COLLEGIATE_NUMBER") or "").strip()
        if lawyer and coleg:
            firm = (os.getenv("LAW_FIRM") or "").strip()
            bar = (os.getenv("LAWYER_BAR_ASSOCIATION") or "").strip()
            city = (os.getenv("LAWYER_OFFICE_CITY") or "").strip()
            lines = [f"<b>Abogado responsable:</b> {lawyer}", f"<b>Nº colegiado:</b> {coleg}"]
            if bar:
                lines.append(f"<b>Colegio:</b> {bar}")
            if firm:
                lines.append(f"<b>Despacho:</b> {firm}")
            if city:
                lines.append(f"<b>Sede:</b> {city}")
            story.append(Paragraph("<br/>".join(lines), styles["Normal"]))
            story.append(Spacer(1, 0.6 * cm))
    except Exception:
        pass

    # Alcance
    disclaimer = Paragraph(
        "<b>ALCANCE:</b> Este informe es un documento de trabajo elaborado a partir de la documentación aportada "
        "en el expediente y los datos disponibles a la fecha de emisión. "
        "Cuando un dato no conste en el expediente o no pueda verificarse, se indicará expresamente.",
        ParagraphStyle("Disclaimer", parent=styles["Normal"], textColor=COLOR_DANGER, fontSize=10),
    )
    story.append(disclaimer)
    story.append(PageBreak())

    # ==========================================
    # ASUNTO ANALIZADO
    # ==========================================
    story.append(Paragraph("<b>1. ASUNTO ANALIZADO</b>", heading_style))
    story.append(Paragraph(legal_report.issue_analyzed, styles["Normal"]))
    story.append(Spacer(1, 0.5 * cm))

    # ==========================================
    # HALLAZGOS
    # ==========================================
    story.append(
        Paragraph(f"<b>2. HALLAZGOS LEGALES ({len(legal_report.findings)})</b>", heading_style)
    )
    story.append(Spacer(1, 0.3 * cm))

    if not legal_report.findings:
        story.append(
            Paragraph(
                "No se identificaron hallazgos legales relevantes en el análisis técnico preliminar.",
                styles["Normal"],
            )
        )
    else:
        for idx, finding in enumerate(legal_report.findings, 1):
            # ✅ CORREGIDO: Usar statement truncado como título (finding.title no existe)
            title_text = (
                finding.statement[:80] + "..." if len(finding.statement) > 80 else finding.statement
            )
            story.append(Paragraph(f"<b>2.{idx}. {title_text}</b>", styles["Heading3"]))

            # ✅ CORREGIDO: Usar statement completo (finding.description no existe)
            story.append(Paragraph(finding.statement, styles["Normal"]))
            story.append(Spacer(1, 0.2 * cm))

            # ✅ CORREGIDO: Usar confidence_note si existe (finding.legal_basis y confidence_level no existen)
            if finding.confidence_note:
                story.append(
                    Paragraph(
                        f"<b>Nota de confianza:</b> {finding.confidence_note}",
                        ParagraphStyle(
                            "ConfNote", parent=styles["Normal"], fontSize=9, textColor=COLOR_GRAY
                        ),
                    )
                )
                story.append(Spacer(1, 0.2 * cm))

            # Evidencias
            if finding.evidence:
                story.append(
                    Paragraph(f"<b>Evidencias ({len(finding.evidence)}):</b>", styles["Normal"])
                )
                for ev_idx, evidence in enumerate(finding.evidence[:3], 1):  # Máx 3 evidencias
                    # Manejar filename opcional
                    ev_text = f"{ev_idx}. {evidence.filename if evidence.filename else evidence.document_id}"
                    if evidence.location.page_start:
                        ev_text += f" (pág. {evidence.location.page_start})"
                    story.append(
                        Paragraph(
                            ev_text,
                            ParagraphStyle(
                                "Evidence",
                                parent=styles["Normal"],
                                fontSize=9,
                                leftIndent=20,
                                textColor=COLOR_GRAY,
                            ),
                        )
                    )

                if len(finding.evidence) > 3:
                    story.append(
                        Paragraph(
                            f"... y {len(finding.evidence) - 3} evidencia(s) más",
                            ParagraphStyle(
                                "MoreEvidence",
                                parent=styles["Normal"],
                                fontSize=8,
                                leftIndent=20,
                                textColor=COLOR_GRAY,
                            ),
                        )
                    )

            story.append(Spacer(1, 0.5 * cm))

    # ==========================================
    # PIE DE PÁGINA FINAL
    # ==========================================
    story.append(PageBreak())
    story.append(Paragraph("<b>FIN DEL INFORME</b>", heading_style))
    story.append(Spacer(1, 1 * cm))
    story.append(
        Paragraph(
            f"Sistema: {legal_report.source_system} | Generado: {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S UTC')}",
            ParagraphStyle(
                "Footer",
                parent=styles["Normal"],
                fontSize=8,
                textColor=COLOR_GRAY,
                alignment=TA_CENTER,
            ),
        )
    )

    # Construir PDF con canvas personalizado (numeración de páginas)
    doc.build(story, canvasmaker=NumberedCanvas)

    # Retornar bytes
    pdf_bytes = buffer.getvalue()
    buffer.close()

    return pdf_bytes
