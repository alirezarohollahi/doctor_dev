
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from typing import Optional

from .env_loader import load_env_file

if os.getenv("DOCTOR_DEV_ENV"):
    try:
        load_env_file(os.getenv("DOCTOR_DEV_ENV"))
    except FileNotFoundError:
        pass

from .admin_store import list_admins, remove_admin, set_password, store_path


def _prompt_password() -> str:
    while True:
        password = getpass.getpass("Password: ")
        if len(password) < 8:
            print("Password must be at least 8 characters.", file=sys.stderr)
            continue
        repeat = getpass.getpass("Repeat password: ")
        if password != repeat:
            print("Passwords do not match.", file=sys.stderr)
            continue
        return password


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="doctor-dev admin", description="Manage Doctor Dev Panel admins")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List admins")

    add = sub.add_parser("add", help="Add a new admin or update an existing admin password")
    add.add_argument("username")
    add.add_argument("--password", help="Password. If omitted, it is prompted securely.")

    passwd = sub.add_parser("passwd", help="Change an admin password")
    passwd.add_argument("username")
    passwd.add_argument("--password", help="Password. If omitted, it is prompted securely.")

    remove = sub.add_parser("remove", help="Remove an admin")
    remove.add_argument("username")
    remove.add_argument("--force-last", action="store_true", help="Allow removing the last admin")

    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            admins = list_admins()
            print(f"Admin store: {store_path()}")
            if not admins:
                print("No admins found.")
                return 0
            for item in admins:
                source = item.get("source") or "store"
                print(f"- {item['username']}  ({source})")
            return 0

        if args.command in {"add", "passwd"}:
            password = args.password or _prompt_password()
            set_password(args.username, password)
            print(json.dumps({"ok": True, "username": args.username, "store": str(store_path())}, ensure_ascii=False))
            return 0

        if args.command == "remove":
            removed = remove_admin(args.username, allow_last=args.force_last)
            if not removed:
                print(f"Admin not found: {args.username}", file=sys.stderr)
                return 1
            print(json.dumps({"ok": True, "removed": args.username, "store": str(store_path())}, ensure_ascii=False))
            return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())







