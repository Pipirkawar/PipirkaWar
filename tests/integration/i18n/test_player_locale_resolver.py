"""Integration-тесты `PlayerLocaleResolverDB` (Спринт 1.5.F).

Проверяем поверх SQLite (in-memory):

1. Игрок без override → `resolve_for_tg_id(...)` возвращает `None`.
2. Игрок с `users.locale_override = 'ru'` → возвращает `Locale("ru")`.
3. Игрок с `users.locale_override = 'en'` → возвращает `Locale("en")`.
4. Незнакомый `tg_id` (нет ряда) → `None`.
5. CHECK-constraint в БД отвергает мусор (`'fr'`).
6. Через репозиторий: `with_locale_override` + `save` сохраняет
   значение, последующий `get_by_tg_id` возвращает его. Это
   гарантирует, что repo+ORM правильно сериализуют новое поле.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from pipirik_wars.application.i18n import Locale
from pipirik_wars.domain.player import Player, Username
from pipirik_wars.infrastructure.db.models import UserORM
from pipirik_wars.infrastructure.db.repositories import SqlAlchemyPlayerRepository
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from pipirik_wars.infrastructure.i18n import PlayerLocaleResolverDB

NOW = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


async def _seed_user(
    uow: SqlAlchemyUnitOfWork,
    *,
    tg_id: int,
    locale_override: str | None,
) -> None:
    async with uow:
        await uow.session.execute(
            insert(UserORM).values(
                tg_id=tg_id,
                username="alice",
                length_cm=2,
                thickness_level=1,
                title=None,
                name=None,
                status="active",
                created_at=NOW,
                updated_at=NOW,
                locale_override=locale_override,
            ),
        )


@pytest.mark.asyncio
class TestPlayerLocaleResolverDB:
    async def test_resolve_returns_none_for_unknown_tg_id(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        resolver = PlayerLocaleResolverDB(uow=uow)
        assert await resolver.resolve_for_tg_id(999) is None

    async def test_resolve_returns_none_when_override_is_null(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        await _seed_user(uow, tg_id=42, locale_override=None)
        resolver = PlayerLocaleResolverDB(uow=uow)
        assert await resolver.resolve_for_tg_id(42) is None

    async def test_resolve_returns_ru_when_set(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        await _seed_user(uow, tg_id=42, locale_override="ru")
        resolver = PlayerLocaleResolverDB(uow=uow)
        assert await resolver.resolve_for_tg_id(42) == Locale("ru")

    async def test_resolve_returns_en_when_set(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        await _seed_user(uow, tg_id=42, locale_override="en")
        resolver = PlayerLocaleResolverDB(uow=uow)
        assert await resolver.resolve_for_tg_id(42) == Locale("en")

    async def test_check_constraint_rejects_unsupported_locale(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        with pytest.raises(IntegrityError):
            await _seed_user(uow, tg_id=42, locale_override="fr")


@pytest.mark.asyncio
class TestPlayerRepositoryLocaleOverridePersistence:
    """Roundtrip через `SqlAlchemyPlayerRepository` (Спринт 1.5.F)."""

    async def test_with_locale_override_persists_via_save(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                Player.new(tg_id=77, username=Username(value="bob"), now=NOW),
            )
            assert stored.locale_override is None
            updated = stored.with_locale_override(
                "ru",
                now=datetime(2026, 5, 5, 13, 0, tzinfo=UTC),
            )
            await repo.save(updated)

        async with uow:
            roundtrip = await repo.get_by_tg_id(77)
            assert roundtrip is not None
            assert roundtrip.locale_override == "ru"

    async def test_can_clear_override_via_save(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        repo = SqlAlchemyPlayerRepository(uow=uow)
        async with uow:
            stored = await repo.add(
                Player.new(tg_id=77, username=Username(value="bob"), now=NOW),
            )
            with_en = stored.with_locale_override(
                "en",
                now=datetime(2026, 5, 5, 13, 0, tzinfo=UTC),
            )
            await repo.save(with_en)
            cleared = with_en.with_locale_override(
                None,
                now=datetime(2026, 5, 5, 14, 0, tzinfo=UTC),
            )
            await repo.save(cleared)

        async with uow:
            roundtrip = await repo.get_by_tg_id(77)
            assert roundtrip is not None
            assert roundtrip.locale_override is None
