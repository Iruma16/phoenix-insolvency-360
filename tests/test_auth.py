"""
Tests para el sistema de autenticación JWT.
"""
import pytest
from datetime import timedelta

from app.api.auth import (
    authenticate_user,
    create_access_token,
    decode_token,
    verify_password,
    get_password_hash,
    TokenData,
)


def test_password_hashing():
    """Test: Hash y verificación de passwords."""
    password = "test_password_123"
    hashed = get_password_hash(password)
    
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong_password", hashed)


def test_authenticate_valid_admin():
    """Test: Autenticación de admin válido."""
    user = authenticate_user("admin", "admin123")
    
    assert user is not None
    assert user.username == "admin"
    assert user.role == "admin"
    assert not user.disabled


def test_authenticate_valid_analyst():
    """Test: Autenticación de analyst válido."""
    user = authenticate_user("analyst", "analyst123")
    
    assert user is not None
    assert user.username == "analyst"
    assert user.role == "user"


def test_authenticate_invalid_username():
    """Test: Autenticación con usuario inexistente."""
    user = authenticate_user("nonexistent", "password")
    
    assert user is None


def test_authenticate_invalid_password():
    """Test: Autenticación con password incorrecto."""
    user = authenticate_user("admin", "wrong_password")
    
    assert user is None


def test_create_access_token():
    """Test: Crear token JWT."""
    data = {"sub": "admin", "role": "admin"}
    token = create_access_token(data)
    
    assert token is not None
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_token_with_expiration():
    """Test: Crear token con expiración custom."""
    data = {"sub": "admin", "role": "admin"}
    expires = timedelta(minutes=10)
    token = create_access_token(data, expires_delta=expires)
    
    assert token is not None


def test_decode_valid_token():
    """Test: Decodificar token válido."""
    data = {"sub": "admin", "role": "admin"}
    token = create_access_token(data)
    
    token_data = decode_token(token)
    
    assert token_data.username == "admin"
    assert token_data.role == "admin"


def test_decode_invalid_token():
    """Test: Decodificar token inválido."""
    from fastapi import HTTPException
    
    with pytest.raises(HTTPException) as exc_info:
        decode_token("invalid_token_xyz")
    
    assert exc_info.value.status_code == 401


def test_token_roundtrip():
    """Test: Crear y decodificar token (roundtrip)."""
    original_data = {"sub": "analyst", "role": "user"}
    token = create_access_token(original_data)
    decoded = decode_token(token)
    
    assert decoded.username == original_data["sub"]
    assert decoded.role == original_data["role"]


def test_different_users_different_tokens():
    """Test: Usuarios diferentes generan tokens diferentes."""
    token1 = create_access_token({"sub": "admin", "role": "admin"})
    token2 = create_access_token({"sub": "analyst", "role": "user"})
    
    assert token1 != token2


def test_token_data_model():
    """Test: Modelo TokenData."""
    token_data = TokenData(username="test", role="user")
    
    assert token_data.username == "test"
    assert token_data.role == "user"

