from dataclasses import dataclass
from decimal import Decimal

from app.domain.common.exceptions import DomainError


@dataclass(frozen=True)
class Amount:
    """Сумма платежа."""

    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            raise DomainError(
                f"Сумма платежа должна быть Decimal, передано {type(self.value).__name__}"
            )
        if self.value < 0:
            raise DomainError(
                f"Сумма платежа не может быть меньше 0б передано {self.value}"
            )
        if -self.value.as_tuple().exponent > 2:
            raise DomainError(
                f"Сумма платежа не может быть точнее 2 знаков после запятой, передано {-self.value.as_tuple().exponent}"
            )
