from __future__ import annotations

from install_common import ask_yes_no, require_root, uninstall_all


def main() -> None:
    require_root()
    remove_data = ask_yes_no("Remove source, config, data, logs and backups too?", default=False)
    uninstall_all(remove_data=remove_data)
    print("Doctor Dev uninstall completed.")


if __name__ == "__main__":
    main()
