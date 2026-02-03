"""
OUTPUT DETERMINISTA DEL RULE ENGINE (LEGAL DECISIONS).

Este módulo define el output OBLIGATORIO del Rule Engine.

REGLAS NO NEGOCIABLES:
- El Rule Engine NO llama a LLM.
- Todas las decisiones son DETERMINISTAS.
- Misma entrada → mismo output (siempre).
- rationale es generado por lógica, NO por LLM.

SEPARACIÓN CRÍTICA:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DECIDE (Rule Engine) ≠ EXPLICA (LLM)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

El Rule Engine DECIDE:
- Qué regla aplica
- Severidad
- Confianza
- Evidencia encontrada vs requerida

El LLM EXPLICA:
- Por qué la regla aplicó (en lenguaje natural)
- Consecuencias legales
- Recomendaciones
"""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ========================================
# VERSIÓN DEL ENGINE
# ========================================
RULE_ENGINE_VERSION = "2.0.0"  # Determinista, sin LLM


# ========================================
# DECISIÓN DE UNA REGLA INDIVIDUAL
# ========================================


class RuleDecision(BaseModel):
    """
    Decisión determinista de UNA regla legal.

    Este modelo contiene TODO lo necesario para entender una decisión legal
    SIN necesidad de LLM.

    PROHIBIDO:
    - Generar este modelo usando LLM
    - Modificar severidad basado en LLM
    - Inferir applies usando razonamiento no determinista
    """

    rule_id: str = Field(..., description="ID único de la regla (ej: TRLC_ART_5_DEBER_SOLICITUD)")

    rule_name: str = Field(
        ..., description="Nombre corto de la regla (ej: Deber de solicitar concurso)"
    )

    article: str = Field(..., description="Artículo legal que fundamenta (ej: TRLC Art. 5)")

    applies: bool = Field(..., description="¿La regla aplica al caso? (decisión DETERMINISTA)")

    severity: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="Severidad de la violación (si applies=True)"
    )

    confidence: Literal["low", "medium", "high", "indeterminate"] = Field(
        ..., description="Confianza en la decisión (basada en evidencia disponible)"
    )

    evidence_required: list[str] = Field(
        default_factory=list,
        description="Evidencia requerida por la regla (doc_types, flags, etc.)",
    )

    evidence_found: list[str] = Field(
        default_factory=list, description="Evidencia encontrada en el caso"
    )

    rationale: str = Field(
        ..., description="Razón CORTA y DETERMINISTA (NO lenguaje elaborado del LLM)"
    )

    score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Score numérico de aplicabilidad [0.0-1.0]"
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadata técnica adicional (NO decisiones)"
    )

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        frozen=False,  # Permitir modificación si necesario
    )


# ========================================
# RESULTADO COMPLETO DEL RULE ENGINE
# ========================================


class RuleEngineResult(BaseModel):
    """
    Resultado COMPLETO del Rule Engine.

    Este es el output OFICIAL del motor de reglas.
    PROHIBIDO modificar este resultado con LLM.

    REGLA CRÍTICA:
    - evaluated_rules = TODAS las reglas evaluadas
    - triggered_rules = Solo las que applies=True
    - discarded_rules = Solo las que applies=False
    """

    evaluated_rules: list[RuleDecision] = Field(
        default_factory=list, description="TODAS las reglas evaluadas (triggered + discarded)"
    )

    triggered_rules: list[RuleDecision] = Field(
        default_factory=list, description="Solo reglas que applies=True (filtro de evaluated_rules)"
    )

    discarded_rules: list[RuleDecision] = Field(
        default_factory=list,
        description="Solo reglas que applies=False (filtro de evaluated_rules)",
    )

    summary_flags: dict[str, bool] = Field(
        default_factory=dict, description="Flags técnicos booleanos (NO lenguaje legal elaborado)"
    )

    engine_version: str = Field(
        default=RULE_ENGINE_VERSION, description="Versión del Rule Engine usado"
    )

    evaluated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp de evaluación"
    )

    case_id: str = Field(..., description="ID del caso evaluado")

    rulebook_version: Optional[str] = Field(default=None, description="Versión del rulebook usado")

    execution_time_ms: Optional[float] = Field(
        default=None, description="Tiempo de ejecución del engine"
    )

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    def to_deterministic_hash(self) -> str:
        """
        Genera hash determinista del resultado.

        Usado para verificar que misma entrada → mismo output.
        Excluye timestamps y execution_time_ms.
        """
        import hashlib
        import json

        # Crear dict sin campos no deterministas
        deterministic_data = {
            "case_id": self.case_id,
            "engine_version": self.engine_version,
            "rulebook_version": self.rulebook_version,
            "triggered_rules": [
                {
                    "rule_id": r.rule_id,
                    "applies": r.applies,
                    "severity": r.severity,
                    "confidence": r.confidence,
                    "score": r.score,
                }
                for r in sorted(self.triggered_rules, key=lambda x: x.rule_id)
            ],
            "summary_flags": dict(sorted(self.summary_flags.items())),
        }

        json_str = json.dumps(deterministic_data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()


# ========================================
# BUILDER PARA CREAR RuleEngineResult
# ========================================


class RuleEngineResultBuilder:
    """
    Builder para construir RuleEngineResult de forma segura.

    Asegura coherencia entre evaluated_rules, triggered_rules y discarded_rules.
    """

    def __init__(self, case_id: str, rulebook_version: Optional[str] = None):
        self.case_id = case_id
        self.rulebook_version = rulebook_version
        self._evaluated: list[RuleDecision] = []
        self._flags: dict[str, bool] = {}
        self._start_time = datetime.utcnow()

    def add_rule_decision(self, decision: RuleDecision) -> None:
        """Añade una decisión de regla al resultado."""
        self._evaluated.append(decision)

    def add_flag(self, flag_name: str, value: bool) -> None:
        """Añade un flag técnico al resultado."""
        self._flags[flag_name] = value

    def build(self) -> RuleEngineResult:
        """
        Construye el RuleEngineResult final.

        Automáticamente separa triggered vs discarded.
        """
        execution_time_ms = (datetime.utcnow() - self._start_time).total_seconds() * 1000

        triggered = [r for r in self._evaluated if r.applies]
        discarded = [r for r in self._evaluated if not r.applies]

        return RuleEngineResult(
            case_id=self.case_id,
            evaluated_rules=self._evaluated,
            triggered_rules=triggered,
            discarded_rules=discarded,
            summary_flags=self._flags,
            engine_version=RULE_ENGINE_VERSION,
            rulebook_version=self.rulebook_version,
            execution_time_ms=execution_time_ms,
        )


# ========================================
# HELPERS DE VALIDACIÓN
# ========================================


def validate_determinism(result: RuleEngineResult) -> bool:
    """
    Valida que el resultado es determinista.

    Verifica:
    - triggered_rules ⊆ evaluated_rules
    - discarded_rules ⊆ evaluated_rules
    - triggered ∪ discarded = evaluated
    - NO hay overlaps
    """
    evaluated_ids = {r.rule_id for r in result.evaluated_rules}
    triggered_ids = {r.rule_id for r in result.triggered_rules}
    discarded_ids = {r.rule_id for r in result.discarded_rules}

    # Verificar subconjuntos
    if not triggered_ids.issubset(evaluated_ids):
        return False

    if not discarded_ids.issubset(evaluated_ids):
        return False

    # Verificar unión
    if triggered_ids.union(discarded_ids) != evaluated_ids:
        return False

    # Verificar NO overlap
    if triggered_ids.intersection(discarded_ids):
        return False

    # Verificar coherencia applies
    for rule in result.triggered_rules:
        if not rule.applies:
            return False

    for rule in result.discarded_rules:
        if rule.applies:
            return False

    return True
