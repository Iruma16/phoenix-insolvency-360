"""
Modelo de Usuario para autenticación y autorización.
"""
from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.sql import func

from app.core.database import Base


class User(Base):
    """
    Modelo de usuario para el sistema.

    Tabla: users
    """

    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)  # UUID o ID único
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, is_admin={self.is_admin})>"
