from __future__ import annotations

import getpass
import shutil
from pathlib import Path

from install_common import (
    BACKUP_ROOT,
    CONFIG_ROOT,
    DATA_ROOT,
    INSTALL_ROOT,
    LOG_ROOT,
    PANEL_SERVICE,
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
    issue_lets_encrypt,
    random_admin_username,
    random_password,
    reload_systemd,
    require_root,
    run,
    save_credentials,
    server_public_ip_guess,
    setup_venv,
    stop_disable_service,
    uninstall_all,
    write_env_file,
    write_json_file,
)


def existing_panel_install() -> bool:
    return (CONFIG_ROOT / "panel" / "panel.env").exists() or (SYSTEMD_ROOT / PANEL_SERVICE).exists()


def remove_existing_panel(remove_data: bool) -> None:
    stop_disable_service(PANEL_SERVICE)
    if (SYSTEMD_ROOT / PANEL_SERVICE).exists():
        (SYSTEMD_ROOT / PANEL_SERVICE).unlink()
        reload_systemd()
    if remove_data:
        shutil.rmtree(CONFIG_ROOT / "panel", ignore_errors=True)
        shutil.rmtree(DATA_ROOT / "panel", ignore_errors=True)
        shutil.rmtree(LOG_ROOT / "panel", ignore_errors=True)


def configure_certificate(mode: str, public_host: str) -> tuple[str, str, str]:
    if mode == "ip-http":
        return "", "", f"http://{public_host}"

    alias = ask("Certificate alias", public_host.replace(".", "-"))
    if mode == "domain-https":
        use_existing = ask_yes_no("Do you want to provide existing certificate files?", default=False)
        if use_existing:
            fullchain = ask("Path to fullchain.pem")
            privkey = ask("Path to privkey.pem")
            cert_path, key_path = copy_existing_cert(alias, fullchain, privkey)
        else:
            email = ask("Email for Let's Encrypt notices")
            cert_path, key_path = issue_lets_encrypt(public_host, email)
        return str(cert_path), str(key_path), f"https://{public_host}"

    use_existing = ask_yes_no("Do you want to provide certificate files for this IP?", default=True)
    if use_existing:
        fullchain = ask("Path to fullchain.pem")
        privkey = ask("Path to privkey.pem")
        cert_path, key_path = copy_existing_cert(alias, fullchain, privkey)
    else:
        print("WARNING: self-signed certificates trigger browser warnings and are not trusted by default.")
        cert_path, key_path = generate_self_signed_cert(public_host, alias)
    return str(cert_path), str(key_path), f"https://{public_host}"


def write_panel_service(env_file: Path) -> None:
    service = f"""[Unit]
Description=Doctor Dev Panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={INSTALL_ROOT}
EnvironmentFile={env_file}
ExecStart={INSTALL_ROOT}/.venv/bin/python -m doctor_dev_panel
Restart=always
RestartSec=3
KillSignal=SIGTERM
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
"""
    path = SYSTEMD_ROOT / PANEL_SERVICE
    path.write_text(service, encoding="utf-8")
    reload_systemd()


def main() -> None:
    require_root()
    platform = detect_platform()
    print(f"Doctor Dev Panel installer | Linux={platform.distro_id} | package_manager={platform.package_manager}")

    if existing_panel_install():
        print("A previous Doctor Dev Panel installation was detected.")
        if ask_yes_no("Remove the previous panel installation and continue from a clean state?", default=False):
            remove_data = ask_yes_no("Also remove panel data/config/logs?", default=False)
            remove_existing_panel(remove_data=remove_data)
        else:
            raise SystemExit("Panel installation cancelled. Existing installation was not changed.")

    install_system_packages()
    ensure_layout()
    clone_or_update_repo()
    setup_venv()

    print("\nPanel bind mode:")
    print("1) IP without certificate")
    print("2) Domain with certificate")
    print("3) IP with certificate")
    choice = ask("Choose mode", "1")
    if choice == "2":
        mode = "domain-https"
        public_host = ask("Domain name, e.g. panel.example.com")
        default_port = 443
    elif choice == "3":
        mode = "ip-https"
        public_host = ask("Public IP", server_public_ip_guess())
        default_port = 8443
    else:
        mode = "ip-http"
        public_host = ask("Public IP or bind address", server_public_ip_guess())
        default_port = 8088

    bind_host = ask("Panel bind host", "0.0.0.0")
    port = ask_int("Panel port", default_port)
    certfile, keyfile, base_url = configure_certificate(mode, public_host)
    if port not in {80, 443}:
        base_url = f"{base_url}:{port}"

    print("\nAdmin setup:")
    if ask_yes_no("Generate admin username/password automatically?", default=True):
        admin_user = random_admin_username()
        admin_password = random_password()
    else:
        admin_user = ask("Admin username", "admin")
        password_1 = getpass.getpass("Admin password: ")
        password_2 = getpass.getpass("Repeat admin password: ")
        if password_1 != password_2 or not password_1:
            raise SystemExit("Admin passwords do not match or are empty.")
        admin_password = password_1

    panel_env = CONFIG_ROOT / "panel" / "panel.env"
    write_env_file(
        panel_env,
        {
            "DOCTOR_DEV_PANEL_HOST": bind_host,
            "DOCTOR_DEV_PANEL_PORT": str(port),
            "DOCTOR_DEV_PANEL_PUBLIC_URL": base_url,
            "DOCTOR_DEV_AUTH_REQUIRED": "1",
            "DOCTOR_DEV_ADMIN_USERNAME": admin_user,
            "DOCTOR_DEV_ADMIN_PASSWORD": admin_password,
            "DOCTOR_DEV_DATA_DIR": str(DATA_ROOT / "panel"),
            "DOCTOR_DEV_LOG_DIR": str(LOG_ROOT / "panel"),
            "DOCTOR_DEV_CONFIG_DIR": str(CONFIG_ROOT / "panel" / "generated"),
            "DOCTOR_DEV_CERT_DIR": str(CONFIG_ROOT / "certs"),
            "DOCTOR_DEV_PANEL_SSL_CERTFILE": certfile,
            "DOCTOR_DEV_PANEL_SSL_KEYFILE": keyfile,
        },
    )
    write_json_file(
        CONFIG_ROOT / "panel" / "install.json",
        {
            "role": "panel",
            "mode": mode,
            "public_url": base_url,
            "bind_host": bind_host,
            "port": port,
            "config_root": str(CONFIG_ROOT),
            "data_root": str(DATA_ROOT),
            "log_root": str(LOG_ROOT),
            "backup_root": str(BACKUP_ROOT),
        },
    )
    save_credentials(
        CONFIG_ROOT / "panel" / "admin_credentials.txt",
        "Doctor Dev Panel Admin",
        {"Panel URL": base_url, "Admin username": admin_user, "Admin password": admin_password},
    )

    create_python_module_wrapper("doctor-panel", "doctor_dev_panel.cli")

    use_systemd = ask_yes_no("Install and start the panel as a systemd service?", default=True)
    if use_systemd:
        write_panel_service(panel_env)
        enable_and_start(PANEL_SERVICE)
    else:
        print("Manual panel start command:")
        print(f"  set -a && . {panel_env} && set +a && {INSTALL_ROOT}/.venv/bin/python -m doctor_dev_panel")

    install_node_here = ask_yes_no("Do you want to install a Node on this server too?", default=False)
    if install_node_here:
        node_installer = INSTALL_ROOT / "scripts" / "install_node.py"
        run([str(INSTALL_ROOT / ".venv" / "bin" / "python"), str(node_installer)])

    print("\nPanel installation completed.")
    print(f"Panel URL: {base_url}")
    print(f"Admin username: {admin_user}")
    print(f"Admin password: {admin_password}")
    print(f"Credentials file: {CONFIG_ROOT / 'panel' / 'admin_credentials.txt'}")
    if use_systemd:
        print(f"Service: {PANEL_SERVICE}")
        print(f"Logs: journalctl -u {PANEL_SERVICE} -f")


if __name__ == "__main__":
    main()
