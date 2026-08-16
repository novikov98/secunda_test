from typing import Any, Protocol
from uuid import UUID

from app.application.payment.dto import StoredPayment
from app.domain.payment.entities import Payment


class DuplicateIdempotencyKeyError(Exception):
    """Ключ идемпотентности занят — репозиторий не смог вставить платёж."""


class WebhookDeliveryError(Exception):
    """Уведомление не доставлено ни с одной попытки."""


class PaymentRepository(Protocol):
    async def add(self, payment: Payment, request_hash: str) -> None: ...

    async def get(self, payment_id: UUID) -> Payment | None: ...

    async def get_by_idempotency_key(self, key: str) -> StoredPayment | None: ...

    async def update_status(self, payment: Payment) -> bool:
        """Проставить финальный статус. False, если платёж уже не pending."""
        ...


class PaymentGateway(Protocol):
    async def charge(self, payment: Payment) -> bool:
        """True — платёж прошёл, False — отклонён шлюзом."""
        ...


class WebhookSender(Protocol):
    async def send(self, url: str, payload: dict[str, Any]) -> None: ...
