"""Тесты `FakeUnitOfWork`."""

from __future__ import annotations

import pytest

from tests.fakes import FakeUnitOfWork


class TestFakeUnitOfWork:
    async def test_commit_on_normal_exit(self) -> None:
        uow = FakeUnitOfWork()
        async with uow:
            pass
        assert uow.commits == 1
        assert uow.rollbacks == 0

    async def test_rollback_on_exception(self) -> None:
        uow = FakeUnitOfWork()
        with pytest.raises(RuntimeError, match="boom"):
            async with uow:
                raise RuntimeError("boom")
        assert uow.commits == 0
        assert uow.rollbacks == 1

    async def test_explicit_commit_counts(self) -> None:
        uow = FakeUnitOfWork()
        async with uow:
            await uow.commit()
        # один из __aexit__, один явный → 2.
        assert uow.commits == 2

    async def test_nested_context_is_rejected(self) -> None:
        uow = FakeUnitOfWork()
        async with uow:
            with pytest.raises(RuntimeError, match="nested"):
                async with uow:
                    pass

    async def test_explicit_rollback_counts(self) -> None:
        uow = FakeUnitOfWork()
        await uow.rollback()
        assert uow.rollbacks == 1
