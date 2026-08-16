import logging

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def configure_logging(level: str) -> None:
    """Включить логи приложения поверх настроек uvicorn и FastStream."""
    # basicConfig ничего не сделает, если обработчик у корня уже есть —
    # uvicorn и FastStream настраивают логирование до старта приложения.
    logging.basicConfig(level=logging.WARNING, format=LOG_FORMAT)
    # Уровень задаём своему логгеру: у корня он остаётся WARNING, но записи
    # доходят до его обработчиков, потому что при всплытии уровень предков
    # не проверяется.
    logging.getLogger("app").setLevel(level.upper())
