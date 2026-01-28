# core/matcher.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import timedelta
import pandas as pd

TOLERANCIA_IMPORTE = 1.0  # € diferencia máxima aceptada
VENTANA_DIAS = 7          # +/- días alrededor de la fecha de la factura


def _normalizar_importe(valor: Any) -> Optional[float]:
    if valor is None:
        return None
    try:
        s = str(valor).strip()
        s = s.replace("€", "").replace(" ", "")
        s = s.replace(".", "").replace(",", ".")
        return abs(float(s))
    except Exception:
        try:
            return abs(float(valor))
        except Exception:
            return None


def _normalizar_fecha(fecha: Any) -> Optional[pd.Timestamp]:
    if fecha is None or fecha == "":
        return None
    ts = pd.to_datetime(fecha, errors="coerce", dayfirst=True)
    if pd.isna(ts):
        return None
    return ts


def cruzar_banco_facturas(
    df_banco: pd.DataFrame,
    facturas: List[Dict[str, Any]],
    tolerancia_importe: float = TOLERANCIA_IMPORTE,
    ventana_dias: int = VENTANA_DIAS,
) -> Dict[str, Any]:
    resultado: Dict[str, Any] = {
        "coincidencias": [],
        "pagos_sin_factura": [],
        "facturas_sin_pago": [],
        "descuadres": [],
    }

    if df_banco is None or not isinstance(df_banco, pd.DataFrame) or df_banco.empty:
        resultado["facturas_sin_pago"] = facturas or []
        return resultado

    df = df_banco.copy()

    if "Importe" not in df.columns:
        resultado["facturas_sin_pago"] = facturas or []
        return resultado

    if "Fecha" not in df.columns:
        df["Fecha"] = None

    df["Importe_num"] = pd.to_numeric(df["Importe"], errors="coerce").fillna(0.0)
    df["Importe_abs"] = df["Importe_num"].abs()
    df["Fecha_ts"] = df["Fecha"].apply(_normalizar_fecha)

    df_salidas = df[df["Importe_num"] < 0].copy()

    if not facturas:
        resultado["pagos_sin_factura"] = df_salidas.to_dict(orient="records")
        return resultado

    usados_idx = set()
    facturas_sin_pago: List[Dict[str, Any]] = []

    for factura in facturas:
        imp_f = _normalizar_importe(factura.get("total_factura"))
        fec_f = _normalizar_fecha(factura.get("fecha_emision"))

        if imp_f is None or fec_f is None:
            facturas_sin_pago.append(factura)
            continue

        fmin = fec_f - timedelta(days=ventana_dias)
        fmax = fec_f + timedelta(days=ventana_dias)

        candidatos = df_salidas[
            df_salidas["Fecha_ts"].notna()
            & df_salidas["Fecha_ts"].between(fmin, fmax)
        ].copy()

        if candidatos.empty:
            facturas_sin_pago.append(factura)
            continue

        candidatos["diff_imp"] = (candidatos["Importe_abs"] - imp_f).abs()
        candidatos = candidatos.sort_values("diff_imp", ascending=True)

        mejor = candidatos.iloc[0]
        idx_mejor = mejor.name
        diff = float(mejor["diff_imp"])

        if diff <= tolerancia_importe and idx_mejor not in usados_idx:
            resultado["coincidencias"].append(
                {"factura": factura, "movimiento_bancario": mejor.drop(labels=["diff_imp"], errors="ignore").to_dict()}
            )
            usados_idx.add(idx_mejor)
        else:
            resultado["descuadres"].append(
                {
                    "factura": factura,
                    "mejor_candidato": mejor.drop(labels=["diff_imp"], errors="ignore").to_dict(),
                    "diferencia_importe": diff,
                    "tolerancia_importe": tolerancia_importe,
                }
            )
            facturas_sin_pago.append(factura)

    resultado["pagos_sin_factura"] = df_salidas[~df_salidas.index.isin(usados_idx)].to_dict(orient="records")
    resultado["facturas_sin_pago"] = facturas_sin_pago
    return resultado
