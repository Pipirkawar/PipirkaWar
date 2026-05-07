"""Unit-тесты `GrantLength` (Спринт 2.5-C.1).

Use-case проксирует прибавку длины в `ILengthGranter.grant(...)` и
дополнительно пишет `ADMIN_GRANT_LENGTH` в админский audit-лог. Тесты
не зовут реальный `AddLength` — это слой `progression`, у него свой
обширный test-suite. Здесь — только поведение «админской обвязки»:
авторизация, маппинг знака дельты на `AuditSource`, идемпотентный
replay, пробрасывание ошибок (`PlayerNotFoundError`,
`AnticheatSoftBanError`, `LengthDeltaInvalidError`).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

import pytest

from pipirik_wars.application.admin import (
    GrantLength,
    GrantLengthBlockedError,
    GrantLengthInput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import AdminAuditAction, AdminAuditSource, AdminRole
from pipirik_wars.domain.player import Player, PlayerStatus, Username
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.errors import (
    AnticheatSoftBanError,
    LengthDeltaInvalidError,
)
from pipirik_wars.domain.progression.length_granter import (
    ILengthGranter,
    LengthGrantResult,
)
from pipirik_wars.domain.shared.ports.audit import AuditSource
from tests.fakes.admin_audit import FakeAdminAuditLogger
from tests.fakes.admin_authz import FakeAdminAuthzAllowAll
from tests.fakes.admin_repo import FakeAdminRepository
from tests.fakes.clock import FakeClock
from tests.fakes.player_repo import FakePlayerRepository
from tests.fakes.uow import FakeUnitOfWork

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


@dataclass
class _FakeLengthGranter(ILengthGranter):
    """Минимальный fake `ILengthGranter`: возвращает скриптованный результат."""

    next_result: LengthGrantResult | None = None
    next_exception: Exception | None = None
    captured_calls: list[dict[str, object]] = field(default_factory=list)

    async def grant(
        self,
        *,
        player_id: int,
        delta_cm: int,
        source: AuditSource,
        reason: str,
        idempotency_key: str | None = None,
    ) -> LengthGrantResult:
        self.captured_calls.append(
            {
                "player_id": player_id,
                "delta_cm": delta_cm,
                "source": source,
                "reason": reason,
                "idempotency_key": idempotency_key,
            }
        )
        if self.next_exception is not None:
            raise self.next_exception
        if self.next_result is None:
            raise AssertionError("FakeLengthGranter.next_result was not set")
        return self.next_result


def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    length_cm: int = 100,
    status: PlayerStatus = PlayerStatus.ACTIVE,
) -> Player:
    new_id = (max((p.id or 0 for p in players.rows), default=0)) + 1
    base = Player.new(tg_id=tg_id, username=Username(value="ivan"), now=_NOW)
    seeded = replace(
        base,
        id=new_id,
        status=status,
        length=replace(base.length, cm=length_cm),
    )
    players.rows.append(seeded)
    return seeded


def _build() -> tuple[
    GrantLength,
    FakeAdminRepository,
    FakePlayerRepository,
    _FakeLengthGranter,
    FakeAdminAuditLogger,
    FakeUnitOfWork,
]:
    admins = FakeAdminRepository()
    players = FakePlayerRepository()
    granter = _FakeLengthGranter()
    audit = FakeAdminAuditLogger()
    uow = FakeUnitOfWork()
    return (
        GrantLength(
            uow=uow,
            admins=admins,
            players=players,
            length_granter=granter,
            audit=audit,
            clock=FakeClock(_NOW),
            authz=FakeAdminAuthzAllowAll(),
        ),
        admins,
        players,
        granter,
        audit,
        uow,
    )


@pytest.mark.asyncio
class TestGrantLength:
    async def test_inactive_admin_raises_authorization_error(self) -> None:
        uc, admins, players, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        admins.rows[0] = replace(admins.rows[0], is_active=False)
        _seed_player(players, tg_id=999)

        with pytest.raises(AuthorizationError):
            await uc.execute(
                GrantLengthInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    delta_cm=50,
                    reason="event reward",
                    idempotency_key="k:42:grant_length:999:202605081200",
                ),
            )

    async def test_unknown_actor_raises_authorization_error(self) -> None:
        uc, _, players, _, _, _ = _build()
        _seed_player(players, tg_id=999)

        with pytest.raises(AuthorizationError):
            await uc.execute(
                GrantLengthInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    delta_cm=50,
                    reason="r",
                    idempotency_key="k",
                ),
            )

    async def test_zero_delta_rejected(self) -> None:
        uc, admins, players, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999)

        with pytest.raises(ValueError, match="delta_cm must be non-zero"):
            await uc.execute(
                GrantLengthInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    delta_cm=0,
                    reason="r",
                    idempotency_key="k",
                ),
            )

    async def test_empty_reason_rejected(self) -> None:
        uc, admins, players, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999)

        with pytest.raises(ValueError, match="reason must be a non-empty string"):
            await uc.execute(
                GrantLengthInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    delta_cm=50,
                    reason="   ",
                    idempotency_key="k",
                ),
            )

    async def test_target_not_found_raises(self) -> None:
        uc, admins, _, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)

        with pytest.raises(PlayerNotFoundError):
            await uc.execute(
                GrantLengthInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    delta_cm=50,
                    reason="r",
                    idempotency_key="k",
                ),
            )

    async def test_banned_target_raises_blocked(self) -> None:
        uc, admins, players, _, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999, status=PlayerStatus.BANNED)

        with pytest.raises(GrantLengthBlockedError) as ctx:
            await uc.execute(
                GrantLengthInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    delta_cm=50,
                    reason="r",
                    idempotency_key="k",
                ),
            )
        assert ctx.value.reason == "player_banned"
        assert ctx.value.tg_id == 999

    async def test_positive_delta_uses_admin_grant_source(self) -> None:
        uc, admins, players, granter, audit, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        target = _seed_player(players, tg_id=999, length_cm=100)
        granter.next_result = LengthGrantResult(
            applied_delta_cm=50,
            clamped_from=None,
            triggered_soft_ban=False,
            new_length_cm=150,
        )

        out = await uc.execute(
            GrantLengthInput(
                actor_tg_id=42,
                target_tg_id=999,
                delta_cm=50,
                reason="event reward",
                idempotency_key="k:42:grant_length:999:202605081200",
                tg_chat_id=12345,
            ),
        )

        assert out.applied_delta_cm == 50
        assert out.new_length_cm == 150
        assert out.was_idempotent_replay is False
        assert out.clamped_from is None
        assert out.triggered_soft_ban is False

        assert len(granter.captured_calls) == 1
        call = granter.captured_calls[0]
        assert call["player_id"] == target.id
        assert call["delta_cm"] == 50
        assert call["source"] is AuditSource.ADMIN_GRANT
        assert call["reason"] == "event reward"
        assert call["idempotency_key"] == "k:42:grant_length:999:202605081200"

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AdminAuditAction.ADMIN_GRANT_LENGTH
        assert entry.target_kind == "player"
        assert entry.target_id == "999"
        assert entry.before == {"length_cm": 100}
        assert entry.after == {"length_cm": 150}
        assert entry.reason == "event reward"
        assert entry.idempotency_key == "k:42:grant_length:999:202605081200"
        assert entry.source is AdminAuditSource.BOT
        assert entry.tg_chat_id == 12345

    async def test_negative_delta_uses_admin_refund_source(self) -> None:
        uc, admins, players, granter, audit, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999, length_cm=100)
        granter.next_result = LengthGrantResult(
            applied_delta_cm=-30,
            clamped_from=None,
            triggered_soft_ban=False,
            new_length_cm=70,
        )

        await uc.execute(
            GrantLengthInput(
                actor_tg_id=42,
                target_tg_id=999,
                delta_cm=-30,
                reason="rollback exploit",
                idempotency_key="k",
            ),
        )

        assert granter.captured_calls[0]["source"] is AuditSource.ADMIN_REFUND
        assert audit.entries[0].before == {"length_cm": 100}
        assert audit.entries[0].after == {"length_cm": 70}

    async def test_clamp_propagated_to_output(self) -> None:
        """Если `AddLength` сработал clamp — мы это пробрасываем наверх."""
        uc, admins, players, granter, audit, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999, length_cm=100)
        granter.next_result = LengthGrantResult(
            applied_delta_cm=20,
            clamped_from=100,  # запрашивали 100, получили 20
            triggered_soft_ban=False,
            new_length_cm=120,
        )

        out = await uc.execute(
            GrantLengthInput(
                actor_tg_id=42,
                target_tg_id=999,
                delta_cm=100,
                reason="big reward",
                idempotency_key="k",
            ),
        )
        assert out.applied_delta_cm == 20
        assert out.clamped_from == 100
        assert out.new_length_cm == 120
        assert audit.entries[0].after == {"length_cm": 120}

    async def test_idempotent_replay_no_audit(self) -> None:
        """`AddLength` вернул `applied=0, new_length=current` → no-op replay."""
        uc, admins, players, granter, audit, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999, length_cm=100)
        granter.next_result = LengthGrantResult(
            applied_delta_cm=0,
            clamped_from=None,
            triggered_soft_ban=False,
            new_length_cm=100,  # длина не изменилась
        )

        out = await uc.execute(
            GrantLengthInput(
                actor_tg_id=42,
                target_tg_id=999,
                delta_cm=50,
                reason="duplicate command",
                idempotency_key="k:42:grant_length:999:202605081200",
            ),
        )

        assert out.was_idempotent_replay is True
        assert out.applied_delta_cm == 0
        assert out.new_length_cm == 100
        # Audit-лог НЕ должен содержать дублирующую запись.
        assert audit.entries == []

    async def test_anticheat_soft_ban_propagated(self) -> None:
        """Если `AddLength` бросил `AnticheatSoftBanError` — мы пробрасываем."""
        uc, admins, players, granter, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999)
        granter.next_exception = AnticheatSoftBanError(
            tg_id=999,
            banned_until=datetime(2026, 5, 9, 12, 0, 0, tzinfo=UTC),
        )

        with pytest.raises(AnticheatSoftBanError):
            await uc.execute(
                GrantLengthInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    delta_cm=50,
                    reason="r",
                    idempotency_key="k",
                ),
            )

    async def test_invalid_delta_propagated(self) -> None:
        """`LengthDeltaInvalidError` (например, delta_cm < 0 для не-admin_refund)."""
        uc, admins, players, granter, _, _ = _build()
        await admins.add(tg_id=42, role=AdminRole.ECONOMIST, created_by_admin_id=None, note=None)
        _seed_player(players, tg_id=999)
        granter.next_exception = LengthDeltaInvalidError(
            delta_cm=50,
            source="admin_grant",
            reason_code="negative_for_non_refund",
        )

        with pytest.raises(LengthDeltaInvalidError):
            await uc.execute(
                GrantLengthInput(
                    actor_tg_id=42,
                    target_tg_id=999,
                    delta_cm=50,
                    reason="r",
                    idempotency_key="k",
                ),
            )
