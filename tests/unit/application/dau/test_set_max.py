"""Юнит-тесты `SetMaxDau` (Спринт 1.2.6)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.dau import SetMaxDau, SetMaxDauResult
from pipirik_wars.domain.admin import Admin, AdminRole
from pipirik_wars.domain.shared.ports import AuditAction
from pipirik_wars.infrastructure.dau import InMemoryDauLimit
from tests.fakes import FakeAdminRepository, FakeAuditLogger, FakeClock, FakeUnitOfWork


def _build_use_case(
    *,
    admins: FakeAdminRepository,
    audit: FakeAuditLogger,
    initial_max_dau: int = 200,
) -> tuple[SetMaxDau, InMemoryDauLimit, FakeClock, FakeUnitOfWork]:
    uow = FakeUnitOfWork()
    clock = FakeClock(datetime(2026, 5, 4, 12, 0, tzinfo=UTC))
    limit = InMemoryDauLimit(initial=initial_max_dau)
    use_case = SetMaxDau(
        uow=uow,
        admins=admins,
        limit=limit,
        audit=audit,
        clock=clock,
    )
    return use_case, limit, clock, uow


def _seed_admin(
    admins: FakeAdminRepository,
    *,
    tg_id: int,
    role: AdminRole,
    is_active: bool = True,
) -> Admin:
    return admins.seed(
        tg_id=tg_id,
        role=role,
        is_active=is_active,
        admin_id=tg_id * 10,
    )


class TestAuthorization:
    @pytest.mark.asyncio
    async def test_super_admin_can_set_max_dau(self) -> None:
        admins = FakeAdminRepository()
        _seed_admin(admins, tg_id=123, role=AdminRole.SUPER_ADMIN)
        audit = FakeAuditLogger()

        use_case, limit, _clock, _uow = _build_use_case(admins=admins, audit=audit)
        result = await use_case.execute(actor_tg_id=123, new_max_dau=1000)

        assert isinstance(result, SetMaxDauResult)
        assert result.previous_max_dau == 200
        assert result.new_max_dau == 1000
        assert result.changed is True
        assert await limit.get() == 1000

    @pytest.mark.asyncio
    async def test_economist_cannot_set_max_dau(self) -> None:
        # Экономист правит баланс, но не runtime-конфиг.
        admins = FakeAdminRepository()
        _seed_admin(admins, tg_id=456, role=AdminRole.ECONOMIST)
        audit = FakeAuditLogger()

        use_case, limit, _clock, _uow = _build_use_case(admins=admins, audit=audit)
        with pytest.raises(AuthorizationError) as exc:
            await use_case.execute(actor_tg_id=456, new_max_dau=1000)
        assert exc.value.requirement == "admin_runtime_config"
        assert await limit.get() == 200  # лимит не изменился

    @pytest.mark.asyncio
    async def test_support_cannot_set_max_dau(self) -> None:
        admins = FakeAdminRepository()
        _seed_admin(admins, tg_id=789, role=AdminRole.SUPPORT)
        audit = FakeAuditLogger()

        use_case, limit, _clock, _uow = _build_use_case(admins=admins, audit=audit)
        with pytest.raises(AuthorizationError):
            await use_case.execute(actor_tg_id=789, new_max_dau=1000)
        assert await limit.get() == 200

    @pytest.mark.asyncio
    async def test_read_only_cannot_set_max_dau(self) -> None:
        admins = FakeAdminRepository()
        _seed_admin(admins, tg_id=101, role=AdminRole.READ_ONLY)
        audit = FakeAuditLogger()

        use_case, limit, _clock, _uow = _build_use_case(admins=admins, audit=audit)
        with pytest.raises(AuthorizationError):
            await use_case.execute(actor_tg_id=101, new_max_dau=1000)
        assert await limit.get() == 200

    @pytest.mark.asyncio
    async def test_unknown_actor_cannot_set_max_dau(self) -> None:
        admins = FakeAdminRepository()  # пусто
        audit = FakeAuditLogger()

        use_case, limit, _clock, _uow = _build_use_case(admins=admins, audit=audit)
        with pytest.raises(AuthorizationError):
            await use_case.execute(actor_tg_id=999, new_max_dau=1000)
        assert await limit.get() == 200

    @pytest.mark.asyncio
    async def test_deactivated_super_admin_cannot_set_max_dau(self) -> None:
        admins = FakeAdminRepository()
        _seed_admin(admins, tg_id=123, role=AdminRole.SUPER_ADMIN, is_active=False)
        audit = FakeAuditLogger()

        use_case, limit, _clock, _uow = _build_use_case(admins=admins, audit=audit)
        with pytest.raises(AuthorizationError):
            await use_case.execute(actor_tg_id=123, new_max_dau=1000)
        assert await limit.get() == 200


class TestValidation:
    @pytest.mark.asyncio
    async def test_zero_max_dau_rejected_with_value_error(self) -> None:
        admins = FakeAdminRepository()
        _seed_admin(admins, tg_id=123, role=AdminRole.SUPER_ADMIN)
        audit = FakeAuditLogger()

        use_case, limit, _clock, _uow = _build_use_case(admins=admins, audit=audit)
        with pytest.raises(ValueError, match="new_max_dau must be >= 1"):
            await use_case.execute(actor_tg_id=123, new_max_dau=0)
        assert await limit.get() == 200

    @pytest.mark.asyncio
    async def test_negative_max_dau_rejected(self) -> None:
        admins = FakeAdminRepository()
        _seed_admin(admins, tg_id=123, role=AdminRole.SUPER_ADMIN)
        audit = FakeAuditLogger()

        use_case, limit, _clock, _uow = _build_use_case(admins=admins, audit=audit)
        with pytest.raises(ValueError, match="new_max_dau must be >= 1"):
            await use_case.execute(actor_tg_id=123, new_max_dau=-100)
        assert await limit.get() == 200


class TestAudit:
    @pytest.mark.asyncio
    async def test_successful_change_writes_audit_with_versions(self) -> None:
        admins = FakeAdminRepository()
        _seed_admin(admins, tg_id=123, role=AdminRole.SUPER_ADMIN)
        audit = FakeAuditLogger()

        use_case, _limit, clock, _uow = _build_use_case(
            admins=admins,
            audit=audit,
            initial_max_dau=200,
        )
        await use_case.execute(actor_tg_id=123, new_max_dau=1000)

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action == AuditAction.DAU_LIMIT_CHANGE
        assert entry.actor_id == 1230  # 123 * 10 (см. _seed_admin)
        assert entry.target_kind == "dau_limit"
        assert entry.target_id == "MAX_DAU"
        assert entry.before == {"max_dau": 200}
        assert entry.after == {"max_dau": 1000}
        assert entry.reason == "admin_set_max_dau"
        assert entry.idempotency_key is not None
        assert entry.idempotency_key.startswith("set_max_dau:123:")
        assert entry.occurred_at == clock.now()

    @pytest.mark.asyncio
    async def test_no_change_still_writes_audit(self) -> None:
        # Если admin зовёт `/set_max_dau N`, где N == текущему значению,
        # это всё равно явное действие — пишем в аудит для трейсинга.
        admins = FakeAdminRepository()
        _seed_admin(admins, tg_id=123, role=AdminRole.SUPER_ADMIN)
        audit = FakeAuditLogger()

        use_case, _limit, _clock, _uow = _build_use_case(
            admins=admins,
            audit=audit,
            initial_max_dau=200,
        )
        result = await use_case.execute(actor_tg_id=123, new_max_dau=200)

        assert result.changed is False
        assert result.previous_max_dau == 200
        assert result.new_max_dau == 200
        assert len(audit.entries) == 1
        assert audit.entries[0].before == {"max_dau": 200}
        assert audit.entries[0].after == {"max_dau": 200}

    @pytest.mark.asyncio
    async def test_unauthorized_does_not_write_audit(self) -> None:
        admins = FakeAdminRepository()
        _seed_admin(admins, tg_id=456, role=AdminRole.SUPPORT)
        audit = FakeAuditLogger()

        use_case, _limit, _clock, _uow = _build_use_case(admins=admins, audit=audit)
        with pytest.raises(AuthorizationError):
            await use_case.execute(actor_tg_id=456, new_max_dau=1000)
        assert audit.entries == []

    @pytest.mark.asyncio
    async def test_validation_error_does_not_write_audit(self) -> None:
        admins = FakeAdminRepository()
        _seed_admin(admins, tg_id=123, role=AdminRole.SUPER_ADMIN)
        audit = FakeAuditLogger()

        use_case, _limit, _clock, _uow = _build_use_case(admins=admins, audit=audit)
        with pytest.raises(ValueError):
            await use_case.execute(actor_tg_id=123, new_max_dau=0)
        assert audit.entries == []
