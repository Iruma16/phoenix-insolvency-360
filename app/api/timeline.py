"""
ENDPOINT DE TIMELINE PAGINADO (OPTIMIZADO) - BACKEND ESCALABLE.

Permite obtener eventos del timeline con:
- Paginación real en BD (LIMIT + OFFSET)
- Filtros en SQL (tipo, severidad, fechas, búsqueda)
- Ordenamiento configurable
- Índices optimizados

PRINCIPIOS:
- Query eficiente incluso con 10K+ eventos
- Solo carga lo que se va a mostrar
- Filtros compilados en SQL, no en memoria
- Estadísticas agregadas sin cargar eventos

SEGURIDAD:
- Autenticación requerida (X-User-ID header)
- Validación de parámetros de paginación
- Logging completo para debugging
"""
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.auth import User, get_current_user
from app.core.database import get_db
from app.models.case import Case
from app.models.timeline_event import TimelineEvent
from app.services.financial_analysis import PaginatedTimelineResponse, TimelineEventResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cases/{case_id}/timeline",
    tags=["timeline"],
)


@router.get(
    "",
    response_model=PaginatedTimelineResponse,
    summary="Timeline paginado con filtros en backend",
    description=(
        "Obtiene timeline de eventos con paginación y filtros aplicados en backend. "
        "Optimizado con índices de BD para alto rendimiento incluso con miles de eventos. "
        "\n\n**Filtros disponibles:**\n"
        "- `event_type`: Tipo de evento\n"
        "- `category`: Categoría del evento\n"
        "- `severity`: Nivel de severidad\n"
        "- `start_date`, `end_date`: Rango de fechas\n"
        "- `search`: Búsqueda en descripción (mín 3 chars)\n"
        "\n\n**Ordenamiento:**\n"
        "- `sort_by`: Campo (date/amount/severity)\n"
        "- `sort_order`: Orden (asc/desc)\n"
        "\n\n**Requiere autenticación**: Header X-User-ID"
    ),
    responses={
        200: {"description": "Timeline paginado obtenido exitosamente"},
        401: {"description": "No autenticado"},
        404: {"description": "Caso no encontrado"},
        422: {"description": "Parámetros de paginación inválidos"},
    },
)
async def get_timeline_paginated(
    case_id: str,
    page: int = Query(1, ge=1, description="Número de página (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Eventos por página (máx 100)"),
    # Filtros opcionales
    event_type: Optional[str] = Query(None, description="Filtrar por tipo de evento"),
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    severity: Optional[str] = Query(None, description="Filtrar por severidad"),
    start_date: Optional[date] = Query(None, description="Fecha inicio (inclusive)"),
    end_date: Optional[date] = Query(None, description="Fecha fin (inclusive)"),
    search: Optional[str] = Query(
        None, min_length=3, description="Búsqueda en descripción (mín 3 chars)"
    ),
    # Ordenamiento
    sort_by: str = Query(
        "date", regex="^(date|amount|severity)$", description="Campo para ordenar"
    ),
    sort_order: str = Query(
        "desc", regex="^(asc|desc)$", description="Orden ascendente o descendente"
    ),
    # Estadísticas opcionales
    include_stats: bool = Query(False, description="Incluir estadísticas agregadas"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaginatedTimelineResponse:
    """
    Obtiene timeline paginado con filtros aplicados en backend.

    OPTIMIZACIONES:
    - ✅ Query con índices compuestos (case_id + date)
    - ✅ Paginación real en BD (LIMIT + OFFSET)
    - ✅ Filtros compilados en SQL
    - ✅ Count() optimizado
    - ✅ Sin cargar eventos innecesarios

    Args:
        case_id: ID del caso
        page: Número de página (1-based)
        page_size: Eventos por página (1-100)
        event_type: Filtro opcional por tipo
        category: Filtro opcional por categoría
        severity: Filtro opcional por severidad
        start_date: Filtro opcional fecha inicio
        end_date: Filtro opcional fecha fin
        search: Búsqueda opcional en descripción
        sort_by: Campo para ordenar (date/amount/severity)
        sort_order: Orden (asc/desc)
        include_stats: Incluir estadísticas agregadas
        db: Sesión de BD
        current_user: Usuario autenticado

    Returns:
        PaginatedTimelineResponse con eventos de la página solicitada

    Raises:
        HTTPException 401: No autenticado
        HTTPException 404: Caso no encontrado
        HTTPException 422: Parámetros inválidos
    """
    logger.info(
        f"📅 Timeline paginated request for case {case_id} by user {current_user.id} "
        f"(page={page}, size={page_size})"
    )

    # ═══════════════════════════════════════════════════════
    # 1. VERIFICAR QUE EL CASO EXISTE
    # ═══════════════════════════════════════════════════════
    case = db.query(Case).filter(Case.case_id == case_id).first()

    if not case:
        logger.warning(f"Case {case_id} not found for timeline request")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Caso '{case_id}' no encontrado"
        )

    # ═══════════════════════════════════════════════════════
    # 2. CONSTRUIR QUERY BASE CON FILTROS
    # ═══════════════════════════════════════════════════════
    query = db.query(TimelineEvent).filter(TimelineEvent.case_id == case_id)

    # Tracking de filtros aplicados (para UI)
    filters_applied = {}

    # Filtro por tipo de evento
    if event_type:
        query = query.filter(TimelineEvent.event_type == event_type)
        filters_applied["event_type"] = event_type
        logger.debug(f"Applied filter: event_type={event_type}")

    # Filtro por categoría
    if category:
        query = query.filter(TimelineEvent.category == category)
        filters_applied["category"] = category
        logger.debug(f"Applied filter: category={category}")

    # Filtro por severidad
    if severity:
        query = query.filter(TimelineEvent.severity == severity)
        filters_applied["severity"] = severity
        logger.debug(f"Applied filter: severity={severity}")

    # Filtro por rango de fechas
    if start_date:
        # Convertir date a datetime (inicio del día)
        start_dt = datetime.combine(start_date, datetime.min.time())
        query = query.filter(TimelineEvent.date >= start_dt)
        filters_applied["start_date"] = start_date.isoformat()
        logger.debug(f"Applied filter: start_date>={start_date}")

    if end_date:
        # Convertir date a datetime (fin del día)
        end_dt = datetime.combine(end_date, datetime.max.time())
        query = query.filter(TimelineEvent.date <= end_dt)
        filters_applied["end_date"] = end_date.isoformat()
        logger.debug(f"Applied filter: end_date<={end_date}")

    # Búsqueda en descripción (case-insensitive)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                TimelineEvent.description.ilike(search_pattern),
                TimelineEvent.title.ilike(search_pattern) if TimelineEvent.title else False,
            )
        )
        filters_applied["search"] = search
        logger.debug(f"Applied filter: search='{search}'")

    # ═══════════════════════════════════════════════════════
    # 3. CONTAR TOTAL (para cálculo de páginas)
    # ═══════════════════════════════════════════════════════
    total_events = query.count()

    logger.info(f"Total events matching filters for case {case_id}: {total_events}")

    # Si no hay eventos, retornar respuesta vacía
    if total_events == 0:
        return PaginatedTimelineResponse(
            case_id=case_id,
            total_events=0,
            page=page,
            page_size=page_size,
            total_pages=0,
            has_next=False,
            has_prev=False,
            filters_applied=filters_applied,
            events=[],
        )

    # Calcular total de páginas
    total_pages = (total_events + page_size - 1) // page_size

    # Validar y ajustar página solicitada
    if page > total_pages:
        logger.warning(f"Requested page {page} > total_pages {total_pages}, adjusting to last page")
        page = total_pages

    # ═══════════════════════════════════════════════════════
    # 4. APLICAR ORDENAMIENTO
    # ═══════════════════════════════════════════════════════
    if sort_by == "date":
        order_col = TimelineEvent.date
    elif sort_by == "amount":
        # Ordenar por amount, pero NULL al final
        order_col = (
            TimelineEvent.amount.nullslast()
            if sort_order == "desc"
            else TimelineEvent.amount.nullsfirst()
        )
    elif sort_by == "severity":
        # Ordenar por severidad, pero NULL al final
        order_col = (
            TimelineEvent.severity.nullslast()
            if sort_order == "desc"
            else TimelineEvent.severity.nullsfirst()
        )
    else:
        order_col = TimelineEvent.date  # fallback

    if sort_order == "desc":
        query = query.order_by(order_col.desc() if sort_by == "date" else order_col)
    else:
        query = query.order_by(order_col.asc() if sort_by == "date" else order_col)

    logger.debug(f"Applied sorting: {sort_by} {sort_order}")

    # ═══════════════════════════════════════════════════════
    # 5. APLICAR PAGINACIÓN (LIMIT + OFFSET)
    # ═══════════════════════════════════════════════════════
    offset = (page - 1) * page_size
    events_page = query.offset(offset).limit(page_size).all()

    logger.info(
        f"✅ Timeline query executed for case {case_id}: "
        f"loaded {len(events_page)} events (page {page}/{total_pages})"
    )

    # ═══════════════════════════════════════════════════════
    # 6. ESTADÍSTICAS AGREGADAS (OPCIONAL)
    # ═══════════════════════════════════════════════════════
    statistics = None

    if include_stats:
        try:
            # Query base sin paginación (con filtros aplicados)
            base_query = db.query(TimelineEvent).filter(TimelineEvent.case_id == case_id)

            # Aplicar mismos filtros
            if event_type:
                base_query = base_query.filter(TimelineEvent.event_type == event_type)
            if category:
                base_query = base_query.filter(TimelineEvent.category == category)
            if severity:
                base_query = base_query.filter(TimelineEvent.severity == severity)
            if start_date:
                base_query = base_query.filter(
                    TimelineEvent.date >= datetime.combine(start_date, datetime.min.time())
                )
            if end_date:
                base_query = base_query.filter(
                    TimelineEvent.date <= datetime.combine(end_date, datetime.max.time())
                )
            if search:
                base_query = base_query.filter(TimelineEvent.description.ilike(f"%{search}%"))

            # Contar por tipo
            type_counts = (
                base_query.with_entities(
                    TimelineEvent.event_type, func.count(TimelineEvent.event_id)
                )
                .group_by(TimelineEvent.event_type)
                .all()
            )

            # Contar por severidad
            severity_counts = (
                base_query.filter(TimelineEvent.severity.isnot(None))
                .with_entities(TimelineEvent.severity, func.count(TimelineEvent.event_id))
                .group_by(TimelineEvent.severity)
                .all()
            )

            # Rango de fechas
            date_range = base_query.with_entities(
                func.min(TimelineEvent.date), func.max(TimelineEvent.date)
            ).first()

            statistics = {
                "total_events": total_events,
                "by_type": {t[0]: t[1] for t in type_counts},
                "by_severity": {s[0]: s[1] for s in severity_counts},
                "date_range": {
                    "min": date_range[0].isoformat() if date_range[0] else None,
                    "max": date_range[1].isoformat() if date_range[1] else None,
                }
                if date_range
                else None,
            }

            logger.debug(f"Statistics computed for case {case_id}")
        except Exception as e:
            logger.exception(f"Error computing statistics for case {case_id}: {e}")
            # No fallar si las estadísticas fallan

    # ═══════════════════════════════════════════════════════
    # 7. CONSTRUIR Y DEVOLVER RESPUESTA
    # ═══════════════════════════════════════════════════════
    return PaginatedTimelineResponse(
        case_id=case_id,
        total_events=total_events,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
        filters_applied=filters_applied,
        events=[TimelineEventResponse.from_orm(event) for event in events_page],
        statistics=statistics,
    )


@router.get(
    "/types",
    response_model=list[str],
    summary="Obtener tipos de eventos disponibles",
    description="Lista todos los tipos de eventos únicos en el timeline del caso (para filtros)",
)
async def get_event_types(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[str]:
    """
    Obtiene lista de tipos de eventos únicos para construir filtros en UI.

    Args:
        case_id: ID del caso
        db: Sesión de BD
        current_user: Usuario autenticado

    Returns:
        Lista de tipos de eventos únicos
    """
    # Verificar caso existe
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(404, f"Caso '{case_id}' no encontrado")

    types = (
        db.query(TimelineEvent.event_type).filter(TimelineEvent.case_id == case_id).distinct().all()
    )

    return [t[0] for t in types if t[0]]


@router.get(
    "/statistics",
    summary="Estadísticas del timeline",
    description="Obtiene estadísticas agregadas del timeline completo (sin paginación)",
)
async def get_timeline_statistics(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Obtiene estadísticas agregadas del timeline sin paginación.

    Útil para dashboards o vistas de resumen.

    Args:
        case_id: ID del caso
        db: Sesión de BD
        current_user: Usuario autenticado

    Returns:
        Dict con estadísticas agregadas
    """
    # Verificar caso existe
    case = db.query(Case).filter(Case.case_id == case_id).first()
    if not case:
        raise HTTPException(404, f"Caso '{case_id}' no encontrado")

    # Total de eventos
    total_events = (
        db.query(func.count(TimelineEvent.event_id))
        .filter(TimelineEvent.case_id == case_id)
        .scalar()
    )

    # Contar por tipo
    type_counts = (
        db.query(TimelineEvent.event_type, func.count(TimelineEvent.event_id))
        .filter(TimelineEvent.case_id == case_id)
        .group_by(TimelineEvent.event_type)
        .all()
    )

    # Contar por severidad
    severity_counts = (
        db.query(TimelineEvent.severity, func.count(TimelineEvent.event_id))
        .filter(TimelineEvent.case_id == case_id)
        .filter(TimelineEvent.severity.isnot(None))
        .group_by(TimelineEvent.severity)
        .all()
    )

    # Contar por categoría
    category_counts = (
        db.query(TimelineEvent.category, func.count(TimelineEvent.event_id))
        .filter(TimelineEvent.case_id == case_id)
        .filter(TimelineEvent.category.isnot(None))
        .group_by(TimelineEvent.category)
        .all()
    )

    # Rango de fechas
    date_range = (
        db.query(func.min(TimelineEvent.date), func.max(TimelineEvent.date))
        .filter(TimelineEvent.case_id == case_id)
        .first()
    )

    # Suma total de montos
    total_amount = (
        db.query(func.sum(TimelineEvent.amount))
        .filter(TimelineEvent.case_id == case_id)
        .filter(TimelineEvent.amount.isnot(None))
        .scalar()
    )

    return {
        "case_id": case_id,
        "total_events": total_events or 0,
        "by_type": {t[0]: t[1] for t in type_counts},
        "by_severity": {s[0]: s[1] for s in severity_counts},
        "by_category": {c[0]: c[1] for c in category_counts},
        "date_range": {
            "min": date_range[0].isoformat() if date_range[0] else None,
            "max": date_range[1].isoformat() if date_range[1] else None,
        }
        if date_range
        else None,
        "total_amount": float(total_amount) if total_amount else None,
    }
