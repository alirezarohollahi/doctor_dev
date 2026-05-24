from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    config_path: str = "./configs/doctor_dev.json"
    runtime_path: str = "./configs/doctor_dev.runtime.json"

    model_config = SettingsConfigDict(
        env_prefix="DOCTOR_DEV_",
        env_file=None,
        extra="ignore",
    )
