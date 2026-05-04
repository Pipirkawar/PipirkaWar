"""Тесты `FakeIdempotencyKey`."""

from __future__ import annotations

import pytest

from tests.fakes import FakeIdempotencyKey


class TestFakeIdempotencyKey:
    def test_build_concatenates_namespace_and_parts(self) -> None:
        idem = FakeIdempotencyKey()
        key = idem.build("referral_signup", ["42", "100"])
        assert key == "referral_signup:42|100"

    def test_build_empty_namespace_raises(self) -> None:
        idem = FakeIdempotencyKey()
        with pytest.raises(ValueError, match="non-empty"):
            idem.build("", ["x"])

    async def test_is_seen_false_initially(self) -> None:
        idem = FakeIdempotencyKey()
        assert await idem.is_seen("referral_signup:1|2") is False

    async def test_mark_then_is_seen_true(self) -> None:
        idem = FakeIdempotencyKey()
        key = idem.build("referral_signup", ["1", "2"])
        await idem.mark(key, namespace="referral_signup")
        assert await idem.is_seen(key) is True

    async def test_mark_with_wrong_namespace_raises(self) -> None:
        idem = FakeIdempotencyKey()
        key = idem.build("referral_signup", ["1", "2"])
        with pytest.raises(ValueError, match="does not match namespace"):
            await idem.mark(key, namespace="daily_head")
