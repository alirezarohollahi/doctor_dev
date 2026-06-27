from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import base64

CONFIG_ROOT = Path(os.getenv("DOCTOR_DEV_CONFIG_ROOT", "/etc/doctor_dev"))
PANEL_ENV = CONFIG_ROOT / "panel" / "panel.env"
PANEL_INSTALL = CONFIG_ROOT / "panel" / "install.json"
SERVICE = "doctor-dev-panel.service"


def run(cmd: list[str], check: bool = False) -> int:
    return subprocess.run(cmd, check=check).returncode


def parse_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value.strip().strip('"')
    return data


def panel_url() -> str:
    if PANEL_INSTALL.exists():
        try:
            data = json.loads(PANEL_INSTALL.read_text(encoding="utf-8"))
            if data.get("public_url"):
                return str(data["public_url"])
        except Exception:
            pass
    env = parse_env(PANEL_ENV)
    scheme = "https" if env.get("DOCTOR_DEV_PANEL_SSL_CERTFILE") else "http"
    host = env.get("DOCTOR_DEV_PANEL_HOST", "127.0.0.1")
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port = env.get("DOCTOR_DEV_PANEL_PORT", "8088")
    return f"{scheme}://{host}:{port}"


def request_json(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    env = parse_env(PANEL_ENV)
    url = panel_url().rstrip("/") + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    if env.get("DOCTOR_DEV_AUTH_REQUIRED", "1") in {"1", "true", "yes", "on"}:
        user = env.get("DOCTOR_DEV_ADMIN_USERNAME", "admin")
        password = env.get("DOCTOR_DEV_ADMIN_PASSWORD", "")
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def cmd_status(_: argparse.Namespace) -> None:
    print(f"Service: {SERVICE}")
    run(["systemctl", "status", SERVICE, "--no-pager"])
    try:
        print(json.dumps(request_json("/health"), indent=2))
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Health check failed: {exc}")


def cmd_start(_: argparse.Namespace) -> None:
    sys.exit(run(["systemctl", "start", SERVICE]))


def cmd_stop(_: argparse.Namespace) -> None:
    sys.exit(run(["systemctl", "stop", SERVICE]))


def cmd_restart(_: argparse.Namespace) -> None:
    sys.exit(run(["systemctl", "restart", SERVICE]))


def cmd_logs(args: argparse.Namespace) -> None:
    cmd = ["journalctl", "-u", SERVICE, "--no-pager"]
    if args.follow:
        cmd.append("-f")
    if args.lines:
        cmd.extend(["-n", str(args.lines)])
    sys.exit(run(cmd))


def cmd_config_show(_: argparse.Namespace) -> None:
    print(f"# {PANEL_ENV}")
    print(PANEL_ENV.read_text(encoding="utf-8") if PANEL_ENV.exists() else "panel env not found")
    if PANEL_INSTALL.exists():
        print(f"\n# {PANEL_INSTALL}")
        print(PANEL_INSTALL.read_text(encoding="utf-8"))


def cmd_admin_show(_: argparse.Namespace) -> None:
    path = CONFIG_ROOT / "panel" / "admin_credentials.txt"
    print(path.read_text(encoding="utf-8") if path.exists() else "admin credentials file not found")


def cmd_nodes_list(_: argparse.Namespace) -> None:
    print(json.dumps(request_json("/api/nodes"), indent=2, ensure_ascii=False))


def cmd_certs_list(_: argparse.Namespace) -> None:
    print(json.dumps(request_json("/api/certificates"), indent=2, ensure_ascii=False))


def cmd_backup_create(_: argparse.Namespace) -> None:
    import shutil
    from datetime import datetime

    backup_root = Path("/var/backups/doctor_dev")
    backup_root.mkdir(parents=True, exist_ok=True)
    name = backup_root / f"panel-backup-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.tar.gz"
    shutil.make_archive(str(name).removesuffix(".tar.gz"), "gztar", root_dir="/", base_dir="etc/doctor_dev")
    print(f"Backup created: {name}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="doctor-panel", description="Doctor Dev Panel CLI")
    sub = parser.add_subparsers(required=True)
    for name, func in [("status", cmd_status), ("start", cmd_start), ("stop", cmd_stop), ("restart", cmd_restart)]:
        p = sub.add_parser(name)
        p.set_defaults(func=func)
    p = sub.add_parser("logs")
    p.add_argument("-f", "--follow", action="store_true")
    p.add_argument("-n", "--lines", type=int, default=200)
    p.set_defaults(func=cmd_logs)
    p = sub.add_parser("config")
    p.add_argument("action", choices=["show"])
    p.set_defaults(func=cmd_config_show)
    p = sub.add_parser("admin")
    p.add_argument("action", choices=["show"])
    p.set_defaults(func=cmd_admin_show)
    p = sub.add_parser("nodes")
    p.add_argument("action", choices=["list"])
    p.set_defaults(func=cmd_nodes_list)
    p = sub.add_parser("cert")
    p.add_argument("action", choices=["list"])
    p.set_defaults(func=cmd_certs_list)
    p = sub.add_parser("backup")
    p.add_argument("action", choices=["create"])
    p.set_defaults(func=cmd_backup_create)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
