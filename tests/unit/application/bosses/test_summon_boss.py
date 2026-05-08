"""Unit-тесты `SummonBoss` (Спринт 3.3-B, ГДД §10.1 — §10.3).

Покрытие:
- happy-path: саммонер призывает рейд-босса; первый рейдер = саммонер;
- audit `BOSS_FIGHT_SUMMONED` с idempotency-key;
- лок берётся (`LockReason.RAID`), scheduler `boss_lobby_close` запланирован;
- random_seed сохранён в `[0, 2**31)`;
- ошибки: player не найден, player заморожен, thickness < 9, длина < 20 см,
  глобальный кулдаун не истёк, активный лок (двойной призыв), пул кандидатов пуст.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.bosses import BossSummoned, SummonBoss
from pipirik_wars.application.dto.inputs import SummonBossInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.bosses import (
    AlreadyInBossFightError,
    BossFightRequirementError,
    BossFightStatus,
    BossKind,
    BossPlayerPoolEmptyError,
    BossSummonOnGlobalCooldownError,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerNotFoundError,
    Thickness,
    Username,
)
from pipirik_wars.domain.player.errors import PlayerFrozenError
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeBossFightRepository,
    FakeBossParticipantRepository,
    FakeClock,
    FakeDelayedJobScheduler,
    FakePlayerRepository,
    FakeRandom,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_SUMMONER_TG_ID = 42


def _build_use_case(
    *,
    seed: int = 12345,
    clock: FakeClock | None = None,
) -> tuple[
    SummonBoss,
    FakeUnitOfWork,
    FakePlayerRepository,
    FakeBossFightRepository,
    FakeBossParticipantRepository,
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeClock,
    FakeDelayedJobScheduler,
]:
    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    boss_participants = FakeBossParticipantRepository()
    boss_fights = FakeBossFightRepository(participants=boss_participants)
    lock_repo = FakeActivityLockRepository()
    audit = FakeAuditLogger()
    used_clock = clock or FakeClock(_NOW)
    rng = FakeRandom(seed=seed)
    locks = ActivityLockService(repository=lock_repo, clock=used_clock)
    balance = FakeBalanceConfig(build_valid_balance())
    scheduler = FakeDelayedJobScheduler()
    use_case = SummonBoss(
        uow=uow,
        players=players,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        locks=locks,
        balance=balance,
        random=rng,
        audit=audit,
        clock=used_clock,
        scheduler=scheduler,
    )
    return (
        use_case,
        uow,
        players,
        boss_fights,
        boss_participants,
        lock_repo,
        audit,
        used_clock,
        scheduler,
    )


async def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    username: str,
    length_cm: int = 100,
    thickness_level: int = 9,
) -> Player:
    fresh = Player.new(tg_id=tg_id, username=Username(value=username), now=_NOW)
    persisted = await players.add(fresh)
    upgraded = persisted.with_thickness(Thickness(level=thickness_level), now=_NOW).with_length(
        Length(cm=length_cm), now=_NOW
    )
    return await players.save(upgraded)


async def _seed_summoner(
    players: FakePlayerRepository,
    *,
    length_cm: int = 100,
    thickness_level: int = 9,
) -> Player:
    return await _seed_player(
        players,
        tg_id=_SUMMONER_TG_ID,
        username="summoner",
        length_cm=length_cm,
        thickness_level=thickness_level,
    )


async def _seed_boss_candidate(
    players: FakePlayerRepository,
    *,
    tg_id: int = 7777,
    username: str = "topplayer",
    length_cm: int = 500,
) -> Player:
    """Зерно «топового» кандидата в боссы — длинее саммонера."""
    return await _seed_player(
        players,
        tg_id=tg_id,
        username=username,
        length_cm=length_cm,
        thickness_level=9,
    )


def _input(*, summoner_tg_id: int = _SUMMONER_TG_ID) -> SummonBossInput:
    return SummonBossInput(summoner_tg_id=summoner_tg_id)


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_creates_boss_fight_in_lobby(self) -> None:
        (
            use_case,
            uow,
            players,
            boss_fights,
            participants,
            _lock_repo,
            _audit,
            clock,
            scheduler,
        ) = _build_use_case()
        summoner = await _seed_summoner(players)
        boss = await _seed_boss_candidate(players)

        result = await use_case.execute(_input())

        assert isinstance(result, BossSummoned)
        bf = result.boss_fight
        assert bf.id == 1
        assert bf.kind is BossKind.RAID
        assert bf.summoner_player_id == summoner.id
        assert bf.boss_player_id == boss.id
        assert bf.status is BossFightStatus.LOBBY
        assert bf.started_at == clock.now()
        cfg = build_valid_balance().bosses
        assert bf.lobby_ends_at == clock.now() + timedelta(minutes=cfg.lobby_minutes)
        assert bf.initial_boss_length_cm == boss.length.cm
        assert bf.current_boss_length_cm == boss.length.cm
        assert len(boss_fights.rows) == 1
        # Саммонер сохранён как первый рейдер.
        assert len(participants.rows) == 1
        sp = participants.rows[0]
        assert sp.boss_fight_id == bf.id
        assert sp.player_id == summoner.id
        assert sp.is_summoner is True
        assert sp.length_at_join_cm == summoner.length.cm
        # Транзакция коммитится ровно раз.
        assert uow.commits == 1
        assert uow.rollbacks == 0
        # Лобби-close-job запланирован на `lobby_ends_at`.
        assert bf.id is not None
        assert scheduler.scheduled_boss_lobby_close[bf.id].run_at == bf.lobby_ends_at

    @pytest.mark.asyncio
    async def test_returns_summoner_participant(self) -> None:
        (
            use_case,
            _uow,
            players,
            _boss_fights,
            _participants,
            _lock_repo,
            _audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        summoner = await _seed_summoner(players)
        await _seed_boss_candidate(players)

        result = await use_case.execute(_input())

        assert result.summoner_participant.player_id == summoner.id
        assert result.summoner_participant.is_summoner is True

    @pytest.mark.asyncio
    async def test_lock_taken_with_raid_reason(self) -> None:
        (
            use_case,
            _uow,
            players,
            _boss_fights,
            _participants,
            lock_repo,
            _audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        summoner = await _seed_summoner(players)
        await _seed_boss_candidate(players)

        await use_case.execute(_input())

        assert summoner.id is not None
        lock = await lock_repo.get(actor_kind="player", actor_id=summoner.id)
        assert lock is not None
        assert lock.reason is LockReason.RAID

    @pytest.mark.asyncio
    async def test_random_seed_persisted_in_range(self) -> None:
        (
            use_case,
            _uow,
            players,
            boss_fights,
            _participants,
            _lock_repo,
            _audit,
            _clock,
            _scheduler,
        ) = _build_use_case(seed=999)
        await _seed_summoner(players)
        await _seed_boss_candidate(players)

        await use_case.execute(_input())

        assert len(boss_fights.rows) == 1
        seed = boss_fights.rows[0].random_seed
        assert 0 <= seed < 2**31

    @pytest.mark.asyncio
    async def test_summoner_excluded_from_boss_pool(self) -> None:
        """Саммонер не может стать боссом своего же рейда (ГДД §10.1)."""
        (
            use_case,
            _uow,
            players,
            boss_fights,
            _participants,
            _lock_repo,
            _audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        # Саммонер сам по себе самый длинный (top-1).
        summoner = await _seed_player(
            players,
            tg_id=_SUMMONER_TG_ID,
            username="summoner",
            length_cm=10_000,
            thickness_level=9,
        )
        boss = await _seed_boss_candidate(players, length_cm=500)

        await use_case.execute(_input())

        # Босс — это другой игрок, не саммонер.
        assert len(boss_fights.rows) == 1
        assert boss_fights.rows[0].boss_player_id == boss.id
        assert boss_fights.rows[0].boss_player_id != summoner.id


class TestAuditEntry:
    @pytest.mark.asyncio
    async def test_audit_records_boss_fight_summoned(self) -> None:
        (
            use_case,
            _uow,
            players,
            _boss_fights,
            _participants,
            _lock_repo,
            audit,
            clock,
            _scheduler,
        ) = _build_use_case()
        summoner = await _seed_summoner(players)
        boss = await _seed_boss_candidate(players)

        result = await use_case.execute(_input())

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.BOSS_FIGHT_SUMMONED
        assert entry.actor_id == summoner.tg_id
        assert entry.target_kind == "boss_fight"
        assert entry.target_id == str(result.boss_fight.id)
        assert entry.before is None
        assert entry.after is not None
        assert entry.after["kind"] == "raid"
        assert entry.after["summoner_player_id"] == summoner.id
        assert entry.after["boss_player_id"] == boss.id
        assert entry.after["initial_boss_length_cm"] == boss.length.cm
        assert entry.idempotency_key == f"boss_fight_summoned:{result.boss_fight.id}"
        assert entry.occurred_at == clock.now()


class TestErrors:
    @pytest.mark.asyncio
    async def test_player_not_found_raises(self) -> None:
        (
            use_case,
            uow,
            _players,
            boss_fights,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()

        with pytest.raises(PlayerNotFoundError) as exc:
            await use_case.execute(_input())

        assert exc.value.tg_id == _SUMMONER_TG_ID
        assert boss_fights.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1
        assert uow.commits == 0

    @pytest.mark.asyncio
    async def test_player_frozen_raises(self) -> None:
        (
            use_case,
            uow,
            players,
            boss_fights,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        summoner = await _seed_summoner(players)
        await _seed_boss_candidate(players)
        await players.save(summoner.freeze(now=_NOW))

        with pytest.raises(PlayerFrozenError) as exc:
            await use_case.execute(_input())

        assert exc.value.tg_id == _SUMMONER_TG_ID
        assert boss_fights.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_thickness_below_required_raises(self) -> None:
        (
            use_case,
            uow,
            players,
            boss_fights,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        summoner = await _seed_summoner(players, thickness_level=8)
        await _seed_boss_candidate(players)

        with pytest.raises(BossFightRequirementError) as exc:
            await use_case.execute(_input())

        assert exc.value.requirement == "thickness"
        assert exc.value.required == 9
        assert exc.value.actual == 8
        assert exc.value.player_id == summoner.id
        assert boss_fights.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_length_below_required_raises(self) -> None:
        (
            use_case,
            uow,
            players,
            boss_fights,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        summoner = await _seed_summoner(players, length_cm=19)
        await _seed_boss_candidate(players)

        with pytest.raises(BossFightRequirementError) as exc:
            await use_case.execute(_input())

        assert exc.value.requirement == "length_total"
        assert exc.value.required == 20
        assert exc.value.actual == 19
        assert exc.value.player_id == summoner.id
        assert boss_fights.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_global_cooldown_not_expired_raises(self) -> None:
        """ГДД §10.1: один призыв в 4 часа на проект."""
        (
            use_case,
            uow,
            players,
            boss_fights,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        await _seed_summoner(players)
        await _seed_boss_candidate(players)

        # Первый призыв проходит.
        first = await use_case.execute(_input())
        assert first.boss_fight.id == 1

        # Сразу попытка повторить — кулдаун глобальный, режет.
        with pytest.raises(BossSummonOnGlobalCooldownError) as exc:
            await use_case.execute(_input())

        assert exc.value.actual_remaining_seconds > 0
        # Кулдаун = 4ч, прошло 0 секунд → остаток ≈ 4 * 3600 = 14400.
        cfg = build_valid_balance().bosses
        expected = cfg.summon_cooldown_hours * 3600
        # Допускаем небольшую погрешность из-за округления.
        assert abs(exc.value.actual_remaining_seconds - expected) <= 1
        # Только один бой создан.
        assert len(boss_fights.rows) == 1
        # Audit — только за первый призыв.
        assert len(audit.entries) == 1
        # Откатилась только вторая транзакция.
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_global_cooldown_expired_allows_new_summon(self) -> None:
        """После истечения 4ч саммонер может призвать ещё раз."""
        clock = FakeClock(_NOW)
        (
            use_case,
            _uow,
            players,
            boss_fights,
            _participants,
            lock_repo,
            _audit,
            _clk,
            _scheduler,
        ) = _build_use_case(clock=clock)
        await _seed_summoner(players)
        await _seed_boss_candidate(players)
        # Дополнительный кандидат, чтобы пул не опустел между призывами.
        await _seed_boss_candidate(players, tg_id=7778, username="topplayer2", length_cm=400)

        # Первый призыв.
        await use_case.execute(_input())

        # Перематываем часы за пределы кулдауна (4ч + 1 секунда).
        cfg = build_valid_balance().bosses
        clock.set(_NOW + timedelta(hours=cfg.summon_cooldown_hours, seconds=1))

        # Снимаем активити-лок саммонера (имитируем окончание лобби).
        # Иначе AlreadyInBossFightError перебьёт cooldown-проверку.
        summoner_id = boss_fights.rows[0].summoner_player_id
        await lock_repo.release(actor_kind="player", actor_id=summoner_id)

        result = await use_case.execute(_input())

        assert result.boss_fight.id == 2
        assert len(boss_fights.rows) == 2

    @pytest.mark.asyncio
    async def test_active_lock_raises_already_in_boss_fight(self) -> None:
        """Двойной призыв подряд: активити-лок саммонера занят первым призывом."""
        (
            use_case,
            uow,
            players,
            boss_fights,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        summoner = await _seed_summoner(players)
        await _seed_boss_candidate(players)

        # Первый призыв ставит лок и создаёт бой.
        await use_case.execute(_input())
        # Стираем boss_fights чтобы обойти cooldown — это узкоспециализированный кейс
        # «лок уже взят», cooldown-кейс уже покрыт отдельно.
        boss_fights.rows.clear()

        with pytest.raises(AlreadyInBossFightError) as exc:
            await use_case.execute(_input())

        assert exc.value.player_id == summoner.id
        # Транзакция второго призыва откатилась.
        assert uow.rollbacks == 1
        # Аудит — только первый.
        assert len(audit.entries) == 1

    @pytest.mark.asyncio
    async def test_pool_empty_raises_when_only_summoner_exists(self) -> None:
        """Кейс редкий, но возможный: единственный игрок — сам саммонер."""
        (
            use_case,
            uow,
            players,
            boss_fights,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        await _seed_summoner(players)
        # Босс-кандидатов больше нет.

        with pytest.raises(BossPlayerPoolEmptyError) as exc:
            await use_case.execute(_input())

        # `pool_size` — это размер top-N до фильтрации (топ — 1: сам саммонер).
        assert exc.value.pool_size == 1
        assert boss_fights.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1

    @pytest.mark.asyncio
    async def test_pool_empty_when_no_players_at_all(self) -> None:
        """Совсем пустой пул (например, саммонер ещё не добавлен в репо)."""
        (
            use_case,
            uow,
            _players,
            boss_fights,
            _participants,
            _lock_repo,
            audit,
            _clock,
            _scheduler,
        ) = _build_use_case()
        # Никаких игроков — даже саммонера нет → PlayerNotFoundError первее
        # (это покрыто отдельно). Чтобы получить пустой пул, добавим
        # только саммонера.
        await _seed_summoner(_players)

        with pytest.raises(BossPlayerPoolEmptyError):
            await use_case.execute(_input())

        assert boss_fights.rows == []
        assert audit.entries == []
        assert uow.rollbacks == 1
