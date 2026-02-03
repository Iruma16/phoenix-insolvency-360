"""
Alembic migration environment.

Objetivos:
- Configurar Alembic para autogenerate.
- Blindar el caso "BD creada por Base.metadata.create_all()" (SQLite/local) sin
  tabla `alembic_version`: permitir `alembic upgrade head` sin pasos manuales
  (p.ej. `alembic stamp ...`) cuando el esquema ya existe.
"""
from logging.config import fileConfig
from typing import Optional

from sqlalchemy import engine_from_config, inspect, pool, text

from alembic import context

# Importar configuración y modelos
from app.core.config import settings
from app.core.database import Base
import app.models  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

# Override sqlalchemy.url from settings, but ensure SQLite path is resolved consistently.
# IMPORTANT: When DATABASE_URL is sqlite:///./..., the relative path depends on current working directory.
# This can cause Alembic to migrate a different .db than the API is using.
try:
    from app.core.database import get_engine

    config.set_main_option("sqlalchemy.url", str(get_engine().url))
except Exception:
    # Fallback: keep settings.database_url (best effort, e.g. offline mode)
    config.set_main_option("sqlalchemy.url", settings.database_url)


def _detect_best_stamp_revision(tables: set[str]) -> Optional[str]:
    """
    Heurística segura para "bootstrap" cuando existen tablas pero no hay
    `alembic_version` (caso típico: DB creada con create_all).
    """
    # CAPA 4 ya existe → al menos hasta case_record_audit
    if "case_record_audit" in tables:
        return "20260130_1700_case_record_audit"
    # CAPA 3/5 existe → al menos hasta case_central
    if "case_record_evidence" in tables or "templates" in tables or "case_submissions" in tables:
        return "20260130_1500_case_central"
    # Cuadro de situación existe → al menos hasta situation
    if "situation_invoices" in tables:
        return "20260130_1230_situation"
    return None


def _bootstrap_alembic_version_if_needed(connection) -> None:
    """
    Si la BD ya tiene tablas pero no tiene `alembic_version`, creamos la tabla
    y la "stampeamos" a una revisión base razonable para permitir upgrade head.
    """
    # En PostgreSQL (prod), no queremos "adivinar" estado: debe existir historial Alembic.
    if settings.uses_postgres:
        return

    tables = set(inspect(connection).get_table_names())
    if "alembic_version" in tables:
        return

    stamp_rev = _detect_best_stamp_revision(tables)
    if not stamp_rev:
        return

    # Importante: NO intentamos inferir migraciones parciales a nivel columna.
    # Este bootstrap solo pretende resolver el caso estructural create_all vs Alembic.
    with connection.begin():
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version ("
                "version_num VARCHAR(32) NOT NULL, "
                "PRIMARY KEY (version_num)"
                ")"
            )
        )
        # Garantizar valor único (PK) en caso de ejecuciones repetidas.
        connection.execute(text("DELETE FROM alembic_version"))
        connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": stamp_rev})


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Opciones para mejor compatibilidad
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No usar pool en migraciones
    )

    with connectable.connect() as connection:
        # Blindaje: si la BD fue creada con create_all y no tiene alembic_version,
        # la bootstrapeamos para permitir `alembic upgrade head` sin pasos manuales.
        _bootstrap_alembic_version_if_needed(connection)

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Opciones para mejor detección de cambios
            compare_type=True,
            compare_server_default=True,
            # Renderizar SQLAlchemy DDL correctamente
            render_as_batch=True,  # Para SQLite
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

