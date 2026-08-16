from typing import Any
from uuid import UUID

from faststream.rabbit import RabbitBroker

from app.infrastructure.broker.topology import NEW_ROUTING_KEY, payments_exchange


class RabbitEventPublisher:
    """Публикация событий из outbox в payments.new."""

    def __init__(self, broker: RabbitBroker) -> None:
        self._broker = broker

    async def publish(self, message_id: UUID, event_type: str, payload: dict[str, Any]) -> None:
        await self._broker.publish(
            payload,
            exchange=payments_exchange,
            routing_key=NEW_ROUTING_KEY,
            message_id=str(message_id),
            headers={"x-event-type": event_type},
            # Сообщение должно пережить перезапуск брокера.
            persist=True,
        )
