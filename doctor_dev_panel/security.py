from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from typing import Tuple


def create_password_hash(password: str, iterations: int = 200_000) -> str:
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_urlsafe(18)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"pbkdf2_sha256${iterations}${salt}${encoded}"


def _parse_hash(password_hash: str) -> Tuple[int, str, str]:
    try:
        algorithm, iterations, salt, digest = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            raise ValueError("unsupported password hash algorithm")
        return int(iterations), salt, digest
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid password hash format") from exc


def verify_password(password: str, password_hash: str) -> bool:
    try:
        iterations, salt, expected = _parse_hash(password_hash)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
        actual = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def generate_secret() -> str:
    return secrets.token_urlsafe(48)


if __name__ == "__main__":
    import argparse
    import getpass

    parser = argparse.ArgumentParser(description="Generate a Doctor Dev admin password hash")
    parser.add_argument("--password", help="password; if omitted it will be prompted securely")
    args = parser.parse_args()
    password = args.password or getpass.getpass("Password: ")
    print(create_password_hash(password))




