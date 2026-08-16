from typing import Any

from app.application.common.outbox import OutboxMessage
from app.domain.payment.entities import Payment

PAYMENT_CREATED = "payment.created"


def payment_created(payment: Payment) -> OutboxMessage:
    """Событие о новом платеже для очереди payments.new."""
    return OutboxMessage(
        aggregate_id=payment.id,
        event_type=PAYMENT_CREATED,
        payload={
            "payment_id": str(payment.id),
            "amount": str(payment.amount.value),
            "currency": payment.currency.value,
            "webhook_url": str(payment.webhook_url),
            "idempotency_key": str(payment.idempotency_key),
        },
    )


def webhook_payload(payment: Payment) -> dict[str, Any]:
    """Тело уведомления о результате обработки."""
    return {
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": str(payment.amount.value),
        "currency": payment.currency.value,
        "description": payment.description,
        "metadata": payment.metadata,
        "created_at": payment.created_at.isoformat(),
        "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
    }
