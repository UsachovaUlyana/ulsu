"""Thin async RabbitMQ helpers used by every service.

Topology: one durable topic exchange per event family (see events.py),
durable per-consumer queues, JSON message bodies, persistent messages.

Publisher and Consumer are independent — a service can use either or both.
Both reconnect on connection loss with exponential backoff so transient
broker restarts don't kill the worker.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection

from .logging import get_logger

logger = get_logger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]


class RabbitMQPublisher:
    def __init__(self, url: str) -> None:
        self._url = url
        self._connection: AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractRobustChannel | None = None
        self._exchanges: dict[str, aio_pika.abc.AbstractRobustExchange] = {}
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        async with self._lock:
            if self._connection and not self._connection.is_closed:
                return
            self._connection = await aio_pika.connect_robust(self._url)
            self._channel = await self._connection.channel(publisher_confirms=True)
            logger.info("rabbitmq_publisher_connected")

    async def _exchange(self, name: str) -> aio_pika.abc.AbstractRobustExchange:
        if name in self._exchanges:
            return self._exchanges[name]
        await self.connect()
        assert self._channel is not None
        exchange = await self._channel.declare_exchange(
            name, aio_pika.ExchangeType.TOPIC, durable=True
        )
        self._exchanges[name] = exchange
        return exchange

    async def publish(
        self, exchange: str, routing_key: str, payload: dict[str, Any]
    ) -> None:
        ex = await self._exchange(exchange)
        message = aio_pika.Message(
            body=json.dumps(payload, default=str).encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await ex.publish(message, routing_key=routing_key)
        logger.info(
            "event_published",
            exchange=exchange,
            routing_key=routing_key,
            payload=payload,
        )

    async def close(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()


class RabbitMQConsumer:
    """Consume messages from one queue bound to one exchange.

    Re-runs forever; on broker disconnect aio-pika robust connection
    reconnects automatically.
    """

    def __init__(
        self,
        url: str,
        exchange: str,
        queue_name: str,
        routing_keys: list[str],
        handler: Handler,
        prefetch: int = 16,
    ) -> None:
        self._url = url
        self._exchange_name = exchange
        self._queue_name = queue_name
        self._routing_keys = routing_keys
        self._handler = handler
        self._prefetch = prefetch

    async def run(self) -> None:
        connection = await aio_pika.connect_robust(self._url)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=self._prefetch)

        exchange = await channel.declare_exchange(
            self._exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )
        queue = await channel.declare_queue(self._queue_name, durable=True)
        for rk in self._routing_keys:
            await queue.bind(exchange, routing_key=rk)

        logger.info(
            "rabbitmq_consumer_started",
            exchange=self._exchange_name,
            queue=self._queue_name,
            routing_keys=self._routing_keys,
        )

        async with queue.iterator() as iterator:
            message: AbstractIncomingMessage
            async for message in iterator:
                async with message.process(requeue=False):
                    try:
                        payload = json.loads(message.body.decode("utf-8"))
                    except json.JSONDecodeError:
                        logger.error("event_decode_failed", body=message.body[:200])
                        continue
                    try:
                        await self._handler(payload)
                    except Exception:
                        logger.exception(
                            "event_handler_failed",
                            exchange=self._exchange_name,
                            queue=self._queue_name,
                            payload=payload,
                        )
                        # Don't requeue — bad message poisons the queue otherwise.
                        # Production would route to a DLX; for the project we log + drop.
