import sqlite3
from datetime import datetime

DB_NAME = "phoenix.db"

def crear_tablas():
    """
    Crea la estructura de la Base de Datos con controles de calidad profesional.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Tabla FACTURAS (Blindada)
    # - UNIQUE: Impide meter la misma factura dos veces.
    # - raw_text: Guarda el texto original del PDF para trazabilidad forense.
    # - created_at: Auditoría temporal.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_factura TEXT,
            fecha_emision TEXT,
            proveedor TEXT,
            cif_proveedor TEXT,
            base_imponible REAL,
            iva_total REAL,
            total_factura REAL,
            concepto TEXT,
            estado_pago TEXT,
            raw_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(numero_factura, proveedor)
        )
    """)
    
    # ÍNDICE: Acelera las búsquedas
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_factura_prov ON facturas(numero_factura, proveedor)")

    # 2. Tabla CONTABILIDAD
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contabilidad (
            id INTEGER PRIMARY KEY,
            concepto TEXT,
            fecha TEXT,
            importe REAL,
            estado TEXT,
            tipo_deuda TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    print("📚 Base de datos verificada (Estructura Profesional v2).")

def guardar_factura_db(datos_dict, texto_original=""):
    """
    Guarda la factura controlando duplicados.
    Devuelve True si se guardó, False si ya existía.
    """
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO facturas (
                numero_factura, fecha_emision, proveedor, cif_proveedor,
                base_imponible, iva_total, total_factura, concepto, estado_pago, raw_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datos_dict.get("numero_factura"),
            datos_dict.get("fecha_emision"),
            datos_dict.get("proveedor"),
            datos_dict.get("cif_proveedor"),
            datos_dict.get("base_imponible"),
            datos_dict.get("iva_total"),
            datos_dict.get("total_factura"),
            datos_dict.get("concepto"),
            datos_dict.get("estado_pago"),
            texto_original  # Evidencia forense
        ))
        
        conn.commit()
        print(f"💾 Factura {datos_dict.get('numero_factura')} guardada y auditada.")
        return True
        
    except sqlite3.IntegrityError:
        print(f"⚠️ AVISO DE AUDITORÍA: La factura {datos_dict.get('numero_factura')} ya existe. Se ignora.")
        return False
        
    except Exception as e:
        print(f"❌ Error crítico en Base de Datos: {e}")
        return False
        
    finally:
        conn.close()

def guardar_asiento_contable(datos_fila):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO contabilidad (id, concepto, fecha, importe, estado, tipo_deuda)
            VALUES (?, ?, ?, ?, ?, ?)
        """, datos_fila)
        conn.commit()
    finally:
        conn.close()