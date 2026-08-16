from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.domain.common.exceptions import DomainError, InvalidStatusTransitionError
from app.domain.payment.enums import Currency, PaymentStatus
from app.domain.payment.values import Amount, IdempotencyKey, WebhookUrl


@dataclass
class Payment:

    id: UUID
    amount: Amount
    currency: Currency
    description: str
    idempotency_key: IdempotencyKey
    webhook_url: WebhookUrl
    status: PaymentStatus
    created_at: datetime
    processed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.description, str):
            raise DomainError(
                f"Описание платежа должно быть строкой, передано {type(self.description).__name__}"
            )
        if not isinstance(self.metadata, dict):
            raise DomainError(
                f"Метаданные должны быть словарём, передано {type(self.metadata).__name__}"
            )
        _ensure_aware(self.created_at, "created_at")
        if self.processed_at is not None:
            _ensure_aware(self.processed_at, "processed_at")

    @classmethod
    def create(
        cls,
        *,
        amount: Amount,
        currency: Currency,
        description: str,
        idempotency_key: IdempotencyKey,
        webhook_url: WebhookUrl,
        metadata: dict[str, Any] | None = None,
        payment_id: UUID | None = None,
        created_at: datetime | None = None,
    ) -> "Payment":
        """Собрать новый платёж в статусе pending."""
        return cls(
            id=payment_id or uuid4(),
            amount=amount,
            currency=currency,
            description=description,
            idempotency_key=idempotency_key,
            webhook_url=webhook_url,
            status=PaymentStatus.PENDING,
            created_at=created_at or datetime.now(UTC),
            processed_at=None,
            metadata=metadata if metadata is not None else {},
        )

    @property
    def is_processed(self) -> bool:
        return self.status.is_final

    def mark_succeeded(self, processed_at: datetime | None = None) -> None:
        self._transition_to(PaymentStatus.SUCCEEDED, processed_at)

    def mark_failed(self, processed_at: datetime | None = None) -> None:
        self._transition_to(PaymentStatus.FAILED, processed_at)

    def _transition_to(self, status: PaymentStatus, processed_at: datetime | None) -> None:
        if self.status is not PaymentStatus.PENDING:
            raise InvalidStatusTransitionError(
                f"Платёж {self.id} уже в статусе {self.status}, " f"перевод в {status} невозможен"
            )
        if processed_at is not None:
            _ensure_aware(processed_at, "processed_at")
        self.status = status
        self.processed_at = processed_at or datetime.now(UTC)


def _ensure_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise DomainError(f"{field_name} должен быть datetime, передано {type(value).__name__}")
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise DomainError(f"{field_name} должен содержать таймзону")
