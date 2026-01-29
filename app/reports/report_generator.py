"""
Generador de informes legales profesionales.

Consume outputs del Auditor y Prosecutor para generar informes en Markdown y PDF.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import os
from sqlalchemy.orm import Session

from app.agents.agent_1_auditor.runner import run_auditor
from app.agents.agent_2_prosecutor.runner import run_prosecutor_from_auditor
from app.agents.handoff import build_agent2_payload
from app.core.database import get_session_factory

# =========================================================
# CONFIGURACIÓN
# =========================================================

REPORTS_BASE_DIR = Path(__file__).parent.parent.parent / "reports"


def _ensure_reports_dir(case_id: str) -> Path:
    """Asegura que existe el directorio de informes para el caso."""
    case_dir = REPORTS_BASE_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


def _format_date(date_str: Optional[str]) -> str:
    """Formatea una fecha para el informe."""
    if not date_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return date_str


def _lawyer_signature_md() -> list[str]:
    """
    Firma del abogado (configurable por variables de entorno).
    """
    name = (os.getenv("LAWYER_NAME") or "").strip()
    coleg = (os.getenv("LAWYER_COLLEGIATE_NUMBER") or "").strip()
    bar = (os.getenv("LAWYER_BAR_ASSOCIATION") or "").strip()
    firm = (os.getenv("LAW_FIRM") or "").strip()
    city = (os.getenv("LAWYER_OFFICE_CITY") or "").strip()

    if not name or not coleg:
        return []

    out = [f"**Abogado responsable:** {name}", f"**Nº colegiado:** {coleg}"]
    if bar:
        out.append(f"**Colegio:** {bar}")
    if firm:
        out.append(f"**Despacho:** {firm}")
    if city:
        out.append(f"**Sede:** {city}")
    return out


def _build_markdown_report(
    case_id: str,
    auditor_result,
    prosecutor_result,
    auditor_fallback: bool,
) -> str:
    """
    Construye el contenido Markdown del informe legal.

    Args:
        case_id: ID del caso
        auditor_result: Resultado del Auditor (AuditorResult)
        prosecutor_result: Resultado del Prosecutor (ProsecutorResult)
        auditor_fallback: True si el Auditor usó fallback
    """
    now = datetime.now()
    report_date = now.strftime("%d/%m/%Y %H:%M")

    md_lines = []

    # Encabezado
    md_lines.append("# INFORME LEGAL (DOCUMENTO DE TRABAJO)")
    md_lines.append("")
    md_lines.append(f"**Caso:** {case_id}")
    md_lines.append(f"**Fecha de generación:** {report_date}")
    sig_lines = _lawyer_signature_md()
    if sig_lines:
        md_lines.append("")
        md_lines.extend(sig_lines)
    md_lines.append("")
    md_lines.append(
        "**Alcance:** Documento de trabajo para orientar próximos pasos, elaborado a partir de la documentación aportada. "
        "Cuando un hecho o dato no conste, se indicará expresamente."
    )
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    # Sección 1: Resumen Ejecutivo
    md_lines.append("## 1. RESUMEN EJECUTIVO")
    md_lines.append("")
    md_lines.append(auditor_result.summary)
    md_lines.append("")

    # Advertencia si hubo fallback
    if auditor_fallback:
        md_lines.append("**ADVERTENCIA:** El análisis se realizó con contexto limitado (documentación insuficiente).")
        md_lines.append("")

    # Sección 2: Riesgos Detectados por el Auditor
    md_lines.append("## 2. RIESGOS LEGALES DETECTADOS")
    md_lines.append("")
    if auditor_result.risks:
        for i, risk in enumerate(auditor_result.risks, 1):
            md_lines.append(f"{i}. {risk}")
        md_lines.append("")
    else:
        md_lines.append("No se detectaron riesgos específicos.")
        md_lines.append("")

    # Sección 3: Acciones Recomendadas
    md_lines.append("## 3. ACCIONES RECOMENDADAS")
    md_lines.append("")
    if auditor_result.next_actions:
        for i, action in enumerate(auditor_result.next_actions, 1):
            md_lines.append(f"{i}. {action}")
        md_lines.append("")
    else:
        md_lines.append("No se proponen acciones específicas en este momento.")
        md_lines.append("")

    # Sección 4: Evaluación de calificación (riesgos)
    md_lines.append("## 4. EVALUACIÓN DE RIESGOS EN FASE DE CALIFICACIÓN")
    md_lines.append("")
    md_lines.append(f"**Nivel de riesgo global:** {prosecutor_result.overall_risk_level.upper()}")
    md_lines.append("")
    md_lines.append(prosecutor_result.summary_for_lawyer)
    md_lines.append("")

    if prosecutor_result.blocking_recommendation:
        md_lines.append(
            "**RECOMENDACIÓN DE CAUTELA:** Se desaconseja presentar el concurso sin medidas defensivas previas."
        )
        md_lines.append("")

    md_lines.append(f"**Hallazgos críticos:** {prosecutor_result.critical_findings_count}")
    md_lines.append("")

    # Sección 5: Hallazgos estructurados (condicionales)
    md_lines.append("## 5. HALLAZGOS Y FUNDAMENTO (POR INDICIO)")
    md_lines.append("")
    if prosecutor_result.accusations:
        for i, acc in enumerate(prosecutor_result.accusations, 1):
            md_lines.append(f"### 5.{i} {acc.title}")
            md_lines.append("")
            md_lines.append(f"**Base legal (referencia):** {acc.legal_ground.replace('_', ' ').title()}")
            md_lines.append(f"**Nivel de riesgo:** {acc.risk_level.upper()}")
            md_lines.append("")
            md_lines.append("**Descripción (condicional):**")
            md_lines.append(acc.description)
            md_lines.append("")
            md_lines.append("**Razonamiento:**")
            md_lines.append(acc.reasoning)
            md_lines.append("")

            # Fundamentos legales
            if acc.legal_articles:
                md_lines.append("**Fundamentos legales (a verificar con texto literal si procede):**")
                for article in acc.legal_articles:
                    md_lines.append(f"- {article}")
                md_lines.append("")

            # Jurisprudencia
            if acc.jurisprudence:
                md_lines.append("**Jurisprudencia relevante:**")
                for jur in acc.jurisprudence:
                    md_lines.append(f"- {jur}")
                md_lines.append("")

            # Evidencias
            if acc.evidences:
                md_lines.append("**Evidencias documentales:**")
                for j, evidence in enumerate(
                    acc.evidences[:5], 1
                ):  # Máximo 5 evidencias por acusación
                    md_lines.append(
                        f"{j}. **Documento:** {evidence.document_name or evidence.document_id}"
                    )
                    if evidence.date:
                        md_lines.append(f"   **Fecha:** {_format_date(evidence.date)}")
                    if evidence.excerpt:
                        excerpt_short = (
                            evidence.excerpt[:200] + "..."
                            if len(evidence.excerpt) > 200
                            else evidence.excerpt
                        )
                        md_lines.append(f"   **Extracto:** {excerpt_short}")
                    md_lines.append("")

            md_lines.append("---")
            md_lines.append("")
    else:
        md_lines.append("No se detectaron hallazgos específicos con la documentación disponible.")
        md_lines.append("")

    # Sección 6: Trazabilidad y Metadatos
    md_lines.append("## 6. TRAZABILIDAD")
    md_lines.append("")
    md_lines.append(f"- **Caso analizado:** {case_id}")
    md_lines.append(f"- **Fecha de análisis:** {report_date}")
    md_lines.append(f"- **Nivel de riesgo global:** {prosecutor_result.overall_risk_level}")
    md_lines.append(f"- **Total de hallazgos:** {len(prosecutor_result.accusations)}")
    md_lines.append(f"- **Hallazgos críticos:** {prosecutor_result.critical_findings_count}")
    if auditor_fallback:
        md_lines.append("- **Alcance:** Documentación limitada (faltan elementos para concluir con plena seguridad)")
    else:
        md_lines.append("- **Alcance:** Elaborado con la documentación aportada en el expediente")
    md_lines.append("")

    # Pie de página
    md_lines.append("---")
    md_lines.append("")
    md_lines.append(
        "*Este informe es un documento de trabajo elaborado a partir de la documentación aportada y los datos disponibles en el expediente.*"
    )
    md_lines.append(f"*Generado el {report_date}*")
    md_lines.append("")

    return "\n".join(md_lines)


def _generate_pdf_from_markdown(md_path: Path, pdf_path: Path) -> None:
    """
    Genera un PDF a partir de un archivo Markdown.

    Intenta usar diferentes librerías en orden de preferencia:
    1. weasyprint + markdown (recomendado)
    2. reportlab (fallback básico)

    Si ninguna está disponible, genera un PDF básico con reportlab si está instalado,
    o lanza RuntimeError indicando que se requiere instalar una librería.
    """
    try:
        # Intentar con weasyprint (mejor calidad)
        import markdown
        from weasyprint import CSS, HTML

        with open(md_path, encoding="utf-8") as f:
            md_content = f.read()

        # Convertir Markdown a HTML
        html_content = markdown.markdown(
            md_content,
            extensions=["extra", "codehilite", "tables"],
        )

        # Añadir estilos básicos
        styles = CSS(
            string="""
            @page {
                size: A4;
                margin: 2cm;
            }
            body {
                font-family: Arial, sans-serif;
                font-size: 11pt;
                line-height: 1.6;
            }
            h1 {
                font-size: 18pt;
                margin-top: 20pt;
                margin-bottom: 10pt;
            }
            h2 {
                font-size: 14pt;
                margin-top: 15pt;
                margin-bottom: 8pt;
            }
            h3 {
                font-size: 12pt;
                margin-top: 12pt;
                margin-bottom: 6pt;
            }
            p {
                margin-bottom: 8pt;
            }
            ul, ol {
                margin-bottom: 8pt;
            }
        """
        )

        HTML(string=html_content).write_pdf(pdf_path, stylesheets=[styles])
        return
    except ImportError:
        pass

    try:
        # Fallback: reportlab básico
        import re

        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        with open(md_path, encoding="utf-8") as f:
            content = f.read()

        # Procesar líneas básicas
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                story.append(Spacer(1, 0.2 * cm))
                continue

            # Detectar headers
            if line.startswith("# "):
                text = line[2:].strip()
                story.append(Paragraph(text, styles["Heading1"]))
            elif line.startswith("## "):
                text = line[3:].strip()
                story.append(Paragraph(text, styles["Heading2"]))
            elif line.startswith("### "):
                text = line[4:].strip()
                story.append(Paragraph(text, styles["Heading3"]))
            elif line.startswith("- ") or line.startswith("* "):
                text = line[2:].strip()
                # Eliminar markdown básico
                text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
                story.append(Paragraph(f"• {text}", styles["Normal"]))
            else:
                # Texto normal, limpiar markdown básico
                text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
                text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
                story.append(Paragraph(text, styles["Normal"]))

            story.append(Spacer(1, 0.1 * cm))

        doc.build(story)
        return
    except ImportError:
        raise RuntimeError(
            "No se encontró ninguna librería para generar PDF. "
            "Instala una de: weasyprint (recomendado) o reportlab. "
            "El informe Markdown está disponible sin PDF."
        )


def generate_case_report(case_id: str, db: Optional[Session] = None) -> Path:
    """
    Genera un informe legal completo para un caso.

    Args:
        case_id: ID del caso a analizar
        db: Sesión de base de datos (opcional, se crea si no se proporciona)

    Returns:
        Path al archivo Markdown generado

    Raises:
        ValueError: Si el caso no existe o no hay datos
        RuntimeError: Si falla la generación del PDF
    """
    # Crear sesión si no se proporciona
    if db is None:
        SessionLocal = get_session_factory()
        db = SessionLocal()
        close_db = True
    else:
        close_db = False

    try:
        # 1. Ejecutar Auditor
        print(f"📊 Ejecutando análisis del Auditor para caso {case_id}...")
        question = "Analiza los riesgos legales y documentales del caso"
        auditor_result, auditor_fallback = run_auditor(
            case_id=case_id,
            question=question,
            db=db,
        )

        # 2. Construir handoff y ejecutar Prosecutor
        print(f"⚖️  Ejecutando análisis del Prosecutor para caso {case_id}...")
        handoff_payload = build_agent2_payload(
            auditor_result=auditor_result,
            case_id=case_id,
            question=question,
            auditor_fallback=auditor_fallback,
        )

        prosecutor_result = run_prosecutor_from_auditor(
            handoff_payload=handoff_payload.dict(),
        )

        # 3. Generar Markdown
        print("📝 Generando informe Markdown...")
        markdown_content = _build_markdown_report(
            case_id=case_id,
            auditor_result=auditor_result,
            prosecutor_result=prosecutor_result,
            auditor_fallback=auditor_fallback,
        )

        # 4. Guardar Markdown
        reports_dir = _ensure_reports_dir(case_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        md_filename = f"informe_{case_id}_{timestamp}.md"
        md_path = reports_dir / md_filename

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        print(f"Informe Markdown guardado: {md_path}")

        # 5. Generar PDF
        try:
            print("Generando PDF...")
            pdf_filename = f"informe_{case_id}_{timestamp}.pdf"
            pdf_path = reports_dir / pdf_filename
            _generate_pdf_from_markdown(md_path, pdf_path)
            print(f"Informe PDF guardado: {pdf_path}")
        except Exception as e:
            print(f"No se pudo generar PDF: {e}")
            print(f"   El informe Markdown está disponible en: {md_path}")

        return md_path

    finally:
        if close_db:
            db.close()
