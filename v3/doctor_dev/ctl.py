from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

import httpx


def print_json(data) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def request(method: str, manager_url: str, path: str, token: Optional[str]):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = manager_url.rstrip("/") + path
    with httpx.Client(timeout=10.0) as client:
        response = client.request(method, url, headers=headers)
        response.raise_for_status()
        return response.json()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="doctor_dev manager CLI")
    parser.add_argument("--manager", default="http://127.0.0.1:7000", help="manager base URL")
    parser.add_argument("--token", default=None, help="manager API token")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health")
    sub.add_parser("status")
    sub.add_parser("groups")

    group = sub.add_parser("group")
    group.add_argument("name")

    inbounds = sub.add_parser("inbounds")
    inbounds.add_argument("name")

    restart = sub.add_parser("restart")
    restart.add_argument("name")

    sub.add_parser("reload")
    sub.add_parser("sync")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "health":
            print_json(request("GET", args.manager, "/health", None))
        elif args.command == "status":
            print_json(request("GET", args.manager, "/status", args.token))
        elif args.command == "groups":
            print_json(request("GET", args.manager, "/groups", args.token))
        elif args.command == "group":
            print_json(request("GET", args.manager, f"/groups/{args.name}", args.token))
        elif args.command == "inbounds":
            print_json(request("GET", args.manager, f"/groups/{args.name}/inbounds", args.token))
        elif args.command == "restart":
            print_json(request("POST", args.manager, f"/groups/{args.name}/restart", args.token))
        elif args.command == "reload":
            print_json(request("POST", args.manager, "/reload", args.token))
        elif args.command == "sync":
            print_json(request("POST", args.manager, "/sync", args.token))
    except httpx.HTTPStatusError as exc:
        print(f"HTTP error {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
