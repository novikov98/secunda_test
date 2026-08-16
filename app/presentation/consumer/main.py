import logging
from typing import Any
from uuid import UUID

import httpx
from faststream import FastStream
from faststream.rabbit import RabbitBroker
from faststream.rabbit.annotations import RabbitMessage

from app.application.payment.use_cases.process_payment import ProcessPaymentUseCase
from app.infrastructure.broker.broker import create_broker, declare_topology
from app.infrastructure.broker.topology import new_queue, payments_exchange
from app.infrastructure.config import Settings, get_settings
from app.infrastructure.db.repositories.payment import SqlAlchemyPaymentRepository
from app.infrastructure.db.session import create_engine, create_session_factory
from app.infrastructure.db.uow import SqlAlchemyUnitOfWork
from app.infrastructure.gateway.fake import FakePaymentGateway
from app.infrastructure.logging import configure_logging
from app.infrastructure.webhook.sender import HttpxWebhookSender
from app.presentation.consumer.retry import RetryPolicy

logger = logging.getLogger(__name__)


def create_consumer_app(settings: Settings | None = None) -> FastStream:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    broker: RabbitBroker = create_broker(settings.rabbitmq)
    app = FastStream(broker)

    engine = create_engine(settings.postgres)
    session_factory = create_session_factory(engine)
    gateway = FakePaymentGateway(settings.gateway)
    client = httpx.AsyncClient()
    webhooks = HttpxWebhookSender(client, settings.webhook)

    retry_policy = RetryPolicy(broker, settings.rabbitmq)

    @broker.subscriber(new_queue, payments_exchange)
    async def handle_payment_created(payload: dict[str, Any], message: RabbitMessage) -> None:
        payment_id = UUID(payload["payment_id"])
        attempt = retry_policy.attempt_of(message)
        logger.info(f"Событие о платеже {payment_id}, попытка {attempt}")

        try:
            async with session_factory() as session:
                use_case = ProcessPaymentUseCase(
                    payments=SqlAlchemyPaymentRepository(session),
                    uow=SqlAlchemyUnitOfWork(session),
                    gateway=gateway,
                    webhooks=webhooks,
                )
                await use_case(payment_id)
        except Exception as exc:
            # Исходное сообщение подтверждаем: повтор уходит отдельным
            # сообщением с увеличенным счётчиком попыток.
            await retry_policy.on_failure(payload, attempt, exc)

    @app.after_startup
    async def declare() -> None:
        await declare_topology(broker)

    @app.after_shutdown
    async def cleanup() -> None:
        await client.aclose()
        await engine.dispose()

    return app


app = create_consumer_app()
