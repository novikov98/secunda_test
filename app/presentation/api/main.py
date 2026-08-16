import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.infrastructure.broker.broker import create_broker, declare_topology
from app.infrastructure.broker.outbox_relay import OutboxRelay
from app.infrastructure.broker.publisher import RabbitEventPublisher
from app.infrastructure.config import get_settings
from app.infrastructure.db.session import create_engine, create_session_factory
from app.infrastructure.logging import configure_logging
from app.presentation.api.exception_handlers import register_exception_handlers
from app.presentation.api.v1.payments import router as payments_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    engine = create_engine(settings.postgres)
    app.state.session_factory = create_session_factory(engine)

    broker = create_broker(settings.rabbitmq)
    await broker.connect()
    await declare_topology(broker)

    relay = OutboxRelay(app.state.session_factory, RabbitEventPublisher(broker), settings.outbox)
    relay_task = asyncio.create_task(relay.run(), name="outbox-relay")
    logger.info("Outbox relay запущен")

    try:
        yield
    finally:
        relay_task.cancel()
        with suppress(asyncio.CancelledError):
            await relay_task
        await broker.stop()
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title=settings.api.title, lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(payments_router)

    @app.get("/health", tags=["service"], summary="Проверка живости")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
