from uuid import UUID

from app.application.common.exceptions import PaymentNotFoundError
from app.application.payment.interfaces import PaymentRepository
from app.domain.payment.entities import Payment


class GetPaymentUseCase:
    """Вернуть платёж по идентификатору."""

    def __init__(self, payments: PaymentRepository) -> None:
        self._payments = payments

    async def __call__(self, payment_id: UUID) -> Payment:
        payment = await self._payments.get(payment_id)
        if payment is None:
            raise PaymentNotFoundError(f"Платёж {payment_id} не найден")
        return payment
