"""
ENDPOINT OFICIAL DE DESCARGA DE PDF CERTIFICADO (PANTALLA 6).

PRINCIPIO: Esta capa NO genera contenido nuevo, NO analiza, NO certifica.
SOLO EMPAQUETA Y ENTREGA el resultado certificado.

PROHIBIDO:
- generar PDF sin trace existente
- generar PDF sin manifest existente
- regenerar PDF con datos distintos
- permitir múltiples PDFs para el mismo trace
- editar el contenido del informe
- ocultar hashes, IDs o avisos legales
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.case import Case
from app.services.pdf_builder import build_certified_pdf


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
    Descarga el informe legal en PDF certificado.
    
    Proceso:
    1. Verificar que el caso existe
    2. Recuperar LegalReport del caso
    3. Recuperar ExecutionTrace del caso
    4. Recuperar HardManifest del trace
    5. Verificar coherencia de IDs y hashes
    6. Generar PDF inmutable
    7. Retornar como StreamingResponse
    
    El nombre del archivo incluye:
    - case_id
    - trace_id
    - manifest_id (primeros 8 chars)
    
    Args:
        case_id: ID del caso
        db: Sesión de base de datos
        
    Returns:
        StreamingResponse con el PDF
        
    Raises:
        HTTPException 404: Si el caso no existe
        HTTPException 404: Si no existe informe legal
        HTTPException 404: Si no existe trace
        HTTPException 404: Si no existe manifest
        HTTPException 422: Si hay incoherencia entre IDs/hashes
    """
    # Verificar que el caso existe
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Caso '{case_id}' no encontrado"
        )
    
    # TODO: En una implementación real, aquí se:
    # 1. Consultaría el LegalReport del caso en BD
    # 2. Consultaría el último ExecutionTrace del caso en BD
    # 3. Consultaría el HardManifest asociado al trace en BD
    # 4. Verificaría coherencia de IDs y hashes
    # 5. Llamaría a build_certified_pdf() del servicio
    # 6. Retornaría el PDF como StreamingResponse
    
    # NOTA: La persistencia de LegalReport, ExecutionTrace y HardManifest en BD
    # no está implementada en las fases previas.
    # Los modelos Pydantic existen (PANTALLA 4, FASE 6) pero no hay:
    # 1. Modelos SQLAlchemy para persistencia
    # 2. Lógica de guardado al generar el informe legal
    # 3. Consultas para recuperar estos objetos
    
    # PARA COMPLETAR LA FUNCIONALIDAD SE REQUIERE:
    # 1. Crear modelos SQLAlchemy para LegalReport, ExecutionTrace, HardManifest
    # 2. Persistir estos objetos en app/api/legal_report.py, trace.py, manifest.py
    # 3. Implementar consultas aquí
    # 4. Usar build_certified_pdf() para generar el PDF
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"No se encontró informe legal certificado para el caso '{case_id}'. "
            "El PDF solo puede generarse a partir de un informe con trace y manifest completos."
        )
    )


# =========================================================
# ENDPOINTS PROHIBIDOS (NO IMPLEMENTADOS)
# =========================================================

# POST /cases/{case_id}/legal-report/pdf → PROHIBIDO (no se crea PDF manualmente)
# PUT /cases/{case_id}/legal-report/pdf → PROHIBIDO (no se edita PDF)
# DELETE /cases/{case_id}/legal-report/pdf → PROHIBIDO (no se borra PDF)
# POST /cases/{case_id}/legal-report/pdf/regenerate → PROHIBIDO (no se regenera)

