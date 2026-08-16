from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status

from app.application.payment.dto import CreatePaymentCommand
from app.presentation.api.dependencies import (
    CreatePaymentDep,
    GetPaymentDep,
    require_api_key,
)
from app.presentation.api.v1.schemas import (
    CreatePaymentRequest,
    ErrorResponse,
    PaymentAcceptedResponse,
    PaymentResponse,
)

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["payments"],
    dependencies=[Depends(require_api_key)],
    responses={
        401: {"model": ErrorResponse, "description": "Неверный API-ключ"},
    },
)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PaymentAcceptedResponse,
    responses={409: {"model": ErrorResponse, "description": "Конфликт ключа идемпотентности"}},
    summary="Создать платёж",
)
async def create_payment(
    body: CreatePaymentRequest,
    create: CreatePaymentDep,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", max_length=255)],
) -> PaymentAcceptedResponse:
    result = await create(
        CreatePaymentCommand(
            amount=body.amount,
            currency=body.currency,
            description=body.description,
            metadata=body.metadata,
            webhook_url=str(body.webhook_url),
            idempotency_key=idempotency_key,
            request_hash=body.request_hash(),
        )
    )
    return PaymentAcceptedResponse.from_domain(result.payment)


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    responses={404: {"model": ErrorResponse, "description": "Платёж не найден"}},
    summary="Получить платёж",
)
async def get_payment(payment_id: UUID, get: GetPaymentDep) -> PaymentResponse:
    return PaymentResponse.from_domain(await get(payment_id))
