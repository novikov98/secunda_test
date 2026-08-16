class ApplicationError(Exception):
    """Ошибка прикладного слоя."""


class PaymentNotFoundError(ApplicationError):
    """Платёж не найден."""


class IdempotencyConflictError(ApplicationError):
    """Ключ идемпотентности уже использован с другим телом запроса."""
