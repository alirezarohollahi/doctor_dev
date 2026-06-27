from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import secrets
import shutil
import ssl
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CONFIG_ROOT = Path(os.getenv("DOCTOR_DEV_CONFIG_ROOT", "/etc/doctor_dev"))
INSTALL_ROOT = Path(os.getenv("DOCTOR_DEV_INSTALL_ROOT", "/opt/doctor_dev"))
DEFAULT_REPO_URL = os.getenv("DOCTOR_DEV_REPO_URL", "https://github.com/alirezarohollahi/doctor_dev")
SYSTEMD_ROOT = Path("/etc/systemd/system")
PANEL_ENV = CONFIG_ROOT / "panel" / "panel.env"
PANEL_INSTALL = CONFIG_ROOT / "panel" / "install.json"
SERVICE = "doctor-dev-panel.service"
BACKUP_ROOT = Path("/var/backups/doctor_dev")

SENSITIVE_KEYS = {"PASSWORD", "SECRET", "TOKEN", "KEY", "API_KEY"}

PANEL_CONFIG_HELP: dict[str, str] = {
    "DOCTOR_DEV_PANEL_HOST": "Panel bind host, for example 0.0.0.0 or 127.0.0.1",
    "DOCTOR_DEV_PANEL_PORT": "Panel port, 1..65535",
    "DOCTOR_DEV_PANEL_PUBLIC_URL": "Public URL shown by installer and CLI",
    "DOCTOR_DEV_AUTH_REQUIRED": "1/0 - enable or disable UI/API auth",
    "DOCTOR_DEV_ADMIN_USERNAME": "Admin username",
    "DOCTOR_DEV_ADMIN_PASSWORD": "Admin password",
    "DOCTOR_DEV_APP_SECRET": "Session signing secret",
    "DOCTOR_DEV_SESSION_TTL_SECONDS": "Login session TTL in seconds",
    "DOCTOR_DEV_DATA_DIR": "Panel data directory",
    "DOCTOR_DEV_LOG_DIR": "Panel log directory",
    "DOCTOR_DEV_CONFIG_DIR": "Generated config directory",
    "DOCTOR_DEV_CERT_DIR": "Certificate storage directory",
    "DOCTOR_DEV_PANEL_SSL_CERTFILE": "Panel TLS certificate fullchain.pem path",
    "DOCTOR_DEV_PANEL_SSL_KEYFILE": "Panel TLS privkey.pem path",
}

PORT_KEYS = {"DOCTOR_DEV_PANEL_PORT"}
INT_KEYS = {"DOCTOR_DEV_PANEL_PORT", "DOCTOR_DEV_SESSION_TTL_SECONDS"}
PATH_KEYS = {
    "DOCTOR_DEV_DATA_DIR",
    "DOCTOR_DEV_LOG_DIR",
    "DOCTOR_DEV_CONFIG_DIR",
    "DOCTOR_DEV_CERT_DIR",
    "DOCTOR_DEV_PANEL_SSL_CERTFILE",
    "DOCTOR_DEV_PANEL_SSL_KEYFILE",
}
BOOL_KEYS = {"DOCTOR_DEV_AUTH_REQUIRED"}


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
    lines = ["# Managed by doctor-panel CLI. Keep a backup before manual edits."]
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


def normalize_bool(value: str) -> str:
    low = value.strip().lower()
    if low in {"1", "true", "yes", "y", "on", "enable", "enabled"}:
        return "1"
    if low in {"0", "false", "no", "n", "off", "disable", "disabled"}:
        return "0"
    raise SystemExit("Boolean values must be one of: 1/0, true/false, yes/no, on/off")


def validate_config_value(key: str, value: str) -> str:
    if key in PATH_KEYS:
        value = sanitize_path(value)
    if key in BOOL_KEYS:
        value = normalize_bool(value)
    if key in INT_KEYS:
        try:
            ivalue = int(value)
        except ValueError as exc:
            raise SystemExit(f"{key} must be an integer") from exc
        if key in PORT_KEYS and not (1 <= ivalue <= 65535):
            raise SystemExit(f"{key} must be between 1 and 65535")
        if key == "DOCTOR_DEV_SESSION_TTL_SECONDS" and ivalue < 60:
            raise SystemExit("DOCTOR_DEV_SESSION_TTL_SECONDS must be at least 60")
        value = str(ivalue)
    if key == "DOCTOR_DEV_ADMIN_PASSWORD" and not value:
        raise SystemExit("Admin password cannot be empty")
    if key == "DOCTOR_DEV_ADMIN_USERNAME" and not value:
        raise SystemExit("Admin username cannot be empty")
    if key in {"DOCTOR_DEV_PANEL_SSL_CERTFILE", "DOCTOR_DEV_PANEL_SSL_KEYFILE"} and value and not Path(value).exists():
        raise SystemExit(f"File does not exist: {value}")
    return value


def redact(key: str, value: str, show_secrets: bool = False) -> str:
    if show_secrets:
        return value
    upper = key.upper()
    if any(marker in upper for marker in SENSITIVE_KEYS) and value:
        return value[:4] + "..." + value[-4:] if len(value) > 10 else "********"
    return value


def service_action(action: str) -> None:
    if shutil.which("systemctl"):
        sys.exit(run(["systemctl", action, SERVICE]))
    raise SystemExit("systemctl was not found. Start/restart the panel manually.")


def panel_url() -> str:
    if PANEL_INSTALL.exists():
        try:
            data = json.loads(PANEL_INSTALL.read_text(encoding="utf-8"))
            if data.get("public_url"):
                return str(data["public_url"])
        except Exception:
            pass
    env = parse_env(PANEL_ENV)
    if env.get("DOCTOR_DEV_PANEL_PUBLIC_URL"):
        return env["DOCTOR_DEV_PANEL_PUBLIC_URL"]
    scheme = "https" if env.get("DOCTOR_DEV_PANEL_SSL_CERTFILE") else "http"
    host = env.get("DOCTOR_DEV_PANEL_HOST", "127.0.0.1")
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port = env.get("DOCTOR_DEV_PANEL_PORT", "8088")
    return f"{scheme}://{host}:{port}"


def request_json(path: str, method: str = "GET", payload: dict | None = None) -> dict | list:
    env = parse_env(PANEL_ENV)
    url = panel_url().rstrip("/") + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    if env.get("DOCTOR_DEV_AUTH_REQUIRED", "1") in {"1", "true", "yes", "on"}:
        user = env.get("DOCTOR_DEV_ADMIN_USERNAME", "admin")
        password = env.get("DOCTOR_DEV_ADMIN_PASSWORD", "")
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    ctx = ssl._create_unverified_context() if url.startswith("https://") else None
    with urlopen(req, timeout=15, context=ctx) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def find_node(identifier: str) -> dict:
    nodes = request_json("/api/nodes")
    assert isinstance(nodes, list)
    for node in nodes:
        if node.get("id") == identifier or node.get("name") == identifier:
            return node
    raise SystemExit(f"Node not found: {identifier}")


def node_payload_from_args(args: argparse.Namespace, existing: dict | None = None) -> dict:
    advanced = dict((existing or {}).get("advanced") or {})
    keep_alive = dict(advanced.get("keep_alive") or {"value": 60, "unit": "seconds"})
    if args.api_port is not None:
        advanced["api_port"] = args.api_port
    elif "api_port" not in advanced:
        advanced["api_port"] = args.port
    if args.keep_alive_value is not None:
        keep_alive["value"] = args.keep_alive_value
    if args.keep_alive_unit is not None:
        keep_alive["unit"] = args.keep_alive_unit
    advanced["keep_alive"] = keep_alive
    if args.data_limit_gb is not None:
        advanced["data_limit_gb"] = args.data_limit_gb
    if args.default_timeout is not None:
        advanced["default_timeout"] = args.default_timeout
    if args.internal_timeout is not None:
        advanced["internal_timeout"] = args.internal_timeout
    if args.proxy_url is not None:
        advanced["proxy_url"] = args.proxy_url or None

    payload = {
        "name": args.name if args.name is not None else (existing or {}).get("name"),
        "address": args.address if args.address is not None else (existing or {}).get("address"),
        "node_port": args.port if args.port is not None else (existing or {}).get("node_port", 9101),
        "api_key": args.api_key if args.api_key is not None else (existing or {}).get("api_key"),
        "connection_type": args.connection_type if args.connection_type is not None else (existing or {}).get("connection_type", "http"),
        "advanced": advanced,
        "certificate": args.certificate if args.certificate is not None else (existing or {}).get("certificate"),
    }
    missing = [key for key in ["name", "address", "api_key"] if not payload.get(key)]
    if missing:
        raise SystemExit(f"Missing required node fields: {', '.join(missing)}")
    return payload



def require_update_ready() -> None:
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise SystemExit("Update must be run as root: sudo doctor-panel update")
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
    before, after, backup = perform_git_update(args, "panel")
    if args.dry_run:
        return
    print(f"Updated Doctor Dev source: {before} -> {after}")
    if backup:
        print(f"Config backup: {backup}")
    if not args.no_restart:
        systemctl_service("restart", SERVICE)
        if args.include_nodes:
            for svc in list_node_service_names():
                systemctl_service("restart", svc)
    print("Panel update finished.")

def cmd_status(_: argparse.Namespace) -> None:
    print(f"Service: {SERVICE}")
    if shutil.which("systemctl"):
        run(["systemctl", "status", SERVICE, "--no-pager"])
    else:
        print("systemctl not found")
    try:
        print(json.dumps(request_json("/health"), indent=2, ensure_ascii=False))
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Health check failed: {exc}")


def cmd_start(_: argparse.Namespace) -> None:
    service_action("start")


def cmd_stop(_: argparse.Namespace) -> None:
    service_action("stop")


def cmd_restart(_: argparse.Namespace) -> None:
    service_action("restart")


def cmd_logs(args: argparse.Namespace) -> None:
    if not shutil.which("journalctl"):
        raise SystemExit("journalctl was not found")
    cmd = ["journalctl", "-u", SERVICE, "--no-pager"]
    if args.follow:
        cmd.append("-f")
    if args.lines:
        cmd.extend(["-n", str(args.lines)])
    sys.exit(run(cmd))


def cmd_config(args: argparse.Namespace) -> None:
    env = parse_env(PANEL_ENV)
    if args.action == "show":
        print(f"# {PANEL_ENV}")
        for key in sorted(env):
            print(f"{key}={redact(key, env[key], args.show_secrets)}")
        if PANEL_INSTALL.exists():
            print(f"\n# {PANEL_INSTALL}")
            print(PANEL_INSTALL.read_text(encoding="utf-8"))
        return
    if args.action == "keys":
        for key, help_text in PANEL_CONFIG_HELP.items():
            print(f"{key}\n  {help_text}")
        return
    if args.action == "get":
        value = env.get(args.key, "")
        print(redact(args.key, value, args.show_secrets))
        return
    if args.action == "set":
        key = args.key
        value = validate_config_value(key, args.value)
        backup = backup_file(PANEL_ENV)
        env[key] = value
        write_env(PANEL_ENV, env)
        print(f"Updated {key} in {PANEL_ENV}")
        if backup:
            print(f"Backup: {backup}")
        if args.restart:
            service_action("restart")
        else:
            print("Restart panel to apply service-level config: doctor-panel restart")
        return
    if args.action == "unset":
        backup = backup_file(PANEL_ENV)
        env.pop(args.key, None)
        write_env(PANEL_ENV, env)
        print(f"Removed {args.key} from {PANEL_ENV}")
        if backup:
            print(f"Backup: {backup}")
        if args.restart:
            service_action("restart")
        return
    if args.action == "edit":
        editor = os.getenv("EDITOR", "nano")
        backup = backup_file(PANEL_ENV)
        code = run([editor, str(PANEL_ENV)])
        if backup:
            print(f"Backup: {backup}")
        sys.exit(code)


def cmd_admin(args: argparse.Namespace) -> None:
    path = CONFIG_ROOT / "panel" / "admin_credentials.txt"
    if args.action == "show":
        print(path.read_text(encoding="utf-8") if path.exists() else "admin credentials file not found")
        return
    if args.action == "reset-password":
        env = parse_env(PANEL_ENV)
        password = args.password or secrets.token_urlsafe(24)
        env["DOCTOR_DEV_ADMIN_PASSWORD"] = password
        backup = backup_file(PANEL_ENV)
        write_env(PANEL_ENV, env)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "Doctor Dev Panel Admin\n"
            f"Panel URL: {panel_url()}\n"
            f"Admin username: {env.get('DOCTOR_DEV_ADMIN_USERNAME', 'admin')}\n"
            f"Admin password: {password}\n",
            encoding="utf-8",
        )
        try:
            path.chmod(0o600)
        except OSError:
            pass
        print(f"Admin password updated. Credentials file: {path}")
        if backup:
            print(f"Backup: {backup}")
        if args.restart:
            service_action("restart")
        else:
            print("Restart panel to apply the new password: doctor-panel restart")


def cmd_nodes(args: argparse.Namespace) -> None:
    if args.action == "list":
        print(json.dumps(request_json("/api/nodes"), indent=2, ensure_ascii=False))
        return
    if args.action == "add":
        payload = node_payload_from_args(args)
        print(json.dumps(request_json("/api/nodes", "POST", payload), indent=2, ensure_ascii=False))
        return
    if args.action == "update":
        existing = find_node(args.node)
        payload = node_payload_from_args(args, existing)
        print(json.dumps(request_json(f"/api/nodes/{existing['id']}", "PUT", payload), indent=2, ensure_ascii=False))
        return
    if args.action == "delete":
        node = find_node(args.node)
        print(json.dumps(request_json(f"/api/nodes/{node['id']}", "DELETE"), indent=2, ensure_ascii=False))
        return
    if args.action == "check":
        node = find_node(args.node)
        print(json.dumps(request_json(f"/api/nodes/{node['id']}/check-status", "POST"), indent=2, ensure_ascii=False))


def cmd_cert(args: argparse.Namespace) -> None:
    if args.action == "list":
        print(json.dumps(request_json("/api/certificates"), indent=2, ensure_ascii=False))
        return
    if args.action == "validate":
        payload = {"mode": args.mode, "domain": args.domain, "fullchain_path": sanitize_path(args.fullchain) if args.fullchain else None, "privkey_path": sanitize_path(args.privkey) if args.privkey else None}
        print(json.dumps(request_json("/api/certificates/validate", "POST", payload), indent=2, ensure_ascii=False))
        return
    if args.action == "add":
        payload = {
            "name": args.name,
            "domain": args.domain,
            "mode": args.mode,
            "fullchain_path": sanitize_path(args.fullchain) if args.fullchain else None,
            "privkey_path": sanitize_path(args.privkey) if args.privkey else None,
            "location": args.location,
        }
        print(json.dumps(request_json("/api/certificates", "POST", payload), indent=2, ensure_ascii=False))


def cmd_backup_create(_: argparse.Namespace) -> None:
    backup_root = BACKUP_ROOT
    backup_root.mkdir(parents=True, exist_ok=True)
    name = backup_root / f"panel-backup-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.tar.gz"
    shutil.make_archive(str(name).removesuffix(".tar.gz"), "gztar", root_dir="/", base_dir="etc/doctor_dev")
    print(f"Backup created: {name}")


def add_node_common_args(p: argparse.ArgumentParser, update: bool = False) -> None:
    p.add_argument("--name", required=not update, help="Node display name")
    p.add_argument("--address", required=not update, help="Node address or domain")
    p.add_argument("--port", type=int, required=not update, help="Node API port")
    p.add_argument("--api-key", required=not update, help="Node API key")
    p.add_argument("--connection-type", choices=["http", "grpc"], default=None)
    p.add_argument("--api-port", type=int, help="Advanced API port metadata")
    p.add_argument("--keep-alive-value", type=int)
    p.add_argument("--keep-alive-unit", choices=["seconds", "minutes", "hours"])
    p.add_argument("--data-limit-gb", type=int)
    p.add_argument("--default-timeout", type=int)
    p.add_argument("--internal-timeout", type=int)
    p.add_argument("--proxy-url")
    p.add_argument("--certificate")


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

    p = sub.add_parser("update", help="Update panel source from GitHub, reinstall Python package, and restart services")
    add_update_common_args(p)
    p.add_argument("--include-nodes", action="store_true", help="Also restart installed node services after updating shared source")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("config", help="Show or edit panel environment settings")
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

    p = sub.add_parser("admin")
    adm = p.add_subparsers(dest="action", required=True)
    pa = adm.add_parser("show")
    pa.set_defaults(func=cmd_admin)
    pr = adm.add_parser("reset-password")
    pr.add_argument("--password", help="New password. If omitted, a secure random password is generated.")
    pr.add_argument("--restart", action="store_true")
    pr.set_defaults(func=cmd_admin)

    p = sub.add_parser("nodes", help="Manage nodes registered in the panel")
    ns = p.add_subparsers(dest="action", required=True)
    pl = ns.add_parser("list")
    pl.set_defaults(func=cmd_nodes)
    pa = ns.add_parser("add")
    add_node_common_args(pa, update=False)
    pa.set_defaults(func=cmd_nodes)
    pu = ns.add_parser("update")
    pu.add_argument("node", help="Node id or name to update")
    add_node_common_args(pu, update=True)
    pu.set_defaults(func=cmd_nodes)
    pd = ns.add_parser("delete")
    pd.add_argument("node", help="Node id or name to delete")
    pd.set_defaults(func=cmd_nodes)
    pc = ns.add_parser("check")
    pc.add_argument("node", help="Node id or name to check")
    pc.set_defaults(func=cmd_nodes)

    p = sub.add_parser("cert")
    cs = p.add_subparsers(dest="action", required=True)
    cl = cs.add_parser("list")
    cl.set_defaults(func=cmd_cert)
    cv = cs.add_parser("validate")
    cv.add_argument("--mode", choices=["file_on_panel", "file_on_node", "uploaded_from_host"], default="file_on_panel")
    cv.add_argument("--domain")
    cv.add_argument("--fullchain", required=True)
    cv.add_argument("--privkey", required=True)
    cv.set_defaults(func=cmd_cert)
    ca = cs.add_parser("add")
    ca.add_argument("--name", required=True, help="Certificate alias")
    ca.add_argument("--domain", required=True)
    ca.add_argument("--mode", choices=["file_on_panel", "file_on_node", "uploaded_from_host"], default="file_on_panel")
    ca.add_argument("--fullchain", required=True)
    ca.add_argument("--privkey", required=True)
    ca.add_argument("--location", choices=["panel", "node", "inline"], default="panel")
    ca.set_defaults(func=cmd_cert)

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
