from __future__ import annotations

import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.core.config import settings
from app.core.database import get_engine

# =========================================================
# INIT DB
# =========================================================


def main():
    """
    Inicializa la base de datos (ROBUSTO):
    - Alembic es la única fuente de verdad del esquema.
    - Evita colisiones típicas de `Base.metadata.create_all()` vs `alembic upgrade`.
    - En BDs existentes creadas "a mano" (create_all), intenta bootstrap:
      si Alembic falla por "table already exists", hace `stamp` a la revisión
      adecuada y reintenta el upgrade.
    """

    engine = get_engine()

    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini = repo_root / "alembic.ini"
    if not alembic_ini.exists():
        raise RuntimeError(f"No se encuentra alembic.ini en {alembic_ini}")

    cfg = Config(str(alembic_ini))
    # CRÍTICO: usar el mismo URL que el engine ya normalizó (evita dos ficheros sqlite distintos).
    cfg.set_main_option("sqlalchemy.url", str(engine.url))

    # Mapeo mínimo: tabla ya existe => revisión mínima que la define.
    table_to_revision = {
        # CAPA 3/5 (case_central_db_layers)
        "case_record_evidence": "20260130_1500_case_central",
        "templates": "20260130_1500_case_central",
        "case_submissions": "20260130_1500_case_central",
        # CAPA 4 (auditoría canónica)
        "case_record_audit": "20260130_1700_case_record_audit",
        # Cuadro de situación
        "situation_invoices": "20260130_1230_situation",
        "situation_evidence": "20260130_1230_situation",
        "situation_audit_log": "20260130_1230_situation",
    }

    def _detect_best_stamp_revision() -> str | None:
        with engine.connect() as conn:
            tables = set(inspect(conn).get_table_names())
        if "case_record_audit" in tables:
            return "20260130_1700_case_record_audit"
        if "case_record_evidence" in tables:
            return "20260130_1500_case_central"
        if "situation_invoices" in tables:
            return "20260130_1230_situation"
        return None

    def _upgrade_head_with_bootstrap() -> None:
        try:
            command.upgrade(cfg, "head")
            return
        except Exception as e:
            msg = str(e)
            # Caso típico SQLite/create_all: "table X already exists"
            m = re.search(r"table\s+([a-zA-Z0-9_]+)\s+already exists", msg)
            if m:
                table = m.group(1)
                stamp_rev = table_to_revision.get(table) or _detect_best_stamp_revision()
                if stamp_rev:
                    command.stamp(cfg, stamp_rev)
                    command.upgrade(cfg, "head")
                    return
            # Si no podemos bootstrappear con seguridad, propagamos.
            raise

    _upgrade_head_with_bootstrap()

    # Fallback hardening (SQLite dev):
    # If for any reason Alembic didn't create new tables (common with relative sqlite paths / CWD issues),
    # ensure alerts tables exist so the UI doesn't 500.
    if not settings.uses_postgres:
        with engine.connect() as conn:
            tables = set(inspect(conn).get_table_names())
        if "alerts" not in tables or "alert_evidences" not in tables:
            # Create from current ORM definitions (includes latest columns).
            from app.core.database import Base
            # Import referenced tables to satisfy ForeignKey resolution in create_all().
            from app.models.case import Case  # noqa: F401
            from app.models.document import Document  # noqa: F401
            from app.models.alert import Alert  # noqa: F401
            from app.models.alert_evidence import AlertEvidence  # noqa: F401

            Base.metadata.create_all(engine, tables=[Alert.__table__, AlertEvidence.__table__])  # type: ignore[attr-defined]

            # Stamp to head so we don't keep retrying upgrades in dev.
            try:
                command.stamp(cfg, "head")
            except Exception:
                # Best-effort; keep going.
                pass

    # Mostrar tablas reales en DB (no metadata).
    with engine.connect() as conn:
        tables = sorted(inspect(conn).get_table_names())
    print("✅ DB lista (Alembic=fuente de verdad). Tablas detectadas:")
    for t in tables:
        print(f"   - {t}")
    print(f"\n📊 Total tablas: {len(tables)}")


if __name__ == "__main__":
    main()
