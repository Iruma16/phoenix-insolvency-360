"""
ENDPOINT OFICIAL DE VISUALIZACIÓN DE TRACE (PANTALLA 5).

PRINCIPIO: Esta capa NO genera, NO edita, NO analiza.
SOLO MUESTRA el trace autoritativo de la ejecución.

PROHIBIDO:
- editar trace
- borrar ejecuciones
- regenerar trace
- modificar decisiones
- ocultar errores o decisiones
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.case import Case
from app.trace.models import ExecutionTrace

router = APIRouter(
    prefix="/cases/{case_id}",
    tags=["trace"],
)


@router.get(
    "/trace",
    response_model=ExecutionTrace,
    summary="Obtener trace autoritativo de la ejecución",
    description=(
        "Devuelve el trace completo e inmutable de la última ejecución del caso. "
        "El trace es la única fuente de verdad sobre qué ocurrió. "
        "SOLO LECTURA - no permite modificación."
    ),
)
def get_execution_trace(
    case_id: str,
    db: Session = Depends(get_db),
) -> ExecutionTrace:
    """
    Obtiene el trace autoritativo de la última ejecución del caso.

    El trace es INMUTABLE y representa la única fuente de verdad.
    Incluye:
    - trace_id (determinista)
    - execution_timestamp y completed_at
    - decisions (ordenadas temporalmente)
    - errors (si existen)
    - chunk_ids, document_ids
    - legal_report_hash (si existe)
    - execution_mode, system_version

    Args:
        case_id: ID del caso
        db: Sesión de base de datos

    Returns:
        ExecutionTrace completo

    Raises:
        HTTPException 404: Si el caso no existe
        HTTPException 404: Si no existe trace para el caso
        HTTPException 409: Si el trace no está completado
    """
    # Verificar que el caso existe
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado"
        )

    # TODO: En una implementación real, aquí se consultaría la BD
    # para obtener el último ExecutionTrace del caso.
    # Por ahora, devolvemos un error indicando que no hay trace.

    # NOTA: La persistencia del trace en BD no está implementada en FASE 6.
    # FASE 6 solo define los modelos Pydantic.
    # Aquí necesitaríamos:
    # 1. Un modelo SQLAlchemy para ExecutionTrace
    # 2. Persistir el trace al generar el informe legal
    # 3. Consultar el último trace del caso

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"No se encontró trace de ejecución para el caso '{case_id}'. "
            "El trace se genera al crear el informe legal."
        ),
    )


# =========================================================
# ENDPOINTS PROHIBIDOS (NO IMPLEMENTADOS)
# =========================================================

# POST /cases/{case_id}/trace → PROHIBIDO (no se crea trace manualmente)
# PUT /cases/{case_id}/trace → PROHIBIDO (no se edita trace)
# DELETE /cases/{case_id}/trace → PROHIBIDO (no se borra trace)
# POST /cases/{case_id}/trace/regenerate → PROHIBIDO (no se regenera trace)
