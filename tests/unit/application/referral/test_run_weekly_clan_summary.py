"""Юнит-тесты `RunWeeklyClanReferralSummary` (Спринт 2.4.E.2).

Покрывают acceptance:
- happy-path: один член клана привёл рефералов → возвращается
  `WeeklyClanReferralSummary` с `total = N` и top-1;
- happy-path: несколько рефереров → top-3 в порядке `count DESC`,
  `total` = сумма;
- frozen-клан → `None` без обращения к репо рефералов;
- клан не существует → `IntegrityError`;
- пустая неделя (`weekly_summary_by_clan = []`) → `None`;
- удалённый реферер (запись есть в `referrals`, но `Player` отсутствует)
  → пропускается; если все top-N пропущены — `None`;
- окно `[since, until)` корректно: `until = clock.now()`,
  `since = until - 7 дней`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pipirik_wars.application.dto.inputs import RunWeeklyClanReferralSummaryInput
from pipirik_wars.application.referral import (
    RunWeeklyClanReferralSummary,
    WeeklyClanReferralSummary,
)
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanStatus,
    ClanTitle,
)
from pipirik_wars.domain.player import Player, PlayerStatus, Thickness
from pipirik_wars.domain.player.value_objects import Length, Username
from pipirik_wars.domain.referral import Referral
from pipirik_wars.shared.errors import IntegrityError
from tests.fakes import (
    FakeClanRepository,
    FakeClock,
    FakePlayerRepository,
    FakeReferralRepository,
    FakeUnitOfWork,
)

NOW = datetime(2026, 5, 10, 18, 0, tzinfo=UTC)  # вс. 18:00 UTC.
WINDOW_START = NOW - timedelta(days=7)


def _make_player(*, player_id: int, tg_id: int) -> Player:
    return Player(
        id=player_id,
        tg_id=tg_id,
        username=Username(value=f"u{player_id}"),
        length=Length(cm=2),
        thickness=Thickness(level=1),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=NOW - timedelta(days=30),
        updated_at=NOW,
    )


def _make_clan(
    *,
    clan_id: int = 1,
    chat_id: int = -100123,
    status: ClanStatus = ClanStatus.ACTIVE,
) -> Clan:
    return Clan(
        id=clan_id,
        chat_id=chat_id,
        chat_kind=ChatKind.SUPERGROUP,
        title=ClanTitle(value=f"Клан #{clan_id}"),
        status=status,
        created_at=NOW - timedelta(days=30),
        updated_at=NOW,
    )


def _make_referral(
    *,
    ref_id: int,
    referrer_id: int,
    referred_id: int,
    created_at: datetime,
) -> Referral:
    return Referral(
        id=ref_id,
        referrer_id=referrer_id,
        referred_id=referred_id,
        created_at=created_at,
    )


def _build() -> tuple[
    RunWeeklyClanReferralSummary,
    FakeClanRepository,
    FakePlayerRepository,
    FakeReferralRepository,
]:
    uow = FakeUnitOfWork()
    clans = FakeClanRepository()
    players = FakePlayerRepository()
    referrals = FakeReferralRepository()
    use_case = RunWeeklyClanReferralSummary(
        uow=uow,
        clans=clans,
        players=players,
        referrals=referrals,
        clock=FakeClock(NOW),
    )
    return use_case, clans, players, referrals


class TestRunWeeklyClanReferralSummary:
    @pytest.mark.asyncio
    async def test_happy_path_single_referrer(self) -> None:
        use_case, clans, players, referrals = _build()
        clan = _make_clan(clan_id=1)
        clans.rows.append(clan)
        member = _make_player(player_id=10, tg_id=1010)
        new_1 = _make_player(player_id=20, tg_id=2020)
        new_2 = _make_player(player_id=21, tg_id=2021)
        players.rows.extend([member, new_1, new_2])
        referrals.clan_members.extend([(1, 10)])
        referrals.items.extend(
            [
                _make_referral(
                    ref_id=1,
                    referrer_id=10,
                    referred_id=20,
                    created_at=WINDOW_START + timedelta(hours=1),
                ),
                _make_referral(
                    ref_id=2,
                    referrer_id=10,
                    referred_id=21,
                    created_at=WINDOW_START + timedelta(hours=2),
                ),
            ],
        )

        result = await use_case.execute(RunWeeklyClanReferralSummaryInput(clan_id=1))

        assert isinstance(result, WeeklyClanReferralSummary)
        assert result.clan.id == 1
        assert result.total == 2
        assert len(result.top) == 1
        assert result.top[0].player.id == 10
        assert result.top[0].count == 2

    @pytest.mark.asyncio
    async def test_top_3_with_more_referrers(self) -> None:
        use_case, clans, players, referrals = _build()
        clans.rows.append(_make_clan(clan_id=1))
        # 4 реферера в клане; 1-й привёл 5, 2-й — 3, 3-й — 2, 4-й — 1.
        for i in (10, 11, 12, 13):
            players.rows.append(_make_player(player_id=i, tg_id=1000 + i))
            referrals.clan_members.append((1, i))
        # Рефералы:
        next_id = 100
        ref_id = 1
        items: list[Referral] = []
        # referrer 10 → 5
        for _ in range(5):
            invited_id = next_id
            next_id += 1
            players.rows.append(_make_player(player_id=invited_id, tg_id=invited_id))
            items.append(
                _make_referral(
                    ref_id=ref_id,
                    referrer_id=10,
                    referred_id=invited_id,
                    created_at=WINDOW_START + timedelta(hours=ref_id),
                ),
            )
            ref_id += 1
        # referrer 11 → 3
        for _ in range(3):
            invited_id = next_id
            next_id += 1
            players.rows.append(_make_player(player_id=invited_id, tg_id=invited_id))
            items.append(
                _make_referral(
                    ref_id=ref_id,
                    referrer_id=11,
                    referred_id=invited_id,
                    created_at=WINDOW_START + timedelta(hours=ref_id),
                ),
            )
            ref_id += 1
        # referrer 12 → 2
        for _ in range(2):
            invited_id = next_id
            next_id += 1
            players.rows.append(_make_player(player_id=invited_id, tg_id=invited_id))
            items.append(
                _make_referral(
                    ref_id=ref_id,
                    referrer_id=12,
                    referred_id=invited_id,
                    created_at=WINDOW_START + timedelta(hours=ref_id),
                ),
            )
            ref_id += 1
        # referrer 13 → 1
        invited_id = next_id
        players.rows.append(_make_player(player_id=invited_id, tg_id=invited_id))
        items.append(
            _make_referral(
                ref_id=ref_id,
                referrer_id=13,
                referred_id=invited_id,
                created_at=WINDOW_START + timedelta(hours=ref_id),
            ),
        )
        referrals.items.extend(items)

        result = await use_case.execute(RunWeeklyClanReferralSummaryInput(clan_id=1))

        assert isinstance(result, WeeklyClanReferralSummary)
        assert result.total == 11
        assert len(result.top) == 3
        assert [(t.player.id, t.count) for t in result.top] == [(10, 5), (11, 3), (12, 2)]

    @pytest.mark.asyncio
    async def test_returns_none_for_frozen_clan(self) -> None:
        use_case, clans, _players, referrals = _build()
        clans.rows.append(_make_clan(clan_id=1, status=ClanStatus.FROZEN))
        # Реферал есть, но клан заморожен — карточки не будет.
        referrals.clan_members.append((1, 10))
        referrals.items.append(
            _make_referral(
                ref_id=1,
                referrer_id=10,
                referred_id=20,
                created_at=WINDOW_START + timedelta(hours=1),
            ),
        )

        result = await use_case.execute(RunWeeklyClanReferralSummaryInput(clan_id=1))
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_week(self) -> None:
        use_case, clans, _players, referrals = _build()
        clans.rows.append(_make_clan(clan_id=1))
        referrals.clan_members.append((1, 10))
        # Рефералы есть, но они вне окна `[since, until)`.
        referrals.items.append(
            _make_referral(
                ref_id=1,
                referrer_id=10,
                referred_id=20,
                created_at=WINDOW_START - timedelta(seconds=1),
            ),
        )

        result = await use_case.execute(RunWeeklyClanReferralSummaryInput(clan_id=1))
        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_clan_raises_integrity_error(self) -> None:
        use_case, _clans, _players, _referrals = _build()
        with pytest.raises(IntegrityError, match="not found"):
            await use_case.execute(RunWeeklyClanReferralSummaryInput(clan_id=999))

    @pytest.mark.asyncio
    async def test_skips_deleted_player(self) -> None:
        # Запись `referrals` ссылается на отсутствующего игрока → пропуск.
        use_case, clans, players, referrals = _build()
        clans.rows.append(_make_clan(clan_id=1))
        player_present = _make_player(player_id=11, tg_id=1011)
        players.rows.append(player_present)
        # 10 — «удалён» (нет в players.rows), 11 — есть.
        referrals.clan_members.extend([(1, 10), (1, 11)])
        referrals.items.extend(
            [
                _make_referral(
                    ref_id=1,
                    referrer_id=10,
                    referred_id=20,
                    created_at=WINDOW_START + timedelta(hours=1),
                ),
                _make_referral(
                    ref_id=2,
                    referrer_id=11,
                    referred_id=21,
                    created_at=WINDOW_START + timedelta(hours=2),
                ),
            ],
        )

        result = await use_case.execute(RunWeeklyClanReferralSummaryInput(clan_id=1))
        assert isinstance(result, WeeklyClanReferralSummary)
        # total — суммарно по всем (включая отсутствующего 10);
        # top — только присутствующие.
        assert result.total == 2
        assert len(result.top) == 1
        assert result.top[0].player.id == 11

    @pytest.mark.asyncio
    async def test_returns_none_when_all_top_referrers_deleted(self) -> None:
        use_case, clans, players, referrals = _build()
        clans.rows.append(_make_clan(clan_id=1))
        # Реферер 10 «удалён» — players.rows пуст в части 10.
        del players.rows[:]
        referrals.clan_members.append((1, 10))
        referrals.items.append(
            _make_referral(
                ref_id=1,
                referrer_id=10,
                referred_id=20,
                created_at=WINDOW_START + timedelta(hours=1),
            ),
        )

        result = await use_case.execute(RunWeeklyClanReferralSummaryInput(clan_id=1))
        assert result is None

    @pytest.mark.asyncio
    async def test_window_boundary_is_half_open(self) -> None:
        use_case, clans, players, referrals = _build()
        clans.rows.append(_make_clan(clan_id=1))
        member = _make_player(player_id=10, tg_id=1010)
        ref_in = _make_player(player_id=21, tg_id=2021)
        ref_at_until = _make_player(player_id=22, tg_id=2022)
        players.rows.extend([member, ref_in, ref_at_until])
        referrals.clan_members.append((1, 10))
        referrals.items.extend(
            [
                _make_referral(
                    ref_id=1,
                    referrer_id=10,
                    referred_id=21,
                    created_at=WINDOW_START,  # граница since включительно.
                ),
                _make_referral(
                    ref_id=2,
                    referrer_id=10,
                    referred_id=22,
                    created_at=NOW,  # граница until — НЕ включается.
                ),
            ],
        )

        result = await use_case.execute(RunWeeklyClanReferralSummaryInput(clan_id=1))
        assert isinstance(result, WeeklyClanReferralSummary)
        assert result.total == 1
