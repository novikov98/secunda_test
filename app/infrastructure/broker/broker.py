from faststream.rabbit import RabbitBroker

from app.infrastructure.broker.topology import (
    DEAD_ROUTING_KEY,
    NEW_ROUTING_KEY,
    RETRY_ROUTING_KEY,
    dlq_queue,
    dlx_exchange,
    new_queue,
    payments_exchange,
    retry_queue,
)
from app.infrastructure.config import RabbitSettings


def create_broker(settings: RabbitSettings) -> RabbitBroker:
    return RabbitBroker(settings.dsn)


async def declare_topology(broker: RabbitBroker) -> None:
    """Создать обменники, очереди и привязки между ними."""
    payments = await broker.declare_exchange(payments_exchange)
    dlx = await broker.declare_exchange(dlx_exchange)

    new = await broker.declare_queue(new_queue)
    retry = await broker.declare_queue(retry_queue)
    dlq = await broker.declare_queue(dlq_queue)

    await new.bind(payments, routing_key=NEW_ROUTING_KEY)
    await retry.bind(dlx, routing_key=RETRY_ROUTING_KEY)
    await dlq.bind(dlx, routing_key=DEAD_ROUTING_KEY)
