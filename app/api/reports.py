"""
Endpoint para generación de informes legales.
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.reports.report_generator import generate_case_report

router = APIRouter(prefix="/reports", tags=["reports"])


class GenerateReportRequest(BaseModel):
    case_id: str


@router.post("/generate")
def generate_report(
    payload: GenerateReportRequest,
    db: Session = Depends(get_db),
):
    """
    Genera un informe legal completo para un caso.

    Devuelve el path al archivo Markdown generado.
    El PDF se genera automáticamente si hay librerías disponibles.
    """
    try:
        md_path = generate_case_report(case_id=payload.case_id, db=db)

        return {
            "status": "success",
            "case_id": payload.case_id,
            "markdown_path": str(md_path),
            "pdf_path": str(md_path.with_suffix(".pdf"))
            if md_path.with_suffix(".pdf").exists()
            else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando informe: {str(e)}")


@router.get("/download/{case_id}/{filename:path}")
def download_report(case_id: str, filename: str):
    """
    Descarga un informe generado.

    Permite descargar archivos .md o .pdf desde reports/{case_id}/
    """
    reports_dir = Path(__file__).parent.parent.parent / "reports" / case_id
    file_path = reports_dir / filename

    # Validación de seguridad
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    if file_path.suffix not in [".md", ".pdf"]:
        raise HTTPException(status_code=400, detail="Tipo de archivo no permitido")

    if not file_path.is_relative_to(reports_dir):
        raise HTTPException(status_code=403, detail="Acceso denegado")

    media_type = "application/pdf" if file_path.suffix == ".pdf" else "text/markdown"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=filename,
    )
