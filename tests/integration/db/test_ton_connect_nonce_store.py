"""Integration-тесты ``SqlAlchemyNonceStore`` (Спринт 4.1-F, F.6.b).

Покрытие:

* ``issue_nonce`` создаёт строку (первый INSERT) с ``issued_at =
  clock.now()`` и ``consumed_at = None``.
* ``issue_nonce`` повторно с тем же ``nonce`` (PK-конфликт) → ``ValueError``.
* ``issue_nonce`` для разных ``nonce`` в одном ``scope`` работает (PK по
  ``nonce``, не по ``(scope, nonce)``).
* ``consume_nonce`` happy-path: первый вызов возвращает ``True`` и помечает
  строку ``consumed_at = now``.
* ``consume_nonce`` неизвестный nonce → ``False``.
* ``consume_nonce`` неправильный scope (правильный nonce) → ``False``.
* ``consume_nonce`` уже consumed → ``False`` (idempotency: второй ``True``
  не выдаётся).
* ``consume_nonce`` истёкший nonce → ``False`` (``expires_at <= now``).
* ``consume_nonce`` ``expires_at == now`` (граница) → ``False``.
* ``consume_nonce`` строгое равенство по ``scope``: попытка consume того
  же nonce под чужим scope-ом не помечает оригинальную строку (race-
  invariant: разные scope-ы изолированы).
* DB-CHECK ``LENGTH(nonce) > 0`` — пустой nonce отклоняется.
* DB-CHECK ``LENGTH(scope) > 0`` — пустой scope отклоняется.
* DB-CHECK ``expires_at > issued_at`` — обратный порядок отклоняется.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from pipirik_wars.infrastructure.db.models import TonConnectNonceORM
from pipirik_wars.infrastructure.db.repositories import SqlAlchemyNonceStore
from pipirik_wars.infrastructure.db.uow import SqlAlchemyUnitOfWork
from tests.fakes.clock import FakeClock

_NOW = datetime(2026, 5, 12, 12, 0, tzinfo=UTC)
_LATER = _NOW + timedelta(seconds=60)
_TTL = timedelta(seconds=600)
_SCOPE = "link_wallet:42:ton_nano"
_NONCE = "abc123_url_safe_nonce_value"


def _make_store(
    uow: SqlAlchemyUnitOfWork,
    clock_start: datetime = _NOW,
) -> tuple[SqlAlchemyNonceStore, FakeClock]:
    clock = FakeClock(clock_start)
    store = SqlAlchemyNonceStore(uow=uow, clock=clock)
    return store, clock


class TestIssueNonce:
    @pytest.mark.asyncio
    async def test_first_insert_records_row(self, uow: SqlAlchemyUnitOfWork) -> None:
        store, clock = _make_store(uow)
        async with uow:
            await store.issue_nonce(scope=_SCOPE, nonce=_NONCE, expires_at=_NOW + _TTL)
            await uow.commit()

        async with uow:
            result = await uow.session.execute(
                select(TonConnectNonceORM).where(TonConnectNonceORM.nonce == _NONCE)
            )
            orm = result.scalar_one()

        assert orm.nonce == _NONCE
        assert orm.scope == _SCOPE
        # SQLite не хранит TZ-инфу, поэтому сверяем naïve-проекцию.
        assert orm.issued_at.replace(tzinfo=UTC) == clock.now()
        assert orm.consumed_at is None
        assert orm.expires_at.replace(tzinfo=UTC) == _NOW + _TTL

    @pytest.mark.asyncio
    async def test_duplicate_nonce_raises_value_error(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        store, _ = _make_store(uow)
        async with uow:
            await store.issue_nonce(scope=_SCOPE, nonce=_NONCE, expires_at=_NOW + _TTL)
            await uow.commit()

        async with uow:
            with pytest.raises(ValueError, match="already issued"):
                await store.issue_nonce(
                    scope=_SCOPE,
                    nonce=_NONCE,
                    expires_at=_NOW + _TTL,
                )

    @pytest.mark.asyncio
    async def test_different_nonces_same_scope_ok(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """PK \u2014 ``nonce``, не ``(scope, nonce)``. Разные nonce ОК."""
        store, _ = _make_store(uow)
        async with uow:
            await store.issue_nonce(scope=_SCOPE, nonce="nonce_a", expires_at=_NOW + _TTL)
            await store.issue_nonce(scope=_SCOPE, nonce="nonce_b", expires_at=_NOW + _TTL)
            await uow.commit()

        async with uow:
            result = await uow.session.execute(
                select(TonConnectNonceORM).where(TonConnectNonceORM.scope == _SCOPE)
            )
            rows = list(result.scalars())
        assert {r.nonce for r in rows} == {"nonce_a", "nonce_b"}


class TestConsumeNonce:
    @pytest.mark.asyncio
    async def test_happy_path(self, uow: SqlAlchemyUnitOfWork) -> None:
        store, _ = _make_store(uow)
        async with uow:
            await store.issue_nonce(scope=_SCOPE, nonce=_NONCE, expires_at=_NOW + _TTL)
            await uow.commit()

        async with uow:
            ok = await store.consume_nonce(scope=_SCOPE, nonce=_NONCE, now=_LATER)
            await uow.commit()
        assert ok is True

        async with uow:
            result = await uow.session.execute(
                select(TonConnectNonceORM).where(TonConnectNonceORM.nonce == _NONCE)
            )
            orm = result.scalar_one()
        assert orm.consumed_at is not None
        assert orm.consumed_at.replace(tzinfo=UTC) == _LATER

    @pytest.mark.asyncio
    async def test_unknown_nonce_returns_false(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        store, _ = _make_store(uow)
        async with uow:
            ok = await store.consume_nonce(
                scope=_SCOPE,
                nonce="never_issued",
                now=_LATER,
            )
        assert ok is False

    @pytest.mark.asyncio
    async def test_wrong_scope_returns_false(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Тот же nonce под чужим scope-ом \u2014 ``False``; оригинальная строка не помечена."""
        store, _ = _make_store(uow)
        async with uow:
            await store.issue_nonce(scope=_SCOPE, nonce=_NONCE, expires_at=_NOW + _TTL)
            await uow.commit()

        async with uow:
            ok = await store.consume_nonce(
                scope="link_wallet:999:usdt_decimal",
                nonce=_NONCE,
                now=_LATER,
            )
            await uow.commit()
        assert ok is False

        async with uow:
            result = await uow.session.execute(
                select(TonConnectNonceORM).where(TonConnectNonceORM.nonce == _NONCE)
            )
            orm = result.scalar_one()
        # Оригинальная строка не помечена.
        assert orm.consumed_at is None

    @pytest.mark.asyncio
    async def test_second_consume_returns_false(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """CAS-семантика: второй consume того же nonce \u2014 ``False``."""
        store, _ = _make_store(uow)
        async with uow:
            await store.issue_nonce(scope=_SCOPE, nonce=_NONCE, expires_at=_NOW + _TTL)
            await uow.commit()

        async with uow:
            first = await store.consume_nonce(scope=_SCOPE, nonce=_NONCE, now=_LATER)
            await uow.commit()
        async with uow:
            second = await store.consume_nonce(
                scope=_SCOPE,
                nonce=_NONCE,
                now=_LATER + timedelta(seconds=1),
            )
            await uow.commit()

        assert first is True
        assert second is False

    @pytest.mark.asyncio
    async def test_expired_nonce_returns_false(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """``expires_at <= now`` \u2014 nonce expired, consume \u2014 ``False``."""
        store, _ = _make_store(uow)
        async with uow:
            await store.issue_nonce(
                scope=_SCOPE,
                nonce=_NONCE,
                expires_at=_NOW + timedelta(seconds=30),
            )
            await uow.commit()

        async with uow:
            ok = await store.consume_nonce(
                scope=_SCOPE,
                nonce=_NONCE,
                now=_NOW + timedelta(seconds=60),  # > expires_at
            )
        assert ok is False

    @pytest.mark.asyncio
    async def test_expires_at_equals_now_boundary_returns_false(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """Граница ``expires_at == now`` строго ``False`` (контракт: ``expires_at > now``)."""
        store, _ = _make_store(uow)
        async with uow:
            await store.issue_nonce(
                scope=_SCOPE,
                nonce=_NONCE,
                expires_at=_NOW + timedelta(seconds=30),
            )
            await uow.commit()

        async with uow:
            ok = await store.consume_nonce(
                scope=_SCOPE,
                nonce=_NONCE,
                now=_NOW + timedelta(seconds=30),  # == expires_at
            )
        assert ok is False


class TestDbConstraints:
    @pytest.mark.asyncio
    async def test_empty_nonce_rejected(self, uow: SqlAlchemyUnitOfWork) -> None:
        """DB-CHECK ``ck_ton_connect_nonces_nonce_non_empty``."""
        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(TonConnectNonceORM).values(
                        nonce="",
                        scope=_SCOPE,
                        issued_at=_NOW,
                        consumed_at=None,
                        expires_at=_NOW + _TTL,
                    )
                )

    @pytest.mark.asyncio
    async def test_empty_scope_rejected(self, uow: SqlAlchemyUnitOfWork) -> None:
        """DB-CHECK ``ck_ton_connect_nonces_scope_non_empty``."""
        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(TonConnectNonceORM).values(
                        nonce=_NONCE,
                        scope="",
                        issued_at=_NOW,
                        consumed_at=None,
                        expires_at=_NOW + _TTL,
                    )
                )

    @pytest.mark.asyncio
    async def test_expires_before_issued_rejected(
        self,
        uow: SqlAlchemyUnitOfWork,
    ) -> None:
        """DB-CHECK ``ck_ton_connect_nonces_expires_after_issued``."""
        async with uow:
            with pytest.raises(IntegrityError):
                await uow.session.execute(
                    insert(TonConnectNonceORM).values(
                        nonce=_NONCE,
                        scope=_SCOPE,
                        issued_at=_NOW,
                        consumed_at=None,
                        expires_at=_NOW - timedelta(seconds=1),
                    )
                )
