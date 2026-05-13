"""Unit tests for GetWebAuditLog use-case (Sprint 4.5-F)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin.get_web_audit_log import (
    PAGE_SIZE,
    AuditLogFilters,
    GetWebAuditLog,
)
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditRecord,
    AdminAuditSource,
    IAdminAuditWebQuery,
)
from pipirik_wars.domain.shared.ports.audit import AuditRecord, IAuditLogQuery


class FakeAuditLogQuery(IAuditLogQuery):
    """In-memory fake for testing."""

    def __init__(self, records: Sequence[AuditRecord] | None = None, total: int = 0) -> None:
        self._records = records or ()
        self._total = total
        self.last_kwargs: dict[str, object] = {}

    async def list_records(
        self,
        *,
        limit: int,
        offset: int = 0,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        actor_id: int | None = None,
        action: str | None = None,
        source: str | None = None,
    ) -> Sequence[AuditRecord]:
        self.last_kwargs = {
            "limit": limit,
            "offset": offset,
            "date_from": date_from,
            "date_to": date_to,
            "actor_id": actor_id,
            "action": action,
            "source": source,
        }
        return self._records

    async def count(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        actor_id: int | None = None,
        action: str | None = None,
        source: str | None = None,
    ) -> int:
        return self._total


class FakeAdminAuditWebQuery(IAdminAuditWebQuery):
    """In-memory fake for testing."""

    def __init__(
        self,
        records: Sequence[AdminAuditRecord] | None = None,
        total: int = 0,
    ) -> None:
        self._records = records or ()
        self._total = total
        self.last_kwargs: dict[str, object] = {}

    async def list_records(
        self,
        *,
        limit: int,
        offset: int = 0,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        admin_id: int | None = None,
        action: str | None = None,
        source: str | None = None,
    ) -> Sequence[AdminAuditRecord]:
        self.last_kwargs = {
            "limit": limit,
            "offset": offset,
            "date_from": date_from,
            "date_to": date_to,
            "admin_id": admin_id,
            "action": action,
            "source": source,
        }
        return self._records

    async def count(
        self,
        *,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        admin_id: int | None = None,
        action: str | None = None,
        source: str | None = None,
    ) -> int:
        return self._total


def _make_audit_record(record_id: int = 1) -> AuditRecord:
    return AuditRecord(
        id=record_id,
        occurred_at=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
        action="length_grant",
        actor_id=42,
        target_kind="player",
        target_id="42",
        reason="test",
        source="forest",
    )


def _make_admin_audit_record(record_id: int = 1) -> AdminAuditRecord:
    return AdminAuditRecord(
        id=record_id,
        actor_admin_id=1,
        actor_tg_id=123456,
        action=AdminAuditAction.ADMIN_PLAYER_LOOKUP,
        target_kind="player",
        target_id="42",
        before=None,
        after=None,
        reason="test lookup",
        idempotency_key=None,
        source=AdminAuditSource.BOT,
        tg_chat_id=999,
        ip=None,
        occurred_at=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio()
async def test_execute_returns_both_logs() -> None:
    audit_q = FakeAuditLogQuery([_make_audit_record()], total=1)
    admin_q = FakeAdminAuditWebQuery([_make_admin_audit_record()], total=1)
    uc = GetWebAuditLog(audit_query=audit_q, admin_audit_query=admin_q)

    result = await uc.execute(AuditLogFilters())
    assert len(result.audit_records) == 1
    assert len(result.admin_audit_records) == 1
    assert result.total_audit == 1
    assert result.total_admin_audit == 1


@pytest.mark.asyncio()
async def test_log_type_bot_excludes_admin() -> None:
    audit_q = FakeAuditLogQuery([_make_audit_record()], total=1)
    admin_q = FakeAdminAuditWebQuery([_make_admin_audit_record()], total=1)
    uc = GetWebAuditLog(audit_query=audit_q, admin_audit_query=admin_q)

    result = await uc.execute(AuditLogFilters(log_type="bot"))
    assert len(result.audit_records) == 1
    assert len(result.admin_audit_records) == 0
    assert result.total_admin_audit == 0


@pytest.mark.asyncio()
async def test_log_type_admin_excludes_bot() -> None:
    audit_q = FakeAuditLogQuery([_make_audit_record()], total=1)
    admin_q = FakeAdminAuditWebQuery([_make_admin_audit_record()], total=1)
    uc = GetWebAuditLog(audit_query=audit_q, admin_audit_query=admin_q)

    result = await uc.execute(AuditLogFilters(log_type="admin"))
    assert len(result.audit_records) == 0
    assert len(result.admin_audit_records) == 1
    assert result.total_audit == 0


@pytest.mark.asyncio()
async def test_pagination_offset() -> None:
    audit_q = FakeAuditLogQuery(total=0)
    admin_q = FakeAdminAuditWebQuery(total=0)
    uc = GetWebAuditLog(audit_query=audit_q, admin_audit_query=admin_q)

    await uc.execute(AuditLogFilters(page=3))
    assert audit_q.last_kwargs["offset"] == (3 - 1) * PAGE_SIZE
    assert audit_q.last_kwargs["limit"] == PAGE_SIZE


@pytest.mark.asyncio()
async def test_negative_page_clamped_to_1() -> None:
    audit_q = FakeAuditLogQuery(total=0)
    admin_q = FakeAdminAuditWebQuery(total=0)
    uc = GetWebAuditLog(audit_query=audit_q, admin_audit_query=admin_q)

    await uc.execute(AuditLogFilters(page=-5))
    assert audit_q.last_kwargs["offset"] == 0


@pytest.mark.asyncio()
async def test_actor_id_parsed_as_int() -> None:
    audit_q = FakeAuditLogQuery(total=0)
    admin_q = FakeAdminAuditWebQuery(total=0)
    uc = GetWebAuditLog(audit_query=audit_q, admin_audit_query=admin_q)

    await uc.execute(AuditLogFilters(actor_id="42"))
    assert audit_q.last_kwargs["actor_id"] == 42


@pytest.mark.asyncio()
async def test_invalid_actor_id_treated_as_none() -> None:
    audit_q = FakeAuditLogQuery(total=0)
    admin_q = FakeAdminAuditWebQuery(total=0)
    uc = GetWebAuditLog(audit_query=audit_q, admin_audit_query=admin_q)

    await uc.execute(AuditLogFilters(actor_id="not_a_number"))
    assert audit_q.last_kwargs["actor_id"] is None


@pytest.mark.asyncio()
async def test_empty_result() -> None:
    audit_q = FakeAuditLogQuery(total=0)
    admin_q = FakeAdminAuditWebQuery(total=0)
    uc = GetWebAuditLog(audit_query=audit_q, admin_audit_query=admin_q)

    result = await uc.execute(AuditLogFilters())
    assert result.total_audit == 0
    assert result.total_admin_audit == 0
    assert len(result.audit_records) == 0
    assert len(result.admin_audit_records) == 0


@pytest.mark.asyncio()
async def test_filters_passed_through() -> None:
    audit_q = FakeAuditLogQuery(total=0)
    admin_q = FakeAdminAuditWebQuery(total=0)
    uc = GetWebAuditLog(audit_query=audit_q, admin_audit_query=admin_q)

    dt = datetime(2026, 1, 1, tzinfo=UTC)
    await uc.execute(
        AuditLogFilters(
            date_from=dt,
            action="length_grant",
            source="bot",
        )
    )
    assert audit_q.last_kwargs["date_from"] == dt
    assert audit_q.last_kwargs["action"] == "length_grant"
    assert audit_q.last_kwargs["source"] == "bot"


@pytest.mark.asyncio()
async def test_page_size_in_result() -> None:
    audit_q = FakeAuditLogQuery(total=0)
    admin_q = FakeAdminAuditWebQuery(total=0)
    uc = GetWebAuditLog(audit_query=audit_q, admin_audit_query=admin_q)

    result = await uc.execute(AuditLogFilters())
    assert result.page_size == PAGE_SIZE
