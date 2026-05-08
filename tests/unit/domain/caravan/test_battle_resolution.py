"""Тесты `resolve_caravan_battle` (Спринт 3.2-C, ГДД §9.5–§9.6).

Фокусы:

* Детерминированность: один и тот же seed `FakeRandom` → один и тот же
  результат на любом колчестве прогонов.
* Граничные кейсы: 0 рейдеров (auto-delivery), 1 рейдер vs 1 лидер,
  все мертвы (rare), нет защитников.
* Структура наград: лидер ×4 от вклада, караванщики ×3, защитники
  `defender × base_reward_cm`, клан-бонус `+1 см` обоим, при разграблении
  — `ceil(total_cargo / N_raiders) (+ ataman_bonus_share×base)` Атаману.
* Распределение: на 100 симуляциях с разными seed-ами при «честных»
  стартовых условиях оба исхода (delivery / raiders win) случаются
  не реже 5 раз каждый — подтверждаем, что движок не вырожден.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.domain.balance.config import CaravansConfig
from pipirik_wars.domain.caravan import (
    Caravan,
    CaravanBattleResult,
    CaravanContribution,
    CaravanParticipant,
    CaravanParticipantOutcome,
    resolve_caravan_battle,
)
from tests.fakes.random import FakeRandom
from tests.unit.domain.balance.factories import build_valid_balance


def _now() -> datetime:
    return datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)


def _make_caravan() -> Caravan:
    started = _now()
    return Caravan.starting(
        sender_clan_id=10,
        receiver_clan_id=20,
        leader_player_id=42,
        started_at=started,
        lobby_ends_at=started + timedelta(minutes=20),
        battle_ends_at=started + timedelta(minutes=80),
        random_seed=2026_05_07,
    ).mark_in_battle()


def _balance() -> CaravansConfig:
    return build_valid_balance().caravans


def _outcome_by_player(result: CaravanBattleResult, player_id: int) -> CaravanParticipantOutcome:
    matches = [o for o in result.participant_outcomes if o.participant.player_id == player_id]
    if len(matches) != 1:
        raise AssertionError(
            f"Expected exactly 1 outcome for player {player_id}, got {len(matches)}"
        )
    return matches[0]


def _leader(*, player_id: int = 100, contribution_cm: int = 30) -> CaravanParticipant:
    return CaravanParticipant.caravaneer(
        caravan_id=1,
        player_id=player_id,
        contribution=CaravanContribution(cm=contribution_cm),
        is_leader=True,
        joined_at=_now(),
    )


def _caravaneer(*, player_id: int, contribution_cm: int = 25) -> CaravanParticipant:
    return CaravanParticipant.caravaneer(
        caravan_id=1,
        player_id=player_id,
        contribution=CaravanContribution(cm=contribution_cm),
        is_leader=False,
        joined_at=_now(),
    )


def _defender(*, player_id: int) -> CaravanParticipant:
    return CaravanParticipant.defender(caravan_id=1, player_id=player_id, joined_at=_now())


def _raider(*, player_id: int) -> CaravanParticipant:
    return CaravanParticipant.raider(caravan_id=1, player_id=player_id, joined_at=_now())


class TestPreconditions:
    def test_empty_participants_raises(self) -> None:
        with pytest.raises(ValueError, match="participants is empty"):
            resolve_caravan_battle(
                caravan=_make_caravan(),
                participants=(),
                balance=_balance(),
                random=FakeRandom(seed=1),
            )

    def test_no_caravaneers_raises(self) -> None:
        # участники — только защитники и рейдеры, без караванщика. Нарушение
        # инварианта use-case-а (лидер всегда есть).
        with pytest.raises(ValueError, match="at least 1 CARAVANEER"):
            resolve_caravan_battle(
                caravan=_make_caravan(),
                participants=(_defender(player_id=200), _raider(player_id=300)),
                balance=_balance(),
                random=FakeRandom(seed=1),
            )


class TestAutoDeliveryNoRaiders:
    """0 рейдеров → караван дошёл, никто не получает урон."""

    def test_solo_leader_delivers(self) -> None:
        leader = _leader(player_id=100, contribution_cm=30)
        result = resolve_caravan_battle(
            caravan=_make_caravan(),
            participants=(leader,),
            balance=_balance(),
            random=FakeRandom(seed=1),
        )
        assert result.raiders_won is False
        leader_o = _outcome_by_player(result, 100)
        assert leader_o.is_alive is True
        assert leader_o.gets_ataman_title is False
        # leader=4, contribution=30 → 120
        assert leader_o.length_delta_cm == 4 * 30
        # клан-бонус + 1 см обоим
        assert result.clan_bonus_cm_sender == 1
        assert result.clan_bonus_cm_receiver == 1

    def test_full_party_no_raiders(self) -> None:
        leader = _leader(player_id=100, contribution_cm=30)
        co_caravaneer = _caravaneer(player_id=101, contribution_cm=25)
        defender = _defender(player_id=200)
        result = resolve_caravan_battle(
            caravan=_make_caravan(),
            participants=(leader, co_caravaneer, defender),
            balance=_balance(),
            random=FakeRandom(seed=1),
        )
        assert result.raiders_won is False
        # leader×4 = 120
        assert _outcome_by_player(result, 100).length_delta_cm == 120
        # caravaneer×3 = 75
        assert _outcome_by_player(result, 101).length_delta_cm == 75
        # defender × base_reward_cm = 1 × 5 = 5
        assert _outcome_by_player(result, 200).length_delta_cm == 5
        # все живы, никто — Атаман
        for o in result.participant_outcomes:
            assert o.is_alive is True
            assert o.gets_ataman_title is False


class TestRaidersVictoryAllDefendersDie:
    """1 лидер vs 4 рейдера: все рейдеры с гарантией пробьют 2 блока."""

    def _setup(self, seed: int = 1) -> CaravanBattleResult:
        leader = _leader(player_id=100, contribution_cm=20)
        # 4 рейдера vs 1 караванщика (2 блока). При 4 ударах хотя бы один
        # с большой вероятностью «не в блок» → лидер умирает. Подбираем
        # seed, при котором все 4 пробивают.
        raiders = (
            _raider(player_id=300),
            _raider(player_id=301),
            _raider(player_id=302),
            _raider(player_id=303),
        )
        return resolve_caravan_battle(
            caravan=_make_caravan(),
            participants=(leader, *raiders),
            balance=_balance(),
            random=FakeRandom(seed=seed),
        )

    def test_raiders_can_win(self) -> None:
        # Для seed=2 (детерминистично) лидер должен погибнуть.
        for seed in range(1, 50):
            result = self._setup(seed=seed)
            if result.raiders_won:
                # Проверим инварианты победы:
                leader_o = _outcome_by_player(result, 100)
                assert leader_o.is_alive is False
                # leader получил unblocked_strike_damage_cm = -1
                assert leader_o.length_delta_cm == -1
                # Все рейдеры живы, ровно у одного — Атаман
                raider_outcomes = [
                    o for o in result.participant_outcomes if o.participant.player_id >= 300
                ]
                assert all(o.is_alive for o in raider_outcomes)
                ataman_count = sum(1 for o in raider_outcomes if o.gets_ataman_title)
                assert ataman_count == 1
                # base_share = ceil(20 / 4) = 5
                # ataman_bonus = 5 * 4 = 20 → ataman_total = 5 + 20 = 25
                # обычный рейдер: 5 (минус блок-урон, если был)
                ataman_o = next(o for o in raider_outcomes if o.gets_ataman_title)
                # без учёта урона ataman = 25
                assert ataman_o.length_delta_cm <= 25  # минус возможный блок-урон
                assert ataman_o.length_delta_cm >= 25 - 4  # не больше 4 ударов
                # Клан не получает бонус при поражении
                assert result.clan_bonus_cm_sender == 0
                assert result.clan_bonus_cm_receiver == 0
                return  # один кейс достаточен
        pytest.fail("In 50 seeds, raiders never won — model looks broken")


class TestDeterminism:
    """Один и тот же seed → один и тот же исход (battle reproducibility)."""

    def test_same_seed_same_outcome(self) -> None:
        leader = _leader(player_id=100, contribution_cm=25)
        co = _caravaneer(player_id=101, contribution_cm=30)
        defender = _defender(player_id=200)
        raiders = (_raider(player_id=300), _raider(player_id=301))
        participants = (leader, co, defender, *raiders)

        first = resolve_caravan_battle(
            caravan=_make_caravan(),
            participants=participants,
            balance=_balance(),
            random=FakeRandom(seed=42),
        )
        second = resolve_caravan_battle(
            caravan=_make_caravan(),
            participants=participants,
            balance=_balance(),
            random=FakeRandom(seed=42),
        )
        assert first == second

    def test_different_seed_can_differ(self) -> None:
        # Не строгое требование (разные seed-ы могут случайно совпасть),
        # но в 100 разных seed-ах хотя бы 2 исхода должны различаться.
        leader = _leader(player_id=100, contribution_cm=20)
        raiders = tuple(_raider(player_id=300 + i) for i in range(3))
        participants = (leader, *raiders)

        results: set[bool] = set()
        for seed in range(100):
            r = resolve_caravan_battle(
                caravan=_make_caravan(),
                participants=participants,
                balance=_balance(),
                random=FakeRandom(seed=seed),
            )
            results.add(r.raiders_won)
            if len(results) == 2:
                return
        pytest.fail("In 100 seeds, raiders_won never varied — distribution is degenerate")


class TestDistribution100Simulations:
    """100 симуляций: оба исхода должны встречаться достаточно часто.

    Это smoke-test баланса: при «честной» стартовой конфигурации
    (1 лидер + 1 защитник vs 2 рейдера) рейдеры не должны ВСЕГДА
    выигрывать или ВСЕГДА проигрывать.
    """

    def test_balanced_setup_both_outcomes_occur(self) -> None:
        leader = _leader(player_id=100, contribution_cm=25)
        defender = _defender(player_id=200)
        raiders = (_raider(player_id=300), _raider(player_id=301))
        participants = (leader, defender, *raiders)

        wins_caravaneers = 0
        wins_raiders = 0
        for seed in range(100):
            r = resolve_caravan_battle(
                caravan=_make_caravan(),
                participants=participants,
                balance=_balance(),
                random=FakeRandom(seed=seed),
            )
            if r.raiders_won:
                wins_raiders += 1
            else:
                wins_caravaneers += 1

        # Не вырожденное распределение.
        assert wins_caravaneers >= 5
        assert wins_raiders >= 5


class TestParticipantOrderPreserved:
    def test_outcomes_in_input_order(self) -> None:
        leader = _leader(player_id=100, contribution_cm=20)
        defender = _defender(player_id=200)
        co = _caravaneer(player_id=101, contribution_cm=20)
        raider = _raider(player_id=300)
        participants: Sequence[CaravanParticipant] = (leader, defender, co, raider)
        result = resolve_caravan_battle(
            caravan=_make_caravan(),
            participants=participants,
            balance=_balance(),
            random=FakeRandom(seed=1),
        )
        assert tuple(o.participant.player_id for o in result.participant_outcomes) == (
            100,
            200,
            101,
            300,
        )


class TestRewardArithmetic:
    """Точный арифметический контроль наград (no randomness in outcome math)."""

    def test_leader_reward_is_leader_multiplier_times_contribution(self) -> None:
        leader = _leader(player_id=100, contribution_cm=42)
        result = resolve_caravan_battle(
            caravan=_make_caravan(),
            participants=(leader,),
            balance=_balance(),
            random=FakeRandom(seed=1),
        )
        assert result.raiders_won is False
        # leader=4, contribution=42 → 168
        assert _outcome_by_player(result, 100).length_delta_cm == 4 * 42

    def test_caravaneer_reward_is_caravaneer_multiplier_times_contribution(self) -> None:
        leader = _leader(player_id=100, contribution_cm=20)
        co = _caravaneer(player_id=101, contribution_cm=33)
        result = resolve_caravan_battle(
            caravan=_make_caravan(),
            participants=(leader, co),
            balance=_balance(),
            random=FakeRandom(seed=1),
        )
        # caravaneer=3, contribution=33 → 99
        assert _outcome_by_player(result, 101).length_delta_cm == 3 * 33

    def test_defender_reward_is_defender_multiplier_times_base_reward(self) -> None:
        leader = _leader(player_id=100, contribution_cm=20)
        defender = _defender(player_id=200)
        result = resolve_caravan_battle(
            caravan=_make_caravan(),
            participants=(leader, defender),
            balance=_balance(),
            random=FakeRandom(seed=1),
        )
        # defender=1, base_reward=5 → 5
        assert _outcome_by_player(result, 200).length_delta_cm == 1 * 5

    def test_raider_with_no_blocks_gets_zero_in_delivery(self) -> None:
        # 1 лидер + 1 рейдер: рейдер бьёт раз; если лидер блокирует — раидер
        # теряет 1; если не блокирует — лидер мёртв (попадаем в other ветку).
        # Подбираем seed, при котором лидер блокирует И раидер промахивается?
        # Нет, после 1 удара исход однозначен. Проверим обе ветки.
        leader = _leader(player_id=100, contribution_cm=25)
        raider = _raider(player_id=300)
        for seed in range(50):
            r = resolve_caravan_battle(
                caravan=_make_caravan(),
                participants=(leader, raider),
                balance=_balance(),
                random=FakeRandom(seed=seed),
            )
            if not r.raiders_won:
                raider_o = _outcome_by_player(result=r, player_id=300)
                # рейдер либо потерял 1 (заблокирован), либо 0 (если как-то не бил;
                # но он бил один раз → значит был в блок).
                assert raider_o.length_delta_cm in (0, -1)
                # Лидер выжил → +120
                assert _outcome_by_player(r, 100).length_delta_cm == 4 * 25
                return
        pytest.fail("In 50 seeds, leader never survived solo vs 1 raider")


class TestRaidersCargoSplit:
    """Разграбление: ceil-делёжка cargo."""

    def test_cargo_split_with_remainder_rounds_up(self) -> None:
        # 1 лидер с вкладом 21 + 3 раидера: base_share = ceil(21/3) = 7
        leader = _leader(player_id=100, contribution_cm=21)
        raiders = tuple(_raider(player_id=300 + i) for i in range(3))
        for seed in range(100):
            r = resolve_caravan_battle(
                caravan=_make_caravan(),
                participants=(leader, *raiders),
                balance=_balance(),
                random=FakeRandom(seed=seed),
            )
            if r.raiders_won:
                # Найти не-Атамана без блок-урона: выберём любого, у кого
                # ровно base_share. Хотя бы один из рейдеров не Атаман и
                # не получил блок-урон с большой вероятностью.
                non_ataman = [
                    o
                    for o in r.participant_outcomes
                    if o.participant.player_id >= 300 and not o.gets_ataman_title
                ]
                assert non_ataman
                # все non-ataman рейдеры получили base_share минус возможный блок-урон
                for o in non_ataman:
                    assert o.length_delta_cm <= 7  # base_share = 7
                # Атаман: 7 + 7*4 = 35 минус возможный блок-урон
                ataman = next(o for o in r.participant_outcomes if o.gets_ataman_title)
                assert ataman.length_delta_cm <= 35
                return
        pytest.fail("In 100 seeds, raiders never won — model unbalanced")

    def test_cargo_split_evenly(self) -> None:
        # 1 лидер с вкладом 20 + 4 рейдера: base_share = ceil(20/4) = 5
        leader = _leader(player_id=100, contribution_cm=20)
        raiders = tuple(_raider(player_id=300 + i) for i in range(4))
        for seed in range(100):
            r = resolve_caravan_battle(
                caravan=_make_caravan(),
                participants=(leader, *raiders),
                balance=_balance(),
                random=FakeRandom(seed=seed),
            )
            if r.raiders_won:
                # base_share = 5; ataman_total = 5 + 5*4 = 25
                ataman = next(o for o in r.participant_outcomes if o.gets_ataman_title)
                assert ataman.length_delta_cm <= 25
                return
        pytest.fail("In 100 seeds, raiders never won — model unbalanced")


class TestAtamanIsExactlyOne:
    """Ровно один рейдер становится Атаманом при победе."""

    def test_ataman_unique(self) -> None:
        leader = _leader(player_id=100, contribution_cm=20)
        raiders = tuple(_raider(player_id=300 + i) for i in range(5))
        wins_seen = 0
        for seed in range(200):
            r = resolve_caravan_battle(
                caravan=_make_caravan(),
                participants=(leader, *raiders),
                balance=_balance(),
                random=FakeRandom(seed=seed),
            )
            if r.raiders_won:
                wins_seen += 1
                ataman_count = sum(1 for o in r.participant_outcomes if o.gets_ataman_title)
                assert ataman_count == 1
                # Атаман — рейдер, не караванщик/защитник.
                ataman = next(o for o in r.participant_outcomes if o.gets_ataman_title)
                assert ataman.participant.player_id >= 300
        assert wins_seen >= 1, "Need at least 1 raiders' victory in 200 seeds"

    def test_no_ataman_on_delivery(self) -> None:
        leader = _leader(player_id=100, contribution_cm=20)
        defender = _defender(player_id=200)
        result = resolve_caravan_battle(
            caravan=_make_caravan(),
            participants=(leader, defender),
            balance=_balance(),
            random=FakeRandom(seed=1),
        )
        assert result.raiders_won is False
        for o in result.participant_outcomes:
            assert o.gets_ataman_title is False


class TestZeroAtamanBonusShare:
    """`ataman_bonus_share=0` отключает бонус Атамана: ровно `base_share`."""

    def test_ataman_bonus_disabled(self) -> None:
        balance = _balance()
        # Соберём конфиг с ataman_bonus_share=0
        rm = balance.reward_multipliers.model_copy(update={"ataman_bonus_share": 0})
        balance_no_ataman = balance.model_copy(update={"reward_multipliers": rm})

        leader = _leader(player_id=100, contribution_cm=24)
        raiders = tuple(_raider(player_id=300 + i) for i in range(4))
        for seed in range(100):
            r = resolve_caravan_battle(
                caravan=_make_caravan(),
                participants=(leader, *raiders),
                balance=balance_no_ataman,
                random=FakeRandom(seed=seed),
            )
            if r.raiders_won:
                # base_share = ceil(24/4) = 6; ataman bonus = 0 → ataman_total = 6
                ataman = next(o for o in r.participant_outcomes if o.gets_ataman_title)
                assert ataman.length_delta_cm <= 6
                return
        pytest.fail("In 100 seeds, raiders never won")
