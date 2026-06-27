from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import ssl
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CONFIG_ROOT = Path(os.getenv("DOCTOR_DEV_CONFIG_ROOT", "/etc/doctor_dev"))
INSTALL_ROOT = Path(os.getenv("DOCTOR_DEV_INSTALL_ROOT", "/opt/doctor_dev"))
DEFAULT_REPO_URL = os.getenv("DOCTOR_DEV_REPO_URL", "https://github.com/alirezarohollahi/doctor_dev")
SYSTEMD_ROOT = Path("/etc/systemd/system")
SERVICE_PREFIX = "doctor-dev-node"
BACKUP_ROOT = Path("/var/backups/doctor_dev")

SENSITIVE_KEYS = {"PASSWORD", "SECRET", "TOKEN", "KEY", "API_KEY"}
NODE_CONFIG_HELP: dict[str, str] = {
    "DOCTOR_DEV_NODE_NAME": "Node display name",
    "DOCTOR_DEV_NODE_PUBLIC_ADDRESS": "Public IP/domain used by panel and other nodes",
    "DOCTOR_DEV_AGENT_HOST": "Node API bind host",
    "DOCTOR_DEV_AGENT_PORT": "Node API port, 1..65535",
    "DOCTOR_DEV_AGENT_API_KEY": "Bearer API key UUID",
    "DOCTOR_DEV_AGENT_PROTOCOL": "rest or grpc metadata",
    "DOCTOR_DEV_AGENT_DATA_DIR": "Node data directory",
    "DOCTOR_DEV_LOG_DIR": "Node log directory",
    "DOCTOR_DEV_AGENT_CONFIG_DIR": "Generated config directory",
    "DOCTOR_DEV_AGENT_CERT_DIR": "Certificate storage directory",
    "DOCTOR_DEV_AGENT_SSL_CERTFILE": "Node API TLS fullchain.pem path",
    "DOCTOR_DEV_AGENT_SSL_KEYFILE": "Node API TLS privkey.pem path",
    "DOCTOR_DEV_ECHO_HOST": "Internal echo/test host",
    "DOCTOR_DEV_ECHO_PORTS": "CSV ports for internal echo/test servers",
}
PATH_KEYS = {
    "DOCTOR_DEV_AGENT_DATA_DIR",
    "DOCTOR_DEV_LOG_DIR",
    "DOCTOR_DEV_AGENT_CONFIG_DIR",
    "DOCTOR_DEV_AGENT_CERT_DIR",
    "DOCTOR_DEV_AGENT_SSL_CERTFILE",
    "DOCTOR_DEV_AGENT_SSL_KEYFILE",
}
PORT_KEYS = {"DOCTOR_DEV_AGENT_PORT"}
INT_KEYS = {"DOCTOR_DEV_AGENT_PORT"}


def run(cmd: list[str], check: bool = False, cwd: Path | None = None) -> int:
    return subprocess.run(cmd, check=check, cwd=str(cwd) if cwd else None).returncode


def run_text(cmd: list[str], check: bool = True, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        cmd,
        check=check,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout.strip()


def parse_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value.strip().strip('"').strip("'")
    return data


def quote_env(value: str) -> str:
    if value == "":
        return ""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_env(path: Path, data: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Managed by doctor-node CLI. Keep a backup before manual edits."]
    for key in sorted(data):
        lines.append(f"{key}={quote_env(str(data[key]))}")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def backup_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup_dir = BACKUP_ROOT / "config-edits"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, backup)
    return backup


def sanitize_path(value: str) -> str:
    value = value.strip().strip('"').strip("'").strip()
    while value.endswith("\\") and not value.endswith("\\\\"):
        value = value[:-1].rstrip()
    return str(Path(os.path.expandvars(os.path.expanduser(value))).resolve()) if value else ""


def parse_ports(value: str) -> str:
    ports: list[int] = []
    for raw in value.split(","):
        raw = raw.strip().strip("\\")
        if not raw:
            continue
        try:
            port = int(raw)
        except ValueError as exc:
            raise SystemExit(f"Invalid port: {raw}") from exc
        if not (1 <= port <= 65535):
            raise SystemExit(f"Invalid port: {port}. Ports must be between 1 and 65535")
        ports.append(port)
    if not ports:
        raise SystemExit("At least one port is required")
    return ",".join(str(port) for port in ports)


def validate_config_value(key: str, value: str) -> str:
    if key in PATH_KEYS:
        value = sanitize_path(value)
    if key in INT_KEYS:
        try:
            ivalue = int(value)
        except ValueError as exc:
            raise SystemExit(f"{key} must be an integer") from exc
        if key in PORT_KEYS and not (1 <= ivalue <= 65535):
            raise SystemExit(f"{key} must be between 1 and 65535")
        value = str(ivalue)
    if key == "DOCTOR_DEV_AGENT_PROTOCOL" and value not in {"rest", "grpc"}:
        raise SystemExit("DOCTOR_DEV_AGENT_PROTOCOL must be rest or grpc")
    if key == "DOCTOR_DEV_AGENT_API_KEY":
        try:
            uuid.UUID(value)
        except ValueError as exc:
            raise SystemExit("DOCTOR_DEV_AGENT_API_KEY must be a valid UUID") from exc
    if key == "DOCTOR_DEV_ECHO_PORTS":
        value = parse_ports(value)
    if key in {"DOCTOR_DEV_AGENT_SSL_CERTFILE", "DOCTOR_DEV_AGENT_SSL_KEYFILE"} and value and not Path(value).exists():
        raise SystemExit(f"File does not exist: {value}")
    if key in {"DOCTOR_DEV_NODE_NAME", "DOCTOR_DEV_NODE_PUBLIC_ADDRESS"} and not value:
        raise SystemExit(f"{key} cannot be empty")
    return value


def redact(key: str, value: str, show_secrets: bool = False) -> str:
    if show_secrets:
        return value
    upper = key.upper()
    if any(marker in upper for marker in SENSITIVE_KEYS) and value:
        return value[:4] + "..." + value[-4:] if len(value) > 10 else "********"
    return value


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
    url = api_url(name).rstrip("/") + path
    req = Request(url)
    req.add_header("Authorization", f"Bearer {env.get('DOCTOR_DEV_AGENT_API_KEY', '')}")
    ctx = ssl._create_unverified_context() if url.startswith("https://") else None
    with urlopen(req, timeout=10, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def service_action(action: str, name: str | None) -> None:
    if shutil.which("systemctl"):
        sys.exit(run(["systemctl", action, service_name(name)]))
    raise SystemExit("systemctl was not found. Start/restart the node manually.")



def require_update_ready() -> None:
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise SystemExit("Update must be run as root: sudo doctor-node update")
    if not INSTALL_ROOT.exists():
        raise SystemExit(f"Install root not found: {INSTALL_ROOT}")
    if not (INSTALL_ROOT / ".git").exists():
        raise SystemExit(f"Install root is not a git checkout: {INSTALL_ROOT}")
    if not shutil.which("git"):
        raise SystemExit("git was not found. Install git first.")


def git_current_branch() -> str:
    branch = run_text(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=INSTALL_ROOT, check=False)
    if not branch or branch == "HEAD":
        return "master"
    return branch


def git_current_commit() -> str:
    return run_text(["git", "rev-parse", "--short", "HEAD"], cwd=INSTALL_ROOT, check=False) or "unknown"


def git_has_dirty_worktree() -> bool:
    return bool(run_text(["git", "status", "--porcelain"], cwd=INSTALL_ROOT, check=False))


def backup_configs(label: str) -> Path | None:
    if not CONFIG_ROOT.exists():
        return None
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    archive_base = BACKUP_ROOT / f"{label}-config-backup-{stamp}"
    shutil.make_archive(str(archive_base), "gztar", root_dir="/", base_dir="etc/doctor_dev")
    return archive_base.with_suffix(".tar.gz")


def list_node_service_names() -> list[str]:
    services: list[str] = []
    if SYSTEMD_ROOT.exists():
        services.extend(path.name for path in SYSTEMD_ROOT.glob("doctor-dev-node-*.service"))
    return sorted(set(services))


def systemctl_service(action: str, service: str) -> int:
    if not shutil.which("systemctl"):
        print(f"systemctl not found; skipped {action} for {service}")
        return 0
    print(f"systemctl {action} {service}")
    return run(["systemctl", action, service])


def reinstall_python_package() -> None:
    python = INSTALL_ROOT / ".venv" / "bin" / "python"
    pip = INSTALL_ROOT / ".venv" / "bin" / "pip"
    if not python.exists():
        run([sys.executable, "-m", "venv", str(INSTALL_ROOT / ".venv")], check=True)
    if not pip.exists():
        pip = python.parent / "pip"
    run([str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], check=True)
    req = INSTALL_ROOT / "requirements.txt"
    if req.exists():
        run([str(pip), "install", "-r", str(req)], check=True)
    run([str(pip), "install", "-e", str(INSTALL_ROOT)], check=True)


def perform_git_update(args: argparse.Namespace, label: str) -> tuple[str, str, Path | None]:
    require_update_ready()
    branch = args.branch or git_current_branch()
    before = git_current_commit()
    if args.repo_url:
        run(["git", "remote", "set-url", "origin", args.repo_url], cwd=INSTALL_ROOT, check=True)
    run(["git", "fetch", "origin", branch], cwd=INSTALL_ROOT, check=True)
    target = f"origin/{branch}"
    after_remote = run_text(["git", "rev-parse", "--short", target], cwd=INSTALL_ROOT, check=False) or "unknown"
    if args.dry_run:
        print(f"Install root: {INSTALL_ROOT}")
        print(f"Current commit: {before}")
        print(f"Remote target: {target} ({after_remote})")
        print("Pending commits:")
        log = run_text(["git", "log", "--oneline", f"HEAD..{target}"], cwd=INSTALL_ROOT, check=False)
        print(log or "  No pending commits.")
        return before, after_remote, None
    if git_has_dirty_worktree() and not args.force:
        raise SystemExit(
            "Local changes were found under /opt/doctor_dev. Commit/stash them first, "
            "or run update with --force to reset to the remote branch."
        )
    backup = None if args.no_backup else backup_configs(label)
    if args.force:
        run(["git", "checkout", branch], cwd=INSTALL_ROOT, check=False)
        run(["git", "reset", "--hard", target], cwd=INSTALL_ROOT, check=True)
    else:
        run(["git", "checkout", branch], cwd=INSTALL_ROOT, check=False)
        run(["git", "pull", "--ff-only", "origin", branch], cwd=INSTALL_ROOT, check=True)
    reinstall_python_package()
    return before, git_current_commit(), backup


def add_update_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--branch", help="Git branch to update from. Default: current branch, or master if detached.")
    p.add_argument("--repo-url", help="Override git origin URL before updating.")
    p.add_argument("--dry-run", action="store_true", help="Fetch and show pending commits without changing files.")
    p.add_argument("--force", action="store_true", help="Reset /opt/doctor_dev to origin/<branch> even if local changes exist.")
    p.add_argument("--no-backup", action="store_true", help="Skip /etc/doctor_dev backup before update.")
    p.add_argument("--no-restart", action="store_true", help="Do not restart services after update.")


def cmd_update(args: argparse.Namespace) -> None:
    before, after, backup = perform_git_update(args, "node")
    if args.dry_run:
        return
    print(f"Updated Doctor Dev source: {before} -> {after}")
    if backup:
        print(f"Config backup: {backup}")
    if not args.no_restart:
        if args.all:
            services = list_node_service_names()
            if not services:
                print("No installed node services found to restart.")
            for svc in services:
                systemctl_service("restart", svc)
        else:
            systemctl_service("restart", service_name(args.name))
        if args.restart_panel:
            systemctl_service("restart", "doctor-dev-panel.service")
    print("Node update finished.")

def cmd_status(args: argparse.Namespace) -> None:
    svc = service_name(args.name)
    print(f"Service: {svc}")
    if shutil.which("systemctl"):
        run(["systemctl", "status", svc, "--no-pager"])
    else:
        print("systemctl not found")
    try:
        print(json.dumps(request_json(args.name, "/health"), indent=2, ensure_ascii=False))
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Health check failed: {exc}")


def cmd_service(args: argparse.Namespace) -> None:
    service_action(args.command, args.name)


def cmd_logs(args: argparse.Namespace) -> None:
    if not shutil.which("journalctl"):
        raise SystemExit("journalctl was not found")
    cmd = ["journalctl", "-u", service_name(args.name), "--no-pager"]
    if args.follow:
        cmd.append("-f")
    if args.lines:
        cmd.extend(["-n", str(args.lines)])
    sys.exit(run(cmd))


def cmd_config(args: argparse.Namespace) -> None:
    path = env_file(args.name)
    env = parse_env(path)
    if args.action == "show":
        print(f"# {path}")
        for key in sorted(env):
            print(f"{key}={redact(key, env[key], args.show_secrets)}")
        install = node_dir(args.name) / "install.json"
        if install.exists():
            print(f"\n# {install}")
            print(install.read_text(encoding="utf-8"))
        return
    if args.action == "keys":
        for key, help_text in NODE_CONFIG_HELP.items():
            print(f"{key}\n  {help_text}")
        return
    if args.action == "get":
        print(redact(args.key, env.get(args.key, ""), args.show_secrets))
        return
    if args.action == "set":
        value = validate_config_value(args.key, args.value)
        backup = backup_file(path)
        env[args.key] = value
        write_env(path, env)
        print(f"Updated {args.key} in {path}")
        if backup:
            print(f"Backup: {backup}")
        if args.restart:
            service_action("restart", args.name)
        else:
            print("Restart node to apply service-level config: doctor-node --name <name> restart")
        return
    if args.action == "unset":
        backup = backup_file(path)
        env.pop(args.key, None)
        write_env(path, env)
        print(f"Removed {args.key} from {path}")
        if backup:
            print(f"Backup: {backup}")
        if args.restart:
            service_action("restart", args.name)
        return
    if args.action == "edit":
        editor = os.getenv("EDITOR", "nano")
        backup = backup_file(path)
        code = run([editor, str(path)])
        if backup:
            print(f"Backup: {backup}")
        sys.exit(code)


def cmd_api_key(args: argparse.Namespace) -> None:
    path = env_file(args.name)
    env = parse_env(path)
    new_key = args.value or str(uuid.uuid4())
    try:
        uuid.UUID(new_key)
    except ValueError as exc:
        raise SystemExit("API key must be a valid UUID") from exc
    backup = backup_file(path)
    env["DOCTOR_DEV_AGENT_API_KEY"] = new_key
    write_env(path, env)
    print(f"Node API key updated: {new_key}")
    if backup:
        print(f"Backup: {backup}")
    if args.restart:
        service_action("restart", args.name)
    else:
        print("Restart node to apply the new key.")


def cmd_cert(args: argparse.Namespace) -> None:
    path = env_file(args.name)
    env = parse_env(path)
    certfile = sanitize_path(args.certfile) if args.certfile else ""
    keyfile = sanitize_path(args.keyfile) if args.keyfile else ""
    if certfile and not Path(certfile).exists():
        raise SystemExit(f"Certificate file does not exist: {certfile}")
    if keyfile and not Path(keyfile).exists():
        raise SystemExit(f"Private key file does not exist: {keyfile}")
    if bool(certfile) != bool(keyfile):
        raise SystemExit("Both --certfile and --keyfile are required, or neither with --clear")
    if args.clear:
        certfile = ""
        keyfile = ""
    env["DOCTOR_DEV_AGENT_SSL_CERTFILE"] = certfile
    env["DOCTOR_DEV_AGENT_SSL_KEYFILE"] = keyfile
    backup = backup_file(path)
    write_env(path, env)
    print("Node certificate config updated.")
    if backup:
        print(f"Backup: {backup}")
    if args.restart:
        service_action("restart", args.name)


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

    p = sub.add_parser("update", help="Update node source from GitHub, reinstall Python package, and restart node service")
    add_update_common_args(p)
    p.add_argument("--all", action="store_true", help="Restart all installed node services after updating shared source")
    p.add_argument("--restart-panel", action="store_true", help="Also restart doctor-dev-panel.service after update")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("config", help="Show or edit node environment settings")
    cfg = p.add_subparsers(dest="action", required=True)
    ps = cfg.add_parser("show")
    ps.add_argument("--show-secrets", action="store_true")
    ps.set_defaults(func=cmd_config)
    pk = cfg.add_parser("keys")
    pk.set_defaults(func=cmd_config)
    pg = cfg.add_parser("get")
    pg.add_argument("key")
    pg.add_argument("--show-secrets", action="store_true")
    pg.set_defaults(func=cmd_config)
    pst = cfg.add_parser("set")
    pst.add_argument("key")
    pst.add_argument("value")
    pst.add_argument("--restart", action="store_true")
    pst.set_defaults(func=cmd_config)
    pu = cfg.add_parser("unset")
    pu.add_argument("key")
    pu.add_argument("--restart", action="store_true")
    pu.set_defaults(func=cmd_config)
    pe = cfg.add_parser("edit")
    pe.set_defaults(func=cmd_config)

    p = sub.add_parser("api-key")
    p.add_argument("action", choices=["rotate"])
    p.add_argument("--value", help="Specific UUID. If omitted, a new UUID is generated.")
    p.add_argument("--restart", action="store_true")
    p.set_defaults(func=cmd_api_key)

    p = sub.add_parser("cert")
    p.add_argument("action", choices=["set"])
    p.add_argument("--certfile")
    p.add_argument("--keyfile")
    p.add_argument("--clear", action="store_true")
    p.add_argument("--restart", action="store_true")
    p.set_defaults(func=cmd_cert)

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
