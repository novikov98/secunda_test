from app.application.common.exceptions import IdempotencyConflictError
from app.application.common.interfaces import OutboxRepository, UnitOfWork
from app.application.payment.dto import (
    CreatePaymentCommand,
    CreatePaymentResult,
    StoredPayment,
)
from app.application.payment.events import payment_created
from app.application.payment.interfaces import (
    DuplicateIdempotencyKeyError,
    PaymentRepository,
)
from app.domain.payment.entities import Payment
from app.domain.payment.values import Amount, IdempotencyKey, WebhookUrl


class CreatePaymentUseCase:
    """Создать платёж и положить событие в outbox одной транзакцией."""

    def __init__(
        self,
        payments: PaymentRepository,
        outbox: OutboxRepository,
        uow: UnitOfWork,
    ) -> None:
        self._payments = payments
        self._outbox = outbox
        self._uow = uow

    async def __call__(self, command: CreatePaymentCommand) -> CreatePaymentResult:
        existing = await self._payments.get_by_idempotency_key(command.idempotency_key)
        if existing is not None:
            return CreatePaymentResult(self._replay(existing, command), created=False)

        payment = Payment.create(
            amount=Amount(command.amount),
            currency=command.currency,
            description=command.description,
            metadata=command.metadata,
            idempotency_key=IdempotencyKey(command.idempotency_key),
            webhook_url=WebhookUrl(command.webhook_url),
        )

        await self._payments.add(payment, command.request_hash)
        await self._outbox.add(payment_created(payment))

        try:
            await self._uow.commit()
        except DuplicateIdempotencyKeyError:
            # Параллельный запрос с тем же ключом успел вставить платёж первым.
            await self._uow.rollback()
            existing = await self._payments.get_by_idempotency_key(command.idempotency_key)
            if existing is None:
                raise
            return CreatePaymentResult(self._replay(existing, command), created=False)

        return CreatePaymentResult(payment, created=True)

    @staticmethod
    def _replay(existing: StoredPayment, command: CreatePaymentCommand) -> Payment:
        if existing.request_hash != command.request_hash:
            raise IdempotencyConflictError(
                f"Ключ идемпотентности {command.idempotency_key} уже использован "
                "с другим телом запроса"
            )
        return existing.payment
