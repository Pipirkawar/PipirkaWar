"""Unit-тесты `GrantThickness` (Спринт 2.5-C.2).

`/grant_thickness <tg_id> <new_level> <reason>` — установка
абсолютного уровня толщины. Идёт прямой мутацией
`Player.with_thickness(...)` без `ILengthGranter`. Проверяем:

- авторизация (inactive / unknown admin → `AuthorizationError`);
- валидация (level < 1 / level > max(unlock_levels) → `ThicknessLevelInvalidError`);
- target not found / banned (PlayerNotFoundError / GrantThicknessBlockedError);
- happy-path (mutate + audit + idempotency.mark);
- domain-уровневая идемпотентность (level == previous → no-op, audit пуст);
- IIdempotencyKey-уровневый replay (повторный вызов → no-op).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin import (
    GrantThickness,
    GrantThicknessBlockedError,
    GrantThicknessInput,
    ThicknessLevelInvalidError,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import AdminAuditAction, AdminAuditSource, AdminRole
from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.player import Player, PlayerStatus, Thickness, Username
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.balance import FakeBalanceConfig
from tests.fakes.clock import FakeClock
from tests.fakes.idempotency import FakeIdempotencyKey
from tests.fakes.player_repo import FakePlayerRepository
from tests.fakes.uow import FakeUnitOfWork
from tests.unit.domain.balance.factories import valid_balance_payload

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _balance() -> BalanceConfig:
    """Дефолтный баланс из factories: max thickness = 3 (mountains)."""
    return BalanceConfig.model_validate(valid_balance_payload())


def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    thickness_level: int = 1,
    status: PlayerStatus = PlayerStatus.ACTIVE,
) -> Player:
    new_id = (max((p.id or 0 for p in players.rows), default=0)) + 1
    base = Player.new(tg_id=tg_id, username=Username(value="ivan"), now=_NOW)
    seeded = replace(
        base,
        id=new_id,
        status=status,
        thickness=Thickness(level=thickness_level),
    )
    players.rows.append(seeded)
    return seeded


def _build() -> tuple[
    GrantThickness,
    FakeAdminRepository,
    FakePlayerRepository,
    FakeBalanceConfig,
    FakeIdempotencyKey,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    players = FakePlayerRepository()
    balance = FakeBalanceConfig(_balance())
    idempotency = FakeIdempotencyKey()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    return (
        GrantThickness(
            uow=uow,
            admins=admins,
            players=players,
            balance=balance,
            idempotency=idempotency,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        ),
        admins,
        players,
        balance,
        idempotency,
        audit,
        uow,
    )


@pytest.mark.asyncio
class TestGrantThickness:
    async def test_inactive_admin_raises_authorization_error(self) -> None:
        uc, admins, players, _, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        admins.rows[0] = replace(admins.rows[0], is_active=False)
        _seed_player(players, tg_id=999)

        with pytest.raises(AuthorizationError):
            await uc.execute(
                GrantThicknessInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    new_level=2,
                    reason="manual upgrade",
                    idempotency_key="k",
                ),
            )

    async def test_unknown_actor_raises(self) -> None:
        uc, _, _, _, _, _, _ = _build()
        with pytest.raises(AuthorizationError):
            await uc.execute(
                GrantThicknessInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    new_level=2,
                    reason="r",
                    idempotency_key="k",
                ),
            )

    async def test_level_below_min_raises(self) -> None:
        uc, admins, players, _, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999)

        with pytest.raises(ThicknessLevelInvalidError) as ctx:
            await uc.execute(
                GrantThicknessInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    new_level=0,
                    reason="r",
                    idempotency_key="k",
                ),
            )
        assert ctx.value.reason_code == "below_min"

    async def test_level_above_max_raises(self) -> None:
        uc, admins, players, _, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999)

        with pytest.raises(ThicknessLevelInvalidError) as ctx:
            await uc.execute(
                GrantThicknessInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    new_level=99,  # max в factories = 3
                    reason="r",
                    idempotency_key="k",
                ),
            )
        assert ctx.value.reason_code == "above_max"
        assert ctx.value.max_level == 3

    async def test_empty_reason_rejected(self) -> None:
        uc, admins, players, _, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999)

        with pytest.raises(ValueError, match="reason must be a non-empty string"):
            await uc.execute(
                GrantThicknessInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    new_level=2,
                    reason="   ",
                    idempotency_key="k",
                ),
            )

    async def test_target_not_found(self) -> None:
        uc, admins, _, _, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)

        with pytest.raises(PlayerNotFoundError):
            await uc.execute(
                GrantThicknessInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    new_level=2,
                    reason="r",
                    idempotency_key="k",
                ),
            )

    async def test_banned_target_raises_blocked(self) -> None:
        uc, admins, players, _, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999, status=PlayerStatus.BANNED)

        with pytest.raises(GrantThicknessBlockedError) as ctx:
            await uc.execute(
                GrantThicknessInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    new_level=2,
                    reason="r",
                    idempotency_key="k",
                ),
            )
        assert ctx.value.reason == "player_banned"

    async def test_happy_path_mutates_and_audits(self) -> None:
        uc, admins, players, _, idempotency, audit, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999, thickness_level=1)

        out = await uc.execute(
            GrantThicknessInput(
                actor_tg_id=42,
                target_tg_id=999,
                new_level=3,
                reason="manual upgrade",
                idempotency_key="admin_grant_thickness:42|999|202605081200",
                tg_chat_id=12345,
            ),
        )

        assert out.previous_level == 1
        assert out.new_level == 3
        assert out.was_already_at_level is False
        assert out.was_idempotent_replay is False

        # Игрок реально обновлён.
        assert players.rows[0].thickness.level == 3

        # Audit запись присутствует.
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AdminAuditAction.ADMIN_GRANT_THICKNESS
        assert entry.target_kind == "player"
        assert entry.target_id == "999"
        assert entry.before == {"thickness_level": 1}
        assert entry.after == {"thickness_level": 3}
        assert entry.reason == "manual upgrade"
        assert entry.source is AdminAuditSource.BOT
        assert entry.tg_chat_id == 12345

        # Idempotency-ключ зафиксирован.
        assert await idempotency.is_seen("admin_grant_thickness:42|999|202605081200")

    async def test_already_at_level_is_no_op_no_audit(self) -> None:
        uc, admins, players, _, idempotency, audit, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999, thickness_level=2)

        out = await uc.execute(
            GrantThicknessInput(
                actor_tg_id=42,
                target_tg_id=999,
                new_level=2,
                reason="r",
                idempotency_key="admin_grant_thickness:42|999|202605081200",
            ),
        )

        assert out.was_already_at_level is True
        assert out.was_idempotent_replay is False
        assert out.new_level == 2
        # Без аудит-записи — не было реальной мутации.
        assert audit.entries == []
        # Но idempotency-ключ всё равно зафиксирован, чтобы повтор шёл по replay-ветке.
        assert await idempotency.is_seen("admin_grant_thickness:42|999|202605081200")

    async def test_replay_returns_current_level(self) -> None:
        uc, admins, players, _, idempotency, audit, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999, thickness_level=2)

        # Pre-mark — имитируем «уже был такой вызов».
        await idempotency.mark(
            "admin_grant_thickness:42|999|202605081200",
            namespace="admin_grant_thickness",
        )

        out = await uc.execute(
            GrantThicknessInput(
                actor_tg_id=42,
                target_tg_id=999,
                new_level=3,
                reason="r",
                idempotency_key="admin_grant_thickness:42|999|202605081200",
            ),
        )

        assert out.was_idempotent_replay is True
        assert out.previous_level == 2
        assert out.new_level == 2  # игрок НЕ обновлён
        assert players.rows[0].thickness.level == 2
        assert audit.entries == []
