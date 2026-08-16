"""Таблицы payments и outbox."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.payment.enums import Currency, PaymentStatus
from app.domain.payment.values import IDEMPOTENCY_KEY_MAX_LENGTH


def _enum_column(enum_type: type, name: str, length: int) -> Enum:
    """VARCHAR вместо нативного enum postgres."""
    return Enum(
        enum_type,
        name=name,
        native_enum=False,
        length=length,
        values_callable=lambda e: [member.value for member in e],
        validate_strings=True,
    )


def _enum_check(column: str, enum_type: type[StrEnum], name: str) -> CheckConstraint:
    """CHECK на допустимые значения колонки."""
    values = ", ".join(f"'{member.value}'" for member in enum_type)
    return CheckConstraint(f"{column} IN ({values})", name=name)


class Base(DeclarativeBase):
    # Единые имена констрейнтов и индексов.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class PaymentModel(Base):
    __tablename__ = "payments"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[Currency] = mapped_column(
        _enum_column(Currency, "currency", 3), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    # `metadata` занято DeclarativeBase, поэтому атрибут называется meta.
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )

    status: Mapped[PaymentStatus] = mapped_column(
        _enum_column(PaymentStatus, "payment_status", 16),
        nullable=False,
        server_default=PaymentStatus.PENDING.value,
        index=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(IDEMPOTENCY_KEY_MAX_LENGTH), nullable=False, unique=True
    )
    # Хеш тела запроса для проверки конфликта идемпотентности.
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    webhook_url: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        _enum_check("currency", Currency, "currency_allowed"),
        _enum_check("status", PaymentStatus, "status_allowed"),
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        CheckConstraint(
            "(status = 'pending') = (processed_at IS NULL)",
            name="processed_at_matches_status",
        ),
    )


class OutboxMessageModel(Base):
    """Событие, ожидающее публикации в брокер."""

    __tablename__ = "outbox"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)

    aggregate_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # Частичный индекс: relay читает только неопубликованные события.
        Index(
            "ix_outbox_unpublished",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )
