"""
Hook para políticas de retención legal (PLACEHOLDER).

⚠️ IMPORTANTE - RETENCIÓN LEGAL vs RETENCIÓN TÉCNICA:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DIFERENCIA CRÍTICA:

1) RETENCIÓN TÉCNICA (TTL):
   - Implementada en retention_policy.py
   - Propósito: Limpieza automática de datos no necesarios
   - Configurable por administrador técnico
   - Ejemplo: TTL de 7 días para decision records de desarrollo

2) RETENCIÓN LEGAL (OBLIGATORIA):
   - Este archivo es el HOOK para implementarla
   - Propósito: Cumplimiento de obligaciones legales de conservación
   - Definida por normativa (RGPD, LOPD, normativa sectorial)
   - Ejemplo: Conservar expedientes legales 6 años (mínimo legal)

⚠️ EL TTL TÉCNICO NO SUSTITUYE LA RETENCIÓN LEGAL ⚠️

En producción legal:
- Los Decision Records de casos reales DEBEN conservarse según normativa
- El TTL técnico NO puede borrar datos con obligación legal de conservación
- Debe existir una política explícita que controle ambos aspectos

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Este archivo proporciona el PUNTO DE EXTENSIÓN para implementar:
- Reglas de retención por tipo de expediente
- Bloqueo de borrado de casos con retención legal activa
- Auditoría de borrados
- Integración con sistemas de archivo legal

NO implementa reglas reales (dependen del contexto legal específico).
"""
from datetime import datetime
from enum import Enum
from typing import Optional


class LegalRetentionCategory(Enum):
    """
    Categorías de retención legal (PLACEHOLDER).

    En producción, definir según normativa aplicable:
    - Concursal: X años según legislación
    - Fiscal: Y años según normativa tributaria
    - Laboral: Z años según normativa laboral
    - etc.
    """

    DEVELOPMENT = "development"  # Sin retención legal (entorno dev)
    LEGAL_CASE = "legal_case"  # Retención legal estándar
    SENSITIVE_CASE = "sensitive_case"  # Retención extendida
    ARCHIVED = "archived"  # Archivo histórico (retención indefinida)


class LegalRetentionPolicy:
    """
    Política de retención legal (PLACEHOLDER).

    Este es el HOOK donde implementar la lógica real en producción.
    """

    @staticmethod
    def get_minimum_retention_days(category: LegalRetentionCategory) -> Optional[int]:
        """
        Retorna días mínimos de retención legal por categoría.

        Returns:
            int: Días mínimos de conservación obligatoria
            None: Sin retención legal (borrable inmediatamente)

        ⚠️ PLACEHOLDER: Valores de ejemplo, NO son normativa real.
        En producción, consultar con asesoría legal.
        """
        if category == LegalRetentionCategory.DEVELOPMENT:
            return None  # Sin obligación legal en dev

        elif category == LegalRetentionCategory.LEGAL_CASE:
            # PLACEHOLDER: En España, casos legales suelen requerir 5-6 años
            return 365 * 6  # 6 años (EJEMPLO)

        elif category == LegalRetentionCategory.SENSITIVE_CASE:
            # PLACEHOLDER: Casos sensibles pueden requerir más tiempo
            return 365 * 10  # 10 años (EJEMPLO)

        elif category == LegalRetentionCategory.ARCHIVED:
            # Archivo histórico: retención indefinida
            return None  # Infinito

        else:
            # Por defecto, conservador: retener
            return 365 * 6

    @staticmethod
    def can_delete_case(
        case_id: str, case_created_at: datetime, category: LegalRetentionCategory
    ) -> tuple[bool, Optional[str]]:
        """
        Verifica si un caso puede ser borrado legalmente.

        Args:
            case_id: ID del caso
            case_created_at: Fecha de creación del caso
            category: Categoría de retención legal

        Returns:
            (can_delete, reason)
            - can_delete: True si puede borrarse, False si está protegido
            - reason: Explicación (para auditoría)

        ⚠️ PLACEHOLDER: Implementar validación real en producción.
        """
        min_days = LegalRetentionPolicy.get_minimum_retention_days(category)

        if min_days is None:
            # Sin retención legal
            if category == LegalRetentionCategory.ARCHIVED:
                return False, "Caso archivado - retención indefinida"
            else:
                return True, "Sin obligación de retención legal"

        # Calcular antigüedad
        age_days = (datetime.utcnow() - case_created_at).days

        if age_days < min_days:
            return False, f"Retención legal activa ({min_days - age_days} días restantes)"
        else:
            return True, f"Período de retención legal cumplido ({age_days} días)"

    @staticmethod
    def log_deletion_attempt(
        case_id: str, allowed: bool, reason: str, requested_by: Optional[str] = None
    ) -> None:
        """
        Registra intento de borrado para auditoría legal.

        ⚠️ En producción, este log debe ser INMUTABLE y PERSISTENTE.
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "case_id": case_id,
            "operation": "DELETE_ATTEMPT",
            "allowed": allowed,
            "reason": reason,
            "requested_by": requested_by or "system",
        }

        # TODO: En producción, escribir a log de auditoría inmutable
        # Ejemplo: append-only database, WORM storage, etc.
        print(f"[LEGAL_AUDIT] {log_entry}")


# ============================
# EJEMPLO DE INTEGRACIÓN
# ============================


def safe_delete_case_with_legal_check(
    case_id: str,
    case_created_at: datetime,
    category: LegalRetentionCategory,
    requested_by: Optional[str] = None,
) -> bool:
    """
    Ejemplo de borrado seguro con validación legal.

    En producción, integrar este check ANTES de cualquier borrado real.
    """
    can_delete, reason = LegalRetentionPolicy.can_delete_case(case_id, case_created_at, category)

    # Log de auditoría
    LegalRetentionPolicy.log_deletion_attempt(case_id, can_delete, reason, requested_by)

    if not can_delete:
        print(f"[LEGAL_RETENTION] DELETE BLOCKED: case_id={case_id} reason={reason}")
        return False

    # Aquí iría el borrado real (si permitido)
    print(f"[LEGAL_RETENTION] DELETE ALLOWED: case_id={case_id} reason={reason}")
    return True
