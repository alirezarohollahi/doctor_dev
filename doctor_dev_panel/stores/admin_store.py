from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .security import create_password_hash, verify_password


def _default_store_path() -> Path:
    configured = os.getenv("ADMIN_STORE_PATH")
    if configured:
        return Path(configured).expanduser()
    etc_path = Path("/etc/doctor-dev-panel/admins.json")
    if etc_path.exists() or os.access(str(etc_path.parent), os.W_OK):
        return etc_path
    return Path.cwd() / "data" / "admins.json"


def store_path() -> Path:
    return _default_store_path().resolve()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _empty_store() -> dict[str, Any]:
    return {"version": 1, "admins": []}


def _env_admin() -> Optional[dict[str, Any]]:
    username = os.getenv("ADMIN_USERNAME", "").strip()
    password_hash = os.getenv("ADMIN_PASSWORD_HASH", "").strip()
    if username and password_hash:
        return {
            "username": username,
            "password_hash": password_hash,
            "created_at": None,
            "updated_at": None,
            "source": "env",
        }
    return None


def load_store(include_env_fallback: bool = True) -> dict[str, Any]:
    path = store_path()
    data = _empty_store()
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
            if not isinstance(data.get("admins"), list):
                data["admins"] = []
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Cannot read admin store: {path}: {exc}") from exc

    if include_env_fallback and not data.get("admins"):
        env_admin = _env_admin()
        if env_admin:
            data["admins"] = [env_admin]
    return data


def save_store(data: dict[str, Any]) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="admins.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
        try:
            os.chmod(path, 0o600)
        except PermissionError:
            pass
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def list_admins() -> list[dict[str, Any]]:
    data = load_store(include_env_fallback=True)
    return [
        {
            "username": item.get("username", ""),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "source": item.get("source", "store"),
        }
        for item in data.get("admins", [])
        if item.get("username")
    ]


def _find_admin(data: dict[str, Any], username: str) -> Optional[dict[str, Any]]:
    for item in data.get("admins", []):
        if str(item.get("username", "")) == username:
            return item
    return None


def authenticate_admin(username: str, password: str) -> bool:
    data = load_store(include_env_fallback=True)
    item = _find_admin(data, username)
    if not item:
        return False
    return verify_password(password, str(item.get("password_hash", "")))


def _load_writable_store_with_env_migration() -> dict[str, Any]:
    data = load_store(include_env_fallback=False)
    if not data.get("admins"):
        env_admin = _env_admin()
        if env_admin:
            env_admin["source"] = "store"
            env_admin["created_at"] = _now()
            env_admin["updated_at"] = _now()
            data["admins"] = [env_admin]
    return data


def set_password(username: str, password: str) -> None:
    username = username.strip()
    if not username:
        raise ValueError("username cannot be empty")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")

    data = _load_writable_store_with_env_migration()
    item = _find_admin(data, username)
    now = _now()
    if item:
        item["password_hash"] = create_password_hash(password)
        item["updated_at"] = now
        item["source"] = "store"
    else:
        data.setdefault("admins", []).append(
            {
                "username": username,
                "password_hash": create_password_hash(password),
                "created_at": now,
                "updated_at": now,
                "source": "store",
            }
        )
    save_store(data)


def remove_admin(username: str, allow_last: bool = False) -> bool:
    username = username.strip()
    data = _load_writable_store_with_env_migration()
    admins = [item for item in data.get("admins", []) if item.get("username")]
    existing = [item for item in admins if item.get("username") == username]
    if not existing:
        return False
    if len(admins) <= 1 and not allow_last:
        raise ValueError("cannot remove the last admin")
    data["admins"] = [item for item in admins if item.get("username") != username]
    save_store(data)
    return True




