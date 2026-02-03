"""
Gestión de invalidación en cascada de pares de duplicados.

CRÍTICO: Cuando se elimina/excluye un documento, invalidar pares relacionados.

Escenario típico:
- A ⇄ B (similarity: 0.95)
- B ⇄ C (similarity: 0.92)
- Usuario decide: "eliminar B"
- Resultado: Pares A-B y B-C invalidados automáticamente
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.logger import logger
from app.models.duplicate_audit import create_audit_entry
from app.models.duplicate_pair import DuplicatePair


class CascadeInvalidationResult:
    """Resultado de invalidación en cascada."""

    def __init__(self):
        self.invalidated_pairs: list[str] = []
        self.warnings: list[str] = []
        self.affected_documents: set = set()

    def to_dict(self) -> dict:
        return {
            "invalidated_pairs": self.invalidated_pairs,
            "total_invalidated": len(self.invalidated_pairs),
            "warnings": self.warnings,
            "affected_documents": list(self.affected_documents),
        }


def invalidate_pairs_for_document(
    document_id: str, case_id: str, reason: str, invalidated_by: str, db: Session
) -> CascadeInvalidationResult:
    """
    Invalida TODOS los pares donde participa un documento.

    Escenario:
    - A ⇄ B
    - B ⇄ C
    - Usuario elimina B

    Resultado:
    - Par A-B invalidado
    - Par B-C invalidado
    - Auditoría completa de ambas invalidaciones

    Args:
        document_id: ID del documento excluido/eliminado
        case_id: ID del caso
        reason: Razón de la invalidación
        invalidated_by: Usuario que causa la invalidación
        db: Sesión de base de datos

    Returns:
        CascadeInvalidationResult con pares invalidados y warnings
    """
    result = CascadeInvalidationResult()

    # Buscar todos los pares donde participa este documento
    pairs = (
        db.query(DuplicatePair)
        .filter(
            DuplicatePair.case_id == case_id,
            ((DuplicatePair.doc_a_id == document_id) | (DuplicatePair.doc_b_id == document_id)),
            DuplicatePair.invalidated_at.is_(None),  # Solo pares activos
        )
        .all()
    )

    if not pairs:
        logger.info(f"[CASCADE] No hay pares activos para invalidar del documento {document_id}")
        return result

    logger.warning(
        f"[CASCADE] Invalidando {len(pairs)} par(es) por exclusión de documento {document_id}"
    )

    for pair in pairs:
        # Snapshot antes de invalidar
        state_before = {
            "decision": pair.decision,
            "decision_version": pair.decision_version,
            "decided_by": pair.decided_by,
            "decided_at": pair.decided_at.isoformat() if pair.decided_at else None,
            "decision_reason": pair.decision_reason,
            "invalidated_at": None,
            "invalidation_reason": None,
        }

        # Invalidar el par
        pair.decision = "invalidated_by_cascade"
        pair.invalidated_at = datetime.utcnow()
        pair.invalidation_reason = (
            f"Document {document_id} was excluded/deleted. " f"Original reason: {reason}"
        )
        pair.decision_version += 1  # Incrementar versión

        # Registrar documentos afectados
        result.affected_documents.add(pair.doc_a_id)
        result.affected_documents.add(pair.doc_b_id)

        # Estado después
        state_after = {
            "decision": pair.decision,
            "decision_version": pair.decision_version,
            "decided_by": pair.decided_by,
            "decided_at": pair.decided_at.isoformat() if pair.decided_at else None,
            "decision_reason": pair.decision_reason,
            "invalidated_at": pair.invalidated_at.isoformat(),
            "invalidation_reason": pair.invalidation_reason,
        }

        # Auditoría append-only
        audit_entry = create_audit_entry(
            pair_id=pair.pair_id,
            case_id=case_id,
            state_before=state_before,
            state_after=state_after,
            decided_by=invalidated_by,
            decision="invalidated_by_cascade",
            reason=pair.invalidation_reason,
            pair_version=pair.decision_version,
            ip_address=None,
            user_agent=None,
        )
        db.add(audit_entry)

        result.invalidated_pairs.append(pair.pair_id)

        # Warning si había decisión previa no-pending
        if pair.decision and pair.decision not in ["pending", "invalidated_by_cascade"]:
            result.warnings.append(
                f"⚠️ Par {pair.pair_id} tenía decisión previa '{state_before['decision']}' "
                f"por {state_before['decided_by']}, ahora invalidada"
            )

    # Commit en bloque
    try:
        db.commit()
        logger.info(
            f"[CASCADE] ✅ {len(result.invalidated_pairs)} par(es) invalidados "
            f"por documento {document_id}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"[CASCADE] Error invalidando pares: {e}")
        raise

    return result


def check_transitive_duplicates(
    document_id: str, case_id: str, db: Session
) -> list[tuple[str, str, float]]:
    """
    Detecta duplicados transitivos (A-B, B-C → potencial A-C).

    NO invalida, solo INFORMA para revisión manual.

    Args:
        document_id: ID del documento a analizar
        case_id: ID del caso
        db: Sesión

    Returns:
        Lista de (doc_id_1, doc_id_2, similarity_indirect) para revisión
    """
    # Buscar pares directos activos
    direct_pairs = (
        db.query(DuplicatePair)
        .filter(
            DuplicatePair.case_id == case_id,
            ((DuplicatePair.doc_a_id == document_id) | (DuplicatePair.doc_b_id == document_id)),
            DuplicatePair.invalidated_at.is_(None),
        )
        .all()
    )

    if not direct_pairs:
        return []

    # Obtener documentos conectados
    connected_docs = set()
    for pair in direct_pairs:
        connected_docs.add(pair.doc_a_id)
        connected_docs.add(pair.doc_b_id)

    connected_docs.discard(document_id)

    # Buscar pares entre documentos conectados (transitivos)
    transitive = []
    for doc_1 in connected_docs:
        for doc_2 in connected_docs:
            if doc_1 >= doc_2:  # Evitar duplicados
                continue

            # Verificar si existe par directo activo
            existing_pair = (
                db.query(DuplicatePair)
                .filter(
                    DuplicatePair.case_id == case_id,
                    DuplicatePair.doc_a_id == min(doc_1, doc_2),
                    DuplicatePair.doc_b_id == max(doc_1, doc_2),
                    DuplicatePair.invalidated_at.is_(None),
                )
                .first()
            )

            if not existing_pair:
                # No existe par directo, pero están conectados por document_id
                # → Transitivo potencial para revisión manual
                transitive.append((doc_1, doc_2, 0.0))  # similarity desconocida

    if transitive:
        logger.info(
            f"[TRANSITIVE] Detectados {len(transitive)} par(es) transitivos "
            f"potenciales para documento {document_id}"
        )

    return transitive
