"""
Helpers de auditoría para cumplimiento legal.

Funciones para registrar acciones sensibles en la base de datos.
"""
from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog
import json
import logging

logger = logging.getLogger(__name__)


def log_audit(
    db: Session,
    user_id: str,
    action: str,
    case_id: str = None,
    details: dict = None,
    ip_address: str = None,
    user_agent: str = None,
    commit: bool = True
) -> AuditLog:
    """
    Registra una acción en la auditoría persistente.
    
    Args:
        db: Sesión de base de datos
        user_id: ID del usuario que realizó la acción
        action: Tipo de acción ("financial_analysis", "generate_report", etc.)
        case_id: ID del caso afectado (opcional)
        details: Diccionario con detalles adicionales
        ip_address: IP del cliente
        user_agent: User-Agent del cliente
        commit: Si True, hace commit automáticamente
        
    Returns:
        AuditLog creado
    """
    try:
        audit_entry = AuditLog(
            user_id=user_id,
            case_id=case_id,
            action=action,
            details=json.dumps(details, default=str) if details else None,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        db.add(audit_entry)
        
        if commit:
            db.commit()
            db.refresh(audit_entry)
        
        logger.debug(f"📝 Audit log created: {user_id} - {action} - {case_id}")
        
        return audit_entry
    
    except Exception as e:
        logger.error(f"Error creating audit log: {e}")
        if commit:
            db.rollback()
        # No fallar por error de auditoría
        return None


def log_access(
    db: Session,
    user_id: str,
    resource_type: str,
    resource_id: str,
    ip_address: str = None,
    user_agent: str = None
):
    """
    Registra acceso a un recurso sensible.
    
    Args:
        db: Sesión de base de datos
        user_id: ID del usuario
        resource_type: Tipo de recurso ("case", "document", "analysis", etc.)
        resource_id: ID del recurso
        ip_address: IP del cliente
        user_agent: User-Agent del cliente
    """
    return log_audit(
        db=db,
        user_id=user_id,
        action=f"access_{resource_type}",
        case_id=resource_id if resource_type == "case" else None,
        details={"resource_type": resource_type, "resource_id": resource_id},
        ip_address=ip_address,
        user_agent=user_agent
    )


def log_access_denied(
    db: Session,
    user_id: str,
    resource_type: str,
    resource_id: str,
    reason: str,
    ip_address: str = None,
    user_agent: str = None
):
    """
    Registra intento de acceso denegado (importante para seguridad).
    
    Args:
        db: Sesión de base de datos
        user_id: ID del usuario que intentó acceder
        resource_type: Tipo de recurso
        resource_id: ID del recurso
        reason: Razón del rechazo
        ip_address: IP del cliente
        user_agent: User-Agent del cliente
    """
    return log_audit(
        db=db,
        user_id=user_id,
        action=f"access_denied_{resource_type}",
        case_id=resource_id if resource_type == "case" else None,
        details={
            "resource_type": resource_type,
            "resource_id": resource_id,
            "reason": reason
        },
        ip_address=ip_address,
        user_agent=user_agent
    )
