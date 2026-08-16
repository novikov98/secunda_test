from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.payment.dto import StoredPayment
from app.domain.payment.entities import Payment
from app.domain.payment.enums import PaymentStatus
from app.infrastructure.db.mappers import payment_from_model, payment_to_model
from app.infrastructure.db.models import PaymentModel


class SqlAlchemyPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, payment: Payment, request_hash: str) -> None:
        self._session.add(payment_to_model(payment, request_hash))

    async def get(self, payment_id: UUID) -> Payment | None:
        model = await self._session.get(PaymentModel, payment_id)
        return payment_from_model(model) if model is not None else None

    async def get_by_idempotency_key(self, key: str) -> StoredPayment | None:
        model = (
            await self._session.execute(
                select(PaymentModel).where(PaymentModel.idempotency_key == key)
            )
        ).scalar_one_or_none()
        if model is None:
            return None
        return StoredPayment(payment_from_model(model), model.request_hash)

    async def update_status(self, payment: Payment) -> bool:
        # Условие на pending отсекает второй обработчик, если сообщение задвоилось.
        result = await self._session.execute(
            update(PaymentModel)
            .where(
                PaymentModel.id == payment.id,
                PaymentModel.status == PaymentStatus.PENDING,
            )
            .values(status=payment.status, processed_at=payment.processed_at)
        )
        return bool(result.rowcount)
