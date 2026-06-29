from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def wait_for_health(base_url: str, timeout_seconds: float = 15.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(base_url + "/health", timeout=1.0) as response:  # noqa: S310 - local test server
                data = json.loads(response.read().decode("utf-8"))
                if response.status == 200 and data.get("status") == "ok":
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.15)
    raise RuntimeError(f"Node did not become healthy: {last_error}")


class PanelNodeEndToEndTests(unittest.TestCase):
    def test_panel_apply_then_runtime_sync_then_drift_ok(self) -> None:
        async def scenario() -> None:
            from doctor_dev_panel.core_store import build_node_config, create_core
            from doctor_dev_panel.node_runtime_cache import get_node_runtime
            from doctor_dev_panel.node_store import create_node
            from doctor_dev_panel.services.drift_detector import detect_node_drift
            from doctor_dev_panel.services.node_control import post_node_api
            from doctor_dev_panel.services.runtime_sync import sync_node_runtime_once

            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                port = free_port()
                api_key = "e2e-node-key"
                node_config_path = tmp_path / "node" / "routing.json"
                env_path = tmp_path / "node.env"
                env_path.write_text(
                    "\n".join(
                        [
                            f"API_KEY={api_key}",
                            "NODE_HOST=127.0.0.1",
                            f"API_PORT={port}",
                            f"DOCTOR_DEV_NODE_DATA_DIR={tmp_path / 'node' / 'data'}",
                            f"DOCTOR_DEV_NODE_ROUTING_CONFIG={node_config_path}",
                            f"DOCTOR_DEV_NODE_LOG_DIR={tmp_path / 'node' / 'logs'}",
                            f"DOCTOR_DEV_NODE_LOG_FILE={tmp_path / 'node' / 'logs' / 'node.log'}",
                            "PYTHON_LOG_LEVEL=WARNING",
                            "UVICORN_LOG_LEVEL=warning",
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )

                panel_env_keys = {
                    "DOCTOR_DEV_DATA_DIR": str(tmp_path / "panel"),
                    "DOCTOR_DEV_NODES_PATH": str(tmp_path / "panel" / "nodes.json"),
                    "DOCTOR_DEV_CORES_PATH": str(tmp_path / "panel" / "cores.json"),
                    "DOCTOR_DEV_NODE_RUNTIME_CACHE_PATH": str(tmp_path / "panel" / "node-runtime-cache.json"),
                    "PUBLIC_SCHEME": "http",
                    "PUBLIC_HOST": "127.0.0.1",
                    "PORT": "8080",
                    "DOCTOR_DEV_PANEL_NODE_SYNC_TIMEOUT": "3",
                    "DOCTOR_DEV_PANEL_NODE_SYNC_CONCURRENCY": "2",
                }
                old_env = {key: os.environ.get(key) for key in panel_env_keys}
                os.environ.update(panel_env_keys)

                proc = subprocess.Popen(
                    [
                        sys.executable,
                        "main.py",
                        "--mode",
                        "node",
                        "--env",
                        str(env_path),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                    ],
                    cwd=str(PROJECT_ROOT),
                    env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                try:
                    wait_for_health(f"http://127.0.0.1:{port}")
                    node = create_node(
                        {
                            "name": "e2e-node",
                            "address": "127.0.0.1",
                            "api_port": port,
                            "api_key": api_key,
                            "enabled": True,
                        }
                    )
                    core = create_core(
                        {
                            "name": "e2e-core",
                            "node_id": node["id"],
                            "enabled": True,
                            "inbounds": [
                                {
                                    "name": "e2e-inbound",
                                    "bind_ip": "127.0.0.1",
                                    "port_mode": "random",
                                    "random_count": 1,
                                    "target_type": "static",
                                    "target_host": "127.0.0.1",
                                    "target_port": 9,
                                    "enabled": True,
                                }
                            ],
                            "balancers": [],
                            "dependencies": [],
                        }
                    )
                    desired = build_node_config(node["id"])
                    self.assertEqual(node["id"], desired["node_id"])
                    self.assertEqual(core["id"], desired["cores"][0]["id"])

                    apply_result = await asyncio.to_thread(post_node_api, node, "/config/apply", desired)
                    self.assertTrue(apply_result.get("ok"), apply_result)
                    self.assertGreaterEqual(apply_result.get("summary", {}).get("listeners_total", 0), 1)

                    sync_result = await sync_node_runtime_once(node)
                    self.assertTrue(sync_result.get("ok"), sync_result)
                    runtime_entry = get_node_runtime(node["id"])
                    self.assertIsInstance(runtime_entry, dict)
                    self.assertTrue(runtime_entry.get("reachable"))
                    self.assertTrue(runtime_entry.get("auth_ok"))
                    self.assertEqual(port, runtime_entry.get("api", {}).get("port"))
                    self.assertTrue(
                        any(
                            item.get("inbound_name") == "e2e-inbound" and item.get("status") == "listening"
                            for item in runtime_entry.get("listeners", [])
                        ),
                        runtime_entry,
                    )

                    drift = detect_node_drift(node["id"], build_node_config(node["id"]), runtime_entry)
                    self.assertTrue(drift.get("ok"), drift)
                    self.assertEqual("ok", drift.get("status"))
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                    for key, value in old_env.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main(verbosity=2)
