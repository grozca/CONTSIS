from __future__ import annotations

from datetime import datetime
from pathlib import Path
from textwrap import dedent

import streamlit as st
import streamlit.components.v1 as components

try:
    from src.app.use_cases import (
        ActionResult,
        LOGO_PATH,
        build_analytics_for_period,
        default_period,
        discover_generated_files,
        export_bi_for_period,
        generate_client_report,
        get_company_options,
        get_dashboard_context,
        get_mail_configuration_status,
        get_operational_status,
        get_period_options,
        get_year_options,
        get_recent_execution_log,
        preview_company_alert_email,
        run_company_alert,
        run_alerts,
        run_operational_pipeline,
        run_operational_step,
    )
    from src.dashboard.executive_view import render_executive_dashboard_body
    from src.dashboard.despacho_view import render_despacho_home
    from src.dashboard.home_view import render_home
except ModuleNotFoundError:
    import sys

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.app.use_cases import (
        ActionResult,
        LOGO_PATH,
        build_analytics_for_period,
        default_period,
        discover_generated_files,
        export_bi_for_period,
        generate_client_report,
        get_company_options,
        get_dashboard_context,
        get_mail_configuration_status,
        get_operational_status,
        get_period_options,
        get_year_options,
        get_recent_execution_log,
        preview_company_alert_email,
        run_company_alert,
        run_alerts,
        run_operational_pipeline,
        run_operational_step,
    )
    from src.dashboard.executive_view import render_executive_dashboard_body
    from src.dashboard.despacho_view import render_despacho_home
    from src.dashboard.home_view import render_home

from src.app.pilot_preferences import (
    FILTER_ALL,
    clear_boveda_root_preference,
    filter_companies_by_owner,
    get_owner_filter_options,
    get_saved_owner_filter,
    save_boveda_root_preference,
    save_owner_filter_preference,
)
from src.utils.config import settings


st.set_page_config(page_title="CONTSIS Desk", page_icon=":office:", layout="wide")


def main() -> None:
    apply_shell_styles()
    render_sidebar_brand()

    pending_section = st.session_state.pop("pending_section", None)
    if pending_section is not None:
        st.session_state["active_section"] = pending_section

    all_companies = get_company_options()
    owner_filter = render_sidebar_pilot_controls(all_companies)
    companies = filter_companies_by_owner(all_companies, owner_filter)
    company_lookup = {str(item.get("rfc") or "").upper(): item for item in companies}
    selected_rfc = str(st.session_state.get("selected_rfc") or "").upper() or None
    if selected_rfc and selected_rfc not in company_lookup:
        selected_rfc = None
        st.session_state["selected_rfc"] = None

    render_sidebar_company_browser(companies, selected_rfc, total_company_count=len(all_companies))
    selected_rfc = str(st.session_state.get("selected_rfc") or "").upper() or None

    periods = get_period_options(selected_rfc) if selected_rfc else []
    period_default = periods[0] if periods else default_period()
    period_context_rfc = st.session_state.get("period_context_rfc")
    current_period = st.session_state.get("selected_period")
    period_widget_key = f"selected_period_widget_{selected_rfc or 'none'}"

    if period_context_rfc != selected_rfc:
        st.session_state["selected_period"] = period_default
        st.session_state["period_context_rfc"] = selected_rfc
    elif periods and current_period not in periods:
        st.session_state["selected_period"] = period_default
    elif not current_period:
        st.session_state["selected_period"] = period_default

    if periods:
        widget_period = st.session_state.get(period_widget_key)
        if widget_period not in periods:
            st.session_state[period_widget_key] = st.session_state.get("selected_period") or period_default
        selected_period = st.sidebar.selectbox(
            "Periodo de trabajo",
            options=periods,
            key=period_widget_key,
        )
        st.session_state["selected_period"] = selected_period
        st.sidebar.caption("Se priorizan periodos detectados en XML extraidos.")
    else:
        selected_period = render_manual_period_picker(selected_rfc, period_default)

    section = st.sidebar.radio(
        "Menu",
        ["Directorio del Despacho", "Resumen Ejecutivo", "Operación", "Tablero", "Informes", "Alertas"],
        key="active_section",
    )

    if section == "Directorio del Despacho":
        render_despacho_home(companies, all_companies, owner_filter)
    elif section == "Resumen Ejecutivo":
        if selected_rfc:
            render_home(selected_rfc, selected_period, all_companies, periods)
        else:
            st.info("Selecciona una empresa desde el Directorio del Despacho para abrir su resumen ejecutivo.")
    elif section == "Operación":
        render_operations(selected_rfc, selected_period)
    elif section == "Tablero":
        render_dashboard(selected_rfc, selected_period)
    elif section == "Informes":
        render_reports(selected_rfc, selected_period)
    elif section == "Alertas":
        render_alerts_module(selected_rfc, selected_period)


def apply_shell_styles() -> None:
    theme_tokens = """
        :root {
            --sr-navy: #002B49;
            --sr-accent: #00A396;
            --app-bg: var(--background-color);
            --app-surface: var(--secondary-background-color);
            --app-surface-strong: #FFFFFF;
            --app-border: rgba(0, 0, 0, 0.05);
            --app-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
            --app-shadow-hover: 0 14px 28px rgba(15, 23, 42, 0.12);
            --app-text: var(--text-color);
            --app-card-title: var(--text-color);
            --app-muted: rgba(0, 43, 73, 0.72);
            --app-check-bg: #FFFFFF;
            --app-check-title: var(--text-color);
            --app-check-detail: rgba(0, 43, 73, 0.72);
            --app-banner-bg: #FFFBEB;
            --app-banner-border: #FDE68A;
            --app-banner-text: #92400E;
        }
    """
    st.markdown(
        "<style>\n"
        + theme_tokens
        + """
        .stApp {
            background-color: var(--app-bg);
            color: var(--app-text);
        }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 95%;
        }
        section[data-testid="stSidebar"] div.stButton > button {
            text-align: left;
            min-height: 2.6rem;
            border-radius: 10px;
            white-space: normal;
            padding: 0.5rem 0.75rem;
        }
        .sidebar-company-active {
            background: rgba(0, 163, 150, 0.10);
            border: 1px solid rgba(0, 163, 150, 0.24);
            border-radius: 12px;
            padding: 0.8rem 0.9rem;
            margin-bottom: 0.85rem;
            color: var(--app-text);
        }
        .sidebar-company-active-label {
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--app-muted);
            margin-bottom: 0.25rem;
        }
        .sidebar-company-active-name {
            font-size: 0.95rem;
            font-weight: 700;
            color: var(--app-card-title);
        }
        .sidebar-company-active-rfc {
            font-size: 0.82rem;
            color: var(--app-muted);
            margin-top: 0.15rem;
        }
        .shell-hero, .module-header, .alert-hero {
            background: var(--sr-navy) !important;
            border: 1px solid rgba(255,255,255,0.08);
            border-bottom: 4px solid var(--sr-accent) !important;
            color: #f8fafc !important;
            border-radius: 12px;
            padding: 24px 30px;
            margin-bottom: 1.5rem;
            box-shadow: 0 10px 18px rgba(0,0,0,0.24);
        }
        .module-header {
            margin-bottom: 1.1rem;
        }
        .shell-hero-top, .module-header-top, .alert-hero-top {
            color: rgba(255,255,255,0.7);
            text-transform: uppercase;
            letter-spacing: 0.1em;
            font-size: 0.75rem;
            font-weight: 600;
            margin-bottom: 0.45rem;
        }
        .shell-hero-main, .module-header-main {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .shell-hero-copy, .module-header-copy {
            flex: 1;
            min-width: 0;
        }
        .shell-hero-logo, .module-header-logo {
            width: auto;
            height: 40px;
            object-fit: contain;
            filter: brightness(0) invert(1);
            flex-shrink: 0;
        }
        .shell-hero-title, .module-header-title {
            color: #f8fafc;
            font-size: 2rem;
            font-weight: 700;
            font-family: Arial, "Segoe UI", sans-serif;
            letter-spacing: -0.02em;
            margin-bottom: 0.15rem;
            line-height: 1.1;
            text-decoration: none;
        }
        .shell-hero-subtitle, .module-header-subtitle {
            color: rgba(255,255,255,0.84);
            font-size: 0.98rem;
        }
        .module-header-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.9rem;
        }
        .module-header-tag {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 6px;
            background: rgba(255,255,255,0.15);
            border: 1px solid rgba(255,255,255,0.2);
            color: #f8fafc;
            font-size: 0.82rem;
            font-weight: 500;
        }
        .shell-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(180px, 1fr));
            gap: 14px;
        }
        .shell-card, .status-card, .alert-metric-card, .panel-card, .op-summary-card {
            background: var(--app-surface);
            border: 1px solid var(--app-border);
            border-radius: 12px;
            padding: 20px;
            box-shadow: var(--app-shadow);
        }
        .shell-card {
            background: #FFFFFF;
            border: 1px solid #E1E4E8;
            padding: 20px;
            min-height: 148px;
            box-shadow: 0 8px 16px rgba(0,0,0,0.05);
            transition: transform 0.2s ease;
        }
        .shell-card:hover {
            transform: translateY(-2px);
            box-shadow: var(--app-shadow-hover);
        }
        .shell-card h3 {
            margin-top: 0;
            margin-bottom: 0.45rem;
            color: var(--app-card-title);
        }
        .shell-subtle {
            color: var(--app-muted);
            font-size: 0.95rem;
        }
        .status-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(180px, 1fr));
            gap: 12px;
            margin-bottom: 1rem;
        }
        .status-label {
            color: var(--app-muted);
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .status-value {
            color: var(--text-color);
            font-size: 1.8rem;
            font-weight: 700;
            margin-top: 0.35rem;
        }
        .check-item {
            display: flex;
            align-items: flex-start;
            gap: 10px;
            background: var(--app-check-bg);
            border: 1px solid var(--app-border);
            border-radius: 12px;
            padding: 12px 14px;
            margin-bottom: 10px;
            box-shadow: var(--app-shadow);
        }
        .check-text-title {
            font-weight: 700;
            color: var(--app-check-title);
        }
        .check-text-detail {
            color: var(--app-check-detail);
        }
        .check-pill-ok, .check-pill-pending {
            display: inline-block;
            min-width: 84px;
            text-align: center;
            border-radius: 999px;
            padding: 0.28rem 0.55rem;
            font-size: 0.78rem;
            font-weight: 700;
            margin-top: 1px;
        }
        .check-pill-ok {
            background: #dcfce7;
            color: #166534;
        }
        .check-pill-pending {
            background: #fef3c7;
            color: #92400e;
        }
        .alert-hero-top {
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.76rem;
            opacity: 0.8;
            margin-bottom: 0.55rem;
        }
        .alert-hero-title {
            font-size: 1.9rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }
        .alert-hero-subtitle {
            opacity: 0.92;
            font-size: 1rem;
        }
        .alert-tag-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.95rem;
        }
        .alert-tag {
            display: inline-block;
            padding: 0.35rem 0.72rem;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.12);
            border: 1px solid rgba(255, 255, 255, 0.16);
            color: #f8fafc;
            font-size: 0.84rem;
        }
        .alert-metric-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(140px, 1fr));
            gap: 12px;
            margin-bottom: 1rem;
        }
        .alert-metric-label {
            color: var(--app-muted);
            font-size: 0.76rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .alert-metric-value {
            color: var(--text-color);
            font-size: 1.8rem;
            font-weight: 700;
            margin-top: 0.35rem;
        }
        .alert-list {
            margin: 0;
            padding-left: 1.1rem;
            color: inherit;
        }
        .alert-list li {
            margin-bottom: 0.35rem;
        }
        .alert-tag-risk-low {
            background: rgba(38, 166, 154, 0.18);
            border-color: rgba(38, 166, 154, 0.55);
        }
        .alert-tag-risk-medium {
            background: rgba(245, 158, 11, 0.16);
            border-color: rgba(245, 158, 11, 0.55);
        }
        .alert-tag-risk-high {
            background: rgba(239, 83, 80, 0.18);
            border-color: rgba(239, 83, 80, 0.55);
        }
        .op-shell {
            background: var(--app-surface-strong);
            border: 1px solid var(--app-border);
            border-radius: 14px;
            padding: 20px 24px;
            color: var(--app-text);
            margin-bottom: 1rem;
            box-shadow: var(--app-shadow);
        }
        .op-title {
            color: var(--app-card-title);
            font-size: 1.7rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }
        .op-subtitle {
            color: var(--app-muted);
            font-size: 0.95rem;
        }
        .op-top-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 0.85rem;
        }
        .op-tag {
            display: inline-block;
            padding: 0.3rem 0.7rem;
            border-radius: 999px;
            background: var(--app-surface);
            border: 1px solid var(--app-border);
            color: var(--app-text);
            font-size: 0.82rem;
        }
        .op-flow-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(110px, 1fr));
            gap: 10px;
            align-items: start;
            margin-top: 0.8rem;
            margin-bottom: 1rem;
        }
        .op-step {
            text-align: center;
            color: var(--app-text);
        }
        .op-step-circle {
            width: 52px;
            height: 52px;
            border-radius: 999px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 0.6rem;
            font-size: 1.4rem;
            font-weight: 700;
            border: 1px solid var(--app-border);
            background: var(--app-surface);
            color: var(--app-muted);
        }
        .op-step-circle.completed {
            background: var(--sr-accent);
            border-color: var(--sr-accent);
            color: #FFFFFF;
            border-radius: 8px;
        }
        .op-step-circle.current {
            background: #3182CE;
            border-color: #3182CE;
            color: #FFFFFF;
            border-radius: 8px;
        }
        .op-step-circle.pending {
            background: var(--app-surface);
            border-color: var(--app-border);
            color: var(--app-muted);
            border-radius: 8px;
        }
        .op-step-label {
            font-size: 0.88rem;
            font-weight: 600;
            line-height: 1.2;
            color: var(--app-card-title);
        }
        .op-step-sub {
            font-size: 0.75rem;
            color: var(--app-muted);
            margin-top: 0.2rem;
        }
        .op-summary-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(150px, 1fr));
            gap: 10px;
            margin-bottom: 1rem;
        }
        .op-summary-card {
            background: var(--app-surface);
            border: 1px solid var(--app-border);
            border-radius: 10px;
            padding: 14px 16px;
        }
        .op-summary-label {
            color: var(--app-muted);
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.09em;
        }
        .op-summary-value {
            color: var(--app-card-title);
            font-size: 1.8rem;
            font-weight: 700;
            margin-top: 0.35rem;
        }
        .op-summary-warn {
            color: #BA7517;
        }
        .op-banner {
            display: flex;
            justify-content: space-between;
            gap: 18px;
            align-items: center;
            background: var(--app-banner-bg);
            border: 1px solid var(--app-banner-border);
            border-left: 3px solid #F59E0B;
            border-radius: 10px;
            padding: 14px 18px;
            margin: 1rem 0;
            color: var(--app-banner-text);
        }
        .op-banner-title {
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 0.1rem;
        }
        .op-banner-sub {
            font-size: 0.9rem;
        }
        .op-footer {
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: center;
            margin-top: 1.2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--app-border);
            color: var(--app-muted);
            font-size: 0.88rem;
        }
        .op-footer strong {
            color: var(--app-card-title);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_brand() -> None:
    if LOGO_PATH.exists():
        st.sidebar.image(str(LOGO_PATH), width="stretch")
    st.sidebar.title("PLATAFORMA")


def render_sidebar_pilot_controls(companies: list[dict]) -> str:
    st.sidebar.markdown("### Piloto local")

    owner_options = get_owner_filter_options(companies)
    token_to_label = {token: label for token, label in owner_options}
    label_to_token = {label: token for token, label in owner_options}
    saved_filter = get_saved_owner_filter(companies)
    saved_label = token_to_label.get(saved_filter, token_to_label[FILTER_ALL])
    labels = list(label_to_token.keys())

    selected_label = st.sidebar.selectbox(
        "Cartera visible",
        options=labels,
        index=labels.index(saved_label),
        key="sidebar_owner_filter",
    )
    selected_filter = label_to_token[selected_label]
    if selected_filter != saved_filter:
        save_owner_filter_preference(selected_filter)
        if selected_filter != FILTER_ALL:
            st.session_state["selected_rfc"] = None
        st.rerun()

    flash_message = st.session_state.pop("pilot_sidebar_flash", None)
    if flash_message:
        st.sidebar.success(flash_message)

    input_key = "sidebar_boveda_dir_input"
    current_boveda = str(settings.boveda_dir)
    if input_key not in st.session_state:
        st.session_state[input_key] = current_boveda

    with st.sidebar.expander("Configuracion avanzada", expanded=False):
        st.text_input(
            "Boveda XML compartida",
            key=input_key,
            help="Ruta base de la boveda. La app usa las subcarpetas zip y extract.",
        )

        save_col, reset_col = st.columns(2)
        with save_col:
            if st.button("Guardar ruta", key="save-boveda-dir", width="stretch"):
                try:
                    base_dir = save_boveda_root_preference(st.session_state.get(input_key, ""))
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.session_state[input_key] = str(base_dir)
                    st.session_state["pilot_sidebar_flash"] = f"Ruta guardada: {base_dir}"
                    st.rerun()
        with reset_col:
            if st.button("Usar local", key="reset-boveda-dir", width="stretch"):
                base_dir = clear_boveda_root_preference()
                st.session_state[input_key] = str(base_dir)
                st.session_state["pilot_sidebar_flash"] = f"Ruta local activa: {base_dir}"
                st.rerun()

        st.caption(f"Ruta activa: {settings.boveda_dir}")
    return selected_filter


def render_sidebar_company_browser(companies: list[dict], selected_rfc: str | None, total_company_count: int) -> None:
    st.sidebar.markdown("### Empresas")
    active_label = "Sin empresa activa"
    active_rfc = "Selecciona una empresa desde el directorio o desde el selector."
    if selected_rfc:
        company = next((item for item in companies if item.get("rfc") == selected_rfc), None)
        if company:
            active_label = str(
                company.get("nombre")
                or company.get("nombre_corto")
                or company.get("razon_social")
                or selected_rfc
            )
            active_rfc = selected_rfc
    st.sidebar.markdown(
        f"""
        <div class="sidebar-company-active">
            <div class="sidebar-company-active-label">Empresa activa</div>
            <div class="sidebar-company-active-name">{active_label}</div>
            <div class="sidebar-company-active-rfc">{active_rfc}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not companies:
        st.sidebar.info("No hay empresas visibles con el filtro actual. Ajusta la cartera o asigna dueños de cuenta en el Directorio del Despacho.")
        return

    options: list[str] = []
    label_to_rfc: dict[str, str] = {}
    current_label: str | None = None

    for company in companies:
        option, rfc = format_company_option(company)
        options.append(option)
        label_to_rfc[option] = rfc
        if rfc == selected_rfc:
            current_label = option

    search_key = "sidebar_company_search"
    if st.session_state.get(search_key) not in options:
        st.session_state.pop(search_key, None)

    selected_label = st.sidebar.selectbox(
        "Buscar y abrir empresa",
        options=options,
        index=(options.index(current_label) if current_label in options else None),
        placeholder="RFC, nombre corto o razon social",
        key=search_key,
    )

    chosen_rfc = label_to_rfc.get(selected_label) if selected_label else None
    if chosen_rfc and chosen_rfc != selected_rfc:
        st.session_state["selected_rfc"] = chosen_rfc
        st.session_state["pending_section"] = "Resumen Ejecutivo"
        st.rerun()


def format_company_option(company: dict) -> tuple[str, str]:
    label = str(
        company.get("nombre")
        or company.get("nombre_corto")
        or company.get("razon_social")
        or company.get("rfc")
    )
    rfc = str(company.get("rfc") or "").upper()
    return f"{label} ({rfc})", rfc


def get_company_display_name(selected_rfc: str | None) -> str:
    if not selected_rfc:
        return "Sin empresa seleccionada"
    for item in get_company_options():
        if item.get("rfc") == selected_rfc:
            return item.get("nombre") or item.get("nombre_corto") or selected_rfc
    return selected_rfc


def render_module_header(
    module_label: str,
    title: str,
    subtitle: str,
    tags: list[str] | None = None,
    show_logo: bool = False,
) -> None:
    tag_html = ""
    if tags:
        tag_html = '<div class="module-header-tags">' + "".join(
            f'<span class="module-header-tag">{tag}</span>' for tag in tags if tag
        ) + "</div>"
    st.markdown(
        f"""
        <div class="module-header">
            <div class="module-header-top">{module_label}</div>
            <div class="module-header-main">
                <div class="module-header-copy">
                    <div class="module-header-title">{title}</div>
                    <div class="module-header-subtitle">{subtitle}</div>
                </div>
            </div>
            {tag_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_operations(selected_rfc: str | None, selected_period: str) -> None:
    year, month = parse_period(selected_period)
    status = get_operational_status(selected_rfc, selected_period)
    generated_files = discover_generated_files(selected_rfc, selected_period) if selected_rfc else {}
    history = get_recent_execution_log()
    steps = build_operation_steps(status, selected_rfc, selected_period, history)
    operation_key = f"operations-result-{selected_rfc}-{selected_period}"
    detail_key = f"operations-detail-{selected_rfc}-{selected_period}"
    company_name = get_company_display_name(selected_rfc)

    render_module_header(
        module_label="Flujo operativo",
        title=company_name,
        subtitle="Transforma ZIPs y XML en Excel, analitica, informe y alertas del despacho.",
        tags=[
            f"RFC: {selected_rfc or 'N/A'}",
            f"Periodo: {selected_period}",
            f"{count_completed_steps(steps)} de {count_core_steps(steps)} pasos completados",
        ],
        show_logo=True,
    )

    top_action_left, top_action_mid, top_action_right = st.columns([1.6, 0.7, 0.7])
    with top_action_left:
        st.markdown("**Flujo de procesamiento**")
    with top_action_mid:
        if st.button("Ver entregables", key=f"top-artifacts-{selected_period}", width="stretch"):
            st.session_state[detail_key] = "artifacts"
            st.rerun()
    with top_action_right:
        if st.button("Ejecutar todo", key=f"top-run-all-{selected_period}", width="stretch", disabled=not bool(selected_rfc)):
            with st.spinner("Ejecutando flujo completo..."):
                st.session_state[operation_key] = run_full_processing_flow(selected_rfc, selected_period, year, month, steps)
            st.rerun()

    render_operation_pipeline(steps)
    render_operation_summary_cards(status)
    render_operation_blocker_banner(steps, selected_rfc, selected_period, year, month, operation_key)

    last_result = st.session_state.get(operation_key)
    if last_result:
        show_action_result(last_result)

    st.markdown("**Acciones por etapa**")
    render_operation_step_cards(
        steps=steps,
        selected_rfc=selected_rfc,
        selected_period=selected_period,
        year=year,
        month=month,
        generated_files=generated_files,
        history=history,
        operation_key=operation_key,
        detail_key=detail_key,
    )

    render_operation_detail_panel(
        detail_key=detail_key,
        status=status,
        generated_files=generated_files,
        history=history,
        steps=steps,
        selected_rfc=selected_rfc,
        selected_period=selected_period,
    )

    footer_cols = st.columns([1.2, 1, 1, 1])
    with footer_cols[0]:
        render_operation_footer(history, steps)
    with footer_cols[1]:
        if st.button("Ver historial", key=f"footer-history-{selected_period}", width="stretch"):
            st.session_state[detail_key] = "history"
            st.rerun()
    with footer_cols[2]:
        if st.button("Exportar log", key=f"footer-export-log-{selected_period}", width="stretch"):
            st.session_state[detail_key] = "history"
            st.rerun()
    with footer_cols[3]:
        if st.button("Ejecutar todo", key=f"footer-run-all-{selected_period}", width="stretch", disabled=not bool(selected_rfc)):
            with st.spinner("Ejecutando flujo completo..."):
                st.session_state[operation_key] = run_full_processing_flow(selected_rfc, selected_period, year, month, steps)
            st.rerun()


def render_dashboard(selected_rfc: str | None, selected_period: str) -> None:
    if not selected_rfc:
        st.info("Selecciona una empresa para visualizar el dashboard.")
        return

    company_name = get_company_display_name(selected_rfc)
    years = get_year_options(selected_rfc)
    parsed_year, parsed_month = parse_period(selected_period)
    default_year = parsed_year if parsed_year in years else (years[0] if years else parsed_year)
    mode_key = f"dashboard-mode-{selected_rfc}"
    year_key = f"dashboard-year-{selected_rfc}"
    month_key = f"dashboard-month-{selected_rfc}"

    current_mode = st.session_state.get(mode_key, "monthly")
    if current_mode not in {"monthly", "ytd", "year"}:
        current_mode = "monthly"
        st.session_state[mode_key] = current_mode

    current_year = st.session_state.get(year_key, default_year)
    if current_year not in (years or [parsed_year]):
        current_year = default_year
        st.session_state[year_key] = current_year

    preview_month_options = get_month_options_for_year(selected_rfc, current_year)
    default_month = parsed_month if parsed_month in preview_month_options else (preview_month_options[-1] if preview_month_options else parsed_month)
    current_month = st.session_state.get(month_key, default_month)
    if preview_month_options and current_month not in preview_month_options:
        current_month = default_month
        st.session_state[month_key] = current_month

    render_module_header(
        module_label="Tablero analitico",
        title=company_name,
        subtitle="Explora tendencias y variaciones para el periodo seleccionado.",
        tags=[
            f"RFC: {selected_rfc}",
            f"Periodo base: {selected_period}",
        ],
        show_logo=True,
    )

    col1, col2, col3 = st.columns([1, 1, 1.1])
    with col1:
        analysis_mode = st.selectbox(
            "Modo de análisis",
            options=["monthly", "ytd", "year"],
            format_func=lambda value: {"monthly": "Mensual", "ytd": "Acumulado del año", "year": "Anual"}[value],
            key=mode_key,
        )
    with col2:
        selected_year = st.selectbox(
            "Año",
            options=years or [parsed_year],
            index=((years or [parsed_year]).index(current_year) if current_year in (years or [parsed_year]) else 0),
            key=year_key,
        )
    with col3:
        month_options = get_month_options_for_year(selected_rfc, selected_year)
        default_month = parsed_month if parsed_month in month_options else (month_options[-1] if month_options else parsed_month)
        if analysis_mode == "monthly":
            selected_month = st.selectbox(
                "Mes",
                options=month_options or list(range(1, 13)),
                index=((month_options or list(range(1, 13))).index(current_month) if current_month in (month_options or list(range(1, 13))) else 0),
                format_func=lambda value: f"{value:02d}",
                key=month_key,
            )
        elif analysis_mode == "ytd":
            ytd_months = get_month_options_for_year(selected_rfc, selected_year)
            selected_month = st.selectbox(
                "Mes corte",
                options=ytd_months or list(range(1, 13)),
                index=((ytd_months or list(range(1, 13))).index(current_month) if current_month in (ytd_months or list(range(1, 13))) else (len(ytd_months) - 1 if ytd_months else parsed_month - 1)),
                format_func=lambda value: f"{value:02d}",
                key=month_key,
            )
        else:
            selected_month = None
            st.write("")
            st.caption("El análisis anual toma todo lo disponible del año seleccionado.")

    effective_period = f"{selected_year:04d}-{selected_month:02d}" if selected_month else f"{selected_year:04d}-12"
    st.session_state["selected_period"] = effective_period

    try:
        dataset = get_dashboard_context(
            effective_period,
            selected_rfc,
            analysis_mode=analysis_mode,
            year=selected_year,
            month_cutoff=selected_month,
        )
    except Exception as exc:
        with st.container(border=True):
            st.info(
                f"No hay datos del tablero para {selected_rfc} en {effective_period}. "
                f"Procesa primero los XML y la capa analitica para habilitar esta vista. Detalle: {exc}"
            )
            action_col1, action_col2 = st.columns(2)
            with action_col1:
                if st.button("Ir a Operacion", key=f"dashboard-empty-ops-{selected_rfc}-{effective_period}", width="stretch"):
                    st.session_state["pending_section"] = "Operación"
                    st.rerun()
            with action_col2:
                if st.button("Ir a Resumen Ejecutivo", key=f"dashboard-empty-home-{selected_rfc}-{effective_period}", width="stretch"):
                    st.session_state["pending_section"] = "Resumen Ejecutivo"
                    st.rerun()
        return
    render_executive_dashboard_body(dataset)


def render_reports(selected_rfc: str | None, selected_period: str) -> None:
    if not selected_rfc:
        st.info("Selecciona una empresa para generar su informe.")
        return
    company_name = get_company_display_name(selected_rfc)
    render_module_header(
        module_label="Informes ejecutivos",
        title=company_name,
        subtitle="Genera archivos listos para el despacho y para compartir con clientes.",
        tags=[
            f"RFC: {selected_rfc}",
            f"Periodo: {selected_period}",
        ],
        show_logo=True,
    )
    report_state_key = f"report-{selected_rfc}-{selected_period}"
    if st.button("Generar / actualizar reporte del periodo", width="stretch"):
        with st.spinner("Generando informe ejecutivo..."):
            st.session_state[report_state_key] = generate_client_report(selected_period, selected_rfc)

    result = st.session_state.get(report_state_key)
    if not result:
        st.info("Genera el informe para ver la vista previa y habilitar descargas.")
        existing = discover_generated_files(selected_rfc, selected_period)
        if existing["report_files"]:
            st.write("Informes ya detectados en disco:")
            for path in existing["report_files"]:
                st.write(f"- `{path}`")
        return

    if not result.success:
        show_action_result(result)
        return

    html_content = result.details["html"]
    text_content = result.details["text"]

    col1, col2 = st.columns([1.3, 1])
    with col1:
        st.markdown("### Vista previa")
        components.html(html_content, height=900, scrolling=True)
    with col2:
        st.markdown("### Descargas")
        st.write(f"Asunto: `{result.details['subject']}`")
        st.download_button("Descargar reporte HTML", data=html_content, file_name=f"{selected_rfc}_{selected_period}_reporte.html", mime="text/html", width="stretch")
        st.download_button("Descargar resumen TXT", data=text_content, file_name=f"{selected_rfc}_{selected_period}_resumen.txt", mime="text/plain", width="stretch")
        st.success(f"Reporte guardado en {result.details['output_html']}")


def render_alerts_module(selected_rfc: str | None, selected_period: str) -> None:
    if not selected_rfc:
        st.info("Selecciona una empresa para previsualizar sus alertas.")
        return

    mail_status = get_mail_configuration_status()
    try:
        payload = preview_company_alert_email(selected_period, selected_rfc)
    except Exception as exc:
        st.info(
            f"No se pudo construir el correo de alertas para {selected_rfc} en {selected_period}. "
            f"Verifica que existan los Excel del periodo y la configuracion del motor. Detalle: {exc}"
        )
        return

    empresa = payload["empresa"]
    summary = payload["summary"]
    alerts = payload["alerts"]
    hero_subtitle = (
        "Correo listo para prueba interna del despacho."
        if int(summary.get("alert_total") or 0) > 0
        else "Sin alertas relevantes; correo listo para resumen mensual."
    )

    st.markdown(
        f"""
        <div class="alert-hero">
            <div class="alert-hero-top">Centro de alertas por empresa</div>
            <div class="alert-hero-title">{empresa['nombre']}</div>
            <div class="alert-hero-subtitle">{hero_subtitle}</div>
            <div class="alert-tag-row">
                <span class="alert-tag">RFC: {empresa['rfc']}</span>
                <span class="alert-tag">Periodo: {selected_period}</span>
                <span class="alert-tag">Destino actual: Director</span>
                <span class="alert-tag">Destinatarios: {mail_status['recipient_count']}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="alert-metric-grid">
            <div class="alert-metric-card"><div class="alert-metric-label">Correo configurado</div><div class="alert-metric-value">{"Si" if mail_status["sender"] else "No"}</div></div>
            <div class="alert-metric-card"><div class="alert-metric-label">Password cargado</div><div class="alert-metric-value">{"Si" if mail_status["has_password"] else "No"}</div></div>
            <div class="alert-metric-card"><div class="alert-metric-label">Ingresos</div><div class="alert-metric-value">${float(summary.get("ingresos_mxn") or 0):,.0f}</div></div>
            <div class="alert-metric-card"><div class="alert-metric-label">Egresos</div><div class="alert-metric-value">${float(summary.get("egresos_mxn") or 0):,.0f}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    top_left, top_right = st.columns([1.1, 1])
    with top_left:
        st.markdown('<div class="panel-card">', unsafe_allow_html=True)
        st.markdown("### Resumen listo para enviar")
        st.write(f"Asunto: `{payload['subject']}`")
        if mail_status["sender"]:
            st.write(f"Remitente configurado: `{mail_status['sender']}`")
        st.write("Destino temporal: `Correo del director`")
        st.write(f"CFDI emitidos: `{int(summary.get('num_cfdi_emitidos') or 0)}`")
        st.write(f"CFDI recibidos: `{int(summary.get('num_cfdi_recibidos') or 0)}`")
        st.markdown("**Alertas detectadas**")
        if alerts:
            st.markdown(
                "<ul class='alert-list'>"
                + "".join(
                    f"<li><strong>{row['severity']}</strong> - {row['type']}: {row['summary']}</li>"
                    for row in alerts[:4]
                )
                + "</ul>",
                unsafe_allow_html=True,
            )
        else:
            st.info("No se detectaron alertas relevantes para este periodo.")
        st.markdown("</div>", unsafe_allow_html=True)

    with top_right:
        st.markdown('<div class="panel-card">', unsafe_allow_html=True)
        st.markdown("### Acciones")
        if payload.get("pdf_bytes"):
            st.download_button(
                "Descargar PDF",
                data=payload["pdf_bytes"],
                file_name=f"{selected_rfc}_{selected_period}_alerta.pdf",
                mime="application/pdf",
                width="stretch",
            )
        elif payload.get("pdf_error"):
            st.warning(f"No se pudo generar el PDF: {payload['pdf_error']}")
        if st.button("Enviar correo", width="stretch", key=f"alert-company-send-{selected_rfc}-{selected_period}", disabled=not mail_status["configured"]):
            with st.spinner("Enviando correo..."):
                show_action_result(run_company_alert(selected_period, selected_rfc, piloto=False))
        if st.button("Reenviar", width="stretch", key=f"alert-company-force-{selected_rfc}-{selected_period}", disabled=not mail_status["configured"]):
            with st.spinner("Reenviando correo..."):
                show_action_result(run_company_alert(selected_period, selected_rfc, piloto=False, forzar=True))
        st.markdown("</div>", unsafe_allow_html=True)

    if not mail_status["configured"]:
        st.warning("Falta completar el correo del despacho en `alertas/.env`. La app no muestra secretos, solo el estado.")
    else:
        st.info("Durante este mes de pruebas, todos los envios de este modulo se redirigen al correo del director.")

    st.markdown("### Vista previa del correo")
    components.html(payload["html"], height=700, scrolling=True)

    tab_resumen, tab_texto, tab_html = st.tabs(["Resumen de alertas", "Texto del correo", "Vista HTML"])

    with tab_resumen:
        res_left, res_right = st.columns([1, 1])
        with res_left:
            st.markdown("### Totales del correo")
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Alertas", int(summary.get("alert_total") or 0))
            kpi2.metric("Alta", int(summary.get("alta") or 0))
            kpi3.metric("Media", int(summary.get("media") or 0))
            kpi4.metric("Baja", int(summary.get("baja") or 0))
        with res_right:
            st.markdown("### Base del periodo")
            st.info(
                f"Ingresos: ${float(summary.get('ingresos_mxn') or 0):,.2f} | "
                f"Egresos: ${float(summary.get('egresos_mxn') or 0):,.2f}"
            )

        list_left, list_right = st.columns(2)
        with list_left:
            st.markdown("### Estado de CFDI")
            st.write(f"- Emitidos tipo I: {int(summary.get('num_cfdi_emitidos') or 0)}")
            st.write(f"- Recibidos tipo I: {int(summary.get('num_cfdi_recibidos') or 0)}")
            st.write(f"- Excel emitidas detectado: {'Si' if summary.get('tiene_emitidas') else 'No'}")
            st.write(f"- Excel recibidas detectado: {'Si' if summary.get('tiene_recibidas') else 'No'}")
        with list_right:
            st.markdown("### Alertas incluidas")
            if alerts:
                for row in alerts[:6]:
                    amount_suffix = f" | ${float(row['amount']):,.0f}" if float(row.get("amount") or 0) else ""
                    st.write(f"- [{row['severity']}] {row['type']}: {row['summary']}{amount_suffix}")
            else:
                st.info("No hay alertas relevantes para este periodo.")

    with tab_texto:
        st.markdown("### Texto del correo")
        st.code(payload["text"], language="text")

    with tab_html:
        st.markdown("### Vista HTML del correo")
        components.html(payload["html"], height=760, scrolling=True)


def render_power_bi(selected_period: str) -> None:
    render_module_header(
        module_label="Exportacion BI",
        title="Datasets para Power BI",
        subtitle="Prepara tablas limpias para cargar en Power BI Desktop o compartir con direccion.",
        tags=[
            f"Periodo: {selected_period}",
            "CSV listos para conectar",
        ],
        show_logo=True,
    )
    st.write("Datasets incluidos:")
    st.write("- `dim_empresas`")
    st.write("- `dim_periodos`")
    st.write("- `fact_kpis_mensuales_empresa`")
    st.write("- `fact_variaciones_mensuales`")
    st.write("- `fact_contrapartes_mensuales`")
    st.write("- `fact_riesgo_mensual`")
    if st.button("Exportar datasets BI del periodo", width="stretch"):
        with st.spinner("Generando CSVs para BI..."):
            show_action_result(export_bi_for_period(selected_period))
    st.info("Tip: en Power BI relaciona `dim_empresas[rfc]` con `fact_*[rfc_empresa]` y `dim_periodos[periodo]` con `fact_*[periodo]`.")


def parse_period(periodo: str) -> tuple[int, int]:
    try:
        year_str, month_str = periodo.split("-")
        return int(year_str), int(month_str)
    except Exception:
        today = datetime.now()
        return today.year, today.month


def normalize_period_input(periodo: str | None) -> str | None:
    raw_value = str(periodo or "").strip()
    if not raw_value:
        return None

    compact_value = raw_value.replace("/", "-").replace("\\", "-").replace(".", "-").replace("_", "-")
    if compact_value.isdigit() and len(compact_value) == 6:
        compact_value = f"{compact_value[:4]}-{compact_value[4:]}"

    try:
        year_str, month_str = compact_value.split("-")
        year = int(year_str)
        month = int(month_str)
    except Exception:
        return None

    if year < 2000 or year > 2100 or month < 1 or month > 12:
        return None
    return f"{year:04d}-{month:02d}"


def format_period(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def get_manual_year_bounds(periods: list[str] | None = None) -> tuple[int, int]:
    current_year = datetime.now().year
    detected_years = [int(period[:4]) for period in (periods or []) if len(period) >= 7 and period[:4].isdigit()]
    minimum_year = min(detected_years) if detected_years else current_year - 5
    minimum_year = min(minimum_year, current_year)
    return minimum_year, current_year


def clamp_period_to_manual_bounds(periodo: str, periods: list[str] | None = None) -> str:
    normalized_period = normalize_period_input(periodo) or default_period()
    year, month = parse_period(normalized_period)
    minimum_year, maximum_year = get_manual_year_bounds(periods)
    clamped_year = min(max(year, minimum_year), maximum_year)
    if clamped_year != year and clamped_year == maximum_year:
        return format_period(clamped_year, datetime.now().month)
    return format_period(clamped_year, month)


def sync_manual_period_widgets(selected_rfc: str | None, active_period: str, periods: list[str] | None = None) -> tuple[str, str]:
    year_key = f"selected_period_year_widget_{selected_rfc or 'none'}"
    month_key = f"selected_period_month_widget_{selected_rfc or 'none'}"
    sync_key = f"selected_period_manual_sync_{selected_rfc or 'none'}"
    minimum_year, maximum_year = get_manual_year_bounds(periods)
    active_year, active_month = parse_period(clamp_period_to_manual_bounds(active_period, periods))
    periods = periods or []

    if st.session_state.get(sync_key) != active_period:
        st.session_state[year_key] = active_year
        st.session_state[month_key] = active_month
        st.session_state[sync_key] = active_period

    selected_year = st.session_state.get(year_key, active_year)
    if selected_year < minimum_year or selected_year > maximum_year:
        selected_year = active_year
        st.session_state[year_key] = active_year

    selected_month = st.session_state.get(month_key, active_month)
    if selected_month not in range(1, 13):
        selected_month = active_month
        st.session_state[month_key] = active_month

    return year_key, month_key


def render_manual_period_picker(selected_rfc: str | None, period_default: str) -> str:
    active_period = clamp_period_to_manual_bounds(
        normalize_period_input(st.session_state.get("selected_period")) or period_default
    )
    year_key, month_key = sync_manual_period_widgets(selected_rfc, active_period)
    minimum_year, maximum_year = get_manual_year_bounds()

    with st.sidebar.container(border=True):
        st.markdown("**Periodo de trabajo**")
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

        selected_period = format_period(int(selected_year), int(selected_month))
        st.caption("Sin periodos detectados todavia. Usa este selector manual mientras procesamos la primera corrida.")
        st.caption(f"Periodo activo: {selected_period}")

    st.session_state["selected_period"] = selected_period
    st.session_state[f"selected_period_manual_sync_{selected_rfc or 'none'}"] = selected_period
    return selected_period


def get_month_options_for_year(rfc_empresa: str, year: int) -> list[int]:
    periods = get_period_options(rfc_empresa)
    months = sorted({int(period[5:7]) for period in periods if period.startswith(f"{year:04d}-")})
    return months


def show_action_result(result) -> None:
    if result.success:
        st.success(result.message)
    else:
        st.error(result.message)
    if result.artifacts:
        st.write("Artefactos:")
        for artifact in result.artifacts:
            st.write(f"- `{artifact}`")
    if result.details:
        st.json(result.details)


def build_operation_steps(status: dict, selected_rfc: str | None, selected_period: str, history: list[dict]) -> list[dict]:
    summary = status["summary"]
    checks = {item["label"]: item["ok"] for item in status["checks"]}
    report_ready = summary.get("report_count", 0) > 0
    alert_ready = any(
        entry.get("periodo") == selected_period and str(entry.get("action", "")).startswith("alertas")
        for entry in history
    )

    steps = [
        {
            "key": "step1",
            "number": 1,
            "core": True,
            "header": "Paso 1 - Preparar XML",
            "title": "Preparar XML",
            "subtitle": "Descomprime y organiza XML del periodo",
            "completed": summary.get("organized_count", 0) > 0,
            "ready": summary.get("zip_files", 0) > 0 or summary.get("extract_count", 0) > 0,
            "metric": f"{summary.get('extract_count', 0)} extraidos / {summary.get('organized_count', 0)} organizados",
            "primary_label": "Preparar XML",
            "secondary_label": "Diagnostico",
            "detail": "Ejecuta descompresion, correccion y organizacion para dejar listos los XML del RFC y periodo.",
        },
        {
            "key": "step2",
            "number": 2,
            "core": True,
            "header": "Paso 2 - Generar Excel SAT",
            "title": "Generar Excel SAT",
            "subtitle": "Excels emitidas y recibidas del periodo",
            "completed": summary.get("excel_count", 0) > 0,
            "ready": summary.get("organized_count", 0) > 0 and bool(selected_rfc),
            "metric": f"{summary.get('excel_count', 0)} Excel(s) generados" if summary.get("excel_count", 0) > 0 else "Pendiente de generar",
            "primary_label": "Generar Excel",
            "secondary_label": "Ver archivos",
            "detail": "Construye los Excels base del cliente usando los XML ya organizados.",
        },
        {
            "key": "step3",
            "number": 3,
            "core": True,
            "header": "Paso 3 - Construir analitica",
            "title": "Construir analitica",
            "subtitle": "Actualiza indicadores y tablas",
            "completed": checks.get("Analytics construidos", False),
            "ready": summary.get("excel_count", 0) > 0,
            "metric": "Analytics disponibles" if checks.get("Analytics construidos", False) else "Pendiente de construir",
            "primary_label": "Construir analitica",
            "secondary_label": "Ver estado",
            "detail": "Prepara la capa que usan tablero, informes y alertas.",
        },
        {
            "key": "step4",
            "number": 4,
            "core": True,
            "header": "Paso 4 - Tablero y alertas",
            "title": "Tablero + alertas",
            "subtitle": "Informe ejecutivo y alertas piloto",
            "completed": report_ready or alert_ready,
            "ready": checks.get("Analytics construidos", False) and bool(selected_rfc),
            "metric": "Informe o alerta listos" if (report_ready or alert_ready) else "Pendiente de preparar salida",
            "primary_label": "Generar informe",
            "secondary_label": "Alertas piloto",
            "detail": "Deja lista la salida ejecutiva para revisar o enviar al cliente.",
        },
        {
            "key": "step5",
            "number": 5,
            "core": False,
            "header": "Extra - Cargar BD operativa",
            "title": "Cargar BD operativa",
            "subtitle": "Carga XML a la SQLite local",
            "completed": checks.get("Base operativa CFDI", False),
            "ready": summary.get("organized_count", 0) > 0,
            "metric": "Base CFDI lista" if checks.get("Base operativa CFDI", False) else "Extra opcional para consulta local",
            "primary_label": "Cargar BD",
            "secondary_label": "Ver log",
            "detail": "Accion extra para dejar una base operativa local de XML.",
        },
        {
            "key": "step6",
            "number": 6,
            "core": False,
            "header": "Extra - Resumen Word",
            "title": "Resumen Word",
            "subtitle": "Documento resumen del periodo",
            "completed": summary.get("word_count", 0) > 0,
            "ready": summary.get("excel_count", 0) > 0 and bool(selected_rfc),
            "metric": f"{summary.get('word_count', 0)} Word generado(s)" if summary.get("word_count", 0) > 0 else "Extra opcional",
            "primary_label": "Generar Word",
            "secondary_label": "Ver archivos",
            "detail": "Genera el resumen Word a partir de los Excels ya creados.",
        },
    ]

    first_open_index = next(
        (index for index, item in enumerate(steps) if item.get("core", True) and not item["completed"]),
        None,
    )
    for index, item in enumerate(steps):
        if item["completed"]:
            item["state"] = "completed"
        elif item.get("core", True) and first_open_index is not None and index == first_open_index and item["ready"]:
            item["state"] = "current"
        else:
            item["state"] = "pending"
        item["disabled"] = not item["ready"] and not item["completed"]
    return steps


def count_completed_steps(steps: list[dict]) -> int:
    return sum(1 for step in steps if step.get("core", True) and step["completed"])


def count_core_steps(steps: list[dict]) -> int:
    return sum(1 for step in steps if step.get("core", True))


def render_operation_pipeline(steps: list[dict]) -> None:
    nodes = []
    for step in (item for item in steps if item.get("core", True)):
        circle_class = f"op-step-circle {step['state']}"
        nodes.append(
            f'<div class="op-step">'
            f'<div class="{circle_class}">{step["number"]}</div>'
            f'<div class="op-step-label">{step["title"]}</div>'
            f'<div class="op-step-sub">{step["subtitle"]}</div>'
            f"</div>"
        )
    st.markdown(f'<div class="op-flow-grid">{"".join(nodes)}</div>', unsafe_allow_html=True)


def render_operation_summary_cards(status: dict) -> None:
    summary = status["summary"]
    organized_class = "op-summary-value op-summary-warn" if summary.get("organized_count", 0) == 0 else "op-summary-value"
    st.markdown(
        f"""
        <div class="op-summary-grid">
            <div class="op-summary-card"><div class="op-summary-label">ZIPs</div><div class="op-summary-value">{summary.get('zip_files', 0)}</div></div>
            <div class="op-summary-card"><div class="op-summary-label">XML extraidos</div><div class="op-summary-value">{summary.get('extract_count', 0)}</div></div>
            <div class="op-summary-card"><div class="op-summary-label">XML organizados</div><div class="{organized_class}">{summary.get('organized_count', 0)}</div></div>
            <div class="op-summary-card"><div class="op-summary-label">Excels</div><div class="op-summary-value">{summary.get('excel_count', 0)}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_operation_blocker_banner(
    steps: list[dict],
    selected_rfc: str | None,
    selected_period: str,
    year: int,
    month: int,
    operation_key: str,
) -> None:
    blocker = next((step for step in steps if step.get("core", True) and not step["completed"]), None)
    if not blocker:
        st.success("Todo el flujo base ya esta listo para este RFC y periodo.")
        return

    banner_text = {
        "step1": "Todavia no estan listos los XML del periodo. Ejecuta la preparacion para descomprimir y organizar.",
        "step2": "Ya hay XML organizados. El siguiente paso clave es generar el Excel SAT del periodo.",
        "step3": "Los Excels ya existen, pero la analitica del periodo sigue pendiente.",
        "step4": "La analitica ya esta lista. Prepara informe y alertas para cerrar el flujo principal.",
    }.get(blocker["key"], "Hay un paso pendiente en el flujo operativo.")

    left, right = st.columns([1.5, 0.7])
    with left:
        banner_html = dedent(
            f"""
            <div class="op-banner">
                <div>
                    <div class="op-banner-title">Bloqueador actual</div>
                    <div class="op-banner-sub">{banner_text}</div>
                </div>
            </div>
            """
        ).strip()
        st.markdown(banner_html, unsafe_allow_html=True)
    with right:
        disabled = blocker["disabled"] or not bool(selected_rfc and selected_period)
        if st.button(blocker["primary_label"], key=f"banner-{blocker['key']}-{selected_period}", width="stretch", disabled=disabled):
            with st.spinner(f"Ejecutando {blocker['title']}..."):
                st.session_state[operation_key] = execute_operation_step(blocker["key"], selected_rfc, selected_period, year, month)
            st.rerun()


def render_operation_step_cards(
    steps: list[dict],
    selected_rfc: str | None,
    selected_period: str,
    year: int,
    month: int,
    generated_files: dict[str, list[Path]],
    history: list[dict],
    operation_key: str,
    detail_key: str,
) -> None:
    core_steps = [step for step in steps if step.get("core", True)]
    extra_steps = [step for step in steps if not step.get("core", True)]

    st.markdown("#### Flujo principal")
    for row_index, start in enumerate(range(0, len(core_steps), 2)):
        row = core_steps[start:start + 2]
        cols = st.columns(2)
        for col, step in zip(cols, row):
            with col:
                render_operation_step_card(
                    step=step,
                    selected_rfc=selected_rfc,
                    selected_period=selected_period,
                    year=year,
                    month=month,
                    operation_key=operation_key,
                    detail_key=detail_key,
                    row_index=row_index,
                )

    if extra_steps:
        st.markdown("#### Acciones extra")
        extra_cols = st.columns(len(extra_steps))
        for col, step in zip(extra_cols, extra_steps):
            with col:
                render_operation_step_card(
                    step=step,
                    selected_rfc=selected_rfc,
                    selected_period=selected_period,
                    year=year,
                    month=month,
                    operation_key=operation_key,
                    detail_key=detail_key,
                    row_index=99,
                )


def render_operation_step_card(
    step: dict,
    selected_rfc: str | None,
    selected_period: str,
    year: int,
    month: int,
    operation_key: str,
    detail_key: str,
    row_index: int,
) -> None:
    with st.container(border=True):
        st.markdown(f"### {step.get('header') or step['title']}")
        st.caption(step["subtitle"])
        st.write(step["detail"])
        status_label = {
            "completed": "OK",
            "current": "En curso",
            "pending": "Pendiente",
        }[step["state"]]
        status_tone = {
            "completed": "success",
            "current": "info",
            "pending": "warning",
        }[step["state"]]
        getattr(st, status_tone)(f"{status_label}: {step['metric']}")

        primary_disabled = step["disabled"] or (not bool(selected_rfc) and step["key"] != "step1")
        if st.button(
            step["primary_label"],
            key=f"primary-{step['key']}-{selected_period}-{row_index}",
            width="stretch",
            disabled=primary_disabled,
        ):
            with st.spinner(f"Ejecutando {step['title']}..."):
                st.session_state[operation_key] = execute_operation_step(step["key"], selected_rfc, selected_period, year, month)
            st.rerun()

        secondary_disabled = not bool(selected_rfc) and step["key"] != "step1"
        if st.button(
            step["secondary_label"],
            key=f"secondary-{step['key']}-{selected_period}-{row_index}",
            width="stretch",
            disabled=secondary_disabled,
        ):
            if step["key"] == "step4" and step["secondary_label"] == "Alertas piloto":
                with st.spinner("Ejecutando alertas piloto..."):
                    st.session_state[operation_key] = run_company_alert(selected_period, selected_rfc, piloto=True)
                st.rerun()
            else:
                st.session_state[detail_key] = step["key"]
                st.rerun()


def render_operation_detail_panel(
    detail_key: str,
    status: dict,
    generated_files: dict[str, list[Path]],
    history: list[dict],
    steps: list[dict],
    selected_rfc: str | None,
    selected_period: str,
) -> None:
    selected_detail = st.session_state.get(detail_key)
    if not selected_detail:
        return

    st.markdown("### Diagnostico y detalle")
    with st.container(border=True):
        if selected_detail == "artifacts":
            st.write("Entregables detectados para el RFC y periodo activos.")
            render_artifact_downloads(generated_files)
            return

        if selected_detail == "history":
            if history:
                st.dataframe(history, width="stretch", hide_index=True)
            else:
                st.info("Todavia no hay ejecuciones registradas desde la app.")
            return

        step = next((item for item in steps if item["key"] == selected_detail), None)
        if not step:
            st.info("No se encontro detalle para la etapa seleccionada.")
            return

        st.write(f"**Paso activo:** {step['title']}")
        st.write(step["detail"])
        st.write(f"**Estado actual:** {step['metric']}")

        if selected_detail == "step1":
            st.write(f"ZIPs detectados: `{status['summary'].get('zip_files', 0)}`")
            st.write(f"XML extraidos en el periodo: `{status['summary'].get('extract_count', 0)}`")
            st.write(f"XML organizados en el periodo: `{status['summary'].get('organized_count', 0)}`")
        elif selected_detail == "step2":
            st.write("Archivos Excel detectados:")
            render_artifact_downloads(
                {
                    "excel_files": generated_files.get("excel_files", []),
                    "word_files": [],
                    "report_files": [],
                    "bi_files": [],
                }
            )
        elif selected_detail == "step3":
            analytics_check = next((item for item in status["checks"] if item["label"] == "Analytics construidos"), None)
            if analytics_check:
                st.write(analytics_check["detail"])
            st.write(f"Periodo actual: `{selected_period}`")
        elif selected_detail == "step4":
            st.write("Informes y alertas relacionadas con el periodo activo.")
            st.write(f"Reportes detectados: `{status['summary'].get('report_count', 0)}`")
            filtered = [entry for entry in history if entry.get("periodo") == selected_period and str(entry.get("action", "")).startswith("alertas")][:5]
            if filtered:
                st.dataframe(filtered, width="stretch", hide_index=True)
            else:
                st.info("Aun no hay alertas ejecutadas para este periodo.")
        elif selected_detail == "step5":
            filtered = [entry for entry in history if entry.get("action") == "r7a"][:5]
            if filtered:
                st.dataframe(filtered, width="stretch", hide_index=True)
            else:
                st.info("No hay ejecuciones recientes de carga a BD.")
        elif selected_detail == "step6":
            st.write("Archivos Word detectados:")
            render_artifact_downloads(
                {
                    "word_files": generated_files.get("word_files", []),
                    "report_files": [],
                    "excel_files": [],
                    "bi_files": [],
                }
            )


def render_operation_footer(history: list[dict], steps: list[dict]) -> None:
    latest = history[0] if history else None
    latest_text = "Sin ejecuciones registradas"
    if latest:
        latest_text = f"{latest.get('timestamp', '')} - {latest.get('action', '')}"
    footer_html = dedent(
        f"""
        <div class="op-footer">
            <div><strong>{count_completed_steps(steps)} pasos completados de {count_core_steps(steps)}</strong></div>
            <div>Ultima ejecucion: {latest_text}</div>
        </div>
        """
    ).strip()
    st.markdown(footer_html, unsafe_allow_html=True)


def execute_operation_step(step_key: str, selected_rfc: str | None, selected_period: str, year: int, month: int) -> ActionResult:
    if step_key == "step1":
        return summarize_action_results(
            "Preparacion XML completada",
            [
                run_operational_step("r6"),
                run_operational_step("r6fix"),
                run_operational_step("r7"),
            ],
        )
    if step_key == "step2":
        return run_operational_step("r8", selected_rfc, year, month)
    if step_key == "step3":
        return build_analytics_for_period(selected_period)
    if step_key == "step4":
        return generate_client_report(selected_period, selected_rfc)
    if step_key == "step5":
        return run_operational_step("r7a")
    if step_key == "step6":
        return summarize_action_results(
            "Resumen Word generado",
            [
                run_operational_step("r9", selected_rfc, year, month),
            ],
        )
    return ActionResult(False, "Paso desconocido", f"No existe una accion configurada para {step_key}.")


def run_full_processing_flow(
    selected_rfc: str | None,
    selected_period: str,
    year: int,
    month: int,
    steps: list[dict],
) -> ActionResult:
    if not selected_rfc:
        return ActionResult(False, "Empresa requerida", "Selecciona una empresa antes de ejecutar todo el flujo.")

    results: list[ActionResult] = []
    step_map = {step["key"]: step for step in steps}
    if not step_map["step1"]["completed"]:
        results.extend([run_operational_step("r6"), run_operational_step("r6fix"), run_operational_step("r7")])
    if not step_map["step2"]["completed"]:
        results.append(run_operational_step("r8", selected_rfc, year, month))
    if not step_map["step3"]["completed"]:
        results.append(build_analytics_for_period(selected_period))
    if not step_map["step4"]["completed"]:
        results.append(generate_client_report(selected_period, selected_rfc))
        results.append(run_company_alert(selected_period, selected_rfc, piloto=True))
    return summarize_action_results("Flujo completo ejecutado", results)


def summarize_action_results(title: str, results: list[ActionResult]) -> ActionResult:
    ok_count = sum(1 for result in results if result.success)
    artifacts: list[str] = []
    details: dict[str, object] = {"results": []}
    for result in results:
        artifacts.extend(result.artifacts)
        details["results"].append({"title": result.title, "success": result.success, "message": result.message})
    success = all(result.success for result in results) if results else True
    message = f"{title}: {ok_count} de {len(results)} acciones completadas."
    return ActionResult(success=success, title=title, message=message, artifacts=artifacts, details=details)


def render_operation_status(status: dict) -> None:
    st.markdown("### Estado del periodo")
    summary = status["summary"]
    st.markdown(
        f"""
        <div class="status-grid">
            <div class="status-card"><div class="status-label">ZIPs</div><div class="status-value">{summary['zip_files']}</div></div>
            <div class="status-card"><div class="status-label">XML Extract</div><div class="status-value">{summary['extract_count']}</div></div>
            <div class="status-card"><div class="status-label">XML Organizados</div><div class="status-value">{summary['organized_count']}</div></div>
            <div class="status-card"><div class="status-label">Excels</div><div class="status-value">{summary['excel_count']}</div></div>
            <div class="status-card"><div class="status-label">Word</div><div class="status-value">{summary['word_count']}</div></div>
            <div class="status-card"><div class="status-label">Reportes</div><div class="status-value">{summary['report_count']}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for item in status["checks"]:
        pill_class = "check-pill-ok" if item["ok"] else "check-pill-pending"
        label = "OK" if item["ok"] else "Pendiente"
        st.markdown(
            f"""
            <div class="check-item">
                <span class="{pill_class}">{label}</span>
                <div>
                    <div class="check-text-title">{item['label']}</div>
                    <div class="check-text-detail">{item['detail']}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_artifact_downloads(files: dict[str, list[Path]]) -> None:
    labels = [
        ("excel_files", "Excel SAT"),
        ("word_files", "Resumen Word"),
        ("report_files", "Reporte despacho"),
        ("bi_files", "CSV BI"),
    ]
    any_found = False
    for key, title in labels:
        items = files.get(key, []) if files else []
        if not items:
            continue
        any_found = True
        st.write(f"**{title}**")
        for path in items:
            mime = guess_mime(path)
            st.download_button(
                f"Descargar {path.name}",
                data=path.read_bytes(),
                file_name=path.name,
                mime=mime,
                width="stretch",
                key=f"download-{key}-{path}",
            )
    if not any_found:
        st.info("Aun no hay archivos detectados para este RFC y periodo.")


def guess_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if suffix == ".csv":
        return "text/csv"
    if suffix == ".html":
        return "text/html"
    if suffix == ".txt":
        return "text/plain"
    return "application/octet-stream"


def build_risk_summary(ingresos: float, egresos: float, risk: dict) -> str:
    if ingresos > 0 and egresos > ingresos:
        pct = ((egresos - ingresos) / ingresos) * 100
        return f"Riesgo: Egresos > Ingresos (+{pct:.1f}%)"
    return str(risk.get("headline") or "Sin senales relevantes")


def fmt_pct_or_na(value: float | None) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return "N/A"


def run_dashboard_app() -> None:
    try:
        main()
    except Exception as exc:
        st.error("No se pudo iniciar CONTSIS Desk. Revisa la configuracion del piloto y los archivos requeridos.")
        st.caption(str(exc))


if __name__ == "__main__":
    run_dashboard_app()
