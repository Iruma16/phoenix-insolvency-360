"""
Sistema de base de datos con soporte para SQLite y PostgreSQL.

Características:
- Pool de conexiones para PostgreSQL
- WAL mode para SQLite
- Migraciones con Alembic
- Singleton pattern para engine
"""
from sqlalchemy import create_engine, event, pool
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager
from typing import Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.core.exceptions import DatabaseException

logger = get_logger()

Base = declarative_base()

# Singleton para el engine y session factory
_engine = None
_session_factory = None


def get_engine():
    """
    Obtiene el engine de base de datos (singleton).
    
    Configuración optimizada según tipo de BD:
    - PostgreSQL: Pool de conexiones con pre-ping
    - SQLite: WAL mode y pragmas optimizados
    
    Returns:
        Engine de SQLAlchemy
    """
    global _engine

    if _engine is None:
        database_url = settings.database_url
        
        logger.info(
            "Initializing database engine",
            action="db_init",
            db_type="postgresql" if settings.uses_postgres else "sqlite"
        )

        # Configuración según tipo de BD
        if settings.uses_postgres:
            # PostgreSQL: Pool de conexiones
            _engine = create_engine(
                database_url,
                echo=settings.debug,
                pool_pre_ping=True,  # Verifica conexiones antes de usarlas
                poolclass=pool.QueuePool,
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_timeout=settings.db_pool_timeout,
                pool_recycle=3600,  # Reciclar conexiones cada hora
                # Opciones de conexión
                connect_args={
                    "connect_timeout": 10,
                    "application_name": "phoenix_legal"
                }
            )
            
            logger.info(
                "PostgreSQL pool configured",
                action="db_pool_config",
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow
            )
        
        else:
            # SQLite: Sin pool, WAL mode
            _engine = create_engine(
                database_url,
                echo=settings.debug,
                connect_args={
                    "check_same_thread": False,
                    "timeout": 30,
                },
                pool_pre_ping=True,
                poolclass=pool.StaticPool,  # Pool estático para SQLite
            )

            # Configurar pragmas de SQLite
            @event.listens_for(_engine, "connect")
            def set_sqlite_pragma(dbapi_conn, connection_record):
                """Optimiza configuración de SQLite."""
                cursor = dbapi_conn.cursor()
                try:
                    # Habilitar WAL mode (Write-Ahead Logging)
                    cursor.execute("PRAGMA journal_mode=WAL")
                    result = cursor.fetchone()
                    if result and result[0].upper() != "WAL":
                        # Si WAL falla, usar DELETE
                        cursor.execute("PRAGMA journal_mode=DELETE")
                    
                    # Optimizaciones
                    cursor.execute("PRAGMA synchronous=NORMAL")  # Balance seguridad/velocidad
                    cursor.execute("PRAGMA foreign_keys=ON")  # Habilitar FKs
                    cursor.execute("PRAGMA busy_timeout=30000")  # Timeout de 30s
                    cursor.execute("PRAGMA cache_size=-64000")  # Cache de 64MB
                    cursor.execute("PRAGMA temp_store=MEMORY")  # Tablas temp en RAM
                    
                except Exception as e:
                    logger.warning(
                        "Could not set SQLite pragmas",
                        action="sqlite_pragma_warning",
                        error=str(e)
                    )
                finally:
                    cursor.close()
            
            logger.info(
                "SQLite configured with WAL mode",
                action="db_sqlite_config"
            )

    return _engine


def get_session_factory():
    """
    Obtiene el session factory (singleton).
    
    Returns:
        Session factory de SQLAlchemy
    """
    global _session_factory

    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,  # Mantener objetos después de commit
        )
        
        logger.info(
            "Session factory created",
            action="db_session_factory"
        )

    return _session_factory


@contextmanager
def get_session():
    """
    Context manager para obtener una sesión de base de datos.
    Garantiza commit/rollback y cierre correcto.
    
    Uso:
        with get_session() as session:
            case = session.query(Case).first()
            # ... operaciones ...
        # Auto-commit al salir del context
    
    Yields:
        Session: Sesión de base de datos
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
        logger.info("Session committed", action="db_session_commit")
    except Exception as e:
        session.rollback()
        logger.error(
            "Session rollback",
            action="db_session_rollback",
            error=e
        )
        raise DatabaseException(
            message="Error en transacción de base de datos",
            details={"original_error": str(e)},
            original_error=e
        )
    finally:
        session.close()


# =========================================================
# FASTAPI DEPENDENCY
# =========================================================

def get_db():
    """
    Dependency para FastAPI.
    Proporciona una sesión por request HTTP.
    
    NO hace commit automático - el endpoint debe hacer commit explícito.
    Esto permite mejor control de transacciones.
    
    Uso en FastAPI:
        @app.post("/cases")
        def create_case(case_data: dict, db: Session = Depends(get_db)):
            case = Case(**case_data)
            db.add(case)
            db.commit()
            return case
    
    Yields:
        Session: Sesión de base de datos
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        logger.error(
            "Request database error",
            action="db_request_error",
            error=e
        )
        raise
    finally:
        db.close()


# =========================================================
# HEALTH CHECK
# =========================================================

def check_database_health() -> dict:
    """
    Verifica la salud de la conexión a base de datos.
    
    Returns:
        Dict con información de salud
    """
    try:
        engine = get_engine()
        
        with engine.connect() as conn:
            # Verificar que podemos ejecutar query
            result = conn.execute("SELECT 1")
            result.fetchone()
        
        # Obtener info del pool (solo PostgreSQL)
        pool_info = {}
        if settings.uses_postgres and hasattr(engine.pool, 'size'):
            pool_info = {
                "pool_size": engine.pool.size(),
                "checked_in": engine.pool.checkedin(),
                "checked_out": engine.pool.checkedout(),
                "overflow": engine.pool.overflow()
            }
        
        return {
            "status": "healthy",
            "database_type": "postgresql" if settings.uses_postgres else "sqlite",
            "pool_info": pool_info
        }
    
    except Exception as e:
        logger.error(
            "Database health check failed",
            action="db_health_check_failed",
            error=e
        )
        return {
            "status": "unhealthy",
            "error": str(e)
        }


# =========================================================
# UTILIDADES
# =========================================================

def reset_engine():
    """
    Resetea el engine (útil para tests).
    
    ADVERTENCIA: Solo usar en tests.
    """
    global _engine, _session_factory
    
    if _engine:
        _engine.dispose()
    
    _engine = None
    _session_factory = None
    
    logger.warning(
        "Database engine reset",
        action="db_engine_reset"
    )
