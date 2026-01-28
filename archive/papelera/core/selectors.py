# core/selectors.py
import pandas as pd

# Umbral configurable (forense básico)
IMPORTE_ALTO = 1000


def seleccionar_movimientos_sospechosos(df: pd.DataFrame) -> dict:
    """
    Devuelve un resumen forense del extracto bancario:
    - Movimientos negativos
    - Importes altos
    - Conceptos repetidos
    - Conceptos raros (texto corto o genérico)
    """

    resultado = {
        "total_registros": len(df),
        "salidas": [],
        "importes_altos": [],
        "conceptos_repetidos": [],
        "conceptos_raros": []
    }

    if df.empty or 'Importe' not in df.columns:
        return resultado

    df = df.copy()
    df['Importe'] = pd.to_numeric(df['Importe'], errors='coerce').fillna(0)
    df['Concepto'] = df['Concepto'].fillna("").astype(str)

    # 1️⃣ Salidas de dinero
    salidas = df[df['Importe'] < 0]
    resultado["salidas"] = salidas.to_dict(orient="records")

    # 2️⃣ Importes altos (absolutos)
    importes_altos = df[df['Importe'].abs() >= IMPORTE_ALTO]
    resultado["importes_altos"] = importes_altos.to_dict(orient="records")

    # 3️⃣ Conceptos repetidos (posibles pagos encubiertos)
    repetidos = (
        df.groupby('Concepto')
        .filter(lambda x: len(x) >= 3)
    )
    resultado["conceptos_repetidos"] = repetidos.to_dict(orient="records")

    # 4️⃣ Conceptos sospechosamente genéricos
    conceptos_raros = df[
        (df['Concepto'].str.len() < 6) |
        (df['Concepto'].str.lower().isin([
            'varios', 'otros', 'ajuste', 'pago', 'transferencia'
        ]))
    ]
    resultado["conceptos_raros"] = conceptos_raros.to_dict(orient="records")

    return resultado
