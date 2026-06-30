
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def read_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 5.0) -> tuple[int, dict]:
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=timeout) as response:  # noqa: S310 - local test server
        raw = response.read(1024 * 256).decode("utf-8", errors="replace")
        return int(response.status), json.loads(raw) if raw else {}


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def forged_peer_token(*, secret: str, target_node_id: str, target_core_id: str, exp_offset: int) -> str:
    now = int(time.time())
    payload = {
        "typ": "doctor-dev-peer",
        "iat": now - 60,
        "exp": now + exp_offset,
        "source_node_id": "node-a",
        "source_core_id": "core-a",
        "target_node_id": target_node_id,
        "target_core_id": target_core_id,
    }
    body = b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    sig = b64(hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest())
    return body + "." + sig


class NodeHttpAuthTests(unittest.TestCase):
    def test_runtime_http_auth_matrix(self) -> None:
        from doctor_dev_node.peer_tokens import issue_peer_token

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            port = free_port()
            api_key = "node-api-key-test"
            peer_secret = "peer-secret-test"
            config_path = tmp_path / "routing.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "node_id": "node-b",
                        "generated_at": "http-auth-test",
                        "peer_verify_secret": peer_secret,
                        "cores": [
                            {
                                "id": "core-b",
                                "name": "core-b",
                                "enabled": True,
                                "dependencies": [],
                                "balancers": [],
                                "inbounds": [],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            env_path = tmp_path / "node.env"
            env_path.write_text(
                "\n".join(
                    [
                        f"API_KEY={api_key}",
                        f"NODE_HOST=127.0.0.1",
                        f"API_PORT={port}",
                        f"DOCTOR_DEV_NODE_DATA_DIR={tmp_path / 'data'}",
                        f"DOCTOR_DEV_NODE_ROUTING_CONFIG={config_path}",
                        f"DOCTOR_DEV_NODE_LOG_DIR={tmp_path / 'logs'}",
                        f"DOCTOR_DEV_NODE_LOG_FILE={tmp_path / 'logs' / 'node.log'}",
                        "PYTHON_LOG_LEVEL=WARNING",
                        "UVICORN_LOG_LEVEL=warning",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(PROJECT_ROOT)
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
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                base = f"http://127.0.0.1:{port}"
                deadline = time.time() + 15
                while True:
                    try:
                        status, health = read_json(base + "/health", timeout=1)
                        if status == 200 and health.get("status") == "ok":
                            break
                    except Exception:
                        if time.time() > deadline:
                            raise
                        time.sleep(0.15)

                status, data = read_json(base + "/runtime", headers={"Authorization": f"Bearer {api_key}"})
                self.assertEqual(200, status)
                self.assertEqual("panel_api_key", data.get("auth_source"))
                self.assertEqual(port, data.get("api", {}).get("port"))

                with self.assertRaises(HTTPError) as missing_auth:
                    read_json(base + "/runtime")
                self.assertEqual(401, missing_auth.exception.code)
                detail = json.loads(missing_auth.exception.read().decode("utf-8"))["detail"]
                self.assertEqual("MISSING_NODE_EXPORT_AUTH", detail["code"])

                with self.assertRaises(HTTPError) as wrong_key:
                    read_json(base + "/runtime", headers={"Authorization": "Bearer wrong"})
                self.assertEqual(401, wrong_key.exception.code)
                detail = json.loads(wrong_key.exception.read().decode("utf-8"))["detail"]
                self.assertEqual("INVALID_NODE_API_KEY", detail["code"])

                token = issue_peer_token(
                    secret=peer_secret,
                    source_node_id="node-a",
                    source_core_id="core-a",
                    target_node_id="node-b",
                    target_core_id="core-b",
                    ttl_seconds=60,
                )
                status, peer_data = read_json(base + "/runtime", headers={"X-Doctor-Node-Token": token})
                self.assertEqual(200, status)
                self.assertEqual("peer_token", peer_data.get("auth_source"))

                bad_target = issue_peer_token(
                    secret=peer_secret,
                    source_node_id="node-a",
                    source_core_id="core-a",
                    target_node_id="node-x",
                    target_core_id="core-b",
                    ttl_seconds=60,
                )
                with self.assertRaises(HTTPError) as wrong_target:
                    read_json(base + "/runtime", headers={"X-Doctor-Node-Token": bad_target})
                self.assertEqual(401, wrong_target.exception.code)
                detail = json.loads(wrong_target.exception.read().decode("utf-8"))["detail"]
                self.assertEqual("INVALID_PEER_TOKEN", detail["code"])
                self.assertIn("target node mismatch", detail["message"])

                expired = forged_peer_token(secret=peer_secret, target_node_id="node-b", target_core_id="core-b", exp_offset=-30)
                with self.assertRaises(HTTPError) as expired_error:
                    read_json(base + "/runtime", headers={"X-Doctor-Node-Token": expired})
                self.assertEqual(401, expired_error.exception.code)
                detail = json.loads(expired_error.exception.read().decode("utf-8"))["detail"]
                self.assertEqual("INVALID_PEER_TOKEN", detail["code"])
                self.assertIn("expired", detail["message"])
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)



