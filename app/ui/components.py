"""
Componentes reutilizables para la UI de Phoenix Legal.

Separa la lógica de render en funciones específicas para:
- Mejor mantenibilidad
- Reutilización de código
- Testing más fácil
"""
import json
import logging
from collections import Counter, defaultdict
from typing import Any, Optional

import streamlit as st

# Importar helpers modularizados
from app.ui.components_modules.common import get_confidence_emoji, get_field_value
from app.ui.components_modules.evidence import render_evidence_expander

# Importar settings para feature flags
try:
    from app.core.config import get_settings

    settings = get_settings()
except ImportError:
    # Fallback si no se puede importar (testing, etc.)
    class _FallbackSettings:
        enable_interactive_charts = True
        enable_advanced_filters = True
        enable_drill_down = True

    settings = _FallbackSettings()


# =========================================================
# HELPER: CACHING DE PREPARACIÓN DE DATOS (PERFORMANCE)
# =========================================================


@st.cache_data(ttl=300, show_spinner=False)
def _prepare_ratio_chart_data(ratios_json: str) -> dict[str, Any]:
    """
    Prepara datos de ratios para gráfico (CACHEADO).

    Args:
        ratios_json: JSON string de ratios (para hasheable)

    Returns:
        Dict con names, values, colors, interpretations
    """
    ratios_dicts = json.loads(ratios_json)

    names = []
    values = []
    colors = []
    interpretations = []

    for ratio in ratios_dicts:
        if ratio.get("value") is not None:
            names.append(ratio.get("name", "Ratio"))
            values.append(ratio.get("value", 0))

            # Color según status
            status = ratio.get("status", "stable")
            color_map = {
                "critical": "#dc2626",
                "red": "#dc2626",
                "concerning": "#f59e0b",
                "yellow": "#f59e0b",
                "stable": "#10b981",
                "green": "#10b981",
            }
            colors.append(color_map.get(status, "#6b7280"))
            interpretations.append(ratio.get("interpretation", ""))

    return {"names": names, "values": values, "colors": colors, "interpretations": interpretations}


@st.cache_data(ttl=300, show_spinner=False)
def _prepare_balance_chart_data(balance_json: str) -> dict[str, Any]:
    """
    Prepara datos de balance para gráficos (CACHEADO).

    Args:
        balance_json: JSON string de balance

    Returns:
        Dict con todos los valores necesarios para gráficos
    """
    balance_dict = json.loads(balance_json)

    def get_value(field_dict):
        if field_dict is None:
            return None
        if isinstance(field_dict, dict):
            return field_dict.get("value")
        return field_dict

    return {
        "ac": get_value(balance_dict.get("activo_corriente")),
        "anc": get_value(balance_dict.get("activo_no_corriente")),
        "at": get_value(balance_dict.get("activo_total")),
        "pc": get_value(balance_dict.get("pasivo_corriente")),
        "pnc": get_value(balance_dict.get("pasivo_no_corriente")),
        "pt": get_value(balance_dict.get("pasivo_total")),
        "pn": get_value(balance_dict.get("patrimonio_neto")),
    }


@st.cache_data(ttl=300, show_spinner=False)
def _prepare_patterns_chart_data(alerts_json: str) -> dict[str, Any]:
    """
    Prepara datos de patrones sospechosos para gráficos (CACHEADO).

    Args:
        alerts_json: JSON string de alerts

    Returns:
        Dict con datos agregados para gráficos
    """
    alerts = json.loads(alerts_json)

    # Contar por categoría
    category_counts = Counter(a.get("category", "otros") for a in alerts)

    # Score promedio por categoría
    category_scores = {}
    for cat in category_counts.keys():
        cat_alerts = [a for a in alerts if a.get("category", "otros") == cat]
        category_scores[cat] = sum(a.get("severity_score", 0) for a in cat_alerts) / len(cat_alerts)

    # Contar por severidad
    severity_counts = Counter(a.get("severity", "medium") for a in alerts)

    # Top alerts por score
    sorted_alerts = sorted(alerts, key=lambda x: x.get("severity_score", 0), reverse=True)
    top_alerts = sorted_alerts[:5]

    return {
        "category_counts": dict(category_counts),
        "category_scores": category_scores,
        "severity_counts": dict(severity_counts),
        "top_alerts": top_alerts,
        "total": len(alerts),
    }


# =========================================================
# HELPER: FALLBACKS SIMPLES (SIN PLOTLY)
# =========================================================


def _render_ratios_simple(ratios_dicts: list[dict[str, Any]]):
    """
    Renderiza ratios sin plotly (fallback simple con métricas).
    Degradación controlada cuando plotly no disponible.
    """
    st.info("💡 Gráficos interactivos deshabilitados. Mostrando vista simplificada.")

    for ratio in ratios_dicts:
        status = ratio.get("status", "stable")
        status_emoji_map = {
            "critical": "🔴",
            "concerning": "🟡",
            "stable": "🟢",
            "red": "🔴",
            "yellow": "🟡",
            "green": "🟢",
        }
        emoji = status_emoji_map.get(status, "⚪")

        name = ratio.get("name")
        value = ratio.get("value")
        interpretation = ratio.get("interpretation")
        formula = ratio.get("formula")
        confidence = ratio.get("confidence", "medium")

        conf_emoji_map = {"high": "✅", "medium": "🟡", "low": "❓"}
        conf_emoji = conf_emoji_map.get(confidence, "")

        st.write(f"{emoji} **{name}** {conf_emoji}")
        if value is not None:
            st.metric("Ratio", f"{value:.2f}")
        st.write(f"   {interpretation}")
        st.caption(f"   Fórmula: {formula}")
        st.markdown("")


def _render_balance_simple(balance_dict: dict[str, Any]):
    """
    Renderiza balance sin plotly (fallback simple con métricas).
    """
    st.info("💡 Gráficos interactivos deshabilitados. Mostrando solo métricas.")
    # No hacer nada adicional, las métricas ya se muestran en render_balance_block


# =========================================================
# NOTA: Helpers movidos a components_modules/
# - get_field_value → components_modules/common.py
# - get_confidence_emoji → components_modules/common.py
# - render_evidence_expander → components_modules/evidence.py
# =========================================================


# =========================================================
# COMPONENTE 1: BALANCE
# =========================================================


def render_balance_block(
    balance_dict: Optional[dict[str, Any]], profit_loss_dict: Optional[dict[str, Any]]
):
    """Renderiza el bloque de datos contables estructurados."""
    st.subheader("1️⃣ DATOS CONTABLES ESTRUCTURADOS")

    if balance_dict:
        st.markdown("───────────────────────────────────────────────────────────")

        # Metadata
        overall_conf = balance_dict.get("overall_confidence", "LOW")
        conf_emoji = {"HIGH": "✅", "MEDIUM": "🟡", "LOW": "❓"}.get(overall_conf, "❓")
        source_date = balance_dict.get("source_date", "N/A")
        st.write(f"📄 **Fecha:** {source_date} {conf_emoji} Confianza: **{overall_conf}**")

        st.markdown("")

        # Datos en columnas
        col1, col2 = st.columns(2)

        with col1:
            # Activo Corriente
            ac = balance_dict.get("activo_corriente")
            ac_val = get_field_value(ac)
            if ac_val is not None:
                emoji = get_confidence_emoji(ac)
                st.metric("Activo Corriente", f"{ac_val:,.0f} € {emoji}")
                if isinstance(ac, dict) and ac.get("evidence"):
                    render_evidence_expander(ac["evidence"], "🔍 Ver origen del dato")

            # Activo Total
            at = balance_dict.get("activo_total")
            at_val = get_field_value(at)
            if at_val is not None:
                emoji = get_confidence_emoji(at)
                st.metric("Activo Total", f"{at_val:,.0f} € {emoji}")
                if isinstance(at, dict) and at.get("evidence"):
                    render_evidence_expander(at["evidence"], "🔍 Ver origen del dato")

            # Patrimonio Neto
            pn = balance_dict.get("patrimonio_neto")
            pn_val = get_field_value(pn)
            if pn_val is not None:
                emoji = get_confidence_emoji(pn)
                delta_color = "off" if pn_val < 0 else "normal"
                st.metric(
                    f"Patrimonio Neto {emoji}",
                    f"{pn_val:,.0f} €",
                    delta="❌ Negativo" if pn_val < 0 else "✅ Positivo",
                    delta_color=delta_color,
                )
                if isinstance(pn, dict) and pn.get("evidence"):
                    render_evidence_expander(pn["evidence"], "🔍 Ver origen del dato")

        with col2:
            # Pasivo Corriente
            pc = balance_dict.get("pasivo_corriente")
            pc_val = get_field_value(pc)
            if pc_val is not None:
                emoji = get_confidence_emoji(pc)
                st.metric("Pasivo Corriente", f"{pc_val:,.0f} € {emoji}")
                if isinstance(pc, dict) and pc.get("evidence"):
                    render_evidence_expander(pc["evidence"], "🔍 Ver origen del dato")

            # Pasivo Total
            pt = balance_dict.get("pasivo_total")
            pt_val = get_field_value(pt)
            if pt_val is not None:
                emoji = get_confidence_emoji(pt)
                st.metric("Pasivo Total", f"{pt_val:,.0f} € {emoji}")
                if isinstance(pt, dict) and pt.get("evidence"):
                    render_evidence_expander(pt["evidence"], "🔍 Ver origen del dato")

        # PyG
        if profit_loss_dict:
            resultado = profit_loss_dict.get("resultado_ejercicio")
            res_val = get_field_value(resultado)
            if res_val is not None:
                emoji = get_confidence_emoji(resultado)
                delta_color = "off" if res_val < 0 else "normal"
                st.metric(
                    f"Resultado del Ejercicio {emoji}",
                    f"{res_val:,.0f} €",
                    delta="❌ Pérdidas" if res_val < 0 else "✅ Beneficios",
                    delta_color=delta_color,
                )
                if isinstance(resultado, dict) and resultado.get("evidence"):
                    render_evidence_expander(resultado["evidence"], "🔍 Ver origen del dato")

        # GRÁFICO INTERACTIVO DE COMPOSICIÓN PATRIMONIAL
        st.markdown("---")
        st.write("**📊 Composición Patrimonial (Drill-down)**")

        try:
            import plotly.graph_objects as go

            # Obtener valores DIRECTAMENTE del backend (sin cálculos en UI)
            ac_val = get_field_value(balance_dict.get("activo_corriente"))
            anc_val = get_field_value(
                balance_dict.get("activo_no_corriente")
            )  # ← Ya viene calculado del backend
            at_val = get_field_value(balance_dict.get("activo_total"))
            pc_val = get_field_value(balance_dict.get("pasivo_corriente"))
            pnc_val = get_field_value(
                balance_dict.get("pasivo_no_corriente")
            )  # ← Ya viene calculado del backend
            pt_val = get_field_value(balance_dict.get("pasivo_total"))
            pn_val = get_field_value(balance_dict.get("patrimonio_neto"))

            if at_val and pt_val and pn_val:
                # Selector de tipo de gráfico
                chart_type = st.radio(
                    "Tipo de gráfico",
                    ["🍰 Composición (Pie)", "📊 Comparativa (Barras)", "🌳 Estructura (Treemap)"],
                    horizontal=True,
                    key="balance_chart_type",
                )

                if chart_type == "🍰 Composición (Pie)":
                    # Pie chart de Activo vs Pasivo+PN
                    fig = go.Figure(
                        data=[
                            go.Pie(
                                labels=["Activo Total", "Pasivo Total", "Patrimonio Neto"],
                                values=[at_val, pt_val, abs(pn_val)],
                                hole=0.3,
                                marker=dict(colors=["#3b82f6", "#ef4444", "#10b981"]),
                                textinfo="label+percent",
                                hovertemplate="<b>%{label}</b><br>%{value:,.0f} €<br>%{percent}<extra></extra>",
                            )
                        ]
                    )

                    fig.update_layout(title="Composición Patrimonial", height=400)

                elif chart_type == "📊 Comparativa (Barras)":
                    # Barras comparativas
                    labels = []
                    values = []
                    colors = []

                    if ac_val:
                        labels.append("Activo Corriente")
                        values.append(ac_val)
                        colors.append("#60a5fa")
                    if anc_val and anc_val > 0:
                        labels.append("Activo No Corriente")
                        values.append(anc_val)
                        colors.append("#3b82f6")
                    if pc_val:
                        labels.append("Pasivo Corriente")
                        values.append(pc_val)
                        colors.append("#fca5a5")
                    if pnc_val and pnc_val > 0:
                        labels.append("Pasivo No Corriente")
                        values.append(pnc_val)
                        colors.append("#ef4444")
                    if pn_val:
                        labels.append("Patrimonio Neto")
                        values.append(abs(pn_val))
                        colors.append("#10b981" if pn_val > 0 else "#f59e0b")

                    fig = go.Figure(
                        data=[
                            go.Bar(
                                x=labels,
                                y=values,
                                marker=dict(color=colors),
                                text=[f"{v:,.0f} €" for v in values],
                                textposition="auto",
                                hovertemplate="<b>%{x}</b><br>%{y:,.0f} €<extra></extra>",
                            )
                        ]
                    )

                    fig.update_layout(
                        title="Comparativa de Masas Patrimoniales",
                        yaxis_title="Importe (€)",
                        height=400,
                    )

                else:  # Treemap
                    # Estructura jerárquica
                    labels_tree = ["Total"]
                    parents_tree = [""]
                    values_tree = [at_val + pt_val + abs(pn_val)]
                    colors_tree = ["#f3f4f6"]

                    # Activo
                    labels_tree.append("ACTIVO")
                    parents_tree.append("Total")
                    values_tree.append(at_val)
                    colors_tree.append("#3b82f6")

                    if ac_val:
                        labels_tree.append("Activo Corriente")
                        parents_tree.append("ACTIVO")
                        values_tree.append(ac_val)
                        colors_tree.append("#60a5fa")

                    if anc_val and anc_val > 0:
                        labels_tree.append("Activo No Corriente")
                        parents_tree.append("ACTIVO")
                        values_tree.append(anc_val)
                        colors_tree.append("#2563eb")

                    # Pasivo
                    labels_tree.append("PASIVO")
                    parents_tree.append("Total")
                    values_tree.append(pt_val)
                    colors_tree.append("#ef4444")

                    if pc_val:
                        labels_tree.append("Pasivo Corriente")
                        parents_tree.append("PASIVO")
                        values_tree.append(pc_val)
                        colors_tree.append("#fca5a5")

                    if pnc_val and pnc_val > 0:
                        labels_tree.append("Pasivo No Corriente")
                        parents_tree.append("PASIVO")
                        values_tree.append(pnc_val)
                        colors_tree.append("#dc2626")

                    # Patrimonio Neto
                    labels_tree.append("Patrimonio Neto")
                    parents_tree.append("Total")
                    values_tree.append(abs(pn_val))
                    colors_tree.append("#10b981" if pn_val > 0 else "#f59e0b")

                    fig = go.Figure(
                        go.Treemap(
                            labels=labels_tree,
                            parents=parents_tree,
                            values=values_tree,
                            marker=dict(colors=colors_tree),
                            textinfo="label+value+percent parent",
                            hovertemplate="<b>%{label}</b><br>%{value:,.0f} €<br>%{percentParent}<extra></extra>",
                        )
                    )

                    fig.update_layout(title="Estructura Patrimonial Jerárquica", height=500)

                st.plotly_chart(fig, use_container_width=True)

        except ImportError:
            st.info(
                "💡 Instala plotly para ver gráficos interactivos: `pip install plotly==5.18.0`"
            )
        except Exception as e:
            st.warning(f"⚠️ Error al generar gráfico: {str(e)}")

    else:
        st.warning(
            "⚠️ No se encontraron datos de Balance. Sube un documento de balance para ver análisis."
        )

    st.markdown("───────────────────────────────────────────────────────────")


# =========================================================
# COMPONENTE 2: CRÉDITOS
# =========================================================


def render_credits_block(credits_dicts: list[dict[str, Any]], total_debt: Optional[float]):
    """Renderiza el bloque de clasificación de créditos."""
    st.subheader("2️⃣ CLASIFICACIÓN DE CRÉDITOS")
    st.markdown("───────────────────────────────────────────────────────────")

    if credits_dicts and total_debt:
        st.write(f"**Total Pasivo:** {total_debt:,.0f} €")
        st.markdown("")

        # Agrupar por tipo
        by_type = defaultdict(list)
        for credit in credits_dicts:
            by_type[credit.get("credit_type")].append(credit)

        # Privilegiados Especiales
        if "privilegiado_especial" in by_type:
            especiales = by_type["privilegiado_especial"]
            total_esp = sum([c.get("amount", 0) for c in especiales])
            pct = (total_esp / total_debt * 100) if total_debt > 0 else 0
            st.write(f"🔴 **Créditos Privilegiados Especiales:** {total_esp:,.0f} € ({pct:.0f}%)")

            for c in especiales:
                creditor = c.get("creditor_name", "Desconocido")
                desc = c.get("description", "")
                amount = c.get("amount", 0)

                with st.expander(f"   └─ {creditor} - {amount:,.0f} €"):
                    st.write(f"**Descripción:** {desc}")
                    if c.get("evidence"):
                        render_evidence_expander(c["evidence"])
            st.markdown("")

        # Privilegiados Generales
        if "privilegiado_general" in by_type:
            generales = by_type["privilegiado_general"]
            total_gen = sum([c.get("amount", 0) for c in generales])
            pct = (total_gen / total_debt * 100) if total_debt > 0 else 0
            st.write(f"🟡 **Créditos Privilegiados Generales:** {total_gen:,.0f} € ({pct:.0f}%)")

            for c in generales:
                creditor = c.get("creditor_name", "Desconocido")
                desc = c.get("description", "")
                amount = c.get("amount", 0)

                with st.expander(f"   └─ {creditor} - {amount:,.0f} €"):
                    st.write(f"**Descripción:** {desc}")
                    if c.get("evidence"):
                        render_evidence_expander(c["evidence"])
            st.markdown("")

        # Ordinarios
        if "ordinario" in by_type:
            ordinarios = by_type["ordinario"]
            total_ord = sum([c.get("amount", 0) for c in ordinarios])
            pct = (total_ord / total_debt * 100) if total_debt > 0 else 0
            st.write(f"⚪ **Créditos Ordinarios:** {total_ord:,.0f} € ({pct:.0f}%)")

            # Mostrar solo primeros 3 expandidos
            for i, c in enumerate(ordinarios[:3]):
                creditor = c.get("creditor_name", "Proveedor")
                desc = c.get("description", "")
                amount = c.get("amount", 0)

                with st.expander(f"   └─ {creditor} - {amount:,.0f} €"):
                    st.write(f"**Descripción:** {desc}")
                    if c.get("evidence"):
                        render_evidence_expander(c["evidence"])

            if len(ordinarios) > 3:
                st.write(f"   └─ ... y {len(ordinarios) - 3} más")
    else:
        st.info("ℹ️ No se detectaron créditos clasificables. Sube facturas, embargos o contratos.")

    st.markdown("───────────────────────────────────────────────────────────")


# =========================================================
# COMPONENTE 3: RATIOS
# =========================================================


def render_ratios_block(ratios_dicts: list[dict[str, Any]]):
    """Renderiza el bloque de ratios financieros CON GRÁFICOS INTERACTIVOS."""
    st.subheader("3️⃣ RATIOS FINANCIEROS (SEMÁFORO)")
    st.markdown("───────────────────────────────────────────────────────────")

    if ratios_dicts:
        # Mostrar modo de visualización
        view_mode = st.radio(
            "Modo de vista",
            ["📊 Gráfico Interactivo", "📋 Lista Detallada"],
            horizontal=True,
            key="ratios_view_mode",
        )

        if view_mode == "📊 Gráfico Interactivo":
            # Verificar feature flag primero
            if not settings.enable_interactive_charts:
                _render_ratios_simple(ratios_dicts)
            else:
                # Preparar datos para gráfico (CACHEADO para performance)
                try:
                    import plotly.graph_objects as go

                    # Usar función cacheada para preparar datos
                    ratios_json = json.dumps(ratios_dicts, sort_keys=True)
                    chart_data = _prepare_ratio_chart_data(ratios_json)

                    names = chart_data["names"]
                    values = chart_data["values"]
                    colors = chart_data["colors"]

                    if values:
                        # Crear gráfico de barras horizontal interactivo
                        fig = go.Figure(
                            data=[
                                go.Bar(
                                    y=names,
                                    x=values,
                                    orientation="h",
                                    marker=dict(color=colors),
                                    text=[f"{v:.2f}" for v in values],
                                    textposition="auto",
                                    hovertemplate="<b>%{y}</b><br>Valor: %{x:.2f}<br><extra></extra>",
                                )
                            ]
                        )

                        fig.update_layout(
                            title="Ratios Financieros - Vista Comparativa",
                            xaxis_title="Valor del Ratio",
                            yaxis_title="",
                            height=400,
                            showlegend=False,
                            hovermode="closest",
                        )

                        st.plotly_chart(fig, use_container_width=True)

                        # Selector de ratio para drill-down
                        st.markdown("---")
                        st.write("**🔍 Detalle de Ratio (Drill-down)**")

                        selected_ratio_name = st.selectbox(
                            "Selecciona un ratio para ver detalles",
                            names,
                            key="ratio_drilldown_select",
                        )

                        # Mostrar detalle del ratio seleccionado
                        selected_ratio = next(
                            (r for r in ratios_dicts if r.get("name") == selected_ratio_name), None
                        )

                        if selected_ratio:
                            col1, col2 = st.columns(2)

                            with col1:
                                st.metric(
                                    "Valor",
                                    f"{selected_ratio.get('value', 0):.2f}",
                                    help="Valor calculado del ratio",
                                )

                                status = selected_ratio.get("status", "stable")
                                status_labels = {
                                    "critical": "🔴 CRÍTICO",
                                    "red": "🔴 CRÍTICO",
                                    "concerning": "🟡 PREOCUPANTE",
                                    "yellow": "🟡 PREOCUPANTE",
                                    "stable": "🟢 ESTABLE",
                                    "green": "🟢 ESTABLE",
                                }
                                st.metric("Estado", status_labels.get(status, status.upper()))

                            with col2:
                                confidence = selected_ratio.get("confidence", "medium")
                                st.metric("Confianza", confidence.upper())
                                st.caption(f"**Fórmula:** {selected_ratio.get('formula', 'N/A')}")

                            # Interpretación
                            st.write("**Interpretación:**")
                            st.info(
                                selected_ratio.get(
                                    "interpretation", "Sin interpretación disponible"
                                )
                            )

                            # Componentes del cálculo (si existen)
                            if selected_ratio.get("components"):
                                st.write("**Componentes del cálculo:**")
                                for comp_name, comp_value in selected_ratio["components"].items():
                                    st.write(f"- {comp_name}: {comp_value:,.2f} €")

                except ImportError:
                    st.warning("⚠️ plotly no instalado. Usando vista simplificada.")
                    _render_ratios_simple(ratios_dicts)
                except Exception as e:
                    st.error(f"Error al generar gráfico: {str(e)}")
                    _render_ratios_simple(ratios_dicts)

        if view_mode == "📋 Lista Detallada":
            # Vista original (lista)
            for ratio in ratios_dicts:
                status = ratio.get("status", "stable")
                status_emoji_map = {
                    "critical": "🔴",
                    "concerning": "🟡",
                    "stable": "🟢",
                    "red": "🔴",
                    "yellow": "🟡",
                    "green": "🟢",
                }
                emoji = status_emoji_map.get(status, "⚪")

                name = ratio.get("name")
                interpretation = ratio.get("interpretation")
                value = ratio.get("value")
                formula = ratio.get("formula")
                confidence = ratio.get("confidence", "medium")

                conf_emoji_map = {"high": "✅", "medium": "🟡", "low": "❓"}
                conf_emoji = conf_emoji_map.get(confidence, "")

                st.write(f"{emoji} **{name}** {conf_emoji}")
                if value is not None:
                    st.write(f"   Ratio: **{value:.2f}**")
                st.write(f"   {interpretation}")
                st.caption(f"   Fórmula: {formula}")
                st.markdown("")
    else:
        st.warning("⚠️ No se pudieron calcular ratios. Verifica que el balance esté completo.")

    st.markdown("───────────────────────────────────────────────────────────")


# =========================================================
# COMPONENTE 4: INSOLVENCIA
# =========================================================


def render_insolvency_block(insolvency_dict: Optional[dict[str, Any]]):
    """Renderiza el bloque de detección de insolvencia."""
    st.subheader("4️⃣ DETECCIÓN DE INSOLVENCIA ACTUAL")
    st.markdown("═══════════════════════════════════════════════════════════")

    if insolvency_dict:
        # Extraer datos del modelo real
        overall_assessment = insolvency_dict.get("overall_assessment", "")
        confidence_level = insolvency_dict.get("confidence_level", "low")
        signals_contables = insolvency_dict.get("signals_contables", [])
        signals_exigibilidad = insolvency_dict.get("signals_exigibilidad", [])
        signals_impago = insolvency_dict.get("signals_impago", [])
        missing = insolvency_dict.get("critical_missing_docs", [])

        # Determinar semáforo basado en señales
        if signals_impago or (signals_contables and signals_exigibilidad):
            st.error(f"🔴 **{overall_assessment}**")
        elif signals_contables or signals_exigibilidad:
            st.warning(f"🟡 **{overall_assessment}**")
        else:
            st.success(f"🟢 **{overall_assessment}**")

        st.markdown("")

        # Señales contables
        if signals_contables:
            st.write("**📊 Señales Contables:**")
            for signal in signals_contables:
                severity = signal.get("severity", "concerning")
                severity_emoji = {"critical": "🔴", "concerning": "🟡", "stable": "🟢"}.get(
                    severity, "⚪"
                )
                description = signal.get("description", "")

                with st.expander(f"{severity_emoji} {description}"):
                    if signal.get("amount") is not None:
                        st.write(f"**Monto:** {signal['amount']:,.0f} €")
                    if signal.get("evidence"):
                        render_evidence_expander(signal["evidence"])
            st.markdown("")

        # Señales de exigibilidad
        if signals_exigibilidad:
            st.write("**⚠️ Señales de Exigibilidad:**")
            for signal in signals_exigibilidad:
                severity = signal.get("severity", "concerning")
                severity_emoji = {"critical": "🔴", "concerning": "🟡", "stable": "🟢"}.get(
                    severity, "⚪"
                )
                description = signal.get("description", "")

                with st.expander(f"{severity_emoji} {description}"):
                    if signal.get("amount") is not None:
                        st.write(f"**Monto:** {signal['amount']:,.0f} €")
                    if signal.get("evidence"):
                        render_evidence_expander(signal["evidence"])
            st.markdown("")

        # Señales de impago efectivo
        if signals_impago:
            st.write("**🚨 Señales de Impago Efectivo:**")
            for signal in signals_impago:
                severity = signal.get("severity", "concerning")
                severity_emoji = {"critical": "🔴", "concerning": "🟡", "stable": "🟢"}.get(
                    severity, "⚪"
                )
                description = signal.get("description", "")

                with st.expander(f"{severity_emoji} {description}"):
                    if signal.get("amount") is not None:
                        st.write(f"**Monto:** {signal['amount']:,.0f} €")
                    if signal.get("evidence"):
                        render_evidence_expander(signal["evidence"])
            st.markdown("")

        # Nivel de confianza de datos
        conf_emoji_map = {"high": "✅", "medium": "🟡", "low": "❓"}
        conf_emoji = conf_emoji_map.get(confidence_level, "❓")
        conf_label = {"high": "ALTA", "medium": "MEDIA", "low": "BAJA"}.get(
            confidence_level, "DESCONOCIDA"
        )
        st.write(f"**Confianza de datos:** {conf_emoji} **{conf_label}**")

        # Documentación faltante
        if missing:
            st.markdown("")
            st.warning("**⚠️ Documentación CRÍTICA faltante:**")
            for doc in missing:
                st.write(f"- {doc}")
    else:
        st.error("❌ No se pudo evaluar insolvencia. Faltan datos críticos.")

    st.markdown("═══════════════════════════════════════════════════════════")


# =========================================================
# COMPONENTE 5: TIMELINE
# =========================================================


def render_timeline_block_backend(case_id: str, client):
    """
    Renderiza timeline CON PAGINACIÓN Y FILTROS EN BACKEND (ESCALABLE).

    ✅ NUEVA VERSIÓN OPTIMIZADA:
    - Paginación real en BD (LIMIT/OFFSET)
    - Filtros aplicados en SQL
    - Índices optimizados
    - Sin cargar todos los eventos en memoria

    Args:
        case_id: ID del caso
        client: PhoenixLegalClient para llamadas API
    """
    st.subheader("5️⃣ TIMELINE DE EVENTOS CRÍTICOS")
    st.markdown("───────────────────────────────────────────────────────────")

    # ═══════════════════════════════════════════════════════
    # INICIALIZAR SESSION STATE (PERSISTENTE)
    # ═══════════════════════════════════════════════════════
    if "timeline_page" not in st.session_state:
        st.session_state.timeline_page = 1
    if "timeline_page_size" not in st.session_state:
        st.session_state.timeline_page_size = 20

    # ═══════════════════════════════════════════════════════
    # FILTROS INTERACTIVOS
    # ═══════════════════════════════════════════════════════
    st.write("**Filtros:**")

    col_f1, col_f2, col_f3 = st.columns(3)

    with col_f1:
        event_type_filter = st.selectbox(
            "Tipo de evento",
            ["Todos", "embargo", "factura_vencida", "reclamacion", "evento_corporativo"],
            key="timeline_type_select",
        )

    with col_f2:
        severity_filter = st.selectbox(
            "Severidad",
            ["Todas", "critical", "high", "medium", "low"],
            key="timeline_severity_select",
        )

    with col_f3:
        search_text = st.text_input(
            "Buscar (descripción)",
            key="timeline_search_input",
            placeholder="Mínimo 3 caracteres...",
        )

    # Filtros de fecha
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input("Desde", value=None, key="timeline_start_date")
    with col_d2:
        end_date = st.date_input("Hasta", value=None, key="timeline_end_date")

    # Botón de reset
    if st.button("🔄 Limpiar Filtros"):
        st.session_state.timeline_page = 1
        st.session_state.timeline_type_select = "Todos"
        st.session_state.timeline_severity_select = "Todas"
        st.session_state.timeline_search_input = ""
        st.rerun()

    st.markdown("---")

    # ═══════════════════════════════════════════════════════
    # LLAMADA AL BACKEND (PAGINACIÓN REAL)
    # ═══════════════════════════════════════════════════════
    try:
        timeline_response = client.get_timeline_paginated(
            case_id=case_id,
            page=st.session_state.timeline_page,
            page_size=st.session_state.timeline_page_size,
            event_type=event_type_filter if event_type_filter != "Todos" else None,
            severity=severity_filter if severity_filter != "Todas" else None,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            search=search_text if len(search_text) >= 3 else None,
            sort_by="date",
            sort_order="desc",
            include_stats=False,  # Stats opcionales
        )

        # Extraer datos de respuesta
        total_events = timeline_response["total_events"]
        page = timeline_response["page"]
        total_pages = timeline_response["total_pages"]
        has_next = timeline_response["has_next"]
        has_prev = timeline_response["has_prev"]
        events = timeline_response["events"]

        # ═══════════════════════════════════════════════════════
        # INFO Y PAGINACIÓN
        # ═══════════════════════════════════════════════════════
        col_info1, col_info2 = st.columns([3, 1])

        with col_info1:
            st.write(f"**Total eventos: {total_events}** | Página {page} de {total_pages}")

        with col_info2:
            page_size_select = st.selectbox(
                "Por página",
                [10, 20, 50, 100],
                index=1,  # Default 20
                key="timeline_page_size_select",
            )
            if page_size_select != st.session_state.timeline_page_size:
                st.session_state.timeline_page_size = page_size_select
                st.session_state.timeline_page = 1  # Reset a primera página
                st.rerun()

        if total_events == 0:
            st.info("ℹ️ No hay eventos que coincidan con los filtros aplicados")
            st.markdown("───────────────────────────────────────────────────────────")
            return

        # Controles de paginación (arriba)
        col_pag1, col_pag2, col_pag3 = st.columns([1, 2, 1])

        with col_pag1:
            if st.button("⬅️ Anterior", disabled=not has_prev, key="timeline_prev_top"):
                st.session_state.timeline_page -= 1
                st.rerun()

        with col_pag2:
            st.write(f"Página {page} de {total_pages}")

        with col_pag3:
            if st.button("Siguiente ➡️", disabled=not has_next, key="timeline_next_top"):
                st.session_state.timeline_page += 1
                st.rerun()

        st.markdown("---")

        # ═══════════════════════════════════════════════════════
        # RENDERIZAR EVENTOS DE ESTA PÁGINA
        # ═══════════════════════════════════════════════════════
        for event in events:
            emoji_map = {
                "embargo": "🚨",
                "factura_vencida": "📄",
                "reclamacion": "⚠️",
                "evento_corporativo": "📋",
            }
            emoji = emoji_map.get(event["event_type"], "📌")

            # Formatear fecha
            date_str = (
                event["date"][:10]
                if isinstance(event["date"], str)
                else event["date"].strftime("%Y-%m-%d")
            )

            # Formatear monto
            amount_str = f" - {event['amount']:,.0f} €" if event.get("amount") else ""

            # Título del expander
            title = event.get("title") or event["description"]
            expander_label = f"{date_str} │ {emoji} {title}{amount_str}"

            with st.expander(expander_label):
                # Descripción completa
                st.write(f"**Descripción:** {event['description']}")

                # Detalles
                col_det1, col_det2 = st.columns(2)

                with col_det1:
                    st.write(f"**Tipo:** {event['event_type']}")
                    if event.get("category"):
                        st.write(f"**Categoría:** {event['category']}")

                with col_det2:
                    if event.get("amount"):
                        st.write(f"**Importe:** {event['amount']:,.0f} €")
                    if event.get("severity"):
                        severity_emoji_map = {
                            "critical": "🔴",
                            "high": "🟠",
                            "medium": "🟡",
                            "low": "🟢",
                        }
                        sev_emoji = severity_emoji_map.get(event["severity"], "⚪")
                        st.write(f"**Severidad:** {sev_emoji} {event['severity'].upper()}")

                # Metadata técnica
                if event.get("extraction_confidence"):
                    st.caption(f"🎯 Confianza: {event['extraction_confidence']:.0%}")

                if event.get("document_id"):
                    st.caption(f"📄 Documento: `{event['document_id'][:12]}...`")

        # Controles de paginación (abajo)
        st.markdown("---")
        col_pag_bot1, col_pag_bot2, col_pag_bot3 = st.columns([1, 2, 1])

        with col_pag_bot1:
            if st.button("⬅️ Anterior", disabled=not has_prev, key="timeline_prev_bottom"):
                st.session_state.timeline_page -= 1
                st.rerun()

        with col_pag_bot2:
            st.write(f"Página {page} de {total_pages}")

        with col_pag_bot3:
            if st.button("Siguiente ➡️", disabled=not has_next, key="timeline_next_bottom"):
                st.session_state.timeline_page += 1
                st.rerun()

    except Exception as e:
        st.error(f"❌ Error al cargar timeline: {e}")
        logger = logging.getLogger(__name__)
        logger.exception(f"Error rendering timeline for case {case_id}")

    st.markdown("───────────────────────────────────────────────────────────")


def render_timeline_block(timeline_dicts: list[dict[str, Any]]):
    """
    Renderiza timeline de eventos CON FILTROS PERSISTENTES Y PAGINACIÓN.

    ⚠️ VERSIÓN LEGACY (CLIENT-SIDE):
    - Carga todos los eventos en memoria
    - Filtros y paginación cosméticos
    - NO escalable para +500 eventos

    👉 Usa render_timeline_block_backend() para versión optimizada

    Garantiza:
    - Filtros persistentes en session_state (no se resetean)
    - Paginación para timelines grandes (> 50 eventos)
    - Reset explícito de filtros
    - UX estable y performante
    """
    st.subheader("5️⃣ TIMELINE DE EVENTOS CRÍTICOS")
    st.markdown("───────────────────────────────────────────────────────────")

    if not timeline_dicts:
        st.info("ℹ️ No se detectaron eventos críticos en el timeline.")
        st.markdown("───────────────────────────────────────────────────────────")
        return

    # ═══════════════════════════════════════════════════════
    # INICIALIZAR SESSION STATE (persistencia explícita)
    # ═══════════════════════════════════════════════════════
    if "timeline_filters_initialized" not in st.session_state:
        st.session_state.timeline_filters_initialized = True
        st.session_state.timeline_page = 1

    # ═══════════════════════════════════════════════════════
    # FILTROS INTERACTIVOS (CON BOTÓN DE RESET)
    # ═══════════════════════════════════════════════════════
    col_header1, col_header2 = st.columns([3, 1])

    with col_header1:
        st.write(f"**Total de eventos: {len(timeline_dicts)}**")

    with col_header2:
        if st.button("🔄 Reset Filtros", key="timeline_reset_btn"):
            # Reset explícito de todos los filtros
            st.session_state.timeline_type_filter = "Todos"
            st.session_state.timeline_date_range = None
            st.session_state.timeline_search = ""
            st.session_state.timeline_page = 1
            st.rerun()

    col_f1, col_f2, col_f3 = st.columns(3)

    with col_f1:
        # Filtro por tipo
        event_types = list(set([e.get("event_type", "otros") for e in timeline_dicts]))
        event_types.insert(0, "Todos")
        type_filter = st.selectbox("Tipo de evento", event_types, key="timeline_type_filter")

    with col_f2:
        # Filtro por rango de fechas
        dates = []
        for e in timeline_dicts:
            date_obj = e.get("date")
            if isinstance(date_obj, str) and date_obj:
                try:
                    from datetime import datetime

                    dates.append(datetime.strptime(date_obj[:10], "%Y-%m-%d").date())
                except:
                    pass
            elif date_obj:
                dates.append(date_obj.date() if hasattr(date_obj, "date") else date_obj)

        if dates:
            min_date = min(dates)
            max_date = max(dates)
            date_range = st.date_input(
                "Rango de fechas",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                key="timeline_date_range",
            )
        else:
            date_range = None

    with col_f3:
        # Búsqueda por texto
        search_text = st.text_input("Buscar en descripción", "", key="timeline_search")

    # Aplicar filtros
    filtered_events = timeline_dicts

    if type_filter != "Todos":
        filtered_events = [e for e in filtered_events if e.get("event_type") == type_filter]

    if date_range and len(date_range) == 2:
        start_date, end_date = date_range
        filtered_temp = []
        for e in filtered_events:
            date_obj = e.get("date")
            try:
                if isinstance(date_obj, str):
                    from datetime import datetime

                    e_date = datetime.strptime(date_obj[:10], "%Y-%m-%d").date()
                else:
                    e_date = date_obj.date() if hasattr(date_obj, "date") else date_obj

                if start_date <= e_date <= end_date:
                    filtered_temp.append(e)
            except:
                filtered_temp.append(e)  # Incluir si no se puede parsear
        filtered_events = filtered_temp

    if search_text:
        filtered_events = [
            e for e in filtered_events if search_text.lower() in e.get("description", "").lower()
        ]

    # Mostrar contador
    st.write(f"**Eventos filtrados: {len(filtered_events)}**")
    st.markdown("---")

    # ═══════════════════════════════════════════════════════
    # PAGINACIÓN (para timelines grandes)
    # ═══════════════════════════════════════════════════════
    ITEMS_PER_PAGE = 20
    total_pages = (len(filtered_events) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    if total_pages > 1:
        col_pag1, col_pag2, col_pag3 = st.columns([1, 2, 1])

        with col_pag1:
            if st.button("⬅️ Anterior", disabled=st.session_state.timeline_page == 1):
                st.session_state.timeline_page -= 1
                st.rerun()

        with col_pag2:
            st.write(f"**Página {st.session_state.timeline_page} de {total_pages}**")

        with col_pag3:
            if st.button("Siguiente ➡️", disabled=st.session_state.timeline_page == total_pages):
                st.session_state.timeline_page += 1
                st.rerun()

        st.markdown("---")

    # Calcular rango de eventos a mostrar
    start_idx = (st.session_state.timeline_page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    events_to_show = filtered_events[start_idx:end_idx]

    # Renderizar eventos de la página actual
    for event in events_to_show:
        # Manejar fecha como datetime o string
        date_obj = event.get("date", "")
        if isinstance(date_obj, str):
            date = date_obj[:10]
        else:
            # Es un datetime object
            date = date_obj.strftime("%Y-%m-%d") if date_obj else ""

        event_type = event.get("event_type", "")
        description = event.get("description", "")
        amount = event.get("amount")

        emoji = {
            "embargo": "🚨",
            "factura_vencida": "📄",
            "reclamacion": "⚠️",
            "evento_corporativo": "📋",
        }.get(event_type, "📌")

        amount_str = f" - {amount:,.0f} €" if amount is not None else ""

        with st.expander(f"{date} │ {emoji} {description}{amount_str}"):
            if amount is not None:
                st.write(f"**Importe:** {amount:,.0f} €")
            st.write(f"**Tipo:** {event_type}")
            if event.get("evidence"):
                render_evidence_expander(event["evidence"])

    # Mostrar navegación al final si hay múltiples páginas
    if total_pages > 1:
        st.markdown("---")
        col_pag_bottom1, col_pag_bottom2, col_pag_bottom3 = st.columns([1, 2, 1])

        with col_pag_bottom1:
            if st.button(
                "⬅️ Anterior ",
                disabled=st.session_state.timeline_page == 1,
                key="timeline_prev_bottom",
            ):
                st.session_state.timeline_page -= 1
                st.rerun()

        with col_pag_bottom2:
            st.write(f"Página {st.session_state.timeline_page}/{total_pages}")

        with col_pag_bottom3:
            if st.button(
                "Siguiente ➡️ ",
                disabled=st.session_state.timeline_page == total_pages,
                key="timeline_next_bottom",
            ):
                st.session_state.timeline_page += 1
                st.rerun()

    st.markdown("───────────────────────────────────────────────────────────")


# =========================================================
# COMPONENTE AVANZADO: PATRONES SOSPECHOSOS
# =========================================================


def render_suspicious_patterns(alerts: list[dict[str, Any]]):
    """
    Renderiza visualización interactiva de patrones sospechosos detectados.
    Incluye gráficos de distribución, temporal y drill-down por patrón.
    """
    st.subheader("🔍 PATRONES SOSPECHOSOS DETECTADOS")
    st.markdown("═══════════════════════════════════════════════════════════")

    if not alerts:
        st.success("✅ No se han detectado patrones sospechosos en el análisis")
        return

    # Filtros
    st.write("**Filtros de visualización:**")
    col_f1, col_f2, col_f3 = st.columns(3)

    with col_f1:
        severities = list(set(a.get("severity", "medium") for a in alerts))
        selected_severity = st.multiselect(
            "Severidad", severities, default=severities, key="patterns_severity_filter"
        )

    with col_f2:
        categories = list(set(a.get("category", "otros") for a in alerts))
        selected_categories = st.multiselect(
            "Categoría", categories, default=categories, key="patterns_category_filter"
        )

    with col_f3:
        min_score = st.slider("Score mínimo", 0, 100, 0, key="patterns_score_filter")

    # Aplicar filtros
    filtered_alerts = [
        a
        for a in alerts
        if (
            a.get("severity", "medium") in selected_severity
            and a.get("category", "otros") in selected_categories
            and a.get("severity_score", 0) >= min_score
        )
    ]

    if not filtered_alerts:
        st.warning("⚠️ No hay patrones que coincidan con los filtros seleccionados")
        return

    st.markdown("---")

    # Modo de visualización
    view_mode = st.radio(
        "Modo de vista",
        ["📊 Gráficos Interactivos", "📋 Lista Detallada", "🌐 Mapa de Calor"],
        horizontal=True,
        key="patterns_view_mode",
    )

    if view_mode == "📊 Gráficos Interactivos":
        try:
            import plotly.graph_objects as go

            # Preparar datos (CACHEADO para performance)
            alerts_json = json.dumps(filtered_alerts, sort_keys=True)
            chart_data = _prepare_patterns_chart_data(alerts_json)

            category_counts = chart_data["category_counts"]
            category_scores = chart_data["category_scores"]
            severity_counts = chart_data["severity_counts"]
            top_alerts = chart_data["top_alerts"]

            # 1. Distribución por Categoría
            st.write("**1️⃣ Distribución por Categoría**")

            fig_cat = go.Figure()

            fig_cat.add_trace(
                go.Bar(
                    x=list(category_counts.keys()),
                    y=list(category_counts.values()),
                    name="Cantidad",
                    marker_color="#3b82f6",
                    yaxis="y",
                    hovertemplate="<b>%{x}</b><br>Cantidad: %{y}<extra></extra>",
                )
            )

            fig_cat.add_trace(
                go.Scatter(
                    x=list(category_scores.keys()),
                    y=list(category_scores.values()),
                    name="Score Promedio",
                    marker_color="#ef4444",
                    mode="lines+markers",
                    yaxis="y2",
                    hovertemplate="<b>%{x}</b><br>Score: %{y:.1f}<extra></extra>",
                )
            )

            fig_cat.update_layout(
                title="Patrones por Categoría (Cantidad vs Score)",
                xaxis_title="Categoría",
                yaxis=dict(title="Cantidad de Patrones", side="left"),
                yaxis2=dict(title="Score Promedio", side="right", overlaying="y", range=[0, 100]),
                height=400,
                hovermode="x unified",
            )

            st.plotly_chart(fig_cat, use_container_width=True)

            # 2. Distribución por Severidad (Pie + Sunburst)
            col_g1, col_g2 = st.columns(2)

            with col_g1:
                st.write("**2️⃣ Distribución por Severidad**")

                severity_colors = {
                    "critical": "#dc2626",
                    "high": "#f59e0b",
                    "medium": "#eab308",
                    "low": "#10b981",
                }

                fig_sev = go.Figure(
                    data=[
                        go.Pie(
                            labels=list(severity_counts.keys()),
                            values=list(severity_counts.values()),
                            marker=dict(
                                colors=[
                                    severity_colors.get(s, "#6b7280")
                                    for s in severity_counts.keys()
                                ]
                            ),
                            hole=0.4,
                            textinfo="label+percent+value",
                            hovertemplate="<b>%{label}</b><br>Cantidad: %{value}<br>%{percent}<extra></extra>",
                        )
                    ]
                )

                fig_sev.update_layout(title="Por Severidad", height=350)

                st.plotly_chart(fig_sev, use_container_width=True)

            with col_g2:
                st.write("**3️⃣ Top 5 Patrones Críticos**")

                if top_alerts:
                    top_names = [
                        a.get("alert_type", f"Patrón {i+1}") for i, a in enumerate(top_alerts)
                    ]
                    top_scores = [a.get("severity_score", 0) for a in top_alerts]
                    top_colors = [
                        severity_colors.get(a.get("severity", "medium"), "#6b7280")
                        for a in top_alerts
                    ]

                    fig_top = go.Figure(
                        data=[
                            go.Bar(
                                y=top_names,
                                x=top_scores,
                                orientation="h",
                                marker=dict(color=top_colors),
                                text=[f"{s:.0f}" for s in top_scores],
                                textposition="auto",
                                hovertemplate="<b>%{y}</b><br>Score: %{x:.1f}<extra></extra>",
                            )
                        ]
                    )

                    fig_top.update_layout(
                        title="Top Patrones por Score",
                        xaxis=dict(title="Score", range=[0, 100]),
                        height=350,
                        showlegend=False,
                    )

                    st.plotly_chart(fig_top, use_container_width=True)

            # 3. Timeline de detección (si hay fecha)
            st.write("**4️⃣ Timeline de Detección**")

            alerts_with_date = [a for a in filtered_alerts if a.get("detected_at") or a.get("date")]

            if alerts_with_date:
                dates = []
                scores = []
                names = []
                colors = []

                for a in alerts_with_date:
                    date_val = a.get("detected_at") or a.get("date")
                    if date_val:
                        dates.append(date_val)
                        scores.append(a.get("severity_score", 0))
                        names.append(a.get("alert_type", "Patrón"))
                        colors.append(severity_colors.get(a.get("severity", "medium"), "#6b7280"))

                fig_timeline = go.Figure(
                    data=[
                        go.Scatter(
                            x=dates,
                            y=scores,
                            mode="markers+lines",
                            marker=dict(size=12, color=colors, line=dict(width=1, color="white")),
                            text=names,
                            hovertemplate="<b>%{text}</b><br>Fecha: %{x}<br>Score: %{y:.1f}<extra></extra>",
                        )
                    ]
                )

                fig_timeline.update_layout(
                    title="Evolución Temporal de Patrones",
                    xaxis_title="Fecha de Detección",
                    yaxis=dict(title="Severity Score", range=[0, 100]),
                    height=350,
                )

                st.plotly_chart(fig_timeline, use_container_width=True)
            else:
                st.info("ℹ️ No hay información temporal disponible para los patrones")

        except ImportError:
            st.warning("⚠️ plotly no disponible. Mostrando vista de lista.")
            view_mode = "📋 Lista Detallada"
        except Exception as e:
            st.error(f"Error al generar gráficos: {str(e)}")
            view_mode = "📋 Lista Detallada"

    if view_mode == "🌐 Mapa de Calor":
        try:
            import plotly.graph_objects as go

            # Matriz Categoría x Severidad
            categories = list(set(a.get("category", "otros") for a in filtered_alerts))
            severities = ["critical", "high", "medium", "low"]

            matrix = []
            for cat in categories:
                row = []
                for sev in severities:
                    count = len(
                        [
                            a
                            for a in filtered_alerts
                            if a.get("category", "otros") == cat
                            and a.get("severity", "medium") == sev
                        ]
                    )
                    row.append(count)
                matrix.append(row)

            fig_heatmap = go.Figure(
                data=go.Heatmap(
                    z=matrix,
                    x=severities,
                    y=categories,
                    colorscale="Reds",
                    hovertemplate="Categoría: %{y}<br>Severidad: %{x}<br>Cantidad: %{z}<extra></extra>",
                    text=matrix,
                    texttemplate="%{text}",
                    textfont={"size": 14},
                )
            )

            fig_heatmap.update_layout(
                title="Mapa de Calor: Categoría vs Severidad",
                xaxis_title="Severidad",
                yaxis_title="Categoría",
                height=400,
            )

            st.plotly_chart(fig_heatmap, use_container_width=True)

        except ImportError:
            st.warning("⚠️ plotly no disponible. Mostrando vista de lista.")
            view_mode = "📋 Lista Detallada"
        except Exception as e:
            st.error(f"Error al generar mapa de calor: {str(e)}")
            view_mode = "📋 Lista Detallada"

    if view_mode == "📋 Lista Detallada":
        # Vista lista con drill-down
        st.write(f"**Total de patrones:** {len(filtered_alerts)}")

        # Agrupar por categoría
        by_category = defaultdict(list)
        for alert in filtered_alerts:
            by_category[alert.get("category", "otros")].append(alert)

        for category, cat_alerts in by_category.items():
            with st.expander(
                f"📂 **{category.upper()}** ({len(cat_alerts)} patrones)", expanded=False
            ):
                for alert in cat_alerts:
                    severity = alert.get("severity", "medium")
                    severity_emoji = {
                        "critical": "🔴",
                        "high": "🟠",
                        "medium": "🟡",
                        "low": "🟢",
                    }.get(severity, "⚪")

                    score = alert.get("severity_score", 0)
                    alert_type = alert.get("alert_type", "Patrón sospechoso")
                    description = alert.get("description", "Sin descripción")

                    st.markdown(f"{severity_emoji} **{alert_type}** (Score: {score:.0f}/100)")
                    st.write(f"   {description}")

                    # Evidencias
                    if alert.get("evidence"):
                        render_evidence_expander(alert["evidence"], "🔍 Ver evidencias del patrón")

                    # Recomendación
                    if alert.get("recommendation"):
                        st.info(f"💡 **Recomendación:** {alert['recommendation']}")

                    st.markdown("---")

    st.markdown("═══════════════════════════════════════════════════════════")
