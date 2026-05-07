"""Unit-тесты `LiftAnticheatBan` (Спринт 1.6.G; ГДД §3.3).

Покрытие:

- happy-path: super_admin снимает активный бан → запись `ANTICHEAT_BAN_LIFTED`.
- идемпотентный no-op: бан уже снят (None или истёк) → нет audit + нет save.
- authz: support / economist / read_only → `AuthorizationError`, нет state-change.
- authz: неактивный super_admin → `AuthorizationError`.
- authz: незнакомый actor (не админ) → `AuthorizationError`.
- player не найден → `PlayerNotFoundError`.
- пустая `reason` → `ValueError` (защита от безответственных unban-ов).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.anticheat import LiftAnticheatBan
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuthorizationDeniedError,
    AdminRole,
    RoleBasedAdminAuthorizationPolicy,
)
from pipirik_wars.domain.player import Player, PlayerStatus
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.player.value_objects import Length, Thickness, Username
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeAdminAuditLogger,
    FakeAdminRepository,
    FakeAuditLogger,
    FakeClock,
    FakePlayerRepository,
    FakeUnitOfWork,
)

_NOW = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
_FUTURE = _NOW + timedelta(days=14)


def _make_player(
    *,
    player_id: int = 1,
    tg_id: int = 10001,
    anticheat_ban_until: datetime | None = None,
) -> Player:
    return Player(
        id=player_id,
        tg_id=tg_id,
        username=Username(value="bob"),
        length=Length(cm=100),
        thickness=Thickness(level=1),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW - timedelta(days=30),
        updated_at=_NOW - timedelta(days=30),
        anticheat_ban_until=anticheat_ban_until,
    )


def _build_use_case(
    *,
    actor_role: AdminRole = AdminRole.SUPER_ADMIN,
    actor_active: bool = True,
    target_player: Player | None = None,
    actor_tg_id: int = 555,
) -> tuple[
    LiftAnticheatBan,
    FakePlayerRepository,
    FakeAuditLogger,
    FakeAdminRepository,
    FakeAdminAuditLogger,
]:
    uow = FakeUnitOfWork()
    clock = FakeClock(_NOW)
    admins = FakeAdminRepository()
    admins.seed(tg_id=actor_tg_id, role=actor_role, is_active=actor_active)
    players = FakePlayerRepository()
    if target_player is not None:
        players.rows.append(target_player)
    audit = FakeAuditLogger()
    admin_audit = FakeAdminAuditLogger()
    use_case = LiftAnticheatBan(
        uow=uow,
        admins=admins,
        players=players,
        audit=audit,
        admin_audit=admin_audit,
        authz=RoleBasedAdminAuthorizationPolicy(),
        clock=clock,
    )
    return use_case, players, audit, admins, admin_audit


# ───────────────────────────── happy path ─────────────────────────────


@pytest.mark.asyncio
async def test_super_admin_lifts_active_ban() -> None:
    target = _make_player(anticheat_ban_until=_FUTURE)
    use_case, players, audit, admins, _ = _build_use_case(target_player=target)

    result = await use_case.execute(
        actor_tg_id=555,
        target_tg_id=target.tg_id,
        reason="manual review: legitimate donate burst",
    )

    assert result.was_banned is True
    assert result.banned_until_before == _FUTURE
    assert result.target_tg_id == target.tg_id
    assert result.reason == "manual review: legitimate donate burst"
    saved = await players.get_by_tg_id(target.tg_id)
    assert saved is not None
    assert saved.anticheat_ban_until is None
    assert len(audit.entries) == 1
    entry = audit.entries[0]
    assert entry.action is AuditAction.ANTICHEAT_BAN_LIFTED
    assert entry.target_kind == "player"
    assert entry.target_id == str(target.id)
    assert entry.actor_id == admins.rows[0].id
    assert entry.before == {"anticheat_ban_until": _FUTURE.isoformat()}
    assert entry.after == {"anticheat_ban_until": None}
    assert entry.reason == "manual review: legitimate donate burst"
    assert entry.idempotency_key == f"anticheat_unban:555:{target.tg_id}:{int(_NOW.timestamp())}"


# ──────────────────────────── idempotent ─────────────────────────────


@pytest.mark.asyncio
async def test_no_active_ban_is_idempotent_noop() -> None:
    target = _make_player(anticheat_ban_until=None)
    use_case, players, audit, _, _ = _build_use_case(target_player=target)

    result = await use_case.execute(
        actor_tg_id=555,
        target_tg_id=target.tg_id,
        reason="precaution",
    )

    assert result.was_banned is False
    assert result.banned_until_before is None
    saved = await players.get_by_tg_id(target.tg_id)
    assert saved is not None
    assert saved is target  # тот же инстанс — save не звался
    assert audit.entries == []


@pytest.mark.asyncio
async def test_expired_ban_is_idempotent_noop() -> None:
    expired = _NOW - timedelta(seconds=1)
    target = _make_player(anticheat_ban_until=expired)
    use_case, _, audit, _, _ = _build_use_case(target_player=target)

    result = await use_case.execute(
        actor_tg_id=555,
        target_tg_id=target.tg_id,
        reason="cleanup expired ban entry",
    )

    assert result.was_banned is False
    assert result.banned_until_before == expired
    assert audit.entries == []


# ───────────────────────────── authz ─────────────────────────────────


@pytest.mark.parametrize(
    "role",
    [AdminRole.SUPPORT, AdminRole.ECONOMIST, AdminRole.READ_ONLY],
)
@pytest.mark.asyncio
async def test_non_super_admin_is_forbidden(role: AdminRole) -> None:
    # Спринт 2.5-D.7: RBAC-отказ фиксируется в admin_audit.
    target = _make_player(anticheat_ban_until=_FUTURE)
    use_case, players, audit, _, admin_audit = _build_use_case(
        actor_role=role,
        target_player=target,
    )

    with pytest.raises(AdminAuthorizationDeniedError):
        await use_case.execute(
            actor_tg_id=555,
            target_tg_id=target.tg_id,
            reason="x",
        )

    # Бан не снят, audit пуст — но admin_audit имеет отпечаток попытки.
    saved = await players.get_by_tg_id(target.tg_id)
    assert saved is not None
    assert saved.anticheat_ban_until == _FUTURE
    assert audit.entries == []
    assert len(admin_audit.entries) == 1


@pytest.mark.asyncio
async def test_inactive_super_admin_is_forbidden() -> None:
    # Inactive-admin отбивается defense-in-depth-проверкой до RBAC —
    # admin_audit пуст (это приватное событие admin-management).
    target = _make_player(anticheat_ban_until=_FUTURE)
    use_case, players, audit, _, admin_audit = _build_use_case(
        actor_active=False,
        target_player=target,
    )

    with pytest.raises(AuthorizationError):
        await use_case.execute(
            actor_tg_id=555,
            target_tg_id=target.tg_id,
            reason="reason",
        )
    saved = await players.get_by_tg_id(target.tg_id)
    assert saved is not None
    assert saved.anticheat_ban_until == _FUTURE
    assert audit.entries == []
    assert admin_audit.entries == []


@pytest.mark.asyncio
async def test_unknown_actor_is_forbidden() -> None:
    target = _make_player(anticheat_ban_until=_FUTURE)
    use_case, _, audit, _, _ = _build_use_case(target_player=target)

    with pytest.raises(AuthorizationError):
        await use_case.execute(
            actor_tg_id=999,  # не зарегистрирован как админ
            target_tg_id=target.tg_id,
            reason="reason",
        )
    assert audit.entries == []


# ──────────────────────── target not found ────────────────────────────


@pytest.mark.asyncio
async def test_player_not_found_raises() -> None:
    use_case, _, audit, _, _ = _build_use_case(target_player=None)

    with pytest.raises(PlayerNotFoundError):
        await use_case.execute(
            actor_tg_id=555,
            target_tg_id=42424242,
            reason="some reason",
        )
    assert audit.entries == []


# ─────────────────────────── reason guard ────────────────────────────


@pytest.mark.parametrize("bad_reason", ["", "   ", "\t\n"])
@pytest.mark.asyncio
async def test_empty_reason_raises_value_error(bad_reason: str) -> None:
    target = _make_player(anticheat_ban_until=_FUTURE)
    use_case, _, audit, _, _ = _build_use_case(target_player=target)

    with pytest.raises(ValueError, match="reason must be non-empty"):
        await use_case.execute(
            actor_tg_id=555,
            target_tg_id=target.tg_id,
            reason=bad_reason,
        )
    assert audit.entries == []


@pytest.mark.asyncio
async def test_reason_is_trimmed_in_audit() -> None:
    target = _make_player(anticheat_ban_until=_FUTURE)
    use_case, _, audit, _, _ = _build_use_case(target_player=target)

    result = await use_case.execute(
        actor_tg_id=555,
        target_tg_id=target.tg_id,
        reason="   manual unban   ",
    )

    assert result.reason == "manual unban"
    assert audit.entries[0].reason == "manual unban"
