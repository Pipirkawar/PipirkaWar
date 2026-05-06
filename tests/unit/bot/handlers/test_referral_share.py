"""Юнит-тесты handler `handle_referral_share` (Спринт 2.4.D-b)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.types import CallbackQuery, Chat

from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.bot.handlers.referral_share import handle_referral_share
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.forest import ForestRun, ForestRunStatus, NoDrop
from pipirik_wars.domain.player import Length, Player, PlayerStatus, Thickness, Username
from pipirik_wars.domain.pvp import (
    Duel,
    DuelMode,
    DuelOutcome,
    DuelState,
    DuelWinner,
    Position,
    RoundChoice,
    RoundOutcome,
)
from tests.fakes import (
    FakeDuelRepository,
    FakeForestRunRepository,
    FakeMessageBundle,
)

_NOW = datetime(2026, 5, 5, 9, 0, tzinfo=UTC)
_RU = Locale("ru")
_EN = Locale("en")


# ───────────── фикстуры ─────────────


def _bundle() -> IMessageBundle:
    return FakeMessageBundle()


def _identity(tg_user_id: int = 100, chat_id: int = 42) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=chat_id,
        chat_kind="private",
        language_code=None,
    )


def _player(
    *,
    pid: int = 1,
    tg_id: int = 100,
    username: str | None = "alice",
    length_cm: int = 25,
    thickness_level: int = 3,
) -> Player:
    return Player(
        id=pid,
        tg_id=tg_id,
        username=Username(value=username) if username else None,
        length=Length(cm=length_cm),
        thickness=Thickness(level=thickness_level),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _stub_players(*players: Player) -> MagicMock:
    repo = MagicMock()
    by_id = {p.id: p for p in players if p.id is not None}

    async def _by_id(*, player_id: int) -> Player | None:
        return by_id.get(player_id)

    repo.get_by_id = AsyncMock(side_effect=_by_id)
    return repo


def _stub_bot() -> MagicMock:
    bot = MagicMock(spec=Bot)
    bot.send_message = AsyncMock()
    return bot


def _callback(*, data: str | None, has_message: bool = True, chat_id: int = 42) -> MagicMock:
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.answer = AsyncMock()
    if has_message:
        cb.message = MagicMock()
        cb.message.chat = Chat(id=chat_id, type="private")
    else:
        cb.message = None
    return cb


def _outcome(
    *,
    p1_delta_cm: int = 0,
    p2_delta_cm: int = 0,
    winner: DuelWinner = DuelWinner.DRAW,
) -> DuelOutcome:
    rounds = tuple(
        RoundOutcome(
            p1_choice=RoundChoice(attack=Position.HIGH, block=Position.LOW),
            p2_choice=RoundChoice(attack=Position.LOW, block=Position.HIGH),
            p1_attack_blocked=False,
            p2_attack_blocked=False,
            p1_damage_to_p2=0,
            p2_damage_to_p1=0,
        )
        for _ in range(3)
    )
    return DuelOutcome(
        winner=winner,
        rounds=rounds,
        p1_delta_cm=p1_delta_cm,
        p2_delta_cm=p2_delta_cm,
        p1_total_dealt=0,
        p2_total_dealt=0,
    )


def _seed_duel(*, winner: DuelWinner, p1_delta_cm: int = 0, p2_delta_cm: int = 0) -> Duel:
    return Duel(
        id=None,
        challenger_id=1,
        challenged_id=2,
        mode=DuelMode.CHAT_THEN_GLOBAL,
        state=DuelState.COMPLETED,
        hit_pct=20,
        expected_rounds=3,
        created_at=_NOW,
        accepted_at=_NOW,
        completed_at=_NOW,
        cancelled_at=None,
        p1_initial_length_cm=25,
        p2_initial_length_cm=25,
        completed_rounds=(),
        pending_round=None,
        final_outcome=_outcome(
            p1_delta_cm=p1_delta_cm,
            p2_delta_cm=p2_delta_cm,
            winner=winner,
        ),
    )


def _seed_forest_run(*, run_id: int = 1, player_id: int = 1, length_delta_cm: int = 7) -> ForestRun:
    return ForestRun(
        id=run_id,
        player_id=player_id,
        status=ForestRunStatus.FINISHED,
        started_at=_NOW,
        ends_at=_NOW + timedelta(minutes=10),
        branch_name="normal",
        length_delta_cm=length_delta_cm,
        drop=NoDrop(),
        finished_at=_NOW + timedelta(minutes=10),
    )


# ─────────────── handle_referral_share ───────────────


@pytest.mark.asyncio
class TestHandleReferralShare:
    async def test_no_data_silently_returns(self) -> None:
        cb = _callback(data=None)
        bot = _stub_bot()
        await handle_referral_share(
            cb,
            cast(Bot, bot),
            _identity(),
            _stub_players(),
            FakeDuelRepository(),
            FakeForestRunRepository(),
            _bundle(),
            _RU,
        )
        bot.send_message.assert_not_awaited()

    async def test_no_identity_silently_returns(self) -> None:
        cb = _callback(data="ref-share:duel:1")
        bot = _stub_bot()
        await handle_referral_share(
            cb,
            cast(Bot, bot),
            None,
            _stub_players(),
            FakeDuelRepository(),
            FakeForestRunRepository(),
            _bundle(),
            _RU,
        )
        bot.send_message.assert_not_awaited()

    async def test_invalid_callback_data_answers_only(self) -> None:
        cb = _callback(data="ref-share:bad")
        bot = _stub_bot()
        await handle_referral_share(
            cb,
            cast(Bot, bot),
            _identity(),
            _stub_players(),
            FakeDuelRepository(),
            FakeForestRunRepository(),
            _bundle(),
            _RU,
        )
        bot.send_message.assert_not_awaited()
        cb.answer.assert_awaited_once()

    async def test_unknown_kind_in_callback_answers_only(self) -> None:
        cb = _callback(data="ref-share:caravan:1")
        bot = _stub_bot()
        await handle_referral_share(
            cb,
            cast(Bot, bot),
            _identity(),
            _stub_players(),
            FakeDuelRepository(),
            FakeForestRunRepository(),
            _bundle(),
            _RU,
        )
        bot.send_message.assert_not_awaited()
        cb.answer.assert_awaited_once()

    async def test_duel_not_found_no_send(self) -> None:
        cb = _callback(data="ref-share:duel:999")
        bot = _stub_bot()
        await handle_referral_share(
            cb,
            cast(Bot, bot),
            _identity(),
            _stub_players(),
            FakeDuelRepository(),
            FakeForestRunRepository(),
            _bundle(),
            _RU,
        )
        bot.send_message.assert_not_awaited()
        cb.answer.assert_awaited_once()

    async def test_forest_run_not_found_no_send(self) -> None:
        cb = _callback(data="ref-share:forest:999")
        bot = _stub_bot()
        await handle_referral_share(
            cb,
            cast(Bot, bot),
            _identity(),
            _stub_players(),
            FakeDuelRepository(),
            FakeForestRunRepository(),
            _bundle(),
            _RU,
        )
        bot.send_message.assert_not_awaited()
        cb.answer.assert_awaited_once()

    async def test_duel_victory_p1_sends_card_to_chat(self) -> None:
        cb = _callback(data="ref-share:duel:1", chat_id=999)
        bot = _stub_bot()
        p1 = _player(pid=1, tg_id=100, username="alice", length_cm=30)
        p2 = _player(pid=2, tg_id=200, username="bob", length_cm=20)
        duels = FakeDuelRepository()
        await duels.add(_seed_duel(winner=DuelWinner.P1, p1_delta_cm=5, p2_delta_cm=-5))
        await handle_referral_share(
            cb,
            cast(Bot, bot),
            _identity(tg_user_id=100),
            _stub_players(p1, p2),
            duels,
            FakeForestRunRepository(),
            _bundle(),
            _RU,
        )
        bot.send_message.assert_awaited_once()
        kwargs = bot.send_message.await_args.kwargs
        assert kwargs["chat_id"] == 999
        text = kwargs["text"]
        assert "ru:referral-share-duel-victory" in text
        assert "winner=@alice" in text
        assert "loser=@bob" in text
        assert "delta_cm=5" in text
        assert "winner_length_cm=30" in text
        assert "deeplink=t.me/pipirik_bot?start=ref_100" in text
        cb.answer.assert_awaited_once()

    async def test_duel_victory_p2_uses_p2_data(self) -> None:
        cb = _callback(data="ref-share:duel:1")
        bot = _stub_bot()
        p1 = _player(pid=1, tg_id=100, username="alice", length_cm=20)
        p2 = _player(pid=2, tg_id=200, username="bob", length_cm=30)
        duels = FakeDuelRepository()
        await duels.add(_seed_duel(winner=DuelWinner.P2, p1_delta_cm=-5, p2_delta_cm=5))
        await handle_referral_share(
            cb,
            cast(Bot, bot),
            _identity(tg_user_id=100),
            _stub_players(p1, p2),
            duels,
            FakeForestRunRepository(),
            _bundle(),
            _RU,
        )
        text = bot.send_message.await_args.kwargs["text"]
        assert "winner=@bob" in text
        assert "loser=@alice" in text
        assert "winner_length_cm=30" in text
        assert "delta_cm=5" in text

    async def test_duel_draw_uses_draw_template(self) -> None:
        cb = _callback(data="ref-share:duel:1")
        bot = _stub_bot()
        p1 = _player(pid=1, tg_id=100, username="alice")
        p2 = _player(pid=2, tg_id=200, username="bob")
        duels = FakeDuelRepository()
        await duels.add(_seed_duel(winner=DuelWinner.DRAW))
        await handle_referral_share(
            cb,
            cast(Bot, bot),
            _identity(tg_user_id=100),
            _stub_players(p1, p2),
            duels,
            FakeForestRunRepository(),
            _bundle(),
            _RU,
        )
        text = bot.send_message.await_args.kwargs["text"]
        assert "ru:referral-share-duel-draw" in text
        assert "p1=@alice" in text
        assert "p2=@bob" in text

    async def test_forest_share_sends_card(self) -> None:
        cb = _callback(data="ref-share:forest:1")
        bot = _stub_bot()
        p1 = _player(pid=1, tg_id=100, username="alice", length_cm=42)
        forest_runs = FakeForestRunRepository()
        # FakeForestRunRepository.add() requires id=None. Insert directly.
        forest_runs.rows.append(_seed_forest_run(run_id=1, player_id=1, length_delta_cm=7))
        await handle_referral_share(
            cb,
            cast(Bot, bot),
            _identity(tg_user_id=100),
            _stub_players(p1),
            FakeDuelRepository(),
            forest_runs,
            _bundle(),
            _RU,
        )
        bot.send_message.assert_awaited_once()
        text = bot.send_message.await_args.kwargs["text"]
        assert "ru:referral-share-forest" in text
        assert "player=@alice" in text
        assert "delta_cm=7" in text
        assert "length_cm=42" in text
        assert "deeplink=t.me/pipirik_bot?start=ref_100" in text

    async def test_forest_share_player_missing_no_send(self) -> None:
        cb = _callback(data="ref-share:forest:1")
        bot = _stub_bot()
        forest_runs = FakeForestRunRepository()
        forest_runs.rows.append(_seed_forest_run(run_id=1, player_id=1))
        await handle_referral_share(
            cb,
            cast(Bot, bot),
            _identity(tg_user_id=100),
            _stub_players(),  # пустой репозиторий игроков
            FakeDuelRepository(),
            forest_runs,
            _bundle(),
            _RU,
        )
        bot.send_message.assert_not_awaited()

    async def test_chat_id_falls_back_to_tg_identity_when_no_message(self) -> None:
        cb = _callback(data="ref-share:duel:1", has_message=False)
        bot = _stub_bot()
        p1 = _player(pid=1, tg_id=100, username="alice", length_cm=30)
        p2 = _player(pid=2, tg_id=200, username="bob", length_cm=20)
        duels = FakeDuelRepository()
        await duels.add(_seed_duel(winner=DuelWinner.P1, p1_delta_cm=5, p2_delta_cm=-5))
        await handle_referral_share(
            cb,
            cast(Bot, bot),
            _identity(tg_user_id=100, chat_id=777),
            _stub_players(p1, p2),
            duels,
            FakeForestRunRepository(),
            _bundle(),
            _RU,
        )
        bot.send_message.assert_awaited_once()
        kwargs = bot.send_message.await_args.kwargs
        assert kwargs["chat_id"] == 777

    async def test_send_failure_does_not_propagate(self) -> None:
        cb = _callback(data="ref-share:duel:1")
        bot = _stub_bot()
        bot.send_message = AsyncMock(side_effect=RuntimeError("network down"))
        p1 = _player(pid=1, tg_id=100, username="alice", length_cm=30)
        p2 = _player(pid=2, tg_id=200, username="bob", length_cm=20)
        duels = FakeDuelRepository()
        await duels.add(_seed_duel(winner=DuelWinner.P1, p1_delta_cm=5, p2_delta_cm=-5))
        # Не должно бросить исключение
        await handle_referral_share(
            cb,
            cast(Bot, bot),
            _identity(tg_user_id=100),
            _stub_players(p1, p2),
            duels,
            FakeForestRunRepository(),
            _bundle(),
            _RU,
        )
        cb.answer.assert_awaited_once()

    async def test_username_none_renders_dash(self) -> None:
        cb = _callback(data="ref-share:duel:1")
        bot = _stub_bot()
        p1 = _player(pid=1, tg_id=100, username=None, length_cm=30)
        p2 = _player(pid=2, tg_id=200, username="bob", length_cm=20)
        duels = FakeDuelRepository()
        await duels.add(_seed_duel(winner=DuelWinner.P1, p1_delta_cm=5, p2_delta_cm=-5))
        await handle_referral_share(
            cb,
            cast(Bot, bot),
            _identity(tg_user_id=100),
            _stub_players(p1, p2),
            duels,
            FakeForestRunRepository(),
            _bundle(),
            _RU,
        )
        text = bot.send_message.await_args.kwargs["text"]
        assert "winner=—" in text
