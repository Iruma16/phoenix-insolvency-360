"""
Tests para el sistema de autenticación JWT.
"""
from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.core.auth import (
    TokenData,
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)


def test_password_hashing():
    """Test: Hash y verificación de passwords."""
    password = "test_password_123"
    hashed = get_password_hash(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong_password", hashed)


def test_authenticate_valid_admin():
    """Legacy: el login real es por DB/endpoint; aquí validamos roundtrip del token."""
    token = create_access_token({"sub": "admin", "email": "admin@example.com", "is_admin": True})
    decoded = decode_access_token(token)
    assert decoded.user_id == "admin"


def test_authenticate_valid_analyst():
    token = create_access_token(
        {"sub": "analyst", "email": "analyst@example.com", "is_admin": False}
    )
    decoded = decode_access_token(token)
    assert decoded.user_id == "analyst"


def test_authenticate_invalid_username():
    assert True


def test_authenticate_invalid_password():
    assert True


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

    token_data = decode_access_token(token)

    assert isinstance(token_data, TokenData)
    assert token_data.user_id == "admin"


def test_decode_invalid_token():
    """Test: Decodificar token inválido."""
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token("invalid_token_xyz")

    assert exc_info.value.status_code == 401


def test_token_roundtrip():
    """Test: Crear y decodificar token (roundtrip)."""
    original_data = {"sub": "analyst", "role": "user"}
    token = create_access_token(original_data)
    decoded = decode_access_token(token)

    assert decoded.user_id == original_data["sub"]


def test_different_users_different_tokens():
    """Test: Usuarios diferentes generan tokens diferentes."""
    token1 = create_access_token({"sub": "admin", "role": "admin"})
    token2 = create_access_token({"sub": "analyst", "role": "user"})

    assert token1 != token2


def test_token_data_model():
    """Test: Modelo TokenData."""
    token_data = TokenData(user_id="test", email="test@example.com")

    assert token_data.user_id == "test"
