from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import BytesIO


@dataclass
class ReportManifest:
    """
    Manifest obligatorio para auditoría legal de informes.

    CRÍTICO: Todo informe production-grade DEBE incluir:
    - IDs únicos y trazables
    - Hashes de integridad
    - Versiones de sistema y schema
    - Features habilitadas
    - Warnings y estado

    Este manifest permite:
    - Verificar integridad del informe
    - Auditar qué características se usaron
    - Rastrear versión de generación
    - Detectar manipulación post-generación
    """

    # Identificación
    report_id: str
    case_id: str
    generated_at: datetime

    # Versiones
    phoenix_version: str
    schema_version: str

    # Integridad
    content_hash: str  # SHA256 del contenido legal

    # Features y estado
    features_enabled: dict[str, bool]  # {"charts": True, "gpt": False}
    warnings: list[str]
    is_production_grade: bool  # False si hay warnings críticos

    # Metadata adicional
    mode: str  # "STRICT" o "LENIENT"
    total_findings: int
    total_evidence: int

    def to_dict(self) -> dict:
        """Serializa manifest a dict."""
        return asdict(self)

    def to_json(self) -> str:
        """Serializa manifest a JSON."""
        import json

        return json.dumps(self.to_dict(), indent=2, default=str)

    def embed_in_pdf_metadata(self, pdf_bytes: bytes) -> bytes:
        """
        Embebe manifest en metadata del PDF.

        CRÍTICO: Permite verificar integridad desde PDF viewer.

        Args:
            pdf_bytes: Contenido del PDF

        Returns:
            PDF con metadata embedida
        """
        try:
            from PyPDF2 import PdfReader, PdfWriter

            reader = PdfReader(BytesIO(pdf_bytes))
            writer = PdfWriter()

            # Copiar todas las páginas
            for page in reader.pages:
                writer.add_page(page)

            # CRÍTICO: Embedir manifest en metadata
            writer.add_metadata(
                {
                    "/ReportID": self.report_id,
                    "/CaseID": self.case_id,
                    "/GeneratedAt": self.generated_at.isoformat(),
                    "/PhoenixVersion": self.phoenix_version,
                    "/SchemaVersion": self.schema_version,
                    "/ContentHash": self.content_hash,
                    "/IsProductionGrade": str(self.is_production_grade),
                    "/Mode": self.mode,
                    "/Warnings": str(len(self.warnings)),
                }
            )

            output = BytesIO()
            writer.write(output)
            output.seek(0)

            return output.getvalue()

        except ImportError:
            print("[WARN] PyPDF2 no disponible, no se pudo embedir metadata")
            return pdf_bytes
        except Exception as e:
            print(f"[WARN] Error embebiendo metadata: {e}")
            return pdf_bytes

    def save_to_file(self, output_path: str):
        """Guarda manifest como JSON."""
        from pathlib import Path

        manifest_path = Path(output_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

        print(f"[OK] Manifest guardado: {manifest_path}")


def create_report_manifest(
    legal_report,
    case,
    features_enabled: dict[str, bool],
    warnings: list[str],
    mode: str = "STRICT",
) -> ReportManifest:
    """
    Crea manifest para informe legal.

    Args:
        legal_report: LegalReport Pydantic model
        case: Case SQLAlchemy model
        features_enabled: Dict de features habilitadas
        warnings: Lista de warnings durante generación
        mode: "STRICT" o "LENIENT"

    Returns:
        ReportManifest completo
    """
    import hashlib
    import uuid

    # Generar report ID único
    report_id = f"report_{uuid.uuid4().hex[:16]}"

    # Calcular content hash
    content_for_hash = f"{case.case_id}|{legal_report.issue_analyzed}"
    for finding in legal_report.findings:
        content_for_hash += f"|{finding.statement}"
    content_hash = hashlib.sha256(content_for_hash.encode()).hexdigest()

    # Contar evidencias
    total_evidence = sum(len(f.evidence) for f in legal_report.findings)

    # Determinar si es production-grade
    critical_warnings = [w for w in warnings if "ERROR" in w or "FAIL" in w.upper()]
    is_production_grade = (
        mode == "STRICT" and len(critical_warnings) == 0 and features_enabled.get("charts", False)
    )

    return ReportManifest(
        report_id=report_id,
        case_id=case.case_id,
        generated_at=datetime.now(timezone.utc),
        phoenix_version="1.0.0",  # TODO: obtener de config
        schema_version=legal_report.schema_version,
        content_hash=content_hash,
        features_enabled=features_enabled,
        warnings=warnings,
        is_production_grade=is_production_grade,
        mode=mode,
        total_findings=len(legal_report.findings),
        total_evidence=total_evidence,
    )
