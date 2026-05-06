"""Юнит-тесты `RequestDailyHead` (Спринт 2.3.C, button-trigger).

Покрывают acceptance-критерии:
- happy-path: новая запись + LENGTH_GRANT-аудит + DAILY_HEAD_ASSIGN-аудит +
  player.length увеличена на bonus_cm;
- идемпотентность: повторный нажим в те же сутки → `was_new=False`,
  без повторных side-effects;
- race-условие (UNIQUE-violation на add) → re-fetch winner, `was_new=False`;
- frozen клан → `ClanFrozenError`, никаких записей;
- неизвестный chat_id → `IntegrityError`;
- `DailyHeadInsufficientActivityError` пробрасывается из доменного сервиса.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pipirik_wars.application.daily_head import RequestDailyHead
from pipirik_wars.application.dto.inputs import RequestDailyHeadInput
from pipirik_wars.application.progression import AddLength
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanFrozenError,
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
_CLAN_CHAT_ID = -100123
_ACTOR_TG_ID = 999
_BONUS_CM = 10  # FakeRandom(seed=1).randint(1, 20) детерминирован


def _make_player(*, player_id: int, tg_id: int, length_cm: int) -> Player:
    return Player(
        id=player_id,
        tg_id=tg_id,
        username=Username(value=f"user{player_id}"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=1),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _make_clan(*, clan_id: int, chat_id: int, status: ClanStatus = ClanStatus.ACTIVE) -> Clan:
    return Clan(
        id=clan_id,
        chat_id=chat_id,
        chat_kind=ChatKind.SUPERGROUP,
        title=ClanTitle(value="Тестовый клан"),
        status=status,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _build(
    *,
    seed: int = 1,
    clan: Clan | None = None,
    active_player_ids: tuple[int, ...] = (10, 11, 12, 13, 14),
    seed_existing_assignment: bool = False,
) -> tuple[
    RequestDailyHead,
    FakeClanRepository,
    FakePlayerRepository,
    FakeDailyHeadRepository,
    FakeAuditLogger,
    FakeUnitOfWork,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    clock = FakeClock(_NOW)
    rng = FakeRandom(seed=seed)
    audit = FakeAuditLogger()
    balance_cfg = build_valid_balance()
    balance = FakeBalanceConfig(balance_cfg)

    clans = FakeClanRepository()
    clans.rows.append(clan or _make_clan(clan_id=42, chat_id=_CLAN_CHAT_ID))

    players_repo = FakePlayerRepository()
    for pid in active_player_ids:
        players_repo.rows.append(_make_player(player_id=pid, tg_id=1000 + pid, length_cm=30))

    heads = FakeDailyHeadRepository()
    if seed_existing_assignment:
        heads.items.append(
            DailyHeadAssignment(
                id=1,
                clan_id=clans.rows[0].id or 42,
                player_id=active_player_ids[0],
                moscow_date=clock.moscow_date(),
                source=DailyHeadSource.BUTTON,
                bonus_cm=7,
                assigned_at=_NOW,
            ),
        )

    activity = FakeDailyActivityRepository()
    activity.by_clan[clans.rows[0].id or 42] = list(active_player_ids)

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

    use_case = RequestDailyHead(
        uow=uow,
        clans=clans,
        players=players_repo,
        heads=heads,
        daily_head_service=daily_head_service,
        length_granter=length_granter,
        audit=audit,
        clock=clock,
    )
    return use_case, clans, players_repo, heads, audit, uow, clock


@pytest.mark.asyncio
class TestRequestDailyHeadHappyPath:
    async def test_creates_assignment_grants_length_and_writes_audit(self) -> None:
        use_case, _, players, heads, audit, _, _ = _build()

        result = await use_case.execute(
            RequestDailyHeadInput(chat_id=_CLAN_CHAT_ID, actor_tg_id=_ACTOR_TG_ID),
        )

        assert result.was_new is True
        assert result.assignment.id is not None
        assert result.assignment.source is DailyHeadSource.BUTTON
        assert 1 <= result.assignment.bonus_cm <= 20
        # Запись добавлена в `daily_heads`.
        assert len(heads.items) == 1
        # Игрок-победитель получил прибавку.
        assert result.player is not None
        winner = next(p for p in players.rows if p.id == result.assignment.player_id)
        assert winner.length.cm == 30 + result.assignment.bonus_cm
        # Аудит: и LENGTH_GRANT (от length_granter), и DAILY_HEAD_ASSIGN (use-case).
        actions = [e.action for e in audit.entries]
        assert AuditAction.LENGTH_GRANT in actions
        assert AuditAction.DAILY_HEAD_ASSIGN in actions

    async def test_length_grant_uses_daily_head_source(self) -> None:
        use_case, _, _, _, audit, _, _ = _build()

        await use_case.execute(
            RequestDailyHeadInput(chat_id=_CLAN_CHAT_ID, actor_tg_id=_ACTOR_TG_ID),
        )

        length_entries = [e for e in audit.entries if e.action is AuditAction.LENGTH_GRANT]
        assert len(length_entries) == 1
        assert length_entries[0].source is AuditSource.DAILY_HEAD

    async def test_daily_head_audit_payload(self) -> None:
        use_case, _, _, _, audit, _, _ = _build()

        result = await use_case.execute(
            RequestDailyHeadInput(chat_id=_CLAN_CHAT_ID, actor_tg_id=_ACTOR_TG_ID),
        )

        head_entry = next(e for e in audit.entries if e.action is AuditAction.DAILY_HEAD_ASSIGN)
        assert head_entry.actor_id == _ACTOR_TG_ID
        assert head_entry.target_kind == "clan"
        assert head_entry.target_id == "42"
        assert head_entry.before is None
        assert head_entry.after is not None
        assert head_entry.after["player_id"] == result.assignment.player_id
        assert head_entry.after["source"] == "button"
        assert head_entry.after["bonus_cm"] == result.assignment.bonus_cm
        assert head_entry.reason == "daily_head_button"

    async def test_idempotency_key_stable_for_same_clan_and_day(self) -> None:
        use_case, _, _, _, audit, _, _ = _build()

        await use_case.execute(
            RequestDailyHeadInput(chat_id=_CLAN_CHAT_ID, actor_tg_id=_ACTOR_TG_ID),
        )

        head_entry = next(e for e in audit.entries if e.action is AuditAction.DAILY_HEAD_ASSIGN)
        # Стабильный idempotency-key (clan_id + moscow_date).
        assert head_entry.idempotency_key == "daily_head_assign:42:2026-05-06"


@pytest.mark.asyncio
class TestRequestDailyHeadIdempotent:
    async def test_returns_existing_without_side_effects(self) -> None:
        use_case, _, _, heads, audit, _, _ = _build(seed_existing_assignment=True)

        result = await use_case.execute(
            RequestDailyHeadInput(chat_id=_CLAN_CHAT_ID, actor_tg_id=_ACTOR_TG_ID),
        )

        assert result.was_new is False
        # Ровно та же запись.
        assert result.assignment.id == 1
        assert result.assignment.bonus_cm == 7
        # Никаких новых записей в `daily_heads`.
        assert len(heads.items) == 1
        # Никаких новых audit-записей.
        assert audit.entries == []

    async def test_double_call_results_in_single_grant(self) -> None:
        use_case, _, _, heads, audit, _, _ = _build()

        result_a = await use_case.execute(
            RequestDailyHeadInput(chat_id=_CLAN_CHAT_ID, actor_tg_id=_ACTOR_TG_ID),
        )
        result_b = await use_case.execute(
            RequestDailyHeadInput(chat_id=_CLAN_CHAT_ID, actor_tg_id=_ACTOR_TG_ID),
        )

        assert result_a.was_new is True
        assert result_b.was_new is False
        assert result_b.assignment.id == result_a.assignment.id
        # Только одна запись в daily_heads.
        assert len(heads.items) == 1
        # LENGTH_GRANT и DAILY_HEAD_ASSIGN должны быть по одному разу.
        length_entries = [e for e in audit.entries if e.action is AuditAction.LENGTH_GRANT]
        head_entries = [e for e in audit.entries if e.action is AuditAction.DAILY_HEAD_ASSIGN]
        assert len(length_entries) == 1
        assert len(head_entries) == 1


@pytest.mark.asyncio
class TestRequestDailyHeadErrors:
    async def test_unknown_chat_id_raises_integrity_error(self) -> None:
        use_case, _, _, _, _, _, _ = _build()
        with pytest.raises(IntegrityError):
            await use_case.execute(
                RequestDailyHeadInput(chat_id=-9999, actor_tg_id=_ACTOR_TG_ID),
            )

    async def test_frozen_clan_raises_clan_frozen_error(self) -> None:
        frozen = _make_clan(clan_id=42, chat_id=_CLAN_CHAT_ID, status=ClanStatus.FROZEN)
        use_case, _, _, heads, audit, _, _ = _build(clan=frozen)

        with pytest.raises(ClanFrozenError):
            await use_case.execute(
                RequestDailyHeadInput(chat_id=_CLAN_CHAT_ID, actor_tg_id=_ACTOR_TG_ID),
            )
        # Никаких записей не должно появиться.
        assert heads.items == []
        assert audit.entries == []

    async def test_insufficient_activity_propagates(self) -> None:
        # min_active_members в build_valid_balance = 5, активных только 2 → ошибка.
        use_case, _, _, heads, audit, _, _ = _build(active_player_ids=(10, 11))

        with pytest.raises(DailyHeadInsufficientActivityError):
            await use_case.execute(
                RequestDailyHeadInput(chat_id=_CLAN_CHAT_ID, actor_tg_id=_ACTOR_TG_ID),
            )
        assert heads.items == []
        assert audit.entries == []


@pytest.mark.asyncio
class TestRequestDailyHeadRace:
    async def test_race_loser_returns_winner_assignment(self) -> None:
        """Симулируем гонку: после `assign_or_get`-выбора кандидата другой
        транзакции успела вставить запись. Use-case ловит
        `DailyHeadAlreadyAssignedError` от `heads.add(...)` и возвращает
        запись победителя.
        """
        use_case, _, players, heads, audit, _, clock = _build()

        # Эмулируем гонку: monkey-patch `heads.add` так, чтобы
        # перед фактическим INSERT-ом мы уже знали о записи победителя
        # (как будто другая транзакция её добавила).
        original_add = heads.add

        async def racing_add(assignment: DailyHeadAssignment) -> DailyHeadAssignment:
            # Победитель попал в репо до нашего add.
            if not heads.items:
                heads.items.append(
                    DailyHeadAssignment(
                        id=99,
                        clan_id=assignment.clan_id,
                        player_id=999,  # другой кандидат
                        moscow_date=assignment.moscow_date,
                        source=DailyHeadSource.CRON,
                        bonus_cm=5,
                        assigned_at=_NOW,
                    ),
                )
            return await original_add(assignment)

        heads.add = racing_add  # type: ignore[method-assign]
        # Победитель — игрок 999, нужно его подсунуть в players-репо.
        players.rows.append(_make_player(player_id=999, tg_id=2999, length_cm=30))

        result = await use_case.execute(
            RequestDailyHeadInput(chat_id=_CLAN_CHAT_ID, actor_tg_id=_ACTOR_TG_ID),
        )

        assert result.was_new is False
        assert result.assignment.id == 99
        assert result.assignment.player_id == 999
        # Race-loser не должен начислять длину или писать audit.
        assert audit.entries == []

        # Smoke: clock использован.
        assert clock.now() == _NOW
