from __future__ import annotations

import os
import uvicorn


def main() -> None:
    host = os.getenv("DOCTOR_DEV_PANEL_HOST", "127.0.0.1")
    port = int(os.getenv("DOCTOR_DEV_PANEL_PORT", "8088"))
    uvicorn.run("doctor_dev_panel.app:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
