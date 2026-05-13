"""Download photos from MinIO via the internal docker network so we can send
them as BufferedInputFile — Telegram's servers can't reach `minio:9000`.

Cached lightly in-process by URL; presigned URLs change per request so the
hit rate is mostly per-handler-call, but it shields against double-fetch.
"""

from __future__ import annotations

import aiohttp

from aiogram.types import BufferedInputFile

from shared.logging import get_logger

logger = get_logger(__name__)


async def fetch_as_input_file(url: str, name: str = "photo.jpg") -> BufferedInputFile | None:
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        ) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning("photo_fetch_failed", url=url, status=resp.status)
                    return None
                data = await resp.read()
        return BufferedInputFile(data, filename=name)
    except Exception:
        logger.exception("photo_fetch_error", url=url)
        return None
