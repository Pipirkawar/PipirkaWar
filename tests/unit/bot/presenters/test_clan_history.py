"""\u042e\u043d\u0438\u0442-\u0442\u0435\u0441\u0442\u044b `ClanHistoryPresenter` (\u0421\u043f\u0440\u0438\u043d\u0442 2.2.G / \u041f\u0414 2.2.5).

\u041f\u043e\u043a\u0440\u044b\u0432\u0430\u0435\u043c:
1. \u041f\u0443\u0441\u0442\u043e\u0439 \u0436\u0443\u0440\u043d\u0430\u043b \u2192 \u043a\u043b\u044e\u0447 `clan-history-empty` \u0441 \u043f\u0440\u043e\u043a\u0438\u043d\u0443\u0442\u044b\u043c `clan_title`.
2. \u041d\u0435\u043f\u0443\u0441\u0442\u043e\u0439: \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a \u043f\u0435\u0440\u0432\u043e\u0439 \u0441\u0442\u0440\u043e\u043a\u043e\u0439 + entries \u043f\u043e \u043f\u043e\u0440\u044f\u0434\u043a\u0443.
3. \u041e\u0442\u0434\u0435\u043b\u044c\u043d\u044b\u0435 \u043a\u043b\u044e\u0447\u0438 `entry-victory/defeat/draw/cancelled`
   \u043e\u0442 \u0432\u044b\u0431\u0438\u0440\u0430\u044e\u0442\u0441\u044f \u043f\u043e `outcome`.
4. \u0414\u043b\u044f CANCELLED \u0432 \u0441\u0442\u0440\u043e\u043a\u0443 \u043d\u0435 \u043f\u0440\u043e\u043a\u0438\u0434\u044b\u0432\u0430\u044e\u0442\u0441\u044f `our_delta_cm` /
   `our_count` / `opponent_count` (\u044d\u0442\u0438 \u043f\u043e\u043b\u044f \u043d\u0435 \u0438\u043c\u0435\u044e\u0442 \u0441\u043c\u044b\u0441\u043b\u0430).
5. `when` \u0444\u043e\u0440\u043c\u0430\u0442\u0438\u0440\u0443\u0435\u0442\u0441\u044f \u043a\u0430\u043a `dd.mm HH:MM` (UTC).
6. End-to-end \u0447\u0435\u0440\u0435\u0437 `FluentMessageBundle` (RU + EN) \u2014 \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u0435\u043c
   \u043d\u0430\u043b\u0438\u0447\u0438\u0435 \u0432\u0441\u0435\u0445 \u043a\u043b\u044e\u0447\u0435\u0439 \u0432 `.ftl`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.presenters.clan_history import ClanHistoryPresenter
from pipirik_wars.domain.clan import ClanTitle
from pipirik_wars.domain.pvp import (
    ClanMassDuelHistoryEntry,
    ClanMassDuelOutcomeForUs,
    MassDuelState,
)
from pipirik_wars.infrastructure.i18n import FluentMessageBundle
from tests.fakes import FakeMessageBundle

_NOW = datetime(2026, 5, 5, 12, 30, tzinfo=UTC)


def _victory(
    *,
    duel_id: int = 1,
    our_delta: int = 20,
    opponent_title: str = "\u041c\u043e\u0440\u0441\u043a\u0438\u0435",
) -> ClanMassDuelHistoryEntry:
    return ClanMassDuelHistoryEntry(
        duel_id=duel_id,
        our_clan_id=10,
        opponent_clan_id=20,
        opponent_clan_title=ClanTitle(value=opponent_title),
        state=MassDuelState.COMPLETED,
        outcome=ClanMassDuelOutcomeForUs.VICTORY,
        our_total_dealt=30,
        our_total_received=10,
        our_delta_cm=our_delta,
        opponent_delta_cm=-our_delta,
        our_participants_count=3,
        opponent_participants_count=2,
        created_at=_NOW,
        completed_at=_NOW,
    )


def _defeat() -> ClanMassDuelHistoryEntry:
    return ClanMassDuelHistoryEntry(
        duel_id=2,
        our_clan_id=10,
        opponent_clan_id=20,
        opponent_clan_title=ClanTitle(value="\u041b\u0435\u0441\u043d\u044b\u0435"),
        state=MassDuelState.COMPLETED,
        outcome=ClanMassDuelOutcomeForUs.DEFEAT,
        our_total_dealt=10,
        our_total_received=30,
        our_delta_cm=-20,
        opponent_delta_cm=20,
        our_participants_count=2,
        opponent_participants_count=3,
        created_at=_NOW,
        completed_at=_NOW,
    )


def _draw() -> ClanMassDuelHistoryEntry:
    return ClanMassDuelHistoryEntry(
        duel_id=3,
        our_clan_id=10,
        opponent_clan_id=20,
        opponent_clan_title=ClanTitle(value="\u0421\u0442\u0435\u043f\u043d\u044b\u0435"),
        state=MassDuelState.COMPLETED,
        outcome=ClanMassDuelOutcomeForUs.DRAW,
        our_total_dealt=15,
        our_total_received=15,
        our_delta_cm=0,
        opponent_delta_cm=0,
        our_participants_count=2,
        opponent_participants_count=2,
        created_at=_NOW,
        completed_at=_NOW,
    )


def _cancelled() -> ClanMassDuelHistoryEntry:
    return ClanMassDuelHistoryEntry(
        duel_id=4,
        our_clan_id=10,
        opponent_clan_id=20,
        opponent_clan_title=ClanTitle(value="\u0413\u0430\u0439\u0441\u043a\u0438\u0435"),
        state=MassDuelState.CANCELLED,
        outcome=ClanMassDuelOutcomeForUs.CANCELLED,
        our_total_dealt=0,
        our_total_received=0,
        our_delta_cm=0,
        opponent_delta_cm=0,
        our_participants_count=2,
        opponent_participants_count=2,
        created_at=_NOW,
        completed_at=None,
    )


def _fluent_bundle() -> IMessageBundle:
    return FluentMessageBundle(
        locales_dir=Path(__file__).resolve().parents[4] / "locales",
    )


class TestClanHistoryPresenterFakeBundle:
    def _make(self) -> ClanHistoryPresenter:
        return ClanHistoryPresenter(bundle=cast(IMessageBundle, FakeMessageBundle()))

    def test_empty_uses_empty_key_with_clan_title(self) -> None:
        text = self._make().render([], clan_title="\u041b\u044c\u0432\u044b", locale=Locale("ru"))
        assert text == "ru:clan-history-empty[clan_title=\u041b\u044c\u0432\u044b]"

    def test_non_empty_starts_with_header(self) -> None:
        text = self._make().render(
            [_victory()], clan_title="\u041b\u044c\u0432\u044b", locale=Locale("en")
        )
        lines = text.split("\n")
        assert lines[0] == "en:clan-history-header[clan_title=\u041b\u044c\u0432\u044b]"
        assert lines[1] == ""

    def test_victory_uses_entry_victory_key_with_params(self) -> None:
        text = self._make().render(
            [_victory(our_delta=42, opponent_title="Soldiers")],
            clan_title="Lions",
            locale=Locale("en"),
        )
        line = text.split("\n")[2]
        assert "en:clan-history-entry-victory[" in line
        assert "idx=1" in line
        assert "opponent_clan_title=Soldiers" in line
        assert "our_delta_cm=42" in line
        assert "our_count=3" in line
        assert "opponent_count=2" in line
        assert "when=05.05 12:30" in line

    def test_defeat_uses_entry_defeat_key(self) -> None:
        text = self._make().render([_defeat()], clan_title="Lions", locale=Locale("ru"))
        line = text.split("\n")[2]
        assert "ru:clan-history-entry-defeat[" in line
        assert "our_delta_cm=-20" in line

    def test_draw_uses_entry_draw_key(self) -> None:
        text = self._make().render([_draw()], clan_title="Lions", locale=Locale("ru"))
        line = text.split("\n")[2]
        assert "ru:clan-history-entry-draw[" in line
        # \u0414\u043b\u044f draw `our_delta_cm=0`, \u043d\u043e \u0432 .ftl-\u043a\u043b\u044e\u0447\u0435 \u044d\u0442\u043e\u0433\u043e \u043f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u0430 \u043d\u0435\u0442 \u2014
        # presenter \u0432\u0441\u0451 \u0440\u0430\u0432\u043d\u043e \u043f\u0440\u043e\u043a\u0438\u0434\u044b\u0432\u0430\u0435\u0442 \u0432\u0441\u0435 \u043f\u043e\u043b\u044f, \u044d\u0442\u043e \u043e\u043a.
        assert "our_count=2" in line
        assert "opponent_count=2" in line

    def test_cancelled_uses_entry_cancelled_key_without_count_or_delta(self) -> None:
        text = self._make().render([_cancelled()], clan_title="Lions", locale=Locale("ru"))
        line = text.split("\n")[2]
        assert "ru:clan-history-entry-cancelled[" in line
        # \u0414\u043b\u044f CANCELLED \u043f\u0440\u043e\u043a\u0438\u0434\u044b\u0432\u0430\u044e\u0442\u0441\u044f \u0442\u043e\u043b\u044c\u043a\u043e idx + opponent_clan_title + when.
        assert "our_count=" not in line
        assert "opponent_count=" not in line
        assert "our_delta_cm=" not in line

    def test_entries_are_indexed_in_order(self) -> None:
        text = self._make().render(
            [_victory(duel_id=1), _defeat(), _draw()],
            clan_title="Lions",
            locale=Locale("ru"),
        )
        idx_1 = text.index("idx=1")
        idx_2 = text.index("idx=2")
        idx_3 = text.index("idx=3")
        assert idx_1 < idx_2 < idx_3

    def test_when_uses_completed_at_for_completed(self) -> None:
        text = self._make().render([_victory()], clan_title="Lions", locale=Locale("ru"))
        assert "when=05.05 12:30" in text

    def test_when_uses_created_at_for_cancelled(self) -> None:
        text = self._make().render([_cancelled()], clan_title="Lions", locale=Locale("ru"))
        # `_cancelled()` \u0438\u043c\u0435\u0435\u0442 created_at=NOW (12:30), completed_at=None.
        assert "when=05.05 12:30" in text

    def test_needs_group_chat_uses_dedicated_key(self) -> None:
        assert (
            self._make().needs_group_chat(locale=Locale("ru")) == "ru:clan-history-needs-group-chat"
        )

    def test_not_registered_uses_dedicated_key(self) -> None:
        assert self._make().not_registered(locale=Locale("en")) == "en:clan-history-not-registered"


class TestClanHistoryPresenterFluent:
    """End-to-end \u0447\u0435\u0440\u0435\u0437 \u0440\u0435\u0430\u043b\u044c\u043d\u044b\u0439 `.ftl`: \u043b\u043e\u0432\u0438\u043c \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0438\u0435 \u043a\u043b\u044e\u0447\u0435\u0439."""

    def _make(self) -> ClanHistoryPresenter:
        return ClanHistoryPresenter(bundle=_fluent_bundle())

    def test_ru_empty_returns_localized_string(self) -> None:
        text = self._make().render([], clan_title="\u041b\u044c\u0432\u044b", locale=Locale("ru"))
        assert "\u041b\u044c\u0432\u044b" in text

    def test_en_empty_returns_localized_string(self) -> None:
        text = self._make().render([], clan_title="Lions", locale=Locale("en"))
        assert "Lions" in text

    def test_ru_victory_renders_opponent_and_delta(self) -> None:
        text = self._make().render(
            [_victory(our_delta=42, opponent_title="\u041c\u043e\u0440\u0441\u043a\u0438\u0435")],
            clan_title="\u041b\u044c\u0432\u044b",
            locale=Locale("ru"),
        )
        assert "\u041c\u043e\u0440\u0441\u043a\u0438\u0435" in text
        assert "42" in text
        # \u0421\u0442\u0440\u043e\u043a\u0430 \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043a\u0430 \u0438\u0437 .ftl \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 «\u041b\u044c\u0432\u044b».
        assert "\u041b\u044c\u0432\u044b" in text

    def test_en_defeat_renders_with_negative_sign(self) -> None:
        text = self._make().render([_defeat()], clan_title="Lions", locale=Locale("en"))
        assert "20" in text
        # \u0421\u0442\u0430\u0442\u0443\u0441 \u00abdefeat\u00bb \u0432 EN-\u043b\u043e\u043a\u0430\u043b\u0438.
        assert "defeat" in text.lower()

    def test_ru_cancelled_renders_localized_status(self) -> None:
        text = self._make().render(
            [_cancelled()], clan_title="\u041b\u044c\u0432\u044b", locale=Locale("ru")
        )
        assert "\u041b\u044c\u0432\u044b" in text
        assert "\u0413\u0430\u0439\u0441\u043a\u0438\u0435" in text

    def test_needs_group_chat_returns_localized_string(self) -> None:
        text = self._make().needs_group_chat(locale=Locale("ru"))
        assert "/clan_history" in text or "\u043a\u043b\u0430\u043d" in text.lower()

    def test_not_registered_returns_localized_string(self) -> None:
        text = self._make().not_registered(locale=Locale("en"))
        assert "clan" in text.lower()
