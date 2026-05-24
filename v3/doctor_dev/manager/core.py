from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from doctor_dev.config.storage import ConfigStorage
from doctor_dev.forwarding.group import ForwardingGroup
from doctor_dev.forwarding.tunnel import ResolvedTarget
from doctor_dev.models.config import DoctorConfig, GroupConfig, RemoteGroupTarget, StaticTarget
from doctor_dev.models.runtime import RemoteDependencyRuntime, RuntimeState

LOGGER = logging.getLogger(__name__)


class DoctorManager:
    def __init__(self, storage: ConfigStorage):
        self.storage = storage
        self.config: DoctorConfig = storage.load_config()
        self.runtime: RuntimeState = storage.load_runtime()
        self.groups: Dict[str, ForwardingGroup] = {}
        self.remote_sync_tasks: List[asyncio.Task] = []
        # Python 3.9 binds asyncio.Lock to the event loop that first uses it.
        # The manager object is created before uvicorn starts its runtime loop,
        # so create the lock lazily inside the running loop.
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @property
    def public_host(self) -> str:
        return self.config.manager.public_host or self.config.manager.host

    async def start(self) -> None:
        async with self._get_lock():
            LOGGER.info("starting manager %s", self.config.manager.name)
            await self._start_groups_locked()
            self._start_remote_sync_tasks_locked()
            self.persist_runtime()

    async def stop(self) -> None:
        async with self._get_lock():
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
            LOGGER.info("reloading config")
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
            "host": self.config.manager.host,
            "port": self.config.manager.port,
            "public_host": self.public_host,
            "groups_total": len(self.config.groups),
            "processes_total": sum(len(group.processes) for group in self.groups.values()),
            "remote_dependencies_total": len(self.config.remote_dependencies),
            "groups": [group.snapshot().model_dump(mode="json") for group in self.groups.values()],
            "remote_dependencies": [dep.model_dump(mode="json") for dep in self.runtime.remote_dependencies.values()],
        }

    def group_status(self, name: str) -> Optional[dict]:
        group = self.groups.get(name)
        if group is None:
            return None
        self.persist_runtime()
        return group.snapshot().model_dump(mode="json")

    def groups_status(self) -> List[dict]:
        self.persist_runtime()
        return [group.snapshot().model_dump(mode="json") for group in self.groups.values()]

    def group_inbounds(self, name: str) -> Optional[dict]:
        group = self.groups.get(name)
        if group is None:
            return None
        return {
            "manager": self.config.manager.name,
            "group": name,
            "inbounds": group.inbounds(),
        }


    def config_dump(self) -> dict:
        return self.config.model_dump(mode="json")

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
            exists = self.config.group_by_name(name) is not None
            if not exists:
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
                LOGGER.exception("dependency sync loop failed for %s: %s", dependency_name, exc)
            await asyncio.sleep(dependency.sync_interval_seconds)

    async def _sync_dependency_locked(self, dependency_name: str) -> bool:
        dependency = self.config.dependency_by_name(dependency_name)
        if dependency is None:
            raise KeyError(f"unknown dependency: {dependency_name}")

        url = dependency.manager_url.rstrip("/") + f"/groups/{dependency.group_name}/inbounds"
        headers = {}
        if dependency.token:
            headers["Authorization"] = f"Bearer {dependency.token}"

        now = datetime.now(timezone.utc).isoformat()
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
                last_sync_at=now,
                inbounds=inbounds,
            )
            changed = previous_inbounds != inbounds
            if changed:
                LOGGER.info("dependency %s changed: %s", dependency.name, inbounds)
            return changed
        except Exception as exc:  # noqa: BLE001
            self.runtime.remote_dependencies[dependency.name] = RemoteDependencyRuntime(
                name=dependency.name,
                manager_url=dependency.manager_url,
                group_name=dependency.group_name,
                status="error",
                last_error=str(exc),
                last_sync_at=now,
                inbounds=previous_inbounds,
            )
            LOGGER.warning("dependency %s sync failed: %s", dependency.name, exc)
            return False

    async def _restart_groups_using_remote_targets_locked(self) -> None:
        dependency_names = {dep.name for dep in self.config.remote_dependencies}
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
            LOGGER.info("restarting group %s because dependency %s changed", group_name, dependency_name)
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
                            resolved.append(
                                ResolvedTarget(host=str(inbound["host"]), port=int(inbound["port"]))
                            )
        return resolved
