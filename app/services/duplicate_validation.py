"""
Validaciones DURAS para gestión de duplicados.

CRÍTICO: Backend es soberano. Frontend NO se confía en sí mismo.
Todas las validaciones de negocio DEBEN estar aquí.
"""
from sqlalchemy.orm import Session

from app.core.exceptions import DocumentValidationError
from app.models.document import Document
from app.models.duplicate_pair import DuplicatePair


class DuplicateValidationError(DocumentValidationError):
    """Error de validación en gestión de duplicados."""

    pass


def validate_duplicate_decision(
    pair: DuplicatePair,
    action: str,
    reason: str,
    user: str,
    db: Session,
    allow_override: bool = False,
) -> None:
    """
    Validaciones DURAS antes de aceptar decisión sobre duplicado.

    CRÍTICO: Backend valida TODO. Frontend solo presenta UI.

    Args:
        pair: Par de duplicados
        action: Acción a tomar
        reason: Razón de la decisión
        user: Usuario que decide
        db: Sesión de BD
        allow_override: Si permite sobrescribir decisión existente

    Raises:
        DuplicateValidationError: Si alguna validación falla
    """
    # 1. Par existe
    if not pair:
        raise DuplicateValidationError("Par de duplicados no encontrado")

    # 2. Par no está eliminado
    if pair.deleted_at:
        raise DuplicateValidationError(
            "No se puede decidir sobre un par eliminado. " "Debe restaurarse primero."
        )

    # 3. Razón obligatoria y suficiente
    if not reason:
        raise DuplicateValidationError("Razón es obligatoria para auditoría legal")

    if len(reason) < 20:
        raise DuplicateValidationError(
            f"Razón debe tener al menos 20 caracteres (actual: {len(reason)}). "
            "Se requiere justificación suficiente para auditoría legal."
        )

    # 4. Usuario identificado
    if not user or len(user) < 3:
        raise DuplicateValidationError("Usuario debe estar identificado correctamente")

    # 5. Acción válida
    valid_actions = ["pending", "keep_both", "mark_duplicate", "exclude_from_analysis"]
    if action not in valid_actions:
        raise DuplicateValidationError(
            f"Acción '{action}' no válida. " f"Debe ser una de: {', '.join(valid_actions)}"
        )

    # 6. Documentos existen y están activos
    doc_a = db.query(Document).filter(Document.document_id == pair.doc_a_id).first()
    doc_b = db.query(Document).filter(Document.document_id == pair.doc_b_id).first()

    if not doc_a or not doc_b:
        raise DuplicateValidationError(
            "Uno de los documentos del par no existe. " "El par puede estar obsoleto."
        )

    # 7. No sobrescribir decisión sin override explícito
    if pair.decision and pair.decision != "pending":
        if not allow_override and "override" not in reason.lower():
            raise DuplicateValidationError(
                f"Este par ya fue resuelto con decisión '{pair.decision}' "
                f"por {pair.decided_by} el {pair.decided_at}. "
                "Para cambiar la decisión, incluye la palabra 'override' en la razón "
                "y justifica por qué se debe modificar."
            )

    # 8. Validaciones específicas por acción
    if action == "exclude_from_analysis":
        # Advertir si el documento está siendo usado en análisis activo
        if doc_a.status == "processed" or doc_b.status == "processed":
            # Esto es warning, no error duro
            # Podría loggear aquí
            pass

    if action == "mark_duplicate":
        # Asegurar que no se marquen como duplicados en cascada
        # (A duplicado de B, B duplicado de C → evitar)
        if doc_a.is_duplicate or doc_b.is_duplicate:
            raise DuplicateValidationError(
                "Uno de los documentos ya está marcado como duplicado de otro. "
                "No se permite duplicación en cascada. "
                "Revise manualmente la situación."
            )


def validate_batch_action(
    pair_ids: list[str], action: str, reason: str, user: str, db: Session
) -> dict:
    """
    Valida batch action ANTES de aplicar.

    Retorna simulación de impacto para confirmación.

    Args:
        pair_ids: Lista de pair_ids a procesar
        action: Acción a aplicar
        reason: Razón común
        user: Usuario
        db: Sesión BD

    Returns:
        Dict con simulación de impacto

    Raises:
        DuplicateValidationError: Si validación general falla
    """
    if not pair_ids:
        raise DuplicateValidationError("Lista de pares vacía")

    if len(pair_ids) > 50:
        raise DuplicateValidationError(
            f"Batch action limitado a 50 pares. " f"Intentando procesar {len(pair_ids)}."
        )

    # Validar razón común
    if not reason or len(reason) < 30:
        raise DuplicateValidationError(
            "Para batch action, razón debe tener al menos 30 caracteres "
            "ya que se aplicará a múltiples documentos."
        )

    # Simular impacto
    simulation = {
        "pairs_total": len(pair_ids),
        "pairs_valid": 0,
        "pairs_invalid": 0,
        "warnings": [],
        "impacts": [],
        "requires_confirmation": False,
    }

    for pair_id in pair_ids:
        pair = db.query(DuplicatePair).filter(DuplicatePair.pair_id == pair_id).first()

        if not pair:
            simulation["pairs_invalid"] += 1
            simulation["warnings"].append(f"Par {pair_id[:8]} no encontrado")
            continue

        try:
            # Validar (sin allow_override para batch)
            validate_duplicate_decision(pair, action, reason, user, db, allow_override=False)
            simulation["pairs_valid"] += 1

            # Calcular impacto
            impact = {
                "pair_id": pair_id,
                "doc_a_id": pair.doc_a_id,
                "doc_b_id": pair.doc_b_id,
                "current_decision": pair.decision,
                "new_decision": action,
            }

            # Advertencias específicas
            if pair.decision and pair.decision != "pending":
                simulation["warnings"].append(
                    f"Par {pair_id[:8]} ya tiene decisión '{pair.decision}'"
                )
                simulation["requires_confirmation"] = True

            if action == "exclude_from_analysis":
                simulation["requires_confirmation"] = True
                simulation["warnings"].append("Excluir documentos afectará análisis del caso")

            simulation["impacts"].append(impact)

        except DuplicateValidationError as e:
            simulation["pairs_invalid"] += 1
            simulation["warnings"].append(f"Par {pair_id[:8]}: {str(e)}")

    return simulation


def validate_reason_quality(reason: str) -> dict:
    """
    Valida calidad de la razón proporcionada.

    Retorna feedback sobre calidad para UX.

    Args:
        reason: Razón a validar

    Returns:
        Dict con score y feedback
    """
    score = 0
    feedback = []

    if len(reason) < 20:
        feedback.append("❌ Muy corta (mínimo 20 caracteres)")
    elif len(reason) < 50:
        score += 33
        feedback.append("⚠️ Corta (recomendado >50 caracteres)")
    elif len(reason) < 100:
        score += 66
        feedback.append("✅ Longitud adecuada")
    else:
        score += 100
        feedback.append("✅ Razón detallada")

    # Buscar palabras clave que indican buena justificación
    good_keywords = [
        "porque",
        "ya que",
        "debido a",
        "se debe a",
        "justificación",
        "motivo",
        "razón",
        "documento",
        "duplicado",
        "análisis",
    ]

    has_keywords = any(kw in reason.lower() for kw in good_keywords)
    if has_keywords:
        feedback.append("✅ Incluye justificación razonada")
    else:
        feedback.append("⚠️ Considera añadir más contexto")

    return {"score": score, "feedback": feedback, "is_valid": score >= 33}
