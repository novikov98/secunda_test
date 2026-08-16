from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.payment.interfaces import DuplicateIdempotencyKeyError

_IDEMPOTENCY_KEY_CONSTRAINT = "uq_payments_idempotency_key"


class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        try:
            await self._session.commit()
        except IntegrityError as exc:
            if _IDEMPOTENCY_KEY_CONSTRAINT in str(exc.orig):
                raise DuplicateIdempotencyKeyError(str(exc.orig)) from exc
            raise

    async def rollback(self) -> None:
        await self._session.rollback()
