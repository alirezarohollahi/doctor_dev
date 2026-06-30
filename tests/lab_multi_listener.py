
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from typing import Iterable

RESET = "\033[0m"
BOLD = "\033[1m"
COLORS = [
    "\033[38;5;39m",   # blue
    "\033[38;5;82m",   # green
    "\033[38;5;214m",  # orange
    "\033[38;5;201m",  # magenta
    "\033[38;5;51m",   # cyan
    "\033[38;5;196m",  # red
]


def now() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def color_for(index: int) -> str:
    return COLORS[index % len(COLORS)]


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, listen_host: str, listen_port: int, color: str) -> None:
    peer = writer.get_extra_info("peername")
    local = writer.get_extra_info("sockname")
    print(f"{color}{BOLD}[{now()}] CONNECT listener={listen_host}:{listen_port} local={local} peer={peer}{RESET}", flush=True)
    total = 0
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            total += len(data)
            text = data.decode("utf-8", errors="replace")
            safe = text.replace("\r", "\\r").replace("\n", "\\n")
            print(f"{color}[{now()}] DATA    listener_port={listen_port} bytes={len(data)} total={total} peer={peer} payload={safe!r}{RESET}", flush=True)
            reply = f"LAB_REPLY listener_port={listen_port} received_bytes={len(data)} total_bytes={total}\n"
            writer.write(reply.encode("utf-8"))
            await writer.drain()
    except Exception as exc:  # noqa: BLE001
        print(f"{color}[{now()}] ERROR   listener_port={listen_port} peer={peer} error={exc}{RESET}", flush=True)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        print(f"{color}[{now()}] CLOSE   listener_port={listen_port} peer={peer} total_bytes={total}{RESET}", flush=True)


async def start_one(host: str, port: int, index: int) -> asyncio.AbstractServer:
    color = color_for(index)
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, host, port, color),
        host=host,
        port=port,
        backlog=4096,
        start_serving=True,
    )
    sockets = server.sockets or []
    for sock in sockets:
        print(f"{color}{BOLD}[READY] listening on {sock.getsockname()} color_index={index}{RESET}", flush=True)
    return server


def parse_ports(raw: str) -> list[int]:
    result: list[int] = []
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            if end < start:
                start, end = end, start
            result.extend(range(start, end + 1))
        else:
            result.append(int(part))
    cleaned: list[int] = []
    for port in result:
        if not 1 <= port <= 65535:
            raise SystemExit(f"invalid port: {port}")
        if port not in cleaned:
            cleaned.append(port)
    return cleaned


async def main() -> None:
    parser = argparse.ArgumentParser(description="Colorful multi-port TCP listener for Doctor Dev forwarding tests.")
    parser.add_argument("--host", default="127.0.0.1", help="bind host, default: 127.0.0.1")
    parser.add_argument("--ports", default="9101,9102,9103,9104", help="comma/range ports, e.g. 9101,9102 or 9101-9104")
    args = parser.parse_args()

    ports = parse_ports(args.ports)
    servers = [await start_one(args.host, port, idx) for idx, port in enumerate(ports)]
    print(f"{BOLD}Lab listener is ready. Ports: {', '.join(map(str, ports))}{RESET}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        for server in servers:
            server.close()
        await asyncio.gather(*(server.wait_closed() for server in servers), return_exceptions=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")



