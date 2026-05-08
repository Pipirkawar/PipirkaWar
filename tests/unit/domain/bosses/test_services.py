"""Тесты `resolve_boss_round` (Спринт 3.3-C, ГДД §10.4–§10.5).

Фокусы:

* Детерминированность: один и тот же seed `FakeRandom` → один и тот же
  результат на любом колчестве прогонов (нужно для аудит-replay).
* Граничные кейсы: 1 рейдер, 5 рейдеров, пустой `alive_raiders`
  (ValueError), все атаки заблокированы / все пробили блок.
* Структура `BossRoundResult`:
  * `boss_damage_taken_cm` ∈ {0, base_damage_cm, 2×base_damage_cm,
    3×base_damage_cm} (3 атаки, каждая либо +base, либо 0).
  * `eliminated_player_ids` подмножество `alive_raiders.player_id`-ов.
  * Согласованность `eliminated_player_ids` с `raider_outcomes`
    (BossRoundResult.__post_init__).
* Распределение: на 200 симуляциях с разными seed-ами при «честных»
  стартовых условиях (5 рейдеров) разные исходы (выбытий) случаются
  достаточно часто — подтверждаем, что движок не вырожден.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from pipirik_wars.domain.balance.config import BossesConfig
from pipirik_wars.domain.bosses import (
    BossFight,
    BossKind,
    BossParticipant,
    BossRaiderRoundOutcome,
    BossRoundResult,
    resolve_boss_round,
)
from tests.fakes.random import FakeRandom
from tests.unit.domain.balance.factories import build_valid_balance


def _now() -> datetime:
    return datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)


def _balance() -> BossesConfig:
    return build_valid_balance().bosses


def _make_boss_fight(*, current_round: int = 0) -> BossFight:
    started = _now()
    fight = BossFight.starting(
        kind=BossKind.RAID,
        summoner_player_id=1001,
        boss_player_id=2002,
        started_at=started,
        lobby_ends_at=datetime(2026, 5, 7, 12, 20, 0, tzinfo=UTC),
        random_seed=2026_05_08,
        initial_boss_length_cm=50,
    ).mark_in_battle()
    for _ in range(current_round):
        fight = fight.with_round_advanced()
    return fight


def _raider(*, player_id: int, is_summoner: bool = False) -> BossParticipant:
    return BossParticipant.raider(
        boss_fight_id=1,
        player_id=player_id,
        is_summoner=is_summoner,
        length_at_join_cm=30,
        joined_at=_now(),
    )


def _outcome_by_player(result: BossRoundResult, player_id: int) -> BossRaiderRoundOutcome:
    matches = [o for o in result.raider_outcomes if o.participant.player_id == player_id]
    if len(matches) != 1:
        raise AssertionError(
            f"Expected exactly 1 outcome for player {player_id}, got {len(matches)}"
        )
    return matches[0]


# ============================================================================
# Базовый happy-path: 5 рейдеров, фиксированный seed.
# ============================================================================


def test_resolve_boss_round_deterministic_same_seed_same_result() -> None:
    """Один и тот же seed → одинаковый исход на двух прогонах.

    Критичный инвариант для post-mortem аудита (boss_fight.random_seed).
    """
    fight = _make_boss_fight()
    raiders = [_raider(player_id=10 + i, is_summoner=(i == 0)) for i in range(5)]
    balance = _balance()

    result_a = resolve_boss_round(
        boss_fight=fight,
        alive_raiders=raiders,
        balance=balance,
        random=FakeRandom(seed=42),
    )
    result_b = resolve_boss_round(
        boss_fight=fight,
        alive_raiders=raiders,
        balance=balance,
        random=FakeRandom(seed=42),
    )

    assert result_a == result_b


def test_resolve_boss_round_different_seeds_can_differ() -> None:
    """Разные seed-ы → как правило разный исход (анти-вырождение).

    Берём 10 разных seed-ов и проверяем, что хотя бы 2 разных исхода
    встретились — это исключает баг «всегда одинаковый результат».
    """
    fight = _make_boss_fight()
    raiders = [_raider(player_id=10 + i, is_summoner=(i == 0)) for i in range(5)]
    balance = _balance()

    seen_results: set[BossRoundResult] = set()
    for seed in range(10):
        result = resolve_boss_round(
            boss_fight=fight,
            alive_raiders=raiders,
            balance=balance,
            random=FakeRandom(seed=seed),
        )
        seen_results.add(result)

    assert len(seen_results) >= 2, (
        f"Engine looks degenerate: 10 seeds → {len(seen_results)} unique results"
    )


def test_resolve_boss_round_returns_outcome_per_alive_raider() -> None:
    """`raider_outcomes` имеет ровно по одному элементу на `alive_raiders`."""
    fight = _make_boss_fight()
    raiders = [_raider(player_id=10 + i, is_summoner=(i == 0)) for i in range(5)]

    result = resolve_boss_round(
        boss_fight=fight,
        alive_raiders=raiders,
        balance=_balance(),
        random=FakeRandom(seed=1),
    )

    assert len(result.raider_outcomes) == 5
    raider_ids = {r.player_id for r in raiders}
    outcome_ids = {o.participant.player_id for o in result.raider_outcomes}
    assert outcome_ids == raider_ids


def test_resolve_boss_round_preserves_alive_raiders_order() -> None:
    """`raider_outcomes` идёт в том же порядке, что и `alive_raiders`."""
    fight = _make_boss_fight()
    raiders = [_raider(player_id=99 - i, is_summoner=(i == 0)) for i in range(5)]

    result = resolve_boss_round(
        boss_fight=fight,
        alive_raiders=raiders,
        balance=_balance(),
        random=FakeRandom(seed=7),
    )

    expected = [r.player_id for r in raiders]
    actual = [o.participant.player_id for o in result.raider_outcomes]
    assert actual == expected


# ============================================================================
# Граничные кейсы.
# ============================================================================


def test_resolve_boss_round_empty_raiders_raises() -> None:
    """Пустой `alive_raiders` — `ValueError` (caller must call `FinishBossFight`)."""
    fight = _make_boss_fight()

    with pytest.raises(ValueError, match="alive_raiders is empty"):
        resolve_boss_round(
            boss_fight=fight,
            alive_raiders=[],
            balance=_balance(),
            random=FakeRandom(seed=0),
        )


def test_resolve_boss_round_single_raider_eliminated() -> None:
    """1 рейдер, который выбыл — `eliminated_player_ids = (его_id,)`,
    `boss_damage_taken_cm` ≤ 2×base_damage_cm (макс. 2 атаки прошли в блок
    до того, как рейдер выбил, но возможно и 0 атак ушло в блок —
    тогда выбывание на 1-й же атаке).

    Запускаем 50 разных seed-ов чтобы поймать кейс «рейдер выбил».
    """
    fight = _make_boss_fight()
    base_damage_cm = _balance().base_damage_cm

    eliminated_seen = False
    for seed in range(50):
        result = resolve_boss_round(
            boss_fight=fight,
            alive_raiders=[_raider(player_id=42, is_summoner=True)],
            balance=_balance(),
            random=FakeRandom(seed=seed),
        )
        # Boss damage не превышает 3×base (3 атаки максимум).
        assert 0 <= result.boss_damage_taken_cm <= 3 * base_damage_cm
        # Все outcome-ы — на одного рейдера.
        assert len(result.raider_outcomes) == 1
        outcome = result.raider_outcomes[0]
        assert outcome.participant.player_id == 42
        if outcome.is_eliminated:
            eliminated_seen = True
            assert outcome.damage_taken_cm == base_damage_cm
            assert result.eliminated_player_ids == (42,)
        else:
            assert outcome.damage_taken_cm == 0
            assert result.eliminated_player_ids == ()

    assert eliminated_seen, "After 50 seeds with 1 raider expected at least 1 elimination"


def test_resolve_boss_round_all_three_attacks_blocked_max_boss_damage() -> None:
    """Если рейдер заблокировал все 3 атаки, `boss_damage_taken_cm = 3×base_damage_cm`.

    Найдём такой seed экспериментально (берём первый seed, при котором
    все 3 атаки не пробили блок 1 рейдера).
    """
    fight = _make_boss_fight()
    base_damage_cm = _balance().base_damage_cm

    found_seed: int | None = None
    for seed in range(100):
        result = resolve_boss_round(
            boss_fight=fight,
            alive_raiders=[_raider(player_id=42, is_summoner=True)],
            balance=_balance(),
            random=FakeRandom(seed=seed),
        )
        if result.boss_damage_taken_cm == 3 * base_damage_cm:
            found_seed = seed
            break

    assert found_seed is not None, (
        "Не нашли seed-а, при котором все 3 атаки заблокированы "
        "(подозрительно: блок-rate должен быть ~2/3, P=8/27 ≈ 30%)"
    )
    result = resolve_boss_round(
        boss_fight=fight,
        alive_raiders=[_raider(player_id=42, is_summoner=True)],
        balance=_balance(),
        random=FakeRandom(seed=found_seed),
    )
    assert result.boss_damage_taken_cm == 3 * base_damage_cm
    assert result.eliminated_player_ids == ()
    assert result.raider_outcomes[0].is_eliminated is False
    assert result.raider_outcomes[0].damage_taken_cm == 0


def test_resolve_boss_round_eliminated_ids_subset_of_raiders() -> None:
    """`eliminated_player_ids` — всегда подмножество входных рейдеров."""
    fight = _make_boss_fight()
    raiders = [_raider(player_id=10 + i) for i in range(5)]
    raider_ids = {r.player_id for r in raiders}

    for seed in range(30):
        result = resolve_boss_round(
            boss_fight=fight,
            alive_raiders=raiders,
            balance=_balance(),
            random=FakeRandom(seed=seed),
        )
        for pid in result.eliminated_player_ids:
            assert pid in raider_ids


def test_resolve_boss_round_eliminated_count_at_most_three() -> None:
    """Не более 3 выбывших за раунд (максимум 3 атаки босса)."""
    fight = _make_boss_fight()
    raiders = [_raider(player_id=10 + i) for i in range(10)]

    for seed in range(50):
        result = resolve_boss_round(
            boss_fight=fight,
            alive_raiders=raiders,
            balance=_balance(),
            random=FakeRandom(seed=seed),
        )
        assert len(result.eliminated_player_ids) <= 3


def test_resolve_boss_round_eliminated_count_at_most_alive_raiders() -> None:
    """Не более `len(alive_raiders)` выбывших (если 2 рейдера, то ≤ 2)."""
    fight = _make_boss_fight()
    raiders = [_raider(player_id=10 + i) for i in range(2)]

    for seed in range(50):
        result = resolve_boss_round(
            boss_fight=fight,
            alive_raiders=raiders,
            balance=_balance(),
            random=FakeRandom(seed=seed),
        )
        assert len(result.eliminated_player_ids) <= 2


# ============================================================================
# Согласованность `BossRoundResult.__post_init__`.
# ============================================================================


def test_boss_round_result_post_init_validates_eliminated_consistency() -> None:
    """`eliminated_player_ids` должен совпадать с подмножеством outcome-ов
    с `is_eliminated=True` в том же порядке."""
    raider = _raider(player_id=10)
    outcome = BossRaiderRoundOutcome(
        participant=raider,
        is_eliminated=True,
        damage_taken_cm=5,
    )

    # Согласованный кейс — OK.
    BossRoundResult(
        raider_outcomes=(outcome,),
        boss_damage_taken_cm=0,
        eliminated_player_ids=(10,),
    )

    # Inconsistent: eliminated_ids пуст, а outcome — eliminated.
    with pytest.raises(ValueError, match="inconsistent"):
        BossRoundResult(
            raider_outcomes=(outcome,),
            boss_damage_taken_cm=0,
            eliminated_player_ids=(),
        )

    # Inconsistent: eliminated_ids содержит чужой id.
    with pytest.raises(ValueError, match="inconsistent"):
        BossRoundResult(
            raider_outcomes=(outcome,),
            boss_damage_taken_cm=0,
            eliminated_player_ids=(99,),
        )


def test_boss_round_result_post_init_validates_negative_boss_damage() -> None:
    raider = _raider(player_id=10)
    outcome = BossRaiderRoundOutcome(participant=raider, is_eliminated=False, damage_taken_cm=0)
    with pytest.raises(ValueError, match="boss_damage_taken_cm"):
        BossRoundResult(
            raider_outcomes=(outcome,),
            boss_damage_taken_cm=-1,
            eliminated_player_ids=(),
        )


def test_boss_raider_round_outcome_validates_is_eliminated_implies_damage() -> None:
    """`is_eliminated=True` требует `damage_taken_cm > 0`."""
    raider = _raider(player_id=10)
    with pytest.raises(ValueError, match="is_eliminated=True"):
        BossRaiderRoundOutcome(participant=raider, is_eliminated=True, damage_taken_cm=0)


def test_boss_raider_round_outcome_validates_alive_implies_no_damage() -> None:
    """`is_eliminated=False` требует `damage_taken_cm == 0`."""
    raider = _raider(player_id=10)
    with pytest.raises(ValueError, match="is_eliminated=False"):
        BossRaiderRoundOutcome(participant=raider, is_eliminated=False, damage_taken_cm=5)


def test_boss_raider_round_outcome_validates_negative_damage() -> None:
    raider = _raider(player_id=10)
    with pytest.raises(ValueError, match="damage_taken_cm"):
        BossRaiderRoundOutcome(participant=raider, is_eliminated=True, damage_taken_cm=-5)


# ============================================================================
# Структурные инварианты результата.
# ============================================================================


def test_resolve_boss_round_boss_damage_is_multiple_of_base() -> None:
    """`boss_damage_taken_cm` всегда кратен `base_damage_cm`."""
    fight = _make_boss_fight()
    raiders = [_raider(player_id=10 + i) for i in range(5)]
    base_damage_cm = _balance().base_damage_cm

    for seed in range(30):
        result = resolve_boss_round(
            boss_fight=fight,
            alive_raiders=raiders,
            balance=_balance(),
            random=FakeRandom(seed=seed),
        )
        assert result.boss_damage_taken_cm % base_damage_cm == 0


def test_resolve_boss_round_eliminated_outcome_damage_equals_base() -> None:
    """Каждый выбывший получает ровно `base_damage_cm` (не больше, не меньше)."""
    fight = _make_boss_fight()
    raiders = [_raider(player_id=10 + i) for i in range(5)]
    base_damage_cm = _balance().base_damage_cm

    for seed in range(30):
        result = resolve_boss_round(
            boss_fight=fight,
            alive_raiders=raiders,
            balance=_balance(),
            random=FakeRandom(seed=seed),
        )
        for outcome in result.raider_outcomes:
            if outcome.is_eliminated:
                assert outcome.damage_taken_cm == base_damage_cm
            else:
                assert outcome.damage_taken_cm == 0


def test_resolve_boss_round_eliminated_outcomes_unique_player_ids() -> None:
    """Каждый рейдер — максимум один outcome (eliminated или нет)."""
    fight = _make_boss_fight()
    raiders = [_raider(player_id=10 + i) for i in range(5)]

    result = resolve_boss_round(
        boss_fight=fight,
        alive_raiders=raiders,
        balance=_balance(),
        random=FakeRandom(seed=99),
    )

    outcome_ids = [o.participant.player_id for o in result.raider_outcomes]
    assert len(outcome_ids) == len(set(outcome_ids))

    eliminated_ids = list(result.eliminated_player_ids)
    assert len(eliminated_ids) == len(set(eliminated_ids))


def test_resolve_boss_round_attack_count_invariant() -> None:
    """Сумма «boss damage / base + кол-во выбывших» = 3 в наилучшем случае.

    Каждая из 3 атак босса либо +base боссу (block), либо +1 выбывший
    (hit). Кроме защитного случая «все рейдеры выбыли в середине
    раунда» — тогда оставшиеся атаки бьют по воздуху.

    Здесь проверяем при 5 рейдерах (никогда не закончатся за 3 атаки),
    что инвариант `(boss_damage / base) + len(eliminated) == 3` строго.
    """
    fight = _make_boss_fight()
    raiders = [_raider(player_id=10 + i) for i in range(5)]
    base_damage_cm = _balance().base_damage_cm

    for seed in range(30):
        result = resolve_boss_round(
            boss_fight=fight,
            alive_raiders=raiders,
            balance=_balance(),
            random=FakeRandom(seed=seed),
        )
        blocks = result.boss_damage_taken_cm // base_damage_cm
        hits = len(result.eliminated_player_ids)
        assert blocks + hits == 3, (
            f"seed={seed}: blocks={blocks} + hits={hits} != 3 "
            f"(boss_damage={result.boss_damage_taken_cm}, eliminated={result.eliminated_player_ids})"
        )


# ============================================================================
# Распределение (анти-вырождение).
# ============================================================================


def test_resolve_boss_round_distribution_5_raiders_200_seeds() -> None:
    """200 симуляций с разными seed-ами — должны быть видны разные исходы.

    На 5 рейдерах:
    * Hit-rate ≈ 1/3 на атаку (раидер блокирует 2/3).
    * Ожидаемое eliminated_count ≈ 3 × 1/3 = 1 рейдер за раунд.
    * Ожидаемое boss_damage ≈ 3 × 2/3 × base = 10 см за раунд.

    Проверяем:
    * eliminated_count в `{0, 1, 2, 3}` встречаются хотя бы по 5 раз
      каждое (исключение — 0, может быть только при удачных всех блоков).
    * boss_damage_cm в `{0, base, 2×base, 3×base}` тоже встречаются.
    """
    fight = _make_boss_fight()
    raiders = [_raider(player_id=10 + i) for i in range(5)]
    base_damage_cm = _balance().base_damage_cm

    eliminated_count_freq: dict[int, int] = {}
    boss_damage_freq: dict[int, int] = {}

    for seed in range(200):
        result = resolve_boss_round(
            boss_fight=fight,
            alive_raiders=raiders,
            balance=_balance(),
            random=FakeRandom(seed=seed),
        )
        ec = len(result.eliminated_player_ids)
        eliminated_count_freq[ec] = eliminated_count_freq.get(ec, 0) + 1
        bd = result.boss_damage_taken_cm
        boss_damage_freq[bd] = boss_damage_freq.get(bd, 0) + 1

    # Должны быть видны >=2 разных значений eliminated_count и boss_damage.
    assert len(eliminated_count_freq) >= 2
    assert len(boss_damage_freq) >= 2

    # Никогда не должно быть >3 выбытий или >3×base урона.
    for ec in eliminated_count_freq:
        assert 0 <= ec <= 3
    for bd in boss_damage_freq:
        assert 0 <= bd <= 3 * base_damage_cm
        assert bd % base_damage_cm == 0


def test_resolve_boss_round_round_advanced_does_not_affect_resolution() -> None:
    """Текущий `boss_fight.current_round` не используется в resolve-е
    (это инкапсулировано в IRandom seed-е use-case-ом).

    Мы создаём 2 fight-а — один на раунде 0, другой на раунде 5 — и
    с одинаковым `random` они должны дать тот же результат.
    """
    fight_round_0 = _make_boss_fight(current_round=0)
    fight_round_5 = _make_boss_fight(current_round=5)
    raiders = [_raider(player_id=10 + i) for i in range(5)]

    result_0 = resolve_boss_round(
        boss_fight=fight_round_0,
        alive_raiders=raiders,
        balance=_balance(),
        random=FakeRandom(seed=42),
    )
    result_5 = resolve_boss_round(
        boss_fight=fight_round_5,
        alive_raiders=raiders,
        balance=_balance(),
        random=FakeRandom(seed=42),
    )

    assert result_0 == result_5


# ============================================================================
# Параметризованные кейсы (разные размеры пула, разные seed-ы).
# ============================================================================


@pytest.mark.parametrize("num_raiders", [1, 2, 3, 5, 10, 20])
def test_resolve_boss_round_various_raider_counts(num_raiders: int) -> None:
    """Работает для разного числа рейдеров без исключений."""
    fight = _make_boss_fight()
    raiders: Sequence[BossParticipant] = [
        _raider(player_id=100 + i, is_summoner=(i == 0)) for i in range(num_raiders)
    ]

    result = resolve_boss_round(
        boss_fight=fight,
        alive_raiders=raiders,
        balance=_balance(),
        random=FakeRandom(seed=num_raiders),
    )
    assert len(result.raider_outcomes) == num_raiders
    assert all(
        o.participant.player_id in {r.player_id for r in raiders} for o in result.raider_outcomes
    )


@pytest.mark.parametrize("seed", [0, 1, 42, 99, 12345])
def test_resolve_boss_round_invariants_across_seeds(seed: int) -> None:
    """Инварианты держатся на любом seed-е."""
    fight = _make_boss_fight()
    raiders = [_raider(player_id=10 + i) for i in range(5)]
    balance = _balance()

    result = resolve_boss_round(
        boss_fight=fight,
        alive_raiders=raiders,
        balance=balance,
        random=FakeRandom(seed=seed),
    )

    # Ровно `len(alive_raiders)` outcome-ов.
    assert len(result.raider_outcomes) == len(raiders)
    # boss_damage_cm кратен base.
    assert result.boss_damage_taken_cm % balance.base_damage_cm == 0
    # boss_damage_cm + eliminated × base = 3 × base (5 raiders, не закончатся).
    blocks = result.boss_damage_taken_cm // balance.base_damage_cm
    assert blocks + len(result.eliminated_player_ids) == 3
    # eliminated_player_ids — подмножество.
    raider_ids = {r.player_id for r in raiders}
    assert all(pid in raider_ids for pid in result.eliminated_player_ids)
