import asyncio
import socket

from doctor_dev_agent.echo_server import start_echo_server
from doctor_dev_agent.tunnel_engine import TunnelManager
from doctor_dev_panel.local_test import tls_roundtrip


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_phase7_runtime_tls_listener_roundtrip():
    async def run() -> None:
        tls_port = free_port()
        echo_port = free_port()
        logs: list[tuple[str, str]] = []

        echo_server = await start_echo_server("127.0.0.1", echo_port, lambda level, message: logs.append((level, message)), label="phase7-test")
        manager = TunnelManager(lambda level, message: logs.append((level, message)))
        try:
            config = {
                "version": "doctor-dev.phase7.v1",
                "node_id": "node_test",
                "core_id": "core_tls",
                "core_name": "phase7-tls-runtime-test",
                "enabled": True,
                "advanced_config": {},
                "inbounds": [
                    {
                        "id": "inbound_tls",
                        "name": "tls-entry",
                        "type": "tunnel",
                        "protocol": "tcp",
                        "enabled": True,
                        "listeners": [
                            {"id": "listener_tls", "listen_ip": "127.0.0.1", "listen_port": tls_port, "port_mode": "fixed", "enabled": True}
                        ],
                        "tls": {
                            "enabled": True,
                            "mode": "file_on_panel",
                            "domain": "local.test",
                            "fullchain_path": "certs/local.test/fullchain.pem",
                            "privkey_path": "certs/local.test/privkey.pem",
                        },
                        "limits": {"max_users": 10, "max_active_connections": 5},
                        "route_id": "route_tls",
                    }
                ],
                "routes": [
                    {
                        "id": "route_tls",
                        "name": "tls-to-echo",
                        "balancer": "round_robin",
                        "fallback_behavior": "error",
                        "enabled": True,
                        "targets": [{"id": "target_echo", "type": "static", "enabled": True, "host": "127.0.0.1", "ports": [echo_port], "priority": 10, "weight": 1}],
                    }
                ],
            }
            warnings = await manager.apply(config)
            assert warnings == []
            assert manager.snapshot()["running_listeners"] == 1
            result = await asyncio.to_thread(tls_roundtrip, "127.0.0.1", tls_port, "hello-phase7-test", 5.0, False)
            assert result["ok"] is True
            assert result["mode"] == "tls"
            assert "doctor-dev-echo:phase7-test:hello-phase7-test" in result["response_text"]
            metrics = manager.snapshot()["metrics"]
            assert metrics["inbounds"]["inbound_tls"]["tls_enabled"] is True
        finally:
            await manager.stop()
            echo_server.close()
            await echo_server.wait_closed()

    asyncio.run(run())
