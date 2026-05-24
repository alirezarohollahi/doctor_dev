from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, TypeVar, Union

from pydantic import BaseModel

from doctor_dev.models.config import DoctorConfig
from doctor_dev.models.runtime import RuntimeState

T = TypeVar("T", bound=BaseModel)


def ensure_parent(path: Union[str, Path]) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def read_json(path: Union[str, Path]) -> Dict[str, Any]:
    file_path = Path(path).expanduser()
    if not file_path.exists():
        return {}
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json_atomic(path: Union[str, Path], data: Dict[str, Any]) -> None:
    file_path = Path(path).expanduser()
    ensure_parent(file_path)
    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True)
        file.write("\n")
    os.replace(tmp_path, file_path)


class ConfigStorage:
    def __init__(self, config_path: str, runtime_path: str):
        self.config_path = config_path
        self.runtime_path = runtime_path

    def load_config(self) -> DoctorConfig:
        data = read_json(self.config_path)
        if not data:
            raise FileNotFoundError(f"config file not found or empty: {self.config_path}")
        return DoctorConfig.model_validate(data)

    def save_config(self, config: DoctorConfig) -> None:
        write_json_atomic(self.config_path, config.model_dump(mode="json"))

    def load_runtime(self) -> RuntimeState:
        data = read_json(self.runtime_path)
        if not data:
            return RuntimeState()
        return RuntimeState.model_validate(data)

    def save_runtime(self, state: RuntimeState) -> None:
        write_json_atomic(self.runtime_path, state.model_dump(mode="json"))
