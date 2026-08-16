import logging
from uuid import UUID

from app.application.common.exceptions import PaymentNotFoundError
from app.application.common.interfaces import UnitOfWork
from app.application.payment.events import webhook_payload
from app.application.payment.interfaces import (
    PaymentGateway,
    PaymentRepository,
    WebhookSender,
)
from app.domain.payment.entities import Payment

logger = logging.getLogger(__name__)


class ProcessPaymentUseCase:
    """Провести платёж через шлюз и уведомить клиента."""

    def __init__(
        self,
        payments: PaymentRepository,
        uow: UnitOfWork,
        gateway: PaymentGateway,
        webhooks: WebhookSender,
    ) -> None:
        self._payments = payments
        self._uow = uow
        self._gateway = gateway
        self._webhooks = webhooks

    async def __call__(self, payment_id: UUID) -> None:
        payment = await self._payments.get(payment_id)
        if payment is None:
            raise PaymentNotFoundError(f"Платёж {payment_id} не найден")

        # Повторно платёж не проводим, а уведомление шлём в любом случае:
        # сообщение могло вернуться именно из-за неудачной отправки webhook.
        if not payment.is_processed:
            payment = await self._charge(payment)

        await self._webhooks.send(str(payment.webhook_url), webhook_payload(payment))

    async def _charge(self, payment: Payment) -> Payment:
        if await self._gateway.charge(payment):
            payment.mark_succeeded()
        else:
            payment.mark_failed()

        applied = await self._payments.update_status(payment)
        await self._uow.commit()
        if applied:
            return payment

        logger.info(f"Платёж {payment.id} обработал параллельный consumer")
        current = await self._payments.get(payment.id)
        return current if current is not None else payment
