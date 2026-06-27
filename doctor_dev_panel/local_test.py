from __future__ import annotations

import socket
import ssl


def _read_response(sock: socket.socket) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def tcp_roundtrip(host: str, port: int, payload: str, timeout: float = 5.0) -> dict:
    data = payload.encode("utf-8")
    with socket.create_connection((host, int(port)), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(data)
        sock.shutdown(socket.SHUT_WR)
        response = _read_response(sock)
    return {
        "ok": True,
        "mode": "tcp",
        "host": host,
        "port": port,
        "sent_bytes": len(data),
        "received_bytes": len(response),
        "response_text": response.decode("utf-8", errors="replace"),
    }


def tls_roundtrip(host: str, port: int, payload: str, timeout: float = 5.0, verify: bool = False) -> dict:
    data = payload.encode("utf-8")
    context = ssl.create_default_context() if verify else ssl._create_unverified_context()
    with socket.create_connection((host, int(port)), timeout=timeout) as raw_sock:
        raw_sock.settimeout(timeout)
        with context.wrap_socket(raw_sock, server_hostname=host if verify else None) as sock:
            sock.settimeout(timeout)
            sock.sendall(data)
            # Do not half-close an SSLSocket here: socket.shutdown() can bypass TLS close_notify
            # and expose encrypted TLS records on some Python/OpenSSL combinations. The local
            # echo target responds immediately, so one TLS recv is enough for the round-trip test.
            response = sock.recv(65536)
            cipher = sock.cipher()
    return {
        "ok": True,
        "mode": "tls",
        "host": host,
        "port": port,
        "verify": verify,
        "cipher": cipher,
        "sent_bytes": len(data),
        "received_bytes": len(response),
        "response_text": response.decode("utf-8", errors="replace"),
    }
