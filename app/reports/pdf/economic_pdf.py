from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import re

from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.economic_report import EconomicReportBundle

from .canvas import NumberedCanvas
from .styles import COLOR_GRAY, COLOR_PRIMARY


def generate_economic_report_pdf(bundle: EconomicReportBundle, *, audience: str = "internal") -> bytes:
    """
    Genera un PDF “para cliente” desde EconomicReportBundle.

    Nota: el bundle ya contiene datos fríos, alertas, roadmap y (opcional) narrativa LLM.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "EcoTitle",
        parent=styles["Heading1"],
        fontSize=22,
        textColor=COLOR_PRIMARY,
        spaceAfter=24,
        alignment=TA_CENTER,
    )
    heading_style = ParagraphStyle(
        "EcoHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=COLOR_PRIMARY,
        spaceAfter=10,
    )
    small_gray = ParagraphStyle(
        "EcoSmall",
        parent=styles["Normal"],
        fontSize=9,
        textColor=COLOR_GRAY,
    )
    body_style = ParagraphStyle(
        "EcoBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
    )
    cell_style = ParagraphStyle(
        "EcoCell",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
    )

    def _safe(s: object) -> str:
        return ("" if s is None else str(s)).strip()

    def _cap(s: str, max_len: int = 240) -> str:
        s = _safe(s)
        return s if len(s) <= max_len else s[: max_len - 20] + " …[truncado]"

    def _p(text: object, max_len: int = 280) -> Paragraph:
        return Paragraph(_cap(_safe(text), max_len), cell_style)

    def _format_date_human(d: object) -> str:
        """
        Formatear fecha para cliente.
        - Bloquea epoch/default: si año < 2000 -> "Fecha no determinada"
        - ISO / datetime -> dd/mm/yyyy
        """
        if d is None:
            return "Fecha no determinada"
        try:
            if hasattr(d, "date"):
                dd = d.date()  # datetime
            else:
                dd = d  # date o str
            s = str(dd)
            # ISO YYYY-MM-DD...
            if len(s) >= 10 and s[4] == "-" and s[7] == "-":
                yyyy = int(s[0:4])
                mm = int(s[5:7])
                day = int(s[8:10])
                if yyyy < 2000 or yyyy > 2100:
                    return "Fecha no determinada"
                return f"{day:02d}/{mm:02d}/{yyyy:04d}"
        except Exception:
            return "Fecha no determinada"
        return "Fecha no determinada"

    def _format_money_es(amount: object) -> str:
        """
        Formatea importes para cliente (ES): 15.000,00 €.
        """
        try:
            if amount is None:
                return "No consta"
            x = float(amount)
            s = f"{x:,.2f}"  # 15,000.00
            # -> 15.000,00
            s = s.replace(",", "X").replace(".", ",").replace("X", ".")
            return f"{s} €"
        except Exception:
            return "No consta"

    def _format_money_in_text_es(text: str) -> str:
        """
        Convierte importes estilo EN/mixto dentro de un texto a formato ES.
        Ejemplos: "115,000 €" -> "115.000,00 €", "-160,000 €" -> "-160.000,00 €"
        """
        t = _safe(text)
        if not t:
            return t

        def _repl(m: re.Match) -> str:
            raw = (m.group(1) or "").strip()
            # Normalizar a float (admite 115,000 o -160,000)
            sign = 1.0
            if raw.startswith(("-", "−")):
                sign = -1.0
                raw2 = raw[1:]
            elif raw.startswith("+"):
                raw2 = raw[1:]
            else:
                raw2 = raw
            # quitar separadores miles/coma
            raw2 = raw2.replace(" ", "")
            if "," in raw2 and "." in raw2:
                # preferencia: si termina en .dd, formato EN
                if re.search(r"\.\d{2}$", raw2):
                    raw2 = raw2.replace(",", "")
                else:
                    raw2 = raw2.replace(".", "").replace(",", ".")
            elif "," in raw2 and "." not in raw2:
                # puede ser miles (115,000) o decimal (123,45)
                if re.search(r",\d{3}\b", raw2):
                    raw2 = raw2.replace(",", "")
                else:
                    raw2 = raw2.replace(",", ".")
            elif "." in raw2 and "," not in raw2:
                if not re.search(r"\.\d{2}$", raw2):
                    raw2 = raw2.replace(".", "")
            try:
                val = sign * float(raw2)
            except Exception:
                return m.group(0)
            return _format_money_es(val)

        return re.sub(r"(?<!\w)([+\-−]?\d[\d\.,\s]{0,15})\s*€", _repl, t)

    def _event_category(text: str) -> str:
        """
        Categoriza eventos para priorizar hitos jurídicamente relevantes.
        """
        t = _safe(text).lower()
        if any(k in t for k in ["embargo", "apremio", "providencia", "diligencia"]):
            return "ejecucion"
        if any(k in t for k in ["tgss", "seguridad social", "aeat", "hacienda", "agencia estatal"]):
            return "deuda_publica"
        if any(k in t for k in ["demanda", "monitorio", "reclamacion", "reclamación", "requerimiento"]):
            return "reclamacion"
        if "vencimiento" in t or "factura" in t:
            return "vencimiento"
        if any(k in t for k in ["crd-", "contrato", "importe:", "fecha inicio", "préstamo", "prestamo", "crédito", "credito"]):
            return "financiacion"
        if any(k in t for k in ["póliza", "poliza", "prima anual", "seguro", "vigencia"]):
            return "seguro"
        if t.count("|") >= 2:
            return "extracto"
        return "otro"

    def _timeline_hitos(financial_analysis: object) -> list[tuple[str, str]]:
        """
        Devuelve una lista corta y cronológica de hitos (fecha, hecho) aptos para cliente.
        """
        try:
            tl = getattr(financial_analysis, "timeline", None) or []
            # Recoger candidatos (máximo por categoría)
            buckets: dict[str, list[tuple[str, str]]] = {
                "vencimiento": [],
                "reclamacion": [],
                "deuda_publica": [],
                "ejecucion": [],
                "financiacion": [],
            }
            for ev in tl[:200]:
                raw_date = getattr(ev, "date", None) or getattr(ev, "event_date", None)
                raw_desc = getattr(ev, "description", None) or getattr(ev, "event", None) or ""
                if not _is_human_event(raw_desc):
                    continue
                cat = _event_category(raw_desc)
                if cat not in buckets:
                    continue
                d = _format_date_human(raw_date)
                buckets[cat].append((d, _cap(raw_desc, 220)))
            # Elegir los primeros N por categoría, luego ordenar por fecha (dd/mm/yyyy) cuando exista
            picked: list[tuple[str, str]] = []
            for cat in ["vencimiento", "reclamacion", "deuda_publica", "ejecucion", "financiacion"]:
                picked.extend(buckets[cat][:3])

            def _key(item: tuple[str, str]) -> tuple[int, int, int, str]:
                d, _ = item
                if d == "Fecha no determinada":
                    return (9999, 99, 99, d)
                try:
                    dd, mm, yy = d.split("/")
                    return (int(yy), int(mm), int(dd), d)
                except Exception:
                    return (9999, 99, 99, d)

            picked = sorted(list({(a, b) for a, b in picked}), key=_key)
            return picked[:12]
        except Exception:
            return []

    def _timeline_lectura_juridica(financial_analysis: object) -> list[str]:
        """
        Lectura jurídica basada SOLO en hitos detectados.
        No recomienda acciones; describe implicaciones prácticas.
        """
        try:
            tl = getattr(financial_analysis, "timeline", None) or []
            first_dates: dict[str, str] = {}
            seen: set[str] = set()
            for ev in tl[:250]:
                raw_date = getattr(ev, "date", None) or getattr(ev, "event_date", None)
                raw_desc = getattr(ev, "description", None) or getattr(ev, "event", None) or ""
                if not _is_human_event(raw_desc):
                    continue
                cat = _event_category(raw_desc)
                if cat in ("seguro", "extracto", "otro"):
                    continue
                d = _format_date_human(raw_date)
                if cat not in first_dates or (first_dates[cat] == "Fecha no determinada" and d != "Fecha no determinada"):
                    first_dates[cat] = d
                seen.add(cat)

            bullets: list[str] = []
            if "vencimiento" in seen:
                bullets.append(
                    f"Se aprecian vencimientos de facturas/obligaciones exigibles (con referencias desde {first_dates.get('vencimiento','Fecha no determinada')}), lo que es compatible con tensión de tesorería."
                )
            if "reclamacion" in seen:
                bullets.append(
                    f"Constan actuaciones de reclamación/requerimiento (con referencias desde {first_dates.get('reclamacion','Fecha no determinada')}), lo que sugiere escalado del conflicto con acreedores."
                )
            if "deuda_publica" in seen:
                bullets.append(
                    f"Constan referencias a deuda pública (AEAT/TGSS) (desde {first_dates.get('deuda_publica','Fecha no determinada')}), que suele tener especial relevancia por recargos/intereses y tratamiento concursal."
                )
            if "ejecucion" in seen:
                bullets.append(
                    f"Constan referencias a medidas de ejecución/embargo/apremio (desde {first_dates.get('ejecucion','Fecha no determinada')}), con posible impacto directo en la operativa y la disponibilidad de tesorería."
                )
            if "financiacion" in seen:
                bullets.append(
                    f"Se observa presencia de financiación/contratos de crédito (desde {first_dates.get('financiacion','Fecha no determinada')}), lo que incrementa el peso de obligaciones financieras en el corto/medio plazo."
                )

            # cerrar con síntesis prudente, si hay señales
            if bullets:
                bullets.append(
                    "En conjunto, la sucesión de vencimientos, reclamaciones y (en su caso) ejecuciones es compatible con un tránsito de incidencias puntuales a un escenario más estructural, a falta de completar la documentación contable y de tesorería."
                )
            return bullets[:5]
        except Exception:
            return []

    def _timeline_fases(financial_analysis: object) -> list[str]:
        """
        Síntesis por fases, estilo "ejemplo", basada en fechas reales del expediente.
        """
        f_v = _first_date_for_category(financial_analysis, "vencimiento")
        f_r = _first_date_for_category(financial_analysis, "reclamacion")
        f_p = _first_date_for_category(financial_analysis, "deuda_publica")
        f_e = _first_date_for_category(financial_analysis, "ejecucion")

        fases: list[str] = []
        if f_v != "Fecha no determinada":
            fases.append(f"{_phase_from_date(f_v).capitalize()}: comienzan a apreciarse vencimientos de obligaciones/facturas.")
        if f_r != "Fecha no determinada":
            fases.append(f"{_phase_from_date(f_r).capitalize()}: constan reclamaciones/requerimientos (escalado de la situación).")
        if f_p != "Fecha no determinada":
            fases.append(f"{_phase_from_date(f_p).capitalize()}: aparecen referencias a deuda pública (AEAT/TGSS).")
        if f_e != "Fecha no determinada":
            fases.append(f"{_phase_from_date(f_e).capitalize()}: constan referencias a ejecución/embargo/apremio.")

        # Cierre prudente si hay al menos 2 hitos
        if len(fases) >= 2:
            fases.append("Conclusión: el patrón temporal es compatible con un paso de incidencias puntuales a un escenario más estructural, a falta de completar contabilidad y tesorería.")
        return fases[:5]
    def _phase_from_date(d: str) -> str:
        """
        Convierte dd/mm/aaaa en etiqueta de fase (ej. "finales de 2023", "primer semestre de 2024").
        Si no hay fecha, devuelve "fecha no determinada".
        """
        if not d or d == "Fecha no determinada":
            return "fecha no determinada"
        try:
            dd, mm, yy = d.split("/")
            m = int(mm)
            y = int(yy)
            if m <= 6:
                return f"primer semestre de {y}"
            if m <= 9:
                return f"segundo semestre de {y}"
            return f"finales de {y}"
        except Exception:
            return "fecha no determinada"

    def _first_date_for_category(financial_analysis: object, cat: str) -> str:
        """
        Devuelve la primera fecha (dd/mm/aaaa) detectada para una categoría de evento.
        """
        try:
            tl = getattr(financial_analysis, "timeline", None) or []
            for ev in tl[:300]:
                raw_date = getattr(ev, "date", None) or getattr(ev, "event_date", None)
                raw_desc = getattr(ev, "description", None) or getattr(ev, "event", None) or ""
                if not _is_human_event(raw_desc):
                    continue
                if _event_category(raw_desc) != cat:
                    continue
                return _format_date_human(raw_date)
        except Exception:
            pass
        return "Fecha no determinada"

    def _extract_dates_from_text(text: str) -> list[str]:
        """Extrae fechas dd/mm/aaaa presentes en texto (para resumen/timeline)."""
        try:
            return re.findall(r"\b(\d{2}/\d{2}/\d{4})\b", _safe(text))
        except Exception:
            return []

    def _infer_doc_type(doc_type: object, filename: object) -> str:
        """
        Tipología documental legible para cliente.
        Si `doc_type` es genérico (p.ej., "contrato"), inferir por nombre/extensión.
        """
        dt = _safe(doc_type).lower()
        fn = _safe(filename)
        low = fn.lower()

        def _by_name() -> str:
            if any(k in low for k in ["balance", "pyg", "p&g", "cuenta de perdidas", "cuenta de pérdidas", "memoria", "gestion"]):
                return "contabilidad"
            if any(k in low for k in ["factura", "invoice", "f-20"]):
                return "factura"
            if any(k in low for k in ["email", "correo"]) or low.endswith(".msg"):
                return "correo"
            if any(k in low for k in ["embargo", "apremio"]):
                return "embargo"
            if any(k in low for k in ["requerimiento", "notificacion", "notificación", "providencia"]):
                return "requerimiento"
            if any(k in low for k in ["auto_"]):
                return "resolución judicial"
            if any(k in low for k in ["demanda", "monitorio"]):
                return "demanda"
            if any(k in low for k in ["reclamacion", "reclamación"]):
                return "reclamación"
            if any(k in low for k in ["escritura", "estatutos", "acta"]):
                return "societario"
            if any(k in low for k in ["contrato", "credito", "crd-"]):
                return "contrato"
            if low.endswith((".xlsx", ".csv")):
                return "hoja de cálculo"
            return "documento"

        # Si ya es específico, respetarlo.
        if dt and dt not in ("contrato", "documento", "unknown", "otro", "other"):
            return dt
        return _by_name()

    def _doc_purpose(doc_type_label: str, filename: str) -> str:
        """
        Finalidad probatoria orientativa (sin inventar hechos): qué suele acreditar ese documento en el expediente.
        """
        dt = _safe(doc_type_label).lower()
        low = _safe(filename).lower()
        if dt in ("embargo",):
            return "Acredita actuación de apremio/embargo"
        if dt in ("requerimiento", "reclamación", "reclamacion", "demanda", "resolución judicial", "resolucion judicial"):
            return "Acredita reclamación o actuación procesal/administrativa"
        if dt in ("factura",):
            return "Acredita una obligación/facturación (vencimiento y cuantía)"
        if dt in ("contabilidad",):
            return "Acredita situación contable/patrimonial"
        if dt in ("contrato",):
            return "Acredita relación contractual y condiciones del crédito"
        if dt in ("societario",):
            return "Acredita decisiones/estructura societaria"
        if "aeat" in low or "tgss" in low or "seguridad social" in low:
            return "Acredita deuda pública o su estado"
        return "Documento de soporte del expediente"
    def _humanize_signal_desc(desc: str) -> str:
        """
        Normaliza señales para lectura cliente:
        - si la descripción es (o termina siendo) solo un nombre de archivo, expresar que es referencia sin detalle
        """
        d = _safe(desc)
        low = d.lower()
        # Caso 1: la descripción es literalmente un filename
        if low.endswith((".pdf", ".png", ".jpg", ".jpeg", ".txt", ".docx", ".xlsx", ".csv")) and " " not in low:
            return f"Consta referencia documental ({d}). No consta fecha o detalle legible en el extracto."
        # Caso 2: patrón típico "Embargo efectivo: <archivo.pdf>"
        m = re.search(
            r":\s*([A-Za-z0-9][A-Za-z0-9_\-\.]*\.(?:pdf|png|jpg|jpeg|txt|docx|xlsx|csv))\s*$",
            d,
            re.IGNORECASE,
        )
        if m:
            fn = m.group(1)
            prefix = d[: m.start()].strip()
            if prefix:
                return f"{prefix}: consta referencia documental ({fn}). No consta detalle legible en el extracto."
            return f"Consta referencia documental ({fn}). No consta detalle legible en el extracto."
        return d

    def _is_human_event(desc: str) -> bool:
        d = _safe(desc)
        if not d:
            return False
        low = d.lower()
        if low.startswith("metadata:") or "timelineevent" in low or low.startswith("{") or low.startswith("["):
            return False
        # Placeholder/truncados típicos
        if low.startswith("fecha:") and "evento" in low and len(d) < 40:
            return False
        # Evitar serializaciones/tablas crudas y placeholders que degradan la legibilidad en cliente
        if "none" in low:
            return False
        if "fecha concepto" in low or "concepto importe" in low:
            return False
        # Evitar líneas de extracto bancario (se presentan en otras secciones si procede)
        if low.count("|") >= 2:
            return False
        return len(d) >= 8

    def _bucket_label(bucket: object) -> str:
        b = _safe(bucket).lower()
        mapping = {
            "contra_la_masa": "Crédito contra la masa",
            "privilegio_especial": "Crédito con privilegio especial",
            "privilegio_general": "Crédito con privilegio general",
            "ordinario": "Crédito ordinario",
            "subordinado": "Crédito subordinado",
            "no_determinable": "No determinable con la documentación actual",
        }
        return mapping.get(b, "No determinable con la documentación actual")

    def _bucket_payment_explainer(bucket: object) -> tuple[str, str]:
        """
        Mensaje orientativo para cliente:
        - prioridad (quién cobra antes)
        - expectativa prudente de cobro
        """
        b = _safe(bucket).lower()
        if b == "contra_la_masa":
            return (
                "En términos generales, este tipo de crédito se atiende con prioridad frente a los créditos concursales.",
                "Si existe tesorería/masa suficiente, suele tener mejores posibilidades de satisfacción que los créditos concursales.",
            )
        if b == "privilegio_especial":
            return (
                "Este crédito puede quedar vinculado a una garantía concreta (por ejemplo, un bien afecto), lo que condiciona su pago.",
                "La satisfacción depende de la existencia y alcance de la garantía; el resto podría quedar como crédito concursal.",
            )
        if b == "privilegio_general":
            return (
                "Este crédito se sitúa en una posición prioritaria frente a los créditos ordinarios.",
                "Tiene mejores expectativas de cobro que los ordinarios, sin perjuicio de la masa disponible y la calificación definitiva.",
            )
        if b == "subordinado":
            return (
                "Este crédito se sitúa en último lugar dentro de los créditos concursales.",
                "Existe un riesgo alto de que no se satisfaga o se haga de forma muy parcial, salvo que exista masa suficiente tras atender los créditos preferentes.",
            )
        if b == "ordinario":
            return (
                "Este crédito se paga después de los créditos con prioridad (contra la masa y privilegiados), si existe masa suficiente.",
                "Existe riesgo de cobro parcial o de no cobro si la masa resultara insuficiente tras atender los créditos preferentes.",
            )
        return (
            "Con la documentación actual no es posible fijar con seguridad la prioridad de pago de esta deuda.",
            "Hasta completar el expediente (naturaleza, períodos, garantías y estado), no puede estimarse con prudencia su expectativa de cobro.",
        )

    def _doc_risk_hint(line: str) -> str:
        """
        Vincula documentos (faltantes/recomendados) con finalidad práctica y riesgo de ausencia.
        Heurística: no inventa hechos; solo orienta el porqué.
        """
        low = _safe(line).lower()
        if "balance" in low or "pérdidas" in low or "perdidas" in low or "pyg" in low:
            return "— necesario para acreditar situación patrimonial y preparar anexos (inventario/estado financiero) del expediente."
        if "extract" in low or "bancar" in low or "tesorer" in low:
            return "— necesario para acreditar tesorería, cobros/pagos y priorizar obligaciones vencidas."
        if "acreedor" in low or "listado" in low:
            return "— necesario para consolidar la lista de acreedores (importe, vencimiento y contacto) y evitar omisiones."
        if "aeat" in low or "tgss" in low or "seguridad social" in low or "hacienda" in low:
            return "— necesario para concretar deuda pública (importe, períodos y recargos) y planificar su tratamiento."
        if "nómin" in low or "nomina" in low or "trabajador" in low or "seguros sociales" in low:
            return "— necesario para delimitar obligaciones laborales y su impacto en pagos esenciales."
        if "inventario" in low or "bienes" in low or "activos" in low:
            return "— necesario para identificar activos, cargas y su influencia en garantías y liquidación."
        return "— útil para completar evidencias y reforzar la trazabilidad del expediente."

    def _neutralize_option_desc(desc: object) -> str:
        """
        Evita tono de recomendación en opciones.
        Convierte verbos directivos ("Valorar", "Completar", "Identificar") en formulaciones descriptivas.
        """
        d = _safe(desc)
        if not d:
            return "—"
        d = d.strip()
        # Normalizaciones comunes
        d = re.sub(r"^\s*Valorar\s+", "Opción posible: ", d, flags=re.IGNORECASE)
        d = re.sub(r"^\s*Completar\s+documentaci[oó]n\s+de\s+la\s+deuda\s*", "Documentación a recabar: ", d, flags=re.IGNORECASE)
        d = re.sub(r"^\s*Completar\s+", "Documentación a recabar: ", d, flags=re.IGNORECASE)
        d = re.sub(r"^\s*Identificar\s+", "Aclaración necesaria: ", d, flags=re.IGNORECASE)
        d = re.sub(r"^\s*Obtener\s+detalle\s*", "Aclaración necesaria: obtener detalle ", d, flags=re.IGNORECASE)
        # Evitar "se recomienda" por estilo
        d = re.sub(r"\bse\s+recomienda\b", "puede ser útil", d, flags=re.IGNORECASE)
        return d

    def _mk_table(data: list[list[object]], col_widths: list[float]) -> Table:
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3D91")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                    ("TOPPADDING", (0, 0), (-1, 0), 6),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ]
            )
        )
        return t

    story = []

    # =========================
    # PORTADA
    # =========================
    story.append(Spacer(1, 2.5 * cm))
    story.append(Paragraph("<b>INFORME DE SITUACIÓN ECONÓMICA</b>", title_style))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(f"<b>Caso:</b> {bundle.case_name}", styles["Normal"]))
    story.append(Paragraph(f"<b>ID Caso:</b> {bundle.case_id}", styles["Normal"]))
    story.append(
        Paragraph(
            f"<b>Generado:</b> {bundle.generated_at.strftime('%d/%m/%Y %H:%M')} UTC",
            styles["Normal"],
        )
    )
    story.append(Spacer(1, 1.2 * cm))

    # Firma del abogado (si está configurada)
    if bundle.lawyer_signature:
        sig = bundle.lawyer_signature
        sig_lines = [
            f"<b>Abogado responsable:</b> {sig.lawyer_name}",
            f"<b>Nº colegiado:</b> {sig.collegiate_number}",
        ]
        if sig.bar_association:
            sig_lines.append(f"<b>Colegio:</b> {sig.bar_association}")
        if sig.law_firm:
            sig_lines.append(f"<b>Despacho:</b> {sig.law_firm}")
        if sig.office_city:
            sig_lines.append(f"<b>Sede:</b> {sig.office_city}")
        story.append(Paragraph("<br/>".join(sig_lines), body_style))
        story.append(Spacer(1, 0.6 * cm))

    footer_scope_last_page = (
        "Alcance del informe: Documento de trabajo para orientar próximos pasos, elaborado a partir de la "
        "documentación aportada en el expediente y los datos extraídos de la misma. Las conclusiones se "
        "formulan de manera conservadora: cuando un dato no consta o no puede verificarse con evidencia, "
        "se indicará explícitamente."
    )
    # PRD literal: evitar saltos de página innecesarios en modo cliente
    if audience != "client":
        story.append(PageBreak())

    # -------------------------
    # MODO CLIENTE (PRD estricto)
    # -------------------------
    if audience == "client":
        contract = getattr(bundle, "narrative_contract", None)
        apps = list(getattr(contract, "debt_legal_applications", None) or []) if contract else []
        addendum = None
        try:
            addendum = (bundle.legal_synthesis or {}).get("lawyer_addendum")
        except Exception:
            addendum = None

        # 1) RESUMEN EJECUTIVO
        story.append(Paragraph("<b>1. RESUMEN EJECUTIVO</b>", heading_style))
        fin = bundle.financial_analysis
        insolv = getattr(fin, "insolvency", None)
        headline = _safe(getattr(bundle.client_summary, "headline", None) or "")
        # Evitar titulares tipo dashboard. Convertirlo a frase narrativa si viene con prefijo.
        headline = re.sub(r"^\s*Situación\s+económica:\s*", "", headline, flags=re.IGNORECASE).strip()
        if headline.lower() == "requiere actuación inmediata.":
            headline = "La situación exige una actuación inmediata y ordenada."
        overall = _safe(getattr(insolv, "overall_assessment", None) or "") if insolv else ""

        embargo_dates: list[str] = []
        exig_dates: list[str] = []
        if insolv:
            for s in (insolv.signals_impago or [])[:12]:
                embargo_dates.extend(_extract_dates_from_text(_safe(getattr(s, "description", None) or "")))
            for s in (insolv.signals_exigibilidad or [])[:12]:
                exig_dates.extend(_extract_dates_from_text(_safe(getattr(s, "description", None) or "")))

        ratio_liq = None
        ratio_end = None
        try:
            for r in (fin.ratios or [])[:30]:
                name = _safe(getattr(r, "name", None)).lower()
                if "liquidez" in name and ratio_liq is None:
                    ratio_liq = float(getattr(r, "value"))
                if "endeudamiento" in name and ratio_end is None:
                    ratio_end = float(getattr(r, "value"))
        except Exception:
            pass

        story.append(
            Paragraph(
                "Del análisis de la documentación aportada se desprende una situación compatible con insolvencia actual, "
                "caracterizada por tensiones de tesorería y la existencia de obligaciones vencidas, con indicios de escalado (reclamaciones y, en su caso, apremios/embargos).",
                body_style,
            )
        )
        if headline:
            story.append(Spacer(1, 0.12 * cm))
            story.append(Paragraph(_cap(headline, 280), body_style))

        # Relato por fases (sin inventar): usar fechas detectadas en timeline/señales.
        first_venc = _first_date_for_category(fin, "vencimiento")
        first_rec = _first_date_for_category(fin, "reclamacion")
        first_pub = _first_date_for_category(fin, "deuda_publica")
        first_ejec = _first_date_for_category(fin, "ejecucion")

        story.append(Spacer(1, 0.12 * cm))
        pv = _phase_from_date(first_venc)
        pr = _phase_from_date(first_rec)
        pp = _phase_from_date(first_pub)
        pe = _phase_from_date(first_ejec)

        evo_parts: list[str] = []
        if pv != "fecha no determinada":
            evo_parts.append(f"se aprecian vencimientos desde {pv}")
        else:
            evo_parts.append("se aprecian vencimientos (sin fecha verificable en el extracto)")

        if pr != "fecha no determinada":
            evo_parts.append(f"y referencias a reclamaciones/requerimientos desde {pr}")
        else:
            evo_parts.append("y constan referencias a reclamaciones/requerimientos (sin fecha verificable en el extracto)")

        if pp != "fecha no determinada":
            evo_parts.append(f"En paralelo, constan referencias a deuda pública desde {pp}")
        else:
            evo_parts.append("En paralelo, constan referencias a deuda pública (sin fecha verificable en el extracto)")

        if pe != "fecha no determinada":
            evo_parts.append(f"y a medidas de ejecución/embargo desde {pe}")
        else:
            evo_parts.append("y a medidas de ejecución/embargo (sin fecha verificable en el extracto)")

        story.append(Paragraph("Evolución: " + ". ".join(evo_parts) + ".", body_style))

        econ_bits: list[str] = []
        if ratio_liq is not None:
            econ_bits.append(f"ratio de liquidez {ratio_liq:.2f}")
        if ratio_end is not None:
            econ_bits.append(f"ratio de endeudamiento {ratio_end:.2f}")
        if econ_bits:
            story.append(Spacer(1, 0.12 * cm))
            story.append(
                Paragraph(
                    "Los indicadores disponibles refuerzan esta conclusión (" + ", ".join(econ_bits) + "). "
                    "En términos prácticos, esto limita la capacidad de atender obligaciones a corto plazo y aumenta el riesgo de que se intensifiquen reclamaciones, recargos o medidas de apremio.",
                    body_style,
                )
            )

        if overall:
            story.append(Spacer(1, 0.12 * cm))
            story.append(Paragraph(_cap(overall, 300), body_style))

        if apps:
            story.append(Spacer(1, 0.12 * cm))
            story.append(
                Paragraph(
                    "Con esta base, el elemento determinante es ordenar las deudas por acreedor, importe y período (y, en su caso, garantías), "
                    "para aplicar el TRLC deuda por deuda y anticipar el impacto práctico en el orden de pagos y en la operativa.",
                    body_style,
                )
            )

        story.append(Spacer(1, 0.6 * cm))

        # 2) EVOLUCIÓN / LÍNEA TEMPORAL
        story.append(Paragraph("<b>2. EVOLUCIÓN DE LA SITUACIÓN (LÍNEA TEMPORAL)</b>", heading_style))
        tl = fin.timeline or []
        story.append(
            Paragraph(
                "La siguiente cronología recoge hechos relevantes que permiten entender la progresión del expediente. "
                "Cuando un hecho no tiene fecha verificable, se indica como “Fecha no determinada”.",
                small_gray,
            )
        )
        hitos = _timeline_hitos(fin)
        if hitos:
            rows: list[list[object]] = [["Fecha", "Hecho"]]
            for d, desc in hitos:
                rows.append([_p(d, 40), _p(desc, 240)])
            story.append(_mk_table(rows, [3.2 * cm, 14.3 * cm]))
            fases = _timeline_fases(fin)
            if fases:
                story.append(Spacer(1, 0.15 * cm))
                story.append(Paragraph("<b>Síntesis por fases</b>", styles["Normal"]))
                for x in fases:
                    story.append(Paragraph(f"• {_cap(x, 320)}", body_style))
            lectura = _timeline_lectura_juridica(fin)
            if lectura:
                story.append(Spacer(1, 0.15 * cm))
                story.append(Paragraph("<b>Lectura jurídica</b>", styles["Normal"]))
                for x in lectura:
                    story.append(Paragraph(f"• {_cap(x, 320)}", body_style))
        else:
            # fallback: comportamiento anterior
            if tl:
                rows: list[list[object]] = [["Fecha", "Hecho"]]
                added = 0
                for ev in tl[:40]:
                    raw_date = getattr(ev, "date", None) or getattr(ev, "event_date", None)
                    raw_desc = getattr(ev, "description", None) or getattr(ev, "event", None) or ""
                    if not _is_human_event(raw_desc):
                        continue
                    rows.append([_p(_format_date_human(raw_date), 40), _p(raw_desc, 240)])
                    added += 1
                    if added >= 12:
                        break
                if len(rows) > 1:
                    story.append(_mk_table(rows, [3.2 * cm, 14.3 * cm]))
                else:
                    story.append(Paragraph("No constan hechos cronológicos legibles con los datos actuales.", body_style))
            else:
                story.append(Paragraph("No consta línea temporal en el expediente con los datos actuales.", body_style))

        story.append(Spacer(1, 0.6 * cm))

        # 3) INVENTARIO DOCUMENTAL
        story.append(Paragraph("<b>3. INVENTARIO DOCUMENTAL</b>", heading_style))
        story.append(Paragraph("<b>3.1 Documentos aportados (revisados)</b>", styles["Normal"]))
        if bundle.documents_presented:
            counts: dict[str, int] = {}
            first: dict[str, object] = {}
            for d in bundle.documents_presented[:500]:
                fn = _safe(getattr(d, "filename", None) or "—")
                counts[fn] = counts.get(fn, 0) + 1
                if fn not in first:
                    first[fn] = d

            rows: list[list[object]] = [["Tipo", "Documento", "Fecha", "Finalidad"]]
            duplicates = 0
            for fn, d0 in list(first.items())[:25]:
                n = counts.get(fn, 1)
                if n > 1:
                    duplicates += (n - 1)
                    fn_disp = f"{fn} (x{n})"
                else:
                    fn_disp = fn
                doc_type_lbl = _infer_doc_type(getattr(d0, "doc_type", None), fn)
                rows.append(
                    [
                        _p(doc_type_lbl, 32),
                        _p(fn_disp, 140),
                        _p(_format_date_human(getattr(d0, "created_at", None)), 40),
                        _p(_doc_purpose(doc_type_lbl, fn), 48),
                    ]
                )
            story.append(Spacer(1, 0.15 * cm))
            story.append(_mk_table(rows, [2.8 * cm, 8.7 * cm, 2.6 * cm, 3.7 * cm]))
            if duplicates > 0:
                story.append(Spacer(1, 0.1 * cm))
                story.append(
                    Paragraph(
                        "Nota: se han detectado cargas repetidas de uno o varios documentos. La existencia de duplicados no altera "
                        "el fondo del análisis, pero puede ser útil depurar el expediente.",
                        small_gray,
                    )
                )
        else:
            story.append(Paragraph("No consta documentación aportada en el expediente.", body_style))

        story.append(Spacer(1, 0.25 * cm))
        story.append(Paragraph("<b>3.2 Documentos faltantes (críticos)</b>", styles["Normal"]))
        if bundle.documents_missing:
            for x in bundle.documents_missing[:12]:
                story.append(Paragraph(f"• {_cap(x, 220)} {_doc_risk_hint(x)}", body_style))
        else:
            story.append(Paragraph("No se han identificado faltantes críticos con los datos actuales.", body_style))

        story.append(Spacer(1, 0.25 * cm))
        story.append(Paragraph("<b>3.3 Documentación recomendada</b>", styles["Normal"]))
        for x in (bundle.documents_recommended or [])[:12]:
            story.append(Paragraph(f"• {_cap(x, 220)} {_doc_risk_hint(x)}", body_style))

        story.append(Spacer(1, 0.6 * cm))

        # 4) SITUACIÓN ECONÓMICA (RATIOS + INTERPRETACIÓN)
        story.append(Paragraph("<b>4. SITUACIÓN ECONÓMICA (RATIOS + INTERPRETACIÓN)</b>", heading_style))
        story.append(Paragraph(f"<b>Fecha de análisis:</b> {fin.analysis_date.strftime('%d/%m/%Y')}", small_gray))

        if fin.ratios:
            # PRD: evitar “estado” técnico interno en modo cliente
            ratios_rows: list[list[object]] = [["Ratio", "Valor", "Interpretación"]]
            for r in fin.ratios[:10]:
                # Formateo cliente: evitar floats largos / ruido (p.ej., 0.4523809523809524)
                rv = getattr(r, "value", None)
                rv_disp: object = "—"
                if rv is not None:
                    try:
                        rv_disp = f"{float(rv):.2f}"
                    except Exception:
                        rv_disp = rv
                ratios_rows.append(
                    [
                        _p(getattr(r, "name", "") or "—", 80),
                        _p(rv_disp, 24),
                        _p(getattr(r, "interpretation", "") or "—", 200),
                    ]
                )
            story.append(_mk_table(ratios_rows, [5.6 * cm, 2.4 * cm, 9.5 * cm]))
        else:
            story.append(Paragraph("No hay ratios calculables con la documentación actual.", body_style))

        if fin.insolvency:
            story.append(Spacer(1, 0.2 * cm))
            story.append(Paragraph("<b>Señales relevantes</b>", styles["Normal"]))
            story.append(Paragraph(fin.insolvency.overall_assessment, body_style))
            story.append(Spacer(1, 0.1 * cm))
            story.append(Paragraph("<b>Señales decisivas (síntesis)</b>", styles["Normal"]))
            decisivas: list[str] = []
            try:
                # Extraer 1 señal contable y 1 de impago, si existen
                if fin.insolvency.signals_contables:
                    decisivas.append(_format_money_in_text_es(_humanize_signal_desc(_safe(getattr(fin.insolvency.signals_contables[0], "description", "") or ""))))
                if fin.insolvency.signals_impago:
                    decisivas.append(_format_money_in_text_es(_humanize_signal_desc(_safe(getattr(fin.insolvency.signals_impago[0], "description", "") or ""))))
                if fin.insolvency.signals_exigibilidad:
                    decisivas.append(_humanize_signal_desc(_safe(getattr(fin.insolvency.signals_exigibilidad[0], "description", "") or "")))
            except Exception:
                decisivas = decisivas
            for x in decisivas[:3]:
                if x:
                    story.append(Paragraph(f"• {_cap(x, 260)}", body_style))
            signals_rows: list[list[object]] = [["Tipo", "Descripción"]]

            def _iter_signals(label: str, items: list) -> None:
                for s in (items or [])[:4]:
                    desc = _safe(getattr(s, "description", None) or s)
                    if not desc or desc.lower().startswith("metadata:"):
                        continue
                    desc2 = _humanize_signal_desc(_format_money_in_text_es(desc))
                    signals_rows.append([_p(label, 20), _p(desc2, 240)])

            _iter_signals("Impago", fin.insolvency.signals_impago)
            _iter_signals("Contable", fin.insolvency.signals_contables)
            _iter_signals("Exigibilidad", fin.insolvency.signals_exigibilidad)
            if len(signals_rows) > 1:
                story.append(Spacer(1, 0.15 * cm))
                story.append(_mk_table(signals_rows, [3.2 * cm, 14.3 * cm]))
                story.append(Spacer(1, 0.12 * cm))
                story.append(
                    Paragraph(
                        "En conjunto, estos indicadores y señales son compatibles con una insolvencia actual o inminente a efectos prácticos, "
                        "porque reflejan falta de liquidez y obligaciones vencidas. Esto debe guiar una actuación ordenada: completar el expediente, "
                        "priorizar pagos esenciales y evitar decisiones que puedan agravar ejecuciones o recargos.",
                        body_style,
                    )
                )
        else:
            story.append(Paragraph("No hay datos suficientes para evaluar insolvencia con trazabilidad.", body_style))

        story.append(Spacer(1, 0.6 * cm))

        # 5) CLASIFICACIÓN DE LAS DEUDAS Y ORDEN LEGAL DE PAGO (DEUDA POR DEUDA)
        story.append(Paragraph("<b>5. CLASIFICACIÓN DE LAS DEUDAS Y ORDEN LEGAL DE PAGO EN EL CONCURSO</b>", heading_style))
        story.append(
            Paragraph(
                "En un procedimiento concursal, no todas las deudas se tratan por igual. El TRLC establece una clasificación "
                "legal de créditos que determina el orden de pago. La Administración Concursal y, en su caso, el Juzgado, "
                "determinarán la calificación definitiva; lo que sigue es una aplicación prudente basada en lo que consta en el expediente.",
                body_style,
            )
        )
        story.append(Spacer(1, 0.15 * cm))
        story.append(Paragraph("<b>5.0 Regla general del orden de pago (visión de conjunto)</b>", styles["Normal"]))
        story.append(
            Paragraph(
                "A efectos prácticos, la satisfacción de deudas suele seguir un orden por “capas” y depende de la masa disponible. "
                "Esta explicación se formula de manera conservadora: la calificación definitiva puede variar si se aportan documentos (períodos, naturaleza y garantías) "
                "o si el auto fija un régimen particular.",
                body_style,
            )
        )
        for s in [
            "Créditos contra la masa: se atienden con prioridad (gastos y obligaciones nacidas con ocasión del procedimiento).",
            "Créditos con privilegio (general o especial): se sitúan en mejor posición que los ordinarios; el privilegio especial depende de una garantía concreta.",
            "Créditos ordinarios: se atienden después de los anteriores, si existe masa suficiente; existe riesgo de cobro parcial o nulo si la masa es insuficiente.",
            "Créditos subordinados: se sitúan en último lugar; existe un riesgo alto de no cobro salvo masa suficiente tras atender el resto.",
            "Garantías (hipoteca/prenda u otras): pueden desplazar la prioridad práctica sobre un bien concreto; si no consta garantía, no puede afirmarse ese efecto.",
        ]:
            story.append(Paragraph(f"• {_cap(s, 280)}", body_style))
        story.append(Spacer(1, 0.25 * cm))

        # Síntesis por tipo de acreedor (sin inventar): solo con importes conocidos
        if apps:
            totals: dict[str, float] = {}
            counts: dict[str, int] = {}
            unknown_amounts: dict[str, int] = {}
            for d0 in apps[:30]:
                ct = _safe(getattr(d0, "creditor_type", None) or "other").lower()
                amt0 = getattr(d0, "amount_eur", None)
                counts[ct] = counts.get(ct, 0) + 1
                if amt0 is None:
                    unknown_amounts[ct] = unknown_amounts.get(ct, 0) + 1
                    continue
                try:
                    totals[ct] = totals.get(ct, 0.0) + float(amt0)
                except Exception:
                    unknown_amounts[ct] = unknown_amounts.get(ct, 0) + 1
            story.append(Paragraph("<b>Resumen por categorías</b>", styles["Normal"]))
            label_map = {
                "public": "Deuda pública (AEAT/TGSS u otras)",
                "bank": "Financiación/entidades financieras",
                "supplier": "Proveedores y comerciales",
                "employee": "Laboral",
                "landlord": "Arrendamientos",
                "related_party": "Vinculadas",
                "other": "Otras",
            }
            for k in ["public", "bank", "supplier", "employee", "landlord", "related_party", "other"]:
                if k not in counts:
                    continue
                total_txt = _format_money_es(totals.get(k)) if k in totals else "No consta importe total"
                unk = unknown_amounts.get(k, 0)
                extra = f" (con {unk} sin importe)" if unk else ""
                story.append(Paragraph(f"• {label_map.get(k,k)}: {total_txt} en {counts.get(k,0)} deudas{extra}.", body_style))
            story.append(Spacer(1, 0.15 * cm))
        if not apps:
            story.append(Paragraph("No constan deudas clasificables con los datos actuales.", body_style))
        else:
            for d in apps[:10]:
                story.append(Spacer(1, 0.25 * cm))
                story.append(Paragraph(f"<b>{_cap(getattr(d, 'creditor_name', '') or 'Acreedor', 80)}</b>", styles["Normal"]))
                amt = getattr(d, "amount_eur", None)
                amt_txt = _format_money_es(amt)
                period_note = getattr(d, "period_note", "") or "No consta período exacto en la documentación aportada"
                sec_note = getattr(d, "security_note", "") or "No consta garantía real asociada"
                bucket = getattr(d, "proposed_trlc_bucket", "no_determinable")
                basis = getattr(d, "classification_basis", "") or "A determinar con documentación adicional."
                story.append(Paragraph(f"<b>Importe:</b> {amt_txt}", body_style))
                story.append(Paragraph(f"<b>Período:</b> {period_note}", body_style))
                story.append(Paragraph(f"<b>Garantía:</b> {sec_note}", body_style))
                story.append(Paragraph(f"<b>Clasificación concursal (prudente):</b> {_bucket_label(bucket)}", body_style))
                story.append(Paragraph(f"<b>Base:</b> {_cap(basis, 360)}", small_gray))

                # Impacto práctico: prioridad de pago (cliente)
                prio, expectancy = _bucket_payment_explainer(bucket)
                story.append(Spacer(1, 0.08 * cm))
                story.append(Paragraph("<b>Impacto práctico (orden de pago y expectativa)</b>", styles["Normal"]))
                story.append(Paragraph(f"• {_cap(prio, 240)}", body_style))
                story.append(Paragraph(f"• {_cap(expectancy, 240)}", body_style))

                arts = getattr(d, "trlc_articles", None) or []
                if arts:
                    story.append(Paragraph("<b>Artículos TRLC aplicables</b>", styles["Normal"]))
                    for a in arts[:4]:
                        story.append(Paragraph(f"• {_cap(getattr(a,'article_ref','') or '—', 60)} — {_cap(getattr(a,'relevance','') or '', 220)}", body_style))

                opts = getattr(d, "legal_options", None) or []
                if opts:
                    story.append(Paragraph("<b>Opciones posibles</b>", styles["Normal"]))
                    for o in opts[:4]:
                        story.append(Paragraph(f"• {_cap(_neutralize_option_desc(getattr(o,'description','') or '—'), 260)}", body_style))

                cons = getattr(d, "practical_consequences", None) or []
                if cons:
                    story.append(Paragraph("<b>Consecuencias prácticas</b>", styles["Normal"]))
                    for x in cons[:4]:
                        story.append(Paragraph(f"• {_cap(x, 260)}", body_style))

                risks = getattr(d, "risks", None) or []
                if risks:
                    story.append(Paragraph("<b>Riesgos</b>", styles["Normal"]))
                    for r in risks[:3]:
                        story.append(Paragraph(f"• {_cap(getattr(r,'statement','') or '—', 260)}", body_style))

                evs = getattr(d, "evidence_refs", None) or []
                if evs:
                    story.append(Paragraph("<b>Evidencia</b>", styles["Normal"]))
                    for e in evs[:2]:
                        story.append(Paragraph(f"• {_cap(getattr(e,'document_name','') or '—', 120)} — {_cap(getattr(e,'excerpt','') or '—', 220)}", small_gray))

        story.append(Spacer(1, 0.6 * cm))

        # 6) RIESGOS POR INACCIÓN
        story.append(Paragraph("<b>6. RIESGOS POR INACCIÓN</b>", heading_style))
        rbi = getattr(contract, "risks_by_inaction", None) if contract else None
        if rbi:
            if getattr(rbi, "legal", None):
                story.append(Paragraph("<b>Riesgos legales</b>", styles["Normal"]))
                for x in (rbi.legal or [])[:8]:
                    story.append(Paragraph(f"• {_cap(x, 260)}", body_style))
            if getattr(rbi, "economic", None):
                story.append(Spacer(1, 0.1 * cm))
                story.append(Paragraph("<b>Riesgos económicos</b>", styles["Normal"]))
                for x in (rbi.economic or [])[:8]:
                    story.append(Paragraph(f"• {_cap(x, 260)}", body_style))
            story.append(Spacer(1, 0.1 * cm))
            story.append(Paragraph("La prolongación de esta situación sin actuación incrementa los riesgos descritos.", small_gray))
            story.append(Spacer(1, 0.1 * cm))
            story.append(
                Paragraph(
                    "Énfasis temporal: en el corto plazo (semanas) el riesgo principal es la continuidad de ejecuciones y el agravamiento de recargos/intereses; "
                    "en un horizonte de meses, aumenta la probabilidad de decisiones procesales con el expediente incompleto y de pérdida de margen de maniobra.",
                    small_gray,
                )
            )
        else:
            story.append(Paragraph("No se dispone de un bloque de riesgos con los datos actuales.", body_style))

        story.append(Spacer(1, 0.6 * cm))

        # 7) PROCESO CONCURSAL Y OPERATIVA PRÁCTICA
        story.append(Paragraph("<b>7. PROCESO CONCURSAL Y OPERATIVA PRÁCTICA</b>", heading_style))
        story.append(
            Paragraph(
                "A efectos orientativos, el procedimiento suele desarrollarse en fases. La aplicación concreta depende del caso y del auto judicial.",
                body_style,
            )
        )
        for s in [
            "Preparación del expediente por el despacho: inventario, lista de acreedores, documentación contable y hechos relevantes.",
            "Presentación ante el juzgado competente y admisión/tramitación.",
            "Auto de declaración de concurso y nombramiento de la Administración Concursal (AC).",
            "Determinación del régimen de facultades: intervención o suspensión (según auto).",
            "Fase común: inventario y lista de acreedores, informe de la AC y comunicaciones.",
            "Salida: convenio o liquidación; y, en su caso, calificación.",
        ]:
            story.append(Paragraph(f"• {_cap(s, 260)}", body_style))

        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("<b>Operativa: tesorería, cuentas y pagos esenciales</b>", styles["Normal"]))
        for s in [
            "Si existen embargos o bloqueo de cuentas, se debe identificar el origen y actuar coordinadamente con el despacho para valorar alternativas y calendario.",
            "Pagos a trabajadores, seguros y gastos ordinarios: se gestionan conforme al régimen fijado en el auto y bajo la supervisión que corresponda (deudor intervenido/suspendido y AC).",
            "Cautela: evitar pagos selectivos o disposiciones relevantes sin cobertura documental y sin asesoramiento, porque pueden agravar riesgos posteriores.",
        ]:
            story.append(Paragraph(f"• {_cap(s, 260)}", body_style))

        story.append(Spacer(1, 0.6 * cm))

        # 8) HOJA DE RUTA (PASOS)
        story.append(Paragraph("<b>8. HOJA DE RUTA (PASOS)</b>", heading_style))
        # Conectar la hoja de ruta con deudas/embargos detectados (sin tono directivo)
        try:
            has_exec = False
            if fin.insolvency and (fin.insolvency.signals_impago or []):
                # si hay señales de impago/embargo, considerarlo “hito operativo”
                has_exec = any("embargo" in _safe(getattr(s, "description", "")).lower() for s in fin.insolvency.signals_impago[:10])
        except Exception:
            has_exec = False
        top_debts = []
        try:
            # Tomar top 3 por importe (si existe)
            apps_sorted = sorted([d for d in (apps or []) if getattr(d, "amount_eur", None) is not None], key=lambda d: float(getattr(d, "amount_eur") or 0), reverse=True)
            for d in apps_sorted[:3]:
                nm = _safe(getattr(d, "creditor_name", "") or "Acreedor")
                top_debts.append(nm)
        except Exception:
            top_debts = []
        extra_ctx = []
        if has_exec:
            extra_ctx.append("constan referencias a embargos/apremio en el expediente")
        if top_debts:
            extra_ctx.append("las deudas de mayor importe identificadas se concentran en: " + ", ".join(top_debts))
        intro = "La siguiente hoja de ruta resume actuaciones prioritarias en función del estado actual del expediente."
        if extra_ctx:
            intro += " En particular, " + "; ".join(extra_ctx) + "."
        story.append(Paragraph(intro, body_style))
        if not bundle.roadmap:
            story.append(Paragraph("No hay hoja de ruta generada con los datos actuales.", body_style))
        else:
            # PRD: ordenar por actor (sin heurísticas: campo estructurado actor)
            cliente = []
            abogado = []
            ac = []

            for s in bundle.roadmap[:30]:
                actor = _safe(getattr(s, "actor", None)).lower()
                item = f"{_safe(getattr(s,'phase',None))} — {_safe(getattr(s,'step',None))}"
                if actor == "cliente":
                    cliente.append(item)
                elif actor == "administracion_concursal":
                    ac.append(item)
                else:
                    abogado.append(item)

            story.append(Paragraph("<b>Cliente</b>", styles["Normal"]))
            for x in (cliente or ["No hay pasos específicos asignables con los datos actuales."])[:10]:
                story.append(Paragraph(f"• {_cap(x, 260)}", body_style))

            story.append(Spacer(1, 0.15 * cm))
            story.append(Paragraph("<b>Abogado</b>", styles["Normal"]))
            for x in (abogado or ["No hay pasos específicos asignables con los datos actuales."])[:10]:
                story.append(Paragraph(f"• {_cap(x, 260)}", body_style))

            story.append(Spacer(1, 0.15 * cm))
            story.append(Paragraph("<b>Administración Concursal</b>", styles["Normal"]))
            for x in (ac or ["Se concretará tras el auto y el nombramiento de la AC."])[:10]:
                story.append(Paragraph(f"• {_cap(x, 260)}", body_style))

        # Adenda del abogado (si aplica)
        try:
            if addendum and isinstance(addendum, dict):
                atext = _safe(addendum.get("text"))
                aplace = _safe(addendum.get("placement")) or "before_signature"
                if atext:
                    # Insertar tras bloque 8 o antes de firma (default)
                    if aplace == "after_block_8":
                        story.append(Spacer(1, 0.5 * cm))
                        story.append(Paragraph("<b>ADENDA DEL ABOGADO</b>", heading_style))
                        for para in re.split(r"\n{2,}", atext.strip())[:6]:
                            story.append(Paragraph(_cap(para.strip(), 520), body_style))
                        story.append(Spacer(1, 0.2 * cm))
        except Exception:
            pass

        story.append(Spacer(1, 0.6 * cm))

        # 9) FIRMA DEL ABOGADO
        story.append(Paragraph("<b>9. FIRMA DEL ABOGADO</b>", heading_style))
        # Si la adenda está configurada para ir antes de firma, insertarla aquí (default)
        try:
            if addendum and isinstance(addendum, dict):
                atext = _safe(addendum.get("text"))
                aplace = _safe(addendum.get("placement")) or "before_signature"
                if atext and aplace != "after_block_8":
                    story.append(Spacer(1, 0.2 * cm))
                    story.append(Paragraph("<b>Adenda del abogado</b>", styles["Normal"]))
                    for para in re.split(r"\n{2,}", atext.strip())[:6]:
                        story.append(Paragraph(_cap(para.strip(), 520), body_style))
                    story.append(Spacer(1, 0.2 * cm))
        except Exception:
            pass
        if bundle.lawyer_signature:
            sig = bundle.lawyer_signature
            firm = sig.law_firm or "Despacho"
            story.append(Paragraph(f"<b>Despacho:</b> {firm}", body_style))
            story.append(Paragraph(f"<b>Abogado/a:</b> {sig.lawyer_name}", body_style))
            story.append(Paragraph(f"<b>Nº colegiado:</b> {sig.collegiate_number}", body_style))
            if sig.bar_association:
                story.append(Paragraph(f"<b>Colegio:</b> {sig.bar_association}", body_style))
            if sig.office_city:
                story.append(Paragraph(f"<b>Sede:</b> {sig.office_city}", body_style))
            story.append(Spacer(1, 0.1 * cm))
            sig_date = getattr(sig, "signature_date", None) or bundle.generated_at.strftime("%Y-%m-%d")
            story.append(Paragraph(f"<b>Fecha de firma:</b> {_format_date_human(sig_date)}", body_style))
        else:
            story.append(Paragraph("Firma no disponible.", body_style))

        # Construir y devolver (client)
        doc.build(
            story,
            canvasmaker=(lambda *args, **kwargs: NumberedCanvas(*args, footer_last_page=footer_scope_last_page, **kwargs)),
        )
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes


    # =========================
    # 1) RESUMEN EJECUTIVO
    # =========================
    story.append(Paragraph("<b>1. RESUMEN EJECUTIVO</b>", heading_style))
    # Internal (default): formato operativo
    story.append(Paragraph(bundle.client_summary.headline, styles["Normal"]))
    if bundle.client_summary.key_points:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("<b>Puntos clave</b>", styles["Normal"]))
        for p in bundle.client_summary.key_points[:6]:
            story.append(Paragraph(f"• {p}", styles["Normal"]))
    if bundle.client_summary.next_7_days:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("<b>Qué hacer en 7 días</b>", styles["Normal"]))
        for p in bundle.client_summary.next_7_days[:6]:
            story.append(Paragraph(f"• {p}", styles["Normal"]))
    if bundle.client_summary.warnings:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("<b>Avisos</b>", styles["Normal"]))
        for w in bundle.client_summary.warnings[:6]:
            story.append(Paragraph(f"• {w}", small_gray))

    # Línea temporal (si existe): ayuda a explicar “cómo se llegó aquí”
    try:
        tl = bundle.financial_analysis.timeline or []
        if tl:
            story.append(Spacer(1, 0.25 * cm))
            story.append(Paragraph("<b>Evolución (línea temporal)</b>", styles["Normal"]))
            rows: list[list[object]] = [["Fecha", "Hecho"]]
            added = 0
            for ev in tl[:20]:
                raw_date = getattr(ev, "date", None) or getattr(ev, "event_date", None)
                raw_desc = getattr(ev, "description", None) or getattr(ev, "event", None) or ""
                if not _is_human_event(raw_desc):
                    continue
                d = _format_date_human(raw_date)
                # si es fecha no determinada, aún permitimos el evento si la descripción es buena
                rows.append([_p(d, 40), _p(raw_desc, 220)])
                added += 1
                if added >= 8:
                    break
            story.append(Spacer(1, 0.1 * cm))
            if len(rows) > 1:
                story.append(_mk_table(rows, [3.2 * cm, 14.3 * cm]))
    except Exception:
        pass

    story.append(Spacer(1, 0.6 * cm))

    # =========================
    # 2) INVENTARIO DOCUMENTAL
    # =========================
    story.append(Paragraph("<b>2. INVENTARIO DOCUMENTAL</b>", heading_style))

    # 2.1 Presentados
    story.append(Paragraph("<b>2.1 Documentos aportados (revisados)</b>", styles["Normal"]))
    if bundle.documents_presented:
        # Agrupar duplicados por nombre de fichero (fallback conservador)
        counts: dict[str, int] = {}
        first: dict[str, object] = {}
        for d in bundle.documents_presented[:500]:
            fn = _safe(getattr(d, "filename", None) or "—")
            counts[fn] = counts.get(fn, 0) + 1
            if fn not in first:
                first[fn] = d

        rows: list[list[object]] = [["Tipo", "Documento", "Fecha"]]
        duplicates = 0
        for fn, d0 in list(first.items())[:25]:
            n = counts.get(fn, 1)
            if n > 1:
                duplicates += (n - 1)
                fn_disp = f"{fn} (x{n})"
            else:
                fn_disp = fn
            rows.append(
                [
                    _p(getattr(d0, "doc_type", None) or "—", 32),
                    _p(fn_disp, 140),
                    _p(getattr(d0, "created_at", None) or "—", 40),
                ]
            )
        story.append(Spacer(1, 0.15 * cm))
        story.append(_mk_table(rows, [3.2 * cm, 11.0 * cm, 3.3 * cm]))
        if duplicates > 0:
            story.append(Spacer(1, 0.1 * cm))
            story.append(
                Paragraph(
                    "Nota: se han detectado cargas repetidas de uno o varios documentos. "
                    "La existencia de duplicados no altera el fondo del análisis, pero se recomienda depurar el expediente.",
                    small_gray,
                )
            )
    else:
        story.append(Paragraph("No consta documentación aportada en el expediente.", body_style))

    # 2.2 Faltantes críticos
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("<b>2.2 Documentos faltantes (críticos/recomendados)</b>", styles["Normal"]))
    if bundle.documents_missing:
        for x in bundle.documents_missing[:12]:
            story.append(Paragraph(f"• {_cap(x, 220)}", body_style))
    else:
        story.append(Paragraph("No se han identificado faltantes críticos con los datos actuales.", body_style))

    # 2.3 Checklist recomendada
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("<b>2.3 Checklist recomendado</b>", styles["Normal"]))
    for x in (bundle.documents_recommended or [])[:12]:
        story.append(Paragraph(f"• {_cap(x, 220)}", body_style))

    story.append(Spacer(1, 0.6 * cm))

    # =========================
    # 3) SITUACIÓN ECONÓMICA (DATOS + INTERPRETACIÓN)
    # =========================
    story.append(Paragraph("<b>3. SITUACIÓN ECONÓMICA (DATOS + INTERPRETACIÓN)</b>", heading_style))

    fin = bundle.financial_analysis
    story.append(Paragraph(f"<b>Fecha análisis:</b> {fin.analysis_date.isoformat()}", small_gray))

    # Ratios
    if fin.ratios:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("<b>Ratios financieros</b>", styles["Normal"]))
        ratios_rows: list[list[object]] = [["Ratio", "Valor", "Estado", "Interpretación"]]
        for r in fin.ratios[:8]:
            val = "N/A" if r.value is None else f"{r.value:.2f}"
            ratios_rows.append(
                [
                    _p(r.name, 60),
                    _p(val, 16),
                    _p(getattr(getattr(r, "status", None), "value", None) or r.status, 24),
                    _p(getattr(r, "interpretation", "") or "—", 200),
                ]
            )
        story.append(_mk_table(ratios_rows, [5.2 * cm, 2.4 * cm, 2.6 * cm, 7.3 * cm]))
    else:
        story.append(Paragraph("No hay ratios calculables con la documentación actual.", styles["Normal"]))

    # Insolvencia
    if fin.insolvency:
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("<b>Señales de insolvencia</b>", styles["Normal"]))
        story.append(Paragraph(fin.insolvency.overall_assessment, styles["Normal"]))
        story.append(Paragraph(f"Confianza: {fin.insolvency.confidence_level.value}", small_gray))
        signals_rows: list[list[object]] = [["Tipo", "Descripción"]]

        def _iter_signals(label: str, items: list) -> None:
            for s in (items or [])[:4]:
                desc = _safe(getattr(s, "description", None) or s)
                if not desc or desc.lower().startswith("metadata:"):
                    continue
                signals_rows.append([_p(label, 20), _p(desc, 240)])

        _iter_signals("Impago", fin.insolvency.signals_impago)
        _iter_signals("Contable", fin.insolvency.signals_contables)
        _iter_signals("Exigibilidad", fin.insolvency.signals_exigibilidad)

        if len(signals_rows) > 1:
            story.append(Spacer(1, 0.15 * cm))
            story.append(_mk_table(signals_rows, [3.2 * cm, 14.3 * cm]))
        if fin.insolvency.critical_missing_docs:
            story.append(Spacer(1, 0.1 * cm))
            story.append(
                Paragraph(
                    "Faltan documentos críticos: " + ", ".join(fin.insolvency.critical_missing_docs[:8]),
                    small_gray,
                )
            )
    else:
        story.append(Paragraph("No hay datos suficientes para evaluar insolvencia con trazabilidad.", styles["Normal"]))

    story.append(Spacer(1, 0.6 * cm))

    # =========================
    # 4) ALERTAS DEL EXPEDIENTE (INTERNAL)
    # =========================
    story.append(Paragraph("<b>4. ALERTAS DEL EXPEDIENTE</b>", heading_style))
    if not bundle.alerts:
        story.append(Paragraph("No hay alertas detectadas.", styles["Normal"]))
    else:
        story.append(
            Paragraph(
                "Se han detectado observaciones internas en la documentación que conviene revisar y depurar. "
                "Estas observaciones no constituyen por sí mismas una conclusión jurídica.",
                small_gray,
            )
        )
        rows: list[list[object]] = [["Tipo", "Descripción", "Documentos (evidencia)"]]
        for a in bundle.alerts[:14]:
            raw = a.alert_type.value if hasattr(a.alert_type, "value") else str(a.alert_type)
            mapping = {
                "MISSING_DATA": "Información faltante (a completar)",
                "INCONSISTENT_DATA": "Inconsistencia de datos (a verificar)",
                "DUPLICATED_DATA": "Duplicidad documental (a depurar)",
                "TEMPORAL_INCONSISTENCY": "Inconsistencia temporal (a verificar)",
                "SUSPICIOUS_PATTERN": "Patrón a revisar (requiere verificación documental)",
            }
            atype = mapping.get(str(raw), "Observación interna (a revisar)")
            desc = _cap(getattr(a, "description", None), 260)

            docs = []
            try:
                for ev in (getattr(a, "evidence", None) or [])[:3]:
                    fn = None
                    if isinstance(ev, dict):
                        fn = ev.get("filename")
                    else:
                        fn = getattr(ev, "filename", None)
                    if fn:
                        docs.append(str(fn))
            except Exception:
                docs = []
            rows.append(
                [
                    _p(atype, 28),
                    _p(desc, 260),
                    _p(", ".join(docs) if docs else "—", 120),
                ]
            )

        story.append(Spacer(1, 0.15 * cm))
        story.append(_mk_table(rows, [3.2 * cm, 10.5 * cm, 3.8 * cm]))

    story.append(Spacer(1, 0.6 * cm))

    # =========================
    # 5) CLASIFICACIÓN DE LAS DEUDAS Y ORDEN LEGAL DE PAGO
    # =========================
    story.append(Paragraph("<b>5. CLASIFICACIÓN DE LAS DEUDAS Y ORDEN LEGAL DE PAGO EN EL CONCURSO</b>", heading_style))
    story.append(
        Paragraph(
            "En un procedimiento concursal, las deudas del deudor no se tratan todas por igual. "
            "La Ley Concursal establece una clasificación legal de los créditos que determina el orden "
            "en el que serán atendidos los pagos, bajo la supervisión de la Administración Concursal y, "
            "en última instancia, del Juzgado de lo Mercantil.",
            body_style,
        )
    )

    # 5.0 Mapa visible: hecho → base legal → consecuencia + riesgos por inacción
    contract = getattr(bundle, "narrative_contract", None)
    if contract and getattr(contract, "fact_law_map", None):
        story.append(Spacer(1, 0.25 * cm))
        story.append(Paragraph("<b>Hechos clave, base legal y consecuencia práctica</b>", styles["Normal"]))
        rows: list[list[object]] = [["Hecho", "Base legal (TRLC)", "Consecuencia", "Riesgo si no se actúa"]]
        for item in (contract.fact_law_map or [])[:10]:
            cites = []
            for c in (item.legal_basis or [])[:2]:
                cit = _safe(getattr(c, "citation", None))
                if cit:
                    cites.append(cit)
            rows.append(
                [
                    _p(getattr(item, "fact", None) or "—", 220),
                    _p(", ".join(cites) if cites else "—", 70),
                    _p(getattr(item, "consequence", None) or "—", 220),
                    _p(getattr(item, "risk_if_inaction", None) or "—", 220),
                ]
            )
        story.append(Spacer(1, 0.15 * cm))
        story.append(_mk_table(rows, [6.2 * cm, 3.0 * cm, 4.2 * cm, 4.0 * cm]))

        # Riesgos por inacción (bloque explícito)
        rbi = getattr(contract, "risks_by_inaction", None)
        if rbi:
            story.append(Spacer(1, 0.25 * cm))
            story.append(Paragraph("<b>Riesgos por inacción</b>", styles["Normal"]))
            if getattr(rbi, "legal", None):
                story.append(Paragraph("<b>Legales</b>", styles["Normal"]))
                for x in (rbi.legal or [])[:6]:
                    story.append(Paragraph(f"• {_cap(x, 260)}", body_style))
            if getattr(rbi, "economic", None):
                story.append(Spacer(1, 0.1 * cm))
                story.append(Paragraph("<b>Económicos</b>", styles["Normal"]))
                for x in (rbi.economic or [])[:6]:
                    story.append(Paragraph(f"• {_cap(x, 260)}", body_style))
            if getattr(rbi, "personal", None):
                story.append(Spacer(1, 0.1 * cm))
                story.append(Paragraph("<b>Personales</b>", styles["Normal"]))
                for x in (rbi.personal or [])[:6]:
                    story.append(Paragraph(f"• {_cap(x, 260)}", body_style))
            story.append(Spacer(1, 0.1 * cm))
            story.append(
                Paragraph(
                    "La prolongación de esta situación sin actuación incrementa los riesgos descritos.",
                    small_gray,
                )
            )

    # 5.1 Criterio general de clasificación
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("<b>5.1 Criterio general de clasificación de créditos</b>", styles["Normal"]))
    story.append(
        Paragraph(
            "Con carácter general, la Ley Concursal distingue entre: "
            "a) créditos contra la masa; y b) créditos concursales (privilegiados, ordinarios y subordinados). "
            "Esta clasificación es relevante porque condiciona qué acreedores cobran primero y qué deudas pueden quedar "
            "condicionadas al resultado final del concurso.",
            body_style,
        )
    )

    # Crédito público + opciones de pago (si hay citas)
    credito = bundle.legal_citations.get("credito_publico") or []
    masa = bundle.legal_citations.get("creditos_contra_masa") or []
    clasif = bundle.legal_citations.get("clasificacion_creditos") or []
    pagos = bundle.legal_citations.get("pago_creditos_concursales") or []
    calif = bundle.legal_citations.get("calificacion") or []
    concurso = bundle.legal_citations.get("concurso") or []
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("<b>5.5 Deudas con la Agencia Tributaria (AEAT) y la Tesorería General de la Seguridad Social (TGSS)</b>", styles["Normal"]))
    story.append(
        Paragraph(
            "Las deudas con AEAT y TGSS tienen un tratamiento específico dentro del procedimiento. "
            "Su calificación (y, en su caso, privilegio) puede condicionar el plan de pagos y las opciones del deudor. "
            "La aplicabilidad concreta requiere la documentación de deuda (certificados, períodos, recargos e intereses).",
            body_style,
        )
    )
    if credito:
        story.append(Spacer(1, 0.15 * cm))
        story.append(Paragraph("<b>Citas (crédito público)</b>", styles["Normal"]))
        seen = set()
        cite_rows: list[list[object]] = [["Cita", "Extracto"]]
        for c in credito:
            citation = _safe(getattr(c, "citation", None))
            if not citation or citation in seen:
                continue
            seen.add(citation)
            excerpt = _cap(getattr(c, "text", None) or "", 260) or "—"
            cite_rows.append([_p(citation, 140), _p(excerpt, 260)])
            if len(cite_rows) >= 7:
                break
        story.append(_mk_table(cite_rows, [8.2 * cm, 9.2 * cm]))
    else:
        story.append(Paragraph("No hay citas legales disponibles para crédito público.", small_gray))

    # 5.2 Créditos que se pagan con prioridad (contra la masa)
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("<b>5.2 Créditos que se pagan con prioridad</b>", styles["Normal"]))
    story.append(
        Paragraph(
            "Tienen prioridad de cobro los denominados créditos contra la masa, que incluyen gastos necesarios para la tramitación "
            "del concurso y determinados créditos laborales y financieros indispensables, en los términos del TRLC (arts. 242 a 250).",
            body_style,
        )
    )
    if masa:
        story.append(Spacer(1, 0.15 * cm))
        cite_rows: list[list[object]] = [["Cita", "Extracto literal"]]
        seen = set()
        for c in masa:
            citation = _safe(getattr(c, "citation", None))
            if not citation or citation in seen:
                continue
            seen.add(citation)
            excerpt = _cap(getattr(c, "text", None) or "", 320) or "—"
            cite_rows.append([_p(citation, 140), _p(excerpt, 320)])
            if len(cite_rows) >= 6:
                break
        story.append(_mk_table(cite_rows, [6.2 * cm, 11.2 * cm]))
    else:
        story.append(
            Paragraph(
                "No hay citas literales disponibles en el expediente para esta sección (corpus no disponible).",
                small_gray,
            )
        )

    # 5.3 Créditos ordinarios y subordinados
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("<b>5.3 Créditos ordinarios y subordinados</b>", styles["Normal"]))
    story.append(
        Paragraph(
            "Los créditos ordinarios se satisfacen una vez atendidos los créditos contra la masa y los privilegiados (TRLC, art. 433). "
            "En último lugar se sitúan los créditos subordinados, que solo se pagan cuando los ordinarios han sido íntegramente satisfechos "
            "(TRLC, art. 435).",
            body_style,
        )
    )
    if clasif or pagos:
        cite_rows = [["Cita", "Extracto literal"]]
        seen = set()
        for c in (clasif + pagos)[:8]:
            citation = _safe(getattr(c, "citation", None))
            if not citation or citation in seen:
                continue
            seen.add(citation)
            excerpt = _cap(getattr(c, "text", None) or "", 320) or "—"
            cite_rows.append([_p(citation, 140), _p(excerpt, 320)])
        story.append(_mk_table(cite_rows, [6.2 * cm, 11.2 * cm]))
    else:
        story.append(Paragraph("No hay citas legales disponibles para clasificación/pago de créditos.", small_gray))

    # 5.4 Consecuencias prácticas para el cliente
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("<b>5.4 Consecuencias prácticas para el cliente</b>", styles["Normal"]))
    for s in [
        "La clasificación de las deudas determinará qué acreedores pueden ejecutar garantías, qué deudas deben atenderse con prioridad y cuáles quedarán condicionadas al resultado final del concurso.",
        "Por este motivo, resulta esencial identificar correctamente cada deuda y su naturaleza jurídica antes de adoptar decisiones estratégicas.",
    ]:
        story.append(Paragraph(f"• {_cap(s, 260)}", body_style))

    # 5.6 Opciones respecto de la deuda pública (orientativas)
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("<b>5.6 Opciones respecto de la deuda pública</b>", styles["Normal"]))
    story.append(
        Paragraph(
            "Con carácter general, las opciones a valorar son: (a) inclusión en el procedimiento concursal asumiendo las limitaciones legales; "
            "y (b) negociación de aplazamientos o fraccionamientos conforme a la normativa específica tributaria y de Seguridad Social, "
            "siempre que concurran requisitos. La elección debe realizarse con cautela y con soporte documental.",
            body_style,
        )
    )

    # 5.7 Riesgos asociados y advertencia legal
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("<b>5.7 Riesgos asociados y advertencia legal</b>", styles["Normal"]))
    story.append(
        Paragraph(
            "En supuestos de irregularidades significativas o impagos relevantes, la situación puede ser analizada en la fase de calificación "
            "del concurso conforme a los arts. 441 y siguientes del TRLC. Sin perjuicio de que la calificación corresponde al juez, "
            "resulta esencial abordar estas deudas de forma ordenada, documentada y con asesoramiento especializado.",
            body_style,
        )
    )

    # Recomendación conservadora (si no hay opciones determinables)
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("<b>Recomendación práctica (conservadora)</b>", styles["Normal"]))
    story.append(
        Paragraph(
            "Con la información disponible no puede adoptarse aún una decisión definitiva. "
            "Es prioritario completar el expediente en los extremos indicados (contabilidad, vencimientos y relación de acreedores) "
            "antes de adoptar decisiones estratégicas.",
            body_style,
        )
    )

    # Declaración de concurso / régimen de facultades (citas)
    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("<b>Declaración de concurso, notificaciones y efectos</b>", styles["Normal"]))
    if concurso:
        cite_rows = [["Cita", "Extracto literal"]]
        seen = set()
        for c in concurso:
            citation = _safe(getattr(c, "citation", None))
            if not citation or citation in seen:
                continue
            seen.add(citation)
            excerpt = _cap(getattr(c, "text", None) or "", 320) or "—"
            cite_rows.append([_p(citation, 140), _p(excerpt, 320)])
            if len(cite_rows) >= 5:
                break
        story.append(_mk_table(cite_rows, [6.2 * cm, 11.2 * cm]))
    else:
        story.append(Paragraph("No hay citas legales disponibles para esta sección.", small_gray))

    # Calificación (si hay citas)
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("<b>Calificación (riesgos y fase posterior)</b>", styles["Normal"]))
    if calif:
        cite_rows = [["Cita", "Extracto"]]
        seen = set()
        for c in calif:
            citation = _safe(getattr(c, "citation", None))
            if not citation or citation in seen:
                continue
            seen.add(citation)
            excerpt = _cap(getattr(c, "text", None) or "", 260) or "—"
            cite_rows.append([_p(citation, 140), _p(excerpt, 260)])
            if len(cite_rows) >= 7:
                break
        story.append(_mk_table(cite_rows, [8.2 * cm, 9.2 * cm]))
    else:
        story.append(Paragraph("No hay citas legales disponibles para calificación.", small_gray))

    # Exoneración
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("<b>Exoneración</b>", styles["Normal"]))
    if bundle.debtor_type == "company":
        story.append(
            Paragraph(
                "El deudor parece ser una empresa. La exoneración suele aplicarse a personas físicas; "
                "este bloque se muestra solo a nivel informativo.",
                styles["Normal"],
            )
        )
    exo = bundle.legal_citations.get("exoneracion") or []
    if exo:
        seen = set()
        cite_rows: list[list[object]] = [["Cita", "Extracto"]]
        for c in exo:
            citation = _safe(getattr(c, "citation", None))
            if not citation or citation in seen:
                continue
            seen.add(citation)
            excerpt = _cap(getattr(c, "text", None) or "", 260) or "—"
            cite_rows.append([_p(citation, 140), _p(excerpt, 260)])
            if len(cite_rows) >= 7:
                break
        story.append(_mk_table(cite_rows, [8.2 * cm, 9.2 * cm]))
    else:
        story.append(Paragraph("No hay citas legales disponibles para exoneración.", small_gray))

    # 5.2 Proceso concursal y roles (explicación para cliente)
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("<b>Proceso concursal (resumen práctico)</b>", styles["Normal"]))
    story.append(
        Paragraph(
            "A efectos orientativos, el procedimiento suele desarrollarse en las siguientes fases (la aplicación concreta depende del caso y del auto):",
            body_style,
        )
    )
    for s in [
        "Preparación del expediente por el despacho: inventario, lista de acreedores, documentación contable y hechos relevantes.",
        "Presentación ante el juzgado competente y admisión/tramitación.",
        "Auto de declaración de concurso y nombramiento de la Administración Concursal (AC).",
        "Determinación del régimen de facultades: intervención o suspensión (según auto).",
        "Fase común: inventario y lista de acreedores, informe de la AC y comunicaciones.",
        "Salida: convenio o liquidación; y, en su caso, calificación.",
    ]:
        story.append(Paragraph(f"• {_cap(s, 260)}", body_style))

    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("<b>Operativa: tesorería, cuentas y pagos</b>", styles["Normal"]))
    for s in [
        "Si existen embargos o bloqueo de cuentas, se debe identificar el origen (AEAT/TGSS/otros) y actuar coordinadamente con el despacho para valorar alternativas y calendario.",
        "Pagos a trabajadores, seguros y gastos ordinarios: se gestionan conforme al régimen fijado en el auto y bajo la supervisión que corresponda (deudor intervenido/suspendido y AC).",
        "Cautela: evitar pagos selectivos o disposiciones relevantes sin cobertura documental y sin asesoramiento, porque pueden agravar riesgos posteriores.",
    ]:
        story.append(Paragraph(f"• {_cap(s, 260)}", body_style))

    story.append(Spacer(1, 0.6 * cm))

    # =========================
    # 6) HOJA DE RUTA
    # =========================
    story.append(Paragraph("<b>6. HOJA DE RUTA (PASOS)</b>", heading_style))
    story.append(
        Paragraph(
            "La siguiente hoja de ruta resume las actuaciones prioritarias recomendadas en función del estado actual del expediente.",
            body_style,
        )
    )
    if not bundle.roadmap:
        story.append(Paragraph("No hay hoja de ruta generada.", styles["Normal"]))
    else:
        roadmap_rows: list[list[object]] = [["Fase", "Paso", "Prioridad", "Estado"]]
        for s in bundle.roadmap[:15]:
            roadmap_rows.append(
                [
                    _p(s.phase, 24),
                    _p(s.step, 240),
                    _p(s.priority, 12),
                    _p(s.status, 18),
                ]
            )
        story.append(_mk_table(roadmap_rows, [2.8 * cm, 10.0 * cm, 2.2 * cm, 2.5 * cm]))

    # =========================
    # FOOTER
    # =========================
    story.append(PageBreak())
    story.append(Paragraph("<b>FIN DEL INFORME</b>", heading_style))
    footer_left = ""
    if bundle.lawyer_signature:
        sig = bundle.lawyer_signature
        firm = sig.law_firm or "Despacho"
        footer_left = f"{firm} — {sig.lawyer_name} (Nº {sig.collegiate_number})"
    else:
        footer_left = "Despacho — Equipo jurídico (Nº colegiado: PENDIENTE)"

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(footer_left, ParagraphStyle("EcoFooterLeft", parent=styles["Normal"], fontSize=9)))
    story.append(
        Paragraph(
            f"Fecha: {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S UTC')}",
            ParagraphStyle(
                "EcoFooter",
                parent=styles["Normal"],
                fontSize=8,
                textColor=COLOR_GRAY,
                alignment=TA_CENTER,
            ),
        )
    )

    doc.build(story, canvasmaker=NumberedCanvas)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

