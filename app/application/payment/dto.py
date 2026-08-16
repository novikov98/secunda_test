from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.domain.payment.entities import Payment
from app.domain.payment.enums import Currency


@dataclass(frozen=True)
class CreatePaymentCommand:
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    webhook_url: str
    idempotency_key: str
    # sha256 тела запроса, чтобы отличить повтор от конфликта.
    request_hash: str


@dataclass(frozen=True)
class StoredPayment:
    """Платёж вместе с хешом запроса, которым он был создан."""

    payment: Payment
    request_hash: str


@dataclass(frozen=True)
class CreatePaymentResult:
    payment: Payment
    # False, если платёж уже существовал и запрос оказался повтором.
    created: bool
