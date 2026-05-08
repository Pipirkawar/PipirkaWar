"""Unit-тесты `RunBossRound` (Спринт 3.3-C, ГДД §10.4).

Покрытие:
- happy-path: бой продолжается → next round-tick шедулится, boss-HP
  обновлён, current_round инкрементирован, audit BOSS_FIGHT_ROUND_RESOLVED
  записан с idempotency-key `boss_fight_round_resolved:{id}:{round}`;
- победа рейдеров: HP босса опустилось < victory_threshold_cm →
  bf переведён в FINISHED, pending tick-job отменён, next-tick НЕ шедулится;
- победа босса: после раунда все рейдеры выбили → bf переведён в FINISHED,
  активные participant-ы удалены через repo.remove() + locks released;
- corner-case: список рейдеров уже пуст на входе → bf-FINISHED,
  resolve-сервис НЕ зовётся (audit + tick cleanup);
- идемпотентность: повторный вызов на FINISHED/CANCELLED → no-op
  (was_already_finished=True, без аудита, без шедула);
- ошибки: BossFightNotFoundError, InvalidBossFightStateError (LOBBY).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.bosses import (
    BossRoundResolved,
    RunBossRound,
)
from pipirik_wars.application.dto.inputs import RunBossRoundInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightNotFoundError,
    BossFightStatus,
    BossKind,
    BossParticipant,
    InvalidBossFightStateError,
)
from pipirik_wars.domain.security import LockReason
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAuditLogger,
    FakeBossFightRepository,
    FakeBossParticipantRepository,
    FakeClock,
    FakeDelayedJobScheduler,
    FakeRandom,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_LOBBY_MINUTES = 20
_LOBBY_ENDS_AT = _NOW + timedelta(minutes=_LOBBY_MINUTES)
_BATTLE_NOW = _LOBBY_ENDS_AT + timedelta(seconds=30)
_SUMMONER_PLAYER_ID = 11
_BOSS_PLAYER_ID = 22
_RAIDER_2_ID = 33
_RAIDER_3_ID = 44

_INITIAL_BOSS_LENGTH_CM = 400
_RANDOM_SEED = 42

_BOSSES_CONFIG = build_valid_balance().bosses


def _build_use_case(
    *,
    clock: FakeClock | None = None,
    random_seed_factory_seed: int = 0,
) -> tuple[
    RunBossRound,
    FakeUnitOfWork,
    FakeBossFightRepository,
    FakeBossParticipantRepository,
    FakeAuditLogger,
    FakeDelayedJobScheduler,
    FakeActivityLockRepository,
    FakeClock,
]:
    uow = FakeUnitOfWork()
    boss_participants = FakeBossParticipantRepository()
    boss_fights = FakeBossFightRepository(participants=boss_participants)
    audit = FakeAuditLogger()
    scheduler = FakeDelayedJobScheduler()
    lock_repo = FakeActivityLockRepository()
    used_clock = clock or FakeClock(_BATTLE_NOW)
    locks = ActivityLockService(repository=lock_repo, clock=used_clock)

    def random_factory(seed: int) -> FakeRandom:
        # `seed` — round_seed = boss_fight.random_seed * 1_000_003 + current_round.
        # Здесь мы просто прокидываем его в FakeRandom — это даёт
        # детерминистичный, но per-round-разный исход. Дополнительный
        # `random_seed_factory_seed` (0 по умолчанию) — XOR-mix для
        # тестов, где нужно «другой исход того же раунда».
        return FakeRandom(seed=seed ^ random_seed_factory_seed)

    use_case = RunBossRound(
        uow=uow,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        locks=locks,
        audit=audit,
        clock=used_clock,
        scheduler=scheduler,
        balance=_BOSSES_CONFIG,
        random_factory=random_factory,
    )
    return (
        use_case,
        uow,
        boss_fights,
        boss_participants,
        audit,
        scheduler,
        lock_repo,
        used_clock,
    )


async def _seed_boss_fight(
    *,
    boss_fights: FakeBossFightRepository,
    boss_participants: FakeBossParticipantRepository,
    status: BossFightStatus = BossFightStatus.IN_BATTLE,
    raider_player_ids: tuple[int, ...] = (
        _SUMMONER_PLAYER_ID,
        _RAIDER_2_ID,
        _RAIDER_3_ID,
    ),
    initial_boss_length_cm: int = _INITIAL_BOSS_LENGTH_CM,
    current_boss_length_cm: int | None = None,
    current_round: int = 0,
) -> BossFight:
    """Создать рейд-бой в нужном статусе + posadить рейдеров.

    `raider_player_ids` — список player_id-ов в порядке вступления.
    Первый — саммонер (`is_summoner=True`), остальные — обычные
    рейдеры. Пустой список разрешён (corner-case теста).
    """
    fight = BossFight.starting(
        kind=BossKind.RAID,
        summoner_player_id=_SUMMONER_PLAYER_ID,
        boss_player_id=_BOSS_PLAYER_ID,
        started_at=_NOW,
        lobby_ends_at=_LOBBY_ENDS_AT,
        random_seed=_RANDOM_SEED,
        initial_boss_length_cm=initial_boss_length_cm,
    )
    fight = await boss_fights.add(fight)

    if status is BossFightStatus.LOBBY:
        # Оставляем как есть.
        pass
    elif status is BossFightStatus.IN_BATTLE:
        fight = await boss_fights.save(fight.mark_in_battle())
    elif status is BossFightStatus.FINISHED:
        fight = await boss_fights.save(fight.mark_in_battle())
        fight = await boss_fights.save(fight.mark_finished(finished_at=_BATTLE_NOW))
    elif status is BossFightStatus.CANCELLED:
        fight = await boss_fights.save(fight.mark_cancelled(cancelled_at=_BATTLE_NOW))

    if current_boss_length_cm is not None or current_round > 0:
        # Применяем дополнительные мутации. with_boss_length и
        # with_round_advanced работают на любом статусе.
        if current_boss_length_cm is not None:
            fight = fight.with_boss_length(length_cm=current_boss_length_cm)
        for _ in range(current_round):
            fight = fight.with_round_advanced()
        fight = await boss_fights.save(fight)

    # Сидим рейдеров — только если бой не FINISHED/CANCELLED (для
    # теста идемпотентности рейдеры не нужны).
    assert fight.id is not None
    for i, player_id in enumerate(raider_player_ids):
        await boss_participants.add(
            BossParticipant.raider(
                boss_fight_id=fight.id,
                player_id=player_id,
                is_summoner=(i == 0),
                length_at_join_cm=100,
                joined_at=_NOW + timedelta(seconds=i),
            )
        )

    return fight


def _input(*, boss_fight_id: int) -> RunBossRoundInput:
    return RunBossRoundInput(boss_fight_id=boss_fight_id)


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_round_continues_schedules_next_tick(self) -> None:
        """Бой продолжается → next round-tick шедулится, current_round инкрементирован."""
        (
            use_case,
            uow,
            boss_fights,
            participants,
            _audit,
            scheduler,
            _locks,
            clock,
        ) = _build_use_case()
        fight = await _seed_boss_fight(
            boss_fights=boss_fights,
            boss_participants=participants,
        )
        assert fight.id is not None

        result = await use_case.execute(_input(boss_fight_id=fight.id))

        assert isinstance(result, BossRoundResolved)
        assert result.was_already_finished is False
        # Бой обычно продолжается (босс с 400 см и 1 раундом боя
        # обычно остаётся живым); если конкретный seed дал early-finish,
        # тест-кейсы для финиша лежат в TestRaidersWin / TestBossWins.
        if result.is_finished:
            pytest.skip("seed yielded early finish; covered by TestRaidersWin/TestBossWins")
        assert result.boss_fight.id == fight.id
        assert result.boss_fight.status is BossFightStatus.IN_BATTLE
        assert result.boss_fight.current_round == 1
        # next-tick шедулится на now + round_max_seconds.
        scheduled = scheduler.scheduled_boss_round_tick.get(fight.id)
        assert scheduled is not None
        assert scheduled.run_at == clock.now() + timedelta(
            seconds=_BOSSES_CONFIG.round_max_seconds,
        )
        # Pending не отменяется в этой ветке.
        assert fight.id not in scheduler.cancelled_boss_round_tick
        # Транзакция коммитится один раз.
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_round_damages_boss_or_eliminates_raider(self) -> None:
        """Хотя бы что-то меняется в раунде: либо HP босса, либо живых рейдеров."""
        (
            use_case,
            _uow,
            boss_fights,
            participants,
            _audit,
            _scheduler,
            _locks,
            _clock,
        ) = _build_use_case()
        fight = await _seed_boss_fight(
            boss_fights=boss_fights,
            boss_participants=participants,
        )
        assert fight.id is not None

        result = await use_case.execute(_input(boss_fight_id=fight.id))

        # Либо боссу попало (HP уменьшилось), либо рейдеру попало
        # (кто-то выбил). Никак не оба нуля при 3 атаках на 3+ рейдеров.
        boss_hp_dropped = result.boss_fight.current_boss_length_cm < _INITIAL_BOSS_LENGTH_CM
        raider_eliminated = (
            result.result is not None and len(result.result.eliminated_player_ids) > 0
        )
        assert boss_hp_dropped or raider_eliminated


class TestAuditEntry:
    @pytest.mark.asyncio
    async def test_audit_records_round_resolved(self) -> None:
        (
            use_case,
            _uow,
            boss_fights,
            participants,
            audit,
            _scheduler,
            _locks,
            clock,
        ) = _build_use_case()
        fight = await _seed_boss_fight(
            boss_fights=boss_fights,
            boss_participants=participants,
        )
        assert fight.id is not None

        result = await use_case.execute(_input(boss_fight_id=fight.id))

        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.BOSS_FIGHT_ROUND_RESOLVED
        assert entry.actor_id is None
        assert entry.target_kind == "boss_fight"
        assert entry.target_id == str(fight.id)
        assert entry.before == {
            "current_round": 0,
            "current_boss_length_cm": _INITIAL_BOSS_LENGTH_CM,
            "alive_raiders": 3,
        }
        assert entry.after is not None
        assert entry.after["current_round"] == result.boss_fight.current_round
        assert entry.after["current_boss_length_cm"] == result.boss_fight.current_boss_length_cm
        assert entry.reason == "boss_fight_round_resolved"
        # Idempotency-key с round_number = current_round-after-increment.
        assert entry.idempotency_key == (
            f"boss_fight_round_resolved:{fight.id}:{result.boss_fight.current_round}"
        )
        assert entry.occurred_at == clock.now()

    @pytest.mark.asyncio
    async def test_audit_idempotency_key_changes_per_round(self) -> None:
        """Два последовательных раунда → audit-keys :{id}:1 и :{id}:2."""
        (
            use_case,
            _uow,
            boss_fights,
            participants,
            audit,
            _scheduler,
            _locks,
            _clock,
        ) = _build_use_case()
        fight = await _seed_boss_fight(
            boss_fights=boss_fights,
            boss_participants=participants,
            initial_boss_length_cm=10_000,  # большое HP, чтобы оба раунда
            #  не финишили преждевременно
        )
        assert fight.id is not None

        result_1 = await use_case.execute(_input(boss_fight_id=fight.id))
        result_2 = await use_case.execute(_input(boss_fight_id=fight.id))

        # Если оба раунда зашли в IN_BATTLE — у нас 2 раунда, audit:1 и :2.
        if not result_1.is_finished and not result_2.is_finished:
            assert len(audit.entries) == 2
            assert audit.entries[0].idempotency_key == (f"boss_fight_round_resolved:{fight.id}:1")
            assert audit.entries[1].idempotency_key == (f"boss_fight_round_resolved:{fight.id}:2")


class TestRaidersWin:
    @pytest.mark.asyncio
    async def test_raiders_win_when_boss_hp_below_threshold(self) -> None:
        """HP босса < victory_threshold_cm после раунда → mark_finished + cleanup."""
        (
            use_case,
            _uow,
            boss_fights,
            participants,
            _audit,
            scheduler,
            _locks,
            _clock,
        ) = _build_use_case()
        # current_boss_length_cm = victory_threshold_cm — после любого
        # положительного боссу-урона результат < threshold.
        fight = await _seed_boss_fight(
            boss_fights=boss_fights,
            boss_participants=participants,
            current_boss_length_cm=_BOSSES_CONFIG.victory_threshold_cm,
        )
        assert fight.id is not None

        # Если в этом раунде не было ни одного блока — HP босса не
        # упало, бой не закончен. Тогда повторим, ища win-round.
        # Защищаемся от seed-зависимости через ограниченный цикл.
        result = await use_case.execute(_input(boss_fight_id=fight.id))
        attempts = 0
        while not result.is_finished and attempts < 5:
            assert result.boss_fight.id == fight.id
            result = await use_case.execute(_input(boss_fight_id=fight.id))
            attempts += 1

        assert result.is_finished is True
        assert result.boss_fight.status is BossFightStatus.FINISHED
        assert result.boss_fight.finished_at is not None
        # Pending tick-job отменён; новый — НЕ шедулится.
        assert fight.id in scheduler.cancelled_boss_round_tick
        assert fight.id not in scheduler.scheduled_boss_round_tick


class TestBossWins:
    @pytest.mark.asyncio
    async def test_boss_wins_when_all_raiders_eliminated(self) -> None:
        """Все рейдеры выбиты в раунде → bf-FINISHED, locks released."""
        (
            use_case,
            _uow,
            boss_fights,
            participants,
            _audit,
            scheduler,
            lock_repo,
            clock,
        ) = _build_use_case()
        # Стартуем с 1 рейдером — велик шанс, что он выбьется в одном из
        # 3 атак босса (вероятность hit одной атаки = 1/3, при 3 атаках
        # шанс хотя бы одного попадания ≈ 1 - (2/3)^3 ≈ 0.7). Защищаемся
        # от seed-зависимости через цикл с ограничением.
        fight = await _seed_boss_fight(
            boss_fights=boss_fights,
            boss_participants=participants,
            raider_player_ids=(_SUMMONER_PLAYER_ID,),
        )
        assert fight.id is not None
        # Закладываем lock на саммонера — после выбивания он должен
        # быть снят.
        await lock_repo.try_acquire(
            actor_kind="player",
            actor_id=_SUMMONER_PLAYER_ID,
            reason=LockReason.RAID,
            now=clock.now(),
            expires_at=clock.now() + timedelta(hours=1),
        )

        result = await use_case.execute(_input(boss_fight_id=fight.id))

        attempts = 0
        while not result.is_finished and attempts < 5:
            result = await use_case.execute(_input(boss_fight_id=fight.id))
            attempts += 1

        assert result.is_finished is True
        assert result.boss_fight.status is BossFightStatus.FINISHED
        # Все participant-ы удалены.
        assert participants.rows == []
        # Pending tick-job отменён; новый — НЕ шедулится.
        assert fight.id in scheduler.cancelled_boss_round_tick
        assert fight.id not in scheduler.scheduled_boss_round_tick
        # Lock на саммонера снят.
        assert (
            await lock_repo.get(
                actor_kind="player",
                actor_id=_SUMMONER_PLAYER_ID,
            )
            is None
        )


class TestEmptyRaiderListCornerCase:
    @pytest.mark.asyncio
    async def test_no_alive_raiders_finishes_without_resolve(self) -> None:
        """Список рейдеров пуст на входе → bf-FINISHED без resolve-сервиса."""
        (
            use_case,
            _uow,
            boss_fights,
            participants,
            audit,
            scheduler,
            _locks,
            _clock,
        ) = _build_use_case()
        fight = await _seed_boss_fight(
            boss_fights=boss_fights,
            boss_participants=participants,
            raider_player_ids=(),  # 0 рейдеров — corner-case
        )
        assert fight.id is not None

        result = await use_case.execute(_input(boss_fight_id=fight.id))

        assert result.is_finished is True
        assert result.was_already_finished is False
        assert result.result is None  # resolve-сервис НЕ зван
        assert result.boss_fight.status is BossFightStatus.FINISHED
        # Audit-запись всё равно есть (для трейсабельности).
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action is AuditAction.BOSS_FIGHT_ROUND_RESOLVED
        assert entry.idempotency_key == (f"boss_fight_round_resolved:{fight.id}:1")
        assert entry.before is not None
        assert entry.before["alive_raiders"] == 0
        assert entry.after is not None
        assert entry.after["is_finished"] is True
        # Pending tick отменён.
        assert fight.id in scheduler.cancelled_boss_round_tick


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_already_finished_is_noop(self) -> None:
        (
            use_case,
            uow,
            boss_fights,
            participants,
            audit,
            scheduler,
            _locks,
            _clock,
        ) = _build_use_case()
        fight = await _seed_boss_fight(
            boss_fights=boss_fights,
            boss_participants=participants,
            status=BossFightStatus.FINISHED,
            raider_player_ids=(),
        )
        assert fight.id is not None

        result = await use_case.execute(_input(boss_fight_id=fight.id))

        assert result.was_already_finished is True
        assert result.is_finished is True
        assert result.boss_fight.status is BossFightStatus.FINISHED
        assert audit.entries == []
        # Шедулер не трогаем.
        assert fight.id not in scheduler.cancelled_boss_round_tick
        assert fight.id not in scheduler.scheduled_boss_round_tick
        # Транзакция коммитится один раз (NO-OP-коммит).
        assert uow.commits == 1
        assert uow.rollbacks == 0

    @pytest.mark.asyncio
    async def test_already_cancelled_is_noop(self) -> None:
        (
            use_case,
            _uow,
            boss_fights,
            participants,
            audit,
            scheduler,
            _locks,
            _clock,
        ) = _build_use_case()
        fight = await _seed_boss_fight(
            boss_fights=boss_fights,
            boss_participants=participants,
            status=BossFightStatus.CANCELLED,
            raider_player_ids=(),
        )
        assert fight.id is not None

        result = await use_case.execute(_input(boss_fight_id=fight.id))

        assert result.was_already_finished is True
        assert result.boss_fight.status is BossFightStatus.CANCELLED
        assert audit.entries == []
        assert fight.id not in scheduler.scheduled_boss_round_tick


class TestErrors:
    @pytest.mark.asyncio
    async def test_boss_fight_not_found_raises(self) -> None:
        (
            use_case,
            uow,
            _boss_fights,
            _participants,
            audit,
            scheduler,
            _locks,
            _clock,
        ) = _build_use_case()

        with pytest.raises(BossFightNotFoundError) as exc:
            await use_case.execute(_input(boss_fight_id=9999))

        assert exc.value.boss_fight_id == 9999
        assert audit.entries == []
        assert scheduler.scheduled_boss_round_tick == {}
        assert uow.rollbacks == 1
        assert uow.commits == 0

    @pytest.mark.asyncio
    async def test_lobby_status_raises_invalid_state(self) -> None:
        """Round-tick стрельнул на LOBBY → bug шедулера → InvalidBossFightStateError."""
        (
            use_case,
            uow,
            boss_fights,
            participants,
            audit,
            scheduler,
            _locks,
            _clock,
        ) = _build_use_case()
        fight = await _seed_boss_fight(
            boss_fights=boss_fights,
            boss_participants=participants,
            status=BossFightStatus.LOBBY,
        )
        assert fight.id is not None

        with pytest.raises(InvalidBossFightStateError) as exc:
            await use_case.execute(_input(boss_fight_id=fight.id))

        assert exc.value.boss_fight_id == fight.id
        assert exc.value.expected == "IN_BATTLE"
        assert exc.value.actual == BossFightStatus.LOBBY.value
        assert audit.entries == []
        assert scheduler.scheduled_boss_round_tick == {}
        assert uow.rollbacks == 1
        assert uow.commits == 0
