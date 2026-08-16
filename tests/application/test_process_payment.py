from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.common.exceptions import PaymentNotFoundError
from app.application.payment.use_cases.process_payment import ProcessPaymentUseCase
from app.domain.payment.entities import Payment
from app.domain.payment.enums import Currency, PaymentStatus
from app.domain.payment.values import Amount, IdempotencyKey, WebhookUrl

WEBHOOK_URL = "https://example.com/hook"


def make_payment(status: PaymentStatus = PaymentStatus.PENDING) -> Payment:
    payment = Payment.create(
        amount=Amount(Decimal("100.00")),
        currency=Currency.RUB,
        description="Оплата заказа",
        idempotency_key=IdempotencyKey("order-42"),
        webhook_url=WebhookUrl(WEBHOOK_URL),
    )
    if status is PaymentStatus.SUCCEEDED:
        payment.mark_succeeded(datetime(2026, 8, 15, 12, 0, tzinfo=UTC))
    elif status is PaymentStatus.FAILED:
        payment.mark_failed(datetime(2026, 8, 15, 12, 0, tzinfo=UTC))
    return payment


class FakePaymentRepository:
    def __init__(self, payment: Payment | None, status_applied: bool = True) -> None:
        self._payment = payment
        self._status_applied = status_applied
        self.updates = 0

    async def get(self, payment_id: UUID) -> Payment | None:
        if self._payment is not None and self._payment.id == payment_id:
            return self._payment
        return None

    async def update_status(self, payment: Payment) -> bool:
        self.updates += 1
        return self._status_applied


class FakeGateway:
    def __init__(self, result: bool) -> None:
        self._result = result
        self.calls = 0

    async def charge(self, payment: Payment) -> bool:
        self.calls += 1
        return self._result


class FakeWebhookSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []

    async def send(self, url: str, payload: dict[str, Any]) -> None:
        self.sent.append((url, payload))


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        pass


class TestProcessPayment:
    async def test_marks_payment_succeeded(self) -> None:
        payment = make_payment()
        payments = FakePaymentRepository(payment)
        gateway = FakeGateway(result=True)
        webhooks = FakeWebhookSender()
        use_case = ProcessPaymentUseCase(payments, FakeUnitOfWork(), gateway, webhooks)

        await use_case(payment.id)

        assert payment.status is PaymentStatus.SUCCEEDED
        assert payments.updates == 1

    async def test_marks_payment_failed_when_gateway_declines(self) -> None:
        payment = make_payment()
        use_case = ProcessPaymentUseCase(
            FakePaymentRepository(payment),
            FakeUnitOfWork(),
            FakeGateway(result=False),
            FakeWebhookSender(),
        )

        await use_case(payment.id)

        assert payment.status is PaymentStatus.FAILED

    async def test_sends_webhook_with_final_status(self) -> None:
        payment = make_payment()
        webhooks = FakeWebhookSender()
        use_case = ProcessPaymentUseCase(
            FakePaymentRepository(payment), FakeUnitOfWork(), FakeGateway(True), webhooks
        )

        await use_case(payment.id)

        url, payload = webhooks.sent[0]
        assert url == WEBHOOK_URL
        assert payload["payment_id"] == str(payment.id)
        assert payload["status"] == PaymentStatus.SUCCEEDED.value
        assert payload["processed_at"] is not None

    async def test_commits_before_sending_webhook(self) -> None:
        payment = make_payment()
        uow = FakeUnitOfWork()
        use_case = ProcessPaymentUseCase(
            FakePaymentRepository(payment), uow, FakeGateway(True), FakeWebhookSender()
        )

        await use_case(payment.id)

        assert uow.commits == 1

    async def test_duplicate_message_does_not_charge_again(self) -> None:
        """Дубль из очереди не проводит платёж повторно."""
        payment = make_payment(PaymentStatus.SUCCEEDED)
        gateway = FakeGateway(result=True)
        payments = FakePaymentRepository(payment)
        use_case = ProcessPaymentUseCase(payments, FakeUnitOfWork(), gateway, FakeWebhookSender())

        await use_case(payment.id)

        assert gateway.calls == 0
        assert payments.updates == 0

    async def test_duplicate_message_still_sends_webhook(self) -> None:
        """Сообщение могло вернуться именно из-за неудачной отправки уведомления."""
        payment = make_payment(PaymentStatus.FAILED)
        webhooks = FakeWebhookSender()
        use_case = ProcessPaymentUseCase(
            FakePaymentRepository(payment), FakeUnitOfWork(), FakeGateway(True), webhooks
        )

        await use_case(payment.id)

        assert len(webhooks.sent) == 1
        assert webhooks.sent[0][1]["status"] == PaymentStatus.FAILED.value

    async def test_uses_result_of_parallel_consumer(self) -> None:
        """Если статус проставил другой обработчик, берём его результат из БД."""
        payment = make_payment()
        payments = FakePaymentRepository(payment, status_applied=False)
        webhooks = FakeWebhookSender()
        use_case = ProcessPaymentUseCase(payments, FakeUnitOfWork(), FakeGateway(True), webhooks)

        await use_case(payment.id)

        assert len(webhooks.sent) == 1

    async def test_unknown_payment_raises(self) -> None:
        use_case = ProcessPaymentUseCase(
            FakePaymentRepository(None), FakeUnitOfWork(), FakeGateway(True), FakeWebhookSender()
        )

        with pytest.raises(PaymentNotFoundError):
            await use_case(uuid4())
