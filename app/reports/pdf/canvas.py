from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

from .styles import COLOR_GRAY


class NumberedCanvas(canvas.Canvas):
    """
    Canvas con doble pasada para numeración correcta.

    CRÍTICO: ReportLab requiere dos pasadas:
    1. Primera: guardar estados de cada página
    2. Segunda: renderizar con total de páginas conocido
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

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
        Dibuja número de página y marca de agua.
        Solo se llama cuando page_count es conocido.
        """
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(COLOR_GRAY)

        # Número de página (inferior derecha)
        page_number_text = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(A4[0] - 2 * cm, 1.5 * cm, page_number_text)

        # Marca de agua "BORRADOR TÉCNICO" (diagonal centro)
        self.setFont("Helvetica-Bold", 50)
        self.setFillColorRGB(0.9, 0.9, 0.9, alpha=0.3)
        self.translate(A4[0] / 2, A4[1] / 2)
        self.rotate(45)
        self.drawCentredString(0, 0, "BORRADOR TÉCNICO")

        self.restoreState()
