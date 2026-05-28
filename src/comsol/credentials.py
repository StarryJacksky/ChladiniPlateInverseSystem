from __future__ import annotations

import os
import secrets
import string
from dataclasses import dataclass
from pathlib import Path


_GENERATED_USER = ""
_GENERATED_PASSWORD = ""

_CRED_STATE_PATH = Path("data/.comsol_credentials.state")


@dataclass(frozen=True)
class ComsolCredentials:
    username: str
    password: str
    generated: bool


def _random_token(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def set_comsol_credentials(username: str, password: str) -> ComsolCredentials:
    clean_username = str(username or "").strip()
    if not clean_username:
        raise ValueError("COMSOL Server username is required.")
    os.environ["COMSOL_SERVER_USER"] = clean_username
    os.environ["COMSOL_SERVER_PASSWORD"] = str(password or "")
    return ComsolCredentials(clean_username, str(password or ""), False)


def _load_persisted_credentials() -> tuple[str, str]:
    try:
        if _CRED_STATE_PATH.exists():
            lines = _CRED_STATE_PATH.read_text(encoding="utf-8").splitlines()
            data = {}
            for line in lines:
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip()
            return data.get("COMSOL_SERVER_USER", ""), data.get("COMSOL_SERVER_PASSWORD", "")
    except OSError:
        pass
    return "", ""


def _persist_credentials(user: str, password: str) -> None:
    try:
        _CRED_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CRED_STATE_PATH.write_text(
            f"COMSOL_SERVER_USER={user}\nCOMSOL_SERVER_PASSWORD={password}\n",
            encoding="utf-8",
        )
        try:
            os.chmod(_CRED_STATE_PATH, 0o600)
        except OSError:
            pass
    except OSError:
        pass


def clear_persisted_credentials() -> None:
    try:
        if _CRED_STATE_PATH.exists():
            _CRED_STATE_PATH.unlink()
    except OSError:
        pass


def ensure_comsol_credentials(config: dict | None = None) -> ComsolCredentials:
    global _GENERATED_USER, _GENERATED_PASSWORD
    comsol_config = (config or {}).get("comsol", {})
    configured_user = str(comsol_config.get("server_user") or "").strip()
    configured_password = str(comsol_config.get("server_password") or "")
    env_user = str(os.environ.get("COMSOL_SERVER_USER") or "").strip()
    env_password = str(os.environ.get("COMSOL_SERVER_PASSWORD") or "")
    if env_user:
        return ComsolCredentials(env_user, env_password, False)
    if configured_user:
        os.environ["COMSOL_SERVER_USER"] = configured_user
        os.environ["COMSOL_SERVER_PASSWORD"] = configured_password
        return ComsolCredentials(configured_user, configured_password, False)
    persisted_user, persisted_password = _load_persisted_credentials()
    if persisted_user:
        os.environ["COMSOL_SERVER_USER"] = persisted_user
        os.environ["COMSOL_SERVER_PASSWORD"] = persisted_password
        return ComsolCredentials(persisted_user, persisted_password, True)
    if not _GENERATED_USER:
        _GENERATED_USER = "codex_" + _random_token(8)
        _GENERATED_PASSWORD = _random_token(24)
    os.environ["COMSOL_SERVER_USER"] = _GENERATED_USER
    os.environ["COMSOL_SERVER_PASSWORD"] = _GENERATED_PASSWORD
    _persist_credentials(_GENERATED_USER, _GENERATED_PASSWORD)
    return ComsolCredentials(_GENERATED_USER, _GENERATED_PASSWORD, True)


def comsol_credentials_status(config: dict | None = None) -> dict:
    credentials = ensure_comsol_credentials(config)
    return {
        "username": credentials.username,
        "has_password": bool(credentials.password),
        "generated": credentials.generated,
    }


def is_credential_failure(output: str) -> bool:
    lowered = output.lower()
    tokens = [
        "comsol_credentials_required",
        "username or password",
        "user name or password",
        "用户名或密码",
        "鐢ㄦ埛鍚嶆垨瀵嗙爜",
        "no user information found",
        "invalid login",
        "login information is incorrect",
        "password at the comsol multiphysics server prompt",
    ]
    return any(token in lowered for token in tokens)
