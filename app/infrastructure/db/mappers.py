"""Перекладывание платежа между доменной сущностью и моделью БД."""

from app.domain.payment.entities import Payment
from app.domain.payment.values import Amount, IdempotencyKey, WebhookUrl
from app.infrastructure.db.models import PaymentModel


def payment_to_model(payment: Payment, request_hash: str) -> PaymentModel:
    return PaymentModel(
        id=payment.id,
        amount=payment.amount.value,
        currency=payment.currency,
        description=payment.description,
        meta=payment.metadata,
        status=payment.status,
        idempotency_key=str(payment.idempotency_key),
        request_hash=request_hash,
        webhook_url=str(payment.webhook_url),
        created_at=payment.created_at,
        processed_at=payment.processed_at,
    )


def payment_from_model(model: PaymentModel) -> Payment:
    return Payment(
        id=model.id,
        amount=Amount(model.amount),
        currency=model.currency,
        description=model.description,
        metadata=dict(model.meta),
        idempotency_key=IdempotencyKey(model.idempotency_key),
        webhook_url=WebhookUrl(model.webhook_url),
        status=model.status,
        created_at=model.created_at,
        processed_at=model.processed_at,
    )
