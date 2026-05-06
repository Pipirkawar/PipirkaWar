"""Юнит-тесты `RunDailyHeadCron` (Спринт 2.3.C, cron-trigger).

Покрывают:
- happy-path: cron-вызов добавляет запись + LENGTH_GRANT/DAILY_HEAD_ASSIGN;
  `actor_id=None` (cron — автомат, нет инициатора-игрока);
- идемпотентность: если кнопка успела раньше, cron вернёт `was_new=False`;
- frozen-клан → тихий `return None` (cron-job не должен падать);
- неизвестный clan_id → `IntegrityError`;
- insufficient activity пробрасывается (шедулер логирует и продолжает работу).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.daily_head import RunDailyHeadCron
from pipirik_wars.application.dto.inputs import RunDailyHeadCronInput
from pipirik_wars.application.progression import AddLength
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanStatus,
)
from pipirik_wars.domain.clan.value_objects import ClanTitle
from pipirik_wars.domain.daily_head import (
    DailyHeadAssignment,
    DailyHeadInsufficientActivityError,
    DailyHeadService,
    DailyHeadSource,
)
from pipirik_wars.domain.player import (
    Player,
    PlayerStatus,
    Thickness,
)
from pipirik_wars.domain.player.value_objects import Length, Username
from pipirik_wars.domain.shared.ports.audit import (
    AuditAction,
    AuditSource,
)
from pipirik_wars.shared.errors import IntegrityError
from tests.fakes import (
    FakeAnticheatAdminAlerter,
    FakeAnticheatRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeClanRepository,
    FakeClock,
    FakeDailyActivityRepository,
    FakeDailyHeadRepository,
    FakeIdempotencyKey,
    FakePlayerRepository,
    FakeRandom,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 6, 9, 0, tzinfo=UTC)
_CLAN_ID = 42


def _make_player(*, player_id: int, length_cm: int = 30) -> Player:
    return Player(
        id=player_id,
        tg_id=1000 + player_id,
        username=Username(value=f"user{player_id}"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=1),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_clan(*, clan_id: int = _CLAN_ID, status: ClanStatus = ClanStatus.ACTIVE) -> Clan:
    return Clan(
        id=clan_id,
        chat_id=-100123,
        chat_kind=ChatKind.SUPERGROUP,
        title=ClanTitle(value="Тестовый клан"),
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _build(
    *,
    clan: Clan | None = None,
    active_player_ids: tuple[int, ...] = (10, 11, 12, 13, 14),
    seed_existing_assignment: bool = False,
) -> tuple[
    RunDailyHeadCron,
    FakeDailyHeadRepository,
    FakeAuditLogger,
]:
    uow = FakeUnitOfWork()
    clock = FakeClock(_NOW)
    rng = FakeRandom(seed=1)
    audit = FakeAuditLogger()
    balance_cfg = build_valid_balance()
    balance = FakeBalanceConfig(balance_cfg)

    clans = FakeClanRepository()
    clans.rows.append(clan or _make_clan())

    players_repo = FakePlayerRepository()
    for pid in active_player_ids:
        players_repo.rows.append(_make_player(player_id=pid))

    heads = FakeDailyHeadRepository()
    if seed_existing_assignment:
        heads.items.append(
            DailyHeadAssignment(
                id=1,
                clan_id=_CLAN_ID,
                player_id=active_player_ids[0],
                moscow_date=clock.moscow_date(),
                source=DailyHeadSource.BUTTON,
                bonus_cm=7,
                assigned_at=_NOW,
            ),
        )

    activity = FakeDailyActivityRepository()
    activity.by_clan[_CLAN_ID] = list(active_player_ids)

    length_granter = AddLength(
        uow=uow,
        players=players_repo,
        anticheat=FakeAnticheatRepository(),
        audit=audit,
        balance=balance,
        clock=clock,
        idempotency=FakeIdempotencyKey(),
        admin_alerter=FakeAnticheatAdminAlerter(),
    )

    daily_head_service = DailyHeadService(
        balance=balance_cfg,
        clock=clock,
        random=rng,
        heads=heads,
        activity=activity,
    )

    use_case = RunDailyHeadCron(
        uow=uow,
        clans=clans,
        players=players_repo,
        heads=heads,
        daily_head_service=daily_head_service,
        length_granter=length_granter,
        audit=audit,
        clock=clock,
    )
    return use_case, heads, audit


@pytest.mark.asyncio
class TestRunDailyHeadCronHappyPath:
    async def test_creates_assignment_with_cron_source(self) -> None:
        use_case, heads, audit = _build()

        result = await use_case.execute(RunDailyHeadCronInput(clan_id=_CLAN_ID))

        assert result is not None
        assert result.was_new is True
        assert result.assignment.source is DailyHeadSource.CRON
        assert len(heads.items) == 1
        # Аудит — оба типа.
        actions = [e.action for e in audit.entries]
        assert AuditAction.LENGTH_GRANT in actions
        assert AuditAction.DAILY_HEAD_ASSIGN in actions

    async def test_audit_actor_id_is_none_for_cron(self) -> None:
        use_case, _, audit = _build()

        await use_case.execute(RunDailyHeadCronInput(clan_id=_CLAN_ID))

        head_entry = next(e for e in audit.entries if e.action is AuditAction.DAILY_HEAD_ASSIGN)
        # Cron — автомат, нет initiator-игрока.
        assert head_entry.actor_id is None
        assert head_entry.reason == "daily_head_cron"

    async def test_length_grant_uses_daily_head_source(self) -> None:
        use_case, _, audit = _build()
        await use_case.execute(RunDailyHeadCronInput(clan_id=_CLAN_ID))
        length_entries = [e for e in audit.entries if e.action is AuditAction.LENGTH_GRANT]
        assert length_entries[0].source is AuditSource.DAILY_HEAD


@pytest.mark.asyncio
class TestRunDailyHeadCronIdempotent:
    async def test_returns_existing_button_assignment(self) -> None:
        """Кнопка успела раньше cron — cron возвращает запись кнопки без новых side-effects."""
        use_case, heads, audit = _build(seed_existing_assignment=True)

        result = await use_case.execute(RunDailyHeadCronInput(clan_id=_CLAN_ID))

        assert result is not None
        assert result.was_new is False
        assert result.assignment.id == 1
        # Source существующего — BUTTON, не CRON.
        assert result.assignment.source is DailyHeadSource.BUTTON
        assert len(heads.items) == 1
        assert audit.entries == []


@pytest.mark.asyncio
class TestRunDailyHeadCronErrors:
    async def test_unknown_clan_raises_integrity_error(self) -> None:
        use_case, _, _ = _build()
        with pytest.raises(IntegrityError):
            await use_case.execute(RunDailyHeadCronInput(clan_id=9999))

    async def test_frozen_clan_returns_none_silently(self) -> None:
        """Cron не должен падать на frozen — это ожидаемый no-op.

        ПД 2.3.8: «frozen-кланы не получают триггер главы». Cron-callback
        в шедулере (2.3.F) не должен ронять job на каждый frozen-клан
        в системе.
        """
        frozen = _make_clan(status=ClanStatus.FROZEN)
        use_case, heads, audit = _build(clan=frozen)

        result = await use_case.execute(RunDailyHeadCronInput(clan_id=_CLAN_ID))

        assert result is None
        assert heads.items == []
        assert audit.entries == []

    async def test_insufficient_activity_propagates(self) -> None:
        """Шедулер сам ловит и логирует — use-case бросает наружу как контракт."""
        use_case, heads, audit = _build(active_player_ids=(10, 11))

        with pytest.raises(DailyHeadInsufficientActivityError):
            await use_case.execute(RunDailyHeadCronInput(clan_id=_CLAN_ID))
        assert heads.items == []
        assert audit.entries == []


@pytest.mark.asyncio
class TestRunDailyHeadCronInteraction:
    async def test_cron_after_button_no_op(self) -> None:
        """Сначала кнопка, потом cron — cron не делает повторных side-effects."""
        # Шаг 1: кнопка через `RequestDailyHead` (но мы используем seed_existing).
        use_case, heads, audit = _build(seed_existing_assignment=True)

        result = await use_case.execute(RunDailyHeadCronInput(clan_id=_CLAN_ID))

        assert result is not None
        assert result.was_new is False
        assert len(heads.items) == 1
        assert audit.entries == []
