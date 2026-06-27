from __future__ import annotations

import json
import os
import shutil
import socket
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from secrets import token_urlsafe
from typing import Iterable
from uuid import UUID, uuid4

REPO_URL = "https://github.com/alirezarohollahi/doctor_dev"
INSTALL_ROOT = Path(os.getenv("DOCTOR_DEV_INSTALL_ROOT", "/opt/doctor_dev"))
CONFIG_ROOT = Path(os.getenv("DOCTOR_DEV_CONFIG_ROOT", "/etc/doctor_dev"))
DATA_ROOT = Path(os.getenv("DOCTOR_DEV_DATA_ROOT", "/var/lib/doctor_dev"))
LOG_ROOT = Path(os.getenv("DOCTOR_DEV_LOG_ROOT", "/var/log/doctor_dev"))
BACKUP_ROOT = Path(os.getenv("DOCTOR_DEV_BACKUP_ROOT", "/var/backups/doctor_dev"))
SYSTEMD_ROOT = Path("/etc/systemd/system")

PANEL_SERVICE = "doctor-dev-panel.service"
NODE_SERVICE_PREFIX = "doctor-dev-node"


@dataclass(frozen=True)
class LinuxPlatform:
    distro_id: str
    distro_like: str
    package_manager: str
    install_command: list[str]
    update_command: list[str]
    packages: list[str]
    certbot_package: str | None


def run(cmd: list[str], *, check: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=check, text=True)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def require_root() -> None:
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise SystemExit("This installer must be run as root. Use: sudo python3 scripts/install_panel.py")


def read_os_release() -> dict[str, str]:
    path = Path("/etc/os-release")
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value.strip().strip('"')
    return data


def detect_platform() -> LinuxPlatform:
    osr = read_os_release()
    distro_id = osr.get("ID", "unknown").lower()
    distro_like = osr.get("ID_LIKE", "").lower()

    if command_exists("apt-get"):
        return LinuxPlatform(
            distro_id,
            distro_like,
            "apt",
            ["apt-get", "install", "-y"],
            ["apt-get", "update"],
            ["python3", "python3-venv", "python3-pip", "git", "curl", "ca-certificates", "openssl", "tar", "unzip"],
            "certbot",
        )
    if command_exists("apk"):
        return LinuxPlatform(
            distro_id,
            distro_like,
            "apk",
            ["apk", "add", "--no-cache"],
            ["apk", "update"],
            ["python3", "py3-pip", "py3-virtualenv", "git", "curl", "ca-certificates", "openssl", "tar", "unzip"],
            "certbot",
        )
    if command_exists("dnf"):
        return LinuxPlatform(
            distro_id,
            distro_like,
            "dnf",
            ["dnf", "install", "-y"],
            ["dnf", "makecache"],
            ["python3", "python3-pip", "git", "curl", "ca-certificates", "openssl", "tar", "unzip"],
            "certbot",
        )
    if command_exists("yum"):
        return LinuxPlatform(
            distro_id,
            distro_like,
            "yum",
            ["yum", "install", "-y"],
            ["yum", "makecache"],
            ["python3", "python3-pip", "git", "curl", "ca-certificates", "openssl", "tar", "unzip"],
            "certbot",
        )
    if command_exists("zypper"):
        return LinuxPlatform(
            distro_id,
            distro_like,
            "zypper",
            ["zypper", "--non-interactive", "install"],
            ["zypper", "refresh"],
            ["python3", "python3-pip", "git", "curl", "ca-certificates", "openssl", "tar", "unzip"],
            "certbot",
        )
    if command_exists("pacman"):
        return LinuxPlatform(
            distro_id,
            distro_like,
            "pacman",
            ["pacman", "-S", "--noconfirm"],
            ["pacman", "-Sy"],
            ["python", "python-pip", "git", "curl", "ca-certificates", "openssl", "tar", "unzip"],
            "certbot",
        )
    raise SystemExit("No supported package manager found. Supported: apt, apk, dnf, yum, zypper, pacman.")


def install_system_packages(extra: Iterable[str] = ()) -> None:
    platform = detect_platform()
    print(f"Detected Linux: {platform.distro_id or 'unknown'} / package manager: {platform.package_manager}")
    try:
        run(platform.update_command, check=False)
    except Exception:
        pass
    packages = list(dict.fromkeys([*platform.packages, *extra]))
    run([*platform.install_command, *packages])


def install_certbot_if_needed() -> None:
    if command_exists("certbot"):
        return
    platform = detect_platform()
    if not platform.certbot_package:
        raise SystemExit("certbot package is not known for this distribution. Install certbot manually or provide existing certificate paths.")
    run([*platform.install_command, platform.certbot_package])


def clean_input(value: str) -> str:
    """Normalize interactive answers without changing their meaning.

    Users often paste paths wrapped in quotes or with a trailing backslash from shell
    line continuations.  A prompt must never crash just because of that.
    """
    value = (value or "").strip().strip("\r\n")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    # A trailing backslash in an interactive installer is almost always accidental.
    while value.endswith("\\"):
        value = value[:-1].rstrip()
    return value


def clean_path_input(value: str) -> str:
    value = clean_input(value)
    # Remove a single escaped-space style only at line ends; keep normal Linux paths intact.
    return os.path.expandvars(value)


def normalize_existing_file_path(value: str) -> Path:
    cleaned = clean_path_input(value)
    if not cleaned:
        raise ValueError("path is empty")
    return Path(cleaned).expanduser().resolve()


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    value = clean_input(input(f"{prompt}{suffix}: "))
    return value if value else (default or "")


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    default_text = "Y/n" if default else "y/N"
    while True:
        value = clean_input(input(f"{prompt} [{default_text}]: ")).lower()
        if not value:
            return default
        if value in {"y", "yes", "1", "true", "on"}:
            return True
        if value in {"n", "no", "0", "false", "off"}:
            return False
        print("Please answer yes or no.")


def ask_choice(prompt: str, choices: set[str], default: str) -> str:
    while True:
        value = ask(prompt, default)
        if value in choices:
            return value
        print(f"Invalid choice. Allowed values: {', '.join(sorted(choices))}")


def ask_int(prompt: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    while True:
        value = ask(prompt, str(default))
        try:
            number = int(value)
        except ValueError:
            print("Please enter a valid number.")
            continue
        if minimum is not None and number < minimum:
            print(f"Number must be >= {minimum}.")
            continue
        if maximum is not None and number > maximum:
            print(f"Number must be <= {maximum}.")
            continue
        return number


def ask_existing_file(prompt: str, *, default: str | None = None, allow_cancel: bool = True) -> Path | None:
    while True:
        value = ask(prompt, default)
        if allow_cancel and clean_input(value).lower() in {"q", "quit", "cancel", "back", "skip"}:
            return None
        try:
            path = normalize_existing_file_path(value)
        except ValueError as exc:
            print(f"Invalid path: {exc}")
            continue
        if path.is_file():
            return path
        print(f"File not found: {path}")
        print("Enter a valid file path, or type 'back' to choose another option.")


def random_password() -> str:
    return token_urlsafe(32)


def random_admin_username() -> str:
    return "admin_" + token_urlsafe(6).replace("-", "_")


def make_uuid() -> str:
    return str(uuid4())


def ask_uuid(prompt: str, default: str | None = None) -> str:
    while True:
        value = ask(prompt, default or make_uuid())
        try:
            return str(UUID(value))
        except Exception:
            print("Please enter a valid UUID, or press Enter to use the generated one.")


def server_public_ip_guess() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except Exception:
        return "0.0.0.0"


def ensure_layout() -> None:
    for path in [INSTALL_ROOT, CONFIG_ROOT, DATA_ROOT, LOG_ROOT, BACKUP_ROOT, CONFIG_ROOT / "panel", CONFIG_ROOT / "nodes", CONFIG_ROOT / "certs"]:
        path.mkdir(parents=True, exist_ok=True)


def clone_or_update_repo() -> None:
    if (INSTALL_ROOT / ".git").exists():
        run(["git", "fetch", "--all"], cwd=INSTALL_ROOT)
        run(["git", "pull", "--ff-only"], cwd=INSTALL_ROOT, check=False)
        return
    if INSTALL_ROOT.exists() and any(INSTALL_ROOT.iterdir()):
        print(f"{INSTALL_ROOT} exists and is not a git checkout. Keeping it as current project source.")
        return
    INSTALL_ROOT.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", REPO_URL, str(INSTALL_ROOT)])


def setup_venv() -> None:
    venv = INSTALL_ROOT / ".venv"
    if not venv.exists():
        run([sys.executable, "-m", "venv", str(venv)])
    pip = venv / "bin" / "pip"
    python = venv / "bin" / "python"
    run([str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    req = INSTALL_ROOT / "requirements.txt"
    if req.exists():
        run([str(pip), "install", "-r", str(req)])
    run([str(pip), "install", "-e", str(INSTALL_ROOT)])


def write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(f"{key}={shell_quote_env(value)}" for key, value in values.items()) + "\n"
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def shell_quote_env(value: str) -> str:
    if value == "" or any(ch.isspace() or ch in value for ch in ['#', '"', "'", '$', '`', '\\']):
        escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
        return f'"{escaped}"'
    return value


def write_json_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def sanitize_service_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.strip().lower())
    return cleaned.strip("-") or "node"


def has_systemd() -> bool:
    return command_exists("systemctl") and Path("/run/systemd/system").exists()


def reload_systemd() -> None:
    if has_systemd():
        run(["systemctl", "daemon-reload"], check=False)


def enable_and_start(service_name: str) -> None:
    if has_systemd():
        run(["systemctl", "enable", "--now", service_name])
    else:
        print("systemd is not available. Start manually with the command printed by the installer.")


def stop_disable_service(service_name: str) -> None:
    if has_systemd():
        run(["systemctl", "disable", "--now", service_name], check=False)


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def create_bin_wrapper(name: str, module_or_command: str) -> None:
    target = Path("/usr/local/bin") / name
    target.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"exec {INSTALL_ROOT}/.venv/bin/{module_or_command} \"$@\"\n",
        encoding="utf-8",
    )
    target.chmod(target.stat().st_mode | stat.S_IEXEC)


def create_python_module_wrapper(name: str, module_name: str) -> None:
    target = Path("/usr/local/bin") / name
    target.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"exec {INSTALL_ROOT}/.venv/bin/python -m {module_name} \"$@\"\n",
        encoding="utf-8",
    )
    target.chmod(target.stat().st_mode | stat.S_IEXEC)


def save_credentials(path: Path, title: str, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [title, "=" * len(title), ""]
    lines.extend(f"{key}: {value}" for key, value in values.items())
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    path.chmod(0o600)


def generate_self_signed_cert(domain_or_ip: str, alias: str) -> tuple[Path, Path]:
    cert_dir = CONFIG_ROOT / "certs" / sanitize_service_part(alias)
    cert_dir.mkdir(parents=True, exist_ok=True)
    fullchain = cert_dir / "fullchain.pem"
    privkey = cert_dir / "privkey.pem"
    subj = f"/CN={domain_or_ip}"
    san = f"subjectAltName=DNS:{domain_or_ip}"
    if all(part.isdigit() and 0 <= int(part) <= 255 for part in domain_or_ip.split(".") if part):
        san = f"subjectAltName=IP:{domain_or_ip}"
    run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(privkey), "-out", str(fullchain),
        "-sha256", "-days", "365", "-subj", subj, "-addext", san,
    ])
    privkey.chmod(0o600)
    fullchain.chmod(0o644)
    return fullchain, privkey


def issue_lets_encrypt(domain: str, email: str) -> tuple[Path, Path]:
    install_certbot_if_needed()
    run([
        "certbot", "certonly", "--standalone", "--non-interactive", "--agree-tos", "--preferred-challenges", "http",
        "-m", email, "-d", domain,
    ])
    base = Path("/etc/letsencrypt/live") / domain
    return base / "fullchain.pem", base / "privkey.pem"


def copy_existing_cert(alias: str, fullchain_path: str | Path, privkey_path: str | Path) -> tuple[Path, Path]:
    src_full = fullchain_path if isinstance(fullchain_path, Path) else normalize_existing_file_path(fullchain_path)
    src_key = privkey_path if isinstance(privkey_path, Path) else normalize_existing_file_path(privkey_path)
    if not src_full.is_file() or not src_key.is_file():
        raise ValueError("Certificate path is invalid. fullchain.pem and privkey.pem must exist.")
    dest_dir = CONFIG_ROOT / "certs" / sanitize_service_part(alias)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_full = dest_dir / "fullchain.pem"
    dest_key = dest_dir / "privkey.pem"
    shutil.copy2(src_full, dest_full)
    shutil.copy2(src_key, dest_key)
    dest_key.chmod(0o600)
    dest_full.chmod(0o644)
    return dest_full, dest_key


def prompt_and_copy_existing_cert(alias: str) -> tuple[Path, Path] | None:
    print("Type 'back' at any certificate path prompt to return to the previous menu.")
    while True:
        fullchain = ask_existing_file("Path to fullchain.pem")
        if fullchain is None:
            return None
        privkey = ask_existing_file("Path to privkey.pem")
        if privkey is None:
            return None
        try:
            return copy_existing_cert(alias, fullchain, privkey)
        except Exception as exc:
            print(f"Certificate copy failed: {exc}")
            if not ask_yes_no("Try certificate paths again?", default=True):
                return None


def uninstall_all(remove_data: bool = False) -> None:
    stop_disable_service(PANEL_SERVICE)
    if has_systemd():
        for service in SYSTEMD_ROOT.glob(f"{NODE_SERVICE_PREFIX}-*.service"):
            stop_disable_service(service.name)
            remove_path(service)
        remove_path(SYSTEMD_ROOT / PANEL_SERVICE)
        reload_systemd()
    for binary in ["doctor-panel", "doctor-node"]:
        remove_path(Path("/usr/local/bin") / binary)
    if remove_data:
        for path in [INSTALL_ROOT, CONFIG_ROOT, DATA_ROOT, LOG_ROOT, BACKUP_ROOT]:
            remove_path(path)
