from dataclasses import dataclass, field
from typing import Any

import pytest

from app.infrastructure.broker.topology import DEAD_ROUTING_KEY, RETRY_ROUTING_KEY
from app.infrastructure.config import RabbitSettings
from app.presentation.consumer.retry import ATTEMPT_HEADER, ERROR_HEADER, RetryPolicy

PAYLOAD: dict[str, Any] = {"payment_id": "8f1d0d6c-0f4d-4a1e-9a5b-6c4f2b3d1e00"}


@dataclass
class FakeMessage:
    headers: dict[str, Any] = field(default_factory=dict)


@dataclass
class PublishedMessage:
    payload: dict[str, Any]
    routing_key: str
    headers: dict[str, Any]
    expiration: float | None


class FakeBroker:
    def __init__(self) -> None:
        self.published: list[PublishedMessage] = []

    async def publish(
        self,
        message: dict[str, Any],
        *,
        exchange: Any = None,
        routing_key: str = "",
        headers: dict[str, Any] | None = None,
        expiration: float | None = None,
        persist: bool = False,
    ) -> None:
        self.published.append(PublishedMessage(message, routing_key, headers or {}, expiration))


def make_policy(broker: FakeBroker, max_attempts: int = 3, base_delay: float = 2.0) -> RetryPolicy:
    settings = RabbitSettings(
        max_delivery_attempts=max_attempts, retry_base_delay_seconds=base_delay
    )
    return RetryPolicy(broker, settings)  # type: ignore[arg-type]


class TestAttemptOf:
    def test_defaults_to_first_attempt(self) -> None:
        assert make_policy(FakeBroker()).attempt_of(FakeMessage()) == 1

    def test_reads_header(self) -> None:
        message = FakeMessage({ATTEMPT_HEADER: 3})

        assert make_policy(FakeBroker()).attempt_of(message) == 3

    @pytest.mark.parametrize("value", ["не число", None, 0, -5])
    def test_falls_back_on_garbage(self, value: Any) -> None:
        message = FakeMessage({ATTEMPT_HEADER: value})

        assert make_policy(FakeBroker()).attempt_of(message) >= 1


class TestOnFailure:
    async def test_sends_to_retry_queue(self) -> None:
        broker = FakeBroker()

        await make_policy(broker).on_failure(PAYLOAD, attempt=1, error=RuntimeError("боль"))

        sent = broker.published[0]
        assert sent.routing_key == RETRY_ROUTING_KEY
        assert sent.payload == PAYLOAD

    async def test_increments_attempt_counter(self) -> None:
        broker = FakeBroker()

        await make_policy(broker).on_failure(PAYLOAD, attempt=1, error=RuntimeError("боль"))

        assert broker.published[0].headers[ATTEMPT_HEADER] == 2

    @pytest.mark.parametrize(("attempt", "expected_delay"), [(1, 2.0), (2, 4.0), (3, 8.0)])
    async def test_delay_grows_exponentially(self, attempt: int, expected_delay: float) -> None:
        broker = FakeBroker()
        policy = make_policy(broker, max_attempts=10, base_delay=2.0)

        await policy.on_failure(PAYLOAD, attempt=attempt, error=RuntimeError("боль"))

        assert broker.published[0].expiration == expected_delay

    async def test_records_error_in_header(self) -> None:
        broker = FakeBroker()

        await make_policy(broker).on_failure(PAYLOAD, attempt=1, error=ValueError("почему-то"))

        assert broker.published[0].headers[ERROR_HEADER] == "ValueError: почему-то"

    async def test_sends_to_dlq_on_last_attempt(self) -> None:
        broker = FakeBroker()

        await make_policy(broker, max_attempts=3).on_failure(
            PAYLOAD, attempt=3, error=RuntimeError("боль")
        )

        sent = broker.published[0]
        assert sent.routing_key == DEAD_ROUTING_KEY
        assert sent.headers[ATTEMPT_HEADER] == 3
        assert sent.expiration is None

    async def test_dlq_message_keeps_payload(self) -> None:
        broker = FakeBroker()

        await make_policy(broker, max_attempts=1).on_failure(
            PAYLOAD, attempt=1, error=RuntimeError("боль")
        )

        assert broker.published[0].payload == PAYLOAD
        assert broker.published[0].routing_key == DEAD_ROUTING_KEY
