from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("DOCTOR_DEV_PANEL_HOST", "0.0.0.0")
    port = int(os.getenv("DOCTOR_DEV_PANEL_PORT", "8088"))
    ssl_certfile = os.getenv("DOCTOR_DEV_PANEL_SSL_CERTFILE") or None
    ssl_keyfile = os.getenv("DOCTOR_DEV_PANEL_SSL_KEYFILE") or None
    uvicorn.run(
        "doctor_dev_panel.app:app",
        host=host,
        port=port,
        reload=False,
        log_level=os.getenv("DOCTOR_DEV_UVICORN_LOG_LEVEL", "info"),
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )


if __name__ == "__main__":
    main()
