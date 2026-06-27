from __future__ import annotations

import shutil
from pathlib import Path

from install_common import (
    CONFIG_ROOT,
    DATA_ROOT,
    INSTALL_ROOT,
    LOG_ROOT,
    NODE_SERVICE_PREFIX,
    SYSTEMD_ROOT,
    ask,
    ask_int,
    ask_yes_no,
    clone_or_update_repo,
    copy_existing_cert,
    create_python_module_wrapper,
    detect_platform,
    enable_and_start,
    ensure_layout,
    generate_self_signed_cert,
    install_system_packages,
    make_uuid,
    reload_systemd,
    require_root,
    sanitize_service_part,
    save_credentials,
    setup_venv,
    stop_disable_service,
    write_env_file,
    write_json_file,
)


def service_name_for(node_name: str) -> str:
    return f"{NODE_SERVICE_PREFIX}-{sanitize_service_part(node_name)}.service"


def remove_existing_node(node_name: str, remove_data: bool) -> None:
    service = service_name_for(node_name)
    stop_disable_service(service)
    service_path = SYSTEMD_ROOT / service
    if service_path.exists():
        service_path.unlink()
        reload_systemd()
    if remove_data:
        safe_name = sanitize_service_part(node_name)
        shutil.rmtree(CONFIG_ROOT / "nodes" / safe_name, ignore_errors=True)
        shutil.rmtree(DATA_ROOT / "nodes" / safe_name, ignore_errors=True)
        shutil.rmtree(LOG_ROOT / "nodes" / safe_name, ignore_errors=True)


def configure_node_certificate(node_name: str) -> tuple[str, str]:
    print("\nNode certificate mode:")
    print("1) No API certificate")
    print("2) Existing fullchain/privkey")
    print("3) Generate self-signed certificate")
    choice = ask("Choose mode", "1")
    if choice == "2":
        fullchain = ask("Path to fullchain.pem")
        privkey = ask("Path to privkey.pem")
        cert_path, key_path = copy_existing_cert(f"node-{node_name}", fullchain, privkey)
        return str(cert_path), str(key_path)
    if choice == "3":
        common_name = ask("Certificate CN / DNS / IP", node_name)
        cert_path, key_path = generate_self_signed_cert(common_name, f"node-{node_name}")
        return str(cert_path), str(key_path)
    return "", ""


def write_node_service(node_name: str, env_file: Path) -> str:
    service_name = service_name_for(node_name)
    service = f"""[Unit]
Description=Doctor Dev Node - {node_name}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={INSTALL_ROOT}
EnvironmentFile={env_file}
ExecStart={INSTALL_ROOT}/.venv/bin/python -m doctor_dev_agent
Restart=always
RestartSec=3
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
"""
    path = SYSTEMD_ROOT / service_name
    path.write_text(service, encoding="utf-8")
    reload_systemd()
    return service_name


def parse_ports(value: str) -> list[int]:
    ports: list[int] = []
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        port = int(raw)
        if port < 1 or port > 65535:
            raise ValueError(f"invalid port: {port}")
        ports.append(port)
    if not ports:
        raise ValueError("at least one port is required")
    return ports


def main() -> None:
    require_root()
    platform = detect_platform()
    print(f"Doctor Dev Node installer | Linux={platform.distro_id} | package_manager={platform.package_manager}")

    install_system_packages()
    ensure_layout()
    clone_or_update_repo()
    setup_venv()

    node_name = ask("Node name", "edge-node-1")
    safe_name = sanitize_service_part(node_name)
    if (CONFIG_ROOT / "nodes" / safe_name / "node.env").exists() or (SYSTEMD_ROOT / service_name_for(node_name)).exists():
        print(f"A previous Node installation was detected for: {node_name}")
        if ask_yes_no("Remove this node installation and continue from a clean state?", default=False):
            remove_existing_node(node_name, remove_data=ask_yes_no("Also remove this node data/config/logs?", default=False))
        else:
            raise SystemExit("Node installation cancelled. Existing installation was not changed.")

    bind_host = ask("Node API bind host", "0.0.0.0")
    api_port = ask_int("Node API port", 9101)
    public_address = ask("Node public address or domain", "127.0.0.1")
    print("\nAPI protocol:")
    print("1) rest")
    print("2) grpc metadata only")
    proto_choice = ask("Choose protocol", "1")
    protocol = "grpc" if proto_choice == "2" else "rest"
    if protocol == "grpc":
        print("Note: current runtime API is REST; grpc is stored in config for future-compatible node metadata.")

    generated_key = make_uuid()
    api_key = ask("Node API key UUID", generated_key)

    while True:
        try:
            echo_ports = parse_ports(ask("Initial echo/test target ports CSV", "3000,3001"))
            break
        except ValueError as exc:
            print(exc)

    certfile, keyfile = configure_node_certificate(node_name)

    node_dir = CONFIG_ROOT / "nodes" / safe_name
    env_file = node_dir / "node.env"
    write_env_file(
        env_file,
        {
            "DOCTOR_DEV_NODE_NAME": node_name,
            "DOCTOR_DEV_NODE_PUBLIC_ADDRESS": public_address,
            "DOCTOR_DEV_AGENT_HOST": bind_host,
            "DOCTOR_DEV_AGENT_PORT": str(api_port),
            "DOCTOR_DEV_AGENT_API_KEY": api_key,
            "DOCTOR_DEV_AGENT_PROTOCOL": protocol,
            "DOCTOR_DEV_AGENT_DATA_DIR": str(DATA_ROOT / "nodes" / safe_name),
            "DOCTOR_DEV_LOG_DIR": str(LOG_ROOT / "nodes" / safe_name),
            "DOCTOR_DEV_AGENT_CONFIG_DIR": str(CONFIG_ROOT / "nodes" / safe_name / "generated"),
            "DOCTOR_DEV_AGENT_CERT_DIR": str(CONFIG_ROOT / "certs"),
            "DOCTOR_DEV_AGENT_SSL_CERTFILE": certfile,
            "DOCTOR_DEV_AGENT_SSL_KEYFILE": keyfile,
            "DOCTOR_DEV_ECHO_HOST": "127.0.0.1",
            "DOCTOR_DEV_ECHO_PORTS": ",".join(str(p) for p in echo_ports),
        },
    )
    write_json_file(
        node_dir / "install.json",
        {
            "role": "node",
            "node_name": node_name,
            "public_address": public_address,
            "api_port": api_port,
            "protocol": protocol,
            "service_name": service_name_for(node_name),
            "echo_ports": echo_ports,
        },
    )
    save_credentials(
        node_dir / "node_credentials.txt",
        f"Doctor Dev Node - {node_name}",
        {"Node name": node_name, "Node address": public_address, "Node API port": str(api_port), "Protocol": protocol, "API key": api_key},
    )

    create_python_module_wrapper("doctor-node", "doctor_dev_agent.cli")

    use_systemd = ask_yes_no("Install and start this node as a systemd service?", default=True)
    service_name = service_name_for(node_name)
    if use_systemd:
        service_name = write_node_service(node_name, env_file)
        enable_and_start(service_name)
    else:
        print("Manual node start command:")
        print(f"  set -a && . {env_file} && set +a && {INSTALL_ROOT}/.venv/bin/python -m doctor_dev_agent")

    print("\nNode installation completed.")
    print(f"Node name: {node_name}")
    print(f"Node API: {public_address}:{api_port}")
    print(f"Protocol: {protocol}")
    print(f"API key: {api_key}")
    print(f"Credentials file: {node_dir / 'node_credentials.txt'}")
    if use_systemd:
        print(f"Service: {service_name}")
        print(f"Logs: journalctl -u {service_name} -f")


if __name__ == "__main__":
    main()
