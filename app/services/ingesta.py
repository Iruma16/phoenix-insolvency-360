from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Union, Tuple
from dataclasses import dataclass

import pdfplumber
import pandas as pd
from docx import Document as DocxDocument
from dotenv import load_dotenv
from openai import OpenAI

# =========================================================
# INICIALIZACIÓN
# =========================================================

print("🟢 [INGESTA] Inicializando módulo de ingesta")
load_dotenv()
client = OpenAI()


# =========================================================
# DATACLASS PARA RESULTADO DE PARSING
# =========================================================

@dataclass
class ParsingResult:
    """
    Resultado del parsing de un documento.
    Incluye texto extraído y metadatos para validación.
    """
    texto: str
    num_paginas: int  # Número de páginas detectadas
    tipo_documento: str  # pdf, docx, txt, etc.
    page_offsets: dict[int, tuple[int, int]] | None = None  # {page_num: (start_char, end_char)}

# =========================================================
# UTILIDADES GENERALES
# =========================================================

def normalizar_fecha(fecha_str: str) -> Optional[str]:
    """
    Intenta convertir múltiples formatos de fecha a YYYY-MM-DD.
    """
    if not fecha_str:
        return None

    formatos = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
    ]

    for fmt in formatos:
        try:
            fecha = datetime.strptime(fecha_str.strip(), fmt).strftime("%Y-%m-%d")
            print(f"✅ [FECHA] Normalizada '{fecha_str}' → '{fecha}'")
            return fecha
        except ValueError:
            continue

    print(f"⚠️ [FECHA] No se pudo normalizar: {fecha_str}")
    return fecha_str


# =========================================================
# INGESTA PDF / TXT
# =========================================================

def leer_pdf(file_stream) -> ParsingResult:
    """
    Lee un archivo PDF y extrae todo el texto.
    Soporta tanto rutas de archivo (string) como streams.
    Retorna ParsingResult con texto y metadatos.
    
    CORRECCIÓN: Calcula page_offsets para trazabilidad de páginas.
    """
    print("📄 [PDF] Inicio lectura de PDF")
    texto_completo = ""
    num_paginas = 0
    page_offsets = {}  # {page_num: (start_char, end_char)}

    try:
        # pdfplumber.open puede manejar tanto rutas como streams
        with pdfplumber.open(file_stream) as pdf:
            num_paginas = len(pdf.pages)
            print(f"📄 [PDF] Número de páginas: {num_paginas}")
            
            current_offset = 0
            for i, page in enumerate(pdf.pages):
                page_num = i + 1  # Páginas comienzan en 1
                page_start = current_offset
                
                text = page.extract_text()
                if text:
                    texto_completo += text + "\n"
                    current_offset += len(text) + 1  # +1 por el \n
                else:
                    print(f"⚠️ [PDF] Página {i+1} sin texto")
                
                page_end = current_offset
                page_offsets[page_num] = (page_start, page_end)

        print(f"✅ [PDF] Texto extraído ({len(texto_completo)} caracteres)")
        print(f"✅ [PDF] Calculados offsets para {len(page_offsets)} páginas")
        
        return ParsingResult(
            texto=texto_completo,
            num_paginas=num_paginas,
            tipo_documento="pdf",
            page_offsets=page_offsets,
        )

    except Exception as e:
        print("❌ [PDF] Error leyendo PDF")
        print(f"❌ [PDF] Detalle: {e}")
        
        return ParsingResult(
            texto="",
            num_paginas=0,
            tipo_documento="pdf",
            page_offsets=None,
        )


def leer_txt(file_stream) -> ParsingResult:
    """
    Lee un archivo TXT.
    Soporta tanto rutas de archivo (string) como streams.
    Retorna ParsingResult con texto y metadatos.
    """
    print("📄 [TXT] Inicio lectura de TXT")
    try:
        # Si es una ruta (string o Path), abrir el archivo
        if isinstance(file_stream, (str, Path)):
            with open(file_stream, "r", encoding="utf-8", errors="ignore") as f:
                texto = f.read()
        else:
            # Si es un stream, leerlo
            content = file_stream.read()
            texto = content.decode("utf-8", errors="ignore") if isinstance(content, bytes) else str(content)
        
        print(f"✅ [TXT] Texto leído ({len(texto)} caracteres)")
        
        return ParsingResult(
            texto=texto,
            num_paginas=1,  # TXT no tiene concepto de páginas
            tipo_documento="txt",
        )
    except Exception as e:
        print("❌ [TXT] Error leyendo TXT")
        print(f"❌ [TXT] Detalle: {e}")
        
        return ParsingResult(
            texto="",
            num_paginas=0,
            tipo_documento="txt",
        )


def leer_docx(file_stream, is_doc_legacy: bool = False) -> ParsingResult:
    """
    Lee un archivo DOCX y extrae todo el texto.
    Soporta tanto rutas de archivo (string) como streams.
    Retorna ParsingResult con texto y metadatos.
    
    Parámetros
    ----------
    file_stream : str, Path, o stream
        Archivo DOCX a leer
    is_doc_legacy : bool
        Si True, indica que es un archivo .doc (formato antiguo).
        Se intentará leer pero puede fallar. Se mostrará un warning si falla.
    """
    file_type = "DOC (legacy)" if is_doc_legacy else "DOCX"
    tipo_doc = "doc" if is_doc_legacy else "docx"
    print(f"📄 [{file_type}] Inicio lectura de {file_type}")
    texto_completo = ""
    
    try:
        # Si file_stream es una ruta (string o Path), abrir el archivo
        if isinstance(file_stream, (str, Path)):
            doc = DocxDocument(str(file_stream))
        else:
            # Si es un stream, python-docx lo maneja directamente
            # Pero si es bytes, necesitamos crear un BytesIO
            from io import BytesIO
            if isinstance(file_stream, bytes):
                file_stream = BytesIO(file_stream)
            doc = DocxDocument(file_stream)
        
        # Extraer texto de todos los párrafos
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                texto_completo += paragraph.text + "\n"
        
        # Extraer texto de las tablas
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    texto_completo += row_text + "\n"
        
        if is_doc_legacy and not texto_completo.strip():
            print(f"⚠️  [{file_type}] Archivo .doc leído pero sin contenido. Puede requerir conversión.")
        else:
            print(f"✅ [{file_type}] Texto extraído ({len(texto_completo)} caracteres)")
        
        return ParsingResult(
            texto=texto_completo.strip(),
            num_paginas=1,  # DOCX no tiene concepto de páginas nativo
            tipo_documento=tipo_doc,
        )
    
    except Exception as e:
        if is_doc_legacy:
            print(f"⚠️  [{file_type}] WARNING: No se pudo leer archivo .doc (formato antiguo)")
            print(f"⚠️  [{file_type}] python-docx solo soporta .docx. Considera convertir a .docx con LibreOffice:")
            print(f"⚠️  [{file_type}]   libreoffice --headless --convert-to docx --outdir /tmp archivo.doc")
            print(f"⚠️  [{file_type}] Detalle del error: {e}")
        else:
            print(f"❌ [DOCX] Error leyendo DOCX")
            print(f"❌ [DOCX] Detalle: {e}")
        
        return ParsingResult(
            texto="",
            num_paginas=0,
            tipo_documento=tipo_doc,
        )


# =========================================================
# INGESTA CSV / EXCEL (BANCOS)
# =========================================================

def detectar_columna(columnas_disponibles, posibles_nombres):
    """
    Detecta automáticamente columnas por sinónimos.
    """
    cols_lower = [c.lower() for c in columnas_disponibles]

    for candidato in posibles_nombres:
        if candidato in cols_lower:
            return columnas_disponibles[cols_lower.index(candidato)]

    for col in columnas_disponibles:
        for candidato in posibles_nombres:
            if candidato in col.lower():
                return col

    return None


def normalizar_datos_banco(df: pd.DataFrame) -> pd.DataFrame:
    print("🏦 [BANCO] Normalizando datos bancarios")
    df.columns = df.columns.str.strip()
    cols = df.columns.tolist()
    print(f"🏦 [BANCO] Columnas detectadas: {cols}")

    posibles_fechas = ["fecha", "date", "f.valor", "f.operacion", "día", "dia", "time"]
    posibles_conceptos = ["concepto", "descripcion", "detalle", "movimiento", "asunto", "transaccion", "transaction", "leyenda"]
    posibles_importes = ["importe", "amount", "cantidad", "saldo", "euros", "valor", "cuantia", "monto"]

    col_fecha = detectar_columna(cols, posibles_fechas)
    col_concepto = detectar_columna(cols, posibles_conceptos)
    col_importe = detectar_columna(cols, posibles_importes)

    print(f"🏦 [BANCO] Mapeo columnas → Fecha:{col_fecha}, Concepto:{col_concepto}, Importe:{col_importe}")

    nuevas_cols = {}
    if col_fecha: nuevas_cols[col_fecha] = "Fecha"
    if col_concepto: nuevas_cols[col_concepto] = "Concepto"
    if col_importe: nuevas_cols[col_importe] = "Importe"

    if nuevas_cols:
        df.rename(columns=nuevas_cols, inplace=True)
        print(f"✅ [BANCO] Columnas renombradas: {nuevas_cols}")
    else:
        print("⚠️ [BANCO] No se pudo mapear automáticamente")

    for c in ["Fecha", "Concepto", "Importe"]:
        if c not in df.columns:
            print(f"⚠️ [BANCO] Columna faltante: {c}, rellenando con None")
            df[c] = None

    if "Fecha" in df.columns:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce", dayfirst=True)

    if "Importe" in df.columns:
        df["Importe"] = (
            df["Importe"]
            .astype(str)
            .str.replace("€", "")
            .str.replace(".", "")
            .str.replace(",", ".")
        )
        df["Importe"] = pd.to_numeric(df["Importe"], errors="coerce").fillna(0)

    print(f"✅ [BANCO] Normalización completada ({len(df)} filas)")
    return df[["Fecha", "Concepto", "Importe"]]


def leer_csv_excel(file_stream, filename: str) -> Optional[pd.DataFrame]:
    print(f"📊 [CSV/EXCEL] Procesando archivo: {filename}")

    try:
        name = filename.lower()

        if name.endswith(".csv"):
            print("📊 [CSV] Detectado CSV")
            df = pd.read_csv(file_stream)
        elif name.endswith((".xls", ".xlsx")):
            print("📊 [EXCEL] Detectado Excel")
            df = pd.read_excel(file_stream)
        else:
            print("⚠️ [CSV/EXCEL] Formato no compatible")
            return None

        print(f"📊 [CSV/EXCEL] DataFrame cargado ({df.shape[0]} filas)")
        return normalizar_datos_banco(df)

    except Exception as e:
        print("❌ [CSV/EXCEL] Error leyendo archivo")
        print(f"❌ [CSV/EXCEL] Detalle: {e}")
        return None


# =========================================================
# FUNCIÓN PÚBLICA ÚNICA (DISPATCHER)
# =========================================================

def ingerir_archivo(
    file_stream,
    filename: str,
) -> Union[ParsingResult, pd.DataFrame, None]:
    """
    Punto único de entrada para ingesta.
    Detecta formato y delega la lectura.
    
    Retorna:
    - ParsingResult para archivos de texto (PDF, TXT, DOCX, DOC)
    - DataFrame para CSV/Excel
    - None si el formato no es soportado
    """

    print("--------------------------------------------------")
    print(f"📥 [INGESTA] Archivo recibido: {filename}")

    name = filename.lower()

    if name.endswith(".pdf"):
        print("📥 [INGESTA] Tipo detectado: PDF")
        return leer_pdf(file_stream)

    if name.endswith(".txt"):
        print("📥 [INGESTA] Tipo detectado: TXT")
        return leer_txt(file_stream)

    if name.endswith(".docx"):
        print("📥 [INGESTA] Tipo detectado: DOCX")
        return leer_docx(file_stream, is_doc_legacy=False)
    
    if name.endswith(".doc"):
        print("📥 [INGESTA] Tipo detectado: DOC (legacy, best effort)")
        # Intentar leer como DOCX (a veces funciona si fue guardado en formato nuevo)
        # Si falla, mostrará warning
        return leer_docx(file_stream, is_doc_legacy=True)

    if name.endswith((".csv", ".xls", ".xlsx")):
        print("📥 [INGESTA] Tipo detectado: CSV/EXCEL")
        return leer_csv_excel(file_stream, filename)

    print(f"⚠️ [INGESTA] Formato no soportado: {filename}")
    return None
