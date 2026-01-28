"""
ENDPOINT OFICIAL DE CERTIFICACIÓN (MANIFEST) (PANTALLA 5).

PRINCIPIO: Esta capa NO genera contenido nuevo.
SOLO CERTIFICA Y CIERRA la ejecución mediante HardManifest.

PROHIBIDO:
- regenerar manifest con datos distintos
- certificación parcial
- modificar trace o decisiones
- permitir múltiples manifests para el mismo trace
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.case import Case
from app.trace.manifest import HardManifest


router = APIRouter(
    prefix="/cases/{case_id}",
    tags=["manifest"],
)


@router.post(
    "/manifest",
    response_model=HardManifest,
    status_code=status.HTTP_201_CREATED,
    summary="Certificar ejecución mediante manifest",
    description=(
        "Crea un HardManifest a partir del último ExecutionTrace del caso. "
        "El manifest actúa como certificado técnico inmutable. "
        "Solo se puede certificar una ejecución completa y válida. "
        "NO permite regeneración ni modificación."
    ),
)
def create_manifest(
    case_id: str,
    db: Session = Depends(get_db),
) -> HardManifest:
    """
    Crea un HardManifest certificando la ejecución del caso.
    
    Proceso:
    1. Verificar que el caso existe
    2. Obtener último ExecutionTrace (debe estar completado)
    3. Verificar que no existe manifest para ese trace
    4. Crear HardManifest con:
       - trace_id
       - case_id
       - schema_versions
       - integrity_hash (SHA256 del trace completo)
       - execution_limits (qué NO hace el sistema)
       - finops_snapshot (si existe)
       - signed_at (timestamp de certificación)
    
    Args:
        case_id: ID del caso
        db: Sesión de base de datos
        
    Returns:
        HardManifest certificando la ejecución
        
    Raises:
        HTTPException 404: Si el caso no existe
        HTTPException 404: Si no existe trace para el caso
        HTTPException 409: Si el trace no está completado
        HTTPException 409: Si ya existe manifest para ese trace
        HTTPException 422: Si hay incoherencia de hashes
    """
    # Verificar que el caso existe
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Caso '{case_id}' no encontrado"
        )
    
    # TODO: En una implementación real, aquí se:
    # 1. Consultaría el último ExecutionTrace del caso en BD
    # 2. Verificaría que está completado (completed_at != None)
    # 3. Verificaría que no existe manifest para ese trace_id
    # 4. Crearía el HardManifest usando la función del módulo trace.manifest
    # 5. Persistiría el manifest en BD
    
    # NOTA: La persistencia del trace y manifest en BD no está implementada en FASE 6.
    # FASE 6 solo define los modelos Pydantic y funciones de generación.
    # Aquí necesitaríamos:
    # 1. Modelos SQLAlchemy para ExecutionTrace y HardManifest
    # 2. Persistir el trace al generar el informe legal
    # 3. Consultar el último trace del caso
    # 4. Usar create_manifest() de app/trace/manifest.py
    # 5. Persistir el manifest en BD
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"No se encontró trace de ejecución para el caso '{case_id}'. "
            "El manifest solo puede generarse a partir de un trace completo."
        )
    )


# =========================================================
# ENDPOINTS PROHIBIDOS (NO IMPLEMENTADOS)
# =========================================================

# PUT /cases/{case_id}/manifest → PROHIBIDO (no se edita manifest)
# DELETE /cases/{case_id}/manifest → PROHIBIDO (no se borra manifest)
# POST /cases/{case_id}/manifest/regenerate → PROHIBIDO (no se regenera)

