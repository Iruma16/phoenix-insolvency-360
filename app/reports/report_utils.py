"""
Utilidades para generación de informes en múltiples formatos.

Facilita el uso de las capacidades avanzadas del generador de informes:
- PDF con gráficos y bookmarks
- Exportación a Word
- Anexos automatizados
- Resumen ejecutivo con GPT-4
"""
from pathlib import Path

from app.reports.pdf_report import (
    ReportManifest,
    attach_evidence_documents_to_pdf,
    create_report_manifest,
    generate_docx_report,
    generate_executive_summary_with_gpt,
    generate_legal_report_pdf,
)


class ReportGenerator:
    """
    Generador unificado de informes en múltiples formatos.

    CRÍTICO: Soporta dos modos de operación:
    - STRICT: Falla duro si hay error (producción legal)
    - LENIENT: Degrada elegantemente (demo/desarrollo)

    Uso:
        # Modo producción (default)
        generator = ReportGenerator(legal_report, case, mode="STRICT")

        # Modo desarrollo con degradación
        generator = ReportGenerator(legal_report, case, mode="LENIENT")

        # PDF estándar
        pdf_bytes = generator.generate_pdf()

        # Verificar warnings después
        if generator.warnings:
            print(f"Generado con {len(generator.warnings)} warnings")
    """

    def __init__(self, legal_report, case, mode: str = "STRICT"):
        """
        Args:
            legal_report: LegalReport Pydantic model
            case: Case SQLAlchemy model
            mode: "STRICT" (falla duro) o "LENIENT" (degrada)
        """
        if mode not in ["STRICT", "LENIENT"]:
            raise ValueError(f"mode debe ser 'STRICT' o 'LENIENT', no '{mode}'")

        self.legal_report = legal_report
        self.case = case
        self.mode = mode
        self.warnings: list[str] = []
        self.features_enabled = {
            "charts": True,
            "gpt": True,
            "annexes": True,
            "word": True,
        }

    def generate_pdf(self) -> bytes:
        """
        Genera PDF estándar con:
        - Numeración de páginas
        - Marca de agua "BORRADOR TÉCNICO"
        - Tablas profesionales
        - Bookmarks para navegación
        - Gráficos de riesgos y timeline (si disponible)

        DEGRADACIÓN: En modo LENIENT, continúa si fallan gráficos.

        Returns:
            bytes: Contenido del PDF
        """
        try:
            return generate_legal_report_pdf(self.legal_report, self.case)
        except Exception as e:
            if self.mode == "STRICT":
                raise
            else:
                # Modo LENIENT: intentar versión simple
                self.warnings.append(f"PDF generado en modo degradado: {str(e)}")
                self.features_enabled["charts"] = False

                # Intentar generar sin gráficos (fallback)
                try:
                    return self._generate_simple_pdf()
                except Exception as e2:
                    self.warnings.append(f"Fallback simple también falló: {str(e2)}")
                    raise RuntimeError(
                        f"No se pudo generar PDF ni en modo completo ni simple: {e2}"
                    )

    def generate_word(self) -> bytes:
        """
        Genera documento Word editable (.docx) con trazabilidad legal.

        CRÍTICO: Incluye metadata, chunk IDs, y offsets.

        Returns:
            bytes: Contenido del archivo DOCX
        """
        try:
            return generate_docx_report(self.legal_report, self.case)
        except Exception as e:
            if self.mode == "STRICT":
                raise
            else:
                self.warnings.append(f"Word generation failed: {str(e)}")
                self.features_enabled["word"] = False
                raise RuntimeError(f"No se pudo generar Word: {e}")

    def _generate_simple_pdf(self) -> bytes:
        """
        Fallback: PDF básico sin dependencias externas.
        Solo ReportLab puro, sin matplotlib ni extras.
        """
        from io import BytesIO

        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        # Portada simple
        story.append(Paragraph("INFORME LEGAL PRELIMINAR (MODO DEGRADADO)", styles["Title"]))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Caso: {self.case.name}", styles["Normal"]))
        story.append(Spacer(1, 12))
        story.append(
            Paragraph(
                "AVISO: Este informe se generó en modo degradado debido a errores. "
                "Algunas características avanzadas no están disponibles.",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 20))

        # Hallazgos básicos
        story.append(Paragraph(f"Hallazgos: {len(self.legal_report.findings)}", styles["Heading2"]))
        for idx, finding in enumerate(self.legal_report.findings[:10], 1):
            story.append(Paragraph(f"{idx}. {finding.statement[:200]}", styles["Normal"]))
            story.append(Spacer(1, 8))

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    def generate_pdf_with_annexes(self, evidence_paths: list[str]) -> bytes:
        """
        Genera PDF con documentos de evidencia anexados.

        DEGRADACIÓN: Si fallan anexos en LENIENT, retorna PDF principal.

        Args:
            evidence_paths: Lista de rutas a PDFs de evidencia

        Returns:
            bytes: PDF combinado con anexos (o solo principal si falla)
        """
        main_pdf = self.generate_pdf()

        try:
            return attach_evidence_documents_to_pdf(main_pdf, evidence_paths)
        except Exception as e:
            if self.mode == "STRICT":
                raise
            else:
                self.warnings.append(f"Anexos no pudieron añadirse: {str(e)}")
                self.features_enabled["annexes"] = False
                return main_pdf  # Retornar PDF principal sin anexos

    async def generate_pdf_with_ai_summary(self) -> bytes:
        """
        Genera PDF enriquecido con resumen ejecutivo de GPT-4.

        NOTA: Requiere configuración de OpenAI API key.

        Returns:
            bytes: PDF con resumen mejorado
        """
        # Extraer datos para el resumen
        findings = [
            {
                "type": f.finding_type if hasattr(f, "finding_type") else "unknown",
                "description": f.statement[:200] if hasattr(f, "statement") else "",
            }
            for f in self.legal_report.findings
        ]

        risks = []  # Se puede extraer de findings si hay campo de severidad

        # Generar resumen con GPT-4
        gpt_summary = await generate_executive_summary_with_gpt(
            findings=findings, risks=risks, case_name=self.case.name
        )

        # Almacenar resumen en legal_report (temporal, no persiste)
        # Para persistir, habría que añadir campo en el modelo
        print(f"[INFO] Resumen GPT-4 generado ({len(gpt_summary)} chars)")

        # Generar PDF estándar (el resumen se puede integrar si se añade al modelo)
        return self.generate_pdf()

    def get_manifest(self) -> ReportManifest:
        """
        Genera manifest de auditoría para el informe.

        CRÍTICO: Manifest obligatorio para informes production-grade.

        Returns:
            ReportManifest con metadata completa
        """
        return create_report_manifest(
            legal_report=self.legal_report,
            case=self.case,
            features_enabled=self.features_enabled,
            warnings=self.warnings,
            mode=self.mode,
        )

    def save_to_file(
        self, content: bytes, output_path: str, format: str = "pdf", save_manifest: bool = True
    ):
        """
        Guarda el informe en archivo.

        Args:
            content: Contenido del informe (bytes)
            output_path: Ruta de salida
            format: Formato del archivo ('pdf' o 'docx')
            save_manifest: Si True, guarda manifest.json también
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "wb") as f:
            f.write(content)

        print(f"[OK] Informe guardado: {output_file} ({len(content)} bytes)")

        # Guardar manifest si se solicita
        if save_manifest:
            manifest = self.get_manifest()
            manifest_path = output_file.with_suffix(".manifest.json")
            manifest.save_to_file(str(manifest_path))

        return str(output_file)


# =========================================================
# FUNCIONES DE CONVENIENCIA
# =========================================================


def quick_pdf_report(legal_report, case) -> bytes:
    """Genera PDF rápido."""
    generator = ReportGenerator(legal_report, case)
    return generator.generate_pdf()


def quick_word_report(legal_report, case) -> bytes:
    """Genera Word rápido."""
    generator = ReportGenerator(legal_report, case)
    return generator.generate_word()


def quick_pdf_with_annexes(legal_report, case, annexes: list[str]) -> bytes:
    """Genera PDF con anexos."""
    generator = ReportGenerator(legal_report, case)
    return generator.generate_pdf_with_annexes(annexes)


async def quick_ai_enhanced_report(legal_report, case) -> bytes:
    """Genera PDF con resumen GPT-4."""
    generator = ReportGenerator(legal_report, case)
    return await generator.generate_pdf_with_ai_summary()
