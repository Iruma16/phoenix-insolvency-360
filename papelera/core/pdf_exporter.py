# core/pdf_exporter.py
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import stringWidth
from datetime import datetime
import tempfile
from typing import Dict, Any


def _wrap_line(text: str, font: str, size: int, max_width: float):
    """Word-wrap simple para ReportLab."""
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = words[0]
    for w in words[1:]:
        test = current + " " + w
        if stringWidth(test, font, size) <= max_width:
            current = test
        else:
            lines.append(current)
            current = w
    lines.append(current)
    return lines


def generar_pdf_informe(
    informe_markdown: str,
    pruebas_forenses: Dict[str, Any],
    nombre_caso: str = "Phoenix Insolvency 360",
) -> str:
    """
    Genera un PDF legal SIN dependencias del sistema.
    Devuelve la ruta del fichero temporal creado.
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    c = canvas.Canvas(tmp.name, pagesize=A4)
    width, height = A4

    margin = 2 * cm
    x = margin
    y = height - margin

    def write(text: str, font="Helvetica", size=10, spacing=12):
        nonlocal y
        if y < margin + 2 * cm:
            c.showPage()
            y = height - margin
        c.setFont(font, size)
        max_w = width - 2 * margin
        for line in _wrap_line(text, font, size, max_w):
            c.drawString(x, y, line)
            y -= spacing

    # Cabecera
    write(nombre_caso, font="Helvetica-Bold", size=14, spacing=18)
    write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}", size=9, spacing=12)
    write(" ", spacing=10)

    # Informe
    write("INFORME EJECUTIVO", font="Helvetica-Bold", size=12, spacing=16)
    write(" ", spacing=10)
    for linea in (informe_markdown or "").splitlines():
        write(linea, size=10, spacing=12)

    write(" ", spacing=14)
    write("PRUEBAS FORENSES (RESUMEN)", font="Helvetica-Bold", size=12, spacing=16)
    write(" ", spacing=10)

    # Resumen breve de pruebas
    if isinstance(pruebas_forenses, dict):
        for k in ["coincidencias", "pagos_sin_factura", "facturas_sin_pago", "descuadres"]:
            v = pruebas_forenses.get(k, [])
            try:
                n = len(v)
            except Exception:
                n = 0
            write(f"- {k}: {n}", size=10, spacing=12)

    write(" ", spacing=14)
    write("Documento generado automáticamente por Phoenix Insolvency 360.", font="Helvetica-Oblique", size=8, spacing=10)
    write("No sustituye asesoramiento legal profesional.", font="Helvetica-Oblique", size=8, spacing=10)

    c.save()
    return tmp.name
