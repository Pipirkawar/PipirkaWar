"""Unit-тесты `DuelLogTemplate` + `pick_duel_log_template` + `classify_round_outcome` (Спринт 2.1.H)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pipirik_wars.domain.pvp import (
    DuelLogNoTemplatesError,
    DuelLogTemplate,
    Position,
    RoundChoice,
    RoundOutcome,
    RoundOutcomeKind,
    classify_round_outcome,
    pick_duel_log_template,
)
from tests.fakes import FakeRandom


class TestDuelLogTemplate:
    def test_valid_construction(self) -> None:
        t = DuelLogTemplate(
            id="pvp.ru.both_hit.0001",
            text="🥊 {p1} и {p2} оба пробили!",
            kind=RoundOutcomeKind.BOTH_HIT,
        )
        assert t.id == "pvp.ru.both_hit.0001"
        assert t.kind is RoundOutcomeKind.BOTH_HIT

    @pytest.mark.parametrize("bad_id", ["", " ", "  pvp ", "pvp\t"])
    def test_invalid_id_rejected(self, bad_id: str) -> None:
        with pytest.raises(ValueError, match="DuelLogTemplate.id"):
            DuelLogTemplate(id=bad_id, text="t", kind=RoundOutcomeKind.BOTH_HIT)

    @pytest.mark.parametrize("bad_text", ["", " ", "  text  "])
    def test_invalid_text_rejected(self, bad_text: str) -> None:
        with pytest.raises(ValueError, match="DuelLogTemplate.text"):
            DuelLogTemplate(id="pvp.ru.0001", text=bad_text, kind=RoundOutcomeKind.BOTH_HIT)

    def test_frozen(self) -> None:
        t = DuelLogTemplate(id="x.0001", text="text", kind=RoundOutcomeKind.SINGLE_HIT)
        with pytest.raises(FrozenInstanceError):
            t.id = "y"  # type: ignore[misc]


class TestClassifyRoundOutcome:
    @staticmethod
    def _make(*, p1_blocked: bool, p2_blocked: bool) -> RoundOutcome:
        return RoundOutcome(
            p1_choice=RoundChoice(attack=Position.HIGH, block=Position.LOW),
            p2_choice=RoundChoice(attack=Position.HIGH, block=Position.LOW),
            p1_attack_blocked=p1_blocked,
            p2_attack_blocked=p2_blocked,
            p1_damage_to_p2=0 if p1_blocked else 5,
            p2_damage_to_p1=0 if p2_blocked else 5,
        )

    def test_both_hit_when_neither_blocked(self) -> None:
        assert (
            classify_round_outcome(self._make(p1_blocked=False, p2_blocked=False))
            is RoundOutcomeKind.BOTH_HIT
        )

    def test_both_blocked_when_both_blocked(self) -> None:
        assert (
            classify_round_outcome(self._make(p1_blocked=True, p2_blocked=True))
            is RoundOutcomeKind.BOTH_BLOCKED
        )

    @pytest.mark.parametrize(
        ("p1_blocked", "p2_blocked"),
        [(False, True), (True, False)],
    )
    def test_single_hit_when_asymmetric(self, p1_blocked: bool, p2_blocked: bool) -> None:
        assert (
            classify_round_outcome(self._make(p1_blocked=p1_blocked, p2_blocked=p2_blocked))
            is RoundOutcomeKind.SINGLE_HIT
        )


class TestPickDuelLogTemplate:
    @staticmethod
    def _build_catalog() -> list[DuelLogTemplate]:
        return [
            DuelLogTemplate(id="bh.1", text="bh1", kind=RoundOutcomeKind.BOTH_HIT),
            DuelLogTemplate(id="bh.2", text="bh2", kind=RoundOutcomeKind.BOTH_HIT),
            DuelLogTemplate(id="sh.1", text="sh1", kind=RoundOutcomeKind.SINGLE_HIT),
            DuelLogTemplate(id="bb.1", text="bb1", kind=RoundOutcomeKind.BOTH_BLOCKED),
        ]

    def test_picks_from_matching_kind(self) -> None:
        rng = FakeRandom(seed=42)
        catalog = self._build_catalog()
        for _ in range(20):
            t = pick_duel_log_template(
                random=rng, templates=catalog, kind=RoundOutcomeKind.BOTH_HIT
            )
            assert t.kind is RoundOutcomeKind.BOTH_HIT

    def test_falls_back_to_any_when_kind_missing(self) -> None:
        """Если в каталоге нет шаблонов запрошенной категории —
        должен вернуть любой непустой (best-effort)."""
        rng = FakeRandom(seed=42)
        # Только BOTH_HIT в каталоге, запрашиваем SINGLE_HIT.
        catalog = [DuelLogTemplate(id="bh.1", text="bh1", kind=RoundOutcomeKind.BOTH_HIT)]
        t = pick_duel_log_template(random=rng, templates=catalog, kind=RoundOutcomeKind.SINGLE_HIT)
        assert t.id == "bh.1"

    def test_empty_catalog_raises(self) -> None:
        rng = FakeRandom(seed=42)
        with pytest.raises(DuelLogNoTemplatesError):
            pick_duel_log_template(random=rng, templates=[], kind=RoundOutcomeKind.BOTH_HIT)
