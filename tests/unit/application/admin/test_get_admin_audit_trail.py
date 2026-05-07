"""Unit-тесты `GetAdminAuditTrail` (Спринт 2.5-D.5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.admin import (
    DEFAULT_AUDIT_LIMIT,
    MAX_AUDIT_LIMIT,
    AdminAuditActionUnknownError,
    GetAdminAuditTrail,
    GetAdminAuditTrailInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    Admin,
    AdminAuditAction,
    AdminAuditRecord,
    AdminAuditSource,
    AdminRole,
)
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_audit_query import FakeAdminAuditQuery
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.clock import FakeClock
from tests.fakes.uow import FakeUnitOfWork

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _build() -> tuple[
    GetAdminAuditTrail,
    FakeAdminRepository,
    FakeAdminAuditQuery,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    query = FakeAdminAuditQuery()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    use_case = GetAdminAuditTrail(
        uow=uow,
        admins=admins,
        query=query,
        audit=audit,
        clock=FakeClock(_NOW),
        authz=FakeAdminAuthzAllowAll(),
    )
    return use_case, admins, query, audit, uow


def _seed_admin(
    admins: FakeAdminRepository,
    *,
    tg_id: int,
    is_active: bool = True,
    role: AdminRole = AdminRole.SUPPORT,
) -> Admin:
    new_id = (max((a.id or 0 for a in admins.rows), default=0)) + 1
    admin = Admin(
        id=new_id,
        tg_id=tg_id,
        role=role,
        is_active=is_active,
        created_at=_NOW,
    )
    admins.rows.append(admin)
    return admin


def _seed_record(
    query: FakeAdminAuditQuery,
    *,
    actor_admin_id: int,
    actor_tg_id: int,
    action: AdminAuditAction,
    occurred_at: datetime,
    target_kind: str = "player",
    target_id: str = "0",
) -> AdminAuditRecord:
    new_id = (max((r.id for r in query.records), default=0)) + 1
    rec = AdminAuditRecord(
        id=new_id,
        actor_admin_id=actor_admin_id,
        actor_tg_id=actor_tg_id,
        action=action,
        target_kind=target_kind,
        target_id=target_id,
        before=None,
        after=None,
        reason="test",
        idempotency_key=None,
        source=AdminAuditSource.BOT,
        tg_chat_id=None,
        ip=None,
        occurred_at=occurred_at,
    )
    query.records.append(rec)
    return rec


@pytest.mark.asyncio
class TestGetAdminAuditTrail:
    async def test_unknown_actor_raises_authorization(self) -> None:
        use_case, _admins, _q, audit, uow = _build()
        with pytest.raises(AuthorizationError):
            await use_case.execute(GetAdminAuditTrailInput(actor_tg_id=999))
        assert uow.commits == 0
        assert audit.entries == []

    async def test_inactive_actor_raises_authorization(self) -> None:
        use_case, admins, _q, audit, uow = _build()
        _seed_admin(admins, tg_id=42, is_active=False)
        with pytest.raises(AuthorizationError):
            await use_case.execute(GetAdminAuditTrailInput(actor_tg_id=42))
        assert uow.commits == 0
        assert audit.entries == []

    async def test_returns_records_sorted_desc_and_audits_read(self) -> None:
        use_case, admins, query, audit, uow = _build()
        actor = _seed_admin(admins, tg_id=10, role=AdminRole.SUPER_ADMIN)
        target = _seed_admin(admins, tg_id=20, role=AdminRole.SUPPORT)
        assert actor.id is not None and target.id is not None
        _seed_record(
            query,
            actor_admin_id=target.id,
            actor_tg_id=20,
            action=AdminAuditAction.ADMIN_PLAYER_FROZEN,
            occurred_at=datetime(2026, 5, 8, 11, 0, tzinfo=UTC),
        )
        _seed_record(
            query,
            actor_admin_id=target.id,
            actor_tg_id=20,
            action=AdminAuditAction.ADMIN_PLAYER_BANNED,
            occurred_at=datetime(2026, 5, 8, 11, 30, tzinfo=UTC),
        )

        out = await use_case.execute(GetAdminAuditTrailInput(actor_tg_id=10))

        assert len(out.records) == 2
        assert out.records[0].action is AdminAuditAction.ADMIN_PLAYER_BANNED
        assert out.records[1].action is AdminAuditAction.ADMIN_PLAYER_FROZEN
        assert out.target_admin_resolved is True  # target=None всегда «resolved»
        assert out.target_admin_tg_id is None
        assert out.action is None
        assert out.limit == DEFAULT_AUDIT_LIMIT
        # И сам факт чтения должен быть записан.
        assert len(audit.entries) == 1
        assert audit.entries[0].action is AdminAuditAction.ADMIN_AUDIT_QUERIED
        assert audit.entries[0].admin_id == actor.id
        assert audit.entries[0].target_kind == "admin_audit_log"
        assert audit.entries[0].target_id == "all"
        assert audit.entries[0].after == {
            "filter_action": None,
            "limit": DEFAULT_AUDIT_LIMIT,
            "results_count": 2,
            "target_resolved": True,
        }

    async def test_filters_by_target_admin_tg_id(self) -> None:
        use_case, admins, query, _audit, _uow = _build()
        _seed_admin(admins, tg_id=10, role=AdminRole.SUPER_ADMIN)
        a = _seed_admin(admins, tg_id=20)
        b = _seed_admin(admins, tg_id=21)
        assert a.id is not None and b.id is not None
        _seed_record(
            query,
            actor_admin_id=a.id,
            actor_tg_id=20,
            action=AdminAuditAction.ADMIN_PLAYER_FROZEN,
            occurred_at=datetime(2026, 5, 8, 11, 0, tzinfo=UTC),
        )
        _seed_record(
            query,
            actor_admin_id=b.id,
            actor_tg_id=21,
            action=AdminAuditAction.ADMIN_PLAYER_FROZEN,
            occurred_at=datetime(2026, 5, 8, 11, 30, tzinfo=UTC),
        )
        out = await use_case.execute(
            GetAdminAuditTrailInput(actor_tg_id=10, target_admin_tg_id=20),
        )
        assert len(out.records) == 1
        assert out.records[0].actor_tg_id == 20
        assert out.target_admin_resolved is True

    async def test_target_admin_not_found_returns_empty_and_marks_resolved_false(
        self,
    ) -> None:
        use_case, admins, _q, audit, _uow = _build()
        _seed_admin(admins, tg_id=10, role=AdminRole.SUPER_ADMIN)
        out = await use_case.execute(
            GetAdminAuditTrailInput(actor_tg_id=10, target_admin_tg_id=9999),
        )
        assert out.records == ()
        assert out.target_admin_resolved is False
        assert audit.entries[0].after == {
            "filter_action": None,
            "limit": DEFAULT_AUDIT_LIMIT,
            "results_count": 0,
            "target_resolved": False,
        }

    async def test_filter_by_action_value(self) -> None:
        use_case, admins, query, _audit, _uow = _build()
        actor = _seed_admin(admins, tg_id=10, role=AdminRole.SUPER_ADMIN)
        assert actor.id is not None
        _seed_record(
            query,
            actor_admin_id=actor.id,
            actor_tg_id=10,
            action=AdminAuditAction.ADMIN_PLAYER_FROZEN,
            occurred_at=datetime(2026, 5, 8, 11, 0, tzinfo=UTC),
        )
        _seed_record(
            query,
            actor_admin_id=actor.id,
            actor_tg_id=10,
            action=AdminAuditAction.ADMIN_PLAYER_BANNED,
            occurred_at=datetime(2026, 5, 8, 11, 30, tzinfo=UTC),
        )
        out = await use_case.execute(
            GetAdminAuditTrailInput(
                actor_tg_id=10,
                action_value=AdminAuditAction.ADMIN_PLAYER_BANNED.value,
            ),
        )
        assert len(out.records) == 1
        assert out.records[0].action is AdminAuditAction.ADMIN_PLAYER_BANNED
        assert out.action is AdminAuditAction.ADMIN_PLAYER_BANNED

    async def test_unknown_action_raises(self) -> None:
        use_case, admins, _q, _audit, _uow = _build()
        _seed_admin(admins, tg_id=10, role=AdminRole.SUPER_ADMIN)
        with pytest.raises(AdminAuditActionUnknownError) as ctx:
            await use_case.execute(
                GetAdminAuditTrailInput(actor_tg_id=10, action_value="bogus_action"),
            )
        assert ctx.value.value == "bogus_action"

    async def test_limit_clamped_to_max(self) -> None:
        use_case, admins, query, _audit, _uow = _build()
        actor = _seed_admin(admins, tg_id=10, role=AdminRole.SUPER_ADMIN)
        assert actor.id is not None
        for i in range(MAX_AUDIT_LIMIT + 10):
            _seed_record(
                query,
                actor_admin_id=actor.id,
                actor_tg_id=10,
                action=AdminAuditAction.ADMIN_PLAYER_FROZEN,
                occurred_at=datetime(2026, 5, 8, 11, 0, 0, tzinfo=UTC) + _delta(i),
            )
        out = await use_case.execute(
            GetAdminAuditTrailInput(actor_tg_id=10, limit=10_000),
        )
        assert out.limit == MAX_AUDIT_LIMIT
        assert len(out.records) == MAX_AUDIT_LIMIT

    async def test_non_positive_limit_falls_back_to_default(self) -> None:
        use_case, admins, _q, _audit, _uow = _build()
        _seed_admin(admins, tg_id=10, role=AdminRole.SUPER_ADMIN)
        out = await use_case.execute(GetAdminAuditTrailInput(actor_tg_id=10, limit=0))
        assert out.limit == DEFAULT_AUDIT_LIMIT

    async def test_empty_records_returns_empty_sequence(self) -> None:
        use_case, admins, _q, audit, _uow = _build()
        _seed_admin(admins, tg_id=10, role=AdminRole.SUPER_ADMIN)
        out = await use_case.execute(GetAdminAuditTrailInput(actor_tg_id=10))
        assert out.records == ()
        # Read-аудит всё равно пишется.
        assert len(audit.entries) == 1


def _delta(i: int) -> timedelta:
    return timedelta(seconds=i)
