"""
ENDPOINT OFICIAL DE GESTIÓN DE CASOS (PANTALLA 0).

PRINCIPIO: Esta capa NO contiene lógica de negocio.
Solo expone el estado real del core para la UI.

PROHIBIDO:
- editar casos existentes
- borrar casos
- sobrescribir outputs
- modificar estados
- inferir datos no existentes
"""
from __future__ import annotations

from typing import List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.models.case import Case
from app.models.document import Document
from app.models.fact import Fact
from app.models.risk import Risk
from app.models.case_summary import (
    CaseSummary,
    CreateCaseRequest,
    AnalysisStatus,
)


router = APIRouter(
    prefix="/cases",
    tags=["cases"],
)


def _calculate_analysis_status(
    case_id: str,
    documents_count: int,
    facts_count: int,
    risks_count: int,
    db: Session,
) -> AnalysisStatus:
    """
    Calcula el estado de análisis de un caso.
    
    REGLAS:
    - NOT_STARTED: sin documentos
    - IN_PROGRESS: con documentos, sin facts/risks generados
    - COMPLETED: con documentos y facts/risks generados
    - FAILED: por ahora no se detecta (requeriría tabla de ejecuciones)
    
    Args:
        case_id: ID del caso
        documents_count: Número de documentos
        facts_count: Número de facts generados
        risks_count: Número de riesgos generados
        db: Sesión de base de datos
        
    Returns:
        AnalysisStatus calculado
    """
    # Sin documentos → NOT_STARTED
    if documents_count == 0:
        return AnalysisStatus.NOT_STARTED
    
    # Con documentos pero sin análisis → IN_PROGRESS
    if facts_count == 0 and risks_count == 0:
        return AnalysisStatus.IN_PROGRESS
    
    # Con documentos y análisis → COMPLETED
    return AnalysisStatus.COMPLETED


def _build_case_summary(case: Case, db: Session) -> CaseSummary:
    """
    Construye un CaseSummary desde un Case del core.
    
    NO inventa datos.
    NO asume estados.
    SOLO lee el estado real.
    
    Args:
        case: Caso del core
        db: Sesión de base de datos
        
    Returns:
        CaseSummary con estado calculado desde el core
    """
    # Contar documentos
    documents_count = (
        db.query(Document)
        .filter(Document.case_id == case.case_id)
        .count()
    )
    
    # Contar facts generados
    facts_count = (
        db.query(Fact)
        .filter(Fact.case_id == case.case_id)
        .count()
    )
    
    # Contar riesgos generados
    risks_count = (
        db.query(Risk)
        .filter(Risk.case_id == case.case_id)
        .count()
    )
    
    # Calcular estado de análisis
    analysis_status = _calculate_analysis_status(
        case_id=case.case_id,
        documents_count=documents_count,
        facts_count=facts_count,
        risks_count=risks_count,
        db=db,
    )
    
    # Obtener timestamp de última creación de documento
    # (proxy de "última ejecución")
    last_doc_update = (
        db.query(func.max(Document.created_at))
        .filter(Document.case_id == case.case_id)
        .scalar()
    )
    
    return CaseSummary(
        case_id=case.case_id,
        name=case.name,
        created_at=case.created_at,
        documents_count=documents_count,
        last_execution_at=last_doc_update,
        analysis_status=analysis_status,
        client_ref=case.client_ref,
    )


@router.post(
    "",
    response_model=CaseSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Crear nuevo caso",
    description=(
        "Crea un nuevo caso en el sistema. "
        "El case_id se genera automáticamente por el core. "
        "NO permite parámetros arbitrarios."
    ),
)
def create_case(
    request: CreateCaseRequest,
    db: Session = Depends(get_db),
) -> CaseSummary:
    """
    Crea un nuevo caso.
    
    El case_id se genera automáticamente (UUID v4).
    El caso inicia en estado NOT_STARTED.
    
    Args:
        request: Datos del caso a crear
        db: Sesión de base de datos
        
    Returns:
        CaseSummary del caso creado
    """
    # Crear caso en el core
    new_case = Case(
        name=request.name,
        client_ref=request.client_ref,
        status="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    
    db.add(new_case)
    db.commit()
    db.refresh(new_case)
    
    # Construir summary
    return _build_case_summary(new_case, db)


@router.get(
    "",
    response_model=List[CaseSummary],
    summary="Listar todos los casos",
    description=(
        "Lista todos los casos existentes en el sistema, "
        "ordenados por fecha de creación (más recientes primero). "
        "Cada caso incluye su estado de análisis calculado desde el core."
    ),
)
def list_cases(
    db: Session = Depends(get_db),
) -> List[CaseSummary]:
    """
    Lista todos los casos existentes.
    
    Ordenados por created_at descendente (más recientes primero).
    El estado de cada caso se calcula desde el core real.
    
    Args:
        db: Sesión de base de datos
        
    Returns:
        Lista de CaseSummary
    """
    # Obtener todos los casos ordenados
    cases = (
        db.query(Case)
        .filter(Case.status == "active")
        .order_by(Case.created_at.desc())
        .all()
    )
    
    # Construir summaries
    return [_build_case_summary(case, db) for case in cases]


@router.get(
    "/{case_id}",
    response_model=CaseSummary,
    summary="Consultar un caso",
    description=(
        "Obtiene el resumen de un caso específico. "
        "El estado de análisis se calcula desde el core real. "
        "Falla con 404 si el caso no existe."
    ),
)
def get_case(
    case_id: str,
    db: Session = Depends(get_db),
) -> CaseSummary:
    """
    Obtiene el resumen de un caso.
    
    Args:
        case_id: ID del caso a consultar
        db: Sesión de base de datos
        
    Returns:
        CaseSummary del caso
        
    Raises:
        HTTPException 404: Si el caso no existe
    """
    # Buscar caso
    case = (
        db.query(Case)
        .filter(Case.case_id == case_id)
        .first()
    )
    
    # Si no existe → 404
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Caso '{case_id}' no encontrado"
        )
    
    # Construir summary
    return _build_case_summary(case, db)


# =========================================================
# ENDPOINTS PROHIBIDOS (NO IMPLEMENTADOS)
# =========================================================

# PUT /cases/{case_id} → PROHIBIDO (no se permite editar casos)
# DELETE /cases/{case_id} → PROHIBIDO (no se permite borrar casos)
# PATCH /cases/{case_id} → PROHIBIDO (no se permite modificar estados)

