"""Unit-тесты helper-функций для маппинга доменных исходов в метрика-label-ы.

Покрытие:
* `pipirik_wars.application.pvp.submit_move._duel_outcome_label` —
  `DuelWinner` → `DuelResolvedOutcome` (без AFK-флагов).
* `pipirik_wars.application.pvp.resolve_afk_round._afk_outcome_label` —
  комбинация `DuelWinner` + `p1_was_afk` + `p2_was_afk` → `DuelResolvedOutcome`.
* `pipirik_wars.application.forest.finish_run._forest_finished_outcome` —
  `Drop`-ADT → `ForestRunOutcome` (`drop` если NameDrop/ItemDrop, иначе `success`).

Эти helper-ы — чистые функции на доменных типах. Тестируем напрямую,
без поднятия use-case-ов: каждый раз создаём минимальный Duel/ForestRun
через `unittest.mock.MagicMock` (для Duel — единственная зависимость
`final_outcome.winner`).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pipirik_wars.application.forest.finish_run import _forest_finished_outcome
from pipirik_wars.application.observability import (
    DuelResolvedOutcome,
    ForestRunOutcome,
)
from pipirik_wars.application.pvp.resolve_afk_round import _afk_outcome_label
from pipirik_wars.application.pvp.submit_move import _duel_outcome_label
from pipirik_wars.domain.forest import (
    ItemDrop,
    NameDrop,
    NoDrop,
)
from pipirik_wars.domain.forest.entities import Item, Name, Rarity, Slot
from pipirik_wars.domain.pvp import DuelWinner


def _make_duel(winner: DuelWinner) -> MagicMock:
    """Минимальный mock-`Duel` с заданным `final_outcome.winner`."""
    outcome = MagicMock()
    outcome.winner = winner
    duel = MagicMock()
    duel.final_outcome = outcome
    return duel


class TestDuelOutcomeLabel:
    """`_duel_outcome_label` для SubmitMove-резолва (не-AFK ветка)."""

    @pytest.mark.parametrize(
        ("winner", "expected"),
        [
            (DuelWinner.P1, "p1_win"),
            (DuelWinner.P2, "p2_win"),
            (DuelWinner.DRAW, "draw"),
        ],
    )
    def test_winner_mapped_to_label(
        self,
        winner: DuelWinner,
        expected: DuelResolvedOutcome,
    ) -> None:
        duel = _make_duel(winner)
        assert _duel_outcome_label(duel) == expected


class TestAfkOutcomeLabel:
    """`_afk_outcome_label` для ResolveAfkRound-резолва (AFK ветка)."""

    @pytest.mark.parametrize(
        ("p1_afk", "p2_afk", "winner", "expected"),
        [
            # Только p1 AFK — всегда `p1_afk` (даже если случайный fallback p1 принёс ничью/победу).
            (True, False, DuelWinner.P2, "p1_afk"),
            (True, False, DuelWinner.P1, "p1_afk"),
            (True, False, DuelWinner.DRAW, "p1_afk"),
            # Только p2 AFK — всегда `p2_afk`.
            (False, True, DuelWinner.P1, "p2_afk"),
            (False, True, DuelWinner.P2, "p2_afk"),
            (False, True, DuelWinner.DRAW, "p2_afk"),
        ],
    )
    def test_single_side_afk_maps_to_pn_afk(
        self,
        p1_afk: bool,
        p2_afk: bool,
        winner: DuelWinner,
        expected: DuelResolvedOutcome,
    ) -> None:
        duel = _make_duel(winner)
        assert _afk_outcome_label(duel, p1_was_afk=p1_afk, p2_was_afk=p2_afk) == expected

    @pytest.mark.parametrize(
        ("winner", "expected"),
        [
            # Оба AFK + p1 выиграл рандомом ⇒ p2 проиграл и был AFK ⇒ `p2_afk`.
            (DuelWinner.P1, "p2_afk"),
            (DuelWinner.P2, "p1_afk"),
            (DuelWinner.DRAW, "draw"),
        ],
    )
    def test_both_sides_afk_uses_winner_to_pick_loser(
        self,
        winner: DuelWinner,
        expected: DuelResolvedOutcome,
    ) -> None:
        duel = _make_duel(winner)
        assert _afk_outcome_label(duel, p1_was_afk=True, p2_was_afk=True) == expected

    @pytest.mark.parametrize(
        ("winner", "expected"),
        [
            # Никто не AFK (теоретически недостижимая ветка — оба уже отправили ходы
            # к моменту срабатывания AFK-таймера) — fallback на обычный winner-mapping.
            (DuelWinner.P1, "p1_win"),
            (DuelWinner.P2, "p2_win"),
            (DuelWinner.DRAW, "draw"),
        ],
    )
    def test_no_afk_fallback_to_normal_winner(
        self,
        winner: DuelWinner,
        expected: DuelResolvedOutcome,
    ) -> None:
        duel = _make_duel(winner)
        assert _afk_outcome_label(duel, p1_was_afk=False, p2_was_afk=False) == expected


class TestForestFinishedOutcome:
    """`_forest_finished_outcome` для FinishForestRun-резолва.

    Маппинг:
    * NameDrop → `drop` (игрок получил имя).
    * ItemDrop → `drop` (игрок получил предмет).
    * NoDrop   → `success` (длина прибавлена, без предметов).

    Используем `MagicMock(spec=ForestRun)` с подменой `drop`-поля —
    helper читает только `isinstance(run.drop, NoDrop)`.
    """

    @staticmethod
    def _make_run(drop: NameDrop | ItemDrop | NoDrop) -> MagicMock:
        run = MagicMock()
        run.drop = drop
        return run

    def test_no_drop_maps_to_success(self) -> None:
        run = self._make_run(NoDrop())
        result: ForestRunOutcome = _forest_finished_outcome(run)
        assert result == "success"

    def test_name_drop_maps_to_drop(self) -> None:
        run = self._make_run(NameDrop(name=Name(value="Bigus Dickus")))
        result: ForestRunOutcome = _forest_finished_outcome(run)
        assert result == "drop"

    def test_item_drop_maps_to_drop(self) -> None:
        item = Item(
            id="item.hat.test_hat",
            slot=Slot.HAT,
            display_name="Test Hat",
            rarity=Rarity.COMMON,
        )
        run = self._make_run(ItemDrop(item=item))
        result: ForestRunOutcome = _forest_finished_outcome(run)
        assert result == "drop"
