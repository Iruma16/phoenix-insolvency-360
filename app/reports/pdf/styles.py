from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.platypus import TableStyle

# Colores corporativos
COLOR_PRIMARY = HexColor("#1e3a8a")  # Azul oscuro
COLOR_SECONDARY = HexColor("#3b82f6")  # Azul
COLOR_DANGER = HexColor("#dc2626")  # Rojo
COLOR_WARNING = HexColor("#f59e0b")  # Naranja
COLOR_SUCCESS = HexColor("#10b981")  # Verde
COLOR_GRAY = HexColor("#6b7280")  # Gris
COLOR_TABLE_ALT = HexColor("#f3f4f6")  # Gris claro para filas alternadas


def create_professional_table_style() -> TableStyle:
    """Crea estilo profesional para tablas con filas alternadas."""
    return TableStyle(
        [
            # Header
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("TOPPADDING", (0, 0), (-1, 0), 12),
            # Filas alternadas
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_TABLE_ALT]),
            # Bordes
            ("GRID", (0, 0), (-1, -1), 0.5, COLOR_GRAY),
            ("LINEBELOW", (0, 0), (-1, 0), 2, COLOR_PRIMARY),
            # Alineación y padding
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 1), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
            # Fuente de datos
            ("FONTSIZE", (0, 1), (-1, -1), 9),
        ]
    )
