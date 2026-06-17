#!/usr/bin/env python3
"""
Standalone doctor-dev admin panel + TCP forwarding manager.

Goal:
- one file: main.py
- one dependency file: requirements.txt
- no pyproject.toml
- serves a pretty admin panel on port 8080
- includes the doctor-dev TCP forwarding manager logic
- includes API endpoints for the front-end and compatibility endpoints for remote nodes

Run:
    pip install -r requirements.txt
    ADMIN_USERNAME=admin ADMIN_PASSWORD='change-me' APP_SECRET='long-random-secret' python main.py

Open:
    http://SERVER_IP:8080

Security note:
This admin panel can edit files and start/stop TCP listeners. Put it behind HTTPS,
a firewall, or a VPN before exposing it to the public internet.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

import httpx
import uvicorn
from dotenv import dotenv_values
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field, ValidationError, field_validator

# =============================================================================
# App constants
# =============================================================================

APP_TITLE = "a project to see every where"
APP_VERSION = "2.0.0-standalone"
ROOT_DIR = Path.cwd().resolve()
SESSION_COOKIE = "apsee_admin_session"
SESSION_TTL_SECONDS = 12 * 60 * 60
DEFAULT_PORT = 8080
BUFFER_SIZE = 65535

EXCLUDED_SCAN_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".cache",
    ".idea",
    ".vscode",
    "doctor_dev.egg-info",
    "DocNodes.back",
}

logger = logging.getLogger("doctor_admin")
manager_logger = logging.getLogger("doctor_manager")

# =============================================================================
# Config + runtime models copied into this file so no package install is needed
# =============================================================================


class TargetStrategy(str, Enum):
    round_robin = "round_robin"
    failover = "failover"


class StaticTarget(BaseModel):
    type: Literal["static"] = "static"
    host: str
    port: int

    @field_validator("port")
    @classmethod
    def valid_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return value


class RemoteGroupTarget(BaseModel):
    type: Literal["remote_group"] = "remote_group"
    dependency: str


Target = Union[StaticTarget, RemoteGroupTarget]


class GroupConfig(BaseModel):
    name: str
    process_count: int = Field(ge=1, le=4096)
    listen_host: str = "0.0.0.0"
    public_host: Optional[str] = None
    port_mode: Literal["random", "fixed"] = "random"
    fixed_ports: List[int] = Field(default_factory=list)
    targets: List[Target] = Field(default_factory=list)
    strategy: TargetStrategy = TargetStrategy.round_robin
    enabled: bool = True

    @field_validator("fixed_ports")
    @classmethod
    def valid_fixed_ports(cls, value: List[int]) -> List[int]:
        for port in value:
            if not 1 <= port <= 65535:
                raise ValueError("fixed_ports must contain ports between 1 and 65535")
        return value


class RemoteDependencyConfig(BaseModel):
    name: str
    manager_url: str
    group_name: str
    token: Optional[str] = None
    sync_interval_seconds: int = Field(default=10, ge=2)


class ManagerConfig(BaseModel):
    name: str
    host: str = "0.0.0.0"
    port: int = 7000
    public_host: Optional[str] = None
    api_token: Optional[str] = None
    log_file: str = "./logs/doctor_dev.log"

    @field_validator("port")
    @classmethod
    def valid_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return value


class DoctorConfig(BaseModel):
    manager: ManagerConfig
    groups: List[GroupConfig] = Field(default_factory=list)
    remote_dependencies: List[RemoteDependencyConfig] = Field(default_factory=list)

    def group_by_name(self, name: str) -> Optional[GroupConfig]:
        for group in self.groups:
            if group.name == name:
                return group
        return None

    def dependency_by_name(self, name: str) -> Optional[RemoteDependencyConfig]:
        for dependency in self.remote_dependencies:
            if dependency.name == name:
                return dependency
        return None


class ProcessRuntime(BaseModel):
    process_id: str
    group_name: str
    listen_host: str
    public_host: str
    listen_port: int
    status: str = "stopped"
    active_connections: int = 0
    connection_count: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    last_error: Optional[str] = None


class GroupRuntime(BaseModel):
    name: str
    status: str = "stopped"
    processes: List[ProcessRuntime] = Field(default_factory=list)


class RemoteDependencyRuntime(BaseModel):
    name: str
    manager_url: str
    group_name: str
    status: str = "unknown"
    last_error: Optional[str] = None
    last_sync_at: Optional[str] = None
    inbounds: List[dict] = Field(default_factory=list)


class RuntimeState(BaseModel):
    groups: Dict[str, GroupRuntime] = Field(default_factory=dict)
    remote_dependencies: Dict[str, RemoteDependencyRuntime] = Field(default_factory=dict)


# =============================================================================
# Request/response models for admin API
# =============================================================================


class LoginBody(BaseModel):
    user_name: str
    password: str


class StartManagerBody(BaseModel):
    config_path: Optional[str] = None
    env_path: Optional[str] = None
    runtime_path: Optional[str] = None


class FileWriteBody(BaseModel):
    path: str
    content: str


class ValidateJsonBody(BaseModel):
    content: str


class PathBody(BaseModel):
    path: str


class GroupNameBody(BaseModel):
    name: str


# =============================================================================
# Storage helpers
# =============================================================================


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_join(path_value: str) -> Path:
    """Return a path under ROOT_DIR, refusing traversal outside the project."""
    if not path_value:
        raise HTTPException(status_code=400, detail="path is required")
    path = Path(path_value)
    if path.is_absolute():
        candidate = path.resolve()
    else:
        candidate = (ROOT_DIR / path).resolve()
    try:
        candidate.relative_to(ROOT_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path must stay inside the project root") from exc
    return candidate


def to_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return str(path)


def ensure_parent(path: Union[str, Path]) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def read_json_file(path: Union[str, Path]) -> Dict[str, Any]:
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
        self.config_path = str(Path(config_path).expanduser())
        self.runtime_path = str(Path(runtime_path).expanduser())

    def load_config(self) -> DoctorConfig:
        data = read_json_file(self.config_path)
        if not data:
            raise FileNotFoundError(f"config file not found or empty: {self.config_path}")
        return DoctorConfig.model_validate(data)

    def save_config(self, config: DoctorConfig) -> None:
        write_json_atomic(self.config_path, config.model_dump(mode="json"))

    def load_runtime(self) -> RuntimeState:
        data = read_json_file(self.runtime_path)
        if not data:
            return RuntimeState()
        return RuntimeState.model_validate(data)

    def save_runtime(self, state: RuntimeState) -> None:
        write_json_atomic(self.runtime_path, state.model_dump(mode="json"))


# =============================================================================
# Logging
# =============================================================================


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = 1000):
        super().__init__()
        self.capacity = capacity
        self.records: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.records.append(msg)
            if len(self.records) > self.capacity:
                self.records = self.records[-self.capacity :]
        except Exception:
            self.handleError(record)

    def tail(self, limit: int = 200) -> List[str]:
        return self.records[-limit:]


memory_log_handler = RingBufferHandler()


def setup_logging(log_file: Optional[str] = None) -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.setLevel(logging.INFO)
    root.addHandler(stream)

    memory_log_handler.setFormatter(formatter)
    memory_log_handler.setLevel(logging.INFO)
    root.addHandler(memory_log_handler)

    if log_file:
        try:
            log_path = safe_join(log_file) if not Path(log_file).is_absolute() else Path(log_file)
            ensure_parent(log_path)
            file_handler = logging.FileHandler(log_path)
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.INFO)
            root.addHandler(file_handler)
        except Exception as exc:  # noqa: BLE001
            root.warning("could not attach file logger %s: %s", log_file, exc)


setup_logging()


# =============================================================================
# Port allocation + forwarding
# =============================================================================


def normalize_bind_host(host: Optional[str]) -> str:
    return "0.0.0.0" if host in {None, ""} else str(host)


def is_port_available(host: str, port: int) -> bool:
    bind_host = normalize_bind_host(host)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((bind_host, port))
            return True
    except OSError:
        return False


def allocate_random_port(host: str) -> int:
    bind_host = normalize_bind_host(host)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((bind_host, 0))
        return int(sock.getsockname()[1])


@dataclass(frozen=True)
class ResolvedTarget:
    host: str
    port: int


class TunnelProcess:
    def __init__(
        self,
        process_id: str,
        group_name: str,
        listen_host: str,
        public_host: str,
        listen_port: int,
        target_provider: Callable[[], List[ResolvedTarget]],
        strategy: str = "round_robin",
    ):
        self.process_id = process_id
        self.group_name = group_name
        self.listen_host = listen_host
        self.public_host = public_host
        self.listen_port = listen_port
        self.target_provider = target_provider
        self.strategy = strategy
        self.server: Optional[asyncio.AbstractServer] = None
        self._rr_index = 0
        self.runtime = ProcessRuntime(
            process_id=process_id,
            group_name=group_name,
            listen_host=listen_host,
            public_host=public_host,
            listen_port=listen_port,
            status="stopped",
        )

    async def start(self) -> None:
        if self.server is not None:
            return
        try:
            self.server = await asyncio.start_server(
                self._handle_client,
                self.listen_host,
                self.listen_port,
                backlog=4096,
            )
        except Exception as exc:  # noqa: BLE001
            self.runtime.status = "error"
            self.runtime.last_error = str(exc)
            manager_logger.exception("[%s] failed to listen on %s:%s", self.process_id, self.listen_host, self.listen_port)
            raise

        sockets = self.server.sockets or []
        if sockets:
            self.listen_port = int(sockets[0].getsockname()[1])
            self.runtime.listen_port = self.listen_port
        self.runtime.status = "running"
        manager_logger.info("[%s] listening on %s:%s", self.process_id, self.listen_host, self.listen_port)

    async def stop(self) -> None:
        self.runtime.status = "stopping"
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        self.runtime.status = "stopped"
        manager_logger.info("[%s] stopped", self.process_id)

    def snapshot(self) -> ProcessRuntime:
        return self.runtime.model_copy(deep=True)

    def _choose_targets(self) -> List[ResolvedTarget]:
        targets = self.target_provider()
        if not targets:
            return []
        if self.strategy == "failover":
            return targets
        index = self._rr_index % len(targets)
        self._rr_index += 1
        return targets[index:] + targets[:index]

    async def _handle_client(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        client_addr = client_writer.get_extra_info("peername")
        self.runtime.connection_count += 1
        self.runtime.active_connections += 1
        target_reader: Optional[asyncio.StreamReader] = None
        target_writer: Optional[asyncio.StreamWriter] = None
        chosen_target: Optional[ResolvedTarget] = None
        try:
            targets = self._choose_targets()
            if not targets:
                raise RuntimeError("no resolved targets available")

            last_error: Optional[Exception] = None
            for target in targets:
                try:
                    chosen_target = target
                    target_reader, target_writer = await asyncio.open_connection(target.host, target.port)
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    manager_logger.warning(
                        "[%s] target connect failed %s:%s for client %s: %s",
                        self.process_id,
                        target.host,
                        target.port,
                        client_addr,
                        exc,
                    )
                    target_reader = None
                    target_writer = None

            if target_reader is None or target_writer is None or chosen_target is None:
                raise RuntimeError(f"all targets failed; last_error={last_error}")

            manager_logger.info(
                "[%s] client %s -> target %s:%s",
                self.process_id,
                client_addr,
                chosen_target.host,
                chosen_target.port,
            )

            client_to_target = asyncio.create_task(self._pipe(client_reader, target_writer, "in"))
            target_to_client = asyncio.create_task(self._pipe(target_reader, client_writer, "out"))
            done, pending = await asyncio.wait(
                [client_to_target, target_to_client],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)
        except Exception as exc:  # noqa: BLE001
            self.runtime.last_error = str(exc)
            manager_logger.exception("[%s] connection error for %s: %s", self.process_id, client_addr, exc)
        finally:
            self.runtime.active_connections = max(0, self.runtime.active_connections - 1)
            for writer in [client_writer, target_writer]:
                if writer is not None:
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except Exception:
                        pass

    async def _pipe(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        direction: str,
    ) -> None:
        try:
            while True:
                data = await reader.read(BUFFER_SIZE)
                if not data:
                    break
                if direction == "in":
                    self.runtime.bytes_in += len(data)
                else:
                    self.runtime.bytes_out += len(data)
                writer.write(data)
                await writer.drain()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.runtime.last_error = str(exc)
            manager_logger.debug("[%s] pipe %s ended: %s", self.process_id, direction, exc)
        finally:
            try:
                writer.close()
            except Exception:
                pass


class ForwardingGroup:
    def __init__(
        self,
        config: GroupConfig,
        manager_public_host: str,
        target_resolver: Callable[[GroupConfig], List[ResolvedTarget]],
        previous_runtime: Optional[GroupRuntime] = None,
    ):
        self.config = config
        self.manager_public_host = manager_public_host
        self.target_resolver = target_resolver
        self.previous_runtime = previous_runtime
        self.processes: List[TunnelProcess] = []

    async def start(self) -> None:
        if not self.config.enabled:
            manager_logger.info("group %s is disabled", self.config.name)
            return
        public_host = self.config.public_host or self.manager_public_host
        ports = self._select_ports()
        self.processes = []
        for index in range(self.config.process_count):
            process_id = f"{self.config.name}-{index + 1}"
            process = TunnelProcess(
                process_id=process_id,
                group_name=self.config.name,
                listen_host=self.config.listen_host,
                public_host=public_host,
                listen_port=ports[index],
                target_provider=lambda cfg=self.config: self.target_resolver(cfg),
                strategy=self.config.strategy.value if hasattr(self.config.strategy, "value") else str(self.config.strategy),
            )
            await process.start()
            self.processes.append(process)
        manager_logger.info("group %s started with %s processes", self.config.name, len(self.processes))

    async def stop(self) -> None:
        for process in self.processes:
            await process.stop()
        self.processes = []
        manager_logger.info("group %s stopped", self.config.name)

    def snapshot(self) -> GroupRuntime:
        processes = [process.snapshot() for process in self.processes]
        if not self.config.enabled:
            status = "disabled"
        elif any(p.status == "running" for p in processes):
            status = "running"
        elif any(p.status == "error" for p in processes):
            status = "error"
        else:
            status = "stopped"
        return GroupRuntime(name=self.config.name, status=status, processes=processes)

    def inbounds(self) -> List[dict]:
        return [
            {
                "process": process.process_id,
                "host": process.public_host,
                "port": process.listen_port,
                "status": process.runtime.status,
            }
            for process in self.processes
        ]

    def _select_ports(self) -> List[int]:
        if self.config.port_mode == "fixed":
            if len(self.config.fixed_ports) != self.config.process_count:
                raise ValueError(f"group {self.config.name}: fixed_ports count must equal process_count")
            return list(self.config.fixed_ports)

        previous_ports = self._previous_ports_by_process()
        ports: List[int] = []
        used = set()
        for index in range(self.config.process_count):
            process_id = f"{self.config.name}-{index + 1}"
            previous_port = previous_ports.get(process_id)
            if previous_port and previous_port not in used and is_port_available(self.config.listen_host, previous_port):
                ports.append(previous_port)
                used.add(previous_port)
            else:
                port = allocate_random_port(self.config.listen_host)
                while port in used:
                    port = allocate_random_port(self.config.listen_host)
                ports.append(port)
                used.add(port)
        return ports

    def _previous_ports_by_process(self) -> Dict[str, int]:
        if self.previous_runtime is None:
            return {}
        return {process.process_id: process.listen_port for process in self.previous_runtime.processes}


# =============================================================================
# Doctor manager core
# =============================================================================


class DoctorManager:
    def __init__(self, storage: ConfigStorage):
        self.storage = storage
        self.config: DoctorConfig = storage.load_config()
        self.runtime: RuntimeState = storage.load_runtime()
        self.groups: Dict[str, ForwardingGroup] = {}
        self.remote_sync_tasks: List[asyncio.Task] = []
        self._lock: Optional[asyncio.Lock] = None
        self.started_at: Optional[str] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @property
    def public_host(self) -> str:
        return self.config.manager.public_host or self.config.manager.host

    async def start(self) -> None:
        async with self._get_lock():
            manager_logger.info("starting manager %s", self.config.manager.name)
            await self._start_groups_locked()
            self._start_remote_sync_tasks_locked()
            self.started_at = now_utc_iso()
            self.persist_runtime()

    async def stop(self) -> None:
        async with self._get_lock():
            manager_logger.info("stopping manager %s", self.config.manager.name)
            for task in self.remote_sync_tasks:
                task.cancel()
            await asyncio.gather(*self.remote_sync_tasks, return_exceptions=True)
            self.remote_sync_tasks = []
            for group in list(self.groups.values()):
                await group.stop()
            self.groups = {}
            self.persist_runtime()

    async def reload_config(self) -> None:
        async with self._get_lock():
            manager_logger.info("reloading config")
            for task in self.remote_sync_tasks:
                task.cancel()
            await asyncio.gather(*self.remote_sync_tasks, return_exceptions=True)
            self.remote_sync_tasks = []
            for group in list(self.groups.values()):
                await group.stop()
            self.groups = {}
            self.config = self.storage.load_config()
            self.runtime = self.storage.load_runtime()
            await self._start_groups_locked()
            self._start_remote_sync_tasks_locked()
            self.persist_runtime()

    async def sync_now(self) -> None:
        async with self._get_lock():
            for dependency in self.config.remote_dependencies:
                await self._sync_dependency_locked(dependency.name)
            await self._restart_groups_using_remote_targets_locked()
            self.persist_runtime()

    def persist_runtime(self) -> None:
        for name, group in self.groups.items():
            self.runtime.groups[name] = group.snapshot()
        self.storage.save_runtime(self.runtime)

    def status(self) -> dict:
        self.persist_runtime()
        return {
            "manager": self.config.manager.name,
            "status": "running",
            "started_at": self.started_at,
            "host": self.config.manager.host,
            "port": self.config.manager.port,
            "public_host": self.public_host,
            "config_path": self.storage.config_path,
            "runtime_path": self.storage.runtime_path,
            "groups_total": len(self.config.groups),
            "processes_total": sum(len(group.processes) for group in self.groups.values()),
            "remote_dependencies_total": len(self.config.remote_dependencies),
            "groups": [group.snapshot().model_dump(mode="json") for group in self.groups.values()],
            "remote_dependencies": [dep.model_dump(mode="json") for dep in self.runtime.remote_dependencies.values()],
        }

    def config_dump(self) -> dict:
        return self.config.model_dump(mode="json")

    def group_status(self, name: str) -> Optional[dict]:
        group = self.groups.get(name)
        if group is None:
            config = self.config.group_by_name(name)
            if config is None:
                return None
            return GroupRuntime(name=name, status="configured_not_running", processes=[]).model_dump(mode="json")
        self.persist_runtime()
        return group.snapshot().model_dump(mode="json")

    def groups_status(self) -> List[dict]:
        self.persist_runtime()
        configured = {group.name for group in self.config.groups}
        result = [group.snapshot().model_dump(mode="json") for group in self.groups.values()]
        running_names = {item["name"] for item in result}
        for name in sorted(configured - running_names):
            result.append(GroupRuntime(name=name, status="configured_not_running", processes=[]).model_dump(mode="json"))
        return result

    def group_inbounds(self, name: str) -> Optional[dict]:
        group = self.groups.get(name)
        if group is None:
            if self.config.group_by_name(name) is None:
                return None
            return {"manager": self.config.manager.name, "group": name, "inbounds": []}
        return {
            "manager": self.config.manager.name,
            "group": name,
            "inbounds": group.inbounds(),
        }

    async def upsert_group_config(self, group_config: GroupConfig) -> dict:
        async with self._get_lock():
            self.config.groups = [g for g in self.config.groups if g.name != group_config.name]
            self.config.groups.append(group_config)
            self.storage.save_config(self.config)
            old_group = self.groups.pop(group_config.name, None)
            if old_group is not None:
                await old_group.stop()
            previous_runtime = self.runtime.groups.get(group_config.name)
            new_group = ForwardingGroup(group_config, self.public_host, self.resolve_targets, previous_runtime)
            await new_group.start()
            self.groups[group_config.name] = new_group
            self.persist_runtime()
            return self.group_status(group_config.name) or {}

    async def delete_group_config(self, name: str) -> bool:
        async with self._get_lock():
            if self.config.group_by_name(name) is None:
                return False
            self.config.groups = [g for g in self.config.groups if g.name != name]
            self.storage.save_config(self.config)
            old_group = self.groups.pop(name, None)
            if old_group is not None:
                await old_group.stop()
            self.runtime.groups.pop(name, None)
            self.persist_runtime()
            return True

    async def restart_group(self, name: str) -> bool:
        async with self._get_lock():
            group_config = self.config.group_by_name(name)
            if group_config is None:
                return False
            old_group = self.groups.pop(name, None)
            if old_group is not None:
                await old_group.stop()
            previous_runtime = self.runtime.groups.get(name)
            new_group = ForwardingGroup(group_config, self.public_host, self.resolve_targets, previous_runtime)
            await new_group.start()
            self.groups[name] = new_group
            self.persist_runtime()
            return True

    async def _start_groups_locked(self) -> None:
        for group_config in self.config.groups:
            previous_runtime = self.runtime.groups.get(group_config.name)
            group = ForwardingGroup(group_config, self.public_host, self.resolve_targets, previous_runtime)
            await group.start()
            self.groups[group_config.name] = group

    def _start_remote_sync_tasks_locked(self) -> None:
        for dependency in self.config.remote_dependencies:
            task = asyncio.create_task(self._remote_sync_loop(dependency.name))
            self.remote_sync_tasks.append(task)

    async def _remote_sync_loop(self, dependency_name: str) -> None:
        while True:
            dependency = self.config.dependency_by_name(dependency_name)
            if dependency is None:
                return
            try:
                async with self._get_lock():
                    changed = await self._sync_dependency_locked(dependency_name)
                    if changed:
                        await self._restart_groups_using_dependency_locked(dependency_name)
                    self.persist_runtime()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                manager_logger.exception("dependency sync loop failed for %s: %s", dependency_name, exc)
            await asyncio.sleep(dependency.sync_interval_seconds)

    async def _sync_dependency_locked(self, dependency_name: str) -> bool:
        dependency = self.config.dependency_by_name(dependency_name)
        if dependency is None:
            raise KeyError(f"unknown dependency: {dependency_name}")

        url = dependency.manager_url.rstrip("/") + f"/groups/{dependency.group_name}/inbounds"
        headers = {}
        if dependency.token:
            headers["Authorization"] = f"Bearer {dependency.token}"

        previous = self.runtime.remote_dependencies.get(dependency.name)
        previous_inbounds = previous.inbounds if previous else []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
            inbounds = payload.get("inbounds", [])
            self.runtime.remote_dependencies[dependency.name] = RemoteDependencyRuntime(
                name=dependency.name,
                manager_url=dependency.manager_url,
                group_name=dependency.group_name,
                status="ok",
                last_error=None,
                last_sync_at=now_utc_iso(),
                inbounds=inbounds,
            )
            changed = previous_inbounds != inbounds
            if changed:
                manager_logger.info("dependency %s changed: %s", dependency.name, inbounds)
            return changed
        except Exception as exc:  # noqa: BLE001
            self.runtime.remote_dependencies[dependency.name] = RemoteDependencyRuntime(
                name=dependency.name,
                manager_url=dependency.manager_url,
                group_name=dependency.group_name,
                status="error",
                last_error=str(exc),
                last_sync_at=now_utc_iso(),
                inbounds=previous_inbounds,
            )
            manager_logger.warning("dependency %s sync failed: %s", dependency.name, exc)
            return False

    async def _restart_groups_using_remote_targets_locked(self) -> None:
        dependency_names = {dependency.name for dependency in self.config.remote_dependencies}
        for dependency_name in dependency_names:
            await self._restart_groups_using_dependency_locked(dependency_name)

    async def _restart_groups_using_dependency_locked(self, dependency_name: str) -> None:
        affected = []
        for group_config in self.config.groups:
            for target in group_config.targets:
                if isinstance(target, RemoteGroupTarget) and target.dependency == dependency_name:
                    affected.append(group_config.name)
                    break
        for group_name in affected:
            manager_logger.info("restarting group %s because dependency %s changed", group_name, dependency_name)
            old_group = self.groups.pop(group_name, None)
            if old_group is not None:
                await old_group.stop()
            group_config = self.config.group_by_name(group_name)
            if group_config is None:
                continue
            previous_runtime = self.runtime.groups.get(group_name)
            new_group = ForwardingGroup(group_config, self.public_host, self.resolve_targets, previous_runtime)
            await new_group.start()
            self.groups[group_name] = new_group

    def resolve_targets(self, group_config: GroupConfig) -> List[ResolvedTarget]:
        resolved: List[ResolvedTarget] = []
        for target in group_config.targets:
            if isinstance(target, StaticTarget):
                resolved.append(ResolvedTarget(host=target.host, port=target.port))
            elif isinstance(target, RemoteGroupTarget):
                runtime = self.runtime.remote_dependencies.get(target.dependency)
                if runtime:
                    for inbound in runtime.inbounds:
                        if inbound.get("status") == "running":
                            resolved.append(ResolvedTarget(host=str(inbound["host"]), port=int(inbound["port"])))
        return resolved


# =============================================================================
# Embedded manager service
# =============================================================================


class EmbeddedManagerService:
    def __init__(self) -> None:
        self.manager: Optional[DoctorManager] = None
        self.config_path: Optional[str] = None
        self.env_path: Optional[str] = None
        self.runtime_path: Optional[str] = None
        self.last_error: Optional[str] = None
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def is_running(self) -> bool:
        return self.manager is not None

    def api_token(self) -> Optional[str]:
        if not self.manager:
            return None
        return self.manager.config.manager.api_token

    def active_summary(self) -> dict:
        return {
            "running": self.is_running(),
            "config_path": self.config_path,
            "env_path": self.env_path,
            "runtime_path": self.runtime_path,
            "last_error": self.last_error,
            "manager_name": self.manager.config.manager.name if self.manager else None,
        }

    def _resolve_paths(
        self,
        config_path: Optional[str],
        env_path: Optional[str],
        runtime_path: Optional[str],
    ) -> Tuple[Path, Path, Optional[Path]]:
        env_abs: Optional[Path] = None
        env_values: Dict[str, Optional[str]] = {}
        if env_path:
            env_abs = safe_join(env_path)
            if env_abs.exists():
                env_values = dict(dotenv_values(env_abs))

        cfg_value = config_path or env_values.get("DOCTOR_DEV_CONFIG_PATH") or "./configs/doctor_dev.json"
        rt_value = runtime_path or env_values.get("DOCTOR_DEV_RUNTIME_PATH")

        cfg_abs = safe_join(str(cfg_value))
        if rt_value:
            rt_abs = safe_join(str(rt_value))
        else:
            rt_abs = cfg_abs.with_suffix(".runtime.json")
        return cfg_abs, rt_abs, env_abs

    async def start(
        self,
        config_path: Optional[str] = None,
        env_path: Optional[str] = None,
        runtime_path: Optional[str] = None,
    ) -> dict:
        async with self._get_lock():
            await self.stop_inside_lock()
            cfg_abs, rt_abs, env_abs = self._resolve_paths(config_path, env_path, runtime_path)
            if not cfg_abs.exists():
                raise HTTPException(status_code=404, detail=f"config file not found: {to_relative(cfg_abs)}")
            # Apply selected env file to this process before manager loads, but only for DOCTOR_DEV_* values.
            if env_abs and env_abs.exists():
                for key, value in dotenv_values(env_abs).items():
                    if key and value is not None and key.startswith("DOCTOR_DEV_"):
                        os.environ[key] = value

            storage = ConfigStorage(str(cfg_abs), str(rt_abs))
            manager = DoctorManager(storage)
            setup_logging(manager.config.manager.log_file)
            await manager.start()
            self.manager = manager
            self.config_path = to_relative(cfg_abs)
            self.runtime_path = to_relative(rt_abs)
            self.env_path = to_relative(env_abs) if env_abs else None
            self.last_error = None
            logger.info("embedded manager started with config %s", self.config_path)
            return self.status()

    async def stop_inside_lock(self) -> None:
        if self.manager is not None:
            await self.manager.stop()
            self.manager = None

    async def stop(self) -> dict:
        async with self._get_lock():
            await self.stop_inside_lock()
            logger.info("embedded manager stopped")
            return self.status()

    async def reload(self) -> dict:
        if self.manager is None:
            raise HTTPException(status_code=409, detail="manager is not running")
        await self.manager.reload_config()
        return self.status()

    async def sync(self) -> dict:
        if self.manager is None:
            raise HTTPException(status_code=409, detail="manager is not running")
        await self.manager.sync_now()
        return self.status()

    async def restart_group(self, name: str) -> dict:
        if self.manager is None:
            raise HTTPException(status_code=409, detail="manager is not running")
        ok = await self.manager.restart_group(name)
        if not ok:
            raise HTTPException(status_code=404, detail="group not found")
        return self.manager.group_status(name) or {}

    def status(self) -> dict:
        base = self.active_summary()
        if self.manager is not None:
            base["manager_status"] = self.manager.status()
        return base


service = EmbeddedManagerService()

# =============================================================================
# Auth helpers
# =============================================================================


def admin_username() -> str:
    return os.getenv("ADMIN_USERNAME", "admin")


def admin_password() -> str:
    return os.getenv("ADMIN_PASSWORD", "admin")


def app_secret() -> bytes:
    secret = os.getenv("APP_SECRET")
    if not secret:
        # Per-run fallback. Usable for local testing; sessions reset after restart.
        secret = "development-only-" + secrets.token_urlsafe(48)
        os.environ["APP_SECRET"] = secret
    return secret.encode("utf-8")


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def sign_payload(payload: dict) -> str:
    body = _b64_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(app_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_payload(token: str) -> Optional[dict]:
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(app_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64_decode(body).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def make_session(username: str) -> str:
    return sign_payload({"sub": username, "exp": int(time.time()) + SESSION_TTL_SECONDS, "nonce": secrets.token_hex(12)})


async def require_admin(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE)
    payload = verify_payload(token or "")
    if not payload:
        raise HTTPException(status_code=401, detail="login required")
    return str(payload.get("sub"))


async def optional_admin(request: Request) -> Optional[str]:
    token = request.cookies.get(SESSION_COOKIE)
    payload = verify_payload(token or "")
    if not payload:
        return None
    return str(payload.get("sub"))


def check_manager_token(authorization: Optional[str]) -> None:
    token = service.api_token()
    if not token:
        return
    if authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="invalid or missing token")


def require_active_manager() -> DoctorManager:
    if service.manager is None:
        raise HTTPException(status_code=409, detail="no active manager; start a config from the admin panel first")
    return service.manager


# =============================================================================
# File scan helpers
# =============================================================================


def should_skip_scan_dir(path: Path) -> bool:
    return path.name in EXCLUDED_SCAN_DIRS or path.name.startswith(".") and path.name not in {".env"}


def list_candidate_files(kind: str = "all") -> List[dict]:
    suffixes: Tuple[str, ...]
    if kind == "config":
        suffixes = (".json",)
    elif kind == "env":
        suffixes = (".env",)
    elif kind == "runtime":
        suffixes = (".runtime.json",)
    else:
        suffixes = (".json", ".env", ".txt", ".log", ".sh")

    results: List[dict] = []
    for current_dir, subdirs, files in os.walk(ROOT_DIR):
        current_path = Path(current_dir)
        subdirs[:] = [d for d in subdirs if not should_skip_scan_dir(current_path / d)]
        for filename in files:
            path = current_path / filename
            rel = to_relative(path)
            if kind == "config":
                if not filename.endswith(".json") or filename.endswith(".runtime.json"):
                    continue
            elif kind == "runtime":
                if not filename.endswith(".runtime.json"):
                    continue
            elif kind == "env":
                if not filename.endswith(".env"):
                    continue
            elif not filename.endswith(suffixes):
                continue
            try:
                stat = path.stat()
                results.append(
                    {
                        "path": rel,
                        "name": filename,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    }
                )
            except OSError:
                continue
    results.sort(key=lambda item: item["path"])
    return results


def example_config() -> str:
    data = {
        "manager": {
            "name": "my-node",
            "host": "0.0.0.0",
            "port": 17002,
            "public_host": "YOUR_PUBLIC_HOST_OR_IP",
            "api_token": secrets.token_urlsafe(24),
            "log_file": "./logs/my-node.log",
        },
        "groups": [
            {
                "name": "my-static-forward",
                "process_count": 1,
                "listen_host": "0.0.0.0",
                "port_mode": "fixed",
                "fixed_ports": [10080],
                "targets": [{"type": "static", "host": "127.0.0.1", "port": 3000}],
                "strategy": "round_robin",
                "enabled": True,
            }
        ],
        "remote_dependencies": [],
    }
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def example_env(config_path: str = "./configs/doctor_dev.json") -> str:
    runtime_path = str(Path(config_path).with_suffix(".runtime.json"))
    return (
        f"DOCTOR_DEV_CONFIG_PATH={config_path}\n"
        f"DOCTOR_DEV_RUNTIME_PATH={runtime_path}\n"
        "DOCTOR_DEV_UVICORN_LOG_LEVEL=info\n"
    )


# =============================================================================
# HTML front-end: SPA with HTML/CSS/JS inside this file
# =============================================================================


FRONTEND_HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>a project to see every where</title>
  <style>
    :root {
      --bg: #080b12;
      --panel: rgba(18, 24, 38, 0.92);
      --panel-2: rgba(28, 36, 55, 0.88);
      --text: #eef4ff;
      --muted: #98a7bd;
      --line: rgba(255,255,255,0.09);
      --accent: #7c5cff;
      --accent-2: #2dd4bf;
      --danger: #fb7185;
      --warning: #fbbf24;
      --ok: #34d399;
      --shadow: 0 18px 70px rgba(0, 0, 0, .45);
      --radius: 20px;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(circle at 12% 12%, rgba(124,92,255,.32), transparent 34%),
        radial-gradient(circle at 88% 4%, rgba(45,212,191,.23), transparent 32%),
        radial-gradient(circle at 60% 100%, rgba(251,113,133,.12), transparent 28%),
        var(--bg);
    }
    a { color: inherit; }
    .hidden { display: none !important; }
    .shell { display: grid; grid-template-columns: 290px 1fr; min-height: 100vh; }
    .sidebar {
      border-right: 1px solid var(--line);
      background: rgba(5, 8, 15, .72);
      backdrop-filter: blur(18px);
      padding: 24px;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
    }
    .brand { display: flex; gap: 14px; align-items: center; margin-bottom: 28px; }
    .logo {
      width: 45px; height: 45px; border-radius: 15px;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      display: grid; place-items: center; font-weight: 900; box-shadow: var(--shadow);
    }
    .brand h1 { font-size: 18px; line-height: 1.15; margin: 0; }
    .brand p { margin: 3px 0 0; color: var(--muted); font-size: 12px; }
    .nav button {
      width: 100%; border: 1px solid transparent; color: var(--muted);
      background: transparent; text-align: left; padding: 13px 14px; border-radius: 14px;
      cursor: pointer; font-weight: 700; margin-bottom: 6px;
    }
    .nav button.active, .nav button:hover {
      color: var(--text); border-color: var(--line); background: rgba(255,255,255,.06);
    }
    .side-card { border: 1px solid var(--line); background: var(--panel); border-radius: var(--radius); padding: 16px; margin-top: 18px; }
    .side-card .small { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
    .main { padding: 28px; overflow: auto; }
    .topbar { display: flex; justify-content: space-between; gap: 16px; align-items: center; margin-bottom: 22px; }
    .topbar h2 { margin: 0; font-size: 27px; }
    .topbar p { margin: 5px 0 0; color: var(--muted); }
    .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 18px; }
    .card {
      border: 1px solid var(--line); background: var(--panel); border-radius: var(--radius);
      box-shadow: var(--shadow); padding: 18px; overflow: hidden;
    }
    .span-12 { grid-column: span 12; }
    .span-8 { grid-column: span 8; }
    .span-6 { grid-column: span 6; }
    .span-4 { grid-column: span 4; }
    .card h3 { margin: 0 0 12px; font-size: 17px; }
    .muted { color: var(--muted); }
    .row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .between { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
    button, .btn {
      border: 1px solid var(--line); background: rgba(255,255,255,.08); color: var(--text);
      padding: 10px 13px; border-radius: 13px; font-weight: 800; cursor: pointer;
      transition: transform .12s ease, background .12s ease, border-color .12s ease;
    }
    button:hover, .btn:hover { transform: translateY(-1px); background: rgba(255,255,255,.12); }
    button.primary { background: linear-gradient(135deg, var(--accent), #4f46e5); border-color: transparent; }
    button.ok { background: rgba(52,211,153,.14); border-color: rgba(52,211,153,.34); color: #bbf7d0; }
    button.warn { background: rgba(251,191,36,.13); border-color: rgba(251,191,36,.32); color: #fde68a; }
    button.danger { background: rgba(251,113,133,.14); border-color: rgba(251,113,133,.34); color: #fecdd3; }
    input, select, textarea {
      width: 100%; color: var(--text); background: rgba(5,8,15,.67); border: 1px solid var(--line);
      border-radius: 13px; padding: 11px 12px; outline: none; font: inherit;
    }
    input:focus, select:focus, textarea:focus { border-color: rgba(124,92,255,.72); box-shadow: 0 0 0 4px rgba(124,92,255,.12); }
    textarea { min-height: 430px; resize: vertical; font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace; font-size: 13px; line-height: 1.48; tab-size: 2; }
    label { display: block; color: var(--muted); font-size: 12px; font-weight: 800; margin-bottom: 6px; }
    .field { margin-bottom: 12px; }
    .pill { display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 7px 10px; font-size: 12px; font-weight: 900; border: 1px solid var(--line); background: rgba(255,255,255,.06); }
    .pill.ok { color: #bbf7d0; border-color: rgba(52,211,153,.35); background: rgba(52,211,153,.12); }
    .pill.err { color: #fecdd3; border-color: rgba(251,113,133,.35); background: rgba(251,113,133,.12); }
    .pill.warn { color: #fde68a; border-color: rgba(251,191,36,.35); background: rgba(251,191,36,.12); }
    table { width: 100%; border-collapse: collapse; overflow: hidden; }
    th, td { border-bottom: 1px solid var(--line); padding: 11px 8px; text-align: left; vertical-align: top; font-size: 13px; }
    th { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }
    code, pre { font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace; }
    pre { white-space: pre-wrap; overflow: auto; color: #dbeafe; background: rgba(0,0,0,.28); border-radius: 14px; padding: 14px; border: 1px solid var(--line); max-height: 520px; }
    .toast { position: fixed; right: 22px; bottom: 22px; z-index: 50; display: grid; gap: 10px; }
    .toast div { background: rgba(15,23,42,.94); border: 1px solid var(--line); padding: 13px 15px; border-radius: 14px; box-shadow: var(--shadow); max-width: 440px; }
    .login-wrap { min-height: 100vh; display: grid; place-items: center; padding: 24px; }
    .login { width: min(450px, 100%); border: 1px solid var(--line); background: var(--panel); border-radius: 28px; padding: 28px; box-shadow: var(--shadow); }
    .login h1 { margin: 0 0 6px; font-size: 28px; }
    .login p { margin: 0 0 22px; color: var(--muted); }
    .metric { font-size: 30px; font-weight: 950; }
    .k { color: var(--muted); font-size: 12px; }
    .path { overflow-wrap: anywhere; font-family: "JetBrains Mono", Consolas, monospace; color: #bfdbfe; }
    @media (max-width: 960px) {
      .shell { grid-template-columns: 1fr; }
      .sidebar { position: relative; height: auto; }
      .span-8, .span-6, .span-4 { grid-column: span 12; }
      .topbar { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <div id="loginView" class="login-wrap hidden">
    <form class="login" id="loginForm">
      <div class="brand">
        <div class="logo">A</div>
        <div>
          <h1>a project to see every where</h1>
          <p>Standalone doctor-dev admin panel</p>
        </div>
      </div>
      <div class="field"><label>user_name</label><input id="loginUser" autocomplete="username" value="admin" /></div>
      <div class="field"><label>password</label><input id="loginPass" type="password" autocomplete="current-password" /></div>
      <button class="primary" style="width:100%">Login</button>
      <p style="margin-top:16px;font-size:12px">Set <code>ADMIN_USERNAME</code>, <code>ADMIN_PASSWORD</code>, and <code>APP_SECRET</code> before using this publicly.</p>
    </form>
  </div>

  <div id="appView" class="shell hidden">
    <aside class="sidebar">
      <div class="brand">
        <div class="logo">A</div>
        <div>
          <h1>a project to see every where</h1>
          <p id="versionText">standalone panel</p>
        </div>
      </div>
      <div class="nav">
        <button data-view="dashboard" class="active">Dashboard</button>
        <button data-view="configs">Config editor</button>
        <button data-view="envs">Env editor</button>
        <button data-view="groups">Groups</button>
        <button data-view="api">Raw API / logs</button>
      </div>
      <div class="side-card">
        <div class="between"><b>Status</b><span id="runPill" class="pill warn">checking</span></div>
        <p class="small">Active config</p>
        <div id="activeConfig" class="small path">-</div>
        <p class="small">Active env</p>
        <div id="activeEnv" class="small path">-</div>
      </div>
      <div class="side-card">
        <button id="refreshBtn" style="width:100%">Refresh all</button>
        <button id="logoutBtn" class="danger" style="width:100%; margin-top:8px">Logout</button>
      </div>
    </aside>

    <main class="main">
      <section id="view-dashboard">
        <div class="topbar">
          <div><h2>Dashboard</h2><p>Start a config, monitor forwarding processes, sync remote dependencies, and manage the running manager.</p></div>
          <div class="row"><button class="ok" id="syncBtn">Sync</button><button class="warn" id="reloadBtn">Reload</button><button class="danger" id="stopBtn">Stop</button></div>
        </div>
        <div class="grid">
          <div class="card span-4"><div class="k">Groups</div><div id="metricGroups" class="metric">-</div></div>
          <div class="card span-4"><div class="k">Processes</div><div id="metricProcesses" class="metric">-</div></div>
          <div class="card span-4"><div class="k">Remote dependencies</div><div id="metricDeps" class="metric">-</div></div>

          <div class="card span-12">
            <h3>Run selected config in the background</h3>
            <div class="grid">
              <div class="span-6"><label>Config file</label><select id="startConfigSelect"></select></div>
              <div class="span-6"><label>Env file optional</label><select id="startEnvSelect"></select></div>
              <div class="span-12 row"><button class="primary" id="startBtn">Start selected config</button><button id="createExampleBtn">Create example config</button></div>
            </div>
          </div>

          <div class="card span-12"><div class="between"><h3>Running groups</h3><button id="refreshGroupsBtn">Refresh groups</button></div><div id="groupsTable"></div></div>
          <div class="card span-12"><h3>Remote dependencies</h3><div id="depsTable"></div></div>
        </div>
      </section>

      <section id="view-configs" class="hidden">
        <div class="topbar"><div><h2>Config editor</h2><p>Load, validate, format, save, and run JSON configs.</p></div><div class="row"><button id="newConfigTemplateBtn">Template</button><button class="ok" id="formatConfigBtn">Format JSON</button><button class="primary" id="saveConfigBtn">Save config</button></div></div>
        <div class="grid">
          <div class="card span-12">
            <div class="grid">
              <div class="span-8"><label>Config path</label><select id="configFileSelect"></select></div>
              <div class="span-4"><label>New / custom path</label><input id="configCustomPath" placeholder="configs/my-node.json" /></div>
              <div class="span-12 row"><button id="loadConfigBtn">Load</button><button id="validateConfigBtn">Validate</button><button class="primary" id="runThisConfigBtn">Run this config</button><span id="configValidation" class="pill warn">not checked</span></div>
            </div>
          </div>
          <div class="card span-12"><textarea id="configEditor" spellcheck="false" placeholder="JSON config will appear here..."></textarea></div>
        </div>
      </section>

      <section id="view-envs" class="hidden">
        <div class="topbar"><div><h2>Env editor</h2><p>Edit .env files used when starting a config.</p></div><div class="row"><button id="newEnvTemplateBtn">Template</button><button class="primary" id="saveEnvBtn">Save env</button></div></div>
        <div class="grid">
          <div class="card span-12">
            <div class="grid">
              <div class="span-8"><label>Env path</label><select id="envFileSelect"></select></div>
              <div class="span-4"><label>New / custom path</label><input id="envCustomPath" placeholder="configs/my-node.env" /></div>
              <div class="span-12 row"><button id="loadEnvBtn">Load</button><button class="primary" id="runWithEnvBtn">Run config from this env</button></div>
            </div>
          </div>
          <div class="card span-12"><textarea id="envEditor" spellcheck="false" placeholder="DOCTOR_DEV_CONFIG_PATH=..."></textarea></div>
        </div>
      </section>

      <section id="view-groups" class="hidden">
        <div class="topbar"><div><h2>Groups</h2><p>Restart, inspect inbounds, delete groups, or add a quick group to the active config.</p></div><button id="refreshGroupsBtn2">Refresh</button></div>
        <div class="grid">
          <div class="card span-8"><h3>All groups</h3><div id="groupsTable2"></div></div>
          <div class="card span-4">
            <h3>Quick add / replace group</h3>
            <div class="field"><label>Name</label><input id="quickGroupName" placeholder="my-forward" /></div>
            <div class="field"><label>Listen port</label><input id="quickGroupPort" type="number" value="10080" /></div>
            <div class="field"><label>Target host</label><input id="quickTargetHost" value="127.0.0.1" /></div>
            <div class="field"><label>Target port</label><input id="quickTargetPort" type="number" value="3000" /></div>
            <button class="primary" id="quickSaveGroupBtn" style="width:100%">Save group to active config</button>
            <p class="muted" style="font-size:12px">For advanced remote_group targets, use the JSON config editor.</p>
          </div>
          <div class="card span-12"><h3>Selected group inbounds</h3><pre id="inboundsBox">Select a group...</pre></div>
        </div>
      </section>

      <section id="view-api" class="hidden">
        <div class="topbar"><div><h2>Raw API / logs</h2><p>Inspect exact status JSON and recent logs.</p></div><div class="row"><button id="refreshRawBtn">Refresh</button><button id="copyStatusBtn">Copy status</button></div></div>
        <div class="grid">
          <div class="card span-6"><h3>Status JSON</h3><pre id="rawStatus">-</pre></div>
          <div class="card span-6"><h3>Recent logs</h3><pre id="rawLogs">-</pre></div>
        </div>
      </section>
    </main>
  </div>
  <div class="toast" id="toast"></div>

<script>
const $ = (id) => document.getElementById(id);
let state = { info: null, status: null, files: {config: [], env: []}, currentView: 'dashboard' };

function toast(msg, bad=false) {
  const box = document.createElement('div');
  box.textContent = msg;
  box.style.borderColor = bad ? 'rgba(251,113,133,.55)' : 'rgba(45,212,191,.45)';
  $('toast').appendChild(box);
  setTimeout(() => box.remove(), 4200);
}

async function api(path, opts={}) {
  const res = await fetch(path, {
    credentials: 'same-origin',
    headers: {'Content-Type': 'application/json', ...(opts.headers || {})},
    ...opts
  });
  let data = null;
  const text = await res.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : (typeof data === 'string' ? data : res.statusText);
    throw new Error(detail);
  }
  return data;
}

function showLogin() { $('loginView').classList.remove('hidden'); $('appView').classList.add('hidden'); }
function showApp() { $('loginView').classList.add('hidden'); $('appView').classList.remove('hidden'); }

function setView(name) {
  state.currentView = name;
  document.querySelectorAll('.nav button').forEach(b => b.classList.toggle('active', b.dataset.view === name));
  ['dashboard','configs','envs','groups','api'].forEach(v => $('view-' + v).classList.toggle('hidden', v !== name));
}

document.querySelectorAll('.nav button').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));

function fillSelect(select, files, emptyText) {
  select.innerHTML = '';
  const empty = document.createElement('option');
  empty.value = '';
  empty.textContent = emptyText || 'None';
  select.appendChild(empty);
  files.forEach(f => {
    const opt = document.createElement('option');
    opt.value = f.path;
    opt.textContent = f.path;
    select.appendChild(opt);
  });
}

function badge(status) {
  if (status === 'running' || status === true || status === 'ok') return `<span class="pill ok">${status}</span>`;
  if (status === 'error' || status === false) return `<span class="pill err">${status}</span>`;
  return `<span class="pill warn">${status || 'unknown'}</span>`;
}

function renderStatus() {
  const s = state.status || {};
  const running = !!s.running;
  $('runPill').className = 'pill ' + (running ? 'ok' : 'warn');
  $('runPill').textContent = running ? 'running' : 'stopped';
  $('activeConfig').textContent = s.config_path || '-';
  $('activeEnv').textContent = s.env_path || '-';
  const ms = s.manager_status || {};
  $('metricGroups').textContent = ms.groups_total ?? '-';
  $('metricProcesses').textContent = ms.processes_total ?? '-';
  $('metricDeps').textContent = ms.remote_dependencies_total ?? '-';
  $('rawStatus').textContent = JSON.stringify(s, null, 2);
  renderGroups(ms.groups || []);
  renderDeps(ms.remote_dependencies || []);
}

function renderGroups(groups) {
  const html = groups.length ? `<table><thead><tr><th>Name</th><th>Status</th><th>Processes</th><th>Traffic</th><th>Actions</th></tr></thead><tbody>` +
    groups.map(g => {
      const bytesIn = (g.processes || []).reduce((a,p) => a + (p.bytes_in || 0), 0);
      const bytesOut = (g.processes || []).reduce((a,p) => a + (p.bytes_out || 0), 0);
      const active = (g.processes || []).reduce((a,p) => a + (p.active_connections || 0), 0);
      return `<tr><td><b>${escapeHtml(g.name)}</b></td><td>${badge(g.status)}</td><td>${(g.processes||[]).length}<br><span class="muted">active: ${active}</span></td><td><span class="muted">in:</span> ${bytesIn}<br><span class="muted">out:</span> ${bytesOut}</td><td class="row"><button onclick="restartGroup('${escapeAttr(g.name)}')">Restart</button><button onclick="showInbounds('${escapeAttr(g.name)}')">Inbounds</button><button class="danger" onclick="deleteGroup('${escapeAttr(g.name)}')">Delete</button></td></tr>`;
    }).join('') + `</tbody></table>` : '<p class="muted">No groups yet.</p>';
  $('groupsTable').innerHTML = html;
  $('groupsTable2').innerHTML = html;
}

function renderDeps(deps) {
  $('depsTable').innerHTML = deps.length ? `<table><thead><tr><th>Name</th><th>Status</th><th>Manager URL</th><th>Group</th><th>Last sync</th><th>Inbounds</th><th>Error</th></tr></thead><tbody>` +
    deps.map(d => `<tr><td><b>${escapeHtml(d.name)}</b></td><td>${badge(d.status)}</td><td class="path">${escapeHtml(d.manager_url || '')}</td><td>${escapeHtml(d.group_name || '')}</td><td>${escapeHtml(d.last_sync_at || '-')}</td><td>${(d.inbounds || []).length}</td><td class="muted">${escapeHtml(d.last_error || '')}</td></tr>`).join('') + `</tbody></table>` : '<p class="muted">No remote dependencies configured or synced yet.</p>';
}

function escapeHtml(s) { return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function escapeAttr(s) { return String(s).replace(/['\\]/g, '\\$&').replace(/"/g, '&quot;'); }

async function refreshFiles() {
  const all = await api('/api/files');
  state.files.config = all.configs;
  state.files.env = all.envs;
  fillSelect($('startConfigSelect'), state.files.config, 'Choose config...');
  fillSelect($('configFileSelect'), state.files.config, 'Choose config...');
  fillSelect($('startEnvSelect'), state.files.env, 'No env file');
  fillSelect($('envFileSelect'), state.files.env, 'Choose env...');
}

async function refreshStatus() {
  state.status = await api('/api/manager/status');
  renderStatus();
}

async function refreshLogs() {
  const logs = await api('/api/logs?limit=220');
  $('rawLogs').textContent = logs.lines.join('\n') || '-';
}

async function refreshAll() {
  try {
    state.info = await api('/api/info');
    $('versionText').textContent = state.info.version + ' / port ' + state.info.port;
    await refreshFiles();
    await refreshStatus();
    await refreshLogs();
  } catch (e) {
    if (String(e.message).includes('login required')) return showLogin();
    toast(e.message, true);
  }
}

$('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    await api('/api/auth/login', {method:'POST', body: JSON.stringify({user_name: $('loginUser').value, password: $('loginPass').value})});
    showApp();
    await refreshAll();
  } catch (err) { toast(err.message, true); }
});

$('logoutBtn').onclick = async () => { await api('/api/auth/logout', {method:'POST'}); showLogin(); };
$('refreshBtn').onclick = refreshAll;
$('refreshGroupsBtn').onclick = refreshStatus;
$('refreshGroupsBtn2').onclick = refreshStatus;
$('refreshRawBtn').onclick = async () => { await refreshStatus(); await refreshLogs(); };

$('startBtn').onclick = async () => {
  try {
    await api('/api/manager/start', {method:'POST', body: JSON.stringify({config_path: $('startConfigSelect').value || null, env_path: $('startEnvSelect').value || null})});
    toast('Manager started');
    await refreshAll();
  } catch (e) { toast(e.message, true); }
};
$('stopBtn').onclick = async () => { try { await api('/api/manager/stop', {method:'POST'}); toast('Manager stopped'); await refreshAll(); } catch(e){ toast(e.message,true); } };
$('reloadBtn').onclick = async () => { try { await api('/api/manager/reload', {method:'POST'}); toast('Reloaded'); await refreshAll(); } catch(e){ toast(e.message,true); } };
$('syncBtn').onclick = async () => { try { await api('/api/manager/sync', {method:'POST'}); toast('Synced remote dependencies'); await refreshAll(); } catch(e){ toast(e.message,true); } };

async function restartGroup(name) { try { await api('/api/manager/groups/' + encodeURIComponent(name) + '/restart', {method:'POST'}); toast('Group restarted: ' + name); await refreshAll(); } catch(e){ toast(e.message,true); } }
async function deleteGroup(name) { if(!confirm('Delete group from active config: ' + name + '?')) return; try { await api('/api/manager/groups/' + encodeURIComponent(name), {method:'DELETE'}); toast('Group deleted'); await refreshAll(); } catch(e){ toast(e.message,true); } }
async function showInbounds(name) { try { const data = await api('/api/manager/groups/' + encodeURIComponent(name) + '/inbounds'); $('inboundsBox').textContent = JSON.stringify(data, null, 2); setView('groups'); } catch(e){ toast(e.message,true); } }
window.restartGroup = restartGroup; window.showInbounds = showInbounds; window.deleteGroup = deleteGroup;

async function readFile(path) { return await api('/api/file?path=' + encodeURIComponent(path)); }
async function writeFile(path, content) { return await api('/api/file', {method:'PUT', body: JSON.stringify({path, content})}); }

$('loadConfigBtn').onclick = async () => {
  const path = $('configCustomPath').value || $('configFileSelect').value;
  if (!path) return toast('Choose a config file', true);
  try { const f = await readFile(path); $('configEditor').value = f.content; $('configCustomPath').value = path; $('configValidation').className='pill warn'; $('configValidation').textContent='loaded'; } catch(e){ toast(e.message,true); }
};
$('validateConfigBtn').onclick = async () => {
  try { const res = await api('/api/validate-config', {method:'POST', body: JSON.stringify({content: $('configEditor').value})}); $('configValidation').className='pill ok'; $('configValidation').textContent='valid: ' + res.manager; } catch(e){ $('configValidation').className='pill err'; $('configValidation').textContent='invalid'; toast(e.message,true); }
};
$('formatConfigBtn').onclick = async () => {
  try { const obj = JSON.parse($('configEditor').value); $('configEditor').value = JSON.stringify(obj, null, 2) + '\n'; } catch(e){ toast('Invalid JSON: ' + e.message, true); }
};
$('saveConfigBtn').onclick = async () => {
  const path = $('configCustomPath').value || $('configFileSelect').value;
  if (!path) return toast('Choose or type a config path', true);
  try { await api('/api/validate-config', {method:'POST', body: JSON.stringify({content: $('configEditor').value})}); await writeFile(path, $('configEditor').value); toast('Config saved'); await refreshFiles(); } catch(e){ toast(e.message,true); }
};
$('runThisConfigBtn').onclick = async () => {
  const path = $('configCustomPath').value || $('configFileSelect').value;
  if (!path) return toast('Choose or type a config path', true);
  try { await api('/api/manager/start', {method:'POST', body: JSON.stringify({config_path: path, env_path: $('startEnvSelect').value || null})}); toast('Running config: ' + path); await refreshAll(); setView('dashboard'); } catch(e){ toast(e.message,true); }
};
$('newConfigTemplateBtn').onclick = async () => { const t = await api('/api/templates/config'); $('configEditor').value = t.content; $('configCustomPath').value = 'configs/my-node.json'; };
$('createExampleBtn').onclick = async () => { setView('configs'); $('newConfigTemplateBtn').click(); };

$('loadEnvBtn').onclick = async () => {
  const path = $('envCustomPath').value || $('envFileSelect').value;
  if (!path) return toast('Choose an env file', true);
  try { const f = await readFile(path); $('envEditor').value = f.content; $('envCustomPath').value = path; } catch(e){ toast(e.message,true); }
};
$('saveEnvBtn').onclick = async () => {
  const path = $('envCustomPath').value || $('envFileSelect').value;
  if (!path) return toast('Choose or type an env path', true);
  try { await writeFile(path, $('envEditor').value); toast('Env saved'); await refreshFiles(); } catch(e){ toast(e.message,true); }
};
$('newEnvTemplateBtn').onclick = async () => { const t = await api('/api/templates/env'); $('envEditor').value = t.content; $('envCustomPath').value = 'configs/my-node.env'; };
$('runWithEnvBtn').onclick = async () => {
  const envPath = $('envCustomPath').value || $('envFileSelect').value;
  if (!envPath) return toast('Choose or type an env path', true);
  try { await api('/api/manager/start', {method:'POST', body: JSON.stringify({env_path: envPath})}); toast('Running from env: ' + envPath); await refreshAll(); setView('dashboard'); } catch(e){ toast(e.message,true); }
};

$('quickSaveGroupBtn').onclick = async () => {
  const group = {
    name: $('quickGroupName').value || 'my-forward',
    process_count: 1,
    listen_host: '0.0.0.0',
    port_mode: 'fixed',
    fixed_ports: [Number($('quickGroupPort').value || 10080)],
    targets: [{type:'static', host: $('quickTargetHost').value || '127.0.0.1', port: Number($('quickTargetPort').value || 3000)}],
    strategy: 'round_robin',
    enabled: true
  };
  try { await api('/api/manager/groups', {method:'POST', body: JSON.stringify(group)}); toast('Group saved and started'); await refreshAll(); } catch(e){ toast(e.message,true); }
};

$('copyStatusBtn').onclick = async () => { await navigator.clipboard.writeText($('rawStatus').textContent); toast('Status copied'); };

(async function boot(){
  try { await api('/api/auth/me'); showApp(); await refreshAll(); }
  catch { showLogin(); }
})();
</script>
</body>
</html>
'''


# =============================================================================
# FastAPI app + admin APIs
# =============================================================================


app = FastAPI(title=APP_TITLE, version=APP_VERSION)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("%s starting on port %s", APP_TITLE, os.getenv("PORT", DEFAULT_PORT))
    initial_config = getattr(app.state, "initial_config", None)
    initial_env = getattr(app.state, "initial_env", None)
    initial_runtime = getattr(app.state, "initial_runtime", None)
    if initial_config or initial_env:
        try:
            await service.start(initial_config, initial_env, initial_runtime)
        except Exception as exc:  # noqa: BLE001
            service.last_error = str(exc)
            logger.exception("failed to auto-start manager: %s", exc)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await service.stop()


@app.middleware("http")
async def add_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Doctor-Admin"] = APP_TITLE
    if service.manager:
        response.headers["X-Doctor-Dev-Manager"] = service.manager.config.manager.name
    return response


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(FRONTEND_HTML)


@app.get("/admin", response_class=HTMLResponse)
async def admin_page() -> HTMLResponse:
    return HTMLResponse(FRONTEND_HTML)


@app.post("/api/auth/login")
async def login(body: LoginBody) -> JSONResponse:
    if not hmac.compare_digest(body.user_name, admin_username()) or not hmac.compare_digest(body.password, admin_password()):
        raise HTTPException(status_code=401, detail="invalid user_name or password")
    response = JSONResponse({"ok": True, "user_name": body.user_name})
    response.set_cookie(
        SESSION_COOKIE,
        make_session(body.user_name),
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "0") == "1",
        max_age=SESSION_TTL_SECONDS,
    )
    return response


@app.post("/api/auth/logout")
async def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/api/auth/me")
async def me(user: str = Depends(require_admin)) -> dict:
    return {"ok": True, "user_name": user}


@app.get("/api/info")
async def app_info(user: str = Depends(require_admin)) -> dict:
    return {
        "title": APP_TITLE,
        "version": APP_VERSION,
        "root_dir": str(ROOT_DIR),
        "port": int(os.getenv("PORT", DEFAULT_PORT)),
        "default_admin_user": admin_username(),
        "active": service.active_summary(),
    }


@app.get("/api/files")
async def files(user: str = Depends(require_admin)) -> dict:
    return {
        "configs": list_candidate_files("config"),
        "envs": list_candidate_files("env"),
        "runtime": list_candidate_files("runtime"),
    }


@app.get("/api/file")
async def read_file(path: str = Query(...), user: str = Depends(require_admin)) -> dict:
    file_path = safe_join(path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="file is not utf-8 text") from exc
    return {"path": to_relative(file_path), "content": content, "size": file_path.stat().st_size}


@app.put("/api/file")
async def save_file(body: FileWriteBody, user: str = Depends(require_admin)) -> dict:
    file_path = safe_join(body.path)
    allowed = file_path.suffix in {".json", ".env", ".txt", ".log", ".sh"} or file_path.name.endswith(".runtime.json")
    if not allowed:
        raise HTTPException(status_code=400, detail="only .json, .env, .txt, .log, and .sh files can be edited from the panel")
    ensure_parent(file_path)
    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    tmp_path.write_text(body.content, encoding="utf-8")
    os.replace(tmp_path, file_path)
    return {"ok": True, "path": to_relative(file_path), "size": file_path.stat().st_size}


@app.post("/api/validate-config")
async def validate_config(body: ValidateJsonBody, user: str = Depends(require_admin)) -> dict:
    try:
        data = json.loads(body.content)
        config = DoctorConfig.model_validate(data)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=json.loads(exc.json())) from exc
    return {
        "ok": True,
        "manager": config.manager.name,
        "groups_total": len(config.groups),
        "remote_dependencies_total": len(config.remote_dependencies),
    }


@app.get("/api/templates/config")
async def template_config(user: str = Depends(require_admin)) -> dict:
    return {"content": example_config()}


@app.get("/api/templates/env")
async def template_env(user: str = Depends(require_admin)) -> dict:
    return {"content": example_env()}


@app.get("/api/logs")
async def logs(limit: int = Query(200, ge=1, le=1000), user: str = Depends(require_admin)) -> dict:
    return {"lines": memory_log_handler.tail(limit)}


@app.get("/api/manager/status")
async def admin_manager_status(user: str = Depends(require_admin)) -> dict:
    return service.status()


@app.post("/api/manager/start")
async def admin_manager_start(body: StartManagerBody, user: str = Depends(require_admin)) -> dict:
    return await service.start(body.config_path, body.env_path, body.runtime_path)


@app.post("/api/manager/stop")
async def admin_manager_stop(user: str = Depends(require_admin)) -> dict:
    return await service.stop()


@app.post("/api/manager/reload")
async def admin_manager_reload(user: str = Depends(require_admin)) -> dict:
    return await service.reload()


@app.post("/api/manager/sync")
async def admin_manager_sync(user: str = Depends(require_admin)) -> dict:
    return await service.sync()


@app.get("/api/manager/groups")
async def admin_groups(user: str = Depends(require_admin)) -> List[dict]:
    manager = require_active_manager()
    return manager.groups_status()


@app.post("/api/manager/groups")
async def admin_create_group(group_config: GroupConfig, user: str = Depends(require_admin)) -> dict:
    manager = require_active_manager()
    return await manager.upsert_group_config(group_config)


@app.put("/api/manager/groups/{group_name}")
async def admin_replace_group(group_name: str, group_config: GroupConfig, user: str = Depends(require_admin)) -> dict:
    if group_config.name != group_name:
        raise HTTPException(status_code=400, detail="path group name and body group name must match")
    manager = require_active_manager()
    return await manager.upsert_group_config(group_config)


@app.delete("/api/manager/groups/{group_name}")
async def admin_delete_group(group_name: str, user: str = Depends(require_admin)) -> dict:
    manager = require_active_manager()
    ok = await manager.delete_group_config(group_name)
    if not ok:
        raise HTTPException(status_code=404, detail="group not found")
    return {"status": "ok", "message": f"group {group_name} deleted"}


@app.post("/api/manager/groups/{group_name}/restart")
async def admin_restart_group(group_name: str, user: str = Depends(require_admin)) -> dict:
    return await service.restart_group(group_name)


@app.get("/api/manager/groups/{group_name}/inbounds")
async def admin_group_inbounds(group_name: str, user: str = Depends(require_admin)) -> dict:
    manager = require_active_manager()
    result = manager.group_inbounds(group_name)
    if result is None:
        raise HTTPException(status_code=404, detail="group not found")
    return result


# =============================================================================
# Compatibility API for remote doctor-dev nodes
# =============================================================================


@app.get("/health")
async def health() -> dict:
    if service.manager is None:
        return {"status": "ok", "admin": APP_TITLE, "manager": None, "running": False}
    return {"status": "ok", "admin": APP_TITLE, "manager": service.manager.config.manager.name, "running": True}


@app.get("/status")
async def status(authorization: Optional[str] = Header(default=None)) -> dict:
    check_manager_token(authorization)
    manager = require_active_manager()
    return manager.status()


@app.get("/config")
async def config(authorization: Optional[str] = Header(default=None)) -> dict:
    check_manager_token(authorization)
    manager = require_active_manager()
    return manager.config_dump()


@app.get("/groups")
async def groups(authorization: Optional[str] = Header(default=None)) -> List[dict]:
    check_manager_token(authorization)
    manager = require_active_manager()
    return manager.groups_status()


@app.post("/groups")
async def create_or_replace_group(group_config: GroupConfig, authorization: Optional[str] = Header(default=None)) -> dict:
    check_manager_token(authorization)
    manager = require_active_manager()
    return await manager.upsert_group_config(group_config)


@app.get("/groups/{group_name}")
async def group_status(group_name: str, authorization: Optional[str] = Header(default=None)) -> dict:
    check_manager_token(authorization)
    manager = require_active_manager()
    result = manager.group_status(group_name)
    if result is None:
        raise HTTPException(status_code=404, detail="group not found")
    return result


@app.get("/groups/{group_name}/inbounds")
async def group_inbounds(group_name: str, authorization: Optional[str] = Header(default=None)) -> dict:
    check_manager_token(authorization)
    manager = require_active_manager()
    result = manager.group_inbounds(group_name)
    if result is None:
        raise HTTPException(status_code=404, detail="group not found")
    return result


@app.post("/reload")
async def reload_config(authorization: Optional[str] = Header(default=None)) -> dict:
    check_manager_token(authorization)
    await service.reload()
    return {"status": "ok", "message": "config reloaded"}


@app.post("/sync")
async def sync_now(authorization: Optional[str] = Header(default=None)) -> dict:
    check_manager_token(authorization)
    await service.sync()
    return {"status": "ok", "message": "remote dependencies synced"}


@app.put("/groups/{group_name}")
async def replace_group(group_name: str, group_config: GroupConfig, authorization: Optional[str] = Header(default=None)) -> dict:
    check_manager_token(authorization)
    if group_config.name != group_name:
        raise HTTPException(status_code=400, detail="path group name and body group name must match")
    manager = require_active_manager()
    return await manager.upsert_group_config(group_config)


@app.delete("/groups/{group_name}")
async def delete_group(group_name: str, authorization: Optional[str] = Header(default=None)) -> dict:
    check_manager_token(authorization)
    manager = require_active_manager()
    ok = await manager.delete_group_config(group_name)
    if not ok:
        raise HTTPException(status_code=404, detail="group not found")
    return {"status": "ok", "message": f"group {group_name} deleted"}


@app.post("/groups/{group_name}/restart")
async def restart_group(group_name: str, authorization: Optional[str] = Header(default=None)) -> dict:
    check_manager_token(authorization)
    ok = await service.restart_group(group_name)
    return {"status": "ok", "message": f"group {group_name} restarted", "group": ok}


# =============================================================================
# CLI entrypoint
# =============================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone doctor-dev admin panel")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"), help="admin server bind host")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", str(DEFAULT_PORT))), help="admin server port")
    parser.add_argument("--config", default=os.getenv("START_CONFIG"), help="config file to auto-start")
    parser.add_argument("--env", default=os.getenv("START_ENV"), help="env file to auto-start")
    parser.add_argument("--runtime", default=os.getenv("START_RUNTIME"), help="runtime file path override")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    app.state.initial_config = args.config
    app.state.initial_env = args.env
    app.state.initial_runtime = args.runtime

    if admin_password() == "admin":
        logger.warning("ADMIN_PASSWORD is using the default value 'admin'. Change it before public use.")
    if not os.getenv("APP_SECRET"):
        logger.warning("APP_SECRET is not set. Sessions will reset on restart; set a long random APP_SECRET for production.")

    uvicorn.run(app, host=args.host, port=args.port, log_level=os.getenv("UVICORN_LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
