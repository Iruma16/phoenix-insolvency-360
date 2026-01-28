"""
Módulo de generación de reportes.
"""
from app.reports.pdf_report import build_report_payload, render_pdf

__all__ = ["build_report_payload", "render_pdf"]
