from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlparse

from app.domain.common.exceptions import DomainError

IDEMPOTENCY_KEY_MAX_LENGTH = 255

_ALLOWED_WEBHOOK_SCHEMES = frozenset({"http", "https"})


@dataclass(frozen=True)
class Amount:
    """Сумма платежа."""

    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise DomainError(
                f"Сумма платежа должна быть Decimal, передано {type(self.value).__name__}"
            )
        # NaN и Infinity надо отсечь до сравнений ниже.
        if not self.value.is_finite():
            raise DomainError(f"Сумма платежа должна быть конечным числом, передано {self.value}")
        if self.value < 0:
            raise DomainError(f"Сумма платежа не может быть меньше 0, передано {self.value}")
        if -self.value.as_tuple().exponent > 2:
            raise DomainError(
                "Сумма платежа не может быть точнее 2 знаков после запятой, "
                f"передано {-self.value.as_tuple().exponent}"
            )

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class IdempotencyKey:
    """Ключ идемпотентности."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise DomainError(
                f"Ключ идемпотентности должен быть строкой, передано {type(self.value).__name__}"
            )
        if not self.value.strip():
            raise DomainError("Ключ идемпотентности не может быть пустым")
        if len(self.value) > IDEMPOTENCY_KEY_MAX_LENGTH:
            raise DomainError(
                f"Ключ идемпотентности не может быть длиннее {IDEMPOTENCY_KEY_MAX_LENGTH} "
                f"символов, передано {len(self.value)}"
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class WebhookUrl:
    """Адрес, на который уходит уведомление о результате платежа."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise DomainError(
                f"Webhook URL должен быть строкой, передано {type(self.value).__name__}"
            )

        parsed = urlparse(self.value)
        if parsed.scheme not in _ALLOWED_WEBHOOK_SCHEMES:
            raise DomainError(
                "Webhook URL должен использовать схему http или https, передано "
                f"{parsed.scheme or 'без схемы'}"
            )
        if not parsed.netloc:
            raise DomainError(f"Webhook URL должен содержать хост, передано {self.value}")

    def __str__(self) -> str:
        return self.value
