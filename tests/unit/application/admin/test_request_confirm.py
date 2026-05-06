"""Unit-тесты `RequestAdminConfirm` (Спринт 2.5-A.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.admin import (
    RequestAdminConfirm,
    RequestAdminConfirmInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditSource,
    AdminRole,
    TotpNotConfiguredError,
)
from pipirik_wars.infrastructure.admin.in_memory_confirm_store import (
    InMemoryAdminConfirmStore,
)
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.clock import FakeClock
from tests.fakes.uow import FakeUnitOfWork

_FIXED_NOW = datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)


def _build_use_case(
    *,
    token: str = "test-token-abc",
    ttl: timedelta = timedelta(seconds=60),
) -> tuple[
    RequestAdminConfirm,
    FakeAdminRepository,
    InMemoryAdminConfirmStore,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
    FakeClock,
]:
    admins = FakeAdminRepository()
    store = InMemoryAdminConfirmStore()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    clock = FakeClock(_FIXED_NOW)
    use_case = RequestAdminConfirm(
        uow=uow,
        admins=admins,
        store=store,
        audit=audit,
        clock=clock,
        token_factory=lambda: token,
        ttl=ttl,
    )
    return use_case, admins, store, audit, uow, clock


@pytest.mark.asyncio
class TestRequestAdminConfirm:
    async def test_unknown_admin_raises_authorization_error(self) -> None:
        use_case, _admins, store, audit, uow, _ = _build_use_case()

        with pytest.raises(AuthorizationError):
            await use_case.execute(
                RequestAdminConfirmInput(
                    actor_tg_id=999,
                    command_kind="ban",
                    target_kind="player",
                    target_id="42",
                ),
            )

        # Никаких побочных эффектов: store пуст, audit пуст, UoW не открыт.
        assert await store.pop(token="test-token-abc") is None
        assert audit.entries == []
        assert uow.commits == 0

    async def test_inactive_admin_raises_authorization_error(self) -> None:
        use_case, admins, _store, _audit, _uow, _ = _build_use_case()
        admins.seed(
            tg_id=42,
            role=AdminRole.SUPER_ADMIN,
            is_active=False,
            totp_secret="JBSWY3DPEHPK3PXP",
        )

        with pytest.raises(AuthorizationError):
            await use_case.execute(
                RequestAdminConfirmInput(
                    actor_tg_id=42,
                    command_kind="ban",
                    target_kind="player",
                    target_id="42",
                ),
            )

    async def test_admin_without_totp_raises_totp_not_configured(self) -> None:
        use_case, admins, _store, audit, uow, _ = _build_use_case()
        admins.seed(tg_id=42, role=AdminRole.SUPER_ADMIN, totp_secret=None)

        with pytest.raises(TotpNotConfiguredError):
            await use_case.execute(
                RequestAdminConfirmInput(
                    actor_tg_id=42,
                    command_kind="ban",
                    target_kind="player",
                    target_id="42",
                ),
            )

        assert audit.entries == []
        assert uow.commits == 0

    async def test_active_admin_with_totp_gets_token_and_audit(self) -> None:
        use_case, admins, store, audit, uow, _ = _build_use_case(
            token="urlsafe-deadbeef",
        )
        admin = admins.seed(
            tg_id=42,
            role=AdminRole.SUPER_ADMIN,
            totp_secret="JBSWY3DPEHPK3PXP",
        )

        result = await use_case.execute(
            RequestAdminConfirmInput(
                actor_tg_id=42,
                command_kind="ban",
                target_kind="player",
                target_id="100500",
                payload={"reason": "spam"},
                tg_chat_id=-100,
            ),
        )

        assert result.token == "urlsafe-deadbeef"
        assert result.ttl_seconds == 60

        # Запись лежит в store-е.
        entry = await store.pop(token="urlsafe-deadbeef")
        assert entry is not None
        assert entry.request.admin_id == admin.id
        assert entry.request.command_kind == "ban"
        assert entry.request.target_kind == "player"
        assert entry.request.target_id == "100500"
        assert entry.request.payload["reason"] == "spam"
        assert entry.expires_at == _FIXED_NOW + timedelta(seconds=60)

        # Audit-запись зафиксирована, UoW зафиксирован 1 раз.
        assert uow.commits == 1
        assert uow.rollbacks == 0
        assert len(audit.entries) == 1
        a = audit.entries[0]
        assert a.admin_id == admin.id
        assert a.action == AdminAuditAction.ADMIN_CONFIRM_REQUESTED
        assert a.target_kind == "player"
        assert a.target_id == "100500"
        assert a.source == AdminAuditSource.BOT
        assert a.tg_chat_id == -100
        assert a.idempotency_key == "urlsafe-deadbeef"
        assert a.occurred_at == _FIXED_NOW

    async def test_custom_ttl_propagates_to_expires_at(self) -> None:
        use_case, admins, store, _audit, _uow, _ = _build_use_case(
            ttl=timedelta(seconds=10),
        )
        admins.seed(
            tg_id=42,
            role=AdminRole.SUPER_ADMIN,
            totp_secret="JBSWY3DPEHPK3PXP",
        )

        await use_case.execute(
            RequestAdminConfirmInput(
                actor_tg_id=42,
                command_kind="ban",
                target_kind="player",
                target_id="42",
            ),
        )
        entry = await store.pop(token="test-token-abc")
        assert entry is not None
        assert entry.expires_at == _FIXED_NOW + timedelta(seconds=10)

    async def test_empty_payload_default_when_omitted(self) -> None:
        use_case, admins, store, _audit, _uow, _ = _build_use_case()
        admins.seed(
            tg_id=42,
            role=AdminRole.SUPER_ADMIN,
            totp_secret="JBSWY3DPEHPK3PXP",
        )

        await use_case.execute(
            RequestAdminConfirmInput(
                actor_tg_id=42,
                command_kind="ban",
                target_kind="player",
                target_id="42",
            ),
        )
        entry = await store.pop(token="test-token-abc")
        assert entry is not None
        assert dict(entry.request.payload) == {}
