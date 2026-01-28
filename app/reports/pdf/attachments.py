from io import BytesIO


def attach_evidence_documents_to_pdf(main_pdf_bytes: bytes, evidence_doc_paths: list[str]) -> bytes:
    """
    Adjunta documentos de evidencia como anexos al PDF principal.

    CRÍTICO: Bookmarks deben apuntar a PÁGINA REAL, no a índice.
    - Calcular offset de páginas acumulado
    - Bookmark con número de página correcto
    - Manejo robusto de errores por anexo

    Args:
        main_pdf_bytes: Contenido del PDF principal
        evidence_doc_paths: Lista de rutas a documentos PDF de evidencia

    Returns:
        bytes: PDF combinado con anexos y bookmarks correctos
    """
    try:
        from pathlib import Path

        from PyPDF2 import PdfMerger, PdfReader

        merger = PdfMerger()

        # Añadir PDF principal
        main_pdf_stream = BytesIO(main_pdf_bytes)
        merger.append(main_pdf_stream)

        # CRÍTICO: Calcular offset de páginas
        try:
            main_reader = PdfReader(main_pdf_stream)
            current_page = len(main_reader.pages)
        except Exception as e:
            print(f"[WARN] No se pudo leer PDF principal para contar páginas: {e}")
            current_page = 0  # Fallback

        # Añadir anexos con tracking de páginas
        successful_annexes = 0
        for _idx, doc_path in enumerate(evidence_doc_paths, 1):
            try:
                doc_path_obj = Path(doc_path)

                # Validar existencia y formato
                if not doc_path_obj.exists():
                    print(f"[WARN] Anexo no existe: {doc_path}")
                    continue

                if not doc_path.lower().endswith(".pdf"):
                    print(f"[WARN] Anexo no es PDF: {doc_path}")
                    continue

                # Leer para contar páginas ANTES de append
                try:
                    annex_reader = PdfReader(doc_path)
                    annex_page_count = len(annex_reader.pages)
                except Exception as e:
                    print(f"[WARN] No se pudo leer anexo {doc_path}: {e}")
                    continue

                # Añadir documento
                merger.append(doc_path)
                successful_annexes += 1

                # CRÍTICO: Bookmark con página REAL
                doc_name = doc_path_obj.stem[:50]  # Limitar nombre
                merger.add_outline_item(
                    f"ANEXO {successful_annexes}: {doc_name}",
                    current_page,  # ✅ Página real, NO idx
                    parent=None,
                )

                # Actualizar contador de páginas
                current_page += annex_page_count

            except Exception as e:
                print(f"[ERROR] No se pudo procesar anexo {doc_path}: {e}")
                continue

        if successful_annexes == 0:
            print("[WARN] No se pudo añadir ningún anexo")

        # Escribir resultado
        output = BytesIO()
        merger.write(output)
        merger.close()
        output.seek(0)

        return output.getvalue()

    except ImportError:
        raise RuntimeError("PyPDF2 no está instalado. Instala con: pip install PyPDF2")
    except Exception as e:
        raise RuntimeError(f"Error adjuntando anexos: {str(e)}")
