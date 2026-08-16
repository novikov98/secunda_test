import logging
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.application.payment.interfaces import WebhookDeliveryError
from app.infrastructure.config import WebhookSettings

logger = logging.getLogger(__name__)


class HttpxWebhookSender:
    """Отправка уведомления с повторами и экспоненциальной задержкой."""

    def __init__(self, client: httpx.AsyncClient, settings: WebhookSettings) -> None:
        self._client = client
        self._settings = settings

    async def send(self, url: str, payload: dict[str, Any]) -> None:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._settings.max_attempts),
                wait=wait_exponential(multiplier=self._settings.retry_base_delay_seconds),
                retry=retry_if_exception_type((httpx.HTTPError, httpx.StreamError)),
                reraise=False,
            ):
                with attempt:
                    await self._post(url, payload, attempt.retry_state.attempt_number)
        except RetryError as exc:
            raise WebhookDeliveryError(
                f"Уведомление на {url} не доставлено за {self._settings.max_attempts} попыток"
            ) from exc

    async def _post(self, url: str, payload: dict[str, Any], attempt: int) -> None:
        logger.info(f"Отправка webhook на {url}, попытка {attempt}")
        response = await self._client.post(
            url, json=payload, timeout=self._settings.timeout_seconds
        )
        # 4xx и 5xx одинаково считаем неудачей: приёмник мог ещё не подняться.
        response.raise_for_status()
