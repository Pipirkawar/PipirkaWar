"""Тесты `FakeNonceStore` — in-memory `INonceStore` (Спринт 4.1-F, шаг F.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.fakes import FakeNonceStore


@pytest.fixture(name="now")
def fixture_now() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class TestFakeNonceStoreIssue:
    async def test_issue_records_call(self, now: datetime) -> None:
        store = FakeNonceStore()
        await store.issue_nonce(
            scope="link_wallet:42:ton_nano",
            nonce="abc123",
            expires_at=now + timedelta(minutes=5),
        )
        assert len(store.issue_calls) == 1
        assert store.issue_calls[0]["scope"] == "link_wallet:42:ton_nano"
        assert store.issue_calls[0]["nonce"] == "abc123"
        assert store.is_known(scope="link_wallet:42:ton_nano", nonce="abc123")
        assert not store.is_consumed(scope="link_wallet:42:ton_nano", nonce="abc123")

    async def test_double_issue_same_scope_nonce_raises(self, now: datetime) -> None:
        store = FakeNonceStore()
        await store.issue_nonce(
            scope="s",
            nonce="n",
            expires_at=now + timedelta(minutes=5),
        )
        with pytest.raises(ValueError, match="already issued"):
            await store.issue_nonce(
                scope="s",
                nonce="n",
                expires_at=now + timedelta(minutes=10),
            )

    async def test_same_nonce_different_scope_ok(self, now: datetime) -> None:
        store = FakeNonceStore()
        await store.issue_nonce(
            scope="link_wallet:42:ton_nano",
            nonce="shared-nonce",
            expires_at=now + timedelta(minutes=5),
        )
        await store.issue_nonce(
            scope="link_wallet:42:usdt_decimal",
            nonce="shared-nonce",
            expires_at=now + timedelta(minutes=5),
        )
        assert store.is_known(scope="link_wallet:42:ton_nano", nonce="shared-nonce")
        assert store.is_known(scope="link_wallet:42:usdt_decimal", nonce="shared-nonce")


class TestFakeNonceStoreConsume:
    async def test_consume_unknown_returns_false(self, now: datetime) -> None:
        store = FakeNonceStore()
        ok = await store.consume_nonce(scope="s", nonce="n", now=now)
        assert ok is False
        assert len(store.consume_calls) == 1

    async def test_consume_known_unconsumed_unexpired_returns_true(
        self,
        now: datetime,
    ) -> None:
        store = FakeNonceStore()
        await store.issue_nonce(
            scope="s",
            nonce="n",
            expires_at=now + timedelta(minutes=5),
        )
        ok = await store.consume_nonce(scope="s", nonce="n", now=now)
        assert ok is True
        assert store.is_consumed(scope="s", nonce="n")

    async def test_second_consume_returns_false_cas_semantics(
        self,
        now: datetime,
    ) -> None:
        store = FakeNonceStore()
        await store.issue_nonce(
            scope="s",
            nonce="n",
            expires_at=now + timedelta(minutes=5),
        )
        first = await store.consume_nonce(scope="s", nonce="n", now=now)
        second = await store.consume_nonce(scope="s", nonce="n", now=now)
        assert first is True
        assert second is False
        assert store.is_consumed(scope="s", nonce="n")

    async def test_consume_expired_returns_false(self, now: datetime) -> None:
        store = FakeNonceStore()
        await store.issue_nonce(
            scope="s",
            nonce="n",
            expires_at=now - timedelta(seconds=1),
        )
        ok = await store.consume_nonce(scope="s", nonce="n", now=now)
        assert ok is False
        # consumed-flag не выставляется на expired (Чтобы не было
        # «consumed_at»-loga в production-репо).
        assert not store.is_consumed(scope="s", nonce="n")

    async def test_consume_exactly_at_expiry_returns_false(
        self,
        now: datetime,
    ) -> None:
        # ``expires_at <= now`` → expired (граничная политика — F.6.b
        # SQL-репо использует strict-less или not-less; здесь та же
        # семантика «<=»).
        store = FakeNonceStore()
        await store.issue_nonce(scope="s", nonce="n", expires_at=now)
        ok = await store.consume_nonce(scope="s", nonce="n", now=now)
        assert ok is False

    async def test_consume_wrong_scope_returns_false(self, now: datetime) -> None:
        store = FakeNonceStore()
        await store.issue_nonce(
            scope="link_wallet:42:ton_nano",
            nonce="n",
            expires_at=now + timedelta(minutes=5),
        )
        ok = await store.consume_nonce(
            scope="link_wallet:99:ton_nano",
            nonce="n",
            now=now,
        )
        assert ok is False
        assert not store.is_consumed(
            scope="link_wallet:42:ton_nano",
            nonce="n",
        )


class TestFakeNonceStoreSatisfiesINonceStore:
    """Дополнительная проверка: ``FakeNonceStore`` runtime-совместим с ``INonceStore``-Protocol."""

    def test_protocol_methods_present(self) -> None:
        store = FakeNonceStore()
        # Protocol — duck-typing, проверяем наличие методов с правильным
        # async-контрактом.
        assert callable(store.issue_nonce)
        assert callable(store.consume_nonce)
