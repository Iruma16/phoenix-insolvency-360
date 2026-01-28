"""
Componentes reutilizables para la UI de Phoenix Legal.

Separa la lógica de render en funciones específicas para:
- Mejor mantenibilidad
- Reutilización de código
- Testing más fácil
"""
import streamlit as st
from typing import Dict, Any, List, Optional
from collections import defaultdict


# =========================================================
# HELPER: VISUALIZACIÓN DE EVIDENCIA
# =========================================================

def render_evidence_expander(evidence: Dict[str, Any], label: str = "🔍 Ver Evidencia"):
    """
    Renderiza un expander con la evidencia completa.
    
    Args:
        evidence: Dict con evidence (document_id, filename, page, excerpt, etc.)
        label: Texto del expander
    """
    if not evidence:
        return
    
    with st.expander(label):
        st.write(f"**📄 Documento:** `{evidence.get('filename', 'N/A')}`")
        
        if evidence.get('page'):
            st.write(f"**📖 Página:** {evidence['page']}")
        
        if evidence.get('document_id'):
            st.caption(f"ID: `{evidence['document_id'][:12]}...`")
        
        if evidence.get('excerpt'):
            st.write("**📝 Fragmento extraído:**")
            st.code(evidence['excerpt'], language=None)
        
        # Metadatos técnicos
        method = evidence.get('extraction_method', 'N/A')
        confidence = evidence.get('extraction_confidence', 0)
        st.caption(f"Método: {method} | Confianza extracción: {confidence:.0%}")


# =========================================================
# HELPERS DE CAMPO
# =========================================================

def get_field_value(field_data):
    """Extrae el valor de un campo (puede ser dict con 'value' o directo)."""
    if field_data is None:
        return None
    if isinstance(field_data, dict) and 'value' in field_data:
        return field_data['value']
    if isinstance(field_data, (int, float)):
        return field_data
    return None


def get_confidence_emoji(field_data):
    """Obtiene el emoji de confianza."""
    if field_data is None or not isinstance(field_data, dict):
        return "❓"
    conf = field_data.get('confidence', 'LOW')
    return {"HIGH": "✅", "MEDIUM": "🟡", "LOW": "❓"}.get(conf, "❓")


# =========================================================
# COMPONENTE 1: BALANCE
# =========================================================

def render_balance_block(balance_dict: Optional[Dict[str, Any]], 
                         profit_loss_dict: Optional[Dict[str, Any]]):
    """Renderiza el bloque de datos contables estructurados."""
    st.subheader("1️⃣ DATOS CONTABLES ESTRUCTURADOS")
    
    if balance_dict:
        st.markdown("───────────────────────────────────────────────────────────")
        
        # Metadata
        overall_conf = balance_dict.get("overall_confidence", "LOW")
        conf_emoji = {"HIGH": "✅", "MEDIUM": "🟡", "LOW": "❓"}.get(overall_conf, "❓")
        source_date = balance_dict.get('source_date', 'N/A')
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
                if isinstance(ac, dict) and ac.get('evidence'):
                    render_evidence_expander(ac['evidence'], "🔍 Ver origen del dato")
            
            # Activo Total
            at = balance_dict.get("activo_total")
            at_val = get_field_value(at)
            if at_val is not None:
                emoji = get_confidence_emoji(at)
                st.metric("Activo Total", f"{at_val:,.0f} € {emoji}")
                if isinstance(at, dict) and at.get('evidence'):
                    render_evidence_expander(at['evidence'], "🔍 Ver origen del dato")
            
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
                    delta_color=delta_color
                )
                if isinstance(pn, dict) and pn.get('evidence'):
                    render_evidence_expander(pn['evidence'], "🔍 Ver origen del dato")
        
        with col2:
            # Pasivo Corriente
            pc = balance_dict.get("pasivo_corriente")
            pc_val = get_field_value(pc)
            if pc_val is not None:
                emoji = get_confidence_emoji(pc)
                st.metric("Pasivo Corriente", f"{pc_val:,.0f} € {emoji}")
                if isinstance(pc, dict) and pc.get('evidence'):
                    render_evidence_expander(pc['evidence'], "🔍 Ver origen del dato")
            
            # Pasivo Total
            pt = balance_dict.get("pasivo_total")
            pt_val = get_field_value(pt)
            if pt_val is not None:
                emoji = get_confidence_emoji(pt)
                st.metric("Pasivo Total", f"{pt_val:,.0f} € {emoji}")
                if isinstance(pt, dict) and pt.get('evidence'):
                    render_evidence_expander(pt['evidence'], "🔍 Ver origen del dato")
        
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
                    delta_color=delta_color
                )
                if isinstance(resultado, dict) and resultado.get('evidence'):
                    render_evidence_expander(resultado['evidence'], "🔍 Ver origen del dato")
    else:
        st.warning("⚠️ No se encontraron datos de Balance. Sube un documento de balance para ver análisis.")
    
    st.markdown("───────────────────────────────────────────────────────────")


# =========================================================
# COMPONENTE 2: CRÉDITOS
# =========================================================

def render_credits_block(credits_dicts: List[Dict[str, Any]], total_debt: Optional[float]):
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
                    if c.get('evidence'):
                        render_evidence_expander(c['evidence'])
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
                    if c.get('evidence'):
                        render_evidence_expander(c['evidence'])
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
                    if c.get('evidence'):
                        render_evidence_expander(c['evidence'])
            
            if len(ordinarios) > 3:
                st.write(f"   └─ ... y {len(ordinarios) - 3} más")
    else:
        st.info("ℹ️ No se detectaron créditos clasificables. Sube facturas, embargos o contratos.")
    
    st.markdown("───────────────────────────────────────────────────────────")


# =========================================================
# COMPONENTE 3: RATIOS
# =========================================================

def render_ratios_block(ratios_dicts: List[Dict[str, Any]]):
    """Renderiza el bloque de ratios financieros."""
    st.subheader("3️⃣ RATIOS FINANCIEROS (SEMÁFORO)")
    st.markdown("───────────────────────────────────────────────────────────")
    
    if ratios_dicts:
        for ratio in ratios_dicts:
            # Mapear FinancialStatus a emoji
            status = ratio.get("status", "stable")
            status_emoji_map = {
                "critical": "🔴",
                "concerning": "🟡", 
                "stable": "🟢",
                # Retrocompatibilidad
                "red": "🔴",
                "yellow": "🟡",
                "green": "🟢"
            }
            emoji = status_emoji_map.get(status, "⚪")
            
            name = ratio.get("name")
            interpretation = ratio.get("interpretation")
            value = ratio.get("value")
            formula = ratio.get("formula")
            confidence = ratio.get("confidence", "medium")
            
            # Emoji de confianza
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

def render_insolvency_block(insolvency_dict: Optional[Dict[str, Any]]):
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
                severity_emoji = {"critical": "🔴", "concerning": "🟡", "stable": "🟢"}.get(severity, "⚪")
                description = signal.get("description", "")
                
                with st.expander(f"{severity_emoji} {description}"):
                    if signal.get('amount') is not None:
                        st.write(f"**Monto:** {signal['amount']:,.0f} €")
                    if signal.get('evidence'):
                        render_evidence_expander(signal['evidence'])
            st.markdown("")
        
        # Señales de exigibilidad
        if signals_exigibilidad:
            st.write("**⚠️ Señales de Exigibilidad:**")
            for signal in signals_exigibilidad:
                severity = signal.get("severity", "concerning")
                severity_emoji = {"critical": "🔴", "concerning": "🟡", "stable": "🟢"}.get(severity, "⚪")
                description = signal.get("description", "")
                
                with st.expander(f"{severity_emoji} {description}"):
                    if signal.get('amount') is not None:
                        st.write(f"**Monto:** {signal['amount']:,.0f} €")
                    if signal.get('evidence'):
                        render_evidence_expander(signal['evidence'])
            st.markdown("")
        
        # Señales de impago efectivo
        if signals_impago:
            st.write("**🚨 Señales de Impago Efectivo:**")
            for signal in signals_impago:
                severity = signal.get("severity", "concerning")
                severity_emoji = {"critical": "🔴", "concerning": "🟡", "stable": "🟢"}.get(severity, "⚪")
                description = signal.get("description", "")
                
                with st.expander(f"{severity_emoji} {description}"):
                    if signal.get('amount') is not None:
                        st.write(f"**Monto:** {signal['amount']:,.0f} €")
                    if signal.get('evidence'):
                        render_evidence_expander(signal['evidence'])
            st.markdown("")
        
        # Nivel de confianza de datos
        conf_emoji_map = {"high": "✅", "medium": "🟡", "low": "❓"}
        conf_emoji = conf_emoji_map.get(confidence_level, "❓")
        conf_label = {"high": "ALTA", "medium": "MEDIA", "low": "BAJA"}.get(confidence_level, "DESCONOCIDA")
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

def render_timeline_block(timeline_dicts: List[Dict[str, Any]]):
    """Renderiza el bloque de timeline de eventos críticos."""
    st.subheader("5️⃣ TIMELINE DE EVENTOS CRÍTICOS")
    st.markdown("───────────────────────────────────────────────────────────")
    
    if timeline_dicts:
        for event in timeline_dicts:
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
                "evento_corporativo": "📋"
            }.get(event_type, "📌")
            
            # ✅ CORREGIDO: amount is not None (no amount if amount)
            amount_str = f" - {amount:,.0f} €" if amount is not None else ""
            
            with st.expander(f"{date} │ {emoji} {description}{amount_str}"):
                if amount is not None:
                    st.write(f"**Importe:** {amount:,.0f} €")
                st.write(f"**Tipo:** {event_type}")
                if event.get('evidence'):
                    render_evidence_expander(event['evidence'])
    else:
        st.info("ℹ️ No se detectaron eventos críticos en el timeline.")
    
    st.markdown("───────────────────────────────────────────────────────────")
