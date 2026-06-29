from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union


def load_env_file(path: Optional[Union[str, os.PathLike[str]]]) -> None:
    """Load simple KEY=VALUE lines into os.environ without overriding existing values."""
    if not path:
        return
    env_path = Path(path).expanduser().resolve()
    if not env_path.exists():
        raise FileNotFoundError(f"env file not found: {env_path}")

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value




