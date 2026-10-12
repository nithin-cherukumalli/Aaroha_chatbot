from __future__ import annotations

import asyncio
import logging
import signal
import socket
import uuid

from app.composition import Container
from app.settings import get_settings


async def worker_loop(container: Container, shutdown: asyncio.Event) -> None:
    worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    while not shutdown.is_set():
        job = container.knowledge.claim_job(worker_id)
        if job:
            await container.knowledge.process_job(job.id)
        else:
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=2)
            except TimeoutError:
                pass


shutdown = asyncio.Event()


def stop(*_: object) -> None:
    shutdown.set()


async def run() -> None:
    settings = get_settings()
    if settings.ingestion_runner != "separate":
        raise RuntimeError("The dedicated worker requires INGESTION_RUNNER=separate.")
    container = Container(settings)
    await container.knowledge.ensure_active_profile()
    await worker_loop(container, shutdown)


if __name__ == "__main__":
    logging.basicConfig(level=get_settings().log_level)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    asyncio.run(run())
