"""
Sistema de autenticación y autorización con JWT.

Para desarrollo: usa X-User-ID header como fallback.
Para producción: usa JWT tokens desde header Authorization: Bearer <token>.
"""
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User as UserModel

# ==============================================================================
# CONFIGURACIÓN JWT
# ==============================================================================

# En producción, usar variables de entorno
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key-CHANGE-IN-PRODUCTION")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 horas

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Security scheme
security = HTTPBearer(auto_error=False)


# ==============================================================================
# MODELOS PYDANTIC
# ==============================================================================


class User(BaseModel):
    """Usuario autenticado (response model)."""

    id: str
    email: str
    is_admin: bool = False
    full_name: Optional[str] = None


class TokenData(BaseModel):
    """Datos extraídos del JWT token."""

    user_id: str
    email: str


# ==============================================================================
# FUNCIONES DE HASHING Y VERIFICACIÓN
# ==============================================================================


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica que una contraseña coincida con su hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Genera hash de una contraseña."""
    return pwd_context.hash(password)


# ==============================================================================
# FUNCIONES JWT
# ==============================================================================


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Crea un JWT token.

    Args:
        data: Datos a incluir en el token (debe contener 'sub' con user_id)
        expires_delta: Tiempo de expiración personalizado

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


def decode_access_token(token: str) -> TokenData:
    """
    Decodifica y valida un JWT token.

    Args:
        token: JWT token como string

    Returns:
        TokenData con user_id y email

    Raises:
        HTTPException: Si el token es inválido o ha expirado
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")

        if user_id is None or email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido: falta user_id o email",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return TokenData(user_id=user_id, email=email)

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token inválido o expirado: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ==============================================================================
# DEPENDENCY: GET CURRENT USER
# ==============================================================================


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_user_id: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """
    Obtiene el usuario autenticado actual.

    Estrategia multi-nivel:
    1. JWT token (producción): Authorization: Bearer <token>
    2. X-User-ID header (desarrollo): X-User-ID: user123
    3. DEFAULT_USER (solo desarrollo local sin auth)

    Args:
        credentials: JWT token desde Authorization header
        x_user_id: User ID desde X-User-ID header (fallback desarrollo)
        db: Sesión de base de datos

    Returns:
        User: Usuario autenticado

    Raises:
        HTTPException 401: Si no hay autenticación válida
    """

    # OPCIÓN 1: JWT Token (producción)
    if credentials and credentials.credentials:
        token_data = decode_access_token(credentials.credentials)

        # Buscar usuario en BD
        user_model = db.query(UserModel).filter(UserModel.id == token_data.user_id).first()

        if not user_model:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no encontrado en base de datos",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user_model.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario desactivado",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Actualizar last_login
        user_model.last_login = datetime.utcnow()
        db.commit()

        return User(
            id=user_model.id,
            email=user_model.email,
            is_admin=user_model.is_admin,
            full_name=user_model.full_name,
        )

    # OPCIÓN 2: X-User-ID header (desarrollo)
    if x_user_id:
        user_model = db.query(UserModel).filter(UserModel.id == x_user_id).first()

        if user_model:
            return User(
                id=user_model.id,
                email=user_model.email,
                is_admin=user_model.is_admin,
                full_name=user_model.full_name,
            )

    # OPCIÓN 3: DEFAULT USER (solo desarrollo sin auth)
    # ⚠️ ELIMINAR EN PRODUCCIÓN
    if os.getenv("ENVIRONMENT", "development") == "development":
        # Buscar o crear usuario por defecto
        default_user = db.query(UserModel).filter(UserModel.email == "dev@phoenix.local").first()

        if not default_user:
            # Crear usuario de desarrollo con contraseña pre-hasheada
            # Hash de "dev-password" = $2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5ND0L1YCK7K7G
            # Esto evita el error de bcrypt al intentar hashear en runtime
            default_user = UserModel(
                id="dev-user-001",
                email="dev@phoenix.local",
                hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5ND0L1YCK7K7G",
                full_name="Usuario Desarrollo",
                is_admin=True,
                is_active=True,
            )
            db.add(default_user)
            db.commit()
            db.refresh(default_user)

        return User(
            id=default_user.id,
            email=default_user.email,
            is_admin=default_user.is_admin,
            full_name=default_user.full_name,
        )

    # Sin autenticación válida
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se proporcionó autenticación válida",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ==============================================================================
# VERIFICACIÓN DE PERMISOS
# ==============================================================================


def check_case_access(user: User, case_user_id: str, case_id: str) -> bool:
    """
    Verifica si un usuario tiene acceso a un caso específico.

    Reglas:
    - Admin: acceso a todo
    - Owner (case.user_id == user.id): acceso
    - Otro: sin acceso

    Args:
        user: Usuario autenticado
        case_user_id: ID del propietario del caso
        case_id: ID del caso

    Returns:
        True si tiene acceso, False si no
    """
    # Admin tiene acceso a todo
    if user.is_admin:
        return True

    # Owner del caso
    if case_user_id == user.id:
        return True

    # Sin acceso
    return False


# ==============================================================================
# FUNCIONES HELPER PARA AUTENTICACIÓN
# ==============================================================================


def authenticate_user(db: Session, email: str, password: str) -> Optional[UserModel]:
    """
    Autentica un usuario con email y contraseña.

    Args:
        db: Sesión de base de datos
        email: Email del usuario
        password: Contraseña en texto plano

    Returns:
        UserModel si las credenciales son válidas, None si no
    """
    user = db.query(UserModel).filter(UserModel.email == email).first()

    if not user:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user
