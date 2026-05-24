from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import List, Optional
from dataclasses import dataclass

from doctor_dev.models.runtime import ProcessRuntime

BUFFER_SIZE = 65535
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedTarget:
    host: str
    port: int


class TunnelProcess:
    def __init__(
        self,
        process_id: str,
        group_name: str,
        listen_host: str,
        public_host: str,
        listen_port: int,
        target_provider: Callable[[], List[ResolvedTarget]],
        strategy: str = "round_robin",
    ):
        self.process_id = process_id
        self.group_name = group_name
        self.listen_host = listen_host
        self.public_host = public_host
        self.listen_port = listen_port
        self.target_provider = target_provider
        self.strategy = strategy
        self.server: Optional[asyncio.AbstractServer] = None
        self._rr_index = 0
        self.runtime = ProcessRuntime(
            process_id=process_id,
            group_name=group_name,
            listen_host=listen_host,
            public_host=public_host,
            listen_port=listen_port,
            status="stopped",
        )

    async def start(self) -> None:
        if self.server is not None:
            return
        self.server = await asyncio.start_server(
            self._handle_client,
            self.listen_host,
            self.listen_port,
            backlog=4096,
        )
        sockets = self.server.sockets or []
        if sockets:
            self.listen_port = int(sockets[0].getsockname()[1])
            self.runtime.listen_port = self.listen_port
        self.runtime.status = "running"
        LOGGER.info("[%s] listening on %s:%s", self.process_id, self.listen_host, self.listen_port)

    async def stop(self) -> None:
        self.runtime.status = "stopping"
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        self.runtime.status = "stopped"
        LOGGER.info("[%s] stopped", self.process_id)

    def snapshot(self) -> ProcessRuntime:
        return self.runtime.model_copy(deep=True)

    def _choose_targets(self) -> List[ResolvedTarget]:
        targets = self.target_provider()
        if not targets:
            return []
        if self.strategy == "failover":
            return targets
        index = self._rr_index % len(targets)
        self._rr_index += 1
        return targets[index:] + targets[:index]

    async def _handle_client(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        client_addr = client_writer.get_extra_info("peername")
        self.runtime.connection_count += 1
        self.runtime.active_connections += 1
        target_reader = None
        target_writer = None
        chosen_target = None
        try:
            targets = self._choose_targets()
            if not targets:
                raise RuntimeError("no resolved targets available")

            last_error: Optional[Exception] = None
            for target in targets:
                try:
                    chosen_target = target
                    target_reader, target_writer = await asyncio.open_connection(target.host, target.port)
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    LOGGER.warning(
                        "[%s] target connect failed %s:%s for client %s: %s",
                        self.process_id,
                        target.host,
                        target.port,
                        client_addr,
                        exc,
                    )
                    target_reader = None
                    target_writer = None

            if target_reader is None or target_writer is None:
                raise RuntimeError(f"all targets failed; last_error={last_error}")

            LOGGER.info(
                "[%s] client %s -> target %s:%s",
                self.process_id,
                client_addr,
                chosen_target.host,
                chosen_target.port,
            )

            client_to_target = asyncio.create_task(
                self._pipe(client_reader, target_writer, "in")
            )
            target_to_client = asyncio.create_task(
                self._pipe(target_reader, client_writer, "out")
            )
            done, pending = await asyncio.wait(
                [client_to_target, target_to_client],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)
        except Exception as exc:  # noqa: BLE001
            self.runtime.last_error = str(exc)
            LOGGER.exception("[%s] connection error for %s: %s", self.process_id, client_addr, exc)
        finally:
            self.runtime.active_connections = max(0, self.runtime.active_connections - 1)
            for writer in [client_writer, target_writer]:
                if writer is not None:
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except Exception:
                        pass

    async def _pipe(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        direction: str,
    ) -> None:
        try:
            while True:
                data = await reader.read(BUFFER_SIZE)
                if not data:
                    break
                if direction == "in":
                    self.runtime.bytes_in += len(data)
                else:
                    self.runtime.bytes_out += len(data)
                writer.write(data)
                await writer.drain()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self.runtime.last_error = str(exc)
            LOGGER.debug("[%s] pipe %s ended: %s", self.process_id, direction, exc)
        finally:
            try:
                writer.close()
            except Exception:
                pass
