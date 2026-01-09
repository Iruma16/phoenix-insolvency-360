"""
API Endpoints para Balance de Situación Concursal.

FASE 1.3: Balance de Situación Automático
"""
from typing import List, Optional
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.models.balance_concursal_output import BalanceConcursalOutput
from app.models.financial_statement import BalanceSheet, IncomeStatement
from app.models.credit import Credit
from app.models.balance_situacion import BalanceSituacion
from app.services.balance_concursal_service import BalanceConcursalService
from app.services.balance_persistence import BalancePersistenceService


router = APIRouter(prefix="/cases/{case_id}/balance-concursal", tags=["Balance Concursal"])


class BalanceConcursalRequest(BaseModel):
    """Request para análisis de balance concursal."""
    balance: BalanceSheet
    creditos: List[Credit]
    pyg: Optional[IncomeStatement] = None
    impagos_exigibles: Optional[List[dict]] = None
    concurso_date: Optional[date] = None


@router.post(
    "",
    response_model=BalanceConcursalOutput,
    status_code=status.HTTP_201_CREATED,
    summary="Analizar Balance de Situación Concursal",
    description=(
        "Analiza un balance de situación según TRLC. "
        "Incluye: clasificación de créditos, ratios financieros, "
        "detección de insolvencia y dictamen jurídico preliminar."
    ),
)
def analyze_balance_concursal(
    case_id: str,
    request: BalanceConcursalRequest,
    db: Session = Depends(get_db),
) -> BalanceConcursalOutput:
    """
    Analiza un balance de situación concursal completo.
    
    Flujo:
    1. Clasifica créditos según TRLC
    2. Calcula ratios financieros
    3. Detecta insolvencia (actual/inminente)
    4. Genera dictamen jurídico
    """
    service = BalanceConcursalService(concurso_date=request.concurso_date)
    persistence = BalancePersistenceService()
    
    try:
        # 1. Analizar
        output = service.analyze_balance_concursal(
            case_id=case_id,
            balance=request.balance,
            creditos=request.creditos,
            pyg=request.pyg,
            impagos_exigibles=request.impagos_exigibles,
        )
        
        # 2. Persistir en BD
        balance_db = persistence.persist_balance(
            db=db,
            output=output,
            created_by="api_user"  # TODO: Obtener usuario real del token JWT
        )
        
        return output
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al analizar balance concursal: {str(e)}"
        )


class BalanceSummary(BaseModel):
    """Resumen de balance para listado."""
    balance_id: str
    case_id: str
    version: int
    fecha_analisis: datetime
    ruleset_version: str
    insolvencia_actual: bool
    insolvencia_inminente: bool
    is_active: bool


@router.get(
    "",
    response_model=BalanceSummary,
    summary="Obtener balance activo",
    description="Obtiene el balance de situación activo de un caso.",
)
def get_active_balance(
    case_id: str,
    db: Session = Depends(get_db),
) -> BalanceSummary:
    """Obtiene el balance activo de un caso."""
    persistence = BalancePersistenceService()
    balance = persistence.get_active_balance(db, case_id)
    
    if not balance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró balance activo para caso {case_id}"
        )
    
    return BalanceSummary(
        balance_id=balance.balance_id,
        case_id=balance.case_id,
        version=balance.version,
        fecha_analisis=balance.fecha_analisis,
        ruleset_version=balance.ruleset_version,
        insolvencia_actual=balance.insolvencia_actual,
        insolvencia_inminente=balance.insolvencia_inminente,
        is_active=balance.is_active,
    )


@router.get(
    "/history",
    response_model=List[BalanceSummary],
    summary="Obtener histórico de balances",
    description="Obtiene el histórico completo de balances de un caso.",
)
def get_balance_history(
    case_id: str,
    db: Session = Depends(get_db),
) -> List[BalanceSummary]:
    """Obtiene el histórico de balances de un caso."""
    persistence = BalancePersistenceService()
    balances = persistence.get_balance_history(db, case_id)
    
    return [
        BalanceSummary(
            balance_id=b.balance_id,
            case_id=b.case_id,
            version=b.version,
            fecha_analisis=b.fecha_analisis,
            ruleset_version=b.ruleset_version,
            insolvencia_actual=b.insolvencia_actual,
            insolvencia_inminente=b.insolvencia_inminente,
            is_active=b.is_active,
        )
        for b in balances
    ]
