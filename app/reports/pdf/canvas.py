from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas
from typing import Optional

from .styles import COLOR_GRAY


class NumberedCanvas(canvas.Canvas):
    """
    Canvas con doble pasada para numeración correcta.

    CRÍTICO: ReportLab requiere dos pasadas:
    1. Primera: guardar estados de cada página
    2. Segunda: renderizar con total de páginas conocido
    """

    def __init__(self, *args, footer_last_page: Optional[str] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self._footer_last_page = footer_last_page

    def showPage(self):
        """Primera pasada: guardar estado sin renderizar número."""
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        """Segunda pasada: renderizar TODAS las páginas con total correcto."""
        num_pages = len(self._saved_page_states)

        for state in self._saved_page_states:
            # Restaurar estado de cada página
            self.__dict__.update(state)
            # Ahora sí sabemos el total
            self.draw_page_number(num_pages)
            # Commit de la página
            super().showPage()

        # Guardar PDF final
        super().save()

    def draw_page_number(self, page_count: int) -> None:
        """
        Dibuja número de página.
        Solo se llama cuando page_count es conocido.
        """
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(COLOR_GRAY)

        # Número de página (inferior derecha)
        page_number_text = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(A4[0] - 2 * cm, 1.5 * cm, page_number_text)

        # Footer solo en última página (inferior izquierda, multilínea)
        if self._footer_last_page and self._pageNumber == page_count:
            self.setFont("Helvetica", 8)
            max_w = A4[0] - (4 * cm)  # márgenes laterales 2cm + 2cm
            lines = simpleSplit(self._footer_last_page, "Helvetica", 8, max_w)
            # Posicionar ligeramente por encima del número de página
            y = 1.25 * cm
            for line in lines[::-1]:
                self.drawString(2 * cm, y, line)
                y += 0.35 * cm

        self.restoreState()
