from __future__ import annotations

import getpass
import secrets

import streamlit_authenticator as stauth
import yaml


DEFAULT_USERS = [
    {"username": "admin", "name": "Administrador SISR", "email": "admin@despacho.local"},
    {"username": "contadora1", "name": "Contadora 1", "email": "contadora1@despacho.local"},
    {"username": "contadora2", "name": "Contadora 2", "email": "contadora2@despacho.local"},
    {"username": "contadora3", "name": "Contadora 3", "email": "contadora3@despacho.local"},
    {"username": "contadora4", "name": "Contadora 4", "email": "contadora4@despacho.local"},
]


def _prompt_password(username: str) -> str | None:
    prompt = f"Contrasena para {username} (deja vacio para omitir este usuario): "
    password = getpass.getpass(prompt)
    if not password:
        return None

    confirmation = getpass.getpass(f"Confirma la contrasena para {username}: ")
    if password != confirmation:
        raise ValueError(f"La confirmacion no coincide para {username}.")
    return password


def main() -> None:
    usernames: dict[str, dict[str, str]] = {}

    for user in DEFAULT_USERS:
        password = _prompt_password(user["username"])
        if password is None:
            continue

        usernames[user["username"]] = {
            "email": user["email"],
            "name": user["name"],
            "password": stauth.Hasher.hash(password),
        }

    if not usernames:
        raise SystemExit("No se capturaron usuarios. No se genero ningun YAML.")

    config = {
        "cookie": {
            "name": "contaisisr_auth",
            "key": secrets.token_hex(32),
            "expiry_days": 30,
        },
        "credentials": {
            "usernames": usernames,
        },
    }

    print("# Guarda este contenido en config/users.yaml")
    print("# Este archivo es local y debe quedar fuera de Git.")
    print(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))


if __name__ == "__main__":
    main()
