from enum import StrEnum


class Currency(StrEnum):
    """Валюты, которые принимает сервис."""

    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class PaymentStatus(StrEnum):
    """Жизненный цикл платежа"""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def is_final(self) -> bool:
        return self is not PaymentStatus.PENDING
