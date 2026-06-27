from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("DOCTOR_DEV_AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("DOCTOR_DEV_AGENT_PORT", "9101"))
    ssl_certfile = os.getenv("DOCTOR_DEV_AGENT_SSL_CERTFILE") or None
    ssl_keyfile = os.getenv("DOCTOR_DEV_AGENT_SSL_KEYFILE") or None
    uvicorn.run(
        "doctor_dev_agent.app:app",
        host=host,
        port=port,
        reload=False,
        log_level=os.getenv("DOCTOR_DEV_UVICORN_LOG_LEVEL", "info"),
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )


if __name__ == "__main__":
    main()
