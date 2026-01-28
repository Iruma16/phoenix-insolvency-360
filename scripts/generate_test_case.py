"""
Generador de Caso de Prueba Realista para Phoenix Legal.

Crea un caso concursal completo con documentos PDF realistas:
- Balance de Situación
- Cuenta de PyG
- Facturas impagadas
- Extractos bancarios
- Avisos de embargo
- Emails de acreedores
- Libro mayor

Empresa: RETAIL DEMO SL
Situación: Insolvencia actual
Riesgos: Pagos preferentes, alzamiento de bienes
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from datetime import datetime, timedelta
from pathlib import Path

# Directorio de salida
OUTPUT_DIR = Path("data/casos_prueba/RETAIL_DEMO_SL")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Estilos
styles = getSampleStyleSheet()
title_style = ParagraphStyle(
    'CustomTitle',
    parent=styles['Heading1'],
    fontSize=18,
    textColor=colors.HexColor('#1a237e'),
    spaceAfter=30,
    alignment=TA_CENTER
)
heading_style = ParagraphStyle(
    'CustomHeading',
    parent=styles['Heading2'],
    fontSize=14,
    textColor=colors.HexColor('#283593'),
    spaceAfter=12
)


def create_balance_sheet():
    """Genera Balance de Situación."""
    filename = OUTPUT_DIR / "01_Balance_Situacion_2023.pdf"
    doc = SimpleDocTemplate(str(filename), pagesize=A4)
    story = []
    
    # Título
    story.append(Paragraph("RETAIL DEMO SL", title_style))
    story.append(Paragraph("BALANCE DE SITUACIÓN", title_style))
    story.append(Paragraph("A 31 de diciembre de 2023", styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Activo
    story.append(Paragraph("ACTIVO", heading_style))
    activo_data = [
        ['CONCEPTO', 'IMPORTE (€)'],
        ['', ''],
        ['A) ACTIVO NO CORRIENTE', '180.000'],
        ['  I. Inmovilizado intangible', '5.000'],
        ['  II. Inmovilizado material', '150.000'],
        ['      1. Terrenos y construcciones', '120.000'],
        ['      2. Instalaciones técnicas', '30.000'],
        ['  III. Inversiones financieras a l/p', '25.000'],
        ['', ''],
        ['B) ACTIVO CORRIENTE', '70.000'],
        ['  I. Existencias', '45.000'],
        ['  II. Deudores comerciales', '21.500'],
        ['  III. Efectivo y equivalentes', '3.500'],
        ['', ''],
        ['TOTAL ACTIVO', '250.000'],
    ]
    
    activo_table = Table(activo_data, colWidths=[120*mm, 40*mm])
    activo_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8eaf6')),
    ]))
    story.append(activo_table)
    story.append(Spacer(1, 20))
    
    # Pasivo
    story.append(Paragraph("PATRIMONIO NETO Y PASIVO", heading_style))
    pasivo_data = [
        ['CONCEPTO', 'IMPORTE (€)'],
        ['', ''],
        ['A) PATRIMONIO NETO', '-230.000'],
        ['  I. Capital', '60.000'],
        ['  II. Reservas', '15.000'],
        ['  III. Resultados ejercicio', '-60.000'],
        ['  IV. Resultados ejercicios anteriores', '-245.000'],
        ['', ''],
        ['B) PASIVO NO CORRIENTE', '180.000'],
        ['  I. Deudas a largo plazo', '180.000'],
        ['      1. Préstamos entidades crédito', '180.000'],
        ['', ''],
        ['C) PASIVO CORRIENTE', '300.000'],
        ['  I. Deudas a corto plazo', '85.000'],
        ['  II. Acreedores comerciales', '105.000'],
        ['  III. Deudas con Administraciones', '110.000'],
        ['      1. Hacienda Pública', '68.000'],
        ['      2. Seguridad Social', '42.000'],
        ['', ''],
        ['TOTAL PATRIMONIO NETO Y PASIVO', '250.000'],
    ]
    
    pasivo_table = Table(pasivo_data, colWidths=[120*mm, 40*mm])
    pasivo_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8eaf6')),
        ('TEXTCOLOR', (0, 2), (1, 2), colors.red),  # Patrimonio neto negativo en rojo
    ]))
    story.append(pasivo_table)
    
    story.append(Spacer(1, 30))
    story.append(Paragraph(
        "<b>SITUACIÓN:</b> Patrimonio neto negativo de 230.000€. Insolvencia actual.",
        ParagraphStyle('Alert', parent=styles['Normal'], textColor=colors.red)
    ))
    
    doc.build(story)
    print(f"✅ Creado: {filename}")


def create_pyg():
    """Genera Cuenta de Pérdidas y Ganancias."""
    filename = OUTPUT_DIR / "02_Cuenta_PyG_2023.pdf"
    doc = SimpleDocTemplate(str(filename), pagesize=A4)
    story = []
    
    story.append(Paragraph("RETAIL DEMO SL", title_style))
    story.append(Paragraph("CUENTA DE PÉRDIDAS Y GANANCIAS", title_style))
    story.append(Paragraph("Ejercicio 2023", styles['Normal']))
    story.append(Spacer(1, 20))
    
    pyg_data = [
        ['CONCEPTO', 'IMPORTE (€)'],
        ['', ''],
        ['1. Importe neto de la cifra de negocios', '120.000'],
        ['2. Variación de existencias', '-15.000'],
        ['3. Aprovisionamientos', '-65.000'],
        ['', ''],
        ['VALOR AÑADIDO (1+2+3)', '40.000'],
        ['', ''],
        ['4. Gastos de personal', '-48.000'],
        ['5. Otros gastos de explotación', '-32.000'],
        ['6. Amortizaciones', '-18.000'],
        ['7. Deterioros', '-5.000'],
        ['', ''],
        ['RESULTADO DE EXPLOTACIÓN', '-63.000'],
        ['', ''],
        ['8. Ingresos financieros', '500'],
        ['9. Gastos financieros', '-12.500'],
        ['', ''],
        ['RESULTADO FINANCIERO', '-12.000'],
        ['', ''],
        ['RESULTADO ANTES DE IMPUESTOS', '-75.000'],
        ['', ''],
        ['10. Impuesto sobre beneficios', '15.000'],
        ['', ''],
        ['RESULTADO DEL EJERCICIO', '-60.000'],
    ]
    
    pyg_table = Table(pyg_data, colWidths=[120*mm, 40*mm])
    pyg_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ffebee')),
        ('TEXTCOLOR', (0, -1), (1, -1), colors.red),
    ]))
    story.append(pyg_table)
    
    doc.build(story)
    print(f"✅ Creado: {filename}")


def create_invoice(supplier_name, amount, invoice_num, days_overdue, filename):
    """Genera una factura impagada."""
    doc = SimpleDocTemplate(str(filename), pagesize=A4)
    story = []
    
    # Fecha de emisión y vencimiento
    issue_date = datetime(2023, 8, 15) - timedelta(days=days_overdue)
    due_date = issue_date + timedelta(days=30)
    
    story.append(Paragraph(f"{supplier_name}", title_style))
    story.append(Paragraph("FACTURA", title_style))
    story.append(Spacer(1, 10))
    
    # Info factura
    info_data = [
        ['Número de Factura:', invoice_num],
        ['Fecha de Emisión:', issue_date.strftime('%d/%m/%Y')],
        ['Fecha de Vencimiento:', due_date.strftime('%d/%m/%Y')],
        ['', ''],
        ['Cliente:', 'RETAIL DEMO SL'],
        ['CIF:', 'B12345678'],
        ['Dirección:', 'Calle Mayor 123, Madrid'],
    ]
    
    info_table = Table(info_data, colWidths=[50*mm, 100*mm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 20))
    
    # Conceptos
    story.append(Paragraph("CONCEPTOS", heading_style))
    concepts_data = [
        ['DESCRIPCIÓN', 'CANTIDAD', 'PRECIO', 'TOTAL'],
        ['Suministro de mercancías', '1', f'{amount - (amount * 0.21):.2f}€', f'{amount - (amount * 0.21):.2f}€'],
        ['', '', 'IVA (21%)', f'{amount * 0.21:.2f}€'],
        ['', '', 'TOTAL', f'{amount:.2f}€'],
    ]
    
    concepts_table = Table(concepts_data, colWidths=[80*mm, 25*mm, 30*mm, 30*mm])
    concepts_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ffebee')),
    ]))
    story.append(concepts_table)
    
    story.append(Spacer(1, 30))
    story.append(Paragraph(
        f"<b>ESTADO:</b> IMPAGADA - Vencida hace {days_overdue} días",
        ParagraphStyle('Alert', parent=styles['Normal'], textColor=colors.red, fontSize=12)
    ))
    
    doc.build(story)
    print(f"✅ Creado: {filename}")


def create_bank_statement():
    """Genera extracto bancario."""
    filename = OUTPUT_DIR / "06_Extracto_Bancario_Dic2023.pdf"
    doc = SimpleDocTemplate(str(filename), pagesize=A4)
    story = []
    
    story.append(Paragraph("BANCO EJEMPLO", title_style))
    story.append(Paragraph("EXTRACTO BANCARIO", title_style))
    story.append(Paragraph("Diciembre 2023", styles['Normal']))
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("Titular: RETAIL DEMO SL", styles['Normal']))
    story.append(Paragraph("Cuenta: ES12 1234 5678 9012 3456 7890", styles['Normal']))
    story.append(Spacer(1, 20))
    
    movements_data = [
        ['FECHA', 'CONCEPTO', 'CARGO', 'ABONO', 'SALDO'],
        ['01/12/2023', 'Saldo inicial', '', '', '8.500€'],
        ['05/12/2023', 'Pago nóminas', '15.000€', '', '-6.500€'],
        ['10/12/2023', 'Ingreso cliente', '', '12.000€', '5.500€'],
        ['12/12/2023', 'Pago SOCIO A (vinculado)', '8.000€', '', '-2.500€'],  # ⚠️ Pago preferente
        ['15/12/2023', 'Pago préstamo', '3.200€', '', '-5.700€'],
        ['18/12/2023', 'Pago SOCIO B (vinculado)', '5.000€', '', '-10.700€'],  # ⚠️ Pago preferente
        ['20/12/2023', 'Ingreso cliente', '', '14.200€', '3.500€'],
        ['', '', '', 'Saldo final:', '3.500€'],
    ]
    
    movements_table = Table(movements_data, colWidths=[25*mm, 65*mm, 25*mm, 25*mm, 25*mm])
    movements_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#fff3e0')),  # Pagos a vinculados
        ('BACKGROUND', (0, 6), (-1, 6), colors.HexColor('#fff3e0')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    story.append(movements_table)
    
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "<b>⚠️ ALERTA:</b> Se detectan pagos a socios/vinculados (12/12 y 18/12) por 13.000€ total.<br/>"
        "Posible pago preferente según Art. 164.2.3 Ley Concursal.",
        ParagraphStyle('Alert', parent=styles['Normal'], textColor=colors.orange, fontSize=10)
    ))
    
    doc.build(story)
    print(f"✅ Creado: {filename}")


def create_embargo_notice(entity, amount, reference, filename):
    """Genera aviso de embargo."""
    doc = SimpleDocTemplate(str(filename), pagesize=A4)
    story = []
    
    story.append(Paragraph(f"{entity}", title_style))
    story.append(Paragraph("AVISO DE EMBARGO", title_style))
    story.append(Spacer(1, 20))
    
    story.append(Paragraph(f"Referencia: {reference}", styles['Normal']))
    story.append(Paragraph(f"Fecha: 15 de noviembre de 2023", styles['Normal']))
    story.append(Spacer(1, 20))
    
    story.append(Paragraph(f"<b>Deudor:</b> RETAIL DEMO SL (CIF: B12345678)", styles['Normal']))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph(
        f"Se le notifica que se ha iniciado procedimiento de embargo por deudas pendientes "
        f"por importe de <b>{amount:,.2f}€</b> correspondientes a:",
        styles['Normal']
    ))
    story.append(Spacer(1, 10))
    
    if "Hacienda" in entity:
        details = [
            "- IVA 4T 2022: 18.000€",
            "- IVA 1T 2023: 22.000€",
            "- IVA 2T 2023: 28.000€",
        ]
    else:
        details = [
            "- Cuotas Seguridad Social Agosto 2023: 14.000€",
            "- Cuotas Seguridad Social Septiembre 2023: 14.000€",
            "- Cuotas Seguridad Social Octubre 2023: 14.000€",
        ]
    
    for detail in details:
        story.append(Paragraph(detail, styles['Normal']))
    
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "<b>REQUERIMIENTO:</b> Debe proceder al pago inmediato. En caso contrario, se "
        "procederá al embargo de bienes y derechos.",
        ParagraphStyle('Alert', parent=styles['Normal'], textColor=colors.red)
    ))
    
    doc.build(story)
    print(f"✅ Creado: {filename}")


def create_creditor_email():
    """Genera email de reclamación de acreedor."""
    filename = OUTPUT_DIR / "09_Email_Reclamacion_Acreedor.pdf"
    doc = SimpleDocTemplate(str(filename), pagesize=A4)
    story = []
    
    story.append(Paragraph("EMAIL - RECLAMACIÓN FORMAL", title_style))
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("<b>De:</b> juridico@proveedoralpha.com", styles['Normal']))
    story.append(Paragraph("<b>Para:</b> admin@retaildemo.com", styles['Normal']))
    story.append(Paragraph("<b>Fecha:</b> 20 de diciembre de 2023", styles['Normal']))
    story.append(Paragraph("<b>Asunto:</b> RECLAMACIÓN FORMAL - Factura 2023-001 IMPAGADA", styles['Normal']))
    story.append(Spacer(1, 20))
    
    email_text = """
    Estimados señores,
    
    Por medio de la presente, y en representación de PROVEEDOR ALPHA SL, nos dirigimos a ustedes 
    para reclamar FORMALMENTE el pago de la factura número 2023-001 por importe de 45.000€, 
    con vencimiento el 14 de septiembre de 2023.
    
    A fecha de hoy, transcurridos más de 3 meses desde el vencimiento, la factura continúa IMPAGADA 
    sin que hayamos recibido respuesta alguna a nuestros múltiples requerimientos telefónicos y escritos.
    
    Les informamos que, de no proceder al pago en el plazo de 10 días hábiles desde la recepción de 
    este correo, nos veremos obligados a:
    
    1. Iniciar procedimiento judicial de reclamación de cantidad
    2. Reclamar intereses de demora según Ley 3/2004
    3. Valorar la presentación de denuncia por alzamiento de bienes si procede
    
    Quedamos a la espera de su pronta respuesta y pago.
    
    Atentamente,
    
    Departamento Jurídico
    PROVEEDOR ALPHA SL
    """
    
    story.append(Paragraph(email_text.replace('\n', '<br/>'), styles['Normal']))
    
    doc.build(story)
    print(f"✅ Creado: {filename}")


def create_readme():
    """Genera README con información del caso."""
    filename = OUTPUT_DIR / "README.md"
    
    content = """# RETAIL DEMO SL - Caso de Prueba Concursal

## 📊 RESUMEN DEL CASO

**Empresa**: RETAIL DEMO SL  
**CIF**: B12345678  
**Sector**: Comercio minorista  
**Tamaño**: PYME (15 empleados)  
**Situación**: **INSOLVENCIA ACTUAL**

---

## 💰 SITUACIÓN FINANCIERA

### Balance (31/12/2023)
- **Activo Total**: 250.000€
- **Pasivo Total**: 480.000€
- **Patrimonio Neto**: **-230.000€** ⚠️
- **Ratio de Solvencia**: 0.52 (crítico)

### Cuenta de PyG (2023)
- **Ingresos**: 120.000€
- **Gastos**: 180.000€
- **Resultado**: **-60.000€** ⚠️

---

## ⚠️ RIESGOS DETECTABLES

### 1. Insolvencia Actual
- Patrimonio neto negativo de 230.000€
- Pasivo supera al activo en 230.000€
- Obligación legal de solicitar concurso (Art. 5 LC)

### 2. Pagos Preferentes (Art. 164.2.3 LC)
- **12/12/2023**: Pago a SOCIO A (vinculado) - 8.000€
- **18/12/2023**: Pago a SOCIO B (vinculado) - 5.000€
- **Total**: 13.000€ en pagos a vinculados con acreedores impagados

### 3. Facturas Vencidas >90 días
- Proveedor Alpha: 45.000€ (120+ días)
- Proveedor Beta: 32.000€ (105+ días)
- Proveedor Gamma: 28.000€ (95+ días)
- **Total deuda comercial vencida**: 105.000€

### 4. Deudas con Administraciones
- Hacienda: 68.000€ (IVA impagado)
- Seguridad Social: 42.000€ (cuotas impagadas)
- **Total deuda pública**: 110.000€ (avisos de embargo)

### 5. Retraso en Solicitud de Concurso
- Insolvencia conocida desde 31/12/2023
- Obligación de solicitar en plazo de 2 meses
- Riesgo de culpabilidad si no se solicita

---

## 📄 DOCUMENTOS INCLUIDOS

1. `01_Balance_Situacion_2023.pdf` - Balance con patrimonio neto negativo
2. `02_Cuenta_PyG_2023.pdf` - Pérdidas de 60.000€
3. `03_Factura_Proveedor_Alpha_45000.pdf` - Impagada 120+ días
4. `04_Factura_Proveedor_Beta_32000.pdf` - Impagada 105+ días
5. `05_Factura_Proveedor_Gamma_28000.pdf` - Impagada 95+ días
6. `06_Extracto_Bancario_Dic2023.pdf` - Con pagos a vinculados
7. `07_Aviso_Embargo_Hacienda.pdf` - Deuda IVA 68.000€
8. `08_Aviso_Embargo_SS.pdf` - Deuda SS 42.000€
9. `09_Email_Reclamacion_Acreedor.pdf` - Amenaza legal

---

## 🎯 ALERTAS ESPERADAS

El sistema DEBE detectar:

✅ **Insolvencia Actual** (Art. 2.2 LC)
✅ **Pagos Preferentes** (Art. 164.2.3 LC)
✅ **Retraso en Solicitud** (Art. 5 LC)
✅ **Deudas con Administraciones** (riesgo alto)
✅ **Acreedores Impagados** >90 días

---

## 🚀 CÓMO USAR ESTE CASO

### 1. Subir Documentos
```bash
# Desde Streamlit UI o API
POST /api/cases/{case_id}/documents
```

### 2. Ejecutar Análisis
```bash
GET /api/cases/{case_id}/analysis/alerts
```

### 3. Generar Informe Legal
```bash
POST /api/cases/{case_id}/legal-report
```

### 4. Descargar PDF Certificado
```bash
GET /api/cases/{case_id}/legal-report/pdf
```

---

## ✅ CRITERIO DE VALIDACIÓN

El sistema está funcionando correctamente SI:

- [x] Detecta insolvencia actual
- [x] Identifica pagos a vinculados
- [x] Alerta sobre facturas vencidas >90 días
- [x] Detecta deudas con administraciones
- [x] Recomienda solicitud inmediata de concurso
- [x] Genera PDF con evidencia documental

---

## 📚 REFERENCIAS LEGALES

- **Ley Concursal** (RDL 1/2020)
- **Art. 2.2**: Insolvencia actual (pasivo > activo)
- **Art. 5**: Obligación de solicitar concurso en 2 meses
- **Art. 164.2.3**: Pagos preferentes a vinculados
- **Art. 257-261**: Calificación culpable del concurso

---

**Generado automáticamente por Phoenix Legal - Sistema de Análisis Concursal**
"""
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Creado: {filename}")


def main():
    """Genera todos los documentos del caso de prueba."""
    print("\n🚀 Generando caso de prueba: RETAIL DEMO SL\n")
    print("=" * 60)
    
    # 1. Balance
    create_balance_sheet()
    
    # 2. Cuenta PyG
    create_pyg()
    
    # 3-5. Facturas impagadas
    create_invoice(
        "PROVEEDOR ALPHA SL",
        45000,
        "2023-001",
        120,
        OUTPUT_DIR / "03_Factura_Proveedor_Alpha_45000.pdf"
    )
    create_invoice(
        "PROVEEDOR BETA SL",
        32000,
        "2023-042",
        105,
        OUTPUT_DIR / "04_Factura_Proveedor_Beta_32000.pdf"
    )
    create_invoice(
        "PROVEEDOR GAMMA SL",
        28000,
        "2023-078",
        95,
        OUTPUT_DIR / "05_Factura_Proveedor_Gamma_28000.pdf"
    )
    
    # 6. Extracto bancario
    create_bank_statement()
    
    # 7-8. Avisos de embargo
    create_embargo_notice(
        "AGENCIA TRIBUTARIA - MINISTERIO DE HACIENDA",
        68000,
        "REF-AT-2023-98765",
        OUTPUT_DIR / "07_Aviso_Embargo_Hacienda.pdf"
    )
    create_embargo_notice(
        "TESORERÍA GENERAL DE LA SEGURIDAD SOCIAL",
        42000,
        "REF-SS-2023-54321",
        OUTPUT_DIR / "08_Aviso_Embargo_SS.pdf"
    )
    
    # 9. Email de acreedor
    create_creditor_email()
    
    # README
    create_readme()
    
    print("=" * 60)
    print(f"\n✅ CASO DE PRUEBA GENERADO EXITOSAMENTE\n")
    print(f"📁 Ubicación: {OUTPUT_DIR}")
    print(f"📄 Archivos: 10 documentos PDF + README.md")
    print(f"\n🎯 El caso está listo para probar en Phoenix Legal")
    print(f"\n🚀 Siguiente paso:")
    print(f"   1. Abrir Streamlit: http://localhost:8501")
    print(f"   2. Crear caso: 'RETAIL DEMO SL - Concurso 2026'")
    print(f"   3. Subir todos los PDFs de: {OUTPUT_DIR}")
    print(f"   4. Ejecutar análisis completo")
    print(f"   5. Generar informe legal")
    print(f"   6. Descargar PDF certificado\n")


if __name__ == "__main__":
    main()
