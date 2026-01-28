"""
Sistema de Detección de Riesgos de Culpabilidad Concursal (Fase B3).

OBJETIVO:
Detectar automáticamente riesgos de calificación culpable del concurso según:
- Art. 257-261 CP (Alzamiento de bienes)
- Art. 164.2 LC (Presunciones de culpabilidad)
- Art. 443 TRLC (Calificación del concurso)

PRINCIPIOS:
1. Evidencia probatoria completa
2. Trazabilidad de cada alerta
3. Scoring de severidad (0-100)
4. NO interpretaciones legales (solo hechos)
5. Confidence level por riesgo

RIESGOS DETECTADOS:
1. Alzamiento de bienes (ventas sospechosas)
2. Pagos preferentes a acreedores
3. Salida injustificada de recursos
4. Irregularidades contables
5. Incumplimiento de deberes formales
"""
from __future__ import annotations

from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.financial_analysis import Evidence, ConfidenceLevel
from app.services.timeline_builder import Timeline, TimelineEvent, EventType


# =========================================================
# ENUMS Y TIPOS
# =========================================================

class RiskCategory(str, Enum):
    """Categoría del riesgo de culpabilidad."""
    ALZAMIENTO_BIENES = "alzamiento_bienes"              # Art. 257-261 CP
    PAGOS_PREFERENTES = "pagos_preferentes"              # Art. 164.2.3 LC
    SALIDA_RECURSOS = "salida_recursos"                  # Art. 164.2.4 LC
    IRREGULARIDADES_CONTABLES = "irregularidades_contables"  # Art. 164.2.1 LC
    INCUMPLIMIENTO_DEBERES = "incumplimiento_deberes"    # Art. 164.2.2 LC
    OTRO = "otro"


class RiskSeverity(str, Enum):
    """Severidad del riesgo (distinto de confidence)."""
    CRITICAL = "critical"  # Riesgo crítico de culpabilidad (score 80-100)
    HIGH = "high"          # Riesgo alto (score 60-79)
    MEDIUM = "medium"      # Riesgo medio (score 40-59)
    LOW = "low"            # Riesgo bajo (score 0-39)


class LegalBasis(BaseModel):
    """Base legal del riesgo."""
    law: str = Field(..., description="Ley aplicable")
    article: str = Field(..., description="Artículo específico")
    description: str = Field(..., description="Descripción del supuesto legal")
    
    class Config:
        extra = "forbid"


class CulpabilityRisk(BaseModel):
    """
    Riesgo de calificación culpable detectado.
    """
    risk_id: str = Field(..., description="ID único del riesgo")
    category: RiskCategory = Field(..., description="Categoría del riesgo")
    severity: RiskSeverity = Field(..., description="Severidad del riesgo")
    score: int = Field(..., ge=0, le=100, description="Score numérico 0-100")
    
    title: str = Field(..., description="Título descriptivo corto")
    description: str = Field(..., description="Descripción detallada del riesgo")
    
    legal_basis: LegalBasis = Field(..., description="Base legal")
    evidence: List[Evidence] = Field(default_factory=list, description="Evidencias del riesgo")
    
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    confidence: ConfidenceLevel = Field(..., description="Confianza en la detección")
    
    # Metadata adicional
    affected_amounts: Optional[float] = Field(None, description="Importes afectados")
    affected_parties: List[str] = Field(default_factory=list, description="Partes involucradas")
    timeframe: Optional[str] = Field(None, description="Marco temporal del riesgo")
    
    # Recomendaciones
    recommended_action: str = Field(..., description="Acción recomendada")
    requires_legal_review: bool = Field(True, description="Requiere revisión legal")
    
    class Config:
        extra = "forbid"


class RiskAnalysisResult(BaseModel):
    """Resultado completo del análisis de riesgos."""
    case_id: str
    analysis_date: datetime
    
    risks: List[CulpabilityRisk] = Field(default_factory=list)
    total_risks: int = Field(0)
    critical_risks: int = Field(0)
    high_risks: int = Field(0)
    
    overall_risk_score: int = Field(..., ge=0, le=100, description="Score global de riesgo")
    overall_severity: RiskSeverity = Field(..., description="Severidad global")
    
    summary: str = Field(..., description="Resumen ejecutivo")
    
    class Config:
        extra = "forbid"


# =========================================================
# DETECCIÓN 1: ALZAMIENTO DE BIENES
# =========================================================

def detect_asset_stripping(
    timeline: Timeline,
    suspect_period_start: Optional[datetime] = None
) -> List[CulpabilityRisk]:
    """
    Detecta posible alzamiento de bienes:
    - Ventas de activos en periodo sospechoso
    - Transmisiones a vinculados
    - Precios significativamente inferiores
    
    Args:
        timeline: Timeline completo del caso
        suspect_period_start: Inicio del periodo sospechoso (2 años antes)
        
    Returns:
        Lista de riesgos detectados
    """
    risks = []
    
    # Filtrar ventas de activos
    asset_sales = [
        e for e in timeline.events
        if e.event_type in [EventType.VENTA_ACTIVO, EventType.TRANSMISION_PARTICIPACIONES]
    ]
    
    # Ventas en periodo sospechoso
    suspect_sales = []
    if suspect_period_start:
        suspect_sales = [
            e for e in asset_sales
            if e.date >= suspect_period_start and e.is_within_suspect_period
        ]
    
    # Riesgo 1: Múltiples ventas en periodo sospechoso
    if len(suspect_sales) >= 2:
        total_amount = sum(e.amount for e in suspect_sales if e.amount)
        
        risk = CulpabilityRisk(
            risk_id=f"RISK_ALZAMIENTO_001_{datetime.utcnow().timestamp()}",
            category=RiskCategory.ALZAMIENTO_BIENES,
            severity=RiskSeverity.HIGH if len(suspect_sales) >= 3 else RiskSeverity.MEDIUM,
            score=min(100, 50 + len(suspect_sales) * 10),  # Base 50 + 10 por venta
            title=f"Múltiples ventas de activos en periodo sospechoso ({len(suspect_sales)})",
            description=(
                f"Se detectaron {len(suspect_sales)} operaciones de venta/transmisión de activos "
                f"en el periodo sospechoso (2 años antes del concurso). "
                f"Importe total conocido: {total_amount:,.2f} € si disponible. "
                f"Requiere análisis de: (1) justificación económica, (2) precios de mercado, "
                f"(3) existencia de vinculación con compradores."
            ),
            legal_basis=LegalBasis(
                law="Código Penal",
                article="Art. 257-261",
                description="Alzamiento de bienes: Actos de disposición patrimonial que perjudican a acreedores"
            ),
            evidence=[e.evidence for e in suspect_sales],
            confidence=ConfidenceLevel.MEDIUM if all(e.confidence > 0.7 for e in suspect_sales) else ConfidenceLevel.LOW,
            affected_amounts=total_amount if total_amount > 0 else None,
            affected_parties=list(set(party for e in suspect_sales for party in e.parties)),
            timeframe=f"{suspect_period_start.strftime('%Y-%m-%d') if suspect_period_start else 'N/A'} - concurso",
            recommended_action="Verificar justificación económica de cada venta, precios de mercado y vinculación con compradores",
            requires_legal_review=True
        )
        risks.append(risk)
    
    # Riesgo 2: Venta única muy significativa
    large_sales = [e for e in suspect_sales if e.amount and e.amount > 100000]
    for sale in large_sales:
        if sale.amount > 500000:  # Ventas > 500k€
            risk = CulpabilityRisk(
                risk_id=f"RISK_ALZAMIENTO_002_{sale.date.timestamp()}",
                category=RiskCategory.ALZAMIENTO_BIENES,
                severity=RiskSeverity.HIGH,
                score=75,
                title=f"Venta significativa de activo en periodo sospechoso ({sale.amount:,.0f} €)",
                description=(
                    f"Venta de activo por importe de {sale.amount:,.2f} € en periodo sospechoso. "
                    f"Fecha: {sale.date.strftime('%d/%m/%Y')}. "
                    f"Requiere verificación urgente de: precio de mercado, justificación económica, "
                    f"destino de los fondos recibidos."
                ),
                legal_basis=LegalBasis(
                    law="Código Penal",
                    article="Art. 257",
                    description="Alzamiento de bienes mediante actos de disposición patrimonial"
                ),
                evidence=[sale.evidence],
                confidence=ConfidenceLevel.MEDIUM if sale.confidence > 0.7 else ConfidenceLevel.LOW,
                affected_amounts=sale.amount,
                affected_parties=sale.parties,
                timeframe=sale.date.strftime('%Y-%m-%d'),
                recommended_action="Verificar tasación independiente, destino de fondos y justificación económica",
                requires_legal_review=True
            )
            risks.append(risk)
    
    return risks


# =========================================================
# DETECCIÓN 2: PAGOS PREFERENTES
# =========================================================

def detect_preferential_payments(
    timeline: Timeline,
    suspect_period_start: Optional[datetime] = None
) -> List[CulpabilityRisk]:
    """
    Detecta pagos preferentes a acreedores:
    - Pagos en periodo sospechoso
    - Tratamiento desigual entre acreedores
    - Pagos a vinculados
    
    Args:
        timeline: Timeline completo
        suspect_period_start: Inicio periodo sospechoso
        
    Returns:
        Lista de riesgos detectados
    """
    risks = []
    
    # Filtrar pagos
    payments = [
        e for e in timeline.events
        if e.event_type in [EventType.PAGO_REALIZADO]
    ]
    
    # Pagos en periodo sospechoso
    suspect_payments = []
    if suspect_period_start:
        suspect_payments = [
            p for p in payments
            if p.date >= suspect_period_start and p.is_within_suspect_period
        ]
    
    # Riesgo: Múltiples pagos significativos en periodo sospechoso
    large_payments = [p for p in suspect_payments if p.amount and p.amount > 10000]
    
    if len(large_payments) >= 3:
        total_amount = sum(p.amount for p in large_payments if p.amount)
        
        risk = CulpabilityRisk(
            risk_id=f"RISK_PAGOS_001_{datetime.utcnow().timestamp()}",
            category=RiskCategory.PAGOS_PREFERENTES,
            severity=RiskSeverity.HIGH,
            score=min(100, 60 + len(large_payments) * 5),
            title=f"Múltiples pagos significativos en periodo sospechoso ({len(large_payments)})",
            description=(
                f"Se detectaron {len(large_payments)} pagos superiores a 10.000 € en periodo sospechoso. "
                f"Importe total: {total_amount:,.2f} €. "
                f"Requiere verificar: (1) si son privilegiados, (2) si hay trato preferente respecto a otros acreedores, "
                f"(3) justificación de pagos anticipados."
            ),
            legal_basis=LegalBasis(
                law="Ley Concursal",
                article="Art. 164.2.3",
                description="Pagos u operaciones que otorgan garantías o privilegios indebidos a acreedores"
            ),
            evidence=[p.evidence for p in large_payments],
            confidence=ConfidenceLevel.MEDIUM,
            affected_amounts=total_amount,
            affected_parties=list(set(party for p in large_payments for party in p.parties)),
            timeframe=f"{suspect_period_start.strftime('%Y-%m-%d') if suspect_period_start else 'N/A'} - concurso",
            recommended_action="Verificar naturaleza de créditos pagados y comparar trato con otros acreedores",
            requires_legal_review=True
        )
        risks.append(risk)
    
    return risks


# =========================================================
# DETECCIÓN 3: SALIDA INJUSTIFICADA DE RECURSOS
# =========================================================

def detect_unjustified_outflows(
    timeline: Timeline
) -> List[CulpabilityRisk]:
    """
    Detecta salidas injustificadas de recursos:
    - Retiros de efectivo sin justificación
    - Gastos personales cargados a empresa
    - Transferencias a vinculados
    """
    risks = []
    
    # Por implementar con extractos bancarios completos
    # Placeholder para estructura
    
    return risks


# =========================================================
# DETECCIÓN 4: IRREGULARIDADES CONTABLES
# =========================================================

def detect_accounting_irregularities(
    validation_result: Optional[Dict],
    timeline: Timeline
) -> List[CulpabilityRisk]:
    """
    Detecta irregularidades contables:
    - Ecuación contable incumplida
    - Manipulación de cifras (Benford)
    - Documentación contable faltante
    
    Args:
        validation_result: Resultado de validación financiera (Fase B1)
        timeline: Timeline del caso
        
    Returns:
        Lista de riesgos detectados
    """
    risks = []
    
    # Si hay validación de Fase B1, usar esos resultados
    if validation_result and not validation_result.get('is_valid'):
        issues = validation_result.get('issues', [])
        
        # Agrupar por severidad
        critical_issues = [i for i in issues if i.get('severity') == 'critical']
        
        if critical_issues:
            risk = CulpabilityRisk(
                risk_id=f"RISK_CONTABLE_001_{datetime.utcnow().timestamp()}",
                category=RiskCategory.IRREGULARIDADES_CONTABLES,
                severity=RiskSeverity.HIGH,
                score=70,
                title=f"Irregularidades contables críticas detectadas ({len(critical_issues)})",
                description=(
                    f"Se detectaron {len(critical_issues)} irregularidades contables críticas: "
                    + "; ".join([i.get('title', '') for i in critical_issues[:3]])
                    + (f" y {len(critical_issues)-3} más" if len(critical_issues) > 3 else "")
                ),
                legal_basis=LegalBasis(
                    law="Ley Concursal",
                    article="Art. 164.2.1",
                    description="Incumplimiento sustancial de obligaciones contables"
                ),
                evidence=[],  # Evidencia viene de validación
                confidence=ConfidenceLevel.HIGH,
                affected_amounts=None,
                affected_parties=[],
                timeframe="Ejercicios contables analizados",
                recommended_action="Auditoría contable completa y revisión de cumplimiento normativo",
                requires_legal_review=True
            )
            risks.append(risk)
    
    # Detectar gaps documentales contables
    accounting_events = [
        e for e in timeline.events
        if e.event_type in [EventType.CIERRE_EJERCICIO, EventType.APROBACION_CUENTAS]
    ]
    
    if len(accounting_events) < 2:  # Menos de 2 ejercicios documentados
        risk = CulpabilityRisk(
            risk_id=f"RISK_CONTABLE_002_{datetime.utcnow().timestamp()}",
            category=RiskCategory.IRREGULARIDADES_CONTABLES,
            severity=RiskSeverity.MEDIUM,
            score=50,
            title="Documentación contable insuficiente",
            description=(
                f"Solo se encontraron {len(accounting_events)} eventos contables documentados "
                f"(cierres de ejercicio o aprobaciones de cuentas). "
                f"Puede indicar incumplimiento del deber de llevanza de contabilidad."
            ),
            legal_basis=LegalBasis(
                law="Código de Comercio + Ley Concursal",
                article="Art. 25-29 CCom + Art. 164.2.1 LC",
                description="Obligación de llevar contabilidad ordenada y adecuada"
            ),
            evidence=[e.evidence for e in accounting_events],
            confidence=ConfidenceLevel.MEDIUM,
            affected_amounts=None,
            affected_parties=[],
            timeframe="Periodo analizado completo",
            recommended_action="Solicitar libros contables oficiales y auditoría de cumplimiento",
            requires_legal_review=True
        )
        risks.append(risk)
    
    return risks


# =========================================================
# FUNCIÓN PRINCIPAL DE ANÁLISIS
# =========================================================

def analyze_culpability_risks(
    timeline: Timeline,
    validation_result: Optional[Dict] = None,
    suspect_period_start: Optional[datetime] = None
) -> RiskAnalysisResult:
    """
    Ejecuta análisis completo de riesgos de culpabilidad.
    
    Args:
        timeline: Timeline completo del caso
        validation_result: Resultado de validación financiera (Fase B1)
        suspect_period_start: Inicio del periodo sospechoso
        
    Returns:
        RiskAnalysisResult con todos los riesgos detectados
    """
    all_risks = []
    
    # 1. Alzamiento de bienes
    all_risks.extend(detect_asset_stripping(timeline, suspect_period_start))
    
    # 2. Pagos preferentes
    all_risks.extend(detect_preferential_payments(timeline, suspect_period_start))
    
    # 3. Salida injustificada de recursos
    all_risks.extend(detect_unjustified_outflows(timeline))
    
    # 4. Irregularidades contables
    all_risks.extend(detect_accounting_irregularities(validation_result, timeline))
    
    # Calcular métricas
    total_risks = len(all_risks)
    critical_risks = len([r for r in all_risks if r.severity == RiskSeverity.CRITICAL])
    high_risks = len([r for r in all_risks if r.severity == RiskSeverity.HIGH])
    
    # Score global (promedio ponderado)
    if all_risks:
        overall_score = sum(r.score for r in all_risks) // len(all_risks)
    else:
        overall_score = 0
    
    # Severidad global
    if overall_score >= 80:
        overall_severity = RiskSeverity.CRITICAL
    elif overall_score >= 60:
        overall_severity = RiskSeverity.HIGH
    elif overall_score >= 40:
        overall_severity = RiskSeverity.MEDIUM
    else:
        overall_severity = RiskSeverity.LOW
    
    # Resumen ejecutivo
    if not all_risks:
        summary = "No se detectaron riesgos significativos de calificación culpable en el análisis técnico preliminar."
    else:
        summary = (
            f"Se detectaron {total_risks} riesgos de culpabilidad: "
            f"{critical_risks} críticos, {high_risks} altos. "
            f"Score global: {overall_score}/100. "
            f"Requiere revisión legal urgente."
        )
    
    return RiskAnalysisResult(
        case_id=timeline.events[0].evidence.document_id if timeline.events else "UNKNOWN",
        analysis_date=datetime.utcnow(),
        risks=all_risks,
        total_risks=total_risks,
        critical_risks=critical_risks,
        high_risks=high_risks,
        overall_risk_score=overall_score,
        overall_severity=overall_severity,
        summary=summary
    )
