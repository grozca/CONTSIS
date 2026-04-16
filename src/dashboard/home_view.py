from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

try:
    import plotly.express as px
except ModuleNotFoundError:
    px = None

try:
    from src.app.use_cases import get_dashboard_context
    from src.dashboard.executive_view import (
        build_balance_combo_chart,
        build_regimen_distribution_donut,
        get_natural_year_balance_timeseries,
    )
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.app.use_cases import get_dashboard_context
    from src.dashboard.executive_view import (
        build_balance_combo_chart,
        build_regimen_distribution_donut,
        get_natural_year_balance_timeseries,
    )


CHART_TITLE_STYLE = (
    "font-size: 1.06rem;"
    "font-weight: 700;"
    "color: #1A202C;"
    "font-family: Inter, Roboto, 'Segoe UI', system-ui, sans-serif;"
    "margin-bottom: 0.35rem;"
)
DONUT_FONT_STACK = "Inter, Roboto, 'Segoe UI', system-ui, sans-serif"


def render_home(
    selected_rfc: str | None,
    selected_period: str,
    companies: list[dict[str, Any]],
    periods: list[str],
) -> None:
    company_label = get_company_label(selected_rfc, companies)

    st.markdown(
        f"""
        <div class="shell-hero">
            <div class="shell-hero-top">Resumen ejecutivo</div>
            <div class="shell-hero-main">
                <div class="shell-hero-copy">
                    <div class="shell-hero-title">{company_label}</div>
                    <div class="shell-hero-subtitle">Periodo: {selected_period}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_period = render_home_period_selector(selected_rfc, selected_period, periods)
    render_health_snapshot(selected_rfc, selected_period)

    st.markdown("### Estado rapido")
    col1, col2, col3 = st.columns(3)
    col1.metric("Empresas disponibles", len(companies))
    col2.metric("Periodos disponibles", len(periods))
    col3.metric("Periodo activo", selected_period)

    st.markdown("### Proximos pasos recomendados")
    render_quick_actions()


def render_health_snapshot(selected_rfc: str | None, selected_period: str) -> None:
    if not selected_rfc:
        st.info("Selecciona una empresa desde el Directorio del Despacho para visualizar su resumen ejecutivo.")
        return

    try:
        dataset = get_dashboard_context(selected_period, selected_rfc, analysis_mode="monthly")
    except Exception as exc:
        if "No hay KPIs cargados" in str(exc):
            render_missing_kpis_state(selected_rfc, selected_period)
        else:
            st.info(f"No se pudo cargar la salud contable para {selected_period}: {exc}")
        return

    kpis = dataset.get("insights", {}).get("kpis", {})
    comparison = dataset.get("comparison") or dataset.get("insights", {}).get("variation", {})
    ingresos = float(kpis.get("ingresos_mxn") or 0)
    egresos = float(kpis.get("egresos_mxn") or 0)
    utilidad = ingresos - egresos

    prev_ingresos = comparison.get("ingresos_anterior")
    prev_egresos = comparison.get("egresos_anterior")
    prev_utilidad = None
    if prev_ingresos is not None or prev_egresos is not None:
        prev_utilidad = float(prev_ingresos or 0) - float(prev_egresos or 0)

    utilidad_delta = build_utility_delta(utilidad, prev_utilidad)
    utilidad_delta_color = "normal" if prev_utilidad is None or utilidad >= prev_utilidad else "inverse"

    st.markdown("### Indicadores clave del periodo")
    col1, col2, col3 = st.columns(3)

    with col1:
        with st.container(border=True):
            st.metric("INGRESOS TOTALES", fmt_money(ingresos))
            st.caption("Monto total detectado en XML de ingreso.")

    with col2:
        with st.container(border=True):
            st.metric("EGRESOS TOTALES", fmt_money(egresos))
            st.caption("Suma de gastos y compras del periodo.")

    with col3:
        with st.container(border=True):
            st.metric(
                "UTILIDAD ESTIMADA",
                fmt_money(utilidad),
                delta=utilidad_delta,
                delta_color=utilidad_delta_color,
            )
            st.caption("Diferencia entre ingresos y egresos respecto al mes anterior.")

    st.markdown("### Analisis visual rapido")
    chart_left, chart_right = st.columns([1.25, 1])

    with chart_left:
        with st.container(border=True):
            st.markdown(_format_chart_title("Tendencia de ingresos y egresos"), unsafe_allow_html=True)
            timeseries = get_natural_year_balance_timeseries(dataset)
            if timeseries.empty:
                st.info("Aun no hay historial suficiente.")
            else:
                fig_trend = build_balance_combo_chart(timeseries)
                fig_trend.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_trend, width="stretch", config={"displayModeBar": False})

    with chart_right:
        with st.container(border=True):
            st.markdown(_format_chart_title("Distribucion por regimen fiscal en XML recibidos"), unsafe_allow_html=True)
            recibidas_df = _get_insight_frame(dataset, "df_recibidas")
            if not isinstance(recibidas_df, pd.DataFrame) or recibidas_df.empty:
                st.info("Sin facturas recibidas con datos de regimen en este corte.")
            else:
                fig_donut = build_regimen_distribution_donut(recibidas_df)
                if not fig_donut.data:
                    st.info("No se pudo construir la distribucion de regimenes para este corte.")
                else:
                    fig_donut.update_layout(height=265, margin=dict(l=0, r=0, t=0, b=0))
                    st.plotly_chart(fig_donut, width="stretch", config={"displayModeBar": False})

    liquidity_left, liquidity_right = st.columns(2)

    with liquidity_left:
        with st.container(border=True):
            st.markdown(_format_chart_title("Estatus de liquidez en XML emitidos (PUE vs PPD)"), unsafe_allow_html=True)
            emitidas_df = _get_insight_frame(dataset, "df_emitidas")
            fig_liquidity = _generate_liquidity_donut(emitidas_df, "emitidas")
            if fig_liquidity is None:
                st.info("Sin facturas emitidas con metodo de pago PUE/PPD para este corte.")
            else:
                fig_liquidity.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_liquidity, width="stretch", config={"displayModeBar": False})

    with liquidity_right:
        with st.container(border=True):
            st.markdown(_format_chart_title("Estatus de liquidez en XML recibidos (PUE vs PPD)"), unsafe_allow_html=True)
            recibidas_df = _get_insight_frame(dataset, "df_recibidas")
            fig_liquidity = _generate_liquidity_donut(recibidas_df, "recibidas")
            if fig_liquidity is None:
                st.info("Sin facturas recibidas con metodo de pago PUE/PPD para este corte.")
            else:
                fig_liquidity.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_liquidity, width="stretch", config={"displayModeBar": False})


def render_quick_actions() -> None:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("Revisar XMLs", width="stretch", key="home-xmls"):
            st.session_state["pending_section"] = "Operación"
            st.rerun()
    with col2:
        if st.button("Ver graficas", width="stretch", key="home-dashboard"):
            st.session_state["pending_section"] = "Dashboard"
            st.rerun()
    with col3:
        if st.button("Generar Word", width="stretch", key="home-report"):
            st.session_state["pending_section"] = "Informes"
            st.rerun()
    with col4:
        if st.button("Enviar alerta", width="stretch", key="home-alert"):
            st.session_state["pending_section"] = "Alertas"
            st.rerun()


def render_missing_kpis_state(selected_rfc: str, selected_period: str) -> None:
    with st.container(border=True):
        st.warning(f"Todavia no hay KPIs cargados para `{selected_rfc}` en `{selected_period}`.")
        st.write(
            "La app ya esta corriendo bien. Lo que falta es detectar XMLs del periodo correcto y construir los analytics "
            "para poder llenar el resumen ejecutivo."
        )
        st.caption("Si estas en una instalacion nueva, este comportamiento es normal hasta terminar la primera corrida.")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Ir a Operacion", width="stretch", key=f"missing-kpis-ops-{selected_rfc}-{selected_period}"):
                st.session_state["pending_section"] = "Operación"
                st.rerun()
        with col2:
            if st.button("Ir al Directorio", width="stretch", key=f"missing-kpis-despacho-{selected_rfc}-{selected_period}"):
                st.session_state["pending_section"] = "Directorio del Despacho"
                st.rerun()

        st.caption("Siguiente paso recomendado: revisa la carpeta compartida de XMLs y luego ejecuta el flujo de Operacion para ese periodo.")


def render_home_period_selector(selected_rfc: str | None, selected_period: str, periods: list[str]) -> str:
    toggle_key = f"home-period-toggle-{selected_rfc or 'none'}"
    button_key = f"home-period-button-{selected_rfc or 'none'}"

    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("Cambiar periodo", key=button_key, width="stretch"):
            st.session_state[toggle_key] = not st.session_state.get(toggle_key, False)
    with col2:
        st.caption(f"Periodo activo en resumen: {selected_period}")

    if not st.session_state.get(toggle_key, False):
        return selected_period

    with st.container(border=True):
        st.markdown("**Seleccion de periodo**")
        if periods:
            select_key = f"home-period-select-{selected_rfc or 'none'}"
            if st.session_state.get(select_key) not in periods:
                st.session_state[select_key] = selected_period if selected_period in periods else periods[0]
            selected_period = st.selectbox("Periodo", options=periods, key=select_key)
            st.caption("Se priorizan los periodos que ya fueron detectados en XMLs o analytics.")
        else:
            selected_period = render_home_manual_period_selector(selected_rfc, selected_period)

    st.session_state["selected_period"] = selected_period
    return selected_period


def render_home_manual_period_selector(selected_rfc: str | None, selected_period: str) -> str:
    year_key = f"home-period-year-{selected_rfc or 'none'}"
    month_key = f"home-period-month-{selected_rfc or 'none'}"
    sync_key = f"home-period-sync-{selected_rfc or 'none'}"
    current_year, current_month = parse_period_value(selected_period)
    current_year = clamp_home_period_year(current_year)
    minimum_year, maximum_year = get_home_year_bounds(current_year)

    if st.session_state.get(sync_key) != selected_period:
        st.session_state[year_key] = current_year
        st.session_state[month_key] = current_month
        st.session_state[sync_key] = selected_period

    if st.session_state.get(year_key) not in range(minimum_year, maximum_year + 1):
        st.session_state[year_key] = current_year
    if st.session_state.get(month_key) not in range(1, 13):
        st.session_state[month_key] = current_month

    col1, col2 = st.columns(2)
    with col1:
        selected_year = st.number_input(
            "Año",
            min_value=minimum_year,
            max_value=maximum_year,
            step=1,
            key=year_key,
            format="%d",
        )
    with col2:
        selected_month = st.selectbox(
            "Mes",
            options=list(range(1, 13)),
            format_func=lambda value: f"{value:02d}",
            key=month_key,
        )

    selected_period = f"{int(selected_year):04d}-{int(selected_month):02d}"
    st.session_state[sync_key] = selected_period
    st.caption("No hay periodos detectados todavia. Puedes cambiar manualmente entre año y mes.")
    return selected_period


def get_home_year_bounds(current_year: int) -> tuple[int, int]:
    maximum_year = datetime.now().year
    safe_year = min(current_year, maximum_year)
    return safe_year - 5, maximum_year


def clamp_home_period_year(current_year: int) -> int:
    return min(current_year, datetime.now().year)


def parse_period_value(periodo: str) -> tuple[int, int]:
    try:
        year_text, month_text = periodo.split("-")
        return int(year_text), int(month_text)
    except Exception:
        today = datetime.now()
        return today.year, today.month


def get_company_label(selected_rfc: str | None, companies: list[dict[str, Any]]) -> str:
    if not selected_rfc:
        return "Seleccione una empresa"
    for company in companies:
        if company.get("rfc") == selected_rfc:
            return str(
                company.get("nombre")
                or company.get("nombre_corto")
                or company.get("razon_social")
                or selected_rfc
            )
    return selected_rfc


def build_utility_delta(current_value: float, previous_value: float | None) -> str:
    if previous_value is None:
        return "Sin comparativo previo"
    delta_value = current_value - previous_value
    prefix = "+" if delta_value >= 0 else "-"
    return f"{prefix}{fmt_money(abs(delta_value))} vs mes anterior"


def fmt_money(value: float) -> str:
    return f"${float(value or 0):,.2f}"


def _get_insight_frame(dataset: dict[str, Any], key: str) -> pd.DataFrame:
    insights = dataset.get("insights", {})
    frame = insights.get(key)
    if isinstance(frame, pd.DataFrame):
        return frame
    frame = dataset.get(key)
    if isinstance(frame, pd.DataFrame):
        return frame
    return pd.DataFrame()


def _generate_liquidity_donut(frame: pd.DataFrame, source: str):
    if px is None:
        return None

    summary = _prepare_liquidity_frame(frame, source)
    if summary.empty:
        return None
    summary = summary[summary["monto"] > 0].reset_index(drop=True)
    if summary.empty:
        return None
    summary["display_label"] = summary.apply(
        lambda row: _format_liquidity_label(row["categoria"], row["num_cfdi"]),
        axis=1,
    )

    color_map = _get_liquidity_color_map(source)
    fig = px.pie(
        summary,
        names="display_label",
        values="monto",
        hole=0.6,
        color="categoria",
        color_discrete_map=color_map,
        custom_data=["categoria", "num_cfdi"],
    )
    fig.update_traces(
        textinfo="none",
        sort=False,
        hovertemplate="%{customdata[0]}: $%{value:,.2f} MXN<br>%{customdata[1]} CFDI<extra></extra>",
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        showlegend=True,
        legend={
            "orientation": "v",
            "x": 0,
            "y": -0.02,
            "xanchor": "left",
            "yanchor": "bottom",
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "font": {
                "family": DONUT_FONT_STACK,
                "size": 12,
                "color": "#334155",
            },
        },
    )
    return fig


def _prepare_liquidity_frame(frame: pd.DataFrame, source: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["categoria", "monto", "num_cfdi"])

    method_col = _find_first_column(frame, ["METODO_PAGO", "MetodoPago", "metodo_pago"])
    amount_col = _find_first_column(frame, ["TOTAL", "SUBTOTAL_MXN", "TOTAL_MXN", "MONTO_TOTAL_MXN"])
    if method_col is None or amount_col is None:
        return pd.DataFrame(columns=["categoria", "monto", "num_cfdi"])

    prepared = frame.copy()
    prepared["__metodo"] = prepared[method_col].astype("string").str.upper().str.strip()
    prepared["__monto"] = pd.to_numeric(prepared[amount_col], errors="coerce").fillna(0.0)
    prepared = prepared[prepared["__metodo"].isin(["PUE", "PPD"])].copy()
    prepared = prepared[prepared["__monto"] > 0].copy()
    if prepared.empty:
        return pd.DataFrame(columns=["categoria", "monto", "num_cfdi"])

    label_map = {
        ("emitidas", "PUE"): "Cobro Contado (PUE)",
        ("emitidas", "PPD"): "Cobro Credito (PPD)",
        ("recibidas", "PUE"): "Pago Contado (PUE)",
        ("recibidas", "PPD"): "Pago Credito (PPD)",
    }
    prepared["categoria"] = prepared["__metodo"].map(lambda value: label_map[(source, value)])

    return (
        prepared.groupby("categoria", dropna=False)
        .agg(monto=("__monto", "sum"), num_cfdi=("__monto", "size"))
        .reset_index()
        .sort_values("monto", ascending=False)
    )


def _get_liquidity_color_map(source: str) -> dict[str, str]:
    if source == "emitidas":
        return {
            "Cobro Contado (PUE)": "#1E9E63",
            "Cobro Credito (PPD)": "#66C28A",
        }
    return {
        "Pago Contado (PUE)": "#E67E22",
        "Pago Credito (PPD)": "#C0392B",
    }


def _find_first_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    upper_lookup = {str(column).strip().upper(): column for column in frame.columns}
    for candidate in candidates:
        match = upper_lookup.get(candidate.upper())
        if match is not None:
            return match
    return None


def _format_chart_title(text: str) -> str:
    return f'<div style="{CHART_TITLE_STYLE}">{text}</div>'


def _format_liquidity_label(category: str, count: object) -> str:
    return f"{category} · {int(count or 0)} CFDI"
