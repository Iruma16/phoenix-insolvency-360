from __future__ import annotations

from app.graphs.state import AuditState

CASE_RETAIL_001: AuditState = {
    "case_id": "CASE_RETAIL_001",
    "company_profile": {
        "type": "SL",
        "sector": "retail",
        "size": "pyme",
        "employees": 12,
        "years_active": 10,
        "issue_start_year": 2023,
    },
    "documents": [
        {
            "doc_id": "DOC_BALANCE_2023",
            "doc_type": "balance_pyg",
            "content": "Balances y PyG 2022–2023 muestran pérdidas progresivas desde Q1 2023.",
            "date": "2023-12-31",
        },
        {
            "doc_id": "DOC_ACTA_NOV_2023",
            "doc_type": "acta_junta",
            "content": "Acta (noviembre 2023): se reconoce deterioro y se acuerda buscar financiación / reestructuración.",
            "date": "2023-11-15",
        },
        {
            "doc_id": "DOC_EMAILS_PROV",
            "doc_type": "emails_proveedores",
            "content": "Emails (desde junio 2023) negociando plazos de pago con proveedores clave.",
            "date": "2023-06-10",
        },
        {
            "doc_id": "DOC_TESORERIA_ENE_2024",
            "doc_type": "informe_tesoreria",
            "content": "Informe tesorería (enero 2024): se constata insolvencia inminente tras fracasar financiación.",
            "date": "2024-01-20",
        },
    ],
    "timeline": [],
    "risks": [],
    "missing_documents": [],
    "legal_findings": [],
    "notes": None,
    "report": None,
}

CASE_RETAIL_002: AuditState = {
    "case_id": "CASE_RETAIL_002",
    "company_profile": {
        "type": "SL",
        "sector": "retail",
        "size": "pyme",
        "employees": 8,
        "years_active": 7,
        "issue_start_year": 2023,
    },
    "documents": [
        {
            "doc_id": "DOC_BALANCE_2023_002",
            "doc_type": "balance_pyg",
            "content": "Balances y PyG 2023 muestran pérdidas progresivas desde Q2 2023. Patrimonio neto negativo desde octubre.",
            "date": "2023-12-31",
        },
        {
            "doc_id": "DOC_ACTA_SEP_2023_002",
            "doc_type": "acta_junta",
            "content": "Acta (septiembre 2023): La junta manifiesta que la situación es controlada y que se espera recuperación en el próximo ejercicio. Se acuerda mantener la actividad.",
            "date": "2023-09-15",
        },
        {
            "doc_id": "DOC_EMAILS_PROV_002",
            "doc_type": "emails_proveedores",
            "content": "Emails (julio 2023) negociando aplazamientos con proveedores principales. No se alcanza acuerdo formal definitivo.",
            "date": "2023-07-01",
        },
        {
            "doc_id": "DOC_EMAILS_BANCO_002",
            "doc_type": "emails_banco",
            "content": "Emails (agosto 2023) solicitando línea de crédito adicional al banco. El banco solicita más garantías pero no se cierra operación.",
            "date": "2023-08-10",
        },
        {
            "doc_id": "DOC_TESORERIA_ENE_2024_002",
            "doc_type": "informe_tesoreria",
            "content": "Informe tesorería (enero 2024): se constata insolvencia actual tras fracasar negociaciones con banco y proveedores.",
            "date": "2024-01-25",
        },
    ],
    "timeline": [],
    "risks": [],
    "missing_documents": [],
    "legal_findings": [],
    "notes": None,
    "report": None,
}

CASE_RETAIL_003: AuditState = {
    "case_id": "CASE_RETAIL_003",
    "company_profile": {
        "type": "SL",
        "sector": "retail",
        "size": "pyme",
        "employees": 6,
        "years_active": 5,
        "issue_start_year": 2022,
    },
    "documents": [
        {
            "doc_id": "DOC_BALANCE_2023_003",
            "doc_type": "balance_pyg",
            "content": "Balance PyG 2023: pérdidas acumuladas severas desde 2022. Patrimonio neto negativo consolidado. Fondos propios inexistentes.",
            "date": "2023-12-31",
        },
        {
            "doc_id": "DOC_ACTA_JUN_2023_003",
            "doc_type": "acta_junta",
            "content": "Acta (junio 2023): La junta determina que la empresa es viable y que la situación es controlada. Se rechaza propuesta de disolución.",
            "date": "2023-06-30",
        },
        {
            "doc_id": "DOC_EMAILS_PROV_003",
            "doc_type": "emails_proveedores",
            "content": "Emails (marzo 2023): Proveedores exigen pago inmediato de deudas vencidas hace 6 meses. Amenaza de acciones legales.",
            "date": "2023-03-10",
        },
        {
            "doc_id": "DOC_INFORME_CONTABLE_003",
            "doc_type": "informe_contable",
            "content": "Informe contable (octubre 2023): No consta contabilidad ordenada. No se han depositado cuentas anuales desde 2021. Irregularidades detectadas en el registro.",
            "date": "2023-10-01",
        },
        {
            "doc_id": "DOC_PAGOS_SOSPECHOSOS_003",
            "doc_type": "operaciones_vinculadas",
            "content": "Registro de operaciones (mayo 2023): Pago de 45.000€ a proveedor vinculado con socio mayoritario, sin factura justificativa clara.",
            "date": "2023-05-20",
        },
        {
            "doc_id": "DOC_TESORERIA_FEB_2024_003",
            "doc_type": "informe_tesoreria",
            "content": "Informe tesorería (febrero 2024): Se reconoce insolvencia grave desde al menos 8 meses. Imposibilidad de atender obligaciones corrientes.",
            "date": "2024-02-15",
        },
    ],
    "timeline": [],
    "risks": [],
    "missing_documents": [],
    "legal_findings": [],
    "notes": None,
    "report": None,
}
