
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass

from doctor_dev_panel.security import create_password_hash


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Doctor Dev Panel password hash")
    parser.add_argument("--password", help="Password. If omitted, it is prompted securely.")
    args = parser.parse_args()
    password = args.password or getpass.getpass("Password: ")
    print(create_password_hash(password))


if __name__ == "__main__":
    main()







