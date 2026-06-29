from __future__ import annotations

import json
import logging
import os
import ssl
from http.client import RemoteDisconnected
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from typing import Optional, Any

from ..logging_utils import debug_json, is_debug_enabled

logger = logging.getLogger("doctor_dev_panel.services.node_control")


class NodeAPIError(RuntimeError):
    """Expected/clean node API failure shown to the UI without a traceback."""


def _env_float(name: str, default: float, *, minimum: float = 0.1, maximum: float = 300.0) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


def _http_error_detail(exc: HTTPError) -> str:
    try:
        raw = exc.read(1024 * 64).decode("utf-8", errors="replace")
        data: Any = json.loads(raw) if raw else {}
    except Exception:
        data = {}
    if isinstance(data, dict):
        detail = data.get("detail")
        if isinstance(detail, dict):
            code = str(detail.get("code") or "").strip()
            message = str(detail.get("message") or "").strip()
            if code and message:
                return f"{code}: {message}"
            if code:
                return code
            if message:
                return message
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    return f"HTTP {exc.code}"


def _node_host(address: str) -> tuple[str, Optional[str]]:
    raw = (address or "").strip()
    if not raw:
        raise ValueError("Node address is empty.")
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    scheme = parsed.scheme if "://" in raw else None
    host = parsed.netloc or parsed.path
    host = host.split("/", 1)[0].strip()
    if not host:
        raise ValueError("Node address is invalid.")
    return host, scheme


def _format_attempts(attempts: list[str]) -> str:
    cleaned = [item for item in attempts if item]
    if not cleaned:
        return "No connection attempt was completed."
    return " | ".join(cleaned[-4:])


def _read_url(
    url: str, api_key: str = "", *, certificate: str = "", timeout: float = 4.0
) -> tuple[int, dict]:
    headers = {"Accept": "application/json", "User-Agent": "DoctorDevPanel/NodeCheck"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = Request(url, headers=headers)
    if is_debug_enabled():
        logger.debug(
            "panel.node_api.request %s",
            debug_json({"method": "GET", "url": url, "headers": headers, "certificate_supplied": bool(certificate.strip())}),
        )
    context = None
    if url.startswith("https://"):
        if certificate.strip():
            context = ssl.create_default_context(cadata=certificate)
        else:
            context = ssl._create_unverified_context()  # noqa: SLF001
    with urlopen(req, timeout=timeout, context=context) as response:  # noqa: S310 - admin configured node URL
        raw = response.read(1024 * 64).decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"raw": raw[:2000]}
        if is_debug_enabled():
            logger.debug("panel.node_api.response %s", debug_json({"url": url, "status": int(response.status), "body": data}))
        return int(response.status), data


def node_scheme_candidates(address: str, certificate: str = "") -> tuple[str, list[str]]:
    host, explicit_scheme = _node_host(address)
    if explicit_scheme:
        return host, [explicit_scheme]
    # A stored certificate means "trust this certificate if the control API is HTTPS".
    # It must not force HTTPS because many nodes expose the control API over HTTP
    # while using certificates for data-plane or reverse-proxy paths. Try HTTPS
    # first when a certificate exists, then fall back to HTTP if the TLS handshake
    # is closed by the remote side.
    return host, (["https", "http"] if certificate.strip() else ["http", "https"])


def node_api_urls(node: dict, path: str) -> list[tuple[str, str, str]]:
    certificate = str(node.get("certificate") or "").strip()
    host, schemes = node_scheme_candidates(str(node.get("address", "")), certificate)
    port = int(node.get("api_port") or 62051)
    return [(f"{scheme}://{host}:{port}{path}", scheme, certificate) for scheme in schemes]


def read_node_export(node: dict) -> dict:
    host, schemes = node_scheme_candidates(str(node.get("address", "")), str(node.get("certificate") or ""))
    port = int(node.get("api_port") or 62051)
    api_key = str(node.get("api_key") or "")
    attempts: list[str] = []
    for path in ("/runtime", "/config/export"):
        for scheme in schemes:
            url = f"{scheme}://{host}:{port}{path}"
            try:
                _, data = _read_url(
                    url,
                    api_key=api_key,
                    certificate=str(node.get("certificate") or ""),
                    timeout=_env_float("DOCTOR_DEV_PANEL_NODE_SYNC_TIMEOUT", 3.0),
                )
                if isinstance(data, dict):
                    return data
            except HTTPError as exc:
                if exc.code == 401:
                    detail = _http_error_detail(exc)
                    raise NodeAPIError(
                        f"Node runtime auth failed for {url}: {detail}. Check the node API key stored in panel against API_KEY in node.env."
                    ) from exc
                attempts.append(f"{url}: HTTP {exc.code}")
            except Exception as exc:  # noqa: BLE001
                attempts.append(f"{url}: {exc}")
    raise NodeAPIError(_format_attempts(attempts))


def check_node_sync(payload: dict) -> dict:
    certificate = str(payload.get("certificate") or "").strip()
    host, schemes = node_scheme_candidates(str(payload.get("address", "")), certificate)
    # api_port is the node management API. Inbound/listener ports live inside
    # runtime config and must not be treated as a second fixed node port.
    port = int(payload.get("api_port") or 62051)
    api_key = str(payload.get("api_key") or "")

    attempts: list[str] = []
    last_error = ""
    for scheme in schemes:
        base = f"{scheme}://{host}:{port}"
        endpoints = [("/status", api_key), ("/health", "")]
        for endpoint, key in endpoints:
            if endpoint == "/status" and not key:
                continue
            url = base + endpoint
            try:
                status_code, data = _read_url(
                    url, key, certificate=certificate if scheme == "https" else "", timeout=_env_float("DOCTOR_DEV_PANEL_NODE_CHECK_TIMEOUT", 4.0)
                )
                if 200 <= status_code < 300:
                    return {
                        "ok": True,
                        "status": "running",
                        "url": url,
                        "http_status": status_code,
                        "using_api_port": port,
                        "using_control_scheme": scheme,
                        "using_tls_certificate": bool(certificate and scheme == "https"),
                        "response": data,
                        "message": "Node connection is healthy.",
                    }
                last_error = f"{url} returned HTTP {status_code}"
            except HTTPError as exc:
                last_error = f"{url} returned HTTP {exc.code}"
            except (RemoteDisconnected, URLError, TimeoutError, OSError, ssl.SSLError, ValueError) as exc:
                last_error = f"{url} failed: {exc}"
            attempts.append(last_error)
    return {
        "ok": False,
        "status": "error",
        "message": last_error or "Node connection check failed.",
        "attempts": attempts[-6:],
        "using_api_port": port,
    }


async def check_node_payload(payload: dict) -> dict:
    import asyncio

    return await asyncio.to_thread(check_node_sync, payload)


def read_node_api(node: dict, path: str, *, timeout: float | None = None) -> dict:
    if timeout is None:
        timeout = _env_float("DOCTOR_DEV_PANEL_NODE_API_TIMEOUT", 5.0)
    attempts: list[str] = []
    api_key = str(node.get("api_key") or "")
    for url, scheme, certificate in node_api_urls(node, path):
        try:
            status_code, data = _read_url(
                url,
                api_key,
                certificate=certificate if scheme == "https" else "",
                timeout=timeout,
            )
            if 200 <= status_code < 300:
                return data
            attempts.append(f"{url} returned HTTP {status_code}")
        except HTTPError as exc:
            if exc.code == 404 and path.startswith("/logs"):
                raise NodeAPIError(
                    "This node is running an older agent. Update the node service, restart it, then try again."
                ) from exc
            raise NodeAPIError(f"Node returned {_http_error_detail(exc)} while handling {path}.") from exc
        except (RemoteDisconnected, URLError, TimeoutError, OSError, ssl.SSLError, ValueError) as exc:
            attempts.append(f"{url} failed: {exc}")
            continue
    raise NodeAPIError(
        "Node API is unreachable while handling "
        f"{path}. Check the API port, TLS/certificate, and node service. "
        f"Attempts: {_format_attempts(attempts)}"
    )


def post_node_api(node: dict, path: str, payload: dict, *, timeout: float | None = None) -> dict:
    if timeout is None:
        timeout = _env_float("DOCTOR_DEV_PANEL_NODE_APPLY_TIMEOUT", 8.0)
    body = json.dumps(payload).encode("utf-8")
    if is_debug_enabled():
        logger.debug("panel.node_api.apply_payload %s", debug_json({"path": path, "payload": payload}))
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "DoctorDevPanel/NodeApply",
    }
    api_key = str(node.get("api_key") or "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    attempts: list[str] = []
    for url, scheme, certificate in node_api_urls(node, path):
        context = None
        if scheme == "https":
            if certificate.strip():
                context = ssl.create_default_context(cadata=certificate)
            else:
                context = ssl._create_unverified_context()  # noqa: SLF001
        if is_debug_enabled():
            logger.debug(
                "panel.node_api.request %s",
                debug_json({"method": "POST", "url": url, "headers": headers, "payload_bytes": len(body), "certificate_supplied": bool(certificate.strip())}),
            )
        req = Request(url, data=body, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=timeout, context=context) as response:  # noqa: S310
                raw = response.read(1024 * 256).decode("utf-8", errors="replace")
                data = json.loads(raw) if raw else {}
                if is_debug_enabled():
                    logger.debug("panel.node_api.response %s", debug_json({"url": url, "status": int(response.status), "body": data}))
                if not (200 <= int(response.status) < 300):
                    attempts.append(f"{url} returned HTTP {response.status}")
                    continue
                if path == "/config/apply" and data.get("ok") is False:
                    errors = data.get("errors") if isinstance(data.get("errors"), list) else []
                    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
                    listener_errors = [
                        str(item.get("error"))
                        for item in summary.get("listeners", [])
                        if isinstance(item, dict) and item.get("status") == "error" and item.get("error")
                    ]
                    details = errors or listener_errors or [str(data.get("message") or "Node rejected the routing configuration.")]
                    raise NodeAPIError("Node rejected routing config: " + " | ".join(details[:4]))
                return data
        except HTTPError as exc:
            if exc.code == 404 and path == "/config/apply":
                raise NodeAPIError(
                    "This node does not support configuration apply yet. Update the node service and restart it."
                ) from exc
            raise NodeAPIError(f"Node returned {_http_error_detail(exc)} while handling {path}.") from exc
        except (RemoteDisconnected, URLError, TimeoutError, OSError, ssl.SSLError, ValueError, json.JSONDecodeError) as exc:
            attempts.append(f"{url} failed: {exc}")
            continue
    raise NodeAPIError(
        "Node API is unreachable while applying configuration. "
        "Check that the API port points to the node control-plane and that TLS/certificate settings match the node service. "
        f"Attempts: {_format_attempts(attempts)}"
    )
