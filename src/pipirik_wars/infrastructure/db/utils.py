"""Хелперы инфраструктурного слоя БД."""

from __future__ import annotations

from datetime import UTC, datetime


def ensure_utc(value: datetime) -> datetime:
    """Нормализует datetime до timezone-aware (UTC).

    Postgres (asyncpg) отдаёт datetime с tzinfo, но SQLite (aiosqlite)
    возвращает naive-datetime даже для колонок `DateTime(timezone=True)`.
    Все доменные сущности проекта работают с UTC-aware datetimes; чтобы
    тесты на SQLite вели себя так же, как production на Postgres, при
    маппинге ORM → domain мы досыпаем UTC, если tzinfo отсутствует.

    Если значение уже tz-aware (Postgres), возвращаем как есть.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
