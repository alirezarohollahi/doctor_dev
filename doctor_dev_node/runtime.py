from __future__ import annotations

import asyncio
import logging
import json
import os
import random
import socket
import ssl
import time
from urllib.request import Request, urlopen
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("doctor_dev_node.runtime")

# Large enough for high-throughput forwarding without making every connection
# allocate huge buffers. Can be tuned from node.env.
BUFFER_SIZE = int(os.getenv("DOCTOR_DEV_FORWARD_BUFFER_SIZE", str(256 * 1024)))
DRAIN_HIGH_WATER = int(os.getenv("DOCTOR_DEV_FORWARD_DRAIN_HIGH_WATER", str(1024 * 1024)))
CONNECT_TIMEOUT = float(os.getenv("DOCTOR_DEV_FORWARD_CONNECT_TIMEOUT", "5"))
SHUTDOWN_TIMEOUT = float(os.getenv("DOCTOR_DEV_FORWARD_SHUTDOWN_TIMEOUT", "3"))
PEER_SYNC_INTERVAL = float(os.getenv("DOCTOR_DEV_NODE_PEER_SYNC_INTERVAL", "10"))
PEER_SYNC_TIMEOUT = float(os.getenv("DOCTOR_DEV_NODE_PEER_SYNC_TIMEOUT", "3"))

LOCAL_TARGET_HOSTS = {"", "127.0.0.1", "localhost", "::1", "0.0.0.0", "[::1]"}


@dataclass(frozen=True)
class Target:
    host: str
    port: int
    name: str = ""
    group_key: str = ""
    endpoint_weight: float = 1.0

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
        self._peer_runtime_cache: dict[str, dict[str, Any]] = {}
        self._peer_sync_last: dict[str, float] = {}
        self._peer_sync_errors: dict[str, str] = {}
        self._peer_tokens: dict[str, dict[str, Any]] = {}
        self._peer_sync_task: Optional[asyncio.Task] = None
        self.connection_count = 0
        self.active_connections = 0
        self.bytes_in = 0
        self.bytes_out = 0
        self.last_error = ""
        self._lock = asyncio.Lock()

    async def stop(self) -> None:
        if self._peer_sync_task:
            self._peer_sync_task.cancel()
            await asyncio.gather(self._peer_sync_task, return_exceptions=True)
            self._peer_sync_task = None
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
                    for port_index, requested_port in enumerate(ports):
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

                        key_seed = f"{core.get('id') or core.get('name')}::{inbound.get('name')}::{bind_ip}:{requested_port}:{port_index}"
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
                            # Random listen ports are requested as 0. Multiple random listeners
                            # for the same inbound would otherwise overwrite each other in the
                            # server registry, leaving only the last one stoppable. Store the
                            # actual assigned port in the key when it is known.
                            key = f"{core.get('id') or core.get('name')}::{inbound.get('name')}::{bind_ip}:{actual_port}"
                            if key in self.servers:
                                key = key_seed
                            self.servers[key] = server
                            self.listeners.append({
                                "core_id": core.get("id"),
                                "core_name": core.get("name"),
                                "inbound_name": inbound.get("name"),
                                "bind_ip": bind_ip,
                                "requested_port": requested_port,
                                "port": actual_port,
                                "port_mode": inbound.get("port_mode"),
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

            if self._peer_sync_endpoints():
                await self._sync_all_peers_once()
            self._restart_peer_sync_if_needed()
            summary = self.summary() | {"started_listeners": started}
            error_count = len([item for item in self.listeners if item.get("status") == "error"])
            summary["listener_errors"] = error_count
            summary["ok"] = error_count == 0 and started > 0
            return summary


    def _endpoint_sync_interval(self, endpoint: dict[str, Any]) -> float:
        try:
            interval = float(endpoint.get("sync_interval") or endpoint.get("update_interval") or PEER_SYNC_INTERVAL or 10)
        except (TypeError, ValueError):
            interval = 10.0
        return min(max(interval, 1.0), 86400.0)

    def _peer_sync_key(self, endpoint: dict[str, Any]) -> str:
        remote_node_id = str(endpoint.get("remote_node_id") or endpoint.get("node_id") or "")
        sync_urls = endpoint.get("sync_urls") if isinstance(endpoint.get("sync_urls"), list) else []
        return remote_node_id + "|" + ",".join(str(u) for u in sync_urls)

    def _restart_peer_sync_if_needed(self) -> None:
        endpoints = self._peer_sync_endpoints()
        if self._peer_sync_task:
            self._peer_sync_task.cancel()
            self._peer_sync_task = None
        if endpoints:
            min_interval = min(self._endpoint_sync_interval(endpoint) for endpoint in endpoints)
            self._peer_sync_task = asyncio.create_task(self._peer_sync_loop())
            logger.info("peer runtime sync enabled: endpoints=%s min_interval=%ss", len(endpoints), min_interval)

    def _add_peer_sync_endpoint(self, endpoints_by_key: dict[str, dict[str, Any]], endpoint: dict[str, Any]) -> None:
        sync_urls = endpoint.get("sync_urls") if isinstance(endpoint.get("sync_urls"), list) else []
        token_url = str(endpoint.get("token_url") or "")
        remote_node_id = str(endpoint.get("remote_node_id") or endpoint.get("node_id") or endpoint.get("ref_id") or "")
        if not sync_urls or not token_url or not remote_node_id:
            return
        endpoint = dict(endpoint)
        endpoint["remote_node_id"] = remote_node_id
        key = self._peer_sync_key(endpoint)
        previous = endpoints_by_key.get(key)
        if not previous or self._endpoint_sync_interval(endpoint) < self._endpoint_sync_interval(previous):
            endpoints_by_key[key] = endpoint

    def _peer_sync_endpoints(self) -> list[dict[str, Any]]:
        endpoints_by_key: dict[str, dict[str, Any]] = {}
        for core in self.config.get("cores", []) if isinstance(self.config.get("cores"), list) else []:
            for dep in core.get("dependencies", []) if isinstance(core.get("dependencies"), list) else []:
                if isinstance(dep, dict) and dep.get("type") == "node" and dep.get("required") is not False:
                    dep = dict(dep)
                    dep["source_core_id"] = str(core.get("id") or "")
                    self._add_peer_sync_endpoint(endpoints_by_key, dep)
            for balancer in core.get("balancers", []) if isinstance(core.get("balancers"), list) else []:
                for endpoint in balancer.get("endpoints", []) if isinstance(balancer.get("endpoints"), list) else []:
                    if not isinstance(endpoint, dict) or endpoint.get("enabled") is False:
                        continue
                    if endpoint.get("type") != "node_inbound":
                        continue
                    endpoint = dict(endpoint)
                    endpoint["source_core_id"] = str(core.get("id") or "")
                    self._add_peer_sync_endpoint(endpoints_by_key, endpoint)
        return list(endpoints_by_key.values())

    async def _peer_sync_loop(self) -> None:
        while True:
            try:
                endpoints = self._peer_sync_endpoints()
                now_ts = time.time()
                due = []
                for endpoint in endpoints:
                    key = self._peer_sync_key(endpoint)
                    last = self._peer_sync_last.get(key, 0.0)
                    if now_ts - last >= self._endpoint_sync_interval(endpoint):
                        due.append(endpoint)
                if due:
                    await asyncio.gather(*(self._sync_peer_endpoint(endpoint) for endpoint in due), return_exceptions=True)
                sleep_for = min([self._endpoint_sync_interval(endpoint) for endpoint in endpoints] or [max(1.0, PEER_SYNC_INTERVAL)])
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.debug("peer runtime sync loop failed: %s", exc)
                sleep_for = max(1.0, PEER_SYNC_INTERVAL)
            await asyncio.sleep(max(1.0, min(sleep_for, 60.0)))

    async def _sync_all_peers_once(self) -> None:
        endpoints = self._peer_sync_endpoints()
        if not endpoints:
            return
        await asyncio.gather(*(self._sync_peer_endpoint(endpoint) for endpoint in endpoints), return_exceptions=True)

    def _endpoint_is_due_for_sync(self, endpoint: dict[str, Any], *, force: bool = False) -> bool:
        if force:
            return True
        key = self._peer_sync_key(endpoint)
        if not key:
            return False
        remote_node_id = str(endpoint.get("remote_node_id") or endpoint.get("node_id") or "")
        if remote_node_id and remote_node_id not in self._peer_runtime_cache:
            return True
        last = float(self._peer_sync_last.get(key, 0.0) or 0.0)
        return time.time() - last >= self._endpoint_sync_interval(endpoint)

    def _peer_endpoints_for_inbound(self, core: dict[str, Any], inbound: dict[str, Any]) -> list[dict[str, Any]]:
        endpoints: list[dict[str, Any]] = []
        if str(inbound.get("target_type") or "static") != "balancer":
            return endpoints
        alias = str(inbound.get("target_balancer") or "").strip()
        balancer = self._balancers_for_core(core).get(alias)
        if not balancer:
            return endpoints
        for endpoint in balancer.get("endpoints", []) if isinstance(balancer.get("endpoints"), list) else []:
            if not isinstance(endpoint, dict) or endpoint.get("enabled") is False:
                continue
            if endpoint.get("type") != "node_inbound":
                continue
            sync_urls = endpoint.get("sync_urls") if isinstance(endpoint.get("sync_urls"), list) else []
            token_url = str(endpoint.get("token_url") or "")
            remote_node_id = str(endpoint.get("remote_node_id") or endpoint.get("node_id") or "")
            if sync_urls and token_url and remote_node_id:
                endpoint = dict(endpoint)
                endpoint["source_core_id"] = str(core.get("id") or "")
                endpoint["remote_node_id"] = remote_node_id
                endpoints.append(endpoint)
        return endpoints

    async def _refresh_peer_targets_for_inbound(self, core: dict[str, Any], inbound: dict[str, Any], *, force: bool = False) -> None:
        endpoints = self._peer_endpoints_for_inbound(core, inbound)
        if not endpoints:
            return
        due = [endpoint for endpoint in endpoints if self._endpoint_is_due_for_sync(endpoint, force=force)]
        if not due:
            return
        await asyncio.gather(*(self._sync_peer_endpoint(endpoint, force=force) for endpoint in due), return_exceptions=True)

    async def _sync_peer_endpoint(self, endpoint: dict[str, Any], *, force: bool = False) -> bool:
        key = self._peer_sync_key(endpoint)
        remote_hint = str(endpoint.get("remote_node_id") or endpoint.get("node_id") or "")
        try:
            data = await asyncio.to_thread(self._fetch_peer_export, endpoint)
            if not data:
                error = f"peer runtime export returned no data for node={remote_hint or 'unknown'}"
                if key:
                    self._peer_sync_errors[key] = error
                logger.warning(error)
                return False
            remote_node_id = str(endpoint.get("remote_node_id") or endpoint.get("node_id") or data.get("node_id") or "")
            if not remote_node_id:
                error = "peer runtime export did not include a node id"
                if key:
                    self._peer_sync_errors[key] = error
                logger.warning(error)
                return False
            data["synced_at_unix"] = time.time()
            data["sync_interval"] = self._endpoint_sync_interval(endpoint)
            self._peer_runtime_cache[remote_node_id] = data
            if key:
                self._peer_sync_errors.pop(key, None)
            logger.info("peer runtime synced: node=%s listeners=%s interval=%ss force=%s", remote_node_id, len(data.get("listeners") or []), data["sync_interval"], force)
            return True
        except Exception as exc:  # noqa: BLE001
            error = f"peer runtime sync failed node={remote_hint or 'unknown'}: {exc}"
            if key:
                self._peer_sync_errors[key] = error
            self.last_error = error
            logger.warning(error)
            return False
        finally:
            if key:
                self._peer_sync_last[key] = time.time()

    def _endpoint_token_refresh_interval(self, endpoint: dict[str, Any]) -> float:
        try:
            interval = float(endpoint.get("token_refresh_interval") or 30)
        except (TypeError, ValueError):
            interval = 30.0
        return min(max(interval, 5.0), 86400.0)

    def _fetch_peer_token(self, endpoint: dict[str, Any]) -> str:
        cache_key = self._peer_sync_key(endpoint) + "|token"
        cached = self._peer_tokens.get(cache_key) or {}
        now_ts = time.time()
        refresh_after = float(cached.get("refresh_after") or self._endpoint_token_refresh_interval(endpoint))
        if cached.get("token") and now_ts - float(cached.get("fetched_at") or 0) < refresh_after:
            return str(cached["token"])

        token_url = str(endpoint.get("token_url") or "")
        if not token_url:
            return ""
        payload = {
            "source_node_id": str(self.config.get("node_id") or ""),
            "source_core_id": str(endpoint.get("source_core_id") or endpoint.get("local_core_id") or ""),
            "target_node_id": str(endpoint.get("remote_node_id") or endpoint.get("node_id") or endpoint.get("ref_id") or ""),
            "target_core_id": str(endpoint.get("remote_core_id") or endpoint.get("core_id") or ""),
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "DoctorDevNode/PeerToken",
        }
        api_key = os.getenv("API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = Request(token_url, data=body, headers=headers, method="POST")
        context = ssl._create_unverified_context() if token_url.startswith("https://") else None
        with urlopen(req, timeout=PEER_SYNC_TIMEOUT, context=context) as response:  # noqa: S310
            raw = response.read(1024 * 64).decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
        token = str(data.get("token") or "")
        if token:
            self._peer_tokens[cache_key] = {
                "token": token,
                "fetched_at": now_ts,
                "refresh_after": float(data.get("refresh_after") or self._endpoint_token_refresh_interval(endpoint)),
            }
        return token

    def _fetch_peer_export(self, endpoint: dict[str, Any]) -> Optional[dict[str, Any]]:
        urls = endpoint.get("sync_urls") if isinstance(endpoint.get("sync_urls"), list) else []
        token = self._fetch_peer_token(endpoint)
        certificate = str(endpoint.get("certificate") or "")
        if not urls or not token:
            return None
        last_error = ""
        for url in urls:
            try:
                headers = {"Accept": "application/json", "User-Agent": "DoctorDevNode/PeerSync", "X-Doctor-Node-Token": token}
                req = Request(str(url), headers=headers)
                context = None
                if str(url).startswith("https://"):
                    context = ssl.create_default_context(cadata=certificate) if certificate.strip() else ssl._create_unverified_context()
                with urlopen(req, timeout=PEER_SYNC_TIMEOUT, context=context) as response:  # noqa: S310 - admin configured peer URL
                    raw = response.read(1024 * 512).decode("utf-8", errors="replace")
                    parsed = json.loads(raw) if raw else {}
                    if isinstance(parsed, dict) and parsed.get("ok") is not False:
                        return parsed
                    last_error = str(parsed.get("message") or parsed)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue
        if last_error:
            logger.debug("peer runtime sync failed: node=%s error=%s", endpoint.get("remote_node_id") or endpoint.get("node_id"), last_error)
        return None


    def validate_config(self, config: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        cores = self._ordered_cores(config.get("cores") if isinstance(config.get("cores"), list) else [])
        enabled_cores = [core for core in cores if isinstance(core, dict) and core.get("enabled") is not False]
        if len(enabled_cores) > 1:
            errors.append("Each node can have only one enabled core.")
            return errors
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
        is_random_listener = str(inbound.get("port_mode") or "fixed") == "random" and listen_port == 0
        if listen_port <= 0 and not is_random_listener:
            return "Inbound must have at least one valid listen port for simple forwarding."
        if str(inbound.get("target_type") or "static") == "static":
            target = self._static_target(inbound)
            if not target:
                return "Static target host/port is invalid."
            # With random mode the OS chooses an available ephemeral listen port,
            # so it cannot collide with an already-listening local upstream port.
            # Self-loop detection is still enforced for fixed ports.
            if not is_random_listener and self._is_direct_self_loop(target, bind_ip, listen_port, inbound):
                return (
                    f"Invalid forwarding loop: inbound {bind_ip}:{listen_port} points back to "
                    f"{target.host}:{target.port}. Set Target Host/Port to the real upstream service."
                )
        return ""

    def _static_target(self, inbound: dict[str, Any]) -> Optional[Target]:
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

        groups = self._target_groups_from_endpoints(alias, endpoints)
        strategy = str(balancer.get("strategy") or "round_robin")
        targets = self._select_targets_from_groups(alias, strategy, groups)
        logger.debug(
            "resolved balancer targets: core=%s inbound=%s alias=%s strategy=%s groups=%s targets=%s",
            core.get("name"),
            inbound.get("name"),
            alias,
            strategy,
            [(g.get("key"), g.get("weight"), [t.key for t in g.get("targets", [])]) for g in groups],
            [t.key for t in targets],
        )
        return targets

    def _endpoint_weight(self, endpoint: dict[str, Any]) -> float:
        try:
            weight = float(endpoint.get("weight") or 1)
        except (TypeError, ValueError):
            weight = 1.0
        return max(0.0, weight)

    def _endpoint_group_key(self, alias: str, endpoint: dict[str, Any], index: int) -> str:
        if endpoint.get("type") == "node_inbound":
            return "|".join(
                [
                    alias,
                    "node_inbound",
                    str(endpoint.get("remote_node_id") or endpoint.get("node_id") or ""),
                    str(endpoint.get("remote_core_id") or endpoint.get("core_id") or ""),
                    str(endpoint.get("remote_inbound_name") or endpoint.get("inbound_name") or ""),
                    str(index),
                ]
            )
        return "|".join([alias, "static", str(endpoint.get("host") or ""), str(endpoint.get("port") or ""), str(index)])

    def _target_with_group(self, target: Target, group_key: str, weight: float) -> Target:
        return Target(target.host, target.port, target.name, group_key=group_key, endpoint_weight=weight)

    def _target_groups_from_endpoints(self, alias: str, endpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for index, endpoint in enumerate(endpoints):
            if not isinstance(endpoint, dict) or endpoint.get("enabled") is False:
                continue
            weight = self._endpoint_weight(endpoint)
            if weight <= 0:
                continue
            group_key = self._endpoint_group_key(alias, endpoint, index)
            targets = [self._target_with_group(t, group_key, weight) for t in self._targets_from_endpoint(endpoint)]
            if not targets:
                continue
            groups.append({"key": group_key, "weight": weight, "targets": targets, "endpoint": endpoint})
        return groups

    def _rotate_group_targets(self, alias: str, group: dict[str, Any], *, least_connections: bool = False, randomize: bool = False) -> list[Target]:
        targets = list(group.get("targets") or [])
        if not targets:
            return []
        if least_connections:
            targets.sort(key=lambda t: self._target_active.get(t.key, 0))
            return targets
        if randomize:
            random.shuffle(targets)
            return targets
        key = f"{alias}::ports::{group.get('key') or ''}"
        idx = self._rr.get(key, 0) % len(targets)
        self._rr[key] = idx + 1
        return targets[idx:] + targets[:idx]

    def _select_targets_from_groups(self, alias: str, strategy: str, groups: list[dict[str, Any]]) -> list[Target]:
        if not groups:
            return []
        if strategy == "failover":
            ordered: list[Target] = []
            for group in groups:
                ordered.extend(self._rotate_group_targets(alias, group))
            return ordered
        if strategy == "random":
            total = sum(float(g.get("weight") or 1) for g in groups)
            cursor = random.uniform(0, total) if total > 0 else 0
            selected = groups[-1]
            upto = 0.0
            for group in groups:
                upto += float(group.get("weight") or 1)
                if cursor <= upto:
                    selected = group
                    break
            return self._rotate_group_targets(alias, selected, randomize=True)
        if strategy == "least_connections":
            selected = min(
                groups,
                key=lambda g: (sum(self._target_active.get(t.key, 0) for t in g.get("targets", [])) / max(float(g.get("weight") or 1), 0.0001), str(g.get("key") or "")),
            )
            return self._rotate_group_targets(alias, selected, least_connections=True)

        weighted: list[dict[str, Any]] = []
        for group in groups:
            repeat = max(1, int(round(float(group.get("weight") or 1))))
            weighted.extend([group] * repeat)
        if not weighted:
            return []
        key = f"{alias}::endpoint"
        idx = self._rr.get(key, 0) % len(weighted)
        self._rr[key] = idx + 1
        return self._rotate_group_targets(alias, weighted[idx])

    def _listener_host_for_target(self, bind_ip: str) -> str:
        host = str(bind_ip or "").strip()
        if host in {"", "0.0.0.0", "*"}:
            return "127.0.0.1"
        if host in {"::", "[::]"}:
            return "::1"
        return host

    def _targets_from_active_listener(self, core_id: str, inbound_name: str) -> list[Target]:
        targets: list[Target] = []
        for listener in self.listeners:
            if listener.get("status") != "listening":
                continue
            if core_id and str(listener.get("core_id") or "") != core_id:
                continue
            if inbound_name and str(listener.get("inbound_name") or "") != inbound_name:
                continue
            try:
                port = int(listener.get("port") or listener.get("requested_port") or 0)
            except (TypeError, ValueError):
                port = 0
            if 1 <= port <= 65535:
                target = Target(self._listener_host_for_target(str(listener.get("bind_ip") or "127.0.0.1")), port, "node-inbound-listener")
                if target.key not in {t.key for t in targets}:
                    targets.append(target)
        return targets

    def _target_from_active_listener(self, core_id: str, inbound_name: str) -> Optional[Target]:
        targets = self._targets_from_active_listener(core_id, inbound_name)
        return targets[0] if targets else None

    def _targets_from_cached_peer(self, endpoint: dict[str, Any]) -> list[Target]:
        remote_node_id = str(endpoint.get("remote_node_id") or endpoint.get("node_id") or "")
        if not remote_node_id:
            return []
        cached = self._peer_runtime_cache.get(remote_node_id)
        if not cached:
            return []
        listeners = cached.get("listeners")
        if not isinstance(listeners, list):
            summary = cached.get("summary") if isinstance(cached.get("summary"), dict) else {}
            listeners = summary.get("listeners") if isinstance(summary.get("listeners"), list) else []
        core_id = str(endpoint.get("remote_core_id") or endpoint.get("core_id") or "")
        inbound_name = str(endpoint.get("remote_inbound_name") or endpoint.get("inbound_name") or "")
        candidates: list[int] = []
        for listener in listeners:
            if not isinstance(listener, dict) or listener.get("status") != "listening":
                continue
            if core_id and str(listener.get("core_id") or "") != core_id:
                continue
            if inbound_name and str(listener.get("inbound_name") or "") != inbound_name:
                continue
            try:
                port = int(listener.get("port") or 0)
            except (TypeError, ValueError):
                port = 0
            if 1 <= port <= 65535 and port not in candidates:
                candidates.append(port)
        if not candidates:
            return []
        host = str(endpoint.get("host") or "").strip() or str(endpoint.get("public_host") or "").strip()
        if not host or host in LOCAL_TARGET_HOSTS:
            # For remote peer cache a localhost-like host is never useful. Keep
            # the explicit fallback host generated by the panel if possible.
            host = str(endpoint.get("peer_host") or "").strip() or host
        if not host:
            return []
        return [Target(host, port, "node-inbound-peer-cache") for port in candidates]

    def _target_from_cached_peer(self, endpoint: dict[str, Any]) -> Optional[Target]:
        targets = self._targets_from_cached_peer(endpoint)
        return random.choice(targets) if targets else None

    def _targets_from_endpoint_live_ports(self, endpoint: dict[str, Any], *, name: str = "node-inbound-live") -> list[Target]:
        ports = endpoint.get("live_ports") if isinstance(endpoint.get("live_ports"), list) else []
        cleaned: list[int] = []
        for item in ports:
            try:
                port = int(item)
            except (TypeError, ValueError):
                continue
            if 1 <= port <= 65535 and port not in cleaned:
                cleaned.append(port)
        if not cleaned:
            return []
        host = str(endpoint.get("host") or "").strip() or str(endpoint.get("public_host") or "").strip() or str(endpoint.get("peer_host") or "").strip()
        if not host:
            return []
        return [Target(host, port, name) for port in cleaned]

    def _endpoint_live_ports_are_newer_than_peer_cache(self, endpoint: dict[str, Any]) -> bool:
        try:
            endpoint_ts = float(endpoint.get("live_ports_synced_at_unix") or 0)
        except (TypeError, ValueError):
            endpoint_ts = 0.0
        if endpoint_ts <= 0:
            return True
        remote_node_id = str(endpoint.get("remote_node_id") or endpoint.get("node_id") or "")
        cached = self._peer_runtime_cache.get(remote_node_id) if remote_node_id else None
        if not isinstance(cached, dict):
            return True
        try:
            cache_ts = float(cached.get("synced_at_unix") or 0)
        except (TypeError, ValueError):
            cache_ts = 0.0
        return endpoint_ts >= cache_ts

    def _targets_from_endpoint(self, endpoint: dict[str, Any]) -> list[Target]:
        etype = str(endpoint.get("type") or "static")
        if etype == "static":
            host = str(endpoint.get("host") or "").strip()
            try:
                port = int(endpoint.get("port") or 0)
            except (TypeError, ValueError):
                port = 0
            if host and 1 <= port <= 65535:
                return [Target(host, port, "static-endpoint")]
            return []

        # Node-inbound endpoints are semantic references. Resolve all active
        # listener ports for the selected inbound, not just the first one. The
        # endpoint weight is applied to the inbound as a whole; if the inbound
        # has N live ports, the balancer splits that endpoint's selected traffic
        # across those N ports.
        core_id = str(endpoint.get("core_id") or "")
        inbound_name = str(endpoint.get("inbound_name") or "")
        current_node_id = str(self.config.get("node_id") or "")
        remote_node_id = str(endpoint.get("remote_node_id") or endpoint.get("node_id") or "")
        is_remote_node_inbound = bool(remote_node_id and current_node_id and remote_node_id != current_node_id)
        if is_remote_node_inbound:
            live_targets = self._targets_from_endpoint_live_ports(endpoint, name="node-inbound-panel-live-cache")
            cached_targets = self._targets_from_cached_peer(endpoint)
            if live_targets and self._endpoint_live_ports_are_newer_than_peer_cache(endpoint):
                return live_targets
            if cached_targets:
                return cached_targets
            if live_targets:
                return live_targets
            resolved_from = str(endpoint.get("resolved_from") or "")
            remote_port_mode = str(endpoint.get("remote_port_mode") or endpoint.get("port_mode") or "")
            if resolved_from == "node_inbound_random_peer_sync" or remote_port_mode == "random":
                logger.debug(
                    "remote random node inbound is not synced yet: node=%s core=%s inbound=%s",
                    remote_node_id,
                    core_id,
                    inbound_name,
                )
                return []
        if inbound_name or core_id:
            active_targets = self._targets_from_active_listener(core_id, inbound_name)
            if active_targets:
                return active_targets
            for core in self.config.get("cores", []) if isinstance(self.config.get("cores"), list) else []:
                if core_id and str(core.get("id")) != core_id:
                    continue
                for inbound in core.get("inbounds", []) if isinstance(core.get("inbounds"), list) else []:
                    if inbound_name and str(inbound.get("name")) != inbound_name:
                        continue
                    ports = inbound.get("fixed_ports") or []
                    targets: list[Target] = []
                    host = str(inbound.get("public_host") or inbound.get("bind_ip") or "127.0.0.1")
                    if host in {"", "0.0.0.0", "*", "::"}:
                        host = "127.0.0.1"
                    for item in ports:
                        try:
                            port = int(item)
                        except (TypeError, ValueError):
                            continue
                        if 1 <= port <= 65535 and f"{host}:{port}" not in {t.key for t in targets}:
                            targets.append(Target(host, port, "node-inbound"))
                    if targets:
                        return targets

        live_targets = self._targets_from_endpoint_live_ports(endpoint, name="node-inbound-explicit-live")
        if live_targets:
            return live_targets
        host = str(endpoint.get("host") or "").strip()
        try:
            port = int(endpoint.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        if host and 1 <= port <= 65535:
            return [Target(host, port, "node-inbound-explicit")]
        return []

    def _target_from_endpoint(self, endpoint: dict[str, Any]) -> Optional[Target]:
        targets = self._targets_from_endpoint(endpoint)
        return targets[0] if targets else None

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

    async def _connect_target(self, targets: list[Target], inbound: dict[str, Any]) -> Optional[tuple[Target, asyncio.StreamReader, asyncio.StreamWriter]]:
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
        target_writer: Optional[asyncio.StreamWriter] = None
        target: Optional[Target] = None
        self._tune_stream_writer(client_writer)
        try:
            # For remote Node Inbound endpoints, refresh dependency runtime before resolving
            # targets when the dependency interval is due. If the first connection attempt
            # still fails, force one immediate refresh and retry once. This keeps B updated
            # when A changes fixed/random live ports without requiring another panel apply.
            await self._refresh_peer_targets_for_inbound(core, inbound, force=False)
            targets = self._resolve_targets(core, inbound)
            if not targets:
                await self._refresh_peer_targets_for_inbound(core, inbound, force=True)
                targets = self._resolve_targets(core, inbound)
            if not targets:
                self.last_error = f"No target for inbound {inbound.get('name')}"
                logger.warning("connection rejected: no target core=%s inbound=%s peer=%s", core.get("name"), inbound.get("name"), peer)
                return

            connected = await self._connect_target(targets, inbound)
            if not connected:
                await self._refresh_peer_targets_for_inbound(core, inbound, force=True)
                refreshed_targets = self._resolve_targets(core, inbound)
                if refreshed_targets:
                    connected = await self._connect_target(refreshed_targets, inbound)
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

    def _tune_server_socket(self, sock: Optional[socket.socket]) -> None:
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
            "peer_sync_interval": PEER_SYNC_INTERVAL,
            "peer_sync_effective_intervals": [self._endpoint_sync_interval(endpoint) for endpoint in self._peer_sync_endpoints()],
            "peer_sync_nodes": len(self._peer_runtime_cache),
            "peer_sync_cache_nodes": list(self._peer_runtime_cache.keys()),
            "peer_sync_errors": dict(self._peer_sync_errors),
            "peer_sync_last": dict(self._peer_sync_last),
        }


runtime = ForwarderRuntime()




