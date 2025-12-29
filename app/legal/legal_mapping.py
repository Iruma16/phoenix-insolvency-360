"""
Diccionario de mapeo jurídico entre findings y artículos de la Ley Concursal.

Este módulo contiene únicamente datos estáticos (no lógica).
Mapea cada tipo de finding a artículos concretos y tipos de riesgo jurídico.

CONTROL DE CALIDAD:
- Cada artículo incluye metadatos de verificación (source, boe_url, last_verified)
- Los metadatos permiten trazabilidad y mantenimiento del catálogo
- last_verified indica la última fecha de verificación normativa
"""

LEGAL_MAP = {
    "accounting_irregularities": {
        "articles": [
            {
                "law": "Ley Concursal",
                "article": "art. 443.1º",
                "description": "Incumplimiento sustancial de la obligación de llevanza de contabilidad ordenada",
                "source": "Texto Refundido LC",
                "boe_url": "https://www.boe.es/buscar/act.php?id=BOE-A-2020-4855",
                "last_verified": "2024-12-30",
                "notes": "Precepto clave en calificación culpable por irregularidades contables"
            },
            {
                "law": "Ley Concursal",
                "article": "art. 444.1",
                "description": "Agravamiento de la insolvencia por llevanza irregular de contabilidad",
                "source": "Texto Refundido LC",
                "boe_url": "https://www.boe.es/buscar/act.php?id=BOE-A-2020-4855",
                "last_verified": "2024-12-30",
                "notes": "Presunción de dolo o culpa grave en calificación culpable"
            }
        ],
        "risk_types": [
            "calificación culpable",
            "responsabilidad patrimonial personal"
        ]
    },
    "delay_filing": {
        "articles": [
            {
                "law": "Ley Concursal",
                "article": "art. 443.3º",
                "description": "Retraso relevante en la solicitud del concurso",
                "source": "Texto Refundido LC",
                "boe_url": "https://www.boe.es/buscar/act.php?id=BOE-A-2020-4855",
                "last_verified": "2024-12-30",
                "notes": "Incumplimiento del deber del art. 5 LC - dos meses desde conocimiento de insolvencia"
            },
            {
                "law": "Ley Concursal",
                "article": "art. 5",
                "description": "Deber de solicitud de concurso voluntario",
                "source": "Texto Refundido LC",
                "boe_url": "https://www.boe.es/buscar/act.php?id=BOE-A-2020-4855",
                "last_verified": "2024-12-30",
                "notes": "Plazo de 2 meses desde conocimiento de insolvencia"
            }
        ],
        "risk_types": [
            "calificación culpable"
        ]
    },
    "document_inconsistency": {
        "articles": [
            {
                "law": "Ley Concursal",
                "article": "art. 443.2º",
                "description": "Inexactitud grave en los documentos aportados al procedimiento",
                "source": "Texto Refundido LC",
                "boe_url": "https://www.boe.es/buscar/act.php?id=BOE-A-2020-4855",
                "last_verified": "2024-12-30",
                "notes": "Aplicable a documentos presentados con la solicitud y durante el concurso"
            },
            {
                "law": "Ley Concursal",
                "article": "art. 444.2",
                "description": "Agravamiento por salida fraudulenta de bienes o inexactitud grave",
                "source": "Texto Refundido LC",
                "boe_url": "https://www.boe.es/buscar/act.php?id=BOE-A-2020-4855",
                "last_verified": "2024-12-30",
                "notes": "Presunción de dolo o culpa grave si hay inexactitud grave en documentos"
            }
        ],
        "risk_types": [
            "calificación culpable"
        ]
    },
    "documentation_gap": {
        "articles": [
            {
                "law": "Ley Concursal",
                "article": "art. 443.4º",
                "description": "Falta de colaboración o de documentación esencial",
                "source": "Texto Refundido LC",
                "boe_url": "https://www.boe.es/buscar/act.php?id=BOE-A-2020-4855",
                "last_verified": "2024-12-30",
                "notes": "Incumplimiento de deberes de colaboración e información al administrador concursal"
            },
            {
                "law": "Ley Concursal",
                "article": "art. 172.2",
                "description": "Deber de colaboración del deudor con la administración concursal",
                "source": "Texto Refundido LC",
                "boe_url": "https://www.boe.es/buscar/act.php?id=BOE-A-2020-4855",
                "last_verified": "2024-12-30",
                "notes": "Obligación de facilitar información y documentación necesaria"
            }
        ],
        "risk_types": [
            "calificación culpable"
        ]
    }
}
