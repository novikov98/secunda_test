from decimal import Decimal

import pytest

from app.domain.common.exceptions import DomainError
from app.domain.payment.values import (
    IDEMPOTENCY_KEY_MAX_LENGTH,
    Amount,
    IdempotencyKey,
    WebhookUrl,
)


class TestAmount:
    @pytest.mark.parametrize(
        "value",
        [Decimal("0"), Decimal("0.01"), Decimal("100"), Decimal("1000.50"), Decimal("1E+2")],
    )
    def test_accepts_valid_values(self, value: Decimal) -> None:
        assert Amount(value).value == value

    def test_rejects_non_decimal(self) -> None:
        with pytest.raises(DomainError, match="должна быть Decimal"):
            Amount(100.5)  # type: ignore[arg-type]

    @pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
    def test_rejects_non_finite(self, value: str) -> None:
        with pytest.raises(DomainError, match="конечным числом"):
            Amount(Decimal(value))

    def test_rejects_negative(self) -> None:
        with pytest.raises(DomainError, match="не может быть меньше 0"):
            Amount(Decimal("-0.01"))

    def test_rejects_more_than_two_decimal_places(self) -> None:
        with pytest.raises(DomainError, match="2 знаков после запятой"):
            Amount(Decimal("10.001"))

    def test_compares_by_value(self) -> None:
        assert Amount(Decimal("10.00")) == Amount(Decimal("10.00"))


class TestIdempotencyKey:
    def test_accepts_regular_key(self) -> None:
        assert str(IdempotencyKey("order-42")) == "order-42"

    @pytest.mark.parametrize("value", ["", "   "])
    def test_rejects_blank_key(self, value: str) -> None:
        with pytest.raises(DomainError, match="не может быть пустым"):
            IdempotencyKey(value)

    def test_rejects_too_long_key(self) -> None:
        with pytest.raises(DomainError, match="не может быть длиннее"):
            IdempotencyKey("x" * (IDEMPOTENCY_KEY_MAX_LENGTH + 1))

    def test_accepts_key_of_max_length(self) -> None:
        key = "x" * IDEMPOTENCY_KEY_MAX_LENGTH
        assert str(IdempotencyKey(key)) == key


class TestWebhookUrl:
    @pytest.mark.parametrize(
        "value",
        [
            "http://localhost:8000/hook",
            "https://example.com/webhooks/payments",
            "https://example.com",
        ],
    )
    def test_accepts_http_and_https(self, value: str) -> None:
        assert str(WebhookUrl(value)) == value

    @pytest.mark.parametrize("value", ["ftp://example.com", "example.com/hook", ""])
    def test_rejects_unsupported_scheme(self, value: str) -> None:
        with pytest.raises(DomainError, match="схему http или https"):
            WebhookUrl(value)

    def test_rejects_url_without_host(self) -> None:
        with pytest.raises(DomainError, match="должен содержать хост"):
            WebhookUrl("https:///path")
