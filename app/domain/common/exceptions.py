class DomainError(Exception):
    """Нарушено доменное правило."""


class InvalidStatusTransitionError(DomainError):
    """Попытка перевести сущность в статус, недопустимый из текущего."""
