from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env(prefix: str) -> SettingsConfigDict:
    return SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix=prefix,
        extra="ignore",
    )


class PostgresSettings(BaseSettings):
    model_config = _env("POSTGRES_")

    host: str = "localhost"
    port: int = 5432
    user: str = "payments"
    password: SecretStr = SecretStr("payments")
    db: str = "payments"

    pool_size: int = 10
    max_overflow: int = 5
    echo: bool = False

    @property
    def dsn(self) -> str:
        """DSN для асинхронного драйвера asyncpg."""
        password = quote_plus(self.password.get_secret_value())
        user = quote_plus(self.user)
        return f"postgresql+asyncpg://{user}:{password}@{self.host}:{self.port}/{self.db}"


class RabbitSettings(BaseSettings):
    model_config = _env("RABBITMQ_")

    host: str = "localhost"
    port: int = 5672
    user: str = "guest"
    password: SecretStr = SecretStr("guest")
    vhost: str = "/"

    max_delivery_attempts: int = 3
    # растёт экспоненциально.
    retry_base_delay_seconds: float = 5.0

    @property
    def dsn(self) -> str:
        password = quote_plus(self.password.get_secret_value())
        user = quote_plus(self.user)
        vhost = quote_plus(self.vhost, safe="")
        return f"amqp://{user}:{password}@{self.host}:{self.port}/{vhost}"


class OutboxSettings(BaseSettings):
    model_config = _env("OUTBOX_")

    #: Сколько событий забирать за один проход.
    batch_size: int = 100
    #: Пауза между проходами.
    poll_interval_seconds: float = 1.0


class WebhookSettings(BaseSettings):
    model_config = _env("WEBHOOK_")

    timeout_seconds: float = 10.0
    #: Всего попыток доставки уведомления (первая + повторные).
    max_attempts: int = 3
    #: Задержки между попытками: base, base*2, base*4, ...
    retry_base_delay_seconds: float = 1.0


class GatewaySettings(BaseSettings):
    """Параметры эмуляции внешнего платёжного шлюза."""

    model_config = _env("GATEWAY_")

    min_delay_seconds: float = 2.0
    max_delay_seconds: float = 5.0
    success_rate: float = Field(default=0.9, ge=0.0, le=1.0)


class ApiSettings(BaseSettings):
    model_config = _env("API_")

    title: str = "Payments processing service"
    host: str = "0.0.0.0"
    port: int = 8000
    key: SecretStr = SecretStr("change-me")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    log_level: str = "INFO"

    api: ApiSettings = Field(default_factory=ApiSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    rabbitmq: RabbitSettings = Field(default_factory=RabbitSettings)
    outbox: OutboxSettings = Field(default_factory=OutboxSettings)
    webhook: WebhookSettings = Field(default_factory=WebhookSettings)
    gateway: GatewaySettings = Field(default_factory=GatewaySettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
