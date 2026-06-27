from __future__ import annotations

import os
import uvicorn


def main() -> None:
    host = os.getenv("DOCTOR_DEV_AGENT_HOST", "127.0.0.1")
    port = int(os.getenv("DOCTOR_DEV_AGENT_PORT", "9101"))
    uvicorn.run("doctor_dev_agent.app:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
