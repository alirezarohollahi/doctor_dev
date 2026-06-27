from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def ask(prompt: str, default: str) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def ask_yes(prompt: str, default: bool = False) -> bool:
    d = "Y/n" if default else "y/N"
    value = input(f"{prompt} [{d}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "1", "true"}


def remove_contents(path: Path, keep: set[str] | None = None) -> None:
    keep = keep or set()
    path.mkdir(parents=True, exist_ok=True)
    for item in path.iterdir():
        if item.name in keep:
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        else:
            try:
                item.unlink()
            except FileNotFoundError:
                pass


def start_process(args: list[str], env: dict[str, str], title: str) -> subprocess.Popen:
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
    print(f"Starting {title}: {' '.join(args)}")
    return subprocess.Popen(args, cwd=ROOT, env=env, creationflags=creationflags)


def main() -> None:
    os.chdir(ROOT)
    print("Doctor Dev clean reset and local start")
    print("This script resets local runtime data, generates admin credentials and starts two local node agents plus the panel.")
    print("")

    if not ask_yes("Continue with local reset", False):
        print("Cancelled.")
        return

    panel_host = ask("Panel host", "127.0.0.1")
    panel_port = int(ask("Panel port", "8088"))
    node_a_port = int(ask("Node A API port", "9101"))
    node_b_port = int(ask("Node B API port", "9102"))
    node_a_echo = ask("Node A echo ports", "3000,3001")
    node_b_echo = ask("Node B echo ports", "3100,3101")

    admin_user = ask("Admin username", f"admin_{secrets.token_hex(3)}")
    admin_password = secrets.token_urlsafe(18)
    key_a = secrets.token_urlsafe(24)
    key_b = secrets.token_urlsafe(24)

    reset_certs = ask_yes("Also remove custom certificates? The bundled local.test certificate will be kept/reused", False)

    remove_contents(ROOT / "data")
    remove_contents(ROOT / "logs")
    remove_contents(ROOT / "configs" / "generated")
    if reset_certs:
        remove_contents(ROOT / "certs", keep={"local.test", ".gitkeep"})

    env_file = ROOT / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                f"DOCTOR_DEV_PANEL_HOST={panel_host}",
                f"DOCTOR_DEV_PANEL_PORT={panel_port}",
                "DOCTOR_DEV_DATA_DIR=./data",
                "DOCTOR_DEV_LOG_DIR=./logs",
                "DOCTOR_DEV_CONFIG_DIR=./configs/generated",
                "DOCTOR_DEV_AUTH_REQUIRED=1",
                f"DOCTOR_DEV_ADMIN_USERNAME={admin_user}",
                f"DOCTOR_DEV_ADMIN_PASSWORD={admin_password}",
                f"DOCTOR_DEV_NODE_A_API_PORT={node_a_port}",
                f"DOCTOR_DEV_NODE_B_API_PORT={node_b_port}",
                f"DOCTOR_DEV_NODE_A_API_KEY={key_a}",
                f"DOCTOR_DEV_NODE_B_API_KEY={key_b}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    base_env = os.environ.copy()
    base_env.update(
        {
            "DOCTOR_DEV_DATA_DIR": "./data",
            "DOCTOR_DEV_LOG_DIR": "./logs",
            "DOCTOR_DEV_CONFIG_DIR": "./configs/generated",
            "DOCTOR_DEV_AUTH_REQUIRED": "1",
            "DOCTOR_DEV_ADMIN_USERNAME": admin_user,
            "DOCTOR_DEV_ADMIN_PASSWORD": admin_password,
            "DOCTOR_DEV_NODE_A_API_PORT": str(node_a_port),
            "DOCTOR_DEV_NODE_B_API_PORT": str(node_b_port),
            "DOCTOR_DEV_NODE_A_API_KEY": key_a,
            "DOCTOR_DEV_NODE_B_API_KEY": key_b,
        }
    )

    start_process(
        [PYTHON, "scripts/start_node.py", "--name", "local-node-a", "--api-port", str(node_a_port), "--api-key", key_a, "--echo-ports", node_a_echo],
        base_env,
        "local-node-a",
    )
    time.sleep(1)
    start_process(
        [PYTHON, "scripts/start_node.py", "--name", "local-node-b", "--api-port", str(node_b_port), "--api-key", key_b, "--echo-ports", node_b_echo],
        base_env,
        "local-node-b",
    )
    time.sleep(1)

    print("\n============================================================")
    print("Doctor Dev is starting")
    print(f"Panel URL : http://{panel_host}:{panel_port}")
    print(f"Admin user: {admin_user}")
    print(f"Admin pass: {admin_password}")
    print("Node A    : local-node-a / 127.0.0.1:%s / key saved in .env.local" % node_a_port)
    print("Node B    : local-node-b / 127.0.0.1:%s / key saved in .env.local" % node_b_port)
    print("State     : data/panel_state.json")
    print("Logs      : logs/")
    print("============================================================\n")
    print("After the browser opens/prompts, use the username/password above.")
    print("Inside the panel click: Seed Local Nodes → Check nodes → Local Test Lab.")
    print("Press Ctrl+C here to stop the panel. Node windows can be closed separately.\n")

    panel_env = base_env.copy()
    panel_env.update({"DOCTOR_DEV_PANEL_HOST": panel_host, "DOCTOR_DEV_PANEL_PORT": str(panel_port)})
    subprocess.run([PYTHON, "-m", "doctor_dev_panel"], cwd=ROOT, env=panel_env, check=False)


if __name__ == "__main__":
    main()
