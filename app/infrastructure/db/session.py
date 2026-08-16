from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.infrastructure.config import PostgresSettings


def create_engine(settings: PostgresSettings) -> AsyncEngine:
    return create_async_engine(
        settings.dsn,
        echo=settings.echo,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        # Объекты остаются доступны после commit.
        expire_on_commit=False,
        autoflush=False,
    )
