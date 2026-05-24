from __future__ import annotations

import argparse
import os

import uvicorn
from dotenv import load_dotenv

from doctor_dev.config.settings import Settings
from doctor_dev.config.storage import ConfigStorage
from doctor_dev.manager.core import DoctorManager
from doctor_dev.manager.rest_api import create_app
from doctor_dev.utils.logging import setup_logger


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="doctor_dev manager server")
    parser.add_argument("--env", default=".env", help="path to .env file")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.env:
        load_dotenv(args.env)

    settings = Settings()
    storage = ConfigStorage(settings.config_path, settings.runtime_path)
    manager = DoctorManager(storage)
    setup_logger(manager.config.manager.log_file)
    app = create_app(manager)

    uvicorn.run(
        app,
        host=manager.config.manager.host,
        port=manager.config.manager.port,
        log_level=os.getenv("DOCTOR_DEV_UVICORN_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
