from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from contextlib import contextmanager

Base = declarative_base()

# Singleton para el engine y session factory
_engine = None
_session_factory = None


def get_database_url() -> str:
    db_url = os.getenv("DATABASE_URL")

    if not db_url:
        raise RuntimeError(
            "DATABASE_URL no está definida en el entorno. "
            "Añádela al archivo .env"
        )

    return db_url


def get_engine():
    """Obtiene el engine de base de datos (singleton)."""
    global _engine

    if _engine is None:
        database_url = get_database_url()

        # Configuración mejorada para SQLite
        connect_args = {}
        if database_url.startswith("sqlite"):
            connect_args = {
                "check_same_thread": False,
                "timeout": 30,
            }

        _engine = create_engine(
            database_url,
            echo=False,
            connect_args=connect_args,
            pool_pre_ping=True,
            poolclass=None,
        )

        # Habilitar WAL mode para SQLite
        if database_url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def set_sqlite_pragma(dbapi_conn, connection_record):
                cursor = dbapi_conn.cursor()
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                    result = cursor.fetchone()
                    if result and result[0].upper() != "WAL":
                        cursor.execute("PRAGMA journal_mode=DELETE")
                    cursor.execute("PRAGMA synchronous=NORMAL")
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.execute("PRAGMA busy_timeout=30000")
                except Exception:
                    pass
                finally:
                    cursor.close()

    return _engine


def get_session_factory():
    """Obtiene el session factory (singleton)."""
    global _session_factory

    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,  # 🔑 CLAVE
        )

    return _session_factory


@contextmanager
def get_session():
    """
    Context manager para obtener una sesión de base de datos.
    Garantiza commit/rollback y cierre correcto.
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# =========================================================
# FASTAPI DEPENDENCY (NUEVO, NO ROMPE NADA)
# =========================================================

def get_db():
    """
    Dependency para FastAPI.
    Proporciona una sesión por request.
    
    NO hace commit automático.
    Ideal para endpoints.
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
