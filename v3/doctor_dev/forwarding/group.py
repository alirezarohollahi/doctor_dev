from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Dict, List, Optional

from doctor_dev.forwarding.port_allocator import allocate_random_port, is_port_available
from doctor_dev.forwarding.tunnel import ResolvedTarget, TunnelProcess
from doctor_dev.models.config import GroupConfig
from doctor_dev.models.runtime import GroupRuntime, ProcessRuntime

LOGGER = logging.getLogger(__name__)


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
            LOGGER.info("group %s is disabled", self.config.name)
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
        LOGGER.info("group %s started with %s processes", self.config.name, len(self.processes))

    async def stop(self) -> None:
        for process in self.processes:
            await process.stop()
        self.processes = []
        LOGGER.info("group %s stopped", self.config.name)

    def snapshot(self) -> GroupRuntime:
        processes = [process.snapshot() for process in self.processes]
        status = "running" if any(p.status == "running" for p in processes) else "stopped"
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
                raise ValueError(
                    f"group {self.config.name}: fixed_ports count must equal process_count"
                )
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
        result: Dict[str, int] = {}
        for process in self.previous_runtime.processes:
            if isinstance(process, ProcessRuntime):
                result[process.process_id] = process.listen_port
        return result
