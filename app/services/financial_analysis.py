"""
MÓDULO DE ANÁLISIS FINANCIERO CONCURSAL - VERSIÓN ENDURECIDA.

PROPÓSITO: Responder con DATOS FRÍOS Y TRAZABLES:
"¿Con los números que tengo, estoy obligada a preocuparme YA o no?"

PRINCIPIOS:
- Trazabilidad probatoria completa (documento + página + chunk + excerpt)
- Separación clara: estado financiero ≠ confianza de datos
- Detección multicapa: contable → exigibilidad → impago efectivo
- NO conclusiones categóricas, sino "señales compatibles con..."
- Pydantic endurecido (extra="forbid")

PROHIBIDO:
- Opiniones jurídicas
- Conclusiones sin evidencia
- Mezclar semáforos de estado y confianza
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# =========================================================
# ENUMS SEPARADOS
# =========================================================


class FinancialStatus(str, Enum):
    """Estado financiero (salud económica)."""

    CRITICAL = "critical"  # 🔴 Situación crítica
    CONCERNING = "concerning"  # 🟡 Preocupante
    STABLE = "stable"  # 🟢 Estable


class ConfidenceLevel(str, Enum):
    """Nivel de confianza de los datos extraídos."""

    HIGH = "high"  # 🟢 Alta confianza (datos verificados, fuente fiable)
    MEDIUM = "medium"  # 🟡 Media (datos incompletos o método incierto)
    LOW = "low"  # 🔴 Baja (datos no verificables o fuente dudosa)


class DataReliability(str, Enum):
    """Fiabilidad de la fuente documental."""

    OFFICIAL = "official"  # Documento oficial verificable
    RELIABLE = "reliable"  # Fuente confiable (Excel, PDF estructurado)
    INCOMPLETE = "incomplete"  # Documento incompleto
    UNCERTAIN = "uncertain"  # Fuente no verificable
    MISSING = "missing"  # Documento no disponible


class CreditType(str, Enum):
    """Clasificación de créditos según TRLC."""

    PRIVILEGED_SPECIAL = "privilegiado_especial"  # Con garantía real
    PRIVILEGED_GENERAL = "privilegiado_general"  # Laborales, públicos
    ORDINARY = "ordinario"  # Sin privilegio
    SUBORDINATED = "subordinado"  # Último orden
    UNDETERMINED = "no_determinado"  # No clasificable aún


# =========================================================
# MODELO DE EVIDENCIA (TRAZABILIDAD PROBATORIA)
# =========================================================


class Evidence(BaseModel):
    """
    Evidencia probatoria con trazabilidad completa.

    Cumple requisitos de cadena probatoria:
    - Documento origen (ID + nombre)
    - Ubicación exacta (página + chunk + offsets)
    - Fragmento literal (excerpt)
    - Método de extracción
    - Confianza de extracción
    """

    document_id: str = Field(..., description="ID único del documento")
    filename: str = Field(..., description="Nombre del archivo original")
    chunk_id: Optional[str] = Field(None, description="ID del chunk si aplica")
    page: Optional[int] = Field(None, description="Número de página (si aplica)")
    start_char: Optional[int] = Field(None, description="Offset inicio en documento")
    end_char: Optional[int] = Field(None, description="Offset fin en documento")
    excerpt: str = Field(..., description="Fragmento literal (máx 200 chars)")
    extraction_method: str = Field(..., description="Método: pdf_text, excel_cell, ocr")
    extraction_confidence: float = Field(..., ge=0.0, le=1.0, description="Confianza 0.0-1.0")

    class Config:
        extra = "forbid"  # Rechazar campos no declarados


# =========================================================
# MODELOS DE DATOS CONTABLES (CON EVIDENCIA POR CAMPO)
# =========================================================


class BalanceField(BaseModel):
    """Campo individual del balance con evidencia."""

    value: float = Field(..., description="Valor numérico")
    evidence: Evidence = Field(..., description="Evidencia probatoria")
    confidence: ConfidenceLevel = Field(..., description="Confianza del campo")

    class Config:
        extra = "forbid"


class BalanceData(BaseModel):
    """
    Balance de situación con trazabilidad por campo.

    Cada cifra tiene su propia evidencia y nivel de confianza.
    """

    activo_corriente: Optional[BalanceField] = None
    activo_no_corriente: Optional[BalanceField] = None
    activo_total: Optional[BalanceField] = None
    pasivo_corriente: Optional[BalanceField] = None
    pasivo_no_corriente: Optional[BalanceField] = None
    pasivo_total: Optional[BalanceField] = None
    patrimonio_neto: Optional[BalanceField] = None

    overall_confidence: ConfidenceLevel = Field(..., description="Confianza global del balance")
    source_date: Optional[str] = Field(None, description="Fecha del balance (YYYY-MM-DD)")

    class Config:
        extra = "forbid"


class ProfitLossField(BaseModel):
    """Campo de PyG con evidencia."""

    value: float
    evidence: Evidence
    confidence: ConfidenceLevel

    class Config:
        extra = "forbid"


class ProfitLossData(BaseModel):
    """Pérdidas y Ganancias con trazabilidad."""

    ingresos_explotacion: Optional[ProfitLossField] = None
    resultado_explotacion: Optional[ProfitLossField] = None
    resultado_ejercicio: Optional[ProfitLossField] = None

    overall_confidence: ConfidenceLevel
    source_date: Optional[str] = None

    class Config:
        extra = "forbid"


# =========================================================
# CLASIFICACIÓN DE CRÉDITOS
# =========================================================


class CreditClassification(BaseModel):
    """Clasificación de un crédito con evidencia."""

    credit_type: CreditType
    amount: float = Field(..., gt=0, description="Importe > 0")
    creditor_name: Optional[str] = None
    creditor_type: Optional[str] = Field(
        None,
        description="Tipo normalizado del acreedor (public/bank/supplier/employee/landlord/related_party/other)",
    )
    amount_confidence: Optional[str] = Field(
        None,
        description="Confianza del importe extraído (exact/approx/unknown). Si no consta, None.",
    )
    period_start: Optional[str] = Field(None, description="Inicio período (YYYY-MM-DD) si consta")
    period_end: Optional[str] = Field(None, description="Fin período (YYYY-MM-DD) si consta")
    period_note: Optional[str] = Field(None, description="Nota de período si no consta fecha exacta")
    period_excerpt: Optional[str] = Field(None, description="Extracto breve que soporta el período (si consta)")
    has_security: Optional[bool] = Field(
        None,
        description="Garantía real: True si consta, None si no consta (no afirmar sin evidencia)",
    )
    security_type: Optional[str] = Field(
        None,
        description="Tipo de garantía (mortgage/pledge/reservation_of_title/other) si consta",
    )
    security_excerpt: Optional[str] = Field(None, description="Extracto breve que soporta la garantía (si consta)")
    description: str
    evidence: Evidence

    class Config:
        extra = "forbid"


# =========================================================
# RATIOS FINANCIEROS
# =========================================================


class FinancialRatio(BaseModel):
    """Ratio financiero calculado."""

    name: str
    value: Optional[float] = None
    status: FinancialStatus  # Estado financiero (no confianza)
    interpretation: str  # En lenguaje humano
    formula: str
    confidence: ConfidenceLevel  # Confianza del cálculo (separado de status)

    class Config:
        extra = "forbid"


# =========================================================
# DETECCIÓN DE INSOLVENCIA (MULTICAPA)
# =========================================================


class InsolvencySignal(BaseModel):
    """
    Señal individual de insolvencia.

    NO es una conclusión, sino un indicador objetivo.
    """

    signal_type: str = Field(..., description="contable, exigibilidad, impago_efectivo")
    description: str = Field(..., description="Descripción clara del indicador")
    evidence: Evidence = Field(..., description="Evidencia probatoria")
    severity: FinancialStatus = Field(..., description="Gravedad del indicador")
    amount: Optional[float] = Field(None, description="Importe si aplica")

    class Config:
        extra = "forbid"


class InsolvencyDetection(BaseModel):
    """
    Detección de insolvencia con estructura multicapa.

    NO concluye categóricamente "es insolvente".
    SINO "señales compatibles con insolvencia" clasificadas por tipo.
    """

    signals_contables: list[InsolvencySignal] = Field(
        default_factory=list,
        description="Señales contables: déficit liquidez, PN negativo, pérdidas",
    )
    signals_exigibilidad: list[InsolvencySignal] = Field(
        default_factory=list, description="Señales de exigibilidad: facturas vencidas >90d"
    )
    signals_impago: list[InsolvencySignal] = Field(
        default_factory=list, description="Señales de impago efectivo: embargos, requerimientos"
    )

    overall_assessment: str = Field(
        ...,
        description="Evaluación global (ej: 'Señales compatibles con insolvencia actual (3 indicadores)')",
    )
    confidence_level: ConfidenceLevel = Field(
        ..., description="Confianza de la evaluación (según calidad de datos)"
    )
    critical_missing_docs: list[str] = Field(
        default_factory=list, description="Documentos críticos faltantes"
    )

    class Config:
        extra = "forbid"


# =========================================================
# TIMELINE
# =========================================================


class TimelineEvent(BaseModel):
    """Evento en el timeline con evidencia."""

    # Identificador estable del evento (para edición/overrides y trazabilidad en UI).
    # Se rellena cuando es posible; si no, puede quedar vacío.
    event_id: Optional[str] = None

    # En salida a cliente puede faltar o ser inválida (epoch/default); se sanea a None.
    date: Optional[datetime] = None
    event_type: str  # "embargo", "factura_vencida", "reclamacion"
    description: str
    amount: Optional[float] = None
    evidence: Evidence

    class Config:
        extra = "forbid"


# =========================================================
# MODELOS DE RESPUESTA PAGINADA PARA TIMELINE
# =========================================================


class TimelineEventResponse(BaseModel):
    """
    Evento individual del timeline para respuesta API.

    Más ligero que TimelineEvent (evidencia opcional).
    Compatible con ORM (from_orm).
    """

    event_id: str = Field(..., description="ID único del evento")
    date: datetime = Field(..., description="Fecha del evento")
    event_type: str = Field(..., description="Tipo de evento")
    category: Optional[str] = Field(None, description="Categoría del evento")
    description: str = Field(..., description="Descripción del evento")
    title: Optional[str] = Field(None, description="Título corto")
    amount: Optional[float] = Field(None, description="Importe asociado")
    severity: Optional[str] = Field(None, description="Severidad: critical/high/medium/low")
    document_id: Optional[str] = Field(None, description="ID del documento fuente")
    extraction_confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Confianza extracción"
    )

    class Config:
        from_attributes = True  # Permite from_orm()
        extra = "forbid"


class PaginatedTimelineResponse(BaseModel):
    """
    Respuesta paginada del timeline.

    Incluye:
    - Metadata de paginación (page, total_pages, etc.)
    - Filtros aplicados (para UI)
    - Eventos de la página actual
    - Estadísticas opcionales
    """

    case_id: str = Field(..., description="ID del caso")

    # Paginación
    total_events: int = Field(..., ge=0, description="Total de eventos en el caso (con filtros)")
    page: int = Field(..., ge=1, description="Página actual (1-based)")
    page_size: int = Field(..., ge=1, le=100, description="Eventos por página")
    total_pages: int = Field(..., ge=0, description="Total de páginas")
    has_next: bool = Field(..., description="Hay página siguiente")
    has_prev: bool = Field(..., description="Hay página anterior")

    # Filtros aplicados (para UI)
    filters_applied: dict = Field(
        default_factory=dict, description="Filtros aplicados en esta query"
    )

    # Eventos de esta página
    events: list[TimelineEventResponse] = Field(
        default_factory=list, description="Eventos de la página"
    )

    # Estadísticas (opcional, solo si se solicita)
    statistics: Optional[dict] = Field(
        None, description="Estadísticas agregadas del timeline completo"
    )

    class Config:
        extra = "forbid"


# =========================================================
# RESULTADO COMPLETO
# =========================================================


class FinancialAnalysisResult(BaseModel):
    """
    Resultado completo del análisis financiero.

    NUEVAS CARACTERÍSTICAS (Fase B1):
    - Validación de coherencia contable
    - Detección de anomalías (Ley de Benford)
    - Extracción estructurada de tablas
    """

    case_id: str
    analysis_date: datetime

    # 1. Datos contables
    balance: Optional[BalanceData] = None
    profit_loss: Optional[ProfitLossData] = None

    # 2. Clasificación de créditos
    credit_classification: list[CreditClassification] = Field(default_factory=list)
    total_debt: Optional[float] = None

    # 3. Ratios financieros
    ratios: list[FinancialRatio] = Field(default_factory=list)

    # 4. Detección de insolvencia (multicapa)
    insolvency: Optional[InsolvencyDetection] = None

    # 5. Timeline
    timeline: list[TimelineEvent] = Field(default_factory=list)

    # 6. NUEVOS CAMPOS (Fase B1)
    validation_result: Optional[dict] = Field(
        None, description="Resultado de validaciones contables"
    )
    data_quality_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Score de calidad de datos (0-1)"
    )

    # 7. NUEVOS CAMPOS (Fase B2 - Timeline)
    timeline_statistics: Optional[dict] = Field(None, description="Estadísticas del timeline")
    timeline_patterns: Optional[list[dict]] = Field(
        None, description="Patrones sospechosos detectados"
    )

    class Config:
        extra = "forbid"


# =========================================================
# FUNCIONES DE CÁLCULO DE RATIOS
# =========================================================


def calculate_liquidity_ratio(
    activo_corriente: Optional[BalanceField], pasivo_corriente: Optional[BalanceField]
) -> FinancialRatio:
    """
    Calcula ratio de liquidez CON EVIDENCIA.

    Interpretación:
    - < 1.0: 🔴 Liquidez crítica
    - 1.0-1.5: 🟡 Situación ajustada
    - > 1.5: 🟢 Sin tensión inmediata
    """
    if not activo_corriente or not pasivo_corriente:
        return FinancialRatio(
            name="Ratio de Liquidez",
            value=None,
            status=FinancialStatus.CRITICAL,
            interpretation="No calculable - faltan datos de activo o pasivo corriente",
            formula="Activo Corriente / Pasivo Corriente",
            confidence=ConfidenceLevel.LOW,
        )

    if pasivo_corriente.value == 0:
        return FinancialRatio(
            name="Ratio de Liquidez",
            value=None,
            status=FinancialStatus.STABLE,
            interpretation="No aplica - sin pasivo corriente",
            formula="Activo Corriente / Pasivo Corriente",
            confidence=ConfidenceLevel.MEDIUM,
        )

    ratio = activo_corriente.value / pasivo_corriente.value

    # Determinar ESTADO FINANCIERO
    if ratio < 1.0:
        status = FinancialStatus.CRITICAL
        interpretation = (
            f"Liquidez crítica: {ratio:.2f}. No puede pagar lo inmediato con lo disponible"
        )
    elif ratio < 1.5:
        status = FinancialStatus.CONCERNING
        interpretation = (
            f"Situación ajustada: {ratio:.2f}. Liquidez justa para obligaciones inmediatas"
        )
    else:
        status = FinancialStatus.STABLE
        interpretation = f"Sin tensión inmediata: {ratio:.2f}. Liquidez suficiente"

    # Determinar CONFIANZA (separado de estado)
    if (
        activo_corriente.confidence == ConfidenceLevel.HIGH
        and pasivo_corriente.confidence == ConfidenceLevel.HIGH
    ):
        confidence = ConfidenceLevel.HIGH
    elif (
        activo_corriente.confidence == ConfidenceLevel.LOW
        or pasivo_corriente.confidence == ConfidenceLevel.LOW
    ):
        confidence = ConfidenceLevel.LOW
    else:
        confidence = ConfidenceLevel.MEDIUM

    return FinancialRatio(
        name="Ratio de Liquidez",
        value=ratio,
        status=status,
        interpretation=interpretation,
        formula="Activo Corriente / Pasivo Corriente",
        confidence=confidence,
    )


def calculate_solvency_ratio(
    activo_total: Optional[BalanceField], pasivo_total: Optional[BalanceField]
) -> FinancialRatio:
    """
    Calcula ratio de solvencia (endeudamiento).

    Interpretación:
    - > 1.0: 🔴 Sobreendeudamiento (deudas > activos)
    - 0.7-1.0: 🟡 Endeudamiento alto
    - < 0.7: 🟢 Endeudamiento controlado
    """
    if not activo_total or not pasivo_total:
        return FinancialRatio(
            name="Ratio de Endeudamiento",
            value=None,
            status=FinancialStatus.CRITICAL,
            interpretation="No calculable - faltan datos de activo o pasivo total",
            formula="Pasivo Total / Activo Total",
            confidence=ConfidenceLevel.LOW,
        )

    if activo_total.value == 0:
        return FinancialRatio(
            name="Ratio de Endeudamiento",
            value=None,
            status=FinancialStatus.CRITICAL,
            interpretation="No calculable - activo total cero",
            formula="Pasivo Total / Activo Total",
            confidence=ConfidenceLevel.LOW,
        )

    ratio = pasivo_total.value / activo_total.value

    # Estado financiero
    if ratio > 1.0:
        status = FinancialStatus.CRITICAL
        interpretation = (
            f"Sobreendeudamiento: {ratio:.2f}. Las deudas superan el valor de los activos"
        )
    elif ratio > 0.7:
        status = FinancialStatus.CONCERNING
        interpretation = (
            f"Endeudamiento alto: {ratio:.2f}. Más del 70% del activo está financiado con deuda"
        )
    else:
        status = FinancialStatus.STABLE
        interpretation = f"Endeudamiento controlado: {ratio:.2f}"

    # Confianza
    if (
        activo_total.confidence == ConfidenceLevel.HIGH
        and pasivo_total.confidence == ConfidenceLevel.HIGH
    ):
        confidence = ConfidenceLevel.HIGH
    elif (
        activo_total.confidence == ConfidenceLevel.LOW
        or pasivo_total.confidence == ConfidenceLevel.LOW
    ):
        confidence = ConfidenceLevel.LOW
    else:
        confidence = ConfidenceLevel.MEDIUM

    return FinancialRatio(
        name="Ratio de Endeudamiento",
        value=ratio,
        status=status,
        interpretation=interpretation,
        formula="Pasivo Total / Activo Total",
        confidence=confidence,
    )


# =========================================================
# DETECCIÓN DE INSOLVENCIA (MULTICAPA Y ENDURECIDA)
# =========================================================


def detect_insolvency_signals(
    balance: Optional[BalanceData],
    profit_loss: Optional[ProfitLossData],
    timeline_events: list[TimelineEvent],
) -> InsolvencyDetection:
    """
    Detecta SEÑALES de insolvencia con estructura multicapa.

    NO concluye "es insolvente" categóricamente.
    Clasifica señales en 3 capas:
    1. Contables: déficit liquidez, PN negativo, pérdidas
    2. Exigibilidad: facturas vencidas >90d con fecha y acreedor
    3. Impago efectivo: embargos, requerimientos judiciales

    Si faltan capas 2 o 3, baja la confianza.
    """
    signals_contables = []
    signals_exigibilidad = []
    signals_impago = []
    missing_docs = []

    # ═══════════════════════════════════════════════════════
    # CAPA 1: SEÑALES CONTABLES
    # ═══════════════════════════════════════════════════════

    if balance:
        # Señal 1: Déficit de liquidez
        if balance.pasivo_corriente and balance.activo_corriente:
            if balance.pasivo_corriente.value > balance.activo_corriente.value:
                deficit = balance.pasivo_corriente.value - balance.activo_corriente.value
                signals_contables.append(
                    InsolvencySignal(
                        signal_type="contable",
                        description=f"Déficit de liquidez: {deficit:,.0f} € (Pasivo Corriente > Activo Corriente)",
                        evidence=balance.pasivo_corriente.evidence,
                        severity=FinancialStatus.CRITICAL,
                        amount=deficit,
                    )
                )

        # Señal 2: Patrimonio neto negativo
        if balance.patrimonio_neto:
            if balance.patrimonio_neto.value < 0:
                signals_contables.append(
                    InsolvencySignal(
                        signal_type="contable",
                        description=f"Patrimonio neto negativo: {balance.patrimonio_neto.value:,.0f} € (quiebra técnica)",
                        evidence=balance.patrimonio_neto.evidence,
                        severity=FinancialStatus.CRITICAL,
                        amount=balance.patrimonio_neto.value,
                    )
                )

        # Señal 3: Pérdidas del ejercicio (AHORA SÍ suma a señales contables)
        if profit_loss and profit_loss.resultado_ejercicio:
            if profit_loss.resultado_ejercicio.value < 0:
                signals_contables.append(
                    InsolvencySignal(
                        signal_type="contable",
                        description=f"Pérdidas del ejercicio: {profit_loss.resultado_ejercicio.value:,.0f} €",
                        evidence=profit_loss.resultado_ejercicio.evidence,
                        severity=FinancialStatus.CONCERNING,
                        amount=profit_loss.resultado_ejercicio.value,
                    )
                )
    else:
        missing_docs.append("Balance de situación (crítico)")

    # ═══════════════════════════════════════════════════════
    # CAPA 2: SEÑALES DE EXIGIBILIDAD
    # ═══════════════════════════════════════════════════════

    for event in timeline_events:
        if event.event_type == "factura_vencida" and event.amount:
            signals_exigibilidad.append(
                InsolvencySignal(
                    signal_type="exigibilidad",
                    description=f"Factura vencida: {event.description}",
                    evidence=event.evidence,
                    severity=FinancialStatus.CONCERNING,
                    amount=event.amount,
                )
            )

    if not signals_exigibilidad:
        missing_docs.append("Facturas vencidas o relación de acreedores (recomendado)")

    # ═══════════════════════════════════════════════════════
    # CAPA 3: SEÑALES DE IMPAGO EFECTIVO
    # ═══════════════════════════════════════════════════════

    for event in timeline_events:
        if event.event_type == "embargo":
            signals_impago.append(
                InsolvencySignal(
                    signal_type="impago_efectivo",
                    description=f"Embargo efectivo: {event.description}",
                    evidence=event.evidence,
                    severity=FinancialStatus.CRITICAL,
                    amount=event.amount,
                )
            )

    # ═══════════════════════════════════════════════════════
    # EVALUACIÓN GLOBAL (NO CATEGÓRICA)
    # ═══════════════════════════════════════════════════════

    total_signals = len(signals_contables) + len(signals_exigibilidad) + len(signals_impago)

    # Determinar assessment según capas presentes
    if total_signals == 0:
        assessment = "No se detectaron señales de insolvencia actual"
        confidence = ConfidenceLevel.MEDIUM if balance else ConfidenceLevel.LOW

    elif signals_impago:  # Embargos = señal más fuerte
        assessment = "Concurren múltiples señales objetivas compatibles con un escenario de insolvencia actual (incluye impagos efectivos)."
        # Alta confianza si tenemos balance + impagos documentados
        confidence = (
            ConfidenceLevel.HIGH
            if (balance and balance.overall_confidence == ConfidenceLevel.HIGH)
            else ConfidenceLevel.MEDIUM
        )

    elif signals_exigibilidad and signals_contables:
        assessment = "Concurren señales objetivas compatibles con tensión financiera (contables y de exigibilidad)."
        confidence = ConfidenceLevel.MEDIUM

    elif signals_contables:
        assessment = "Concurren señales contables de alerta que requieren contraste con documentación completa."
        # Baja confianza si SOLO tenemos señales contables sin exigibilidad
        confidence = ConfidenceLevel.LOW if not balance else ConfidenceLevel.MEDIUM

    else:
        assessment = "Evaluación indeterminada - datos insuficientes"
        confidence = ConfidenceLevel.LOW

    # Documentos críticos adicionales
    if not profit_loss:
        missing_docs.append("Cuenta de Pérdidas y Ganancias (recomendado)")

    return InsolvencyDetection(
        signals_contables=signals_contables,
        signals_exigibilidad=signals_exigibilidad,
        signals_impago=signals_impago,
        overall_assessment=assessment,
        confidence_level=confidence,
        critical_missing_docs=missing_docs,
    )
