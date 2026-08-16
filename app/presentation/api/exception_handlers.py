from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.application.common.exceptions import (
    IdempotencyConflictError,
    PaymentNotFoundError,
)
from app.domain.common.exceptions import DomainError


def _json(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


async def _not_found(_: Request, exc: PaymentNotFoundError) -> JSONResponse:
    return _json(status.HTTP_404_NOT_FOUND, str(exc))


async def _conflict(_: Request, exc: IdempotencyConflictError) -> JSONResponse:
    return _json(status.HTTP_409_CONFLICT, str(exc))


async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
    return _json(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PaymentNotFoundError, _not_found)  # type: ignore[arg-type]
    app.add_exception_handler(IdempotencyConflictError, _conflict)  # type: ignore[arg-type]
    app.add_exception_handler(DomainError, _domain_error)  # type: ignore[arg-type]
