from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services import courtpack_fs


def _build_pdf_with_fields_bytes() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(72, 800, "Formulario smoke test")
    c.acroForm.textfield(
        name="field_text_1",
        x=72,
        y=760,
        width=200,
        height=18,
        value="",
    )
    c.acroForm.checkbox(
        name="field_check_1",
        x=72,
        y=720,
        buttonStyle="check",
        checked=False,
    )
    c.showPage()
    c.save()
    return buf.getvalue()


def test_courtpack_read_pdf_form_fields_smoke(tmp_path: Path):
    pdf_path = tmp_path / "doc0.pdf"
    pdf_path.write_bytes(_build_pdf_with_fields_bytes())

    fields = courtpack_fs.read_pdf_form_fields(pdf_path)
    names = [f.name for f in fields]
    assert "field_text_1" in names
    assert "field_check_1" in names
