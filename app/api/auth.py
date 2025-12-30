"""
Sistema de autenticación JWT para Phoenix Legal.

Roles mínimos: admin, user
Protege endpoints críticos de análisis y descarga.
"""
import os
from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.core.logger import get_logger

logger = get_logger()

# Configuración
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CHANGE_THIS_IN_PRODUCTION_USE_ENV_VAR")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 horas

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security scheme
security = HTTPBearer()


class TokenData(BaseModel):
    """Datos del token JWT."""
    username: str
    role: str


class User(BaseModel):
    """Usuario del sistema."""
    username: str
    role: str  # "admin" o "user"
    disabled: bool = False


class UserInDB(User):
    """Usuario con password hasheado."""
    hashed_password: str


# Base de datos de usuarios en memoria (solo para MVP)
# En producción: usar BD real
USERS_DB = {
    "admin": UserInDB(
        username="admin",
        role="admin",
        hashed_password=pwd_context.hash("admin123"),  # CAMBIAR EN PRODUCCIÓN
        disabled=False
    ),
    "analyst": UserInDB(
        username="analyst",
        role="user",
        hashed_password=pwd_context.hash("analyst123"),  # CAMBIAR EN PRODUCCIÓN
        disabled=False
    ),
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica que el password coincide con el hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hashea un password."""
    return pwd_context.hash(password)


def authenticate_user(username: str, password: str) -> Optional[User]:
    """
    Autentica un usuario.
    
    Args:
        username: Nombre de usuario
        password: Password en texto plano
    
    Returns:
        User si la autenticación es exitosa, None en caso contrario
    """
    user = USERS_DB.get(username)
    if not user:
        logger.warning(f"Intento de login con usuario inexistente", action="auth_failed", username=username)
        return None
    
    if not verify_password(password, user.hashed_password):
        logger.warning(f"Intento de login con password incorrecto", action="auth_failed", username=username)
        return None
    
    if user.disabled:
        logger.warning(f"Intento de login con usuario deshabilitado", action="auth_failed", username=username)
        return None
    
    logger.info(f"Usuario autenticado exitosamente", action="auth_success", username=username, role=user.role)
    return User(username=user.username, role=user.role, disabled=user.disabled)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Crea un token JWT.
    
    Args:
        data: Datos a incluir en el token
        expires_delta: Tiempo de expiración (opcional)
    
    Returns:
        Token JWT como string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return encoded_jwt


def decode_token(token: str) -> TokenData:
    """
    Decodifica y valida un token JWT.
    
    Args:
        token: Token JWT
    
    Returns:
        TokenData con los datos del token
    
    Raises:
        HTTPException: Si el token es inválido
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        
        if username is None or role is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return TokenData(username=username, role=role)
    
    except jwt.ExpiredSignatureError:
        logger.warning("Token expirado", action="auth_token_expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    except jwt.JWTError as e:
        logger.error("Error decodificando token", action="auth_token_error", error=e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No se pudo validar el token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    """
    Dependencia para obtener el usuario actual desde el token.
    
    Args:
        credentials: Credenciales HTTP Bearer
    
    Returns:
        Usuario actual
    
    Raises:
        HTTPException: Si el token es inválido o el usuario no existe
    """
    token = credentials.credentials
    token_data = decode_token(token)
    
    user = USERS_DB.get(token_data.username)
    if user is None:
        logger.warning("Usuario del token no encontrado", action="auth_user_not_found", username=token_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado",
        )
    
    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario deshabilitado",
        )
    
    return User(username=user.username, role=user.role, disabled=user.disabled)


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependencia para obtener el usuario actual activo.
    
    Args:
        current_user: Usuario actual
    
    Returns:
        Usuario actual si está activo
    
    Raises:
        HTTPException: Si el usuario está deshabilitado
    """
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    return current_user


async def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Dependencia para requerir rol admin.
    
    Args:
        current_user: Usuario actual
    
    Returns:
        Usuario si es admin
    
    Raises:
        HTTPException: Si el usuario no es admin
    """
    if current_user.role != "admin":
        logger.warning(
            "Acceso denegado: se requiere rol admin",
            action="auth_forbidden",
            username=current_user.username,
            role=current_user.role
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de administrador",
        )
    return current_user

