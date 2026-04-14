from __future__ import annotations

import base64
from functools import lru_cache
from typing import Any

import pandas as pd
import streamlit as st

from runtime_paths import asset_path
from src.app.pilot_preferences import (
    get_company_account_owner,
    get_owner_filter_label,
    list_account_owners,
    save_account_owner_assignments,
)
from src.utils.config import settings


def render_despacho_home(
    companies: list[dict[str, Any]],
    all_companies: list[dict[str, Any]],
    owner_filter: str,
) -> None:
    apply_despacho_styles()
    logo_data_uri = get_despacho_logo_data_uri()
    company_options = build_company_options(companies)
    picker_version = int(st.session_state.get("despacho_company_picker_version", 0))
    picker_key = f"despacho_company_picker_{picker_version}"
    filter_label = get_owner_filter_label(owner_filter, all_companies)
    logo_markup = (
        f'<div class="despacho-hero-logo-wrap"><img class="despacho-hero-logo" src="{logo_data_uri}" alt="Logo Sis Rodriguez"></div>'
        if logo_data_uri
        else '<div class="despacho-hero-logo-wrap" aria-hidden="true"></div>'
    )

    st.markdown(
        f"""
        <div class="shell-hero despacho-hero">
            <div class="despacho-hero-grid">
                <div class="despacho-hero-balance" aria-hidden="true"></div>
                <div class="despacho-hero-copy-block">
                    <div class="shell-hero-top">Directorio del despacho</div>
                    <div class="despacho-hero-title">SIS RODRIGUEZ</div>
                </div>
                {logo_markup}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, center, right = st.columns([1, 1.8, 1])
    with center:
        st.markdown(
            f"""
            <div class="despacho-search-copy">
                Vista actual: <strong>{filter_label}</strong>. Selecciona una empresa para abrir su resumen ejecutivo y continuar con el flujo operativo.
            </div>
            """,
            unsafe_allow_html=True,
        )
        selected_label = None
        if company_options:
            with st.container():
                selected_label = st.selectbox(
                    "Buscar cliente o empresa...",
                    options=list(company_options.keys()),
                    index=None,
                    placeholder="Escribe RFC, nombre corto o razon social",
                    key=picker_key,
                    label_visibility="collapsed",
                )
        else:
            st.info(
                "No hay empresas visibles con el filtro actual. Ajusta la cartera desde la barra lateral o asigna usuarios mas abajo."
            )

    if selected_label:
        selected_rfc = company_options[selected_label]["rfc"]
        open_company_summary(selected_rfc)

    st.markdown("### Empresas recientes")
    st.caption("Accesos rapidos para volver a las empresas que se consultan con mas frecuencia.")

    recent_companies = get_recent_companies(companies)
    if recent_companies:
        st.markdown('<div class="recent-card-btn">', unsafe_allow_html=True)
        columns = st.columns(3)
        for column, company in zip(columns, recent_companies):
            with column:
                rfc = str(company.get("rfc") or "").upper()
                if st.button(
                    company["nombre"],
                    key=f"recent-company-{rfc}",
                    type="primary",
                    width="stretch",
                ):
                    open_company_summary(rfc)
                st.markdown(f'<div class="recent-card-rfc">RFC: {rfc}</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.caption("Sin empresas recientes para esta vista.")

    st.markdown("### Vista general")
    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    metric_1.metric("Empresas visibles", len(companies))
    metric_2.metric("Catalogo total", len(all_companies))
    metric_3.metric("Correos registrados", count_registered_emails(all_companies))
    metric_4.metric("Empresa activa", get_active_company_name(all_companies))

    st.caption(f"Boveda XML activa: {settings.boveda_dir}")

    st.markdown("### Configuracion de cartera")
    st.caption("Asignar usuario por RFC.")
    render_account_owner_assignment_editor(all_companies)


def apply_despacho_styles() -> None:
    st.markdown(
        """
        <style>
        .despacho-hero {
            padding-top: 1.7rem;
            padding-bottom: 1.55rem;
        }
        .despacho-hero-grid {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
            align-items: center;
            gap: 1rem;
        }
        .despacho-hero-copy-block {
            text-align: center;
        }
        .despacho-hero-balance {
            min-height: 1px;
        }
        .despacho-hero-logo-wrap {
            display: flex;
            justify-content: flex-end;
            align-items: center;
            min-height: 72px;
        }
        .despacho-hero-logo {
            width: min(180px, 100%);
            max-height: 92px;
            object-fit: contain;
            filter: none !important;
            background: transparent;
        }
        .despacho-hero-title {
            color: #f8fafc;
            font-size: 2.2rem;
            font-weight: 700;
            letter-spacing: -0.03em;
            line-height: 1.1;
        }
        .despacho-search-copy {
            color: rgba(0, 43, 73, 0.76);
            font-size: 1.08rem;
            line-height: 1.45;
            max-width: 640px;
            margin: 0.35rem auto 0.85rem;
            text-align: center;
        }
        .recent-card-btn {
            margin-top: 0.35rem;
        }
        div.stButton > button {
            border-radius: 12px;
            border: 1px solid rgba(0, 43, 73, 0.08);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        div.stButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 10px 18px rgba(15, 23, 42, 0.10);
        }
        div.stButton > button[kind="primary"] {
            background: #002B49;
            color: #ffffff;
            min-height: 120px;
            font-weight: 700;
            font-size: 1.4rem;
            letter-spacing: -0.01em;
            justify-content: center;
            border: 1px solid rgba(255,255,255,0.10);
            border-bottom: 4px solid #00A396;
            box-shadow: 0 10px 18px rgba(0,0,0,0.18);
        }
        .recent-card-rfc {
            margin-top: 0.7rem;
            color: rgba(0, 43, 73, 0.68);
            font-size: 0.9rem;
        }
        @media (max-width: 900px) {
            .despacho-hero-grid {
                grid-template-columns: 1fr;
                gap: 0.8rem;
            }
            .despacho-hero-copy-block {
                order: 1;
            }
            .despacho-hero-logo-wrap {
                order: 2;
                justify-content: center;
                min-height: 0;
            }
            .despacho-hero-balance {
                display: none;
            }
            .despacho-hero-logo {
                width: min(150px, 100%);
                max-height: 78px;
            }
            .despacho-hero-title {
                font-size: 1.95rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@lru_cache(maxsize=1)
def get_despacho_logo_data_uri() -> str:
    logo_path = asset_path("src", "assets", "logo_sisrodriguez_isotipo.png")
    try:
        encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:image/png;base64,{encoded}"


def build_company_options(companies: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    options: dict[str, dict[str, Any]] = {}
    for company in companies:
        nombre = str(
            company.get("nombre")
            or company.get("nombre_corto")
            or company.get("razon_social")
            or company.get("rfc")
            or "SIN_NOMBRE"
        )
        rfc = str(company.get("rfc") or "").upper()
        if not rfc:
            continue
        options[f"{nombre} ({rfc})"] = company
    return options


def get_recent_companies(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets = ("IBAYRO", "NOFER", "SEGUROCA")
    selected: list[dict[str, Any]] = []

    for target in targets:
        match = next((company for company in companies if company_matches(company, target)), None)
        if match:
            selected.append(match)

    if len(selected) < 3:
        for company in companies:
            if company not in selected:
                selected.append(company)
            if len(selected) == 3:
                break

    return selected[:3]


def company_matches(company: dict[str, Any], target: str) -> bool:
    values = [
        company.get("nombre"),
        company.get("nombre_corto"),
        company.get("razon_social"),
        company.get("rfc"),
    ]
    normalized_target = target.upper()
    return any(normalized_target in str(value or "").upper() for value in values)


def get_active_company_name(companies: list[dict[str, Any]]) -> str:
    selected_rfc = st.session_state.get("selected_rfc")
    if not selected_rfc:
        return "Sin seleccion"

    match = next((company for company in companies if company.get("rfc") == selected_rfc), None)
    if not match:
        return selected_rfc
    return str(match.get("nombre") or match.get("nombre_corto") or match.get("razon_social") or selected_rfc)


def count_registered_emails(companies: list[dict[str, Any]]) -> int:
    return sum(len(company.get("emails") or []) for company in companies)


def render_account_owner_assignment_editor(companies: list[dict[str, Any]]) -> None:
    flash_message = st.session_state.pop("account_owner_assignment_flash", None)
    if flash_message:
        st.success(flash_message)

    if not companies:
        st.info("No hay empresas disponibles para asignar.")
        return

    rows = [
        {
            "RFC": str(company.get("rfc") or "").upper(),
            "Empresa": str(
                company.get("nombre")
                or company.get("nombre_corto")
                or company.get("razon_social")
                or company.get("rfc")
                or "SIN_NOMBRE"
            ),
            "Usuario asignado": get_company_account_owner(company) or "",
        }
        for company in companies
        if str(company.get("rfc") or "").strip()
    ]

    frame = pd.DataFrame(rows)
    edited = st.data_editor(
        frame,
        hide_index=True,
        use_container_width=True,
        disabled=["RFC", "Empresa"],
        key="account-owner-editor",
        num_rows="fixed",
        column_config={
            "RFC": st.column_config.TextColumn("RFC"),
            "Empresa": st.column_config.TextColumn("Empresa"),
            "Usuario asignado": st.column_config.TextColumn(
                "Usuario asignado",
                help="Escribe el nombre del usuario responsable. Dejalo vacio para mostrarlo en Sin asignar.",
            ),
        },
    )

    save_col, info_col = st.columns([0.8, 1.2])
    with save_col:
        if st.button("Guardar asignaciones", key="save-account-owner-assignments", width="stretch"):
            assignments = {
                str(row["RFC"]).strip().upper(): str(row["Usuario asignado"]).strip()
                for row in edited.to_dict("records")
            }
            try:
                changes, path = save_account_owner_assignments(assignments)
            except Exception as exc:
                st.error(f"No se pudieron guardar las asignaciones: {exc}")
            else:
                message = f"Asignaciones guardadas en {path.name}. RFC actualizados: {changes}."
                st.session_state["account_owner_assignment_flash"] = message
                st.rerun()
    with info_col:
        owners = list_account_owners(companies)
        owners_label = ", ".join(owners) if owners else "Sin asignaciones guardadas."
        st.caption(f"Usuarios detectados: {owners_label}")


def open_company_summary(rfc: str) -> None:
    st.session_state["despacho_company_picker_version"] = int(
        st.session_state.get("despacho_company_picker_version", 0)
    ) + 1
    st.session_state["selected_rfc"] = rfc
    st.session_state["pending_section"] = "Resumen Ejecutivo"
    st.rerun()
