"""
Extracción estructurada avanzada de tablas en Excel.

FASE B1: ANÁLISIS FINANCIERO PROFUNDO
Objetivo: Extraer tablas de Excel de forma más inteligente para análisis contable.

MEJORAS sobre excel_parser.py básico:
1. Detección automática de rangos de tabla
2. Identificación de encabezados
3. Detección de totales y subtotales
4. Extracción de filas con contexto semántico
5. Soporte para tablas multi-hoja

CASOS DE USO:
- Balances con activo/pasivo en columnas diferentes
- PyG con múltiples ejercicios (comparativa)
- Listados de acreedores con clasificación
- Extractos bancarios con movimientos
"""
from __future__ import annotations

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import re

from openpyxl.worksheet.worksheet import Worksheet


class CellType(str, Enum):
    """Tipo de celda en una tabla."""
    HEADER = "header"         # Encabezado de columna
    SUBHEADER = "subheader"   # Subencabezado
    DATA = "data"             # Dato numérico
    LABEL = "label"           # Etiqueta / descripción
    TOTAL = "total"           # Fila de total
    SUBTOTAL = "subtotal"     # Subtotal parcial
    EMPTY = "empty"           # Celda vacía


@dataclass
class Cell:
    """
    Celda con contexto semántico.
    """
    row: int
    col: int
    value: str
    numeric_value: Optional[float]
    cell_type: CellType
    is_bold: bool = False
    is_italic: bool = False


@dataclass
class TableRange:
    """
    Rango de una tabla detectada en una hoja.
    """
    sheet_name: str
    start_row: int
    end_row: int
    start_col: int
    end_col: int
    header_row: Optional[int] = None
    has_totals: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "sheet": self.sheet_name,
            "rows": (self.start_row, self.end_row),
            "cols": (self.start_col, self.end_col),
            "header_row": self.header_row,
            "has_totals": self.has_totals,
        }


@dataclass
class ExtractedTable:
    """
    Tabla extraída con estructura semántica.
    """
    range_info: TableRange
    headers: List[str]
    rows: List[List[Cell]]
    total_rows: List[List[Cell]]  # Filas de totales separadas
    
    def to_dict(self) -> Dict:
        return {
            "range": self.range_info.to_dict(),
            "headers": self.headers,
            "num_rows": len(self.rows),
            "num_total_rows": len(self.total_rows),
        }


# =========================================================
# DETECCIÓN DE TIPO DE CELDA
# =========================================================

def is_numeric_value(value: str) -> bool:
    """Detecta si un valor es numérico (incluyendo formatos con separadores)."""
    if not value or not isinstance(value, str):
        return False
    
    # Limpiar espacios y símbolos comunes
    cleaned = value.strip().replace(",", "").replace(".", "").replace("€", "").replace("$", "")
    cleaned = re.sub(r'\s+', '', cleaned)
    
    # Verificar si es número (permitir negativos)
    try:
        float(cleaned)
        return True
    except ValueError:
        return False


def is_total_label(value: str) -> bool:
    """Detecta si una etiqueta indica total o subtotal."""
    if not value or not isinstance(value, str):
        return False
    
    value_lower = value.lower().strip()
    
    total_keywords = [
        "total", "suma", "sum", "importe total",
        "total general", "total activo", "total pasivo",
        "resultado", "balance"
    ]
    
    for keyword in total_keywords:
        if keyword in value_lower:
            return True
    
    return False


def is_header_row(row_values: List[str]) -> bool:
    """
    Detecta si una fila es un encabezado.
    
    Criterios:
    - Mayoría de celdas son texto (no números)
    - Contiene palabras clave de headers
    - No contiene muchas celdas vacías consecutivas
    """
    if not row_values or len(row_values) == 0:
        return False
    
    # Filtrar vacías
    non_empty = [v for v in row_values if v and str(v).strip()]
    
    if len(non_empty) < 2:
        return False  # Muy pocas celdas con contenido
    
    # Contar cuántas son numéricas
    numeric_count = sum(1 for v in non_empty if is_numeric_value(str(v)))
    
    # Si más del 70% son números, probablemente no es header
    if numeric_count / len(non_empty) > 0.7:
        return False
    
    # Palabras clave de headers
    header_keywords = [
        "concepto", "descripción", "importe", "saldo",
        "debe", "haber", "ejercicio", "año", "fecha",
        "activo", "pasivo", "patrimonio", "ingresos", "gastos"
    ]
    
    row_text = " ".join(str(v).lower() for v in non_empty)
    
    for keyword in header_keywords:
        if keyword in row_text:
            return True
    
    return False


def classify_cell(value: str, row_context: List[str], position: int) -> CellType:
    """
    Clasifica una celda según su contenido y contexto.
    
    Args:
        value: Valor de la celda
        row_context: Valores de toda la fila
        position: Posición en la fila (0-indexed)
        
    Returns:
        CellType clasificado
    """
    if not value or str(value).strip() == "":
        return CellType.EMPTY
    
    value_str = str(value).strip()
    
    # Si es total/subtotal (basado en etiqueta)
    if is_total_label(value_str):
        return CellType.TOTAL
    
    # Si es numérico
    if is_numeric_value(value_str):
        # Verificar si la fila completa es de totales
        if any(is_total_label(str(v)) for v in row_context):
            return CellType.TOTAL
        return CellType.DATA
    
    # Si es texto en primera columna, probablemente es label
    if position == 0 or position == 1:
        return CellType.LABEL
    
    # Por defecto, es label
    return CellType.LABEL


# =========================================================
# DETECCIÓN DE RANGOS DE TABLA
# =========================================================

def detect_table_ranges(sheet: Worksheet) -> List[TableRange]:
    """
    Detecta rangos de tablas en una hoja de Excel.
    
    Una tabla se detecta por:
    - Grupo de filas/columnas contiguas con datos
    - Presencia de header row
    - Filas con estructura consistente
    
    Args:
        sheet: Hoja de Excel (openpyxl Worksheet)
        
    Returns:
        Lista de TableRange detectados
    """
    ranges = []
    
    # Obtener dimensiones de la hoja
    max_row = sheet.max_row
    max_col = sheet.max_column
    
    if max_row == 0 or max_col == 0:
        return ranges
    
    # Por ahora, detectamos una tabla simple: toda la hoja con datos
    # (en el futuro se puede sofisticar para detectar múltiples tablas)
    
    # Buscar primera fila con datos
    start_row = None
    for row_idx in range(1, min(max_row + 1, 100)):  # Buscar en primeras 100 filas
        row_values = [cell.value for cell in sheet[row_idx]]
        non_empty = [v for v in row_values if v is not None and str(v).strip()]
        
        if len(non_empty) >= 2:  # Al menos 2 celdas con contenido
            start_row = row_idx
            break
    
    if start_row is None:
        return ranges  # No hay datos
    
    # Buscar última fila con datos
    end_row = max_row
    for row_idx in range(max_row, max(start_row, max_row - 50), -1):  # Buscar desde el final
        row_values = [cell.value for cell in sheet[row_idx]]
        non_empty = [v for v in row_values if v is not None and str(v).strip()]
        
        if len(non_empty) >= 2:
            end_row = row_idx
            break
    
    # Detectar header row (suele ser la primera fila con datos)
    header_row = None
    for row_idx in range(start_row, min(start_row + 5, end_row + 1)):
        row_values = [str(cell.value) if cell.value is not None else "" for cell in sheet[row_idx]]
        if is_header_row(row_values):
            header_row = row_idx
            break
    
    # Detectar si hay totales (última fila suele tener "Total")
    has_totals = False
    if end_row > start_row:
        last_row_values = [str(cell.value) if cell.value is not None else "" for cell in sheet[end_row]]
        has_totals = any(is_total_label(v) for v in last_row_values)
    
    # Crear rango
    table_range = TableRange(
        sheet_name=sheet.title,
        start_row=start_row,
        end_row=end_row,
        start_col=1,
        end_col=max_col,
        header_row=header_row,
        has_totals=has_totals,
    )
    
    ranges.append(table_range)
    
    return ranges


# =========================================================
# EXTRACCIÓN DE TABLA CON CONTEXTO SEMÁNTICO
# =========================================================

def extract_table(sheet: Worksheet, table_range: TableRange) -> ExtractedTable:
    """
    Extrae una tabla con clasificación semántica de celdas.
    
    Args:
        sheet: Hoja de Excel
        table_range: Rango de la tabla
        
    Returns:
        ExtractedTable con estructura semántica
    """
    # Extraer headers
    headers = []
    if table_range.header_row:
        header_cells = sheet[table_range.header_row]
        headers = [
            str(cell.value).strip() if cell.value is not None else ""
            for cell in header_cells[table_range.start_col-1:table_range.end_col]
        ]
    
    # Extraer filas de datos
    data_rows = []
    total_rows = []
    
    start_data_row = (table_range.header_row + 1) if table_range.header_row else table_range.start_row
    
    for row_idx in range(start_data_row, table_range.end_row + 1):
        row_cells = sheet[row_idx]
        
        # Extraer valores de la fila
        row_values = [
            str(cell.value).strip() if cell.value is not None else ""
            for cell in row_cells[table_range.start_col-1:table_range.end_col]
        ]
        
        # Clasificar cada celda
        cells = []
        is_total_row = False
        
        for col_idx, value in enumerate(row_values):
            # Intentar convertir a número
            numeric_value = None
            if is_numeric_value(value):
                try:
                    cleaned = value.replace(",", "").replace("€", "").replace("$", "").strip()
                    numeric_value = float(cleaned)
                except:
                    pass
            
            # Clasificar celda
            cell_type = classify_cell(value, row_values, col_idx)
            
            if cell_type == CellType.TOTAL:
                is_total_row = True
            
            cell = Cell(
                row=row_idx,
                col=table_range.start_col + col_idx,
                value=value,
                numeric_value=numeric_value,
                cell_type=cell_type,
            )
            cells.append(cell)
        
        # Separar filas de datos vs totales
        if is_total_row:
            total_rows.append(cells)
        else:
            # Filtrar filas completamente vacías
            if any(c.cell_type != CellType.EMPTY for c in cells):
                data_rows.append(cells)
    
    return ExtractedTable(
        range_info=table_range,
        headers=headers,
        rows=data_rows,
        total_rows=total_rows,
    )


# =========================================================
# FUNCIÓN PRINCIPAL
# =========================================================

def extract_structured_tables(sheet: Worksheet) -> List[ExtractedTable]:
    """
    Extrae todas las tablas estructuradas de una hoja.
    
    Args:
        sheet: Hoja de Excel (openpyxl Worksheet)
        
    Returns:
        Lista de ExtractedTable con estructura semántica
    """
    # Detectar rangos
    ranges = detect_table_ranges(sheet)
    
    # Extraer cada tabla
    tables = []
    for table_range in ranges:
        table = extract_table(sheet, table_range)
        tables.append(table)
    
    return tables
