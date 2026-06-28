from __future__ import annotations

import asyncio
import logging
import random
import socket
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("doctor_dev_node.runtime")
BUFFER_SIZE = 65536


@dataclass
class Target:
    host: str
    port: int
    name: str = ""


class ForwarderRuntime:
    """Small asyncio TCP forwarding runtime used by node-side applied configs.

    It intentionally keeps the hot path simple: accept TCP, select a target,
    pipe bytes in both directions with a large buffer, and avoid any panel-side
    decisions during data-plane traffic.
    """

    def __init__(self) -> None:
        self.servers: dict[str, asyncio.AbstractServer] = {}
        self.listeners: list[dict[str, Any]] = []
        self.config: dict[str, Any] = {"version": 1, "cores": []}
        self._rr: dict[str, int] = {}
        self.connection_count = 0
        self.active_connections = 0
        self.bytes_in = 0
        self.bytes_out = 0
        self.last_error = ""
        self._lock = asyncio.Lock()

    async def stop(self) -> None:
        for key, server in list(self.servers.items()):
            try:
                server.close()
                await server.wait_closed()
                logger.info("listener stopped: %s", key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("failed to stop listener %s: %s", key, exc)
        self.servers.clear()
        self.listeners.clear()

    async def apply_config(self, config: dict[str, Any]) -> dict[str, Any]:
        logger.debug("runtime apply_config received: cores=%s raw=%r", len(config.get("cores") or []) if isinstance(config, dict) else 0, config)
        async with self._lock:
            await self.stop()
            self.config = config if isinstance(config, dict) else {"version": 1, "cores": []}
            self.last_error = ""
            cores = self.config.get("cores") if isinstance(self.config.get("cores"), list) else []
            started = 0
            for core in cores:
                if not isinstance(core, dict) or core.get("enabled") is False:
                    continue
                for inbound in core.get("inbounds", []) if isinstance(core.get("inbounds"), list) else []:
                    if not isinstance(inbound, dict) or inbound.get("enabled") is False:
                        continue
                    ports = self._ports_for(inbound)
                    for requested_port in ports:
                        bind_ip = str(inbound.get("bind_ip") or "0.0.0.0")
                        key = f"{core.get('id') or core.get('name')}::{inbound.get('name')}::{bind_ip}:{requested_port}"
                        try:
                            server = await asyncio.start_server(
                                lambda r, w, c=core, ib=inbound: self._handle_client(c, ib, r, w),
                                host=bind_ip,
                                port=requested_port,
                                backlog=4096,
                                reuse_address=True,
                                start_serving=True,
                            )
                            sock = server.sockets[0] if server.sockets else None
                            actual_port = int(sock.getsockname()[1]) if sock else requested_port
                            self.servers[key] = server
                            self.listeners.append({
                                "core_id": core.get("id"),
                                "core_name": core.get("name"),
                                "inbound_name": inbound.get("name"),
                                "bind_ip": bind_ip,
                                "requested_port": requested_port,
                                "port": actual_port,
                                "target_type": inbound.get("target_type"),
                                "target_balancer": inbound.get("target_balancer"),
                                "status": "listening",
                            })
                            started += 1
                            logger.info("listener started: %s:%s core=%s inbound=%s", bind_ip, actual_port, core.get("name"), inbound.get("name"))
                        except Exception as exc:  # noqa: BLE001
                            self.last_error = str(exc)
                            self.listeners.append({
                                "core_id": core.get("id"),
                                "core_name": core.get("name"),
                                "inbound_name": inbound.get("name"),
                                "bind_ip": bind_ip,
                                "requested_port": requested_port,
                                "status": "error",
                                "error": str(exc),
                            })
                            logger.warning("listener failed: %s:%s core=%s inbound=%s error=%s", bind_ip, requested_port, core.get("name"), inbound.get("name"), exc)
            return self.summary() | {"started_listeners": started}

    def _ports_for(self, inbound: dict[str, Any]) -> list[int]:
        if inbound.get("port_mode") == "random":
            count = max(1, min(int(inbound.get("random_count") or 1), 4096))
            return [0 for _ in range(count)]
        ports = inbound.get("fixed_ports") if isinstance(inbound.get("fixed_ports"), list) else []
        cleaned: list[int] = []
        for port in ports:
            try:
                port_num = int(port)
            except (TypeError, ValueError):
                continue
            if 1 <= port_num <= 65535 and port_num not in cleaned:
                cleaned.append(port_num)
        return cleaned or [int(inbound.get("target_port") or 0) or 0]

    def _balancers_for_core(self, core: dict[str, Any]) -> dict[str, dict[str, Any]]:
        result = {}
        for balancer in core.get("balancers", []) if isinstance(core.get("balancers"), list) else []:
            if isinstance(balancer, dict) and balancer.get("enabled") is not False:
                alias = str(balancer.get("alias") or "").strip()
                if alias:
                    result[alias] = balancer
        return result

    def _resolve_target(self, core: dict[str, Any], inbound: dict[str, Any]) -> Target | None:
        target_type = str(inbound.get("target_type") or "static")
        if target_type == "static":
            target = Target(str(inbound.get("target_host") or "127.0.0.1"), int(inbound.get("target_port") or 80), "static")
            logger.debug("resolved static target: core=%s inbound=%s target=%s:%s", core.get("name"), inbound.get("name"), target.host, target.port)
            return target
        alias = str(inbound.get("target_balancer") or "").strip()
        balancer = self._balancers_for_core(core).get(alias)
        if not balancer:
            logger.debug("target balancer not found: core=%s inbound=%s alias=%s", core.get("name"), inbound.get("name"), alias)
            return None
        endpoints = [e for e in (balancer.get("endpoints") or []) if isinstance(e, dict) and e.get("enabled") is not False]
        if not endpoints:
            logger.debug("target balancer has no enabled endpoints: core=%s inbound=%s alias=%s", core.get("name"), inbound.get("name"), alias)
            return None
        strategy = str(balancer.get("strategy") or "round_robin")
        endpoint: dict[str, Any]
        if strategy == "random":
            endpoint = random.choice(endpoints)
        elif strategy == "failover":
            endpoint = endpoints[0]
        else:
            idx = self._rr.get(alias, 0) % len(endpoints)
            self._rr[alias] = idx + 1
            endpoint = endpoints[idx]
        return self._target_from_endpoint(endpoint)

    def _target_from_endpoint(self, endpoint: dict[str, Any]) -> Target | None:
        etype = str(endpoint.get("type") or "static")
        if etype == "static":
            return Target(str(endpoint.get("host") or "127.0.0.1"), int(endpoint.get("port") or 80), "static-endpoint")
        # node_inbound endpoint: prefer explicit host/port saved in the endpoint, otherwise
        # resolve against the applied config by core_id + inbound_name.
        host = str(endpoint.get("host") or "").strip()
        try:
            port = int(endpoint.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        if host and port:
            return Target(host, port, "node-inbound-explicit")
        core_id = str(endpoint.get("core_id") or "")
        inbound_name = str(endpoint.get("inbound_name") or "")
        for core in self.config.get("cores", []) if isinstance(self.config.get("cores"), list) else []:
            if core_id and str(core.get("id")) != core_id:
                continue
            for inbound in core.get("inbounds", []) if isinstance(core.get("inbounds"), list) else []:
                if inbound_name and str(inbound.get("name")) != inbound_name:
                    continue
                ports = inbound.get("fixed_ports") or []
                if ports:
                    return Target(str(inbound.get("public_host") or inbound.get("bind_ip") or "127.0.0.1"), int(ports[0]), "node-inbound")
        return None

    async def _handle_client(self, core: dict[str, Any], inbound: dict[str, Any], client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
        self.connection_count += 1
        self.active_connections += 1
        peer = client_writer.get_extra_info("peername")
        target = self._resolve_target(core, inbound)
        if not target:
            self.last_error = f"No target for inbound {inbound.get('name')}"
            logger.warning("connection rejected: no target core=%s inbound=%s peer=%s", core.get("name"), inbound.get("name"), peer)
            client_writer.close()
            await client_writer.wait_closed()
            self.active_connections -= 1
            return
        try:
            self._set_nodelay(client_writer)
            target_reader, target_writer = await asyncio.open_connection(target.host, target.port)
            self._set_nodelay(target_writer)
            logger.debug("proxy connected peer=%s -> %s:%s inbound=%s", peer, target.host, target.port, inbound.get("name"))
            a = asyncio.create_task(self._pipe(client_reader, target_writer, "in"))
            b = asyncio.create_task(self._pipe(target_reader, client_writer, "out"))
            done, pending = await asyncio.wait({a, b}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            logger.debug("proxy connection failed peer=%s target=%s:%s error=%s", peer, target.host, target.port, exc)
        finally:
            for writer in (client_writer, locals().get("target_writer")):
                if writer:
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except Exception:
                        pass
            self.active_connections = max(0, self.active_connections - 1)

    async def _pipe(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, direction: str) -> None:
        while True:
            data = await reader.read(BUFFER_SIZE)
            if not data:
                break
            if direction == "in":
                self.bytes_in += len(data)
            else:
                self.bytes_out += len(data)
            writer.write(data)
            await writer.drain()

    def _set_nodelay(self, writer: asyncio.StreamWriter) -> None:
        sock = writer.get_extra_info("socket")
        if sock is not None:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass

    def summary(self) -> dict[str, Any]:
        return {
            "runtime_active": bool(self.servers),
            "listeners_total": len(self.listeners),
            "listeners": self.listeners,
            "active_connections": self.active_connections,
            "connection_count": self.connection_count,
            "bytes_in": self.bytes_in,
            "bytes_out": self.bytes_out,
            "last_error": self.last_error,
        }


runtime = ForwarderRuntime()
