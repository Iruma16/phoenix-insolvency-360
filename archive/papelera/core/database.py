# core/database.py
import sqlite3
import pandas as pd
import hashlib
import os
from datetime import datetime
from typing import Tuple, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "audit_data.db")


def create_connection() -> Optional[sqlite3.Connection]:
    try:
        # check_same_thread=False ayuda con Streamlit (hilos)
        return sqlite3.connect(DB_PATH, check_same_thread=False)
    except Exception as e:
        print(f"❌ Error conectando a DB: {e}")
        return None


def generar_hash_fila(row: pd.Series) -> str:
    raw_str = f"{row.get('Fecha','')}{row.get('Concepto','')}{row.get('Importe','')}"
    return hashlib.md5(str(raw_str).encode("utf-8")).hexdigest()


def insert_contabilidad(df: pd.DataFrame) -> Tuple[int, int]:
    conn = create_connection()
    if conn is None:
        return 0, 0

    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS contabilidad (
                id_hash TEXT PRIMARY KEY,
                Fecha TEXT,
                Concepto TEXT,
                Importe REAL,
                Saldo REAL,
                Categoria TEXT
            )
        """)

        if df is None or df.empty:
            conn.commit()
            return 0, 0

        dfx = df.copy()

        if "id_hash" not in dfx.columns:
            dfx["id_hash"] = dfx.apply(generar_hash_fila, axis=1)

        # Solo columnas conocidas (evita meter basura)
        cols = ["id_hash", "Fecha", "Concepto", "Importe", "Saldo", "Categoria"]
        for c in cols:
            if c not in dfx.columns:
                dfx[c] = None
        dfx = dfx[cols]

        # Conteo antes
        before = pd.read_sql_query("SELECT COUNT(*) AS n FROM contabilidad", conn)["n"].iloc[0]

        # Insert OR IGNORE (dedupe por PK)
        rows = dfx.to_dict(orient="records")
        cur.executemany(
            """
            INSERT OR IGNORE INTO contabilidad (id_hash, Fecha, Concepto, Importe, Saldo, Categoria)
            VALUES (:id_hash, :Fecha, :Concepto, :Importe, :Saldo, :Categoria)
            """,
            rows
        )
        conn.commit()

        after = pd.read_sql_query("SELECT COUNT(*) AS n FROM contabilidad", conn)["n"].iloc[0]
        nuevos = int(after - before)
        duplicados = int(len(dfx) - nuevos)
        return nuevos, duplicados

    except Exception as e:
        print(f"❌ Error SQL Contabilidad: {e}")
        return 0, 0
    finally:
        conn.close()


def cargar_datos_desde_sql() -> Optional[pd.DataFrame]:
    conn = create_connection()
    if conn is None:
        return None
    try:
        return pd.read_sql_query("SELECT * FROM contabilidad", conn)
    except Exception:
        return None
    finally:
        conn.close()


def guardar_texto_pdf(nombre_archivo: str, texto_contenido: str) -> bool:
    conn = create_connection()
    if conn is None:
        return False
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documentos_pdf (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre_archivo TEXT,
                texto_contenido TEXT,
                fecha_subida TEXT
            )
        """)
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            """
            INSERT INTO documentos_pdf (nombre_archivo, texto_contenido, fecha_subida)
            VALUES (?, ?, ?)
            """,
            (nombre_archivo, texto_contenido, fecha_actual)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Error guardando PDF: {e}")
        return False
    finally:
        conn.close()


def recuperar_ultimo_pdf() -> str:
    conn = create_connection()
    if conn is None:
        return ""
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='documentos_pdf';")
        if cur.fetchone() is None:
            return ""

        cur.execute("SELECT texto_contenido FROM documentos_pdf ORDER BY id DESC LIMIT 1;")
        row = cur.fetchone()
        return row[0] if row else ""
    except Exception as e:
        print(f"❌ Error recuperando PDF: {e}")
        return ""
    finally:
        conn.close()
