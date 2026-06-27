from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start one Doctor Dev node agent.")
    parser.add_argument("--name", required=True, help="Node name shown in the panel")
    parser.add_argument("--host", default="127.0.0.1", help="Agent bind host")
    parser.add_argument("--api-port", type=int, required=True, help="Agent API port")
    parser.add_argument("--api-key", required=True, help="API key used by the panel")
    parser.add_argument("--node-port", type=int, default=62050, help="Logical node port stored in the panel")
    parser.add_argument("--echo-host", default="127.0.0.1", help="Local echo target bind host")
    parser.add_argument("--echo-ports", default="3000,3001", help="Comma-separated echo target ports")
    parser.add_argument("--data-dir", default="./data", help="Agent data directory")
    parser.add_argument("--log-dir", default="./logs", help="Log directory")
    parser.add_argument("--config-dir", default="./configs/generated", help="Generated config directory")
    parser.add_argument("--cert-dir", default="./certs/agent", help="Agent certificate directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    env = {
        "DOCTOR_DEV_NODE_NAME": args.name,
        "DOCTOR_DEV_AGENT_HOST": args.host,
        "DOCTOR_DEV_AGENT_PORT": str(args.api_port),
        "DOCTOR_DEV_AGENT_API_KEY": args.api_key,
        "DOCTOR_DEV_NODE_PORT": str(args.node_port),
        "DOCTOR_DEV_ECHO_HOST": args.echo_host,
        "DOCTOR_DEV_ECHO_PORTS": args.echo_ports,
        "DOCTOR_DEV_AGENT_DATA_DIR": args.data_dir,
        "DOCTOR_DEV_LOG_DIR": args.log_dir,
        "DOCTOR_DEV_AGENT_CONFIG_DIR": args.config_dir,
        "DOCTOR_DEV_AGENT_CERT_DIR": args.cert_dir,
    }
    os.environ.update(env)
    print("Doctor Dev node agent")
    print(f"  name      : {args.name}")
    print(f"  api       : http://{args.host}:{args.api_port}")
    print(f"  echo ports: {args.echo_ports}")
    print("Press Ctrl+C to stop this node.\n")
    from doctor_dev_agent.__main__ import main as run_agent

    run_agent()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
