from __future__ import annotations

import streamlit as st

from app.ui.api_client import PhoenixLegalClient


def render_sidebar(client: PhoenixLegalClient) -> dict:
    """
    Renderiza sidebar (health + selector de casos).

    Devuelve un dict con:
    - selected_case_id
    - cases (lista)
    """
    st.sidebar.title("⚖️ Phoenix Legal")

    # Health check
    try:
        health = client.health_check()
        st.sidebar.success(f"✅ API: {health['status']}")
    except Exception as e:
        st.sidebar.error(f"❌ API no disponible: {e}")
        st.stop()

    st.sidebar.subheader("📁 Casos")

    cases = []
    try:
        cases = client.list_cases()
        if cases:
            case_options = {
                f"{case['name']} ({case['case_id'][:8]}...)": case["case_id"] for case in cases
            }
            selected_label = st.sidebar.selectbox(
                "Selecciona un caso:", options=list(case_options.keys()), key="case_selector"
            )
            selected_case_id = case_options[selected_label]
        else:
            st.sidebar.info("No hay casos creados")
            selected_case_id = None
    except Exception as e:
        st.sidebar.error(f"Error al cargar casos: {e}")
        selected_case_id = None
        cases = []

    st.session_state["selected_case_id"] = selected_case_id
    return {"selected_case_id": selected_case_id, "cases": cases}
