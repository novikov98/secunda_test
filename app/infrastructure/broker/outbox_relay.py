import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.broker.publisher import RabbitEventPublisher
from app.infrastructure.config import OutboxSettings
from app.infrastructure.db.models import OutboxMessageModel

logger = logging.getLogger(__name__)

_MAX_ERROR_LENGTH = 500


class OutboxRelay:
    """Фоновый цикл: публикует события из outbox и отмечает их как отправленные."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        publisher: RabbitEventPublisher,
        settings: OutboxSettings,
    ) -> None:
        self._session_factory = session_factory
        self._publisher = publisher
        self._settings = settings

    async def run(self) -> None:
        while True:
            try:
                published = await self.publish_batch()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Проход outbox relay завершился ошибкой")
                published = 0

            if published == 0:
                await asyncio.sleep(self._settings.poll_interval_seconds)

    async def publish_batch(self) -> int:
        """Опубликовать одну пачку событий. Возвращает число отправленных."""
        async with self._session_factory() as session, session.begin():
            messages = await self._lock_unpublished(session)

            published = 0
            for message in messages:
                try:
                    await self._publisher.publish(message.id, message.event_type, message.payload)
                except Exception as exc:
                    message.attempts += 1
                    message.last_error = str(exc)[:_MAX_ERROR_LENGTH]
                    logger.warning(f"Не удалось опубликовать событие {message.id}: {exc}")
                else:
                    message.published_at = datetime.now(UTC)
                    published += 1

            return published

    async def _lock_unpublished(self, session: AsyncSession) -> list[OutboxMessageModel]:
        result = await session.execute(
            select(OutboxMessageModel)
            .where(OutboxMessageModel.published_at.is_(None))
            .order_by(OutboxMessageModel.created_at)
            .limit(self._settings.batch_size)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())
