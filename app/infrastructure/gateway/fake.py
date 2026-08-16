import asyncio
import logging
import random

from app.domain.payment.entities import Payment
from app.infrastructure.config import GatewaySettings

logger = logging.getLogger(__name__)


class FakePaymentGateway:
    """Эмуляция внешнего шлюза: случайная задержка и заданная доля успеха."""

    def __init__(self, settings: GatewaySettings) -> None:
        self._settings = settings

    async def charge(self, payment: Payment) -> bool:
        delay = random.uniform(self._settings.min_delay_seconds, self._settings.max_delay_seconds)
        await asyncio.sleep(delay)

        succeeded = random.random() < self._settings.success_rate
        result = "успех" if succeeded else "отказ"
        logger.info(f"Шлюз обработал платёж {payment.id} за {delay:.1f} сек: {result}")
        return succeeded
