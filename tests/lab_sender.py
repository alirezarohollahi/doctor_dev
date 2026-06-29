#!/usr/bin/env python3
from __future__ import annotations

import argparse
import socket
import time
from datetime import datetime


def now() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def main() -> None:
    parser = argparse.ArgumentParser(description="Send TCP payloads to a Doctor Dev forwarding/listener port.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--message", default="hello-from-lab-sender")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--interval", type=float, default=0.3)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--no-read", action="store_true", help="send data but do not wait for reply")
    args = parser.parse_args()

    with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
        sock.settimeout(args.timeout)
        print(f"[{now()}] CONNECT host={args.host} port={args.port}")
        for i in range(1, args.count + 1):
            payload = f"{args.message} #{i} ts={now()}\n".encode("utf-8")
            print(f"[{now()}] SEND    bytes={len(payload)} payload={payload.decode('utf-8', errors='replace').strip()!r}")
            sock.sendall(payload)
            if not args.no_read:
                try:
                    reply = sock.recv(65536)
                    print(f"[{now()}] REPLY   bytes={len(reply)} payload={reply.decode('utf-8', errors='replace').strip()!r}")
                except socket.timeout:
                    print(f"[{now()}] REPLY   timeout")
            if i != args.count:
                time.sleep(max(0.0, args.interval))
        print(f"[{now()}] DONE")


if __name__ == "__main__":
    main()
