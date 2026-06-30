
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


    def test_node_inbound_endpoint_option_label_hides_runtime_port(self) -> None:
        app_js = (PROJECT_ROOT / "doctor_dev_panel" / "web" / "assets" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function inboundOptionLabel(item)", app_js)
        label_block = app_js.split("function inboundOptionLabel(item)", 1)[1].split("function endpointInboundOptions", 1)[0]
        self.assertNotIn("item.ports.join", label_block)
        self.assertNotIn("random ×", label_block)


    def test_node_level_runtime_interval_is_removed_from_ui_and_schema(self) -> None:
        index_html = (PROJECT_ROOT / "doctor_dev_panel" / "web" / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "doctor_dev_panel" / "web" / "assets" / "js" / "app.js").read_text(encoding="utf-8")
        schemas = (PROJECT_ROOT / "doctor_dev_panel" / "schemas.py").read_text(encoding="utf-8")
        self.assertNotIn("nodeUpdateInterval", index_html)
        self.assertNotIn("nodeUpdateInterval", app_js)
        node_body = schemas.split("class NodeBody", 1)[1].split("class CoreInboundBody", 1)[0]
        self.assertNotIn("update_interval", node_body)

    def test_dependency_level_sync_interval_is_present(self) -> None:
        app_js = (PROJECT_ROOT / "doctor_dev_panel" / "web" / "assets" / "js" / "app.js").read_text(encoding="utf-8")
        schemas = (PROJECT_ROOT / "doctor_dev_panel" / "schemas.py").read_text(encoding="utf-8")
        dep_body = schemas.split("class CoreDependencyBody", 1)[1].split("class CoreAdvancedConfigBody", 1)[0]
        self.assertIn("sync_interval", dep_body)
        self.assertIn("Sync Interval", app_js)
        self.assertIn("data-field=\"sync_interval\"", app_js)

    def test_build_config_uses_dependency_sync_interval_for_peer_sync(self) -> None:
        from doctor_dev_panel.stores import core_store, node_store
        from doctor_dev_panel.stores.core_store import build_node_config, create_core
        from doctor_dev_panel.stores.node_store import create_node

        with tempfile.TemporaryDirectory() as tmp:
            old = {
                "DOCTOR_DEV_NODES_PATH": os.environ.get("DOCTOR_DEV_NODES_PATH"),
                "DOCTOR_DEV_CORES_PATH": os.environ.get("DOCTOR_DEV_CORES_PATH"),
                "DOCTOR_DEV_NODE_RUNTIME_CACHE_PATH": os.environ.get("DOCTOR_DEV_NODE_RUNTIME_CACHE_PATH"),
                "PUBLIC_HOST": os.environ.get("PUBLIC_HOST"),
                "PUBLIC_SCHEME": os.environ.get("PUBLIC_SCHEME"),
                "PORT": os.environ.get("PORT"),
            }
            try:
                os.environ["DOCTOR_DEV_NODES_PATH"] = str(Path(tmp) / "nodes.json")
                os.environ["DOCTOR_DEV_CORES_PATH"] = str(Path(tmp) / "cores.json")
                os.environ["DOCTOR_DEV_NODE_RUNTIME_CACHE_PATH"] = str(Path(tmp) / "runtime.json")
                os.environ["PUBLIC_HOST"] = "127.0.0.1"
                os.environ["PUBLIC_SCHEME"] = "http"
                os.environ["PORT"] = "9000"

                node_a = create_node({"name": "A", "address": "127.0.0.1", "api_port": 9001, "api_key": "a"})
                node_b = create_node({"name": "B", "address": "127.0.0.1", "api_port": 9002, "api_key": "b"})
                core_a = create_core({
                    "name": "Core A",
                    "node_id": node_a["id"],
                    "enabled": True,
                    "inbounds": [{
                        "name": "a-in",
                        "enabled": True,
                        "bind_ip": "0.0.0.0",
                        "port_mode": "fixed",
                        "fixed_ports": [1211, 1212],
                        "target_type": "static",
                        "target_host": "127.0.0.1",
                        "target_port": 9101,
                    }],
                    "balancers": [],
                    "dependencies": [],
                })
                create_core({
                    "name": "Core B",
                    "node_id": node_b["id"],
                    "enabled": True,
                    "dependencies": [{"type": "node", "ref_id": node_a["id"], "sync_interval": 3, "required": True}],
                    "inbounds": [],
                    "balancers": [{
                        "alias": "b-to-a",
                        "strategy": "round_robin",
                        "enabled": True,
                        "endpoints": [{
                            "type": "node_inbound",
                            "node_id": node_a["id"],
                            "core_id": core_a["id"],
                            "inbound_name": "a-in",
                            "weight": 1,
                            "enabled": True,
                        }],
                    }],
                })
                config = build_node_config(node_b["id"])
                core_b_cfg = config["cores"][0]
                dep = core_b_cfg["dependencies"][0]
                endpoint = core_b_cfg["balancers"][0]["endpoints"][0]
                self.assertEqual(3, dep["sync_interval"])
                self.assertEqual(3, endpoint["sync_interval"])
                self.assertEqual(core_a["id"], dep["remote_core_id"])
                self.assertIn("token_url", dep)
                self.assertIn("sync_urls", dep)
                self.assertNotIn("update_interval", dep)
                self.assertNotIn("update_interval", endpoint)
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


    def test_self_node_dependency_is_filtered(self) -> None:
        from doctor_dev_panel.stores.core_store import normalize_core

        core = normalize_core({
            "name": "Core B",
            "node_id": "node-b",
            "dependencies": [
                {"type": "node", "ref_id": "node-b", "sync_interval": 5, "required": True},
                {"type": "node", "ref_id": "node-a", "sync_interval": 7, "required": True},
            ],
        })

        self.assertEqual(1, len(core["dependencies"]))
        self.assertEqual("node-a", core["dependencies"][0]["ref_id"])

    def test_legacy_nodes_get_persistent_peer_verify_secret(self) -> None:
        from doctor_dev_panel.stores.node_store import get_node, list_nodes

        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("DOCTOR_DEV_NODES_PATH")
            try:
                store = Path(tmp) / "nodes.json"
                os.environ["DOCTOR_DEV_NODES_PATH"] = str(store)
                store.write_text(
                    '{"version":4,"nodes":[{"id":"node_1111111111111111","name":"legacy","address":"127.0.0.1","api_port":9001,"api_key":"k","enabled":true}]}\n',
                    encoding="utf-8",
                )
                first = get_node("node_1111111111111111")
                second = get_node("node_1111111111111111")
                self.assertTrue(first and first.get("peer_verify_secret"))
                self.assertEqual(first.get("peer_verify_secret"), second.get("peer_verify_secret"))
                persisted = store.read_text(encoding="utf-8")
                self.assertIn("peer_verify_secret", persisted)
                self.assertEqual(1, len(list_nodes()))
            finally:
                if old is None:
                    os.environ.pop("DOCTOR_DEV_NODES_PATH", None)
                else:
                    os.environ["DOCTOR_DEV_NODES_PATH"] = old


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


    def test_node_inbound_endpoint_resolves_all_live_ports_with_endpoint_level_weight(self) -> None:
        from doctor_dev_node.runtime import ForwarderRuntime

        rt = ForwarderRuntime()
        rt.config = {"node_id": "node-b", "cores": []}
        core = {
            "name": "core-b",
            "balancers": [
                {
                    "alias": "b-to-a",
                    "strategy": "round_robin",
                    "endpoints": [
                        {
                            "type": "node_inbound",
                            "node_id": "node-a",
                            "remote_node_id": "node-a",
                            "core_id": "core-a",
                            "remote_core_id": "core-a",
                            "inbound_name": "a-one",
                            "remote_inbound_name": "a-one",
                            "host": "127.0.0.1",
                            "live_ports": [1209, 1210, 1213],
                            "live_ports_synced_at_unix": 20,
                            "weight": 1,
                        },
                        {
                            "type": "node_inbound",
                            "node_id": "node-a",
                            "remote_node_id": "node-a",
                            "core_id": "core-a",
                            "remote_core_id": "core-a",
                            "inbound_name": "a-two",
                            "remote_inbound_name": "a-two",
                            "host": "127.0.0.1",
                            "live_ports": [1212],
                            "live_ports_synced_at_unix": 20,
                            "weight": 1,
                        },
                    ],
                }
            ],
        }
        inbound = {"name": "b-in", "target_type": "balancer", "target_balancer": "b-to-a"}
        selected_first_ports = [rt._resolve_targets(core, inbound)[0].port for _ in range(6)]
        self.assertEqual([1209, 1212, 1210, 1212, 1213, 1212], selected_first_ports)

    def test_node_inbound_endpoint_prefers_newer_panel_live_ports_over_stale_peer_cache(self) -> None:
        from doctor_dev_node.runtime import ForwarderRuntime

        rt = ForwarderRuntime()
        rt.config = {"node_id": "node-b", "cores": []}
        endpoint = {
            "type": "node_inbound",
            "node_id": "node-a",
            "remote_node_id": "node-a",
            "core_id": "core-a",
            "remote_core_id": "core-a",
            "inbound_name": "a-one",
            "remote_inbound_name": "a-one",
            "host": "127.0.0.1",
            "live_ports": [1209],
            "live_ports_synced_at_unix": 20,
        }
        rt._peer_runtime_cache["node-a"] = {
            "synced_at_unix": 10,
            "listeners": [
                {"status": "listening", "core_id": "core-a", "inbound_name": "a-one", "port": 1211},
            ],
        }
        self.assertEqual([1209], [t.port for t in rt._targets_from_endpoint(endpoint)])
        endpoint["live_ports_synced_at_unix"] = 5
        self.assertEqual([1211], [t.port for t in rt._targets_from_endpoint(endpoint)])

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



