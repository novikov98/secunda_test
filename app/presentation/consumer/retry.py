import logging
from typing import Any

from faststream.rabbit import RabbitBroker
from faststream.rabbit.annotations import RabbitMessage

from app.infrastructure.broker.topology import (
    DEAD_ROUTING_KEY,
    RETRY_ROUTING_KEY,
    dlx_exchange,
)
from app.infrastructure.config import RabbitSettings

logger = logging.getLogger(__name__)

ATTEMPT_HEADER = "x-attempt"
ERROR_HEADER = "x-error"

_MAX_ERROR_LENGTH = 200


class RetryPolicy:
    """Повторы через payments.retry и перевод в DLQ после исчерпания попыток."""

    def __init__(self, broker: RabbitBroker, settings: RabbitSettings) -> None:
        self._broker = broker
        self._settings = settings

    def attempt_of(self, message: RabbitMessage) -> int:
        """Номер текущей попытки, считая с единицы."""
        raw = message.headers.get(ATTEMPT_HEADER, 1)
        try:
            return max(int(raw), 1)
        except (TypeError, ValueError):
            return 1

    async def on_failure(self, payload: dict[str, Any], attempt: int, error: Exception) -> None:
        if attempt >= self._settings.max_delivery_attempts:
            await self._to_dlq(payload, attempt, error)
        else:
            await self._to_retry(payload, attempt, error)

    async def _to_retry(self, payload: dict[str, Any], attempt: int, error: Exception) -> None:
        delay = self._settings.retry_base_delay_seconds * 2 ** (attempt - 1)
        logger.warning(
            f"Попытка {attempt} из {self._settings.max_delivery_attempts} "
            f"не удалась ({error}), повтор через {delay:.1f} сек"
        )
        # Задержка живёт на самом сообщении, поэтому растёт от попытки к попытке.
        # По истечении TTL очередь вернёт его в payments.new.
        await self._broker.publish(
            payload,
            exchange=dlx_exchange,
            routing_key=RETRY_ROUTING_KEY,
            headers=self._headers(attempt + 1, error),
            expiration=delay,
            persist=True,
        )

    async def _to_dlq(self, payload: dict[str, Any], attempt: int, error: Exception) -> None:
        logger.error(f"Попытки исчерпаны ({attempt}), сообщение уходит в DLQ: {error}")
        await self._broker.publish(
            payload,
            exchange=dlx_exchange,
            routing_key=DEAD_ROUTING_KEY,
            headers=self._headers(attempt, error),
            persist=True,
        )

    @staticmethod
    def _headers(attempt: int, error: Exception) -> dict[str, Any]:
        return {
            ATTEMPT_HEADER: attempt,
            ERROR_HEADER: f"{type(error).__name__}: {error}"[:_MAX_ERROR_LENGTH],
        }
