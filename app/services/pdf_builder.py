"""
PDF BUILDER - Construcción de PDF inmutable certificado (PANTALLA 6).

PRINCIPIO: Esta capa NO genera contenido nuevo, NO analiza, NO certifica.
SOLO EMPAQUETA Y ENTREGA el resultado certificado.

PROHIBIDO:
- generar PDF sin trace existente
- generar PDF sin manifest existente
- regenerar PDF con datos distintos
- editar el contenido del informe
- ocultar hashes, IDs o avisos legales
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Optional, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

from app.models.legal_report import LegalReport
from app.trace.models import ExecutionTrace
from app.trace.manifest import HardManifest, ExecutionLimits


def _execution_limits_to_text(limits: ExecutionLimits) -> List[str]:
    """
    Convierte ExecutionLimits a lista de textos descriptivos.
    """
    texts = []
    if limits.cannot_process_without_documents:
        texts.append("No realiza análisis sin documentos aportados")
    if limits.cannot_generate_without_evidence:
        texts.append("No genera respuestas sin evidencia documental")
    if limits.cannot_guarantee_legal_validity:
        texts.append("No garantiza validez legal (solo técnica)")
    if limits.requires_human_review:
        texts.append("Requiere revisión humana experta obligatoria")
    return texts


def _build_cover_page(
    case_id: str,
    report_id: str,
    trace_id: str,
    manifest: HardManifest,
    styles: dict
) -> list:
    """
    Construye la portada del PDF.
    
    Incluye:
    - case_id, report_id, trace_id, manifest_id
    - system_version
    - fecha de certificación
    """
    elements = []
    
    # Título principal
    elements.append(Spacer(1, 2*cm))
    title = Paragraph(
        "<b>INFORME LEGAL CERTIFICADO</b>",
        styles['Title']
    )
    elements.append(title)
    elements.append(Spacer(1, 1*cm))
    
    # Subtítulo
    subtitle = Paragraph(
        "Sistema Phoenix Legal - Análisis Automatizado de Documentación Concursal",
        styles['Heading2']
    )
    elements.append(subtitle)
    elements.append(Spacer(1, 2*cm))
    
    # Tabla de identificadores
    data = [
        ['<b>Campo</b>', '<b>Valor</b>'],
        ['ID de Caso', case_id],
        ['ID de Informe', report_id],
        ['ID de Trace', trace_id],
        ['ID de Manifest', manifest.trace_id],  # El manifest usa trace_id
        ['Versión del Sistema', manifest.system_version],
        ['Fecha de Certificación', manifest.signed_at.strftime('%Y-%m-%d %H:%M:%S UTC')],
    ]
    
    table = Table(data, colWidths=[8*cm, 10*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 2*cm))
    
    # Nota de inmutabilidad
    note = Paragraph(
        "<i>Este documento representa una ejecución única e inmutable del sistema. "
        "Los identificadores mostrados garantizan la trazabilidad completa del análisis.</i>",
        styles['Normal']
    )
    elements.append(note)
    
    elements.append(PageBreak())
    
    return elements


def _build_legal_disclaimer(
    manifest: HardManifest,
    report: LegalReport,
    styles: dict
) -> list:
    """
    Construye la sección de aviso legal.
    
    Incluye:
    - Texto fijo sobre uso orientativo
    - Límites del sistema (execution_limits)
    - Disclaimer del informe
    """
    elements = []
    
    # Título de sección
    elements.append(Paragraph("<b>AVISO LEGAL</b>", styles['Heading1']))
    elements.append(Spacer(1, 0.5*cm))
    
    # Disclaimer del informe (de PANTALLA 4)
    elements.append(Paragraph("<b>Naturaleza del Informe:</b>", styles['Heading3']))
    elements.append(Spacer(1, 0.3*cm))
    disclaimer_para = Paragraph(report.disclaimer_legal, styles['Justify'])
    elements.append(disclaimer_para)
    elements.append(Spacer(1, 0.5*cm))
    
    # Límites del sistema (del manifest)
    elements.append(Paragraph("<b>Límites Declarados del Sistema:</b>", styles['Heading3']))
    elements.append(Spacer(1, 0.3*cm))
    
    limits_text = _execution_limits_to_text(manifest.execution_limits)
    for limit in limits_text:
        limit_para = Paragraph(f"• {limit}", styles['Normal'])
        elements.append(limit_para)
        elements.append(Spacer(1, 0.2*cm))
    
    elements.append(PageBreak())
    
    return elements


def _build_legal_findings(
    report: LegalReport,
    styles: dict
) -> list:
    """
    Construye la sección de hallazgos legales.
    
    Incluye:
    - Asunto analizado
    - Cada hallazgo con su base legal y evidencia resumida
    """
    elements = []
    
    # Título de sección
    elements.append(Paragraph("<b>INFORME LEGAL</b>", styles['Heading1']))
    elements.append(Spacer(1, 0.5*cm))
    
    # Asunto analizado
    elements.append(Paragraph("<b>Asunto Analizado:</b>", styles['Heading3']))
    elements.append(Spacer(1, 0.3*cm))
    issue_para = Paragraph(report.issue_analyzed, styles['Justify'])
    elements.append(issue_para)
    elements.append(Spacer(1, 0.5*cm))
    
    # Hallazgos
    if report.findings:
        elements.append(Paragraph(
            f"<b>Hallazgos Identificados ({len(report.findings)}):</b>",
            styles['Heading2']
        ))
        elements.append(Spacer(1, 0.5*cm))
        
        for idx, finding in enumerate(report.findings, 1):
            # Título del hallazgo
            elements.append(Paragraph(
                f"<b>Hallazgo {idx}: {finding.title}</b>",
                styles['Heading3']
            ))
            elements.append(Spacer(1, 0.3*cm))
            
            # Descripción
            desc_para = Paragraph(finding.description, styles['Justify'])
            elements.append(desc_para)
            elements.append(Spacer(1, 0.3*cm))
            
            # Base legal
            elements.append(Paragraph("<b>Base Legal:</b>", styles['Normal']))
            for legal_ref in finding.legal_basis:
                legal_text = f"• {legal_ref.law_name}, Art. {legal_ref.article}: {legal_ref.description}"
                legal_para = Paragraph(legal_text, styles['Normal'])
                elements.append(legal_para)
            elements.append(Spacer(1, 0.3*cm))
            
            # Nivel de confianza
            confidence_text = f"<b>Nivel de Confianza:</b> {finding.confidence_level.value}"
            elements.append(Paragraph(confidence_text, styles['Normal']))
            elements.append(Spacer(1, 0.3*cm))
            
            # Evidencia resumida
            elements.append(Paragraph(
                f"<b>Evidencia Documental ({len(finding.evidence)} elementos):</b>",
                styles['Normal']
            ))
            for ev_idx, evidence in enumerate(finding.evidence[:3], 1):  # Limitar a 3 evidencias
                ev_text = (
                    f"  {ev_idx}. Documento: {evidence.filename}, "
                    f"Chunk: {evidence.chunk_id}, "
                    f"Ubicación: chars {evidence.location.start_char}-{evidence.location.end_char}"
                )
                if evidence.location.page_start:
                    ev_text += f", página {evidence.location.page_start}"
                ev_para = Paragraph(ev_text, styles['Small'])
                elements.append(ev_para)
            
            if len(finding.evidence) > 3:
                more_text = f"  ... y {len(finding.evidence) - 3} elementos adicionales de evidencia."
                elements.append(Paragraph(more_text, styles['Small']))
            
            elements.append(Spacer(1, 0.5*cm))
    else:
        elements.append(Paragraph(
            "No se identificaron hallazgos que requieran traducción legal en el momento de la generación del informe.",
            styles['Justify']
        ))
    
    elements.append(PageBreak())
    
    return elements


def _build_traceability_summary(
    trace: ExecutionTrace,
    styles: dict
) -> list:
    """
    Construye la sección de resumen de trazabilidad.
    
    Incluye:
    - Timeline resumido de decisiones
    - Chunks y documentos utilizados
    """
    elements = []
    
    # Título de sección
    elements.append(Paragraph("<b>RESUMEN DE TRAZABILIDAD</b>", styles['Heading1']))
    elements.append(Spacer(1, 0.5*cm))
    
    # Información de ejecución
    exec_info = [
        f"<b>Modo de Ejecución:</b> {trace.execution_mode}",
        f"<b>Inicio:</b> {trace.execution_timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}",
    ]
    if trace.completed_at:
        exec_info.append(f"<b>Finalización:</b> {trace.completed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    for info in exec_info:
        elements.append(Paragraph(info, styles['Normal']))
    elements.append(Spacer(1, 0.5*cm))
    
    # Documentos y chunks utilizados
    elements.append(Paragraph("<b>Recursos Utilizados:</b>", styles['Heading3']))
    elements.append(Spacer(1, 0.3*cm))
    resources_text = [
        f"• Documentos analizados: {len(trace.document_ids)}",
        f"• Chunks procesados: {len(trace.chunk_ids)}",
        f"• Decisiones registradas: {len(trace.decisions)}",
    ]
    for text in resources_text:
        elements.append(Paragraph(text, styles['Normal']))
    elements.append(Spacer(1, 0.5*cm))
    
    # Timeline de decisiones (resumido)
    if trace.decisions:
        elements.append(Paragraph("<b>Timeline de Decisiones (primeras 10):</b>", styles['Heading3']))
        elements.append(Spacer(1, 0.3*cm))
        
        for decision in trace.decisions[:10]:
            decision_text = (
                f"• [{decision.timestamp.strftime('%H:%M:%S')}] "
                f"{decision.step_name} ({decision.decision_type}): {decision.description[:80]}..."
            )
            elements.append(Paragraph(decision_text, styles['Small']))
        
        if len(trace.decisions) > 10:
            more_text = f"... y {len(trace.decisions) - 10} decisiones adicionales registradas."
            elements.append(Paragraph(more_text, styles['Small']))
    
    elements.append(PageBreak())
    
    return elements


def _build_technical_certificate(
    manifest: HardManifest,
    styles: dict
) -> list:
    """
    Construye la sección de certificado técnico.
    
    Incluye:
    - HardManifest completo
    - integrity_hash (visible)
    - Firma temporal (signed_at)
    """
    elements = []
    
    # Título de sección
    elements.append(Paragraph("<b>CERTIFICADO TÉCNICO</b>", styles['Heading1']))
    elements.append(Spacer(1, 0.5*cm))
    
    # Descripción
    cert_desc = Paragraph(
        "Este certificado garantiza la integridad y trazabilidad completa del análisis realizado. "
        "El hash de integridad permite verificar que el contenido no ha sido modificado.",
        styles['Justify']
    )
    elements.append(cert_desc)
    elements.append(Spacer(1, 0.5*cm))
    
    # Datos del manifest
    data = [
        ['<b>Campo</b>', '<b>Valor</b>'],
        ['Trace ID', manifest.trace_id],
        ['Case ID', manifest.case_id],
        ['Hash de Integridad', manifest.integrity_hash[:32] + '...'],  # Truncar para display
        ['Firmado en', manifest.signed_at.strftime('%Y-%m-%d %H:%M:%S UTC')],
        ['Versión del Sistema', manifest.system_version],
    ]
    
    # Añadir schema versions
    data.append(['Schema: chunk', manifest.schema_versions.chunk_schema])
    data.append(['Schema: rag', manifest.schema_versions.rag_schema])
    data.append(['Schema: legal_output', manifest.schema_versions.legal_output_schema])
    data.append(['Schema: trace', manifest.schema_versions.trace_schema])
    
    table = Table(data, colWidths=[6*cm, 12*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Hash completo en monospace
    elements.append(Paragraph("<b>Hash de Integridad Completo (SHA256):</b>", styles['Normal']))
    elements.append(Spacer(1, 0.2*cm))
    hash_style = ParagraphStyle(
        'MonoHash',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=8,
        wordWrap='CJK'
    )
    hash_para = Paragraph(manifest.integrity_hash, hash_style)
    elements.append(hash_para)
    
    return elements


def build_certified_pdf(
    case_id: str,
    report: LegalReport,
    trace: ExecutionTrace,
    manifest: HardManifest
) -> BytesIO:
    """
    Construye el PDF certificado completo.
    
    Contenido en orden:
    1. Portada (con IDs)
    2. Aviso legal
    3. Informe legal completo
    4. Resumen de trazabilidad
    5. Certificado técnico
    
    Args:
        case_id: ID del caso
        report: LegalReport certificado
        trace: ExecutionTrace inmutable
        manifest: HardManifest certificado
        
    Returns:
        BytesIO con el PDF generado
    """
    # Verificar coherencia de IDs
    if report.case_id != case_id:
        raise ValueError(f"Incoherencia: report.case_id ({report.case_id}) != case_id ({case_id})")
    
    if trace.case_id != case_id:
        raise ValueError(f"Incoherencia: trace.case_id ({trace.case_id}) != case_id ({case_id})")
    
    if manifest.case_id != case_id:
        raise ValueError(f"Incoherencia: manifest.case_id ({manifest.case_id}) != case_id ({case_id})")
    
    # Crear buffer
    buffer = BytesIO()
    
    # Crear documento
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    # Estilos
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='Justify',
        parent=styles['Normal'],
        alignment=TA_JUSTIFY,
        fontSize=10
    ))
    styles.add(ParagraphStyle(
        name='Small',
        parent=styles['Normal'],
        fontSize=8
    ))
    styles['Title'].alignment = TA_CENTER
    styles['Heading2'].alignment = TA_CENTER
    
    # Construir contenido
    elements = []
    
    # 1. Portada
    elements.extend(_build_cover_page(
        case_id, report.report_id, trace.trace_id, manifest, styles
    ))
    
    # 2. Aviso legal
    elements.extend(_build_legal_disclaimer(manifest, report, styles))
    
    # 3. Informe legal
    elements.extend(_build_legal_findings(report, styles))
    
    # 4. Resumen de trazabilidad
    elements.extend(_build_traceability_summary(trace, styles))
    
    # 5. Certificado técnico
    elements.extend(_build_technical_certificate(manifest, styles))
    
    # Construir PDF
    doc.build(elements)
    
    # Retornar buffer
    buffer.seek(0)
    return buffer

