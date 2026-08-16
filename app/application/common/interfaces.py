from typing import Protocol

from app.application.common.outbox import OutboxMessage


class UnitOfWork(Protocol):
    """Границы транзакции."""

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class OutboxRepository(Protocol):
    async def add(self, message: OutboxMessage) -> None: ...
