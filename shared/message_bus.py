from __future__ import annotations
import asyncio
from typing import Any


class MessageBus:
    """
    Lightweight in-process pub/sub using asyncio.Queue.
    One queue per channel — producers await publish(), consumers await consume().
    Drop-in replaceable with Redis streams later if you need multi-process scaling.
    """

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}

    def _get_queue(self, channel: str) -> asyncio.Queue:
        if channel not in self._queues:
            self._queues[channel] = asyncio.Queue()
        return self._queues[channel]

    async def publish(self, channel: str, message: Any) -> None:
        await self._get_queue(channel).put(message)

    async def consume(self, channel: str) -> Any:
        """Block until a message arrives on this channel."""
        return await self._get_queue(channel).get()

    async def consume_nowait(self, channel: str) -> Any | None:
        """Return immediately — None if queue is empty."""
        try:
            return self._get_queue(channel).get_nowait()
        except asyncio.QueueEmpty:
            return None

    def qsize(self, channel: str) -> int:
        return self._get_queue(channel).qsize()


# Singleton — import and use everywhere
bus = MessageBus()
