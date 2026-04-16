from __future__ import annotations

import base64
from datetime import datetime
from functools import lru_cache
from typing import Any

import streamlit as st
import yaml
from yaml import SafeLoader

from runtime_paths import asset_path, config_path

try:
    import streamlit_authenticator as stauth
except ModuleNotFoundError:  # pragma: no cover
    stauth = None


USERS_CONFIG_PATH = config_path("config", "users.yaml")
USERS_EXAMPLE_PATH = asset_path("config", "users.example.yaml")
LOGIN_LOGO_PATH = asset_path("src", "assets", "logo_sisrodriguez_transparente_v2.png")


def require_authentication() -> Any | None:
    authenticator = _build_authenticator()
    if authenticator is None:
        return None

    silent_result = authenticator.login(location="unrendered", key="contaisisr-login-silent")
    name, auth_status, username = _resolve_auth_state(silent_result)

    if auth_status:
        _store_login_state(username=username, name=name)
        return authenticator

    _render_login_view(authenticator)
    name, auth_status, username = _resolve_auth_state()

    if auth_status:
        _store_login_state(username=username, name=name)
        st.rerun()

    st.session_state["authenticated_username"] = None
    st.session_state["authenticated_name"] = None
    st.session_state["authenticated_status"] = auth_status
    st.session_state.pop("auth_session_started_at", None)
    st.session_state.pop("auth_user_started_for", None)

    if auth_status is False:
        st.error("Usuario o contrasena incorrectos.")
    return None


def render_top_session_bar(authenticator: Any) -> None:
    _inject_auth_ui_styles()
    username = str(st.session_state.get("authenticated_username") or "").strip()
    name = str(st.session_state.get("authenticated_name") or username or "Usuario").strip()
    started_at = str(st.session_state.get("auth_session_started_at") or "").strip()

    left, right = st.columns([7.4, 1.6])
    with left:
        st.markdown('<div class="session-topbar-spacer"></div>', unsafe_allow_html=True)
    with right:
        with st.popover(
            name,
            icon=":material/account_circle:",
            use_container_width=True,
            key="top-session-popover",
        ):
            st.markdown("**Sesion activa**")
            st.caption(name)
            st.caption(username or "Sin usuario")
            if started_at:
                st.caption(f"Inicio: {started_at}")
            authenticator.logout(
                "Cerrar sesion",
                "main",
                key="topbar-logout",
                use_container_width=True,
                callback=_clear_app_session_state,
            )
            if st.session_state.get("logout"):
                st.rerun()


def _build_authenticator() -> Any | None:
    if stauth is None:
        st.error(
            "Falta la dependencia `streamlit-authenticator`. "
            "Instalala con `./.venv/Scripts/python.exe -m pip install streamlit-authenticator`."
        )
        return None

    try:
        config = _load_users_config()
    except Exception as exc:
        st.error(f"No se pudo cargar la configuracion de usuarios: {exc}")
        st.info(
            "Usa `config/users.example.yaml` como plantilla y genera el archivo real con "
            "`./.venv/Scripts/python.exe crear_usuarios.py`, luego guarda el resultado en `config/users.yaml`."
        )
        return None

    credentials = config.get("credentials")
    if not isinstance(credentials, dict):
        st.error("`config/users.yaml` no contiene la seccion `credentials`.")
        return None

    cookie = config.get("cookie")
    if not isinstance(cookie, dict):
        st.error("`config/users.yaml` no contiene la seccion `cookie`.")
        return None

    cookie_name = str(cookie.get("name") or "contaisisr_auth").strip()
    cookie_key = str(cookie.get("key") or "").strip()
    cookie_expiry_days = float(cookie.get("expiry_days") or 30)

    if not cookie_key:
        st.error("`config/users.yaml` necesita un `cookie.key` no vacio.")
        return None

    return stauth.Authenticate(
        credentials=credentials,
        cookie_name=cookie_name,
        cookie_key=cookie_key,
        cookie_expiry_days=cookie_expiry_days,
    )


def _load_users_config() -> dict[str, Any]:
    if not USERS_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"No existe users.yaml en: {USERS_CONFIG_PATH}. "
            f"Puedes partir de {USERS_EXAMPLE_PATH}."
        )

    payload = yaml.load(USERS_CONFIG_PATH.read_text(encoding="utf-8"), Loader=SafeLoader)
    if not isinstance(payload, dict):
        raise ValueError("El archivo users.yaml debe tener una raiz tipo objeto.")
    return payload


def _render_login_view(authenticator: Any) -> None:
    _inject_auth_ui_styles()
    logo_data_uri = _get_login_logo_data_uri()

    hero_col, form_col = st.columns([1.05, 0.95], gap="large")
    with hero_col:
        st.markdown(
            f"""
            <div class="auth-hero-card">
                <div class="auth-hero-top">Acceso privado del despacho</div>
                <div class="auth-hero-logo-wrap">
                    <img class="auth-hero-logo" src="{logo_data_uri}" alt="Sis Rodriguez Contadores Publicos">
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with form_col:
        authenticator.login(
            location="main",
            key="contaisisr-login",
            clear_on_submit=False,
            fields={
                "Form name": "Acceso a CONTSIS",
                "Username": "Usuario",
                "Password": "Contrasena",
                "Login": "Entrar",
            },
        )


def _store_login_state(username: Any, name: Any) -> None:
    normalized_username = str(username or "").strip()
    normalized_name = str(name or normalized_username or "Usuario").strip()
    previous_username = str(st.session_state.get("auth_user_started_for") or "").strip()

    if normalized_username and previous_username != normalized_username:
        st.session_state["auth_session_started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state["auth_user_started_for"] = normalized_username

    st.session_state["authenticated_username"] = normalized_username or None
    st.session_state["authenticated_name"] = normalized_name
    st.session_state["authenticated_status"] = True
    st.session_state.pop("logout", None)


def _resolve_auth_state(login_result: Any | None = None) -> tuple[Any, Any, Any]:
    name = st.session_state.get("name")
    auth_status = st.session_state.get("authentication_status")
    username = st.session_state.get("username")

    if isinstance(login_result, tuple) and len(login_result) == 3:
        login_name, login_auth_status, login_username = login_result
        name = login_name if login_name is not None else name
        auth_status = login_auth_status if login_auth_status is not None else auth_status
        username = login_username if login_username is not None else username

    return name, auth_status, username


@lru_cache(maxsize=1)
def _get_login_logo_data_uri() -> str:
    if not LOGIN_LOGO_PATH.exists():
        return ""
    encoded = base64.b64encode(LOGIN_LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _inject_auth_ui_styles() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stSidebarCollapsedControl"] {
            display: none;
        }
        .auth-hero-card {
            background: linear-gradient(145deg, #0f5b82 0%, #2d7fa4 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-bottom: 4px solid #00A396;
            border-radius: 22px;
            padding: 1.85rem 2rem;
            color: #f8fafc;
            box-shadow: 0 18px 40px rgba(0, 0, 0, 0.16);
            min-height: 26rem;
        }
        .auth-hero-top {
            text-transform: uppercase;
            letter-spacing: 0.1em;
            font-size: 0.76rem;
            color: rgba(255,255,255,0.72);
            margin-bottom: 1.35rem;
            font-weight: 700;
            text-align: left;
        }
        .auth-hero-logo-wrap {
            min-height: 20rem;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .auth-hero-logo {
            width: min(390px, 100%);
            height: auto;
            display: block;
            margin: 0 auto;
            object-fit: contain;
        }
        form[data-testid="stForm"] {
            background: #ffffff;
            border: 1px solid rgba(0, 43, 73, 0.08);
            border-radius: 20px;
            padding: 1rem 1rem 0.45rem;
            box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
            margin-top: 3.5rem;
        }
        .session-topbar-spacer {
            min-height: 0.5rem;
        }
        @media (max-width: 980px) {
            .auth-hero-card {
                min-height: 0;
                margin-bottom: 1rem;
            }
            .auth-hero-logo-wrap {
                min-height: 14rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _clear_app_session_state(*_args: Any, **_kwargs: Any) -> None:
    keys_to_clear = [
        "selected_rfc",
        "selected_period",
        "sidebar_company_search",
        "active_section",
        "pending_section",
        "period_context_rfc",
        "operation_selected_rfc",
        "operation_selected_period",
        "operation_target_company",
        "operation_upload_result",
        "authenticated_username",
        "authenticated_name",
        "authenticated_status",
        "auth_session_started_at",
        "auth_user_started_for",
        "top-session-popover",
        "contaisisr-login",
        "contaisisr-login-silent",
    ]
    for key in keys_to_clear:
        st.session_state.pop(key, None)
