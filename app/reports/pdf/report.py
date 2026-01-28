from datetime import datetime, timezone
from typing import Any

from app.core.variables import DATA

from .payload import build_report_payload
from .render import render_pdf


def generate_report_for_case(case_id: str, analysis_result: dict[str, Any]) -> str:
    """
    Función conveniente que genera un PDF del informe para un caso.

    Args:
        case_id: ID del caso
        analysis_result: Resultado del análisis completo

    Returns:
        Ruta del PDF generado
    """

    # Construir payload
    payload = build_report_payload(case_id, analysis_result)

    # Definir ruta de salida
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    reports_dir = DATA / "cases" / case_id / "reports"
    pdf_filename = f"phoenix_legal_report_{case_id}_{timestamp}.pdf"
    pdf_path = reports_dir / pdf_filename

    # Renderizar PDF
    output_path = render_pdf(payload, str(pdf_path))

    # Actualizar latest.txt
    latest_file = reports_dir / "latest.txt"
    with open(latest_file, "w", encoding="utf-8") as f:
        f.write(pdf_filename)

    return output_path
