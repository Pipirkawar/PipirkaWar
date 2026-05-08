"""Integration-тест частот scroll-drop-а на боссах (Спринт 3.3-D, D.12, ПД §3.3.6).

Сценарий: 100 рейдов × 5 рейдеров (= 500 независимых ролл-сэмплов
на каждый тип скролла) с детерминированным `FakeRandom`-фабрикой
и реальным `BossesConfig.scroll_drop` из `valid_balance_payload()`.

Проверяется:

* `regular`-частота укладывается в 3σ-границы (Bernoulli, `n=500`,
  `p=cfg.scroll_drop.regular`);
* `blessed`-частота укладывается в 3σ-границы (Bernoulli, `n=500`,
  `p=cfg.scroll_drop.blessed`) с аддитивным флором `±10` (на малых
  `p` σ маленькая, чистый 3σ слишком тесен и вызовет флапы);
* агрегаты в `BossFightFinished.scroll_drops` и в `audit.entries`
  (action=`SCROLL_DROP`) совпадают по числу записей — sanity-check
  на «ролл шёл per-player и пишется ровно один audit на скролл».

Цель — обнаружить регрессии в ролл-цепочке
`FinishBossFight._roll_scroll_drops`, ломающие распределение:

* перепутаны regular/blessed (`if cfg.regular...`/`if cfg.blessed...`);
* ролл идёт не на каждого рейдера (например, выходит из цикла);
* реюз одного RNG-инстанса между фитами (тогда каждый последующий
  фит «съедает» вторую половину предыдущего seed-а — частоты
  скачут).

Используется `FakeRandom(seed=s)` (на `random.Random` под капотом) с
разными per-fight seed-ами через `random_factory=lambda s: FakeRandom(seed=s)`.
Внутри use-case-а seed считается как `boss_fight.random_seed * 1_000_003 +
boss_fight.current_round`, что даёт независимые RNG-стримы на каждый
из 100 фитов. Тест полностью воспроизводим в CI (детерминированный
seed-набор `range(100)`), ни одного `time.time()`/`os.urandom`.

Уровень — application + audit + balance + RNG, без БД (для проверки
распределения SQLAlchemy не нужен). Аналогичный по архитектуре
`tests/unit/domain/enchantment/test_scroll_drops.py` (10 000 прогонов
PvE-локаций) — тот же `_bernoulli_bounds` приём, та же интуиция
«3σ + 10-флор от ожидаемого».
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.bosses import (
    BossFightFinished,
    FinishBossFight,
)
from pipirik_wars.application.dto.inputs import FinishBossFightInput
from pipirik_wars.application.progression import AddLength
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.bosses import (
    BossFight,
    BossKind,
    BossParticipant,
)
from pipirik_wars.domain.player import Length, Player, Username
from pipirik_wars.domain.shared.ports import AuditAction
from tests.fakes import (
    FakeActivityLockRepository,
    FakeAnticheatAdminAlerter,
    FakeAnticheatRepository,
    FakeAuditLogger,
    FakeBalanceConfig,
    FakeBossFightRepository,
    FakeBossParticipantRepository,
    FakeClock,
    FakeDelayedJobScheduler,
    FakeIdempotencyKey,
    FakePlayerRepository,
    FakeRandom,
    FakeUnitOfWork,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NUM_FIGHTS = 100
_RAIDERS_PER_FIGHT = 5
_TOTAL_TRIALS = _NUM_FIGHTS * _RAIDERS_PER_FIGHT  # 500 на каждый тип скролла

_NOW = datetime(2026, 5, 8, 14, 0, tzinfo=UTC)
_LOBBY_MINUTES = 20
_LOBBY_ENDS_AT = _NOW - timedelta(minutes=_LOBBY_MINUTES)
_STARTED = _NOW - timedelta(hours=2)
_INITIAL_BOSS_LENGTH_CM = 400

_BOSS_TG_BASE = 1_000
_RAIDER_TG_BASE = 10_000
"""Уникальные tg_id-ы: `_BOSS_TG_BASE + fight_idx` для босса,
`_RAIDER_TG_BASE + fight_idx * 10 + raider_idx` для рейдеров."""


def _bernoulli_bounds(p: float, *, n: int = _TOTAL_TRIALS) -> tuple[float, float]:
    """3σ-bounds на число успехов в `n` прогонах Bernoulli с шансом `p`.

    Аддитивный флор `±10` нужен для малых `p` (например, `blessed=0.005`,
    `n=500` ⇒ `expected=2.5`, `σ≈1.58`, чистый 3σ-bound ≈ `[-2.2, 7.2]`
    — слишком узко, тест флапает на pinned seed-ах). 10-флор делает
    нижнюю границу 0-clamp-нутой и расширяет верхнюю до ~12, что
    оставляет запас на стохастику без потери чувствительности к
    регрессиям (например, удвоенный `blessed`-шанс уйдёт за границу).
    """
    expected = p * n
    sigma = math.sqrt(n * p * (1 - p))
    delta = max(3 * sigma, 10.0)
    return expected - delta, expected + delta


async def _seed_player(
    players: FakePlayerRepository,
    *,
    tg_id: int,
    username: str,
    length_cm: int,
) -> Player:
    player = await players.add(
        Player.new(tg_id=tg_id, username=Username(value=username), now=_STARTED),
    )
    if length_cm != player.length.cm:
        player = await players.save(
            player.with_length(Length(cm=length_cm), now=_STARTED),
        )
    assert player.id is not None
    return player


async def _seed_fight_in_battle(
    *,
    boss_fights: FakeBossFightRepository,
    boss_participants: FakeBossParticipantRepository,
    summoner_player_id: int,
    boss_player_id: int,
    raider_player_ids: tuple[int, ...],
    random_seed: int,
    raider_length_at_join_cm: int,
    victory_threshold_cm: int,
) -> BossFight:
    """Создать `BossFight.IN_BATTLE` с force-ed-ным `current_boss_length_cm`-ом
    в `victory_threshold_cm - 1` (то есть гарантированная победа рейдеров,
    что и активирует `_roll_scroll_drops`)."""
    fight = BossFight.starting(
        kind=BossKind.RAID,
        summoner_player_id=summoner_player_id,
        boss_player_id=boss_player_id,
        started_at=_NOW - timedelta(minutes=_LOBBY_MINUTES + 5),
        lobby_ends_at=_LOBBY_ENDS_AT,
        random_seed=random_seed,
        initial_boss_length_cm=_INITIAL_BOSS_LENGTH_CM,
    )
    fight = await boss_fights.add(fight)
    fight = await boss_fights.save(fight.mark_in_battle())
    fight = fight.with_boss_length(length_cm=victory_threshold_cm - 1)
    fight = await boss_fights.save(fight)
    assert fight.id is not None
    for i, player_id in enumerate(raider_player_ids):
        await boss_participants.add(
            BossParticipant.raider(
                boss_fight_id=fight.id,
                player_id=player_id,
                is_summoner=(i == 0),
                length_at_join_cm=raider_length_at_join_cm,
                joined_at=_NOW + timedelta(seconds=i),
            )
        )
    return fight


def _build_use_case(
    *,
    uow: FakeUnitOfWork,
    players: FakePlayerRepository,
    boss_fights: FakeBossFightRepository,
    boss_participants: FakeBossParticipantRepository,
    audit: FakeAuditLogger,
    clock: FakeClock,
    lock_repo: FakeActivityLockRepository,
    scheduler: FakeDelayedJobScheduler,
) -> FinishBossFight:
    """Собрать `FinishBossFight` со всеми реальными application-зависимостями.

    Используется реальный `AddLength` length-granter (с
    `FakeAnticheatRepository`-кэпом + `FakeAnticheatAdminAlerter`-ом,
    как в unit-тестах). Это тот же DI-граф, что и production —
    тест проверяет всю application-сборку на стат-распределении.

    `random_factory=lambda s: FakeRandom(seed=s)` — пробрасывает в RNG
    реальный seed, который use-case считает как
    `boss_fight.random_seed * 1_000_003 + boss_fight.current_round`,
    что даёт независимые streams на каждый фит.
    """
    locks = ActivityLockService(repository=lock_repo, clock=clock)
    balance_full = FakeBalanceConfig(build_valid_balance())
    length_granter = AddLength(
        uow=uow,
        players=players,
        anticheat=FakeAnticheatRepository(),
        audit=audit,
        balance=balance_full,
        clock=clock,
        idempotency=FakeIdempotencyKey(),
        admin_alerter=FakeAnticheatAdminAlerter(),
    )
    return FinishBossFight(
        uow=uow,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        players=players,
        length_granter=length_granter,
        locks=locks,
        audit=audit,
        clock=clock,
        scheduler=scheduler,
        balance=balance_full.get().bosses,
        random_factory=lambda s: FakeRandom(seed=s),
    )


@pytest.mark.asyncio
async def test_scroll_drop_frequencies_within_bernoulli_bounds() -> None:
    """100 рейдов × 5 рейдеров: regular/blessed-частоты в 3σ от cfg.scroll_drop."""
    balance = build_valid_balance()
    cfg_scroll = balance.bosses.scroll_drop
    victory_threshold_cm = balance.bosses.victory_threshold_cm

    uow = FakeUnitOfWork()
    players = FakePlayerRepository()
    boss_participants = FakeBossParticipantRepository()
    boss_fights = FakeBossFightRepository(participants=boss_participants)
    audit = FakeAuditLogger()
    clock = FakeClock(_NOW)
    lock_repo = FakeActivityLockRepository()
    scheduler = FakeDelayedJobScheduler()

    use_case = _build_use_case(
        uow=uow,
        players=players,
        boss_fights=boss_fights,
        boss_participants=boss_participants,
        audit=audit,
        clock=clock,
        lock_repo=lock_repo,
        scheduler=scheduler,
    )

    regular_count = 0
    blessed_count = 0
    total_drops = 0

    for fight_idx in range(_NUM_FIGHTS):
        # Босс с большим length-ом — чтобы revoke не упёрся в floor.
        boss = await _seed_player(
            players,
            tg_id=_BOSS_TG_BASE + fight_idx,
            username=f"boss{fight_idx}",
            length_cm=_INITIAL_BOSS_LENGTH_CM + 100,
        )
        raiders: list[Player] = []
        for raider_idx in range(_RAIDERS_PER_FIGHT):
            raider = await _seed_player(
                players,
                tg_id=_RAIDER_TG_BASE + fight_idx * 10 + raider_idx,
                username=f"r{fight_idx}_{raider_idx}",
                length_cm=50,
            )
            raiders.append(raider)
        assert boss.id is not None
        raider_ids = tuple(r.id for r in raiders if r.id is not None)
        assert len(raider_ids) == _RAIDERS_PER_FIGHT

        fight = await _seed_fight_in_battle(
            boss_fights=boss_fights,
            boss_participants=boss_participants,
            summoner_player_id=raider_ids[0],
            boss_player_id=boss.id,
            raider_player_ids=raider_ids,
            random_seed=fight_idx,
            raider_length_at_join_cm=50,
            victory_threshold_cm=victory_threshold_cm,
        )
        assert fight.id is not None

        result = await use_case.execute(FinishBossFightInput(boss_fight_id=fight.id))

        assert isinstance(result, BossFightFinished)
        assert result.raiders_won is True, (
            f"fight_idx={fight_idx}: ожидалась победа рейдеров "
            f"(current_boss_length_cm={victory_threshold_cm - 1} "
            f"< victory_threshold_cm={victory_threshold_cm})"
        )

        for drop in result.scroll_drops:
            if drop.blessed:
                blessed_count += 1
            else:
                regular_count += 1
            total_drops += 1

    # Sanity-check агрегатов: число `SCROLL_DROP`-аудит-записей совпадает
    # с числом `BossScrollDrop`-ов в результатах (per-player ролл, ровно
    # один audit на скролл).
    audit_scroll_count = sum(
        1 for entry in audit.entries if entry.action is AuditAction.SCROLL_DROP
    )
    assert audit_scroll_count == total_drops, (
        f"audit_scroll_count={audit_scroll_count} != total_drops={total_drops} "
        f"(ролл должен писать ровно один audit на каждый скролл)"
    )

    # Регуляр: 500 трайлов × p=0.05 → ~25, 3σ-bounds ≈ [10, 40].
    p_regular = cfg_scroll.regular
    lo_r, hi_r = _bernoulli_bounds(p_regular)
    assert lo_r <= regular_count <= hi_r, (
        f"regular_count={regular_count} not in [{lo_r:.1f}, {hi_r:.1f}] "
        f"(expected ~{p_regular * _TOTAL_TRIALS:.1f}, p={p_regular}, n={_TOTAL_TRIALS})"
    )

    # Блессед: 500 трайлов × p=0.005 → ~2.5, σ маленькая → 10-флор
    # расширяет до ~[0, 12].
    p_blessed = cfg_scroll.blessed
    lo_b, hi_b = _bernoulli_bounds(p_blessed)
    assert lo_b <= blessed_count <= hi_b, (
        f"blessed_count={blessed_count} not in [{lo_b:.1f}, {hi_b:.1f}] "
        f"(expected ~{p_blessed * _TOTAL_TRIALS:.1f}, p={p_blessed}, n={_TOTAL_TRIALS})"
    )


@pytest.mark.asyncio
async def test_scroll_drops_independent_per_fight() -> None:
    """Sanity: число scroll-drop-аудитов масштабируется ~линейно с числом фитов.

    Проверяет, что не происходит «накопления» (один и тот же RNG-инстанс
    между фитами не съедает уникальные ролл-результаты, давая, например,
    одинаковую частоту во всех фитах).

    На 10 фитах ожидаем ≥ 1 регулярного дропа (p=0.05, n=50, P(0)≈0.077).
    На 100 фитах — заведомо больше; коэффициент роста не должен быть
    ровно 10× (на маленьких числах разброс), но > 1.5× — обязан.
    """
    balance = build_valid_balance()
    victory_threshold_cm = balance.bosses.victory_threshold_cm

    async def _run(num_fights: int) -> int:
        uow = FakeUnitOfWork()
        players = FakePlayerRepository()
        boss_participants = FakeBossParticipantRepository()
        boss_fights = FakeBossFightRepository(participants=boss_participants)
        audit = FakeAuditLogger()
        clock = FakeClock(_NOW)
        lock_repo = FakeActivityLockRepository()
        scheduler = FakeDelayedJobScheduler()

        use_case = _build_use_case(
            uow=uow,
            players=players,
            boss_fights=boss_fights,
            boss_participants=boss_participants,
            audit=audit,
            clock=clock,
            lock_repo=lock_repo,
            scheduler=scheduler,
        )

        regular_total = 0
        for fight_idx in range(num_fights):
            boss = await _seed_player(
                players,
                tg_id=_BOSS_TG_BASE + fight_idx,
                username=f"boss{fight_idx}",
                length_cm=_INITIAL_BOSS_LENGTH_CM + 100,
            )
            raider_ids: list[int] = []
            for raider_idx in range(_RAIDERS_PER_FIGHT):
                raider = await _seed_player(
                    players,
                    tg_id=_RAIDER_TG_BASE + fight_idx * 10 + raider_idx,
                    username=f"r{fight_idx}_{raider_idx}",
                    length_cm=50,
                )
                assert raider.id is not None
                raider_ids.append(raider.id)
            assert boss.id is not None
            fight = await _seed_fight_in_battle(
                boss_fights=boss_fights,
                boss_participants=boss_participants,
                summoner_player_id=raider_ids[0],
                boss_player_id=boss.id,
                raider_player_ids=tuple(raider_ids),
                random_seed=fight_idx,
                raider_length_at_join_cm=50,
                victory_threshold_cm=victory_threshold_cm,
            )
            assert fight.id is not None
            result = await use_case.execute(
                FinishBossFightInput(boss_fight_id=fight.id),
            )
            for drop in result.scroll_drops:
                if not drop.blessed:
                    regular_total += 1
        return regular_total

    short_run = await _run(10)
    long_run = await _run(_NUM_FIGHTS)

    # `short_run` может быть малым (на 10 × 5 = 50 трайлов p=0.05 ⇒ ~2.5);
    # `long_run` — около 25; разница > 1.5× — гарантирует масштабирование.
    assert long_run >= max(int(short_run * 1.5), short_run + 5), (
        f"long_run={long_run} (n=100) должно заметно превышать "
        f"short_run={short_run} (n=10); если они близки — между фитами "
        f"течёт один RNG-стрим вместо независимых per-fight."
    )
