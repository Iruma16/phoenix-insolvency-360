# core/init_db.py
import sqlite3
from core.database import DB_PATH

DDL_CONTABILIDAD = """
CREATE TABLE IF NOT EXISTS contabilidad (
    id_hash TEXT PRIMARY KEY,
    Fecha TEXT,
    Concepto TEXT,
    Importe REAL,
    Saldo REAL,
    Categoria TEXT
);
"""

DDL_PDFS = """
CREATE TABLE IF NOT EXISTS documentos_pdf (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_archivo TEXT,
    texto_contenido TEXT,
    fecha_subida TEXT
);
"""

IDX_CONTAB_FECHA = "CREATE INDEX IF NOT EXISTS idx_contabilidad_fecha ON contabilidad(Fecha);"
IDX_CONTAB_CONCEPTO = "CREATE INDEX IF NOT EXISTS idx_contabilidad_concepto ON contabilidad(Concepto);"
IDX_PDFS_FECHA = "CREATE INDEX IF NOT EXISTS idx_pdf_fecha ON documentos_pdf(fecha_subida);"


def init_db() -> None:
    """
    Inicializa el esquema SQLite.
    Idempotente: se puede llamar mil veces sin problema.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(DDL_CONTABILIDAD)
        cur.execute(DDL_PDFS)
        cur.execute(IDX_CONTAB_FECHA)
        cur.execute(IDX_CONTAB_CONCEPTO)
        cur.execute(IDX_PDFS_FECHA)
        conn.commit()
    finally:
        conn.close()
