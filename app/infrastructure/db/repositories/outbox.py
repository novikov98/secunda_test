from sqlalchemy.ext.asyncio import AsyncSession

from app.application.common.outbox import OutboxMessage
from app.infrastructure.db.models import OutboxMessageModel


class SqlAlchemyOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, message: OutboxMessage) -> None:
        self._session.add(
            OutboxMessageModel(
                id=message.id,
                aggregate_id=message.aggregate_id,
                event_type=message.event_type,
                payload=message.payload,
            )
        )
