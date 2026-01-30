#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Phoenix Legal — Dataset sintético doc_2 (FULL PACK 1..8)
Salida:
  /Users/irumabragado/Documents/procesos/202512_phoenix-legal/case_retail_demo_sl_2026/doc_2

Genera documentos representativos de:
1) Contabilidad y situación económica
2) Documentación societaria
3) Bienes y masa activa
4) Pasivo privado (acreedores)
5) Pasivo público (AEAT/TGSS)
6) Procedimientos judiciales/administrativos (incl. LexNET)
7) Operaciones vinculadas
8) Documentación blanda (emails, comunicaciones, informes, notas)

NOTA: esto solo crea archivos. La ingesta poblará documents + document_chunks.
"""

from __future__ import annotations

import json
import os
import random
import string
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Optional

# PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# DOCX
from docx import Document as DocxDocument  # python-docx

# XLSX
from openpyxl import Workbook
from openpyxl.utils import get_column_letter


# -----------------------
# CONFIG
# -----------------------

OUT_DIR = Path("/Users/irumabragado/Documents/procesos/202512_phoenix-legal/case_retail_demo_sl_2026/doc_2")

CASE_NAME = "RETAIL DEMO SL - Caso Concursal 2026 (doc_2)"
DEBTOR_NAME = "RETAIL DEMO SL"
DEBTOR_TAX_ID = "B-87991234"
DEBTOR_ADDRESS = "C/ Guzmán el Bueno 81, 28015 Madrid"
DEBTOR_REG = "Registro Mercantil de Madrid, Tomo 12345, Folio 67, Hoja M-987654"
DEBTOR_ACTIVITY = "Comercio minorista de productos electrónicos y servicios asociados"
ADMIN_NAME = "María López Serrano"
ADMIN_NIF = "12345678Z"

CURRENCY = "EUR"
RANDOM_SEED = 20260130
random.seed(RANDOM_SEED)


# -----------------------
# HELPERS
# -----------------------

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")

def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def euro(x: float) -> str:
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"

def randi(a: int, b: int) -> int:
    return random.randint(a, b)

def rand_amount(min_v: int, max_v: int) -> float:
    return float(randi(min_v, max_v))

def d(days_ago: int) -> date:
    return (date.today() - timedelta(days=days_ago))

def today_utc() -> datetime:
    return datetime.utcnow()

def rand_invoice_number() -> str:
    return f"F-{randi(2023, 2026)}-{randi(1000, 9999)}"

def rand_tax_id_company() -> str:
    letter = random.choice(list("ABCDEFGHJNPQRSUVW"))
    digits = "".join(random.choice(string.digits) for _ in range(7))
    ctrl = random.choice(string.digits + "ABCDEFGHJNPQRSUVW")
    return f"{letter}{digits}{ctrl}"

def make_pdf(path: Path, title: str, lines: list[str]) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, h - 20 * mm, title)

    c.setFont("Helvetica", 10)
    y = h - 30 * mm
    for ln in lines:
        if y < 15 * mm:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = h - 20 * mm
        c.drawString(20 * mm, y, ln[:160])
        y -= 6 * mm

    c.showPage()
    c.save()

def make_docx(path: Path, title: str, paragraphs: list[str]) -> None:
    doc = DocxDocument()
    doc.add_heading(title, level=1)
    doc.add_paragraph(f"Generado: {today_utc().isoformat()}Z")
    doc.add_paragraph("")
    for p in paragraphs:
        doc.add_paragraph(p)
    doc.save(str(path))

def make_eml(path: Path, subject: str, body: str, from_addr: str, to_addr: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0100")
    msg.set_content(body)
    path.write_bytes(msg.as_bytes())

def make_xlsx(path: Path, sheet_name: str, headers: list[str], rows: list[list[Any]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    ws.append(headers)
    for r in rows:
        ws.append(r)

    # autosize simple
    for col in range(1, len(headers) + 1):
        col_letter = get_column_letter(col)
        ws.column_dimensions[col_letter].width = min(45, max(12, len(str(headers[col-1])) + 2))
    wb.save(str(path))


# -----------------------
# DOMAIN POOLS
# -----------------------

@dataclass
class Supplier:
    name: str
    tax_id: str
    email: str
    address: str

def suppliers_pool() -> list[Supplier]:
    return [
        Supplier("Proveedor Alpha S.L.", rand_tax_id_company(), "cobros@alpha-proveedor.es", "Av. Europa 12, 28108 Alcobendas"),
        Supplier("Proveedor Beta S.A.", rand_tax_id_company(), "facturacion@beta-sa.es", "C/ Industria 44, 28923 Alcorcón"),
        Supplier("Servicios Gamma S.L.", rand_tax_id_company(), "administracion@gamma-servicios.es", "Pº Castellana 210, 28046 Madrid"),
        Supplier("Logística Delta S.L.", rand_tax_id_company(), "cobros@delta-logistica.es", "C/ Puerto 3, 28850 Torrejón de Ardoz"),
        Supplier("Tecnología Épsilon S.L.", rand_tax_id_company(), "cobros@epsilon-tech.es", "C/ Serrano 98, 28006 Madrid"),
    ]


# -----------------------
# 1) CONTABILIDAD (núcleo duro)
# -----------------------

def gen_accounting(base: Path) -> dict[str, Any]:
    out = base / "01_contabilidad"
    ensure_dir(out)

    years = [2023, 2024, 2025]
    # forzar tendencia negativa (PN negativo, pérdidas y tesorería tensionada)
    bs_files = []
    pyg_files = []
    pn_files = []
    cf_files = []
    inter_files = []

    for y in years:
        # Balance
        total_activo = 200000 + (y - 2023) * 15000
        pn = -230000 + (y - 2023) * 20000  # sigue negativo, pero cambia
        pasivo = total_activo - pn

        lines_bs = [
            "BALANCE DE SITUACIÓN (sintético)",
            f"Sociedad: {DEBTOR_NAME} — CIF {DEBTOR_TAX_ID}",
            f"Ejercicio: {y}",
            "",
            "ACTIVO",
            f"Activo no corriente: {euro(total_activo * 0.60)}",
            f"Activo corriente: {euro(total_activo * 0.40)}",
            f"TOTAL ACTIVO: {euro(total_activo)}",
            "",
            "PATRIMONIO NETO Y PASIVO",
            f"Patrimonio neto: {euro(pn)}",
            f"Pasivo no corriente: {euro(pasivo * 0.25)}",
            f"Pasivo corriente: {euro(pasivo * 0.75)}",
            f"TOTAL PN Y PASIVO: {euro(total_activo)}",
            "",
            "Señales: patrimonio neto negativo, tensión de liquidez, riesgo insolvencia.",
        ]
        p = out / f"{y}_Balance_Situacion.pdf"
        make_pdf(p, f"Balance de Situación {y}", lines_bs)
        bs_files.append(p.name)

        # PyG
        ingresos = 480000 + (y - 2023) * 25000
        gastos = ingresos + 40000 + (y - 2023) * 8000  # pérdidas
        res = ingresos - gastos
        lines_pyg = [
            "CUENTA DE PÉRDIDAS Y GANANCIAS (sintética)",
            f"Sociedad: {DEBTOR_NAME} — CIF {DEBTOR_TAX_ID}",
            f"Ejercicio: {y}",
            "",
            f"Ingresos: {euro(ingresos)}",
            f"Gastos de explotación: {euro(-gastos)}",
            f"RESULTADO DEL EJERCICIO: {euro(res)}",
            "",
            "Señales: pérdidas recurrentes y deterioro operativo.",
        ]
        p2 = out / f"{y}_Cuenta_PyG.pdf"
        make_pdf(p2, f"Cuenta PyG {y}", lines_pyg)
        pyg_files.append(p2.name)

        # Estado cambios PN (DOCX)
        doc_pn = out / f"{y}_Estado_Cambios_PN.docx"
        make_docx(
            doc_pn,
            f"Estado de Cambios en el Patrimonio Neto {y} (síntesis)",
            [
                f"Patrimonio neto inicial: {euro(pn - 15000)}",
                f"Resultado del ejercicio: {euro(res)}",
                "Ajustes: deterioros / provisiones (sintético).",
                f"Patrimonio neto final: {euro(pn)}",
                "Comentario: PN negativo sostenido. Potencial insolvencia actual/inminente.",
            ],
        )
        pn_files.append(doc_pn.name)

        # Estado flujos efectivo (XLSX)
        cf = out / f"{y}_Estado_Flujos_Efectivo.xlsx"
        headers = ["concepto", "importe"]
        rows = [
            ["Flujos de explotación", -18000 - (y - 2023) * 6000],
            ["Flujos de inversión", -9000],
            ["Flujos de financiación", 12000],
            ["Variación neta de efectivo", -15000 - (y - 2023) * 6000],
        ]
        make_xlsx(cf, "EFE", headers, rows)
        cf_files.append(cf.name)

    # Balance intermedio (si concurso no coincide con cierre)
    inter = out / "2026_Balance_Intermedio_30Jun.pdf"
    make_pdf(
        inter,
        "Balance Intermedio 30/06/2026",
        [
            f"Sociedad: {DEBTOR_NAME} — CIF {DEBTOR_TAX_ID}",
            "Fecha: 30/06/2026",
            "",
            "Señales: caída de ventas Q2, incremento impagos, caja tensionada.",
            "Tesorería reportada: 22.000 € (pero conciliación detecta partidas no disponibles).",
            "Pasivo exigible corto plazo: 410.000 €.",
        ],
    )
    inter_files.append(inter.name)

    # Auxiliares: libro mayor + sumas y saldos (XLSX)
    mayor = out / "Libro_Mayor_2025.xlsx"
    rows_mayor = []
    for i in range(1, 120):
        rows_mayor.append([
            f"2025-{randi(1,12):02d}-{randi(1,28):02d}",
            random.choice(["430 Clientes", "400 Proveedores", "572 Bancos", "640 Sueldos", "475 HP acreedora", "476 SS acreedora"]),
            random.choice(["Cargo", "Abono"]),
            rand_amount(50, 8500),
            random.choice(["Factura proveedor", "Cobro TPV", "Nóminas", "Impuestos", "Cuotas SS", "Transferencia vinculada"]),
        ])
    make_xlsx(mayor, "MAYOR", ["fecha", "cuenta", "mov", "importe", "concepto"], rows_mayor)

    sumas = out / "Balance_Sumas_y_Saldos_2025.xlsx"
    rows_sumas = [
        ["572 Bancos", 220000, 245000, -25000],
        ["400 Proveedores", 120000, 40000, 80000],
        ["475 HP acreedora", 70000, 15000, 55000],
        ["476 SS acreedora", 52000, 12000, 40000],
        ["129 Resultado", 0, 60000, -60000],
    ]
    make_xlsx(sumas, "SUMAS_SALDOS", ["cuenta", "debe", "haber", "saldo"], rows_sumas)

    # Extractos bancarios 24 meses (PDF + CSV) + conciliación bancaria (XLSX)
    bank_dir = out / "Extractos_Bancarios_24m"
    ensure_dir(bank_dir)

    movements = []
    start = date.today() - timedelta(days=730)
    saldo = 45000.0
    for i in range(1, 220):
        dt = start + timedelta(days=i * 3)
        concept = random.choice([
            "TPV ventas", "Pago proveedor", "Recibo alquiler", "Nóminas", "Impuestos", "Cuotas SS", "Comisión bancaria",
        ])
        if i in (40, 95, 160):
            concept = "TRANSFERENCIA A SOCIEDAD VINCULADA - ADMINISTRADOR"
            amount = -float(randi(1500, 6500))
        else:
            amount = float(randi(-9000, 11000))
        saldo += amount
        movements.append([dt.isoformat(), concept, amount, saldo])

    # CSV
    bank_csv = bank_dir / "Movimientos_24m.csv"
    lines = ["fecha,concepto,importe,saldo"]
    for m in movements:
        lines.append(f"{m[0]},{m[1]},{m[2]},{m[3]}")
    write_text(bank_csv, "\n".join(lines))

    # PDF resumen
    bank_pdf = bank_dir / "Extracto_24m_resumen.pdf"
    pdf_lines = [
        "EXTRACTOS BANCARIOS (resumen 24 meses)",
        f"Titular: {DEBTOR_NAME} — CIF {DEBTOR_TAX_ID}",
        "IBAN (enmascarado): ES12 **** **** **** 1234",
        "",
        "Se incluyen movimientos con posibles pagos selectivos y transferencias a vinculados.",
        f"Total movimientos: {len(movements)}",
        f"Saldo final (aprox): {euro(movements[-1][3])}",
        "",
        "MUESTRA (10 últimos):",
    ]
    for m in movements[-10:]:
        pdf_lines.append(f"{m[0]} | {m[1]} | {euro(float(m[2]))} | saldo {euro(float(m[3]))}")
    make_pdf(bank_pdf, "Extracto bancario 24 meses (resumen)", pdf_lines)

    concil = bank_dir / "Conciliacion_Bancaria_2026_06.xlsx"
    conc_rows = [
        ["fecha", "concepto", "importe", "estado", "nota"],
        ["2026-06-05", "TPV ventas", 4200, "PENDIENTE", "cobro no abonado aún"],
        ["2026-06-11", "Recibo alquiler", -1800, "CONCILIADO", ""],
        ["2026-06-18", "Pago proveedor", -9200, "PENDIENTE", "posible devolución/impago"],
    ]
    make_xlsx(concil, "CONCILIACION", conc_rows[0], conc_rows[1:])

    return {
        "balances_pdf": bs_files,
        "pyg_pdf": pyg_files,
        "pn_docs": pn_files,
        "cashflow_xlsx": cf_files,
        "intermediate": inter_files,
        "aux": [mayor.name, sumas.name, bank_csv.name, bank_pdf.name, concil.name],
    }


# -----------------------
# 2) SOCIETARIA
# -----------------------

def gen_corporate(base: Path) -> dict[str, Any]:
    out = base / "02_societaria"
    ensure_dir(out)

    constit = out / "01_Escritura_Constitucion.pdf"
    make_pdf(
        constit,
        "Escritura de Constitución",
        [
            f"Sociedad: {DEBTOR_NAME} ({DEBTOR_TAX_ID})",
            f"Domicilio: {DEBTOR_ADDRESS}",
            f"Objeto social: {DEBTOR_ACTIVITY}",
            "Capital social inicial: 3.000,00 €",
            "Administrador: " + ADMIN_NAME,
            "Fecha: 2018-03-14",
            "",
            "Cláusulas relevantes: administración, representación, duración, transmisión participaciones.",
        ],
    )

    estat = out / "02_Estatutos_Sociales_Vigentes.docx"
    make_docx(
        estat,
        "Estatutos sociales vigentes",
        [
            "Artículo 1 — Denominación y régimen jurídico.",
            "Artículo 2 — Objeto social.",
            "Artículo 3 — Domicilio social.",
            "Artículo 10 — Órgano de administración.",
            "Artículo 12 — Facultades y deber de lealtad / diligencia del administrador (síntesis).",
            "Anexo — Modificación estatutaria 2024 (sintética).",
        ],
    )

    cap = out / "03_Ampliacion_Capital_2024.pdf"
    make_pdf(
        cap,
        "Escritura de ampliación de capital (2024)",
        [
            f"Sociedad: {DEBTOR_NAME}",
            "Ampliación de capital: 50.000 €",
            "Suscripción: socios actuales",
            "Fecha: 2024-09-10",
            "",
            "Observación: ampliación previa a deterioro de tesorería. Revisar trazabilidad de fondos.",
        ],
    )

    admin_change = out / "04_Cambio_Administrador_2025.pdf"
    make_pdf(
        admin_change,
        "Cambio de administrador (2025)",
        [
            f"Sociedad: {DEBTOR_NAME}",
            "Cese administrador: Juan Pérez Díaz (NIF 11111111H)",
            f"Nombramiento administrador: {ADMIN_NAME} (NIF {ADMIN_NIF})",
            "Fecha: 2025-11-18",
            "",
            "Señal: cambio próximo a presión acreedores / deuda pública.",
        ],
    )

    junta = out / "05_Acta_Junta_2025.docx"
    make_docx(
        junta,
        "Acta de Junta General (2025)",
        [
            "Punto 1: aprobación de cuentas.",
            "Punto 2: medidas de liquidez (aplazamientos, recortes, renegociación bancaria).",
            "Punto 3: autorización de actuaciones y poderes para negociar con acreedores y tramitar gestiones concursales si procede.",
        ],
    )

    return {
        "societaria": [
            constit.name,
            estat.name,
            cap.name,
            admin_change.name,
            junta.name,
        ]
    }


def main() -> None:
    """
    Genera el paquete sintético doc_2.
    Nota: este script solo crea archivos locales (no ingiere ni escribe en BD).
    """
    ensure_dir(OUT_DIR)

    manifest: dict[str, Any] = {
        "case_name": CASE_NAME,
        "out_dir": str(OUT_DIR),
        "generated_at": today_utc().isoformat() + "Z",
        "packs": {},
    }

    manifest["packs"]["01_contabilidad"] = gen_accounting(OUT_DIR)
    manifest["packs"]["02_societaria"] = gen_corporate(OUT_DIR)

    write_json(OUT_DIR / "manifest.json", manifest)


if __name__ == "__main__":
    main()