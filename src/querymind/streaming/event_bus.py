"""EventBus: in-process, async, fan-out pub/sub keyed by `correlation_id`.

No persistent subscriptions, no external broker (Kafka, Redis, RabbitMQ)
-- every topic and every subscriber queue lives only as long as this
process, and only as long as at least one subscriber is registered for
it; see rule 9 of the Phase 17 spec. Publishers know nothing about
subscribers; subscribers know nothing about publishers -- both only ever
talk to this bus (rule 3).

A single asyncio event loop, with no `await` between checking and
mutating `_subscribers`, already makes every method below atomic with
respect to every other coroutine -- no `asyncio.Lock` is needed, and
adding one would only obscure that.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass

from querymind.streaming.exceptions import UnknownSubscriptionError
from querymind.streaming.models import PipelineEvent


@dataclass(frozen=True, slots=True)
class Subscription:
    """A handle returned by `EventBus.subscribe`. Pass it back to `EventBus.unsubscribe` when
    done -- `queue` is where every event published for `correlation_id` arrives, in order.
    """

    correlation_id: str
    queue: asyncio.Queue[PipelineEvent]


class EventBus:
    """Fan-out pub/sub: every subscriber currently registered for a `correlation_id` receives
    every event published to it -- an independent, unbounded `asyncio.Queue` per subscriber
    (rule 5: "use asyncio.Queue where appropriate"; unbounded so a slow subscriber's `publish`
    is never blocked by another, and `publish` itself never blocks on a full queue).
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[PipelineEvent]]] = defaultdict(set)

    async def subscribe(self, correlation_id: str) -> Subscription:
        """Register a new, empty queue for `correlation_id` and return a handle to it."""
        queue: asyncio.Queue[PipelineEvent] = asyncio.Queue()
        self._subscribers[correlation_id].add(queue)
        return Subscription(correlation_id=correlation_id, queue=queue)

    async def unsubscribe(self, subscription: Subscription) -> None:
        """Remove `subscription`'s queue. Drops the whole topic once its last subscriber leaves,
        so a correlation_id nobody is listening to never accumulates state forever.
        """
        queues = self._subscribers.get(subscription.correlation_id)
        if queues is None or subscription.queue not in queues:
            raise UnknownSubscriptionError(
                f"No active subscription for correlation_id={subscription.correlation_id!r} "
                "matches this queue -- it may already have been unsubscribed."
            )
        queues.discard(subscription.queue)
        if not queues:
            del self._subscribers[subscription.correlation_id]

    async def publish(self, event: PipelineEvent) -> None:
        """Fan `event` out to every subscriber currently listening on `event.correlation_id`.
        A silent no-op if nobody is subscribed -- a publisher never knows or needs to know
        whether anyone is listening (rule 3).
        """
        for queue in tuple(self._subscribers.get(event.correlation_id, ())):
            queue.put_nowait(event)

    def subscriber_count(self, correlation_id: str) -> int:
        """How many subscribers are currently registered for `correlation_id`. Observability/
        testing only -- no publish/subscribe decision in this class ever depends on it.
        """
        return len(self._subscribers.get(correlation_id, ()))
