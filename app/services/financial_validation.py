"""
Validación de coherencia y detección de anomalías en estados financieros.

FASE B1: ANÁLISIS FINANCIERO PROFUNDO
Objetivo: Detectar inconsistencias y anomalías que puedan indicar:
- Errores contables
- Manipulación de cifras
- Incoherencias entre estados financieros

MÉTODOS:
1. Validación de ecuaciones contables básicas
2. Coherencia entre Balance y PyG
3. Ley de Benford para detectar manipulación
4. Ratios fuera de rangos razonables
"""
from __future__ import annotations

import math
from collections import Counter
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.services.financial_analysis import (
    BalanceData,
    ConfidenceLevel,
    Evidence,
    ProfitLossData,
)

# =========================================================
# ENUMS Y MODELOS
# =========================================================


class ValidationSeverity(str, Enum):
    """Severidad de una validación fallida."""

    CRITICAL = "critical"  # Viola principios contables básicos
    HIGH = "high"  # Inconsistencia importante
    MEDIUM = "medium"  # Anomalía sospechosa
    LOW = "low"  # Desviación menor


class ValidationIssue(BaseModel):
    """Problema detectado en validación."""

    code: str = Field(..., description="Código del problema (ej: BALANCE_EQUATION_FAILED)")
    severity: ValidationSeverity = Field(..., description="Severidad del problema")
    title: str = Field(..., description="Título descriptivo")
    description: str = Field(..., description="Descripción detallada del problema")
    expected_value: Optional[float] = Field(None, description="Valor esperado")
    actual_value: Optional[float] = Field(None, description="Valor real encontrado")
    deviation_percent: Optional[float] = Field(None, description="% de desviación")
    affected_fields: list[str] = Field(default_factory=list, description="Campos afectados")
    evidence: list[Evidence] = Field(default_factory=list, description="Evidencias del problema")

    class Config:
        extra = "forbid"


class ValidationResult(BaseModel):
    """Resultado completo de validación."""

    is_valid: bool = Field(..., description="True si pasa todas las validaciones")
    total_checks: int = Field(..., description="Total de validaciones ejecutadas")
    passed_checks: int = Field(..., description="Validaciones pasadas")
    issues: list[ValidationIssue] = Field(default_factory=list, description="Problemas encontrados")
    confidence_level: ConfidenceLevel = Field(..., description="Confianza en los datos")

    class Config:
        extra = "forbid"


# =========================================================
# VALIDACIÓN DE ECUACIÓN CONTABLE BÁSICA
# =========================================================


def validate_balance_equation(balance: BalanceData) -> Optional[ValidationIssue]:
    """
    Valida la ecuación contable básica: Activo = Pasivo + Patrimonio Neto

    REGLA FUNDAMENTAL: Esta ecuación DEBE cumplirse siempre.
    Si no se cumple, hay un error crítico en los datos.

    Args:
        balance: Datos del balance

    Returns:
        ValidationIssue si falla, None si pasa
    """
    # Calcular totales
    total_activo = 0.0
    if balance.activo_corriente:
        total_activo += balance.activo_corriente.value
    if balance.activo_no_corriente:
        total_activo += balance.activo_no_corriente.value

    total_pasivo = 0.0
    if balance.pasivo_corriente:
        total_pasivo += balance.pasivo_corriente.value
    if balance.pasivo_no_corriente:
        total_pasivo += balance.pasivo_no_corriente.value

    patrimonio_neto = balance.patrimonio_neto.value if balance.patrimonio_neto else 0.0

    # Calcular lado derecho (Pasivo + PN)
    lado_derecho = total_pasivo + patrimonio_neto

    # Tolerancia: 0.1% de desviación permitida (por redondeos)
    tolerance_percent = 0.1
    max_deviation = max(abs(total_activo), abs(lado_derecho)) * (tolerance_percent / 100)

    deviation = abs(total_activo - lado_derecho)

    if deviation > max_deviation:
        # ECUACIÓN NO SE CUMPLE
        deviation_percent = (
            (deviation / max(abs(total_activo), abs(lado_derecho))) * 100
            if max(abs(total_activo), abs(lado_derecho)) > 0
            else 0
        )

        return ValidationIssue(
            code="BALANCE_EQUATION_FAILED",
            severity=ValidationSeverity.CRITICAL,
            title="Ecuación contable básica no se cumple",
            description=(
                f"La ecuación fundamental Activo = Pasivo + Patrimonio Neto no se cumple. "
                f"Esto indica un error grave en los datos contables. "
                f"Activo: {total_activo:,.2f} €, Pasivo + PN: {lado_derecho:,.2f} €, "
                f"Diferencia: {deviation:,.2f} € ({deviation_percent:.2f}%)"
            ),
            expected_value=total_activo,
            actual_value=lado_derecho,
            deviation_percent=deviation_percent,
            affected_fields=["activo_total", "pasivo_total", "patrimonio_neto"],
            evidence=[],  # Podríamos añadir evidencias de los campos involucrados
        )

    return None


# =========================================================
# VALIDACIÓN DE COHERENCIA BALANCE - PYG
# =========================================================


def validate_balance_pyg_coherence(
    balance: BalanceData, pyg: ProfitLossData
) -> list[ValidationIssue]:
    """
    Valida coherencia entre Balance y PyG.

    REGLAS:
    1. Resultado del ejercicio (PyG) debe reflejarse en Patrimonio Neto
    2. Si hay beneficios, PN debería aumentar (comparado con año anterior)
    3. Si hay pérdidas, PN debería disminuir

    Args:
        balance: Datos del balance
        pyg: Datos de Pérdidas y Ganancias

    Returns:
        Lista de problemas encontrados
    """
    issues = []

    # Obtener resultado del ejercicio de PyG
    if not pyg.resultado_ejercicio:
        return issues  # No podemos validar sin este dato

    resultado = pyg.resultado_ejercicio.value

    # Si el resultado es significativo (más de 1000€), validar coherencia
    if abs(resultado) > 1000:
        # TODO: Comparar con variación de PN entre ejercicios
        # Por ahora, solo advertimos si hay incoherencias evidentes

        # Si hay grandes pérdidas pero PN es muy alto, puede ser sospechoso
        if (
            resultado < -100000
            and balance.patrimonio_neto
            and balance.patrimonio_neto.value > 1000000
        ):
            issues.append(
                ValidationIssue(
                    code="PYG_BALANCE_INCONSISTENCY",
                    severity=ValidationSeverity.MEDIUM,
                    title="Posible inconsistencia entre PyG y Balance",
                    description=(
                        f"El resultado del ejercicio muestra pérdidas de {abs(resultado):,.2f} €, "
                        f"pero el Patrimonio Neto es de {balance.patrimonio_neto.value:,.2f} €. "
                        f"Verificar si las pérdidas están correctamente reflejadas."
                    ),
                    expected_value=None,
                    actual_value=resultado,
                    deviation_percent=None,
                    affected_fields=["resultado_ejercicio", "patrimonio_neto"],
                    evidence=[],
                )
            )

    return issues


# =========================================================
# LEY DE BENFORD PARA DETECCIÓN DE MANIPULACIÓN
# =========================================================


def get_first_digit(number: float) -> Optional[int]:
    """
    Obtiene el primer dígito significativo de un número.

    Args:
        number: Número del cual extraer el primer dígito

    Returns:
        Primer dígito (1-9) o None si no se puede determinar
    """
    if number == 0:
        return None

    # Trabajar con valor absoluto
    abs_number = abs(number)

    # Convertir a string y extraer primer dígito no-cero
    num_str = f"{abs_number:.10f}".replace(".", "")

    for char in num_str:
        if char != "0":
            return int(char)

    return None


def calculate_benford_expected_distribution() -> dict[int, float]:
    """
    Calcula la distribución esperada según la Ley de Benford.

    La Ley de Benford establece que en muchos conjuntos de datos naturales,
    el primer dígito sigue esta distribución logarítmica:

    P(d) = log10(1 + 1/d)

    Returns:
        Diccionario con probabilidades esperadas para cada dígito 1-9
    """
    return {digit: math.log10(1 + 1 / digit) for digit in range(1, 10)}


def analyze_benford_law(numbers: list[float], min_samples: int = 30) -> Optional[ValidationIssue]:
    """
    Analiza si un conjunto de números sigue la Ley de Benford.

    La Ley de Benford se usa para detectar manipulación de datos financieros.
    Si los números se desvían significativamente de la distribución esperada,
    puede indicar fraude o manipulación.

    Args:
        numbers: Lista de números a analizar
        min_samples: Mínimo de muestras necesarias (default: 30)

    Returns:
        ValidationIssue si se detecta desviación significativa, None si pasa
    """
    # Filtrar números válidos
    valid_numbers = [n for n in numbers if n != 0 and not math.isnan(n) and not math.isinf(n)]

    if len(valid_numbers) < min_samples:
        return None  # No hay suficientes muestras para análisis confiable

    # Extraer primeros dígitos
    first_digits = []
    for num in valid_numbers:
        digit = get_first_digit(num)
        if digit is not None:
            first_digits.append(digit)

    if len(first_digits) < min_samples:
        return None

    # Calcular distribución observada
    digit_counts = Counter(first_digits)
    total_count = len(first_digits)
    observed_dist = {digit: digit_counts.get(digit, 0) / total_count for digit in range(1, 10)}

    # Obtener distribución esperada según Benford
    expected_dist = calculate_benford_expected_distribution()

    # Calcular chi-cuadrado para medir desviación
    chi_squared = 0.0
    for digit in range(1, 10):
        observed = observed_dist[digit]
        expected = expected_dist[digit]

        # Chi-cuadrado: sum((O - E)^2 / E)
        if expected > 0:
            chi_squared += ((observed - expected) ** 2) / expected

    # Umbral crítico chi-cuadrado para 8 grados de libertad (9 dígitos - 1)
    # Nivel de significancia 0.05: 15.51
    # Nivel de significancia 0.01: 20.09
    critical_value_05 = 15.51
    critical_value_01 = 20.09

    if chi_squared > critical_value_05:
        severity = (
            ValidationSeverity.HIGH
            if chi_squared > critical_value_01
            else ValidationSeverity.MEDIUM
        )

        return ValidationIssue(
            code="BENFORD_LAW_VIOLATION",
            severity=severity,
            title="Desviación de la Ley de Benford detectada",
            description=(
                f"Los números analizados ({len(first_digits)} valores) se desvían "
                f"significativamente de la Ley de Benford (χ² = {chi_squared:.2f}, "
                f"umbral crítico = {critical_value_05:.2f}). "
                f"Esto puede indicar manipulación de datos financieros o errores sistemáticos. "
                f"Se recomienda revisar manualmente las cifras."
            ),
            expected_value=None,
            actual_value=chi_squared,
            deviation_percent=None,
            affected_fields=["cifras_contables"],
            evidence=[],
        )

    return None


# =========================================================
# FUNCIÓN PRINCIPAL DE VALIDACIÓN
# =========================================================


def validate_financial_data(
    balance: Optional[BalanceData], pyg: Optional[ProfitLossData]
) -> ValidationResult:
    """
    Ejecuta todas las validaciones sobre los datos financieros.

    Args:
        balance: Datos del balance (opcional)
        pyg: Datos de PyG (opcional)

    Returns:
        ValidationResult con todos los problemas encontrados
    """
    issues = []
    total_checks = 0

    # ========================================
    # 1. VALIDAR ECUACIÓN CONTABLE
    # ========================================
    if balance:
        total_checks += 1
        balance_issue = validate_balance_equation(balance)
        if balance_issue:
            issues.append(balance_issue)

    # ========================================
    # 2. VALIDAR COHERENCIA BALANCE - PYG
    # ========================================
    if balance and pyg:
        total_checks += 1
        coherence_issues = validate_balance_pyg_coherence(balance, pyg)
        issues.extend(coherence_issues)

    # ========================================
    # 3. LEY DE BENFORD
    # ========================================
    if balance:
        total_checks += 1

        # Recopilar todos los valores numéricos del balance
        numbers = []
        if balance.activo_corriente:
            numbers.append(balance.activo_corriente.value)
        if balance.activo_no_corriente:
            numbers.append(balance.activo_no_corriente.value)
        if balance.pasivo_corriente:
            numbers.append(balance.pasivo_corriente.value)
        if balance.pasivo_no_corriente:
            numbers.append(balance.pasivo_no_corriente.value)
        if balance.patrimonio_neto:
            numbers.append(balance.patrimonio_neto.value)

        # Añadir valores de PyG si existen
        if pyg:
            if pyg.ingresos_explotacion:
                numbers.append(pyg.ingresos_explotacion.value)
            if pyg.gastos_explotacion:
                numbers.append(pyg.gastos_explotacion.value)
            if pyg.resultado_ejercicio:
                numbers.append(pyg.resultado_ejercicio.value)

        benford_issue = analyze_benford_law(numbers)
        if benford_issue:
            issues.append(benford_issue)

    # ========================================
    # RESULTADO FINAL
    # ========================================
    passed_checks = total_checks - len(issues)
    is_valid = len(issues) == 0

    # Determinar nivel de confianza basado en problemas encontrados
    if not issues:
        confidence = ConfidenceLevel.HIGH
    elif any(issue.severity == ValidationSeverity.CRITICAL for issue in issues):
        confidence = ConfidenceLevel.LOW
    elif any(issue.severity == ValidationSeverity.HIGH for issue in issues):
        confidence = ConfidenceLevel.MEDIUM
    else:
        confidence = ConfidenceLevel.HIGH

    return ValidationResult(
        is_valid=is_valid,
        total_checks=total_checks,
        passed_checks=passed_checks,
        issues=issues,
        confidence_level=confidence,
    )
