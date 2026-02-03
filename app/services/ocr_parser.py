"""
Parser OCR para documentos escaneados (PDFs e imágenes).

FASE 2A: INGESTA MULTI-FORMATO
Objetivo: Extraer texto de documentos escaneados usando Tesseract OCR.

Casos de uso:
- PDFs escaneados (sin capa de texto)
- Avisos de embargo escaneados
- Denuncias judiciales escaneadas
- Facturas en formato imagen

PRINCIPIOS:
- Detectar si documento requiere OCR
- Convertir PDF → imágenes → OCR
- Soportar imágenes directas (.jpg, .png, .tiff)
- Retornar ParsingResult con flag ocr_applied=True
- Fail gracefully si Tesseract no está instalado
"""
from __future__ import annotations

import io
from typing import Optional

try:
    import pytesseract
    from pdf2image import convert_from_bytes
    from PIL import Image

    HAS_OCR_SUPPORT = True
except ImportError:
    HAS_OCR_SUPPORT = False


class OCRResult:
    """
    Resultado del OCR de un documento.
    """

    def __init__(
        self,
        texto: str,
        num_paginas: int,
        page_offsets: Optional[dict[int, tuple[int, int]]] = None,
        confidence: Optional[float] = None,
    ):
        self.texto = texto
        self.num_paginas = num_paginas
        self.page_offsets = page_offsets or {}
        self.confidence = confidence
        self.ocr_applied = True


def is_tesseract_available() -> bool:
    """
    Verifica si Tesseract está instalado y accesible.

    Returns:
        True si Tesseract está disponible
    """
    if not HAS_OCR_SUPPORT:
        return False

    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_image(image: Image.Image, lang: str = "spa") -> str:
    """
    Aplica OCR a una imagen PIL.

    Args:
        image: Imagen PIL
        lang: Idioma para OCR (spa=español, eng=inglés)

    Returns:
        Texto extraído
    """
    if not HAS_OCR_SUPPORT:
        raise RuntimeError("pytesseract no está instalado")

    try:
        # Configuración de Tesseract
        # --psm 3: Segmentación automática de página
        # --oem 3: Motor LSTM (mejor calidad)
        custom_config = r"--psm 3 --oem 3"

        text = pytesseract.image_to_string(image, lang=lang, config=custom_config)

        return text.strip()

    except Exception as e:
        print(f"⚠️ [OCR] Error en OCR de imagen: {e}")
        return ""


def ocr_pdf_from_bytes(pdf_bytes: bytes, lang: str = "spa") -> OCRResult:
    """
    Aplica OCR a un PDF escaneado desde bytes.

    Args:
        pdf_bytes: Bytes del PDF
        lang: Idioma para OCR

    Returns:
        OCRResult con texto extraído
    """
    if not HAS_OCR_SUPPORT:
        print("❌ [OCR] pytesseract/pdf2image no instalados")
        return OCRResult(
            texto="ERROR: OCR no disponible (instalar pytesseract y pdf2image)",
            num_paginas=0,
        )

    if not is_tesseract_available():
        print("❌ [OCR] Tesseract no está instalado en el sistema")
        return OCRResult(
            texto="ERROR: Tesseract no instalado (apt-get install tesseract-ocr tesseract-ocr-spa)",
            num_paginas=0,
        )

    try:
        print("🔍 [OCR] Convirtiendo PDF a imágenes...")

        # Convertir PDF a imágenes (una por página)
        # dpi=300 para buena calidad OCR
        images = convert_from_bytes(pdf_bytes, dpi=300)

        print(f"🔍 [OCR] {len(images)} páginas detectadas")

        # Aplicar OCR a cada página
        texto_completo = ""
        page_offsets = {}

        for i, image in enumerate(images):
            print(f"🔍 [OCR] Procesando página {i+1}/{len(images)}...")

            start_offset = len(texto_completo)

            page_text = ocr_image(image, lang=lang)

            if page_text:
                texto_completo += f"\n--- PÁGINA {i+1} ---\n{page_text}\n"

            end_offset = len(texto_completo)
            page_offsets[i + 1] = (start_offset, end_offset)

        print(f"✅ [OCR] OCR completado: {len(texto_completo)} caracteres extraídos")

        return OCRResult(
            texto=texto_completo,
            num_paginas=len(images),
            page_offsets=page_offsets,
        )

    except Exception as e:
        print(f"❌ [OCR] Error en OCR de PDF: {e}")
        return OCRResult(
            texto=f"ERROR: {str(e)}",
            num_paginas=0,
        )


def ocr_pdf_from_path(pdf_path: str, lang: str = "spa") -> OCRResult:
    """
    Aplica OCR a un PDF escaneado desde ruta de archivo.

    Args:
        pdf_path: Ruta al archivo PDF
        lang: Idioma para OCR

    Returns:
        OCRResult con texto extraído
    """
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    return ocr_pdf_from_bytes(pdf_bytes, lang=lang)


def ocr_image_from_bytes(image_bytes: bytes, lang: str = "spa") -> OCRResult:
    """
    Aplica OCR a una imagen desde bytes.

    Args:
        image_bytes: Bytes de la imagen (.jpg, .png, .tiff)
        lang: Idioma para OCR

    Returns:
        OCRResult con texto extraído
    """
    if not HAS_OCR_SUPPORT:
        print("❌ [OCR] PIL no instalado")
        return OCRResult(
            texto="ERROR: PIL no disponible",
            num_paginas=0,
        )

    if not is_tesseract_available():
        print("❌ [OCR] Tesseract no está instalado")
        return OCRResult(
            texto="ERROR: Tesseract no instalado",
            num_paginas=0,
        )

    try:
        # Abrir imagen con PIL
        image = Image.open(io.BytesIO(image_bytes))

        print(f"🔍 [OCR] Procesando imagen {image.size}...")

        # Aplicar OCR
        texto = ocr_image(image, lang=lang)

        print(f"✅ [OCR] OCR completado: {len(texto)} caracteres extraídos")

        return OCRResult(
            texto=texto,
            num_paginas=1,
            page_offsets={1: (0, len(texto))},
        )

    except Exception as e:
        print(f"❌ [OCR] Error en OCR de imagen: {e}")
        return OCRResult(
            texto=f"ERROR: {str(e)}",
            num_paginas=0,
        )


def ocr_image_from_path(image_path: str, lang: str = "spa") -> OCRResult:
    """
    Aplica OCR a una imagen desde ruta de archivo.

    Args:
        image_path: Ruta al archivo de imagen
        lang: Idioma para OCR

    Returns:
        OCRResult con texto extraído
    """
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    return ocr_image_from_bytes(image_bytes, lang=lang)


def should_apply_ocr_to_pdf(pdf_bytes: bytes, threshold_chars: int = 50) -> bool:
    """
    Determina si un PDF necesita OCR (es escaneado).

    Heurística: Si tiene < threshold_chars por página → es escaneado.

    Args:
        pdf_bytes: Bytes del PDF
        threshold_chars: Umbral de caracteres por página

    Returns:
        True si requiere OCR
    """
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if len(pdf.pages) == 0:
                return False

            # Revisar primeras 3 páginas
            pages_to_check = min(3, len(pdf.pages))
            total_text_length = 0

            for i in range(pages_to_check):
                try:
                    text = pdf.pages[i].extract_text() or ""
                    total_text_length += len(text.strip())
                except Exception:
                    pass

            avg_chars_per_page = total_text_length / pages_to_check if pages_to_check > 0 else 0

            # Si promedio < threshold → es escaneado
            return avg_chars_per_page < threshold_chars

    except Exception as e:
        print(f"⚠️ [OCR] Error verificando si PDF necesita OCR: {e}")
        return False
