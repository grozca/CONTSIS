from __future__ import annotations

import pandas as pd
import streamlit as st

try:
    import plotly.graph_objects as go
except ModuleNotFoundError:
    go = None


C_BRAND = "#002B49"
C_ACCENT = "#00A396"
C_LIGHT_CARD = "#F0F2F6"
C_LIGHT_CARD_ALT = "#FFFFFF"
C_LIGHT_BORDER = "rgba(0, 0, 0, 0.05)"
C_LIGHT_TEXT = "#002B49"
C_LIGHT_MUTED = "#5B6B7E"
C_HEADING = "#1A202C"
C_AXIS_TEXT = "#64748B"
C_FONT_STACK = "Inter, Roboto, 'Segoe UI', system-ui, sans-serif"
C_INGRESO = "#2ECC71"
C_EGRESO = "#E74C3C"
C_BALANCE = "#3498DB"
C_WARN = "#D8951A"
C_OTHER = "#9A9893"

def get_visual_tokens() -> dict[str, object]:
    return {
        "dark": False,
        "card_bg": C_LIGHT_CARD,
        "card_bg_alt": C_LIGHT_CARD_ALT,
        "border": C_LIGHT_BORDER,
        "text": C_LIGHT_TEXT,
        "muted": C_LIGHT_MUTED,
        "shadow": "0 8px 20px rgba(15, 23, 42, 0.08)",
        "signal_bg": "#FDF0F0",
        "signal_border": "#F0C2C2",
        "signal_text": "#8F2F2F",
        "grid": "rgba(15, 23, 42, 0.05)",
        "zero_line": "rgba(0, 0, 0, 0)",
        "hover_bg": "#FFFFFF",
        "marker_line": C_LIGHT_CARD_ALT,
    }


def get_plotly_font(tokens: dict[str, object], *, muted: bool = True) -> dict[str, object]:
    return {
        "family": C_FONT_STACK,
        "size": 12,
        "color": tokens["muted"] if muted else tokens["text"],
    }


def get_axis_font() -> dict[str, object]:
    return {
        "family": C_FONT_STACK,
        "size": 12,
        "color": C_AXIS_TEXT,
        "weight": 600,
    }


def get_compact_donut_legend(tokens: dict[str, object]) -> dict[str, object]:
    return {
        "orientation": "v",
        "x": 0.0,
        "y": -0.02,
        "xanchor": "left",
        "yanchor": "bottom",
        "bgcolor": "rgba(0,0,0,0)",
        "borderwidth": 0,
        "font": {
            **get_plotly_font(tokens, muted=False),
            "size": 12,
        },
    }


def get_compact_donut_layout(tokens: dict[str, object], *, height: int = 360) -> dict[str, object]:
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "margin": {"l": 0, "r": 0, "t": 0, "b": 0},
        "showlegend": True,
        "legend": get_compact_donut_legend(tokens),
        "height": height,
    }


def get_minimal_xaxis() -> dict[str, object]:
    return {
        "title": None,
        "showgrid": False,
        "showline": False,
        "zeroline": False,
        "ticks": "",
        "tickfont": get_axis_font(),
    }


def get_minimal_yaxis(tokens: dict[str, object], *, tickprefix: str | None = None) -> dict[str, object]:
    axis = {
        "showgrid": True,
        "gridcolor": tokens["grid"],
        "gridwidth": 1,
        "showline": False,
        "zeroline": False,
        "ticks": "",
        "tickfont": get_axis_font(),
    }
    if tickprefix is not None:
        axis["tickprefix"] = tickprefix
    return axis


def build_risk_summary(ingresos: float, egresos: float, risk: dict) -> str:
    if ingresos > 0 and egresos > ingresos:
        pct = ((egresos - ingresos) / ingresos) * 100
        return f"Riesgo: Egresos > Ingresos (+{pct:.1f}%)"
    return str(risk.get("headline") or "Sin senales relevantes")


def merged_plotly_layout(**overrides) -> dict:
    tokens = get_visual_tokens()
    layout = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 40, "r": 40, "t": 40, "b": 40},
        font=get_plotly_font(tokens, muted=True),
        legend={
            "orientation": "h",
            "y": 1.10,
            "x": 0,
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "font": get_plotly_font(tokens, muted=True),
        },
        hoverlabel={
            "bgcolor": tokens["hover_bg"],
            "font_color": C_LIGHT_TEXT,
            "bordercolor": tokens["hover_bg"],
        },
    )
    layout.update(overrides)
    return layout


def render_executive_dashboard(dataset: dict) -> None:
    apply_styles()
    render_top_banner(dataset)
    render_audit_alerts(dataset)
    render_executive_dashboard_body(dataset)


def render_executive_dashboard_body(dataset: dict) -> None:
    apply_styles()
    render_fiscal_alert(dataset)
    render_kpi_row(dataset)
    render_document_counts_row(dataset)
    render_balance_row(dataset)
    render_trend_row(dataset)
    render_counterparties(dataset)
    render_signals(dataset)
    render_operations_table(dataset)


def apply_styles() -> None:
    tokens = get_visual_tokens()
    st.markdown(
        f"""
        <style>
        .dark-hero {{
            background: linear-gradient(145deg, {C_BRAND} 0%, #0B4B78 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 22px;
            padding: 26px 28px;
            margin-bottom: 1rem;
            box-shadow: {tokens["shadow"]};
        }}
        .dark-eyebrow {{
            color: rgba(255,255,255,0.72);
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.72rem;
            margin-bottom: 0.55rem;
        }}
        .dark-title {{
            color: #FFFFFF;
            font-size: 2rem;
            font-weight: 700;
            font-family: Arial, "Segoe UI", sans-serif;
            margin-bottom: 0.35rem;
        }}
        .dark-subtitle {{
            color: rgba(255,255,255,0.84);
            font-size: 0.98rem;
        }}
        .dark-pills {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.95rem;
        }}
        .dark-pill {{
            display: inline-block;
            padding: 0.38rem 0.78rem;
            border-radius: 999px;
            background: rgba(255,255,255,0.10);
            color: #FFFFFF;
            font-size: 0.85rem;
            border: 1px solid rgba(255,255,255,0.14);
        }}
        .kpi-shell {{
            background: linear-gradient(145deg, {tokens["card_bg"]} 0%, {tokens["card_bg_alt"]} 100%);
            border: 1px solid {tokens["border"]};
            border-radius: 18px;
            padding: 18px 22px;
            min-height: 142px;
            margin-bottom: 0.85rem;
            box-shadow: {tokens["shadow"]};
        }}
        .kpi-label {{
            color: {tokens["muted"]};
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.45rem;
        }}
        .kpi-value {{
            color: {tokens["text"]};
            font-size: 1.9rem;
            font-weight: 700;
            margin-bottom: 0.3rem;
        }}
        .kpi-value-green {{
            color: {C_INGRESO};
        }}
        .kpi-value-red {{
            color: {C_EGRESO};
        }}
        .kpi-help {{
            color: {tokens["muted"]};
            font-size: 0.9rem;
        }}
        .mini-kpi-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(160px, 1fr));
            gap: 12px;
            margin-top: -0.1rem;
            margin-bottom: 1rem;
        }}
        .mini-kpi-card {{
            background: linear-gradient(145deg, {tokens["card_bg"]} 0%, {tokens["card_bg_alt"]} 100%);
            border: 1px solid {tokens["border"]};
            border-radius: 16px;
            padding: 14px 18px;
            box-shadow: {tokens["shadow"]};
        }}
        .mini-kpi-label {{
            color: {tokens["muted"]};
            font-size: 0.74rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.3rem;
        }}
        .mini-kpi-value {{
            color: {tokens["text"]};
            font-size: 1.45rem;
            font-weight: 700;
            line-height: 1.1;
            margin-bottom: 0.15rem;
        }}
        .mini-kpi-help {{
            color: {tokens["muted"]};
            font-size: 0.88rem;
        }}
        .risk-badge {{
            display: inline-block;
            padding: 0.32rem 0.75rem;
            border-radius: 999px;
            font-size: 0.84rem;
            font-weight: 600;
            margin-top: 0.15rem;
        }}
        .risk-badge-bajo {{
            background: #F4E8D9;
            color: #8A5B1C;
        }}
        .risk-badge-medio {{
            background: #F6D9B5;
            color: #8A4A00;
        }}
        .risk-badge-alto {{
            background: #F8D9D9;
            color: #9D2D2D;
        }}
        .signal-box {{
            background: {tokens["signal_bg"]};
            border: 1px solid {tokens["signal_border"]};
            border-radius: 14px;
            padding: 14px 16px;
            color: {tokens["signal_text"]};
            margin-top: 0.8rem;
            margin-bottom: 0.9rem;
            font-size: 0.98rem;
        }}
        .section-card {{
            background: linear-gradient(145deg, {tokens["card_bg"]} 0%, {tokens["card_bg_alt"]} 100%);
            border: 1px solid {tokens["border"]};
            border-radius: 18px;
            padding: 16px 18px 10px;
            margin-bottom: 1rem;
            box-shadow: {tokens["shadow"]};
        }}
        .section-heading {{
            color: {C_HEADING};
            font-size: 1.16rem;
            font-weight: 700;
            font-family: {C_FONT_STACK};
            margin-bottom: 0.15rem;
        }}
        .section-subheading {{
            color: {tokens["muted"]};
            font-size: 0.98rem;
            margin-bottom: 0.9rem;
        }}
        .signal-item {{
            background: linear-gradient(145deg, {tokens["card_bg"]} 0%, {tokens["card_bg_alt"]} 100%);
            border: 1px solid {tokens["border"]};
            border-left: 4px solid {C_BALANCE};
            border-radius: 12px;
            padding: 12px 14px;
            margin-bottom: 0.65rem;
            box-shadow: {tokens["shadow"]};
        }}
        .signal-label {{
            color: {tokens["muted"]};
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin-bottom: 0.2rem;
        }}
        .signal-text {{
            color: {tokens["text"]};
            font-size: 0.94rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_top_banner(dataset: dict) -> None:
    empresa = dataset["empresa"]
    risk = dataset["insights"]["risk"]
    kpis = dataset["insights"]["kpis"]
    period_label = dataset.get("period_label") or dataset.get("periodo") or dataset["insights"].get("periodo")
    mode_label = {
        "monthly": "Vista mensual",
        "ytd": "Acumulado del ano",
        "year": "Vista anual",
    }.get(dataset.get("analysis_mode"), "Vista ejecutiva")
    risk_summary = build_risk_summary(float(kpis.get("ingresos_mxn") or 0), float(kpis.get("egresos_mxn") or 0), risk)

    st.markdown(
        f"""
        <div class="dark-hero">
            <div class="dark-eyebrow">CONTSIS | tablero analitico CFDI</div>
            <div class="dark-title">{empresa['nombre_corto'] or empresa['rfc']}</div>
            <div class="dark-subtitle">{mode_label} para {period_label}</div>
            <div class="dark-pills">
                <span class="dark-pill">RFC: {empresa['rfc']}</span>
                <span class="dark-pill">Riesgo: {translate_risk_level(risk['level']).title()} ({risk['score']})</span>
                <span class="dark-pill">{risk_summary}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_fiscal_alert(dataset: dict) -> None:
    kpis = dataset["insights"]["kpis"]
    risk = dataset["insights"]["risk"]
    ingresos = float(kpis.get("ingresos_mxn") or 0)
    egresos = float(kpis.get("egresos_mxn") or 0)

    if egresos > ingresos or risk["level"] == "high":
        st.markdown(
            f'<div class="signal-box">{build_risk_summary(ingresos, egresos, risk)}</div>',
            unsafe_allow_html=True,
        )


def render_audit_alerts(dataset: dict) -> None:
    recibidas_df = _get_raw_frame(dataset, "df_recibidas")
    if recibidas_df.empty:
        return

    regimen_col = _find_first_column(
        recibidas_df,
        ["REGIMEN_CODIGO", "RECEPTOR_REGIMENFISCAL", "REGIMEN_FISCAL"],
    )
    if regimen_col is None:
        return

    prepared = recibidas_df.copy()
    tipo_col = _find_first_column(prepared, ["TIPO_COMPROB", "TIPO_COMPROBANTE", "TIPODECOMPROBANTE"])
    if tipo_col is not None:
        prepared = prepared[prepared[tipo_col].astype("string").str.upper().str.strip().eq("I")].copy()
    if prepared.empty:
        return

    has_616 = prepared[regimen_col].astype("string").str.contains("616", case=False, na=False).any()
    if has_616:
        st.error(
            "ALERTA DE AUDITORIA: Se detectaron facturas recibidas con Regimen 616 (Sin obligaciones fiscales). "
            "Se sugiere revision inmediata para evitar no deducibilidad."
        )


def render_kpi_row(dataset: dict) -> None:
    kpis = dataset["insights"]["kpis"]
    variation = dataset["insights"]["variation"]
    risk = dataset["insights"]["risk"]

    ingresos = float(kpis.get("ingresos_mxn") or 0)
    egresos = float(kpis.get("egresos_mxn") or 0)
    balance = ingresos - egresos

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            build_kpi_card("Ingresos MXN", fmt_money_card(ingresos), fmt_delta_label(variation.get("variacion_ingresos_pct")), "green"),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            build_kpi_card("Egresos MXN", fmt_money_card(egresos), fmt_delta_label(variation.get("variacion_egresos_pct")), "red"),
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(build_balance_card(balance, risk), unsafe_allow_html=True)


def render_document_counts_row(dataset: dict) -> None:
    kpis = dataset["insights"]["kpis"]
    emitidos = int(kpis.get("num_cfdi_emitidos") or 0)
    recibidos = int(kpis.get("num_cfdi_recibidos") or 0)
    pagos = int(kpis.get("num_pagos") or 0)

    st.markdown(
        f"""
        <div class="mini-kpi-grid">
            <div class="mini-kpi-card">
                <div class="mini-kpi-label">Facturas emitidas</div>
                <div class="mini-kpi-value">{emitidos:,}</div>
            </div>
            <div class="mini-kpi-card">
                <div class="mini-kpi-label">Facturas recibidas</div>
                <div class="mini-kpi-value">{recibidos:,}</div>
            </div>
            <div class="mini-kpi-card">
                <div class="mini-kpi-label">Pagos detectados</div>
                <div class="mini-kpi-value">{pagos:,}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_balance_row(dataset: dict) -> None:
    proveedores_df = pd.DataFrame(dataset["insights"]["top_proveedores"])
    timeseries = get_balance_timeseries(dataset)
    emitidas_df = _get_raw_frame(dataset, "df_emitidas")
    recibidas_df = _get_raw_frame(dataset, "df_recibidas")

    left, right = st.columns([1, 1.6])
    with left:
        render_card_header("CFDI emitidos vs recibidos", "Comprobantes y pagos por rol")
        if go is None or (emitidas_df.empty and recibidas_df.empty):
            st.info("Sin datos crudos suficientes para construir la distribucion documental del corte.")
        else:
            st.plotly_chart(build_mix_donut(emitidas_df, recibidas_df), width="stretch")

    with right:
        render_card_header("Balance mensual acumulado", "Ingreso -> Egreso -> Balance")
        if timeseries.empty:
            st.info("Aun no hay historial suficiente para construir la grafica de balance.")
        elif go is None:
            st.bar_chart(timeseries.set_index("periodo")[["ingresos_mxn", "egresos_mxn"]], height=360)
        else:
            st.plotly_chart(build_balance_combo_chart(timeseries), width="stretch")


def render_trend_row(dataset: dict) -> None:
    history = get_trend_timeseries(dataset)
    proveedores_df = pd.DataFrame(dataset["insights"]["top_proveedores"])

    left, right = st.columns([1.4, 0.95])
    with left:
        render_card_header("Tendencia ingresos vs egresos", "Comparativa mensual")
        if go is None:
            st.line_chart(history.set_index("periodo")[["ingresos_mxn", "egresos_mxn"]], height=360)
        else:
            if len(history) == 1:
                st.plotly_chart(build_single_period_chart(history), width="stretch")
            else:
                st.plotly_chart(build_trend_chart(history), width="stretch")

    with right:
        render_card_header("Concentracion egresos", "Top proveedores del corte")
        if proveedores_df.empty or "monto_total_mxn" not in proveedores_df.columns:
            st.info("Aun no hay proveedores con datos para este corte.")
        elif go is None:
            render_rank_table(proveedores_df)
        else:
            st.plotly_chart(build_expense_concentration_donut(proveedores_df), width="stretch")


def render_counterparties(dataset: dict) -> None:
    proveedores_df = pd.DataFrame(dataset["insights"]["top_proveedores"])
    render_card_header("Pareto de proveedores", "Concentracion de gasto")
    if proveedores_df.empty or "monto_total_mxn" not in proveedores_df.columns:
        st.info("Aun no hay proveedores con datos para construir el pareto.")
    elif go is None:
        render_rank_table(proveedores_df)
    else:
        st.plotly_chart(build_pareto_bar(proveedores_df), width="stretch")


def render_signals(dataset: dict) -> None:
    st.markdown("### Senales ejecutivas")
    signals = dataset["insights"]["risk"]["signals"]
    if not signals:
        st.info("No se detectaron senales relevantes para el periodo.")
        return
    for signal in signals:
        st.markdown(
            f'<div class="signal-item"><div class="signal-label">{translate_signal(signal["severity"])}</div><div class="signal-text">{signal["message"]}</div></div>',
            unsafe_allow_html=True,
        )


def render_operations_table(dataset: dict) -> None:
    st.markdown("### Detalle operativo")
    timeseries = pd.DataFrame(dataset.get("range_timeseries") or dataset["timeseries"])
    if timeseries.empty:
        st.info("No hay tabla historica disponible.")
        return
    st.dataframe(
        timeseries,
        width="stretch",
        hide_index=True,
        column_config={
            "ingresos_mxn": st.column_config.NumberColumn("Ingresos", format="$ %,.2f"),
            "egresos_mxn": st.column_config.NumberColumn("Egresos", format="$ %,.2f"),
            "balance_mxn": st.column_config.NumberColumn("Balance", format="$ %,.2f"),
            "ingresos_acumulados_mxn": st.column_config.NumberColumn("Ingresos acumulados", format="$ %,.2f"),
            "egresos_acumulados_mxn": st.column_config.NumberColumn("Egresos acumulados", format="$ %,.2f"),
            "balance_acumulado_mxn": st.column_config.NumberColumn("Balance acumulado", format="$ %,.2f"),
        },
    )


def render_card_header(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="section-card">
            <div class="section-heading">{title}</div>
            <div class="section-subheading">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_kpi_card(label: str, value: str, delta: str, tone: str) -> str:
    tone_class = "kpi-value-green" if tone == "green" else "kpi-value-red"
    return (
        '<div class="kpi-shell">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value {tone_class}">{value}</div>'
        f'<div class="kpi-help">{delta}</div>'
        "</div>"
    )


def build_balance_card(balance: float, risk: dict) -> str:
    badge = translate_risk_level(risk["level"]).lower()
    tone = "kpi-value-green" if balance >= 0 else "kpi-value-red"
    return (
        '<div class="kpi-shell">'
        '<div class="kpi-label">Balance neto</div>'
        f'<div class="kpi-value {tone}">{fmt_money_card(balance)}</div>'
        f'<div class="risk-badge risk-badge-{badge}">Riesgo {badge}</div>'
        "</div>"
    )


def get_trend_timeseries(dataset: dict) -> pd.DataFrame:
    history = pd.DataFrame(dataset.get("timeseries") or [])
    if history.empty:
        history = pd.DataFrame(dataset.get("range_timeseries") or [])
    if history.empty:
        return history
    filtered = filter_timeseries_to_active_year(dataset, history)
    return filtered.tail(12).copy()


def get_balance_timeseries(dataset: dict) -> pd.DataFrame:
    range_ts = pd.DataFrame(dataset.get("range_timeseries") or [])
    history = pd.DataFrame(dataset.get("timeseries") or [])
    if len(range_ts) >= 2:
        selected = range_ts.copy()
    elif len(history) >= 2:
        selected = filter_timeseries_to_active_year(dataset, history).tail(6).copy()
    elif not range_ts.empty:
        selected = range_ts.copy()
    else:
        selected = history.copy()
    if selected.empty:
        return selected
    selected["balance_mxn"] = selected["ingresos_mxn"] - selected["egresos_mxn"]
    selected["mes_corto"] = selected["periodo"].map(format_month_label)
    return selected


def get_natural_year_balance_timeseries(dataset: dict) -> pd.DataFrame:
    history = pd.DataFrame(dataset.get("timeseries") or [])
    if history.empty:
        history = pd.DataFrame(dataset.get("range_timeseries") or [])
    if history.empty:
        return history

    active_year = get_active_year_from_dataset(dataset)
    if active_year is None:
        selected = history.sort_values("periodo").reset_index(drop=True).copy()
    else:
        selected = filter_timeseries_to_active_year(dataset, history)
        selected = complete_natural_year_timeseries(selected, active_year)

    if selected.empty:
        return selected
    selected["balance_mxn"] = selected["ingresos_mxn"] - selected["egresos_mxn"]
    selected["mes_corto"] = selected["periodo"].map(format_month_label)
    return selected


def filter_timeseries_to_active_year(dataset: dict, timeseries: pd.DataFrame) -> pd.DataFrame:
    if timeseries.empty or "periodo" not in timeseries.columns:
        return timeseries

    active_year = get_active_year_from_dataset(dataset)
    if active_year is None:
        return timeseries.sort_values("periodo").reset_index(drop=True)

    filtered = timeseries[
        timeseries["periodo"].astype(str).str.startswith(f"{active_year:04d}-")
    ].copy()
    if filtered.empty:
        filtered = timeseries.copy()
    return filtered.sort_values("periodo").reset_index(drop=True)


def complete_natural_year_timeseries(timeseries: pd.DataFrame, year: int) -> pd.DataFrame:
    months = pd.DataFrame({"periodo": [f"{year:04d}-{month:02d}" for month in range(1, 13)]})
    merged = months.merge(timeseries, on="periodo", how="left")

    numeric_columns = [
        "ingresos_mxn",
        "egresos_mxn",
        "num_cfdi_emitidos",
        "num_cfdi_recibidos",
        "num_pagos",
        "ticket_promedio_emitido",
        "ticket_promedio_recibido",
        "balance_mxn",
        "ingresos_acumulados_mxn",
        "egresos_acumulados_mxn",
        "balance_acumulado_mxn",
        "emitidos_acumulados",
        "recibidos_acumulados",
        "pagos_acumulados",
    ]
    for column in numeric_columns:
        if column in merged.columns:
            merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0.0)

    return merged.sort_values("periodo").reset_index(drop=True)


def get_active_year_from_dataset(dataset: dict) -> int | None:
    candidates = [
        dataset.get("period_end"),
        dataset.get("period_start"),
        dataset.get("periodo"),
    ]
    for value in candidates:
        text = str(value or "").strip()
        if len(text) >= 4 and text[:4].isdigit():
            return int(text[:4])
    return None


def build_trend_chart(timeseries: pd.DataFrame) -> "go.Figure":
    tokens = get_visual_tokens()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=timeseries["periodo"].map(format_month_label),
            y=timeseries["ingresos_mxn"],
            mode="lines+markers",
            name="Ingresos",
            line={"color": C_INGRESO, "width": 3},
            marker={"size": 9, "line": {"color": tokens["marker_line"], "width": 2}},
            hovertemplate="Ingresos: $%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=timeseries["periodo"].map(format_month_label),
            y=timeseries["egresos_mxn"],
            mode="lines+markers",
            name="Egresos",
            line={"color": C_EGRESO, "width": 3, "dash": "dash"},
            marker={"size": 9, "line": {"color": tokens["marker_line"], "width": 2}},
            hovertemplate="Egresos: $%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        **merged_plotly_layout(
            hovermode="x unified",
            xaxis=get_minimal_xaxis(),
            yaxis=get_minimal_yaxis(tokens, tickprefix="$"),
            height=360,
        )
    )
    return fig


def build_single_period_chart(timeseries: pd.DataFrame) -> "go.Figure":
    tokens = get_visual_tokens()
    row = timeseries.iloc[0]
    labels = ["Ingresos", "Egresos", "Balance"]
    values = [float(row["ingresos_mxn"]), float(row["egresos_mxn"]), float(row["balance_mxn"])]
    colors = [C_INGRESO, C_EGRESO, C_BALANCE]

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=values,
            marker={"color": colors},
            text=[f"${value:,.0f}" for value in values],
            textposition="outside",
            hovertemplate="%{x}: $%{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        **merged_plotly_layout(
            showlegend=False,
            xaxis=get_minimal_xaxis(),
            yaxis=get_minimal_yaxis(tokens, tickprefix="$"),
            height=360,
        )
    )
    return fig


def build_balance_combo_chart(timeseries: pd.DataFrame) -> "go.Figure":
    tokens = get_visual_tokens()
    if timeseries.empty:
        return go.Figure()

    chart_df = timeseries.copy()
    if "periodo" in chart_df.columns:
        chart_df = chart_df.sort_values("periodo").reset_index(drop=True)

    for column in ["ingresos_mxn", "egresos_mxn", "balance_mxn"]:
        if column not in chart_df.columns:
            chart_df[column] = 0
        chart_df[column] = pd.to_numeric(chart_df[column], errors="coerce").fillna(0.0)

    chart_df["mes_corto"] = chart_df["periodo"].map(format_month_label)
    months = chart_df["mes_corto"]
    ingresos = chart_df["ingresos_mxn"]
    egresos = -chart_df["egresos_mxn"].abs()
    balance = chart_df["balance_mxn"]
    max_abs = max(
        float(ingresos.abs().max() or 0),
        float(egresos.abs().max() or 0),
        float(balance.abs().max() or 0),
        1.0,
    )
    y_limit = max_abs * 1.25

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=months,
            y=ingresos,
            name="Ingresos",
            marker={"color": "#2ECC71"},
            hovertemplate="Ingresos: $%{y:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=months,
            y=egresos,
            name="Egresos",
            marker={"color": "#E74C3C"},
            customdata=chart_df["egresos_mxn"],
            hovertemplate="Egresos: $%{customdata:,.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=months,
            y=balance,
            mode="lines+markers",
            name="Balance neto",
            line={"color": "#3498DB", "width": 3},
            marker={"size": 8, "color": "#3498DB", "line": {"color": tokens["text"], "width": 1.2}},
            hovertemplate="Balance: $%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        **merged_plotly_layout(
            barmode="group",
            hovermode="x unified",
            bargap=0.40,
            bargroupgap=0.08,
            legend={
                "orientation": "h",
                "y": 1.12,
                "x": 0,
                "bgcolor": "rgba(0,0,0,0)",
                "borderwidth": 0,
                "font": get_plotly_font(tokens, muted=True),
            },
            xaxis={
                **get_minimal_xaxis(),
                "tickmode": "array",
                "tickvals": months.tolist(),
                "ticktext": months.tolist(),
            },
            yaxis={
                **get_minimal_yaxis(tokens, tickprefix="$"),
                "range": [-y_limit, y_limit],
            },
            height=380,
        )
    )
    return fig


def build_expense_concentration_donut(frame: pd.DataFrame) -> "go.Figure":
    tokens = get_visual_tokens()
    if frame.empty or "monto_total_mxn" not in frame.columns:
        return go.Figure()
    prepared = frame.copy().sort_values("monto_total_mxn", ascending=False)
    if prepared.empty:
        return go.Figure()
    top = prepared.head(4).copy()
    others = prepared.iloc[4:]
    labels = top["nombre_counterparty"].astype(str).str[:24].tolist()
    values = top["monto_total_mxn"].tolist()
    colors = [C_BALANCE, C_INGRESO, C_WARN, "#B54E24"]
    if not others.empty:
        labels.append("Otros")
        values.append(float(others["monto_total_mxn"].sum()))
        colors.append(C_OTHER)
    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.62,
            marker={"colors": colors, "line": {"color": tokens["marker_line"], "width": 3}},
            textinfo="none",
            sort=False,
            hovertemplate="%{label}: $%{value:,.0f} MXN (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(
        **get_compact_donut_layout(tokens, height=360)
    )
    return fig


def build_regimen_distribution_donut(frame: pd.DataFrame) -> "go.Figure":
    tokens = get_visual_tokens()
    if frame.empty:
        return go.Figure()

    prepared = frame.copy()
    tipo_col = _find_first_column(prepared, ["TIPO_COMPROB", "TIPO_COMPROBANTE", "TIPODECOMPROBANTE"])
    if tipo_col:
        prepared = prepared[prepared[tipo_col].astype(str).str.upper().eq("I")].copy()
    if prepared.empty:
        return go.Figure()

    code_col = _find_first_column(prepared, ["REGIMEN_CODIGO", "RECEPTOR_REGIMENFISCAL"])
    desc_col = _find_first_column(prepared, ["REGIMEN_DESC", "RECEPTOR_REGIMEN_DESC"])
    amount_col = _find_first_column(prepared, ["TOTAL", "TOTAL_MXN", "MONTO_TOTAL_MXN"])

    if amount_col is None or (code_col is None and desc_col is None):
        return go.Figure()

    prepared["__amount"] = pd.to_numeric(prepared[amount_col], errors="coerce").fillna(0.0)
    prepared["__regimen"] = prepared.apply(
        lambda row: _format_regimen_label(
            row.get(code_col) if code_col else None,
            row.get(desc_col) if desc_col else None,
        ),
        axis=1,
    )

    grouped = (
        prepared.groupby("__regimen", dropna=False)
        .agg(total=("__amount", "sum"), num_cfdi=("__amount", "size"))
        .reset_index()
        .rename(columns={"__regimen": "regimen"})
        .sort_values("total", ascending=False)
    )
    grouped = grouped[grouped["total"] > 0].reset_index(drop=True)
    if grouped.empty:
        return go.Figure()

    palette = ["#1D4ED8", "#60A5FA", "#93C5FD", "#1E3A8A", "#BFDBFE", "#64748B", "#CBD5E1", "#0F172A"]
    colors = [palette[index % len(palette)] for index in range(len(grouped))]
    fig = go.Figure(
        go.Pie(
            labels=grouped["regimen"],
            values=grouped["total"],
            customdata=grouped[["num_cfdi"]].to_numpy(),
            hole=0.62,
            marker={"colors": colors, "line": {"color": tokens["marker_line"], "width": 3}},
            textinfo="none",
            sort=False,
            hovertemplate="%{label}: $%{value:,.0f} MXN<br>%{customdata[0]} CFDI<extra></extra>",
        )
    )
    fig.update_layout(
        **get_compact_donut_layout(tokens, height=360)
    )
    return fig


def build_mix_donut(emitidas_df: pd.DataFrame, recibidas_df: pd.DataFrame) -> "go.Figure":
    tokens = get_visual_tokens()
    counts = _build_document_flow_counts(emitidas_df, recibidas_df)
    if counts.empty:
        return go.Figure()

    flow_colors = [
        "#E07A5F",  # Emitidos
        "#A44A3F",  # Pagos emitidos
        "#5B8CC0",  # Recibidos
        "#1F4E79",  # Pagos recibidos
    ]

    fig = go.Figure(
        go.Pie(
            labels=counts["label"],
            values=counts["count"],
            customdata=counts[["base_label"]].to_numpy(),
            hole=0.60,
            marker={
                "colors": flow_colors,
                "line": {"color": tokens["marker_line"], "width": 3},
            },
            textinfo="none",
            sort=False,
            hovertemplate="%{customdata[0]}: %{value} CFDIs<extra></extra>",
        )
    )
    fig.update_layout(
        **get_compact_donut_layout(tokens, height=360)
    )
    return fig


def _build_document_flow_counts(emitidas_df: pd.DataFrame, recibidas_df: pd.DataFrame) -> pd.DataFrame:
    emitidos_docs, pagos_emitidos = _split_document_role_counts(emitidas_df)
    recibidos_docs, pagos_recibidos = _split_document_role_counts(recibidas_df)

    frame = pd.DataFrame(
        [
            {"base_label": "Emitidos", "label": f"Emitidos · {emitidos_docs} CFDI", "count": emitidos_docs},
            {"base_label": "Pagos emitidos", "label": f"Pagos emitidos · {pagos_emitidos} CFDI", "count": pagos_emitidos},
            {"base_label": "Recibidos", "label": f"Recibidos · {recibidos_docs} CFDI", "count": recibidos_docs},
            {"base_label": "Pagos recibidos", "label": f"Pagos recibidos · {pagos_recibidos} CFDI", "count": pagos_recibidos},
        ]
    )
    return frame[frame["count"] > 0].reset_index(drop=True)


def _split_document_role_counts(frame: pd.DataFrame) -> tuple[int, int]:
    if frame.empty:
        return 0, 0

    tipo_col = _find_first_column(frame, ["TIPO_COMPROB", "TIPO_COMPROBANTE", "TIPODECOMPROBANTE"])
    if tipo_col is None:
        return int(len(frame)), 0

    tipos = frame[tipo_col].astype("string").str.upper().str.strip()
    pagos = int(tipos.eq("P").sum())
    comprobantes = int((tipos.ne("P") & tipos.ne("")).sum())
    return comprobantes, pagos


def build_pareto_bar(frame: pd.DataFrame) -> "go.Figure":
    tokens = get_visual_tokens()
    if frame.empty or "monto_total_mxn" not in frame.columns:
        return go.Figure()
    df = frame.copy().sort_values("monto_total_mxn", ascending=False).head(5)
    fig = go.Figure(
        go.Bar(
            x=df["monto_total_mxn"],
            y=df["nombre_counterparty"].astype(str).str[:26],
            orientation="h",
            marker={"color": build_rank_colors(len(df)), "line": {"width": 0}},
            hovertemplate="<b>%{y}</b><br>$%{x:,.0f} MXN<extra></extra>",
        )
    )
    fig.update_layout(
        **merged_plotly_layout(
            showlegend=False,
            xaxis=get_minimal_yaxis(tokens, tickprefix="$"),
            yaxis={**get_minimal_xaxis(), "title": None, "automargin": True, "autorange": "reversed"},
            height=max(280, len(df) * 54 + 40),
        )
    )
    return fig


def render_rank_table(frame: pd.DataFrame) -> None:
    if frame.empty or "monto_total_mxn" not in frame.columns:
        st.info("Sin registros relevantes.")
        return
    table = frame.copy().sort_values(by="monto_total_mxn", ascending=False)
    table = table.rename(
        columns={
            "nombre_counterparty": "Nombre",
            "rfc_counterparty": "RFC",
            "num_cfdi": "CFDI",
            "monto_total_mxn": "Monto",
            "porcentaje_del_total": "% del total",
        }
    )
    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        column_config={
            "Monto": st.column_config.NumberColumn("Monto", format="$ %,.2f"),
            "% del total": st.column_config.NumberColumn("% del total", format="%.2f %%"),
        },
    )


def build_rank_colors(length: int) -> list[str]:
    palette = [C_BALANCE, C_INGRESO, C_WARN, "#7E73D4", "#B54E24"]
    return [palette[index % len(palette)] for index in range(length)]


def _find_first_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    upper_lookup = {str(column).strip().upper(): column for column in frame.columns}
    for candidate in candidates:
        match = upper_lookup.get(candidate.upper())
        if match is not None:
            return match
    return None


def _get_raw_frame(dataset: dict, key: str) -> pd.DataFrame:
    insights = dataset.get("insights", {})
    frame = insights.get(key)
    if isinstance(frame, pd.DataFrame):
        return frame
    frame = dataset.get(key)
    if isinstance(frame, pd.DataFrame):
        return frame
    return pd.DataFrame()


def _format_regimen_label(code: object, desc: object) -> str:
    code_text = str(code or "").strip()
    desc_text = str(desc or "").strip()
    if code_text and desc_text and desc_text.upper() != code_text.upper():
        return f"{code_text} - {desc_text}"
    if code_text:
        return code_text
    if desc_text:
        return desc_text
    return "Sin regimen"


def _format_inline_title(text: str) -> str:
    return (
        '<div style="'
        f"font-size: 1.06rem;"
        f"font-weight: 700;"
        f"color: {C_HEADING};"
        f"font-family: {C_FONT_STACK};"
        'margin-bottom: 0.35rem;">'
        f"{text}"
        "</div>"
    )


def fmt_money_card(value: float) -> str:
    return f"${float(value or 0):,.0f}"


def fmt_currency(value: float) -> str:
    return f"${float(value or 0):,.2f} MXN"


def fmt_delta_label(value: float | None) -> str:
    if value is None:
        return "Sin comparativo previo"
    if value > 0:
        return f"Sube {float(value):.1f}% vs periodo anterior"
    if value < 0:
        return f"Baja {abs(float(value)):.1f}% vs periodo anterior"
    return "Sin cambio vs periodo anterior"


def translate_risk_level(level: str) -> str:
    return {"low": "bajo", "medium": "medio", "high": "alto"}.get(level, level)


def translate_signal(level: str) -> str:
    return {"low": "Bajo", "medium": "Medio", "high": "Alto"}.get(level, level)


def format_month_label(periodo: str) -> str:
    months = {
        "01": "Ene",
        "02": "Feb",
        "03": "Mar",
        "04": "Abr",
        "05": "May",
        "06": "Jun",
        "07": "Jul",
        "08": "Ago",
        "09": "Sep",
        "10": "Oct",
        "11": "Nov",
        "12": "Dic",
    }
    if "-" not in str(periodo):
        return str(periodo)
    _, month = str(periodo).split("-", 1)
    return months.get(month[:2], str(periodo))
