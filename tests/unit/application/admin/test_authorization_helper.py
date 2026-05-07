"""Unit-тесты `ensure_admin_authorized` helper-а (Спринт 2.5-D.8 + D.11).

D.11 — выровненная coverage: для каждой роли из `AdminRole`
проверяется, что при отказе helper пишет audit-запись с правильным
`actor_role` и `command_kind`. Это страхует regression-ы вида
«helper всегда пишет actor_role=read_only, что бы ни передали».
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
from pipirik_wars.domain.admin import (
    Admin,
    AdminAuditAction,
    AdminAuditSource,
    AdminAuthorizationDeniedError,
    AdminCommandKind,
    AdminRole,
)
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll, FakeAdminAuthzDenyAll
from tests.fakes.uow import FakeUnitOfWork

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _admin(role: AdminRole = AdminRole.SUPPORT) -> Admin:
    return Admin(
        id=42,
        tg_id=1001,
        role=role,
        is_active=True,
        created_at=_NOW,
        created_by_admin_id=None,
        note=None,
        totp_secret=None,
    )


@pytest.mark.asyncio
class TestEnsureAdminAuthorized:
    async def test_allow_does_not_record_audit(self) -> None:
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        await ensure_admin_authorized(
            admin=_admin(),
            command_kind=AdminCommandKind.FIND_PLAYER,
            policy=FakeAdminAuthzAllowAll(),
            audit=audit,
            uow=uow,
            target_kind="player",
            target_id="12345",
            tg_chat_id=999,
            occurred_at=_NOW,
        )
        assert audit.entries == []
        assert uow.commits == 0

    async def test_deny_records_audit_and_raises(self) -> None:
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        with pytest.raises(AdminAuthorizationDeniedError) as exc_info:
            await ensure_admin_authorized(
                admin=_admin(role=AdminRole.READ_ONLY),
                command_kind=AdminCommandKind.BAN_PLAYER,
                policy=FakeAdminAuthzDenyAll(),
                audit=audit,
                uow=uow,
                target_kind="player",
                target_id="12345",
                tg_chat_id=999,
                occurred_at=_NOW,
            )
        assert exc_info.value.command_kind is AdminCommandKind.BAN_PLAYER
        assert exc_info.value.actor_role is AdminRole.READ_ONLY

        # Audit-запись персистится в отдельной транзакции (uow.commits == 1).
        assert uow.commits == 1
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AdminAuditAction.ADMIN_AUTHORIZATION_DENIED
        assert entry.source is AdminAuditSource.BOT
        assert entry.target_kind == "player"
        assert entry.target_id == "12345"
        assert entry.tg_chat_id == 999
        assert entry.occurred_at == _NOW
        assert entry.before is None
        assert entry.after == {
            "command_kind": "ban_player",
            "actor_role": "read_only",
        }
        assert "ban_player" in (entry.reason or "")
        assert "read_only" in (entry.reason or "")

    async def test_deny_includes_reason_suffix(self) -> None:
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        with pytest.raises(AdminAuthorizationDeniedError):
            await ensure_admin_authorized(
                admin=_admin(role=AdminRole.READ_ONLY),
                command_kind=AdminCommandKind.REQUEST_ADMIN_CONFIRM,
                policy=FakeAdminAuthzDenyAll(),
                audit=audit,
                uow=uow,
                target_kind="player",
                target_id="12345",
                tg_chat_id=None,
                occurred_at=_NOW,
                reason_suffix="ban_player",
            )
        assert "ban_player" in (audit.entries[0].reason or "")

    @pytest.mark.parametrize(
        ("role", "command"),
        [
            (AdminRole.READ_ONLY, AdminCommandKind.BAN_PLAYER),
            (AdminRole.READ_ONLY, AdminCommandKind.REQUEST_ADMIN_CONFIRM),
            (AdminRole.READ_ONLY, AdminCommandKind.SET_BALANCE_VALUE),
            (AdminRole.SUPPORT, AdminCommandKind.GRANT_LENGTH),
            (AdminRole.SUPPORT, AdminCommandKind.SET_BALANCE_VALUE),
            (AdminRole.SUPPORT, AdminCommandKind.SETUP_TOTP),
            (AdminRole.SUPPORT, AdminCommandKind.LIFT_ANTICHEAT_BAN),
            (AdminRole.ECONOMIST, AdminCommandKind.BAN_PLAYER),
            (AdminRole.ECONOMIST, AdminCommandKind.FREEZE_CLAN),
            (AdminRole.ECONOMIST, AdminCommandKind.LIFT_ANTICHEAT_BAN),
            (AdminRole.ECONOMIST, AdminCommandKind.BROADCAST_ANNOUNCEMENT),
        ],
        ids=lambda v: v.value if hasattr(v, "value") else str(v),
    )
    async def test_deny_audit_entry_carries_correct_actor_role_and_command(
        self,
        *,
        role: AdminRole,
        command: AdminCommandKind,
    ) -> None:
        """Helper не «затирает» actor_role/command_kind константой.

        Любая комбинация (роль × запрещённая команда) → audit-запись
        c `after = {"command_kind": <это>, "actor_role": <это>}`,
        `reason` содержит и роль, и команду, исключение несёт ту же
        пару. Параметризовано по разным ролям и командам, чтобы
        regression вида «helper пишет actor_role=read_only независимо
        от admin.role» падал немедленно.
        """
        audit = FakeAdminAuditLogger()
        uow = FakeUnitOfWork()
        with pytest.raises(AdminAuthorizationDeniedError) as exc_info:
            await ensure_admin_authorized(
                admin=_admin(role=role),
                command_kind=command,
                policy=FakeAdminAuthzDenyAll(),
                audit=audit,
                uow=uow,
                target_kind="player",
                target_id="12345",
                tg_chat_id=999,
                occurred_at=_NOW,
            )
        assert exc_info.value.command_kind is command
        assert exc_info.value.actor_role is role
        assert uow.commits == 1
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AdminAuditAction.ADMIN_AUTHORIZATION_DENIED
        assert entry.after == {
            "command_kind": command.value,
            "actor_role": role.value,
        }
        assert command.value in (entry.reason or "")
        assert role.value in (entry.reason or "")
