from __future__ import annotations

import asyncio
import random
import ssl
import tempfile
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

BUFFER_SIZE = 65536


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class TargetEntry:
    id: str
    host: str
    port: int
    weight: int = 1
    priority: int = 100
    source_type: str = "static"
    tls_enabled: bool = False


class RouteRuntime:
    def __init__(self, route: dict[str, Any], targets: list[TargetEntry]):
        self.route = route
        self.targets = targets
        self.rr_index = 0
        self.weighted_targets: list[TargetEntry] = []
        for target in targets:
            self.weighted_targets.extend([target] * max(1, int(target.weight)))

    def ordered_targets(self) -> list[TargetEntry]:
        if not self.targets:
            return []
        balancer = self.route.get("balancer", "round_robin")
        if balancer == "random":
            return [random.choice(self.targets)]
        if balancer == "weighted_round_robin":
            pool = self.weighted_targets or self.targets
            target = pool[self.rr_index % len(pool)]
            self.rr_index += 1
            return [target]
        if balancer == "failover":
            return sorted(self.targets, key=lambda item: (item.priority, item.id))
        # default: round_robin
        target = self.targets[self.rr_index % len(self.targets)]
        self.rr_index += 1
        return [target]


class TunnelManager:
    def __init__(self, log_callback):
        self.log = log_callback
        self.servers: list[asyncio.AbstractServer] = []
        self.config: dict[str, Any] | None = None
        self.routes: dict[str, RouteRuntime] = {}
        self.listener_to_inbound: dict[tuple[str, int], dict[str, Any]] = {}
        self._temp_dirs: list[tempfile.TemporaryDirectory] = []
        self.metrics: dict[str, Any] = {
            "active_connections": 0,
            "total_connections": 0,
            "bytes_in": 0,
            "bytes_out": 0,
            "started_at": None,
            "last_applied_at": None,
            "last_error": None,
            "inbounds": {},
            "routes": {},
        }

    async def stop(self) -> None:
        for server in self.servers:
            server.close()
        for server in self.servers:
            await server.wait_closed()
        if self.servers:
            self.log("info", f"stopped {len(self.servers)} tunnel listener(s)")
        self.servers = []
        self.listener_to_inbound = {}
        self.routes = {}
        for td in self._temp_dirs:
            try:
                td.cleanup()
            except Exception:
                pass
        self._temp_dirs = []
        self.metrics["active_connections"] = 0

    async def apply(self, config: dict[str, Any]) -> list[str]:
        await self.stop()
        self.config = config
        self.metrics["last_applied_at"] = now_iso()
        self.metrics["started_at"] = now_iso()
        self.metrics["last_error"] = None
        warnings: list[str] = []

        inbounds = config.get("inbounds", [])
        routes = config.get("routes", [])
        inbound_by_id = {item["id"]: item for item in inbounds}
        route_by_id = {item["id"]: item for item in routes}

        for route in routes:
            resolved, route_warnings = self._resolve_route_targets(route, inbound_by_id)
            warnings.extend(route_warnings)
            self.routes[route["id"]] = RouteRuntime(route, resolved)
            self.metrics["routes"][route["id"]] = {
                "name": route.get("name"),
                "balancer": route.get("balancer"),
                "targets_total": len(resolved),
            }

        for inbound in inbounds:
            self.metrics["inbounds"].setdefault(
                inbound["id"],
                {
                    "name": inbound.get("name"),
                    "active_connections": 0,
                    "total_connections": 0,
                    "bytes_in": 0,
                    "bytes_out": 0,
                    "rejected_connections": 0,
                    "tls_enabled": bool((inbound.get("tls") or {}).get("enabled")),
                    "tls_mode": (inbound.get("tls") or {}).get("mode", "none"),
                },
            )
            if not inbound.get("enabled", True):
                continue
            route_id = inbound.get("route_id")
            if not route_id or route_id not in route_by_id:
                warnings.append(f"inbound {inbound.get('name')} has no valid route; listener not started")
                continue
            for listener in inbound.get("listeners", []):
                if not listener.get("enabled", True):
                    continue
                host = listener.get("listen_ip") or "127.0.0.1"
                mode = listener.get("port_mode", "fixed")
                if mode == "fixed":
                    candidate_ports = [int(listener.get("listen_port"))]
                elif mode == "random":
                    candidate_ports = [0]
                elif mode == "range":
                    start = int(listener.get("port_range_start") or 0)
                    end = int(listener.get("port_range_end") or 0)
                    candidate_ports = list(range(start, end + 1)) if start and end and start <= end else []
                    if not candidate_ports:
                        warnings.append(f"inbound {inbound.get('name')} has invalid listener port range; listener skipped")
                        continue
                else:
                    warnings.append(f"inbound {inbound.get('name')} has unsupported port_mode={mode}; listener skipped")
                    continue

                inbound_tls = inbound.get("tls") or {}
                ssl_context, tls_warnings = self._build_server_ssl_context(inbound_tls)
                warnings.extend(tls_warnings)
                if inbound_tls.get("enabled") and ssl_context is None:
                    warnings.append(f"inbound {inbound.get('name')} TLS listener not started because TLS context is invalid")
                    continue

                started = False
                last_start_error: Exception | None = None
                for port in candidate_ports:
                    try:
                        server = await asyncio.start_server(
                            lambda reader, writer, inbound=inbound: self._handle_client(inbound, reader, writer),
                            host,
                            port,
                            backlog=4096,
                            ssl=ssl_context,
                        )
                    except OSError as exc:
                        last_start_error = exc
                        if mode == "range":
                            continue
                        raise
                    self.servers.append(server)
                    actual_port = int((server.sockets or [None])[0].getsockname()[1]) if server.sockets else int(port)
                    self.listener_to_inbound[(host, actual_port)] = inbound
                    inbound_metrics = self.metrics["inbounds"].setdefault(inbound["id"], {})
                    inbound_metrics.setdefault("runtime_listeners", []).append({
                        "listen_ip": host,
                        "listen_port": actual_port,
                        "requested_port_mode": mode,
                        "tls_enabled": bool(ssl_context),
                    })
                    tls_label = "tls" if ssl_context else "tcp"
                    self.log("info", f"listener started inbound={inbound.get('name')} on {host}:{actual_port} route={route_id} mode={tls_label} port_mode={mode}")
                    started = True
                    break
                if not started:
                    warnings.append(f"inbound {inbound.get('name')} listener could not start for port_mode={mode}: {last_start_error}")

        if not self.servers:
            warnings.append("no tunnel listener was started")
        return warnings

    def _resolve_route_targets(self, route: dict[str, Any], inbound_by_id: dict[str, dict[str, Any]]) -> tuple[list[TargetEntry], list[str]]:
        resolved: list[TargetEntry] = []
        warnings: list[str] = []
        for target in route.get("targets", []):
            if not target.get("enabled", True):
                continue
            target_type = target.get("type")
            weight = int(target.get("weight", 1))
            priority = int(target.get("priority", 100))
            if target_type == "static":
                host = target.get("host")
                for port in target.get("ports", []):
                    resolved.append(TargetEntry(id=target.get("id", "target"), host=host, port=int(port), weight=weight, priority=priority, source_type="static", tls_enabled=bool(target.get("tls_enabled", False))))
            elif target_type == "local_inbound":
                local_inbound = inbound_by_id.get(target.get("local_inbound_id"))
                if not local_inbound:
                    warnings.append(f"local_inbound target not found: {target.get('local_inbound_id')}")
                    continue
                fixed = [l for l in local_inbound.get("listeners", []) if l.get("enabled", True) and l.get("port_mode") == "fixed" and l.get("listen_port")]
                if not fixed:
                    warnings.append(f"local_inbound target has no fixed listener: {local_inbound.get('name')}")
                    continue
                listener = fixed[0]
                host = listener.get("listen_ip") or "127.0.0.1"
                if host == "0.0.0.0":
                    host = "127.0.0.1"
                resolved.append(TargetEntry(id=target.get("id", "target"), host=host, port=int(listener["listen_port"]), weight=weight, priority=priority, source_type="local_inbound", tls_enabled=bool((local_inbound.get("tls") or {}).get("enabled"))))
            elif target_type == "remote_group":
                endpoints = target.get("resolved_endpoints") or []
                if not endpoints:
                    warnings.append(f"remote_group target has no resolved endpoints: {target.get('remote_node_id')}")
                    continue
                for endpoint in endpoints:
                    host = endpoint.get("host")
                    port = endpoint.get("port")
                    if not host or not port:
                        warnings.append(f"remote_group endpoint is incomplete: {endpoint}")
                        continue
                    resolved.append(
                        TargetEntry(
                            id=target.get("id", "target"),
                            host=str(host),
                            port=int(port),
                            weight=weight,
                            priority=priority,
                            source_type="remote_group",
                            tls_enabled=bool(endpoint.get("tls_enabled", False)),
                        )
                    )
            else:
                warnings.append(f"unsupported target type ignored: {target_type}")
        return resolved, warnings


    def _cert_paths_from_tls(self, tls: dict[str, Any]) -> tuple[str | None, str | None, list[str]]:
        warnings: list[str] = []
        mode = tls.get("mode", "none")
        if not tls.get("enabled") or mode == "none":
            return None, None, warnings

        if mode == "pasted_content":
            fullchain = tls.get("fullchain_content")
            privkey = tls.get("privkey_content")
            if not fullchain or not privkey:
                return None, None, ["TLS pasted_content selected but certificate/key content is incomplete"]
            td = tempfile.TemporaryDirectory(prefix="doctor-dev-tls-")
            self._temp_dirs.append(td)
            base = Path(td.name)
            cert_path = base / "fullchain.pem"
            key_path = base / "privkey.pem"
            cert_path.write_text(fullchain, encoding="utf-8")
            key_path.write_text(privkey, encoding="utf-8")
            return str(cert_path), str(key_path), warnings

        cert_path = tls.get("fullchain_path")
        key_path = tls.get("privkey_path")
        if not cert_path or not key_path:
            return None, None, [f"TLS mode={mode} selected but fullchain_path/privkey_path is incomplete"]
        return str(cert_path), str(key_path), warnings

    def _build_server_ssl_context(self, tls: dict[str, Any]) -> tuple[ssl.SSLContext | None, list[str]]:
        if not tls.get("enabled"):
            return None, []
        cert_path, key_path, warnings = self._cert_paths_from_tls(tls)
        if not cert_path or not key_path:
            return None, warnings or ["TLS is enabled but certificate material is missing"]
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
            return ctx, warnings
        except Exception as exc:  # noqa: BLE001
            return None, warnings + [f"TLS listener disabled because certificate chain could not be loaded: {exc}"]

    def _build_client_ssl_context(self) -> ssl.SSLContext:
        # When a target endpoint uses a self-signed certificate, runtime target-to-target TLS skips certificate verification by design.
        # Production-grade verification can be added once trust stores / expected hostnames are configurable per target.
        return ssl._create_unverified_context()

    async def _handle_client(self, inbound: dict[str, Any], reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        inbound_id = inbound["id"]
        inbound_name = inbound.get("name", inbound_id)
        route_id = inbound.get("route_id")
        peer = writer.get_extra_info("peername")
        limits = inbound.get("limits", {}) or {}
        max_active = limits.get("max_active_connections")
        max_users = limits.get("max_users")
        inbound_metrics = self.metrics["inbounds"].setdefault(inbound_id, {})

        if max_users and int(inbound_metrics.get("total_connections", 0)) >= int(max_users):
            inbound_metrics["rejected_connections"] = int(inbound_metrics.get("rejected_connections", 0)) + 1
            self.log("warning", f"connection rejected inbound={inbound_name} reason=max_users peer={peer}")
            writer.close()
            await writer.wait_closed()
            return

        if max_active and int(inbound_metrics.get("active_connections", 0)) >= int(max_active):
            inbound_metrics["rejected_connections"] = int(inbound_metrics.get("rejected_connections", 0)) + 1
            self.log("warning", f"connection rejected inbound={inbound_name} reason=max_active_connections peer={peer}")
            writer.close()
            await writer.wait_closed()
            return

        self.metrics["active_connections"] = int(self.metrics.get("active_connections", 0)) + 1
        self.metrics["total_connections"] = int(self.metrics.get("total_connections", 0)) + 1
        inbound_metrics["active_connections"] = int(inbound_metrics.get("active_connections", 0)) + 1
        inbound_metrics["total_connections"] = int(inbound_metrics.get("total_connections", 0)) + 1

        try:
            route = self.routes.get(route_id or "")
            if route is None or not route.targets:
                raise RuntimeError(f"no runtime target for route_id={route_id}")
            last_error: Exception | None = None
            for target in route.ordered_targets():
                try:
                    tls_label = "tls" if target.tls_enabled else "tcp"
                    self.log("info", f"accepted inbound={inbound_name} peer={peer} target={target.host}:{target.port} target_mode={tls_label} balancer={route.route.get('balancer')}")
                    client_ssl = self._build_client_ssl_context() if target.tls_enabled else None
                    upstream_reader, upstream_writer = await asyncio.wait_for(asyncio.open_connection(target.host, target.port, ssl=client_ssl, server_hostname=None if client_ssl else None), timeout=5)
                    await self._pipe_pair(reader, writer, upstream_reader, upstream_writer, inbound_id)
                    return
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    self.log("warning", f"target failed inbound={inbound_name} target={target.host}:{target.port} error={exc}")
                    if route.route.get("balancer") != "failover":
                        break
            raise RuntimeError(f"all selected targets failed: {last_error}")
        except Exception as exc:  # noqa: BLE001
            self.metrics["last_error"] = str(exc)
            self.log("error", f"connection failed inbound={inbound_name} peer={peer} error={exc}")
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        finally:
            self.metrics["active_connections"] = max(0, int(self.metrics.get("active_connections", 0)) - 1)
            inbound_metrics["active_connections"] = max(0, int(inbound_metrics.get("active_connections", 0)) - 1)

    async def _pipe_pair(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
        inbound_id: str,
    ) -> None:
        async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter, direction: str) -> None:
            total = 0
            try:
                while True:
                    data = await src.read(BUFFER_SIZE)
                    if not data:
                        break
                    total += len(data)
                    dst.write(data)
                    await dst.drain()
            finally:
                try:
                    if hasattr(dst, "can_write_eof") and dst.can_write_eof():
                        dst.write_eof()
                        await dst.drain()
                    else:
                        dst.close()
                        await dst.wait_closed()
                except Exception:
                    try:
                        dst.close()
                        await dst.wait_closed()
                    except Exception:
                        pass
                if direction == "in":
                    self.metrics["bytes_in"] = int(self.metrics.get("bytes_in", 0)) + total
                    self.metrics["inbounds"][inbound_id]["bytes_in"] = int(self.metrics["inbounds"][inbound_id].get("bytes_in", 0)) + total
                else:
                    self.metrics["bytes_out"] = int(self.metrics.get("bytes_out", 0)) + total
                    self.metrics["inbounds"][inbound_id]["bytes_out"] = int(self.metrics["inbounds"][inbound_id].get("bytes_out", 0)) + total

        await asyncio.gather(
            pipe(client_reader, upstream_writer, "in"),
            pipe(upstream_reader, client_writer, "out"),
            return_exceptions=True,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "running_listeners": len(self.servers),
            "last_config_core": self.config.get("core_name") if self.config else None,
            "metrics": self.metrics,
        }
