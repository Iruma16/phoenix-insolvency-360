"""
Compatibilidad: `app.reports.pdf_report`.

Históricamente este módulo contenía un archivo monolítico (~2000 líneas). Para
mantener el repo limpio y modular, el generador PDF se ha movido a
`app.reports.pdf.*` y aquí dejamos un *facade* estable para no romper imports.

Camino oficial de generación PDF:
- `build_report_payload()` + `render_pdf()` (pipeline)
- `generate_report_for_case()` (helper)
- `generate_legal_report_pdf()` (PDF desde `LegalReport`)
"""

from app.reports.pdf import (  # noqa: F401
    NumberedCanvas,
    ReportManifest,
    attach_evidence_documents_to_pdf,
    build_report_payload,
    create_professional_table_style,
    create_report_manifest,
    create_risk_distribution_chart,
    create_timeline_chart,
    generate_docx_report,
    generate_legal_report_pdf,
    generate_report_for_case,
    render_pdf,
)
from app.reports.pdf.gpt_summary import generate_executive_summary_with_gpt  # noqa: F401

__all__ = [
    "NumberedCanvas",
    "create_professional_table_style",
    "create_risk_distribution_chart",
    "create_timeline_chart",
    "build_report_payload",
    "render_pdf",
    "generate_report_for_case",
    "generate_executive_summary_with_gpt",
    "attach_evidence_documents_to_pdf",
    "generate_docx_report",
    "ReportManifest",
    "create_report_manifest",
    "generate_legal_report_pdf",
]
