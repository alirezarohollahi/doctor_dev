#!/usr/bin/env python3
from __future__ import annotations

import argparse
import socket
import threading
import time
from datetime import datetime
from typing import Optional

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[38;5;82m"
CYAN = "\033[38;5;51m"
YELLOW = "\033[38;5;214m"
RED = "\033[38;5;196m"


def now() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def send_once(*, host: str, port: int, payload: bytes, timeout: float, read_reply: bool, label: str) -> Optional[str]:
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            local = sock.getsockname()
            print(f"{CYAN}[{now()}] CONNECT {label} target={host}:{port} local={local}{RESET}", flush=True)
            sock.sendall(payload)
            print(f"{GREEN}[{now()}] SEND    {label} bytes={len(payload)} payload={payload.decode('utf-8', errors='replace').strip()!r}{RESET}", flush=True)
            if not read_reply:
                return None
            try:
                reply = sock.recv(65536)
                decoded = reply.decode("utf-8", errors="replace").strip()
                print(f"{YELLOW}[{now()}] REPLY   {label} bytes={len(reply)} payload={decoded!r}{RESET}", flush=True)
                return decoded
            except socket.timeout:
                print(f"{RED}[{now()}] REPLY   {label} timeout{RESET}", flush=True)
                return None
    except Exception as exc:  # noqa: BLE001
        print(f"{RED}[{now()}] ERROR   {label} {host}:{port} {exc}{RESET}", flush=True)
        return None


def send_persistent(*, host: str, port: int, message: str, count: int, interval: float, timeout: float, read_reply: bool) -> None:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        local = sock.getsockname()
        print(f"{CYAN}[{now()}] CONNECT persistent target={host}:{port} local={local}{RESET}", flush=True)
        for i in range(1, count + 1):
            payload = f"{message} #{i} ts={now()}\n".encode("utf-8")
            print(f"{GREEN}[{now()}] SEND    persistent #{i}/{count} bytes={len(payload)} payload={payload.decode('utf-8', errors='replace').strip()!r}{RESET}", flush=True)
            sock.sendall(payload)
            if read_reply:
                try:
                    reply = sock.recv(65536)
                    print(f"{YELLOW}[{now()}] REPLY   persistent #{i}/{count} bytes={len(reply)} payload={reply.decode('utf-8', errors='replace').strip()!r}{RESET}", flush=True)
                except socket.timeout:
                    print(f"{RED}[{now()}] REPLY   persistent #{i}/{count} timeout{RESET}", flush=True)
            if i != count:
                time.sleep(max(0.0, interval))
        print(f"{CYAN}[{now()}] CLOSE   persistent target={host}:{port}{RESET}", flush=True)


def send_concurrent(*, host: str, port: int, message: str, count: int, hold: float, timeout: float, read_reply: bool) -> None:
    def worker(i: int) -> None:
        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                sock.settimeout(timeout)
                local = sock.getsockname()
                payload = f"{message} concurrent=#{i} ts={now()}\n".encode("utf-8")
                print(f"{CYAN}[{now()}] CONNECT concurrent #{i}/{count} target={host}:{port} local={local}{RESET}", flush=True)
                sock.sendall(payload)
                print(f"{GREEN}[{now()}] SEND    concurrent #{i}/{count} bytes={len(payload)}{RESET}", flush=True)
                if read_reply:
                    try:
                        reply = sock.recv(65536)
                        print(f"{YELLOW}[{now()}] REPLY   concurrent #{i}/{count} bytes={len(reply)} payload={reply.decode('utf-8', errors='replace').strip()!r}{RESET}", flush=True)
                    except socket.timeout:
                        print(f"{RED}[{now()}] REPLY   concurrent #{i}/{count} timeout{RESET}", flush=True)
                time.sleep(max(0.0, hold))
                print(f"{CYAN}[{now()}] CLOSE   concurrent #{i}/{count}{RESET}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"{RED}[{now()}] ERROR   concurrent #{i}/{count} {exc}{RESET}", flush=True)

    threads: list[threading.Thread] = []
    for i in range(1, count + 1):
        thread = threading.Thread(target=worker, args=(i,), daemon=False)
        thread.start()
        threads.append(thread)
        time.sleep(0.05)
    for thread in threads:
        thread.join()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Send TCP payloads to a Doctor Dev forwarding/listener port. "
            "Default behavior is one TCP connection per message, because Doctor Dev balancers choose a target per connection."
        )
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--message", default="hello-from-lab-sender")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--interval", type=float, default=0.3)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--no-read", action="store_true", help="send data but do not wait for reply")
    parser.add_argument(
        "--mode",
        choices=["per-message", "persistent", "concurrent"],
        default="per-message",
        help=(
            "per-message opens a fresh TCP connection for each payload; "
            "persistent sends all payloads on one TCP connection; "
            "concurrent opens many simultaneous connections for least_connections tests."
        ),
    )
    parser.add_argument("--hold", type=float, default=5.0, help="seconds to keep concurrent connections open")
    args = parser.parse_args()

    read_reply = not args.no_read
    if args.mode == "persistent":
        send_persistent(
            host=args.host,
            port=args.port,
            message=args.message,
            count=max(1, args.count),
            interval=args.interval,
            timeout=args.timeout,
            read_reply=read_reply,
        )
    elif args.mode == "concurrent":
        send_concurrent(
            host=args.host,
            port=args.port,
            message=args.message,
            count=max(1, args.count),
            hold=args.hold,
            timeout=args.timeout,
            read_reply=read_reply,
        )
    else:
        for i in range(1, max(1, args.count) + 1):
            payload = f"{args.message} #{i} ts={now()}\n".encode("utf-8")
            send_once(
                host=args.host,
                port=args.port,
                payload=payload,
                timeout=args.timeout,
                read_reply=read_reply,
                label=f"per-message #{i}/{args.count}",
            )
            if i != args.count:
                time.sleep(max(0.0, args.interval))
        print(f"{BOLD}[{now()}] DONE mode={args.mode} count={args.count} target={args.host}:{args.port}{RESET}", flush=True)


if __name__ == "__main__":
    main()
