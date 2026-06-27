from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
WEB_DIR = PACKAGE_DIR / "web"
ROOT_DIR = Path.cwd().resolve()

APP_TITLE = os.getenv("APP_NAME", "Doctor Dev Panel")
APP_VERSION = "0.1.0-login-foundation"
SESSION_COOKIE = os.getenv("SESSION_COOKIE", "doctor_dev_session")
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "43200"))
DEFAULT_PORT = int(os.getenv("PORT", "8080"))

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
