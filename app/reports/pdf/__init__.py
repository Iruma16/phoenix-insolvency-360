"""
Paquete PDF (Phoenix Legal).

Este paquete agrupa el generador de informes en módulos pequeños para mantener el
repo limpio (sin archivos monolíticos).
"""

from .attachments import attach_evidence_documents_to_pdf
from .canvas import NumberedCanvas
from .charts import create_risk_distribution_chart, create_timeline_chart
from .docx import generate_docx_report
from .legal_pdf import generate_legal_report_pdf
from .manifest import ReportManifest, create_report_manifest
from .payload import build_report_payload
from .render import render_pdf
from .report import generate_report_for_case
from .styles import (
    COLOR_DANGER,
    COLOR_GRAY,
    COLOR_PRIMARY,
    COLOR_SECONDARY,
    COLOR_SUCCESS,
    COLOR_TABLE_ALT,
    COLOR_WARNING,
    create_professional_table_style,
)

__all__ = [
    "NumberedCanvas",
    "COLOR_PRIMARY",
    "COLOR_SECONDARY",
    "COLOR_DANGER",
    "COLOR_WARNING",
    "COLOR_SUCCESS",
    "COLOR_GRAY",
    "COLOR_TABLE_ALT",
    "create_professional_table_style",
    "create_risk_distribution_chart",
    "create_timeline_chart",
    "build_report_payload",
    "render_pdf",
    "generate_report_for_case",
    "attach_evidence_documents_to_pdf",
    "generate_docx_report",
    "ReportManifest",
    "create_report_manifest",
    "generate_legal_report_pdf",
]
