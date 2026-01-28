"""
Sistema de seguridad para Phoenix Legal.

Incluye:
- Autenticación JWT
- Rate limiting
- Validación de tokens
- Gestión de permisos
"""
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import jwt
from fastapi import HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.exceptions import (
    InvalidTokenException,
    TokenExpiredException,
)
from app.core.logger import get_logger

logger = get_logger()


# =========================================================
# CONFIGURACIÓN DE SEGURIDAD
# =========================================================

# Context para hashing de passwords
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer token security
security = HTTPBearer()

# Rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
    enabled=settings.rate_limit_enabled,
)


# =========================================================
# ROLES Y PERMISOS
# =========================================================


class UserRole(str, Enum):
    """Roles de usuario."""

    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Permission(str, Enum):
    """Permisos del sistema."""

    # Casos
    CASE_CREATE = "case:create"
    CASE_READ = "case:read"
    CASE_UPDATE = "case:update"
    CASE_DELETE = "case:delete"

    # Documentos
    DOCUMENT_UPLOAD = "document:upload"
    DOCUMENT_READ = "document:read"
    DOCUMENT_DELETE = "document:delete"

    # Análisis
    ANALYSIS_RUN = "analysis:run"
    ANALYSIS_READ = "analysis:read"

    # Reportes
    REPORT_GENERATE = "report:generate"
    REPORT_READ = "report:read"

    # Sistema
    SYSTEM_CONFIG = "system:config"
    SYSTEM_ADMIN = "system:admin"


# Mapeo de roles a permisos
ROLE_PERMISSIONS: dict[UserRole, list[Permission]] = {
    UserRole.ADMIN: [p for p in Permission],  # Todos los permisos
    UserRole.ANALYST: [
        Permission.CASE_CREATE,
        Permission.CASE_READ,
        Permission.CASE_UPDATE,
        Permission.DOCUMENT_UPLOAD,
        Permission.DOCUMENT_READ,
        Permission.ANALYSIS_RUN,
        Permission.ANALYSIS_READ,
        Permission.REPORT_GENERATE,
        Permission.REPORT_READ,
    ],
    UserRole.VIEWER: [
        Permission.CASE_READ,
        Permission.DOCUMENT_READ,
        Permission.ANALYSIS_READ,
        Permission.REPORT_READ,
    ],
}


# =========================================================
# GESTIÓN DE PASSWORDS
# =========================================================


def hash_password(password: str) -> str:
    """
    Hashea un password.

    Args:
        password: Password en texto plano

    Returns:
        Hash del password
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica un password contra su hash.

    Args:
        plain_password: Password en texto plano
        hashed_password: Hash del password

    Returns:
        True si coincide
    """
    return pwd_context.verify(plain_password, hashed_password)


# =========================================================
# JWT - CREACIÓN Y VALIDACIÓN
# =========================================================


def create_access_token(
    user_id: str, role: UserRole, expires_delta: Optional[timedelta] = None
) -> str:
    """
    Crea un token JWT de acceso.

    Args:
        user_id: ID del usuario
        role: Rol del usuario
        expires_delta: Tiempo de expiración custom

    Returns:
        Token JWT codificado
    """
    to_encode = {"sub": user_id, "role": role.value, "type": "access"}

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    to_encode["exp"] = expire
    to_encode["iat"] = datetime.utcnow()

    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    logger.info(
        "Access token created",
        action="token_create",
        user_id=user_id,
        role=role.value,
        expires_at=expire.isoformat(),
    )

    return encoded_jwt


def decode_token(token: str) -> dict[str, Any]:
    """
    Decodifica y valida un token JWT.

    Args:
        token: Token JWT

    Returns:
        Payload del token

    Raises:
        InvalidTokenException: Si el token es inválido
        TokenExpiredException: Si el token expiró
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("Expired token", action="token_expired")
        raise TokenExpiredException()

    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token", action="token_invalid", error=str(e))
        raise InvalidTokenException(reason=str(e))


# =========================================================
# DEPENDENCIES PARA FASTAPI
# =========================================================


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict[str, Any]:
    """
    Obtiene el usuario actual desde el token JWT.

    Uso en FastAPI:
        @app.get("/protected")
        async def protected(user = Depends(get_current_user)):
            return {"user_id": user["sub"]}

    Args:
        credentials: Credenciales HTTP Bearer

    Returns:
        Dict con información del usuario

    Raises:
        HTTPException: Si el token es inválido
    """
    try:
        token = credentials.credentials
        payload = decode_token(token)
        return payload

    except (InvalidTokenException, TokenExpiredException) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e.message),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_active_user(
    current_user: dict[str, Any] = Security(get_current_user),
) -> dict[str, Any]:
    """
    Obtiene el usuario actual y verifica que esté activo.

    Args:
        current_user: Usuario actual

    Returns:
        Dict con información del usuario
    """
    # Aquí podrías verificar en BD si el usuario está activo
    # Por ahora, solo retornamos el usuario
    return current_user


def require_permission(required_permission: Permission):
    """
    Dependency factory para requerir permisos específicos.

    Uso:
        @app.post("/cases", dependencies=[Depends(require_permission(Permission.CASE_CREATE))])
        async def create_case():
            # ... código ...

    Args:
        required_permission: Permiso requerido

    Returns:
        Dependency function
    """

    async def permission_checker(current_user: dict[str, Any] = Security(get_current_user)):
        user_role = UserRole(current_user.get("role"))
        user_permissions = ROLE_PERMISSIONS.get(user_role, [])

        if required_permission not in user_permissions:
            logger.warning(
                "Insufficient permissions",
                action="permission_denied",
                user_id=current_user.get("sub"),
                role=user_role.value,
                required_permission=required_permission.value,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permisos insuficientes. Se requiere: {required_permission.value}",
            )

        return current_user

    return permission_checker


def require_role(required_role: UserRole):
    """
    Dependency factory para requerir roles específicos.

    Uso:
        @app.get("/admin", dependencies=[Depends(require_role(UserRole.ADMIN))])
        async def admin_endpoint():
            # ... código ...

    Args:
        required_role: Rol requerido

    Returns:
        Dependency function
    """

    async def role_checker(current_user: dict[str, Any] = Security(get_current_user)):
        user_role = UserRole(current_user.get("role"))

        if user_role != required_role:
            logger.warning(
                "Insufficient role",
                action="role_denied",
                user_id=current_user.get("sub"),
                user_role=user_role.value,
                required_role=required_role.value,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rol insuficiente. Se requiere: {required_role.value}",
            )

        return current_user

    return role_checker


# =========================================================
# RATE LIMITING
# =========================================================


def get_rate_limit_key(request: Request) -> str:
    """
    Genera key para rate limiting.

    Puede ser customizado para usar user_id en vez de IP.

    Args:
        request: Request de FastAPI

    Returns:
        Key única para rate limiting
    """
    # Por defecto, usar IP
    ip = get_remote_address(request)

    # Si hay usuario autenticado, usar su ID
    try:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            payload = decode_token(token)
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
    except:
        pass

    return f"ip:{ip}"


# =========================================================
# HELPERS DE SEGURIDAD
# =========================================================


def check_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Verifica la fortaleza de un password.

    Args:
        password: Password a verificar

    Returns:
        Tuple (es_válido, mensaje_error)
    """
    if len(password) < 8:
        return False, "Password debe tener al menos 8 caracteres"

    if not any(c.isupper() for c in password):
        return False, "Password debe contener al menos una mayúscula"

    if not any(c.islower() for c in password):
        return False, "Password debe contener al menos una minúscula"

    if not any(c.isdigit() for c in password):
        return False, "Password debe contener al menos un número"

    return True, None


def sanitize_user_input(input_str: str, max_length: int = 1000) -> str:
    """
    Sanitiza input del usuario.

    Args:
        input_str: String a sanitizar
        max_length: Longitud máxima permitida

    Returns:
        String sanitizado
    """
    # Truncar
    sanitized = input_str[:max_length]

    # Remover caracteres potencialmente peligrosos
    # (esto es básico, para producción usar una librería robusta)
    dangerous_chars = ["<", ">", "&", "'", '"']
    for char in dangerous_chars:
        sanitized = sanitized.replace(char, "")

    return sanitized.strip()
