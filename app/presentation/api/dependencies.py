import secrets
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.payment.use_cases.create_payment import CreatePaymentUseCase
from app.application.payment.use_cases.get_payment import GetPaymentUseCase
from app.infrastructure.config import Settings, get_settings
from app.infrastructure.db.repositories.outbox import SqlAlchemyOutboxRepository
from app.infrastructure.db.repositories.payment import SqlAlchemyPaymentRepository
from app.infrastructure.db.uow import SqlAlchemyUnitOfWork

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def require_api_key(
    settings: SettingsDep,
    api_key: Annotated[str | None, Security(_api_key_header)] = None,
) -> None:
    expected = settings.api.key.get_secret_value()
    # compare_digest вместо ==, чтобы время сравнения не зависело от ключа.
    if api_key is None or not secrets.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный или отсутствующий заголовок X-API-Key",
        )


def get_create_payment_use_case(session: SessionDep) -> CreatePaymentUseCase:
    return CreatePaymentUseCase(
        payments=SqlAlchemyPaymentRepository(session),
        outbox=SqlAlchemyOutboxRepository(session),
        uow=SqlAlchemyUnitOfWork(session),
    )


def get_get_payment_use_case(session: SessionDep) -> GetPaymentUseCase:
    return GetPaymentUseCase(payments=SqlAlchemyPaymentRepository(session))


CreatePaymentDep = Annotated[CreatePaymentUseCase, Depends(get_create_payment_use_case)]
GetPaymentDep = Annotated[GetPaymentUseCase, Depends(get_get_payment_use_case)]
