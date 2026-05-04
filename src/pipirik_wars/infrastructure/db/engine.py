"""Фабрика async engine + sessionmaker."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pipirik_wars.infrastructure.settings import DatabaseSettings


def build_engine(settings: DatabaseSettings) -> AsyncEngine:
    """Собрать async engine из настроек.

    Pool-конфигурация применяется только к Postgres; SQLite её
    игнорирует (что и нужно для тестов).
    """
    url = settings.url.get_secret_value()
    is_sqlite = url.startswith("sqlite")
    kwargs: dict[str, object] = {"echo": settings.echo}
    if not is_sqlite:
        kwargs["pool_size"] = settings.pool_size
        kwargs["max_overflow"] = settings.max_overflow
    return create_async_engine(url, **kwargs)


def build_sessionmaker(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Sessionmaker без autoflush — UoW сам управляет flush/commit."""
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        class_=AsyncSession,
    )
