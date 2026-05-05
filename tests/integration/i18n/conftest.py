"""Делаем фикстуры из `tests/integration/db/conftest.py` доступными
здесь — `PlayerLocaleResolverDB` тестируется на той же in-memory
SQLite через `SqlAlchemyUnitOfWork`. Дублировать фикстуры не нужно.
"""

from __future__ import annotations

from tests.integration.db.conftest import (  # noqa: F401  re-export для pytest
    engine,
    session_maker,
    uow,
)
