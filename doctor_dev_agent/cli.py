from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

CONFIG_ROOT = Path(os.getenv("DOCTOR_DEV_CONFIG_ROOT", "/etc/doctor_dev"))
SERVICE_PREFIX = "doctor-dev-node"


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


def node_dir(name: str | None) -> Path:
    base = CONFIG_ROOT / "nodes"
    if name:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in name.lower()).strip("-")
        return base / safe
    candidates = sorted(path for path in base.iterdir() if path.is_dir()) if base.exists() else []
    if not candidates:
        raise SystemExit("No node config found. Pass --name or install a node first.")
    return candidates[0]


def service_name(name: str | None) -> str:
    d = node_dir(name)
    install = d / "install.json"
    if install.exists():
        try:
            data = json.loads(install.read_text(encoding="utf-8"))
            if data.get("service_name"):
                return data["service_name"]
        except Exception:
            pass
    return f"{SERVICE_PREFIX}-{d.name}.service"


def env_file(name: str | None) -> Path:
    return node_dir(name) / "node.env"


def api_url(name: str | None) -> str:
    env = parse_env(env_file(name))
    scheme = "https" if env.get("DOCTOR_DEV_AGENT_SSL_CERTFILE") else "http"
    host = env.get("DOCTOR_DEV_AGENT_HOST", "127.0.0.1")
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port = env.get("DOCTOR_DEV_AGENT_PORT", "9101")
    return f"{scheme}://{host}:{port}"


def request_json(name: str | None, path: str) -> dict:
    env = parse_env(env_file(name))
    req = Request(api_url(name).rstrip("/") + path)
    req.add_header("Authorization", f"Bearer {env.get('DOCTOR_DEV_AGENT_API_KEY', '')}")
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def cmd_status(args: argparse.Namespace) -> None:
    svc = service_name(args.name)
    print(f"Service: {svc}")
    run(["systemctl", "status", svc, "--no-pager"])
    try:
        print(json.dumps(request_json(args.name, "/health"), indent=2))
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Health check failed: {exc}")


def cmd_service(args: argparse.Namespace) -> None:
    sys.exit(run(["systemctl", args.command, service_name(args.name)]))


def cmd_logs(args: argparse.Namespace) -> None:
    cmd = ["journalctl", "-u", service_name(args.name), "--no-pager"]
    if args.follow:
        cmd.append("-f")
    if args.lines:
        cmd.extend(["-n", str(args.lines)])
    sys.exit(run(cmd))


def cmd_config_show(args: argparse.Namespace) -> None:
    path = env_file(args.name)
    print(f"# {path}")
    print(path.read_text(encoding="utf-8") if path.exists() else "node env not found")
    install = node_dir(args.name) / "install.json"
    if install.exists():
        print(f"\n# {install}")
        print(install.read_text(encoding="utf-8"))


def cmd_runtime(args: argparse.Namespace) -> None:
    print(json.dumps(request_json(args.name, "/runtime"), indent=2, ensure_ascii=False))


def cmd_health(args: argparse.Namespace) -> None:
    print(json.dumps(request_json(args.name, "/health"), indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="doctor-node", description="Doctor Dev Node CLI")
    parser.add_argument("--name", help="Node name. If omitted, the first installed node config is used.")
    sub = parser.add_subparsers(required=True)
    p = sub.add_parser("status")
    p.set_defaults(func=cmd_status)
    for command in ["start", "stop", "restart"]:
        p = sub.add_parser(command)
        p.set_defaults(func=cmd_service, command=command)
    p = sub.add_parser("logs")
    p.add_argument("-f", "--follow", action="store_true")
    p.add_argument("-n", "--lines", type=int, default=200)
    p.set_defaults(func=cmd_logs)
    p = sub.add_parser("config")
    p.add_argument("action", choices=["show"])
    p.set_defaults(func=cmd_config_show)
    p = sub.add_parser("runtime")
    p.set_defaults(func=cmd_runtime)
    p = sub.add_parser("health")
    p.set_defaults(func=cmd_health)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
