from __future__ import annotations

import asyncio
import os
import logging
import socket
import tempfile
import unittest
from pathlib import Path


logging.disable(logging.CRITICAL)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StaticQualityTests(unittest.TestCase):
    def test_removed_data_dump_feature_terms_are_absent(self) -> None:
        # The removed data-dump feature should not leave UI, docs, script, or code references.
        terms = [
            "back" + "up",
            "Back" + "up",
            "BACK" + "UP",
            "بک" + "اپ",
            "بک" + "\u200c" + "آپ",
            "پشتی" + "بان",
            "پشتی" + "بان" + "\u200c" + "گیری",
        ]
        ignored_parts = {".git", ".venv", "venv", "logs", "data", "run", "__pycache__", "dist", "build"}
        ignored_suffixes = {".pyc", ".pyo", ".zip", ".png", ".jpg", ".jpeg", ".webp", ".ico"}
        hits: list[str] = []
        for path in PROJECT_ROOT.rglob("*"):
            if not path.is_file():
                continue
            rel_parts = path.relative_to(PROJECT_ROOT).parts
            if ignored_parts.intersection(rel_parts):
                continue
            if path.suffix.lower() in ignored_suffixes:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for term in terms:
                if term in text:
                    hits.append(str(path.relative_to(PROJECT_ROOT)))
                    break
        self.assertEqual([], hits)

    def test_runtime_uses_pydantic_v2_requirements(self) -> None:
        requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("pydantic==2.5.3", requirements)
        self.assertNotIn("pydantic==1", requirements)

    def test_panel_node_control_logic_is_outside_app_module(self) -> None:
        app_text = (PROJECT_ROOT / "doctor_dev_panel" / "app.py").read_text(encoding="utf-8")
        service_text = (PROJECT_ROOT / "doctor_dev_panel" / "services" / "node_control.py").read_text(encoding="utf-8")
        self.assertNotIn("urlopen", app_text)
        self.assertNotIn("Request(", app_text)
        self.assertIn("def read_node_api", service_text)
        self.assertIn("def post_node_api", service_text)
        self.assertIn("def read_node_export", service_text)


    def test_panel_app_imports_and_uses_route_modules(self) -> None:
        from doctor_dev_panel.app import app

        routes = {(getattr(route, "path", ""), tuple(sorted(getattr(route, "methods", []) or []))) for route in app.routes}
        self.assertIn(("/api/auth/login", ("POST",)), routes)
        self.assertIn(("/api/nodes", ("GET",)), routes)
        self.assertIn(("/api/cores", ("GET",)), routes)
        self.assertIn(("/api/logs", ("GET",)), routes)
        self.assertIn(("/health", ("GET",)), routes)

        app_text = (PROJECT_ROOT / "doctor_dev_panel" / "app.py").read_text(encoding="utf-8")
        self.assertIn("app.include_router(auth_router)", app_text)
        self.assertIn("app.include_router(nodes_router)", app_text)
        self.assertIn("app.include_router(cores_router)", app_text)
        self.assertNotIn("@app.post(\"/api/nodes", app_text)
        self.assertNotIn("@app.post(\"/api/cores", app_text)

    def test_legacy_fixed_node_data_port_is_not_in_env_examples(self) -> None:
        for rel in ("env.examples/node.env", "node.env.example"):
            text = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("API_PORT=", text)
            self.assertNotIn("SERVICE_PORT=", text)
            self.assertNotIn("SERVICE_PROTOCOL=", text)


class NodeRuntimeContractTests(unittest.TestCase):
    def test_api_identity_reports_actual_bound_port(self) -> None:
        from doctor_dev_node.server import api_identity

        old = {key: os.environ.get(key) for key in ("DOCTOR_DEV_NODE_BOUND_HOST", "DOCTOR_DEV_NODE_BOUND_API_PORT", "NODE_HOST", "API_PORT")}
        try:
            os.environ["NODE_HOST"] = "0.0.0.0"
            os.environ["API_PORT"] = "62051"
            os.environ["DOCTOR_DEV_NODE_BOUND_HOST"] = "127.0.0.1"
            os.environ["DOCTOR_DEV_NODE_BOUND_API_PORT"] = "9098"
            identity = api_identity()
            self.assertEqual("127.0.0.1", identity["host"])
            self.assertEqual(9098, identity["port"])
            self.assertEqual(9098, identity["api_port"])
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_peer_token_target_and_expiry_checks(self) -> None:
        from doctor_dev_node.peer_tokens import issue_peer_token, verify_peer_token

        token = issue_peer_token(
            secret="secret-1",
            source_node_id="node-a",
            source_core_id="core-a",
            target_node_id="node-b",
            target_core_id="core-b",
            ttl_seconds=60,
        )
        payload = verify_peer_token(token, secret="secret-1", target_node_id="node-b", target_core_id="core-b")
        self.assertEqual("node-a", payload["source_node_id"])
        with self.assertRaises(ValueError):
            verify_peer_token(token, secret="secret-1", target_node_id="node-x", target_core_id="core-b")
        with self.assertRaises(ValueError):
            verify_peer_token(token, secret="wrong-secret", target_node_id="node-b", target_core_id="core-b")

    def test_failed_apply_rolls_back_previous_runtime(self) -> None:
        async def scenario() -> None:
            from doctor_dev_node import server
            from doctor_dev_node.runtime import runtime

            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                old_env = {key: os.environ.get(key) for key in ("API_KEY", "DOCTOR_DEV_NODE_DATA_DIR", "DOCTOR_DEV_NODE_ROUTING_CONFIG", "DOCTOR_DEV_NODE_LOG_DIR", "DOCTOR_DEV_NODE_LOG_FILE")}
                try:
                    os.environ["API_KEY"] = "test-key"
                    os.environ["DOCTOR_DEV_NODE_DATA_DIR"] = str(tmp_path / "data")
                    os.environ["DOCTOR_DEV_NODE_ROUTING_CONFIG"] = str(tmp_path / "data" / "routing.json")
                    os.environ["DOCTOR_DEV_NODE_LOG_DIR"] = str(tmp_path / "logs")
                    os.environ["DOCTOR_DEV_NODE_LOG_FILE"] = str(tmp_path / "logs" / "node.log")
                    await runtime.stop()

                    valid = {
                        "version": 1,
                        "node_id": "node-test",
                        "generated_at": "test",
                        "cores": [
                            {
                                "id": "core-1",
                                "name": "core-1",
                                "enabled": True,
                                "dependencies": [],
                                "balancers": [],
                                "inbounds": [
                                    {
                                        "name": "inbound-random",
                                        "enabled": True,
                                        "bind_ip": "127.0.0.1",
                                        "port_mode": "random",
                                        "random_count": 1,
                                        "target_type": "static",
                                        "target_host": "127.0.0.1",
                                        "target_port": 9,
                                    }
                                ],
                            }
                        ],
                    }
                    ok = await server.apply_config(server.ApplyConfigBody(**valid), authorization="Bearer test-key")
                    self.assertTrue(ok["ok"])
                    self.assertTrue(runtime.summary()["runtime_active"])

                    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    blocker.bind(("127.0.0.1", 0))
                    blocker.listen(1)
                    occupied_port = blocker.getsockname()[1]
                    try:
                        bad = {
                            "version": 1,
                            "node_id": "node-test",
                            "generated_at": "test-bad",
                            "cores": [
                                {
                                    "id": "core-1",
                                    "name": "core-1",
                                    "enabled": True,
                                    "dependencies": [],
                                    "balancers": [],
                                    "inbounds": [
                                        {
                                            "name": "inbound-fixed-busy",
                                            "enabled": True,
                                            "bind_ip": "127.0.0.1",
                                            "port_mode": "fixed",
                                            "fixed_ports": [occupied_port],
                                            "target_type": "static",
                                            "target_host": "127.0.0.1",
                                            "target_port": 9,
                                        }
                                    ],
                                }
                            ],
                        }
                        result = await server.apply_config(server.ApplyConfigBody(**bad), authorization="Bearer test-key")
                        self.assertFalse(result["ok"])
                        self.assertTrue(result["previous_runtime_kept"])
                        self.assertTrue(runtime.summary()["runtime_active"])
                        listeners = runtime.summary().get("listeners", [])
                        self.assertTrue(any(item.get("inbound_name") == "inbound-random" and item.get("status") == "listening" for item in listeners))
                    finally:
                        blocker.close()
                finally:
                    await runtime.stop()
                    for key, value in old_env.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main(verbosity=2)
