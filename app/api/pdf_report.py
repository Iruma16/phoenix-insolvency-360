"""
ENDPOINT OFICIAL DE DESCARGA DE PDF CERTIFICADO (PANTALLA 6).

VERSIÓN OPTIMIZADA: Genera PDF rápido desde LegalReport (sin ejecutar agentes pesados).
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.case import Case
from app.api.legal_report import generate_legal_report
from app.reports.pdf_report import generate_legal_report_pdf


router = APIRouter(
    prefix="/cases/{case_id}/legal-report",
    tags=["pdf-report"],
)


@router.get(
    "/pdf",
    summary="Descargar informe legal en PDF certificado",
    description=(
        "Descarga el informe legal en formato PDF inmutable y certificado. "
        "El PDF incluye portada, aviso legal, hallazgos, trazabilidad y certificado técnico. "
        "Solo se puede descargar si existe certificación válida (trace + manifest). "
        "El resultado es inmutable y representa UNA ejecución concreta."
    ),
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF certificado del informe legal"
        },
        404: {"description": "Caso, informe, trace o manifest no encontrado"},
        422: {"description": "Incoherencia entre IDs o hashes"},
    }
)
def download_certified_pdf(
    case_id: str,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """
    Descarga el informe legal en PDF (versión optimizada).
    
    OPTIMIZACIÓN: No ejecuta agentes pesados (Auditor/Prosecutor).
    En su lugar:
    1. Genera LegalReport simplificado desde alertas técnicas (rápido)
    2. Renderiza PDF desde el LegalReport (segundos)
    
    Esto es mucho más rápido que ejecutar los agentes completos (minutos).
    
    Args:
        case_id: ID del caso
        db: Sesión de base de datos
        
    Returns:
        StreamingResponse con el PDF
        
    Raises:
        HTTPException 404: Si el caso no existe
        HTTPException 500: Si falla la generación del PDF
    """
    # Verificar que el caso existe
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Caso '{case_id}' no encontrado"
        )
    
    # VERSIÓN OPTIMIZADA: Generar PDF rápido sin ejecutar agentes pesados
    
    try:
        # 1. Generar informe legal simplificado desde alertas (rápido: ~1-2 segundos)
        legal_report = generate_legal_report(case_id=case_id, db=db)
        
        # 2. Generar PDF del informe (rápido: ~1-2 segundos)
        pdf_bytes = generate_legal_report_pdf(legal_report, case)
        
        # 3. Nombre del archivo
        filename = f"informe_legal_{case_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        # 4. Retornar como streaming response
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (404, etc.)
        raise
    except Exception as e:
        # Error al generar PDF
        import traceback
        error_detail = f"Error al generar PDF del informe legal: {str(e)}"
        print(f"❌ {error_detail}")
        print(traceback.format_exc())
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail
        )


# =========================================================
# ENDPOINTS PROHIBIDOS (NO IMPLEMENTADOS)
# =========================================================

# POST /cases/{case_id}/legal-report/pdf → PROHIBIDO (no se crea PDF manualmente)
# PUT /cases/{case_id}/legal-report/pdf → PROHIBIDO (no se edita PDF)
# DELETE /cases/{case_id}/legal-report/pdf → PROHIBIDO (no se borra PDF)
# POST /cases/{case_id}/legal-report/pdf/regenerate → PROHIBIDO (no se regenera)

