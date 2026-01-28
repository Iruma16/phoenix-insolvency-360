"""
API v2 - Endpoints de Prosecutor con Plantilla Formal de Acusación.

Esta versión incluye:
- Generación de plantilla formal de acusación legal
- Estructura obligatoria de 3 secciones
- Hashes SHA256 para trazabilidad forense
- Exportación a texto estructurado
- Validación estructural completa
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    get_current_user,
    require_permission,
    Permission,
    limiter
)
from app.core.telemetry import (
    track_analysis,
    api_requests_total,
    api_request_duration
)
from app.core.logger import get_logger
from app.core.exceptions import PhoenixException

from app.agents.agent_2_prosecutor.runner import run_prosecutor
from app.agents.agent_2_prosecutor.formal_generator import (
    generar_plantilla_formal,
    exportar_plantilla_a_texto,
)


logger = get_logger()
router = APIRouter(prefix="/v2/prosecutor", tags=["Prosecutor v2"])


# =========================================================
# MODELOS DE REQUEST/RESPONSE
# =========================================================

class ProsecutorAnalysisRequest(BaseModel):
    """Request para análisis prosecutor con generación de plantilla formal."""
    
    case_id: str = Field(
        ...,
        description="ID único del caso",
        min_length=3,
        max_length=100,
        example="CASE_RETAIL_001"
    )
    
    generate_formal_template: bool = Field(
        default=True,
        description="Si se debe generar la plantilla formal de acusación"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "case_id": "CASE_RETAIL_001",
                "generate_formal_template": True
            }
        }


class DocumentoAntecedente(BaseModel):
    """Documento con hash SHA256."""
    doc_id: str
    nombre_documento: str
    hash_sha256: str
    paginas_relevantes: List[int] = []
    descripcion: str


class FuenteVerificable(BaseModel):
    """Fuente documental verificable."""
    doc_id: str
    chunk_id: str
    pagina: Optional[int]
    extracto_literal: str
    ubicacion_exacta: str


class HechoProbado(BaseModel):
    """Hecho probado numerado."""
    numero: int
    descripcion_factica: str
    fuentes: List[FuenteVerificable]
    nivel_certeza: str


class BaseLegalTRLC(BaseModel):
    """Base legal TRLC."""
    articulo: str
    texto_articulo: str
    tipo_infraccion: str


class RiesgoDetectado(BaseModel):
    """Riesgo detectado con base legal."""
    numero: int
    titulo_riesgo: str
    descripcion_riesgo: str
    severidad: str
    base_legal: BaseLegalTRLC
    hechos_relacionados: List[int]
    consecuencias_juridicas: str
    nivel_confianza: float


class SeccionAntecedentes(BaseModel):
    """SECCIÓN I: ANTECEDENTES."""
    case_id: str
    documentos: List[DocumentoAntecedente]
    total_documentos: int
    total_paginas_analizadas: int
    observaciones_preliminares: Optional[str]


class SeccionHechosProbados(BaseModel):
    """SECCIÓN II: HECHOS PROBADOS."""
    hechos: List[HechoProbado]
    total_hechos: int
    resumen_cronologico: Optional[str]


class SeccionRiesgosDetectados(BaseModel):
    """SECCIÓN III: RIESGOS DETECTADOS."""
    riesgos: List[RiesgoDetectado]
    total_riesgos: int
    distribucion_severidad: Dict[str, int]
    calificacion_concursal_sugerida: str
    fundamento_calificacion: str


class PlantillaFormal(BaseModel):
    """Plantilla formal completa."""
    version_plantilla: str
    generado_por: str
    seccion_i_antecedentes: SeccionAntecedentes
    seccion_ii_hechos_probados: SeccionHechosProbados
    seccion_iii_riesgos_detectados: SeccionRiesgosDetectados
    certificacion_estructural: str


class ProsecutorAnalysisResponse(BaseModel):
    """Response de análisis prosecutor con plantilla formal."""
    
    case_id: str = Field(..., description="ID del caso")
    status: str = Field(..., description="Estado del análisis")
    
    total_acusaciones: int = Field(
        ...,
        description="Número total de acusaciones formuladas"
    )
    
    plantilla_formal: Optional[PlantillaFormal] = Field(
        None,
        description="Plantilla formal de acusación (si se generó)"
    )
    
    solicitud_evidencia: Optional[Dict[str, Any]] = Field(
        None,
        description="Solicitud de evidencia adicional (si no hay acusaciones)"
    )
    
    processing_time_seconds: float = Field(
        ...,
        description="Tiempo de procesamiento en segundos"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "case_id": "CASE_RETAIL_001",
                "status": "completed",
                "total_acusaciones": 2,
                "plantilla_formal": {
                    "version_plantilla": "1.0.0",
                    "seccion_i_antecedentes": {
                        "total_documentos": 5,
                        "total_paginas_analizadas": 23
                    },
                    "seccion_ii_hechos_probados": {
                        "total_hechos": 2
                    },
                    "seccion_iii_riesgos_detectados": {
                        "total_riesgos": 2,
                        "calificacion_concursal_sugerida": "CULPABLE_AGRAVADO"
                    }
                },
                "processing_time_seconds": 8.5
            }
        }


class ErrorResponse(BaseModel):
    """Response de error."""
    
    error_code: str = Field(..., description="Código de error único")
    message: str = Field(..., description="Mensaje descriptivo")
    details: Optional[Dict[str, Any]] = Field(
        None,
        description="Detalles adicionales"
    )


# =========================================================
# ENDPOINTS
# =========================================================

@router.post(
    "/analyze",
    response_model=ProsecutorAnalysisResponse,
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Análisis completado exitosamente",
            "model": ProsecutorAnalysisResponse
        },
        400: {
            "description": "Request inválido",
            "model": ErrorResponse
        },
        401: {
            "description": "No autenticado"
        },
        403: {
            "description": "Sin permisos suficientes"
        },
        404: {
            "description": "Caso no encontrado",
            "model": ErrorResponse
        },
        429: {
            "description": "Rate limit excedido"
        },
        500: {
            "description": "Error interno del servidor",
            "model": ErrorResponse
        }
    },
    summary="Ejecuta análisis prosecutor con plantilla formal",
    description="""
    Ejecuta análisis prosecutor y genera plantilla formal de acusación legal.
    
    ## Proceso
    
    1. **Análisis probatorio**: Detecta acusaciones con evidencia completa
    2. **Gates bloqueantes**: Valida 5 requisitos obligatorios
    3. **Generación de plantilla formal**:
       - **SECCIÓN I**: ANTECEDENTES (documentos + hashes SHA256)
       - **SECCIÓN II**: HECHOS PROBADOS (numerados con fuentes verificables)
       - **SECCIÓN III**: RIESGOS DETECTADOS (con base legal TRLC)
    
    ## Estructura obligatoria
    
    La plantilla formal cumple los siguientes requisitos:
    
    - ✅ Todos los documentos tienen hash SHA256 verificable
    - ✅ Todos los hechos tienen al menos una fuente documental
    - ✅ Todos los riesgos tienen base legal TRLC
    - ✅ Cross-references validadas (hechos ↔ riesgos)
    - ✅ Sin narrativa especulativa (prohibido: "parece", "podría", etc.)
    
    ## Tiempos esperados
    
    - **Con acusaciones**: 8-15 segundos
    - **Sin evidencia suficiente**: 3-5 segundos (retorna solicitud de evidencia)
    
    ## Permisos requeridos
    
    - `analysis:run`
    
    ## Rate limiting
    
    - 60 requests por minuto por usuario
    """,
    dependencies=[Depends(require_permission(Permission.ANALYSIS_RUN))]
)
@limiter.limit("60/minute")
async def analyze_prosecutor(
    request: Request,
    payload: ProsecutorAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Ejecuta análisis prosecutor con generación de plantilla formal.
    """
    import time
    start_time = time.time()
    
    logger.info(
        "Prosecutor analysis request received",
        case_id=payload.case_id,
        action="prosecutor_analysis_request",
        user_id=current_user.get("sub")
    )
    
    try:
        # Trackear métricas
        with track_analysis("prosecutor"):
            # Ejecutar análisis prosecutor
            prosecutor_result = run_prosecutor(case_id=payload.case_id)
        
        # Generar plantilla formal si hay acusaciones
        plantilla_formal = None
        if payload.generate_formal_template and prosecutor_result.acusaciones:
            try:
                plantilla_obj = generar_plantilla_formal(prosecutor_result)
                
                # Convertir a modelo de response
                plantilla_formal = PlantillaFormal(
                    version_plantilla=plantilla_obj.version_plantilla,
                    generado_por=plantilla_obj.generado_por,
                    seccion_i_antecedentes=SeccionAntecedentes(
                        case_id=plantilla_obj.seccion_i_antecedentes.case_id,
                        documentos=[
                            DocumentoAntecedente(
                                doc_id=doc.doc_id,
                                nombre_documento=doc.nombre_documento,
                                hash_sha256=doc.hash_sha256,
                                paginas_relevantes=doc.paginas_relevantes,
                                descripcion=doc.descripcion,
                            )
                            for doc in plantilla_obj.seccion_i_antecedentes.documentos
                        ],
                        total_documentos=plantilla_obj.seccion_i_antecedentes.total_documentos,
                        total_paginas_analizadas=plantilla_obj.seccion_i_antecedentes.total_paginas_analizadas,
                        observaciones_preliminares=plantilla_obj.seccion_i_antecedentes.observaciones_preliminares,
                    ),
                    seccion_ii_hechos_probados=SeccionHechosProbados(
                        hechos=[
                            HechoProbado(
                                numero=h.numero,
                                descripcion_factica=h.descripcion_factica,
                                fuentes=[
                                    FuenteVerificable(
                                        doc_id=f.doc_id,
                                        chunk_id=f.chunk_id,
                                        pagina=f.pagina,
                                        extracto_literal=f.extracto_literal,
                                        ubicacion_exacta=f.ubicacion_exacta,
                                    )
                                    for f in h.fuentes
                                ],
                                nivel_certeza=h.nivel_certeza,
                            )
                            for h in plantilla_obj.seccion_ii_hechos_probados.hechos
                        ],
                        total_hechos=plantilla_obj.seccion_ii_hechos_probados.total_hechos,
                        resumen_cronologico=plantilla_obj.seccion_ii_hechos_probados.resumen_cronologico,
                    ),
                    seccion_iii_riesgos_detectados=SeccionRiesgosDetectados(
                        riesgos=[
                            RiesgoDetectado(
                                numero=r.numero,
                                titulo_riesgo=r.titulo_riesgo,
                                descripcion_riesgo=r.descripcion_riesgo,
                                severidad=r.severidad,
                                base_legal=BaseLegalTRLC(
                                    articulo=r.base_legal.articulo,
                                    texto_articulo=r.base_legal.texto_articulo,
                                    tipo_infraccion=r.base_legal.tipo_infraccion,
                                ),
                                hechos_relacionados=r.hechos_relacionados,
                                consecuencias_juridicas=r.consecuencias_juridicas,
                                nivel_confianza=r.nivel_confianza,
                            )
                            for r in plantilla_obj.seccion_iii_riesgos_detectados.riesgos
                        ],
                        total_riesgos=plantilla_obj.seccion_iii_riesgos_detectados.total_riesgos,
                        distribucion_severidad=plantilla_obj.seccion_iii_riesgos_detectados.distribucion_severidad,
                        calificacion_concursal_sugerida=plantilla_obj.seccion_iii_riesgos_detectados.calificacion_concursal_sugerida,
                        fundamento_calificacion=plantilla_obj.seccion_iii_riesgos_detectados.fundamento_calificacion,
                    ),
                    certificacion_estructural=plantilla_obj.certificacion_estructural,
                )
                
                logger.info(
                    "Formal template generated successfully",
                    case_id=payload.case_id,
                    total_hechos=plantilla_obj.seccion_ii_hechos_probados.total_hechos,
                    total_riesgos=plantilla_obj.seccion_iii_riesgos_detectados.total_riesgos,
                    calificacion=plantilla_obj.seccion_iii_riesgos_detectados.calificacion_concursal_sugerida
                )
            
            except ValueError as e:
                # No se puede generar plantilla (sin acusaciones)
                logger.warning(
                    "Cannot generate formal template without accusations",
                    case_id=payload.case_id,
                    reason=str(e)
                )
        
        # Calcular tiempo de procesamiento
        processing_time = time.time() - start_time
        
        # Formatear response
        response = ProsecutorAnalysisResponse(
            case_id=payload.case_id,
            status="completed",
            total_acusaciones=prosecutor_result.total_acusaciones,
            plantilla_formal=plantilla_formal,
            solicitud_evidencia=(
                prosecutor_result.solicitud_evidencia.dict() 
                if prosecutor_result.solicitud_evidencia else None
            ),
            processing_time_seconds=processing_time
        )
        
        # Métricas
        api_requests_total.labels(
            method="POST",
            endpoint="/v2/prosecutor/analyze",
            status_code=200
        ).inc()
        
        api_request_duration.labels(
            method="POST",
            endpoint="/v2/prosecutor/analyze"
        ).observe(processing_time)
        
        logger.info(
            "Prosecutor analysis completed successfully",
            case_id=payload.case_id,
            action="prosecutor_analysis_success",
            processing_time=processing_time,
            total_acusaciones=prosecutor_result.total_acusaciones
        )
        
        return response
    
    except PhoenixException as e:
        # Excepción conocida del sistema
        logger.error(
            "Prosecutor analysis failed with Phoenix exception",
            case_id=payload.case_id,
            action="prosecutor_analysis_failed",
            error=e
        )
        
        # Mapear a código HTTP apropiado
        status_code = {
            "CASE_NOT_FOUND": status.HTTP_404_NOT_FOUND,
            "INSUFFICIENT_EVIDENCE": status.HTTP_400_BAD_REQUEST,
            "LEGAL_ANALYSIS_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
        }.get(e.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Métricas
        api_requests_total.labels(
            method="POST",
            endpoint="/v2/prosecutor/analyze",
            status_code=status_code
        ).inc()
        
        raise HTTPException(
            status_code=status_code,
            detail=e.to_dict()
        )
    
    except Exception as e:
        # Excepción inesperada
        logger.error(
            "Unexpected error in prosecutor analysis",
            case_id=payload.case_id,
            action="prosecutor_analysis_unexpected_error",
            error=e
        )
        
        # Métricas
        api_requests_total.labels(
            method="POST",
            endpoint="/v2/prosecutor/analyze",
            status_code=500
        ).inc()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "INTERNAL_ERROR",
                "message": "Error interno del servidor",
                "details": {"original_error": str(e)}
            }
        )


@router.post(
    "/analyze/export-text",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Exporta plantilla formal a texto estructurado",
    description="""
    Ejecuta análisis prosecutor y exporta la plantilla formal a formato de texto estructurado.
    
    Este formato es útil para:
    - Generación de PDFs
    - Inclusión en documentos Word
    - Revisión legal manual
    - Archivado
    """,
    dependencies=[Depends(require_permission(Permission.ANALYSIS_RUN))]
)
@limiter.limit("60/minute")
async def export_formal_template_text(
    request: Request,
    payload: ProsecutorAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Exporta plantilla formal a texto estructurado.
    """
    logger.info(
        "Formal template export request received",
        case_id=payload.case_id,
        action="template_export_request",
        user_id=current_user.get("sub")
    )
    
    try:
        # Ejecutar análisis prosecutor
        prosecutor_result = run_prosecutor(case_id=payload.case_id)
        
        # Generar plantilla formal
        if not prosecutor_result.acusaciones:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "NO_ACCUSATIONS",
                    "message": "No se puede generar plantilla sin acusaciones",
                    "details": {
                        "solicitud_evidencia": (
                            prosecutor_result.solicitud_evidencia.dict()
                            if prosecutor_result.solicitud_evidencia else None
                        )
                    }
                }
            )
        
        plantilla_obj = generar_plantilla_formal(prosecutor_result)
        
        # Exportar a texto
        texto = exportar_plantilla_a_texto(plantilla_obj)
        
        logger.info(
            "Formal template exported successfully",
            case_id=payload.case_id,
            action="template_export_success",
            length=len(texto)
        )
        
        return PlainTextResponse(
            content=texto,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename=acusacion_formal_{payload.case_id}.txt"
            }
        )
    
    except HTTPException:
        raise
    
    except Exception as e:
        logger.error(
            "Unexpected error in template export",
            case_id=payload.case_id,
            action="template_export_error",
            error=e
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "EXPORT_ERROR",
                "message": "Error al exportar plantilla",
                "details": {"original_error": str(e)}
            }
        )


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Health check del servicio prosecutor",
    description="Verifica el estado del servicio prosecutor y sus dependencias."
)
async def health_check():
    """Health check endpoint."""
    from app.core.database import check_database_health
    from app.core.telemetry import get_system_stats
    
    db_health = check_database_health()
    system_stats = get_system_stats()
    
    return {
        "status": "healthy" if db_health["status"] == "healthy" else "degraded",
        "service": "prosecutor",
        "version": "2.0",
        "formal_template_version": "1.0.0",
        "database": db_health,
        "system_stats": system_stats
    }

