from __future__ import annotations

import asyncio
import logging
import os
import random
import socket
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("doctor_dev_node.runtime")

# Large enough for high-throughput forwarding without making every connection
# allocate huge buffers. Can be tuned from node.env.
BUFFER_SIZE = int(os.getenv("DOCTOR_DEV_FORWARD_BUFFER_SIZE", str(256 * 1024)))
DRAIN_HIGH_WATER = int(os.getenv("DOCTOR_DEV_FORWARD_DRAIN_HIGH_WATER", str(1024 * 1024)))
CONNECT_TIMEOUT = float(os.getenv("DOCTOR_DEV_FORWARD_CONNECT_TIMEOUT", "5"))
SHUTDOWN_TIMEOUT = float(os.getenv("DOCTOR_DEV_FORWARD_SHUTDOWN_TIMEOUT", "3"))

LOCAL_TARGET_HOSTS = {"", "127.0.0.1", "localhost", "::1", "0.0.0.0", "[::1]"}


@dataclass(frozen=True)
class Target:
    host: str
    port: int
    name: str = ""

    @property
    def key(self) -> str:
        return f"{self.host}:{self.port}"


class ForwarderRuntime:
    """High-throughput TCP forwarding runtime used by node-side configs.

    The runtime is intentionally simple and fast: listen, resolve a target,
    connect, then pipe bytes in both directions. Control-plane work is kept out
    of the data-plane path.
    """

    def __init__(self) -> None:
        self.servers: dict[str, asyncio.AbstractServer] = {}
        self.listeners: list[dict[str, Any]] = []
        self.config: dict[str, Any] = {"version": 1, "cores": []}
        self._rr: dict[str, int] = {}
        self._target_active: dict[str, int] = {}
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
        self._rr.clear()
        self._target_active.clear()

    async def apply_config(self, config: dict[str, Any]) -> dict[str, Any]:
        logger.debug(
            "runtime apply_config received: cores=%s raw=%r",
            len(config.get("cores") or []) if isinstance(config, dict) else 0,
            config,
        )
        async with self._lock:
            proposed_config = config if isinstance(config, dict) else {"version": 1, "cores": []}
            validation_errors = self.validate_config(proposed_config)
            if validation_errors:
                self.last_error = validation_errors[0]
                logger.warning("runtime config rejected before reload: errors=%s", validation_errors)
                current = self.summary()
                current.update({
                    "ok": False,
                    "started_listeners": 0,
                    "listener_errors": len(validation_errors),
                    "errors": validation_errors,
                })
                return current

            await self.stop()
            self.config = proposed_config
            self.last_error = ""
            cores = self._ordered_cores(self.config.get("cores") if isinstance(self.config.get("cores"), list) else [])
            started = 0

            for core in cores:
                if not isinstance(core, dict) or core.get("enabled") is False:
                    continue
                dep_error = self._dependency_error(core, cores)
                if dep_error:
                    self.last_error = dep_error
                    self.listeners.append({
                        "core_id": core.get("id"),
                        "core_name": core.get("name"),
                        "status": "error",
                        "error": dep_error,
                    })
                    logger.warning("core skipped because dependency check failed: core=%s error=%s", core.get("name"), dep_error)
                    continue

                for inbound in core.get("inbounds", []) if isinstance(core.get("inbounds"), list) else []:
                    if not isinstance(inbound, dict) or inbound.get("enabled") is False:
                        continue
                    ports = self._ports_for(inbound)
                    for requested_port in ports:
                        bind_ip = str(inbound.get("bind_ip") or "0.0.0.0").strip() or "0.0.0.0"
                        preflight_error = self._preflight_inbound_target(core, inbound, bind_ip, requested_port)
                        if preflight_error:
                            self.last_error = preflight_error
                            self.listeners.append({
                                "core_id": core.get("id"),
                                "core_name": core.get("name"),
                                "inbound_name": inbound.get("name"),
                                "bind_ip": bind_ip,
                                "requested_port": requested_port,
                                "status": "error",
                                "error": preflight_error,
                            })
                            logger.warning("listener rejected before start: %s:%s core=%s inbound=%s error=%s", bind_ip, requested_port, core.get("name"), inbound.get("name"), preflight_error)
                            continue

                        key = f"{core.get('id') or core.get('name')}::{inbound.get('name')}::{bind_ip}:{requested_port}"
                        try:
                            server = await asyncio.start_server(
                                lambda r, w, c=core, ib=inbound: self._handle_client(c, ib, r, w),
                                host=bind_ip,
                                port=requested_port,
                                backlog=int(os.getenv("DOCTOR_DEV_FORWARD_BACKLOG", "4096")),
                                reuse_address=True,
                                start_serving=True,
                            )
                            sock = server.sockets[0] if server.sockets else None
                            actual_port = int(sock.getsockname()[1]) if sock else requested_port
                            self._tune_server_socket(sock)
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

            summary = self.summary() | {"started_listeners": started}
            error_count = len([item for item in self.listeners if item.get("status") == "error"])
            summary["listener_errors"] = error_count
            summary["ok"] = error_count == 0 and started > 0
            return summary


    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        cores = self._ordered_cores(config.get("cores") if isinstance(config.get("cores"), list) else [])
        for core in cores:
            if not isinstance(core, dict) or core.get("enabled") is False:
                continue
            dep_error = self._dependency_error_for_config(core, cores, str(config.get("node_id") or ""))
            if dep_error:
                errors.append(f"{core.get('name') or core.get('id')}: {dep_error}")
                continue
            for inbound in core.get("inbounds", []) if isinstance(core.get("inbounds"), list) else []:
                if not isinstance(inbound, dict) or inbound.get("enabled") is False:
                    continue
                ports = self._ports_for(inbound)
                if not ports:
                    errors.append(f"{core.get('name')}/{inbound.get('name')}: inbound has no valid listen port")
                    continue
                for requested_port in ports:
                    bind_ip = str(inbound.get("bind_ip") or "0.0.0.0").strip() or "0.0.0.0"
                    preflight_error = self._preflight_inbound_target(core, inbound, bind_ip, requested_port)
                    if preflight_error:
                        errors.append(f"{core.get('name')}/{inbound.get('name')}: {preflight_error}")
        return errors

    def _ordered_cores(self, cores: list[Any]) -> list[dict[str, Any]]:
        valid = [c for c in cores if isinstance(c, dict)]
        by_id = {str(c.get("id") or ""): c for c in valid if c.get("id")}
        result: list[dict[str, Any]] = []
        seen: set[str] = set()

        def visit(core: dict[str, Any]) -> None:
            cid = str(core.get("id") or id(core))
            if cid in seen:
                return
            seen.add(cid)
            for dep in core.get("dependencies", []) if isinstance(core.get("dependencies"), list) else []:
                if not isinstance(dep, dict) or dep.get("required") is False or dep.get("type") != "core":
                    continue
                dep_core = by_id.get(str(dep.get("ref_id") or ""))
                if dep_core:
                    visit(dep_core)
            result.append(core)

        for core in valid:
            visit(core)
        return result


    def _dependency_error_for_config(self, core: dict[str, Any], cores: list[dict[str, Any]], current_node_id: str) -> str:
        by_id = {str(c.get("id") or ""): c for c in cores if c.get("id")}
        for dep in core.get("dependencies", []) if isinstance(core.get("dependencies"), list) else []:
            if not isinstance(dep, dict) or dep.get("required") is False:
                continue
            dep_type = str(dep.get("type") or "core")
            ref_id = str(dep.get("ref_id") or "").strip()
            if not ref_id:
                continue
            if dep_type == "core":
                dep_core = by_id.get(ref_id)
                if not dep_core:
                    return f"Required core dependency is missing: {ref_id}"
                if dep_core.get("enabled") is False:
                    return f"Required core dependency is disabled: {dep_core.get('name') or ref_id}"
            elif dep_type == "node" and ref_id not in {current_node_id, "self"}:
                logger.debug("node dependency cannot be verified on this node: core=%s ref=%s", core.get("name"), ref_id)
        return ""

    def _dependency_error(self, core: dict[str, Any], cores: list[dict[str, Any]]) -> str:
        return self._dependency_error_for_config(core, cores, str(self.config.get("node_id") or ""))

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
        return cleaned

    def _balancers_for_core(self, core: dict[str, Any]) -> dict[str, dict[str, Any]]:
        result = {}
        for balancer in core.get("balancers", []) if isinstance(core.get("balancers"), list) else []:
            if isinstance(balancer, dict) and balancer.get("enabled") is not False:
                alias = str(balancer.get("alias") or "").strip()
                if alias:
                    result[alias] = balancer
        return result

    def _preflight_inbound_target(self, core: dict[str, Any], inbound: dict[str, Any], bind_ip: str, listen_port: int) -> str:
        if listen_port <= 0:
            return "Inbound must have at least one fixed listen port for simple forwarding."
        if str(inbound.get("target_type") or "static") == "static":
            target = self._static_target(inbound)
            if not target:
                return "Static target host/port is invalid."
            if self._is_direct_self_loop(target, bind_ip, listen_port, inbound):
                return (
                    f"Invalid forwarding loop: inbound {bind_ip}:{listen_port} points back to "
                    f"{target.host}:{target.port}. Set Target Host/Port to the real upstream service."
                )
        return ""

    def _static_target(self, inbound: dict[str, Any]) -> Target | None:
        host = str(inbound.get("target_host") or "").strip()
        try:
            port = int(inbound.get("target_port") or 0)
        except (TypeError, ValueError):
            port = 0
        if not host or not (1 <= port <= 65535):
            return None
        return Target(host, port, "static")

    def _resolve_targets(self, core: dict[str, Any], inbound: dict[str, Any]) -> list[Target]:
        target_type = str(inbound.get("target_type") or "static")
        if target_type == "static":
            target = self._static_target(inbound)
            if target:
                logger.debug("resolved static target: core=%s inbound=%s target=%s:%s", core.get("name"), inbound.get("name"), target.host, target.port)
                return [target]
            logger.debug("static target is invalid: core=%s inbound=%s", core.get("name"), inbound.get("name"))
            return []

        alias = str(inbound.get("target_balancer") or "").strip()
        balancer = self._balancers_for_core(core).get(alias)
        if not balancer:
            logger.debug("target balancer not found: core=%s inbound=%s alias=%s", core.get("name"), inbound.get("name"), alias)
            return []
        endpoints = [e for e in (balancer.get("endpoints") or []) if isinstance(e, dict) and e.get("enabled") is not False]
        if not endpoints:
            logger.debug("target balancer has no enabled endpoints: core=%s inbound=%s alias=%s", core.get("name"), inbound.get("name"), alias)
            return []

        targets = [target for endpoint in endpoints for target in [self._target_from_endpoint(endpoint)] if target]
        strategy = str(balancer.get("strategy") or "round_robin")
        if strategy == "random":
            random.shuffle(targets)
        elif strategy == "failover":
            pass
        elif strategy == "least_connections":
            targets.sort(key=lambda t: self._target_active.get(t.key, 0))
        else:
            if targets:
                idx = self._rr.get(alias, 0) % len(targets)
                self._rr[alias] = idx + 1
                targets = targets[idx:] + targets[:idx]
        logger.debug("resolved balancer targets: core=%s inbound=%s alias=%s strategy=%s targets=%s", core.get("name"), inbound.get("name"), alias, strategy, [t.key for t in targets])
        return targets

    def _target_from_endpoint(self, endpoint: dict[str, Any]) -> Target | None:
        etype = str(endpoint.get("type") or "static")
        if etype == "static":
            host = str(endpoint.get("host") or "").strip()
            try:
                port = int(endpoint.get("port") or 0)
            except (TypeError, ValueError):
                port = 0
            if host and 1 <= port <= 65535:
                return Target(host, port, "static-endpoint")
            return None

        host = str(endpoint.get("host") or "").strip()
        try:
            port = int(endpoint.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        if host and 1 <= port <= 65535:
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

    def _is_direct_self_loop(self, target: Target, bind_ip: str, listen_port: int, inbound: dict[str, Any]) -> bool:
        if target.port != listen_port:
            return False
        target_host = target.host.strip().lower()
        bind_host = bind_ip.strip().lower()
        public_host = str(inbound.get("public_host") or "").strip().lower()
        if target_host in LOCAL_TARGET_HOSTS:
            return bind_host in {"0.0.0.0", "127.0.0.1", "localhost", "::", "::1", "[::1]"}
        if public_host and target_host == public_host:
            return True
        return target_host == bind_host

    def _is_runtime_self_loop(self, target: Target, inbound: dict[str, Any]) -> bool:
        for listener in self.listeners:
            if listener.get("status") != "listening":
                continue
            try:
                lport = int(listener.get("port") or listener.get("requested_port") or 0)
            except (TypeError, ValueError):
                lport = 0
            if lport != target.port:
                continue
            bind_ip = str(listener.get("bind_ip") or "0.0.0.0")
            if self._is_direct_self_loop(target, bind_ip, lport, inbound):
                return True
        return False

    async def _connect_target(self, targets: list[Target], inbound: dict[str, Any]) -> tuple[Target, asyncio.StreamReader, asyncio.StreamWriter] | None:
        last_error = ""
        for target in targets:
            if self._is_runtime_self_loop(target, inbound):
                last_error = f"refusing forwarding loop to {target.host}:{target.port}"
                logger.warning("%s inbound=%s", last_error, inbound.get("name"))
                continue
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(target.host, target.port), timeout=CONNECT_TIMEOUT)
                self._tune_stream_writer(writer)
                return target, reader, writer
            except Exception as exc:  # noqa: BLE001
                last_error = f"{target.host}:{target.port} failed: {exc}"
                logger.debug("target connect failed: inbound=%s target=%s:%s error=%s", inbound.get("name"), target.host, target.port, exc)
                continue
        if last_error:
            self.last_error = last_error
        return None

    async def _handle_client(self, core: dict[str, Any], inbound: dict[str, Any], client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
        self.connection_count += 1
        self.active_connections += 1
        peer = client_writer.get_extra_info("peername")
        target_writer: asyncio.StreamWriter | None = None
        target: Target | None = None
        self._tune_stream_writer(client_writer)
        try:
            targets = self._resolve_targets(core, inbound)
            if not targets:
                self.last_error = f"No target for inbound {inbound.get('name')}"
                logger.warning("connection rejected: no target core=%s inbound=%s peer=%s", core.get("name"), inbound.get("name"), peer)
                return

            connected = await self._connect_target(targets, inbound)
            if not connected:
                logger.warning("connection rejected: all targets failed core=%s inbound=%s peer=%s last_error=%s", core.get("name"), inbound.get("name"), peer, self.last_error)
                return

            target, target_reader, target_writer = connected
            self._target_active[target.key] = self._target_active.get(target.key, 0) + 1
            logger.debug("proxy connected peer=%s -> %s:%s inbound=%s", peer, target.host, target.port, inbound.get("name"))

            await self._relay_pair(client_reader, client_writer, target_reader, target_writer)
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            logger.debug("proxy connection failed peer=%s target=%s error=%s", peer, target.key if target else "", exc)
        finally:
            if target:
                self._target_active[target.key] = max(0, self._target_active.get(target.key, 1) - 1)
            for writer in (client_writer, target_writer):
                if writer:
                    await self._close_writer(writer)
            self.active_connections = max(0, self.active_connections - 1)

    async def _relay_pair(self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter, target_reader: asyncio.StreamReader, target_writer: asyncio.StreamWriter) -> None:
        tasks = [
            asyncio.create_task(self._pipe(client_reader, target_writer, "in")),
            asyncio.create_task(self._pipe(target_reader, client_writer, "out")),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        failed = False
        for task in done:
            exc = task.exception()
            if exc:
                failed = True
                logger.debug("pipe finished with error: %s", exc)
        if failed:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        else:
            await asyncio.gather(*pending, return_exceptions=True)

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
            transport = writer.transport if hasattr(writer, "transport") else None
            if transport is None or transport.get_write_buffer_size() >= DRAIN_HIGH_WATER:
                await writer.drain()
        try:
            await writer.drain()
            if writer.can_write_eof():
                writer.write_eof()
                await writer.drain()
        except Exception:
            pass

    def _tune_server_socket(self, sock: socket.socket | None) -> None:
        if sock is None:
            return
        self._tune_socket(sock)

    def _tune_stream_writer(self, writer: asyncio.StreamWriter) -> None:
        sock = writer.get_extra_info("socket")
        if sock is not None:
            self._tune_socket(sock)
        transport = writer.transport if hasattr(writer, "transport") else None
        if transport is not None:
            try:
                transport.set_write_buffer_limits(high=DRAIN_HIGH_WATER, low=max(65536, DRAIN_HIGH_WATER // 4))
            except Exception:
                pass

    def _tune_socket(self, sock: socket.socket) -> None:
        for opt, value in (
            ((socket.IPPROTO_TCP, socket.TCP_NODELAY), 1),
            ((socket.SOL_SOCKET, socket.SO_KEEPALIVE), 1),
            ((socket.SOL_SOCKET, socket.SO_RCVBUF), int(os.getenv("DOCTOR_DEV_FORWARD_RCVBUF", str(1024 * 1024)))),
            ((socket.SOL_SOCKET, socket.SO_SNDBUF), int(os.getenv("DOCTOR_DEV_FORWARD_SNDBUF", str(1024 * 1024)))),
        ):
            try:
                sock.setsockopt(opt[0], opt[1], value)
            except OSError:
                pass

    async def _close_writer(self, writer: asyncio.StreamWriter) -> None:
        try:
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), timeout=SHUTDOWN_TIMEOUT)
        except Exception:
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
            "buffer_size": BUFFER_SIZE,
            "connect_timeout": CONNECT_TIMEOUT,
        }


runtime = ForwarderRuntime()
