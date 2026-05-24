from __future__ import annotations

import socket


def is_port_available(host: str, port: int) -> bool:
    bind_host = "0.0.0.0" if host in {"", None} else host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((bind_host, port))
            return True
    except OSError:
        return False


def allocate_random_port(host: str) -> int:
    bind_host = "0.0.0.0" if host in {"", None} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((bind_host, 0))
        return int(sock.getsockname()[1])
