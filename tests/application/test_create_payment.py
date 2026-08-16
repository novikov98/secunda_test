from decimal import Decimal
from uuid import UUID

import pytest

from app.application.common.exceptions import IdempotencyConflictError
from app.application.common.outbox import OutboxMessage
from app.application.payment.dto import CreatePaymentCommand, StoredPayment
from app.application.payment.events import PAYMENT_CREATED
from app.application.payment.interfaces import DuplicateIdempotencyKeyError
from app.application.payment.use_cases.create_payment import CreatePaymentUseCase
from app.domain.payment.entities import Payment
from app.domain.payment.enums import Currency, PaymentStatus
from app.domain.payment.values import Amount, IdempotencyKey, WebhookUrl

IDEMPOTENCY_KEY = "order-42"


class FakePaymentRepository:
    """Хранилище в памяти: add откладывает запись до commit."""

    def __init__(self) -> None:
        self.committed: dict[str, StoredPayment] = {}
        self.staged: StoredPayment | None = None

    async def add(self, payment: Payment, request_hash: str) -> None:
        self.staged = StoredPayment(payment, request_hash)

    async def get(self, payment_id: UUID) -> Payment | None:
        for stored in self.committed.values():
            if stored.payment.id == payment_id:
                return stored.payment
        return None

    async def get_by_idempotency_key(self, key: str) -> StoredPayment | None:
        return self.committed.get(key)

    def flush(self) -> None:
        if self.staged is not None:
            self.committed[str(self.staged.payment.idempotency_key)] = self.staged
            self.staged = None


class FakeOutboxRepository:
    def __init__(self) -> None:
        self.staged: list[OutboxMessage] = []
        self.committed: list[OutboxMessage] = []

    async def add(self, message: OutboxMessage) -> None:
        self.staged.append(message)

    def flush(self) -> None:
        self.committed.extend(self.staged)
        self.staged.clear()


class FakeUnitOfWork:
    def __init__(self, payments: FakePaymentRepository, outbox: FakeOutboxRepository) -> None:
        self._payments = payments
        self._outbox = outbox
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1
        self._payments.flush()
        self._outbox.flush()

    async def rollback(self) -> None:
        self._payments.staged = None
        self._outbox.staged.clear()


class ConflictingUnitOfWork(FakeUnitOfWork):
    """Первый commit падает так, будто ключ занял параллельный запрос."""

    def __init__(
        self,
        payments: FakePaymentRepository,
        outbox: FakeOutboxRepository,
        winner: StoredPayment,
    ) -> None:
        super().__init__(payments, outbox)
        self._winner = winner

    async def commit(self) -> None:
        self.commits += 1
        self._payments.committed[str(self._winner.payment.idempotency_key)] = self._winner
        raise DuplicateIdempotencyKeyError("uq_payments_idempotency_key")


def make_command(**overrides: object) -> CreatePaymentCommand:
    kwargs: dict[str, object] = {
        "amount": Decimal("100.00"),
        "currency": Currency.RUB,
        "description": "Оплата заказа",
        "metadata": {"order_id": 42},
        "webhook_url": "https://example.com/hook",
        "idempotency_key": IDEMPOTENCY_KEY,
        "request_hash": "hash-a",
    }
    kwargs.update(overrides)
    return CreatePaymentCommand(**kwargs)  # type: ignore[arg-type]


def make_stored_payment(request_hash: str = "hash-a") -> StoredPayment:
    """Платёж, как будто уже лежащий в БД."""
    payment = Payment.create(
        amount=Amount(Decimal("100.00")),
        currency=Currency.RUB,
        description="Оплата заказа",
        idempotency_key=IdempotencyKey(IDEMPOTENCY_KEY),
        webhook_url=WebhookUrl("https://example.com/hook"),
    )
    return StoredPayment(payment, request_hash)


@pytest.fixture
def payments() -> FakePaymentRepository:
    return FakePaymentRepository()


@pytest.fixture
def outbox() -> FakeOutboxRepository:
    return FakeOutboxRepository()


class TestCreatePayment:
    async def test_creates_pending_payment(
        self, payments: FakePaymentRepository, outbox: FakeOutboxRepository
    ) -> None:
        use_case = CreatePaymentUseCase(payments, outbox, FakeUnitOfWork(payments, outbox))

        result = await use_case(make_command())

        assert result.created is True
        assert result.payment.status is PaymentStatus.PENDING
        assert result.payment.amount.value == Decimal("100.00")

    async def test_writes_payment_and_event_in_one_commit(
        self, payments: FakePaymentRepository, outbox: FakeOutboxRepository
    ) -> None:
        uow = FakeUnitOfWork(payments, outbox)
        use_case = CreatePaymentUseCase(payments, outbox, uow)

        result = await use_case(make_command())

        assert uow.commits == 1
        assert len(payments.committed) == 1
        assert len(outbox.committed) == 1
        assert outbox.committed[0].event_type == PAYMENT_CREATED
        assert outbox.committed[0].aggregate_id == result.payment.id

    async def test_repeat_returns_same_payment_without_new_event(
        self, payments: FakePaymentRepository, outbox: FakeOutboxRepository
    ) -> None:
        use_case = CreatePaymentUseCase(payments, outbox, FakeUnitOfWork(payments, outbox))
        first = await use_case(make_command())

        second = await use_case(make_command())

        assert second.created is False
        assert second.payment.id == first.payment.id
        assert len(outbox.committed) == 1

    async def test_same_key_with_different_body_conflicts(
        self, payments: FakePaymentRepository, outbox: FakeOutboxRepository
    ) -> None:
        use_case = CreatePaymentUseCase(payments, outbox, FakeUnitOfWork(payments, outbox))
        await use_case(make_command())

        with pytest.raises(IdempotencyConflictError):
            await use_case(make_command(request_hash="hash-b"))

    async def test_loser_of_race_returns_winner_payment(
        self, payments: FakePaymentRepository, outbox: FakeOutboxRepository
    ) -> None:
        """Проигравший гонку запрос отдаёт платёж победителя, а не падает."""
        winner = make_stored_payment()
        use_case = CreatePaymentUseCase(
            payments, outbox, ConflictingUnitOfWork(payments, outbox, winner)
        )

        result = await use_case(make_command())

        assert result.created is False
        assert result.payment.id == winner.payment.id

    async def test_loser_of_race_with_different_body_conflicts(
        self, payments: FakePaymentRepository, outbox: FakeOutboxRepository
    ) -> None:
        winner = make_stored_payment(request_hash="hash-a")
        use_case = CreatePaymentUseCase(
            payments, outbox, ConflictingUnitOfWork(payments, outbox, winner)
        )

        with pytest.raises(IdempotencyConflictError):
            await use_case(make_command(request_hash="hash-b"))
