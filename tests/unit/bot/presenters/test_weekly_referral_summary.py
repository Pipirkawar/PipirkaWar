"""Unit-тесты `WeeklyClanReferralSummaryPresenter` (Спринт 2.4.E.3)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.referral import (
    WeeklyClanReferralEntryDTO,
    WeeklyClanReferralSummary,
)
from pipirik_wars.bot.presenters.weekly_referral_summary import (
    WeeklyClanReferralSummaryPresenter,
)
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanStatus,
    ClanTitle,
)
from pipirik_wars.domain.player import (
    DisplayName,
    Player,
    PlayerStatus,
    Thickness,
    Title,
)
from pipirik_wars.domain.player.value_objects import Length, Username
from tests.fakes import FakeMessageBundle

NOW = datetime(2026, 5, 10, 18, 0, tzinfo=UTC)


def _presenter() -> WeeklyClanReferralSummaryPresenter:
    return WeeklyClanReferralSummaryPresenter(
        bundle=cast(IMessageBundle, FakeMessageBundle()),
    )


def _make_player(
    *,
    pid: int,
    username: str | None = "alice",
    title: Title | None = None,
    length_cm: int = 50,
) -> Player:
    return Player(
        id=pid,
        tg_id=1000 + pid,
        username=Username(value=username) if username else None,
        length=Length(cm=length_cm),
        thickness=Thickness(level=1),
        title=title,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )


def _make_clan() -> Clan:
    return Clan(
        id=1,
        chat_id=-100123,
        chat_kind=ChatKind.SUPERGROUP,
        title=ClanTitle(value="Огурцы"),
        status=ClanStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )


def _summary_with_top(
    *,
    top: tuple[WeeklyClanReferralEntryDTO, ...],
    total: int,
) -> WeeklyClanReferralSummary:
    return WeeklyClanReferralSummary(clan=_make_clan(), total=total, top=top)


class TestWeeklyClanReferralSummaryPresenter:
    def test_renders_full_card_with_three_entries(self) -> None:
        top = (
            WeeklyClanReferralEntryDTO(player=_make_player(pid=10, username="alice"), count=5),
            WeeklyClanReferralEntryDTO(player=_make_player(pid=11, username="bob"), count=3),
            WeeklyClanReferralEntryDTO(player=_make_player(pid=12, username="carol"), count=2),
        )
        summary = _summary_with_top(top=top, total=10)
        text = _presenter().render(
            summary,
            locale=Locale("ru"),
            display_names=[
                DisplayName(value="Алиса"),
                DisplayName(value="Боб"),
                DisplayName(value="Кэрол"),
            ],
        )
        # Заголовок.
        assert "ru:weekly-referral-summary-title[clan_title=Огурцы]" in text
        # Total.
        assert "ru:weekly-referral-summary-total[total=10]" in text
        # 3 строки top-N.
        assert "rank=1" in text
        assert "rank=2" in text
        assert "rank=3" in text
        # Алиса (DisplayName) и @alice (username).
        assert "Алиса @alice" in text
        # Footer.
        assert "ru:weekly-referral-summary-footer" in text

    def test_renders_with_single_entry(self) -> None:
        top = (
            WeeklyClanReferralEntryDTO(
                player=_make_player(pid=10, username="alice"),
                count=2,
            ),
        )
        summary = _summary_with_top(top=top, total=2)
        text = _presenter().render(
            summary,
            locale=Locale("en"),
            display_names=[DisplayName(value="Alice")],
        )
        assert "en:weekly-referral-summary-title[clan_title=Огурцы]" in text
        assert "en:weekly-referral-summary-total[total=2]" in text
        assert "rank=1" in text
        assert "rank=2" not in text

    def test_referrer_with_title_includes_title_key(self) -> None:
        top = (
            WeeklyClanReferralEntryDTO(
                player=_make_player(pid=10, username="alice", title=Title.NEWBIE),
                count=1,
            ),
        )
        summary = _summary_with_top(top=top, total=1)
        text = _presenter().render(
            summary,
            locale=Locale("ru"),
            display_names=[DisplayName(value="Алиса")],
        )
        assert "ru:profile-title-newbie" in text
        assert "Алиса" in text
        assert "@alice" in text

    def test_referrer_without_username_or_display_name_falls_back_to_id(self) -> None:
        top = (
            WeeklyClanReferralEntryDTO(
                player=_make_player(pid=42, username=None),
                count=1,
            ),
        )
        summary = _summary_with_top(top=top, total=1)
        text = _presenter().render(
            summary,
            locale=Locale("ru"),
            display_names=[None],
        )
        # Без display_name + без username — id-фолбэк.
        assert "id42" in text

    def test_referrer_uses_display_name_when_username_missing(self) -> None:
        top = (
            WeeklyClanReferralEntryDTO(
                player=_make_player(pid=42, username=None),
                count=1,
            ),
        )
        summary = _summary_with_top(top=top, total=1)
        text = _presenter().render(
            summary,
            locale=Locale("ru"),
            display_names=[DisplayName(value="Безымянный")],
        )
        assert "Безымянный" in text
