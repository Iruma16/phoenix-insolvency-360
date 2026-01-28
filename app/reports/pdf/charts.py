from io import BytesIO
from typing import Optional


def create_risk_distribution_chart(risks: list[dict]) -> Optional[BytesIO]:
    """
    Crea gráfico de barras con distribución de riesgos.

    CRÍTICO: Manejo correcto de recursos matplotlib:
    - Backend 'Agg' ANTES de import pyplot
    - plt.close(fig) SIEMPRE
    - finally con plt.close('all')

    Returns:
        BytesIO con imagen PNG o None si no hay datos
    """
    fig = None
    plt = None  # ✅ CRÍTICO: Inicializar antes del try
    try:
        import matplotlib

        matplotlib.use("Agg")  # CRÍTICO: Antes de import pyplot
        import matplotlib.pyplot as plt

        # Contar riesgos por severidad
        counts = {
            "Alto": sum(1 for r in risks if r.get("severity") == "high"),
            "Medio": sum(1 for r in risks if r.get("severity") == "medium"),
            "Bajo": sum(1 for r in risks if r.get("severity") == "low"),
        }

        if sum(counts.values()) == 0:
            return None

        # Crear figura
        fig, ax = plt.subplots(figsize=(8, 4), dpi=150)  # DPI fijo
        categories = list(counts.keys())
        values = list(counts.values())
        chart_colors = ["#dc2626", "#f59e0b", "#10b981"]

        bars = ax.bar(categories, values, color=chart_colors, width=0.6)

        # Añadir valores sobre las barras
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    height,
                    f"{int(height)}",
                    ha="center",
                    va="bottom",
                    fontweight="bold",
                )

        ax.set_ylabel("Cantidad", fontsize=11)
        ax.set_title("Distribución de Riesgos por Severidad", fontsize=13, fontweight="bold")
        ax.set_ylim(0, max(values) * 1.2 if values else 1)
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()

        # Guardar en buffer
        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        buf.seek(0)

        return buf

    except ImportError:
        # matplotlib no disponible - degradación elegante
        print("[INFO] matplotlib no disponible, gráfico omitido")
        return None
    except Exception as e:
        print(f"[WARN] Error creando gráfico de riesgos: {e}")
        return None
    finally:
        # ✅ CRÍTICO: Solo cerrar si plt existe (evita NameError si ImportError)
        if plt is not None:
            if fig is not None:
                plt.close(fig)
            plt.close("all")  # Seguridad extra


def create_timeline_chart(timeline: list[dict]) -> Optional[BytesIO]:
    """
    Crea gráfico de línea temporal de eventos.

    CRÍTICO: Normalización obligatoria de datos legales:
    - Validación de fechas
    - Orden explícito cronológico
    - Deduplicación por fecha
    - Manejo de recursos matplotlib

    Returns:
        BytesIO con imagen PNG o None si no hay datos válidos
    """
    fig = None
    plt = None  # ✅ CRÍTICO: Inicializar antes del try
    try:
        import matplotlib

        matplotlib.use("Agg")  # CRÍTICO: Antes de pyplot
        from datetime import datetime as dt

        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt

        if not timeline or len(timeline) < 2:
            return None

        # NORMALIZACIÓN OBLIGATORIA de datos
        events_clean = []
        for event in timeline[:20]:  # Límite razonable
            date_str = event.get("date")

            # Validación estricta
            if not date_str or date_str == "Fecha desconocida":
                continue

            # Parseo robusto con múltiples formatos
            date_obj = None
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y-%m", "%Y"]:
                try:
                    date_obj = dt.strptime(str(date_str).strip(), fmt)
                    break
                except (ValueError, AttributeError):
                    continue

            if date_obj:
                events_clean.append(
                    {
                        "date": date_obj,
                        "desc": str(event.get("description", "Sin descripción"))[:40],
                    }
                )

        # Validación: mínimo 2 eventos válidos
        if len(events_clean) < 2:
            print("[INFO] Timeline: menos de 2 eventos válidos, omitiendo gráfico")
            return None

        # ORDEN EXPLÍCITO cronológico
        events_clean.sort(key=lambda x: x["date"])

        # DEDUPLICACIÓN por fecha (evita superposición)
        seen_dates = set()
        events_unique = []
        for ev in events_clean:
            date_key = ev["date"].strftime("%Y-%m-%d")
            if date_key not in seen_dates:
                events_unique.append(ev)
                seen_dates.add(date_key)

        if len(events_unique) < 2:
            print("[INFO] Timeline: después de deduplicar quedan < 2 eventos")
            return None

        # Crear figura con DPI fijo
        fig, ax = plt.subplots(figsize=(10, 4), dpi=150)
        dates = [e["date"] for e in events_unique]
        y_values = list(range(len(dates)))

        ax.plot(
            dates,
            y_values,
            marker="o",
            linestyle="-",
            linewidth=2,
            markersize=8,
            color="#1e3a8a",
            markerfacecolor="#3b82f6",
        )

        # Formatear eje X
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.xticks(rotation=45, ha="right")

        ax.set_ylabel("Secuencia de Eventos", fontsize=11)
        ax.set_title("Línea Temporal de Eventos del Caso", fontsize=13, fontweight="bold")
        ax.grid(True, alpha=0.3, linestyle="--")
        plt.tight_layout()

        # Guardar en buffer
        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        buf.seek(0)

        return buf

    except ImportError:
        print("[INFO] matplotlib no disponible, timeline omitida")
        return None
    except Exception as e:
        print(f"[WARN] Error creando timeline: {e}")
        return None
    finally:
        # ✅ CRÍTICO: Solo cerrar si plt existe (evita NameError si ImportError)
        if plt is not None:
            if fig is not None:
                plt.close(fig)
            plt.close("all")
