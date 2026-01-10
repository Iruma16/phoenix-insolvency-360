"""
API de autenticación con JWT y base de datos real.

Endpoints:
- POST /auth/login: Autenticación y generación de token
- POST /auth/register: Registro de nuevos usuarios (solo admin)
- GET /auth/me: Información del usuario actual
"""
from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_password_hash,
    User,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.models.user import User as UserModel
from app.core.logger import get_logger

logger = get_logger()

router = APIRouter(prefix="/auth", tags=["Autenticación"])


# ==============================================================================
# MODELOS PYDANTIC
# ==============================================================================

class Token(BaseModel):
    """Response del endpoint de login."""
    access_token: str
    token_type: str
    user: User


class LoginRequest(BaseModel):
    """Request para login con email/password."""
    email: str  # EmailStr requiere email-validator
    password: str


class RegisterRequest(BaseModel):
    """Request para registro de nuevos usuarios."""
    email: str  # EmailStr requiere email-validator
    password: str
    full_name: Optional[str] = None
    is_admin: bool = False


class UserResponse(BaseModel):
    """Response con información de usuario."""
    id: str
    email: str
    full_name: Optional[str]
    is_admin: bool
    is_active: bool
    created_at: str


# ==============================================================================
# ENDPOINTS
# ==============================================================================

@router.post("/login", response_model=Token)
async def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Autentica un usuario y devuelve un JWT token.
    
    Args:
        login_data: Email y contraseña
        db: Sesión de base de datos
        
    Returns:
        Token JWT y datos del usuario
        
    Raises:
        HTTPException 401: Si las credenciales son inválidas
    """
    # Autenticar usuario
    user_model = authenticate_user(db, login_data.email, login_data.password)
    
    if not user_model:
        logger.warning(
            "Intento de login fallido",
            action="auth_failed",
            email=login_data.email
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user_model.is_active:
        logger.warning(
            "Intento de login con usuario desactivado",
            action="auth_failed",
            email=login_data.email,
            user_id=user_model.id
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario desactivado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Crear token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user_model.id,
            "email": user_model.email,
            "is_admin": user_model.is_admin,
        },
        expires_delta=access_token_expires,
    )
    
    logger.info(
        "Usuario autenticado exitosamente",
        action="auth_success",
        user_id=user_model.id,
        email=user_model.email
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=User(
            id=user_model.id,
            email=user_model.email,
            is_admin=user_model.is_admin,
            full_name=user_model.full_name,
        ),
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    register_data: RegisterRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Registra un nuevo usuario (solo admin).
    
    Args:
        register_data: Datos del nuevo usuario
        current_user: Usuario actual (debe ser admin)
        db: Sesión de base de datos
        
    Returns:
        Datos del usuario creado
        
    Raises:
        HTTPException 403: Si el usuario actual no es admin
        HTTPException 400: Si el email ya está registrado
    """
    # Verificar permisos de admin
    if not current_user.is_admin:
        logger.warning(
            "Intento de registro sin permisos",
            action="register_forbidden",
            user_id=current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requieren permisos de administrador",
        )
    
    # Verificar que el email no exista
    existing_user = db.query(UserModel).filter(UserModel.email == register_data.email).first()
    if existing_user:
        logger.warning(
            "Intento de registro con email existente",
            action="register_failed",
            email=register_data.email
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya está registrado",
        )
    
    # Crear nuevo usuario
    import uuid
    new_user = UserModel(
        id=str(uuid.uuid4()),
        email=register_data.email,
        hashed_password=get_password_hash(register_data.password),
        full_name=register_data.full_name,
        is_admin=register_data.is_admin,
        is_active=True,
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    logger.info(
        "Usuario registrado exitosamente",
        action="register_success",
        user_id=new_user.id,
        email=new_user.email,
        by_admin=current_user.id
    )
    
    return UserResponse(
        id=new_user.id,
        email=new_user.email,
        full_name=new_user.full_name,
        is_admin=new_user.is_admin,
        is_active=new_user.is_active,
        created_at=new_user.created_at.isoformat(),
    )


@router.get("/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Obtiene información del usuario actual.
    
    Args:
        current_user: Usuario autenticado
        
    Returns:
        Datos del usuario actual
    """
    return current_user


# ==============================================================================
# EXPORTAR ROUTER
# ==============================================================================

__all__ = ["router"]
