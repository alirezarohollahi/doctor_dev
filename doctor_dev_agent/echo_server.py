from __future__ import annotations

import asyncio
from typing import Callable


async def start_echo_server(host: str, port: int, log: Callable[[str, str], None], label: str = "local") -> asyncio.AbstractServer:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        log("info", f"echo accepted peer={peer} on {host}:{port} label={label}")
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                writer.write(f"doctor-dev-echo:{label}:".encode("utf-8") + data)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle, host, port)
    log("info", f"local echo target started on {host}:{port} label={label}")
    return server
