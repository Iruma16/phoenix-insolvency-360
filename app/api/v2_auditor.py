"""
API v2 - Endpoints de auditoría mejorados.

Esta versión incluye:
- Capa de servicios
- Rate limiting
- Autenticación JWT
- Métricas
- Manejo de errores mejorado
- Documentación completa
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import PhoenixException
from app.core.logger import get_logger
from app.core.security import Permission, get_current_user, limiter, require_permission
from app.core.telemetry import api_request_duration, api_requests_total, track_analysis
from app.services.audit_service import AuditService

logger = get_logger()
router = APIRouter(prefix="/v2/auditor", tags=["Auditor v2"])


# =========================================================
# MODELOS DE REQUEST/RESPONSE
# =========================================================


class AnalysisRequest(BaseModel):
    """Request para análisis de auditoría."""

    case_id: str = Field(
        ...,
        description="ID único del caso",
        min_length=3,
        max_length=100,
        example="CASE_RETAIL_001",
    )

    question: Optional[str] = Field(
        None,
        description="Pregunta específica para el análisis",
        max_length=500,
        example="¿Existe riesgo de retraso en solicitud de concurso?",
    )

    class Config:
        schema_extra = {
            "example": {
                "case_id": "CASE_RETAIL_001",
                "question": "¿Existe riesgo de retraso en solicitud de concurso?",
            }
        }


class FindingResponse(BaseModel):
    """Hallazgo individual."""

    risk_type: str = Field(..., description="Tipo de riesgo")
    severity: str = Field(..., description="Severidad (low, medium, high)")
    confidence: str = Field(..., description="Confianza (low, medium, high)")
    description: str = Field(..., description="Descripción del hallazgo")
    recommendation: str = Field(..., description="Recomendación")
    evidence: list[str] = Field(default=[], description="Evidencias")


class AnalysisResponse(BaseModel):
    """Response exitoso de análisis."""

    case_id: str = Field(..., description="ID del caso")
    status: str = Field(..., description="Estado del análisis")

    summary: Optional[str] = Field(None, description="Resumen ejecutivo del análisis")

    findings: list[FindingResponse] = Field(default=[], description="Lista de hallazgos")

    quality_score: int = Field(
        ..., description="Score de calidad del análisis (0-100)", ge=0, le=100
    )

    llm_used: bool = Field(..., description="Si se usó LLM en el análisis")

    processing_time_seconds: float = Field(..., description="Tiempo de procesamiento en segundos")

    class Config:
        schema_extra = {
            "example": {
                "case_id": "CASE_RETAIL_001",
                "status": "completed",
                "summary": "Se detectaron 2 riesgos de severidad alta...",
                "findings": [
                    {
                        "risk_type": "delay_filing",
                        "severity": "high",
                        "confidence": "high",
                        "description": "Posible retraso en solicitud de concurso",
                        "recommendation": "Verificar fechas de insolvencia",
                        "evidence": ["balance_2023.pdf", "acta_junta_2023.pdf"],
                    }
                ],
                "quality_score": 85,
                "llm_used": True,
                "processing_time_seconds": 12.5,
            }
        }


class ErrorResponse(BaseModel):
    """Response de error."""

    error_code: str = Field(..., description="Código de error único")
    message: str = Field(..., description="Mensaje descriptivo")
    details: Optional[dict[str, Any]] = Field(None, description="Detalles adicionales")


# =========================================================
# ENDPOINTS
# =========================================================


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {"description": "Análisis completado exitosamente", "model": AnalysisResponse},
        400: {"description": "Request inválido", "model": ErrorResponse},
        401: {"description": "No autenticado"},
        403: {"description": "Sin permisos suficientes"},
        404: {"description": "Caso no encontrado", "model": ErrorResponse},
        429: {"description": "Rate limit excedido"},
        500: {"description": "Error interno del servidor", "model": ErrorResponse},
    },
    summary="Ejecuta análisis de auditoría",
    description="""
    Ejecuta un análisis completo de auditoría sobre un caso.
    
    ## Proceso
    
    1. **Validación**: Verifica que el caso existe y tiene documentación
    2. **Análisis heurístico**: Detecta riesgos usando reglas deterministas
    3. **Análisis LLM** (opcional): Enriquece con razonamiento contextualizado
    4. **Rule Engine**: Aplica reglas legales del TRLC
    5. **Scoring**: Calcula score de calidad del análisis
    
    ## Tiempos esperados
    
    - **Con LLM**: 10-30 segundos
    - **Sin LLM** (modo degradado): 2-5 segundos
    
    ## Permisos requeridos
    
    - `analysis:run`
    
    ## Rate limiting
    
    - 60 requests por minuto por usuario
    """,
    dependencies=[Depends(require_permission(Permission.ANALYSIS_RUN))],
)
@limiter.limit("60/minute")
async def analyze_case(
    request: Request,
    payload: AnalysisRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """
    Ejecuta análisis de auditoría.

    Este endpoint es la versión mejorada con:
    - Capa de servicios
    - Métricas automáticas
    - Logging estructurado
    - Manejo de errores robusto
    """
    import time

    start_time = time.time()

    logger.info(
        "Analysis request received",
        case_id=payload.case_id,
        action="analysis_request",
        user_id=current_user.get("sub"),
    )

    try:
        # Trackear métricas
        with track_analysis("complete"):
            # Usar servicio para lógica de negocio
            service = AuditService(db=db)
            result = service.analyze_case(case_id=payload.case_id, question=payload.question)

        # Calcular tiempo de procesamiento
        processing_time = time.time() - start_time

        # Formatear response
        response = AnalysisResponse(
            case_id=payload.case_id,
            status="completed",
            summary=result.get("summary"),
            findings=[FindingResponse(**f) for f in result.get("findings", [])],
            quality_score=result.get("quality_score", 0),
            llm_used=result.get("llm_insights", {}).get("used", False),
            processing_time_seconds=processing_time,
        )

        # Métricas
        api_requests_total.labels(
            method="POST", endpoint="/v2/auditor/analyze", status_code=200
        ).inc()

        api_request_duration.labels(method="POST", endpoint="/v2/auditor/analyze").observe(
            processing_time
        )

        logger.info(
            "Analysis completed successfully",
            case_id=payload.case_id,
            action="analysis_success",
            processing_time=processing_time,
            findings_count=len(response.findings),
        )

        return response

    except PhoenixException as e:
        # Excepción conocida del sistema
        logger.error(
            "Analysis failed with Phoenix exception",
            case_id=payload.case_id,
            action="analysis_failed",
            error=e,
        )

        # Mapear a código HTTP apropiado
        status_code = {
            "CASE_NOT_FOUND": status.HTTP_404_NOT_FOUND,
            "INSUFFICIENT_EVIDENCE": status.HTTP_400_BAD_REQUEST,
            "LEGAL_ANALYSIS_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
        }.get(e.code, status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Métricas
        api_requests_total.labels(
            method="POST", endpoint="/v2/auditor/analyze", status_code=status_code
        ).inc()

        raise HTTPException(status_code=status_code, detail=e.to_dict())

    except Exception as e:
        # Excepción inesperada
        logger.error(
            "Unexpected error in analysis",
            case_id=payload.case_id,
            action="analysis_unexpected_error",
            error=e,
        )

        # Métricas
        api_requests_total.labels(
            method="POST", endpoint="/v2/auditor/analyze", status_code=500
        ).inc()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "INTERNAL_ERROR",
                "message": "Error interno del servidor",
                "details": {"original_error": str(e)},
            },
        )


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check del servicio de auditoría",
    description="Verifica el estado del servicio de auditoría y sus dependencias.",
)
async def health_check():
    """Health check endpoint."""
    from app.core.database import check_database_health
    from app.core.llm_config import is_llm_enabled
    from app.core.telemetry import get_system_stats

    db_health = check_database_health()
    system_stats = get_system_stats()

    return {
        "status": "healthy" if db_health["status"] == "healthy" else "degraded",
        "service": "auditor",
        "version": "2.0",
        "llm_available": is_llm_enabled(),
        "database": db_health,
        "system_stats": system_stats,
    }
