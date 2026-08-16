from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.domain.common.exceptions import DomainError, InvalidStatusTransitionError
from app.domain.payment.entities import Payment
from app.domain.payment.enums import Currency, PaymentStatus
from app.domain.payment.values import Amount, IdempotencyKey, WebhookUrl


def make_payment(**overrides: object) -> Payment:
    kwargs: dict[str, object] = {
        "amount": Amount(Decimal("100.00")),
        "currency": Currency.RUB,
        "description": "Оплата заказа №42",
        "idempotency_key": IdempotencyKey("order-42"),
        "webhook_url": WebhookUrl("https://example.com/hook"),
    }
    kwargs.update(overrides)
    return Payment.create(**kwargs)  # type: ignore[arg-type]


class TestCreate:
    def test_new_payment_is_pending(self) -> None:
        payment = make_payment()

        assert payment.status is PaymentStatus.PENDING
        assert payment.processed_at is None
        assert payment.is_processed is False

    def test_generates_id_and_created_at(self) -> None:
        payment = make_payment()

        assert isinstance(payment.id, UUID)
        assert payment.created_at.tzinfo is not None

    def test_accepts_explicit_id_and_created_at(self) -> None:
        payment_id = uuid4()
        created_at = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)

        payment = make_payment(payment_id=payment_id, created_at=created_at)

        assert payment.id == payment_id
        assert payment.created_at == created_at

    def test_metadata_defaults_to_empty_dict(self) -> None:
        assert make_payment().metadata == {}

    def test_metadata_is_not_shared_between_payments(self) -> None:
        first, second = make_payment(), make_payment()

        first.metadata["order_id"] = 42

        assert second.metadata == {}

    def test_rejects_non_string_description(self) -> None:
        with pytest.raises(DomainError, match="Описание платежа"):
            make_payment(description=42)

    def test_rejects_non_dict_metadata(self) -> None:
        with pytest.raises(DomainError, match="Метаданные"):
            make_payment(metadata=["не", "словарь"])

    def test_rejects_naive_created_at(self) -> None:
        with pytest.raises(DomainError, match="таймзону"):
            make_payment(created_at=datetime(2026, 8, 15, 12, 0))  # noqa: DTZ001


class TestTransitions:
    def test_marks_succeeded(self) -> None:
        payment = make_payment()
        processed_at = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)

        payment.mark_succeeded(processed_at)

        assert payment.status is PaymentStatus.SUCCEEDED
        assert payment.processed_at == processed_at
        assert payment.is_processed is True

    def test_marks_failed(self) -> None:
        payment = make_payment()

        payment.mark_failed()

        assert payment.status is PaymentStatus.FAILED
        assert payment.processed_at is not None

    def test_generates_processed_at_when_omitted(self) -> None:
        before = datetime.now(UTC)

        payment = make_payment()
        payment.mark_succeeded()

        assert payment.processed_at is not None
        assert before <= payment.processed_at <= datetime.now(UTC) + timedelta(seconds=1)

    @pytest.mark.parametrize("first", ["mark_succeeded", "mark_failed"])
    @pytest.mark.parametrize("second", ["mark_succeeded", "mark_failed"])
    def test_rejects_second_transition(self, first: str, second: str) -> None:
        """Дубль сообщения из очереди не должен переписывать результат платежа."""
        payment = make_payment()
        getattr(payment, first)()

        with pytest.raises(InvalidStatusTransitionError):
            getattr(payment, second)()

    def test_rejected_transition_keeps_state_intact(self) -> None:
        payment = make_payment()
        payment.mark_succeeded()
        processed_at = payment.processed_at

        with pytest.raises(InvalidStatusTransitionError):
            payment.mark_failed()

        assert payment.status is PaymentStatus.SUCCEEDED
        assert payment.processed_at == processed_at

    def test_rejects_naive_processed_at(self) -> None:
        payment = make_payment()

        with pytest.raises(DomainError, match="таймзону"):
            payment.mark_succeeded(datetime(2026, 8, 15, 12, 0))  # noqa: DTZ001

        assert payment.status is PaymentStatus.PENDING


class TestPaymentStatus:
    def test_pending_is_not_final(self) -> None:
        assert PaymentStatus.PENDING.is_final is False

    @pytest.mark.parametrize("status", [PaymentStatus.SUCCEEDED, PaymentStatus.FAILED])
    def test_terminal_statuses_are_final(self, status: PaymentStatus) -> None:
        assert status.is_final is True
