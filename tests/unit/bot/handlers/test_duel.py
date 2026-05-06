"""Юнит-тесты `/duel`-handler-ов и PvP-callback-ов (Спринты 2.1.E + 2.1.F.3).

Бэкфилл к 2.1.E (handler был ~11% покрыт) + новые тесты для F.3:
private-flow `/duel` → enqueue в global-lobby, новый `/duel_global` → matchmaking.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.types import CallbackQuery, Chat, Message, User

from pipirik_wars.application.dto.inputs import (
    AcceptDuelInput,
    CancelDuelInput,
    ChallengeDuelInput,
    MatchFromLobbyInput,
)
from pipirik_wars.application.i18n import IMessageBundle, IPlayerLocaleResolver, Locale
from pipirik_wars.application.pvp import (
    AcceptDuel,
    CancelDuel,
    ChallengeDuel,
    DuelMatched,
    EmptyLobby,
    IDuelLogTemplateProvider,
    LobbyEntryStale,
    MatchFromLobby,
    SubmitMove,
)
from pipirik_wars.application.pvp.accept_duel import DuelAccepted
from pipirik_wars.application.pvp.challenge_duel import DuelChallenged
from pipirik_wars.application.pvp.submit_move import MoveSubmitted
from pipirik_wars.bot.handlers.duel import (
    handle_cancel_duel,
    handle_duel,
    handle_duel_global,
    handle_pvp_accept,
    handle_pvp_attack,
    handle_pvp_block,
    handle_pvp_reject,
    handle_share_pvp_result,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.balance import PvpConfig, PvpDuel1v1Config, PvpMassDuelConfig
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerNotFoundError,
    PlayerStatus,
    Thickness,
    Username,
)
from pipirik_wars.domain.progression import AnticheatSoftBanError
from pipirik_wars.domain.pvp import (
    Duel,
    DuelLogTemplate,
    DuelMode,
    DuelNotFoundError,
    DuelOutcome,
    DuelState,
    DuelWinner,
    InvalidDuelStateError,
    MoveAlreadySubmittedError,
    NotADuelParticipantError,
    PendingRound,
    Position,
    PvpRequirementsNotMetError,
    RoundChoice,
    RoundOutcome,
    RoundOutcomeKind,
    SelfChallengeError,
)
from pipirik_wars.domain.security import LockAlreadyHeldError
from pipirik_wars.domain.shared.ports import IRandom
from tests.fakes import FakeBalanceConfig, FakeDuelRepository, FakeMessageBundle, FakeRandom
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 5, 9, 0, tzinfo=UTC)
_RU = Locale("ru")
_EN = Locale("en")


# ─────────────────────── фикстуры/билдеры ───────────────────────


def _bundle() -> IMessageBundle:
    return FakeMessageBundle()


def _balance(
    *,
    global_lobby_ttl_minutes: int = 10,
    chat_to_global_promotion_minutes: int = 3,
    min_length_cm: int = 20,
    min_thickness_level: int = 2,
) -> IBalanceConfig:
    base = build_valid_balance()
    cfg = base.model_copy(
        update={
            "pvp": PvpConfig(
                duel_1v1=PvpDuel1v1Config(
                    rounds=3,
                    hit_pct=10,
                    min_length_cm=min_length_cm,
                    min_thickness_level=min_thickness_level,
                    global_lobby_ttl_minutes=global_lobby_ttl_minutes,
                    chat_to_global_promotion_minutes=chat_to_global_promotion_minutes,
                    round_timer_seconds=45,
                ),
                mass_duel=PvpMassDuelConfig(
                    cooldown_hours=6,
                    min_length_cm=20,
                    min_thickness_level=2,
                    min_clan_members=1,
                ),
            ),
        }
    )
    return FakeBalanceConfig(cfg)


def _identity(chat_kind: str = "private", tg_user_id: int = 100) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=42,
        chat_kind=chat_kind,
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


def _duel(
    *,
    duel_id: int = 11,
    mode: DuelMode = DuelMode.CHAT_THEN_GLOBAL,
    state: DuelState = DuelState.PENDING_ACCEPT,
    challenger_id: int = 1,
    challenged_id: int | None = 2,
    pending: PendingRound | None = None,
    final: DuelOutcome | None = None,
    completed_rounds: tuple[RoundOutcome, ...] = (),
) -> Duel:
    return Duel(
        id=duel_id,
        challenger_id=challenger_id,
        challenged_id=challenged_id,
        mode=mode,
        state=state,
        hit_pct=20,
        expected_rounds=3,
        created_at=_NOW,
        accepted_at=_NOW if state is not DuelState.PENDING_ACCEPT else None,
        completed_at=_NOW if state is DuelState.COMPLETED else None,
        cancelled_at=None,
        p1_initial_length_cm=25,
        p2_initial_length_cm=25,
        completed_rounds=completed_rounds,
        pending_round=pending,
        final_outcome=final,
    )


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
        rounds=rounds,
        p1_total_dealt=0,
        p2_total_dealt=0,
        p1_delta_cm=p1_delta_cm,
        p2_delta_cm=p2_delta_cm,
        winner=winner,
    )


def _msg(
    *,
    chat_type: str = "private",
    from_id: int = 100,
    from_username: str | None = "alice",
    reply_user: User | None = None,
) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.chat = Chat(id=42, type=chat_type)
    msg.answer = AsyncMock()
    msg.from_user = User(
        id=from_id,
        is_bot=False,
        first_name="Алиса",
        username=from_username,
    )
    if reply_user is not None:
        reply = MagicMock(spec=Message)
        reply.from_user = reply_user
        msg.reply_to_message = reply
    else:
        msg.reply_to_message = None
    return msg


def _stub_challenge(
    *,
    duel: Duel | None = None,
    error: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=ChallengeDuel)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    use_case.execute = AsyncMock(
        return_value=DuelChallenged(duel=duel if duel is not None else _duel()),
    )
    return use_case


def _stub_accept(
    *,
    duel: Duel | None = None,
    error: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=AcceptDuel)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    accepted = (
        duel
        if duel is not None
        else _duel(
            state=DuelState.IN_PROGRESS,
            pending=PendingRound(round_num=1, p1_choice=None, p2_choice=None),
        )
    )
    use_case.execute = AsyncMock(return_value=DuelAccepted(duel=accepted))
    return use_case


def _stub_cancel(*, error: BaseException | None = None) -> MagicMock:
    use_case = MagicMock(spec=CancelDuel)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
    else:
        use_case.execute = AsyncMock(return_value=None)
    return use_case


def _stub_match(
    *,
    result: DuelMatched | EmptyLobby | LobbyEntryStale | None = None,
    error: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=MatchFromLobby)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    if result is None:
        result = EmptyLobby()
    use_case.execute = AsyncMock(return_value=result)
    return use_case


def _stub_submit(
    *,
    duel: Duel | None = None,
    duel_completed: bool = False,
    error: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=SubmitMove)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    base = (
        duel
        if duel is not None
        else _duel(
            state=DuelState.IN_PROGRESS,
            pending=PendingRound(round_num=1, p1_choice=None, p2_choice=None),
        )
    )
    use_case.execute = AsyncMock(
        return_value=MoveSubmitted(duel=base, duel_completed=duel_completed),
    )
    return use_case


def _stub_players(*players: Player) -> MagicMock:
    repo = MagicMock()
    by_id = {p.id: p for p in players if p.id is not None}

    async def _by_id(*, player_id: int) -> Player | None:
        return by_id.get(player_id)

    repo.get_by_id = AsyncMock(side_effect=_by_id)
    repo.get_by_tg_id = AsyncMock(
        side_effect=lambda tg_id: next(
            (p for p in players if p.tg_id == tg_id),
            None,
        )
    )
    return repo


def _stub_locale_resolver(default: Locale = _RU) -> MagicMock:
    res = MagicMock(spec=IPlayerLocaleResolver)

    async def _resolve(_tg_id: int) -> Locale:
        return default

    res.resolve_for_tg_id = AsyncMock(side_effect=_resolve)
    return res


def _stub_bot() -> MagicMock:
    bot = MagicMock(spec=Bot)
    bot.send_message = AsyncMock()
    return bot


def _callback(*, data: str | None, has_message: bool = True) -> MagicMock:
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.answer = AsyncMock()
    if has_message:
        cb.message = MagicMock()
        cb.message.edit_reply_markup = AsyncMock()
        cb.message.edit_text = AsyncMock()
        cb.message.chat = Chat(id=42, type="private")
    else:
        cb.message = None
    return cb


def _command(args: str | None = None) -> MagicMock:
    obj = MagicMock()
    obj.args = args
    return obj


# ─────────────────────── /duel ───────────────────────


@pytest.mark.asyncio
class TestHandleDuel:
    async def test_no_identity_returns_silently(self) -> None:
        msg = _msg()
        challenge = _stub_challenge()

        await handle_duel(
            cast(Message, msg),
            _command(),
            None,
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        msg.answer.assert_not_awaited()
        challenge.execute.assert_not_awaited()

    async def test_private_no_reply_calls_challenge_global_only(self) -> None:
        msg = _msg(chat_type="private")
        challenge = _stub_challenge(duel=_duel(mode=DuelMode.GLOBAL_ONLY, challenged_id=None))

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("private"),
            cast(ChallengeDuel, challenge),
            _balance(global_lobby_ttl_minutes=7),
            _bundle(),
            _RU,
        )

        challenge.execute.assert_awaited_once()
        called: ChallengeDuelInput = challenge.execute.await_args.args[0]
        assert called.mode == "global_only"
        assert called.challenged_tg_id is None
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert "ru:duel-global-enqueued" in sent
        assert "duel_id=11" in sent
        assert "ttl_minutes=7" in sent

    async def test_private_no_reply_player_not_found(self) -> None:
        msg = _msg(chat_type="private")
        challenge = _stub_challenge(error=PlayerNotFoundError(tg_id=100))

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("private"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-not-registered")

    async def test_private_no_reply_requirements_length(self) -> None:
        msg = _msg(chat_type="private")
        challenge = _stub_challenge(
            error=PvpRequirementsNotMetError(
                tg_id=100,
                requirement="length",
                required=20,
                actual=5,
            ),
        )

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("private"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        sent = msg.answer.await_args.args[0]
        assert "ru:duel-requirements-not-met" in sent
        assert "min_length_cm=20" in sent

    async def test_private_no_reply_requirements_thickness(self) -> None:
        msg = _msg(chat_type="private")
        challenge = _stub_challenge(
            error=PvpRequirementsNotMetError(
                tg_id=100,
                requirement="thickness",
                required=2,
                actual=1,
            ),
        )

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("private"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        sent = msg.answer.await_args.args[0]
        assert "ru:duel-requirements-not-met" in sent
        assert "min_thickness_level=2" in sent

    async def test_private_no_reply_anticheat_blocked(self) -> None:
        msg = _msg(chat_type="private")
        until = _NOW + timedelta(hours=1)
        challenge = _stub_challenge(
            error=AnticheatSoftBanError(tg_id=100, banned_until=until),
        )

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("private"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _EN,
        )

        sent = msg.answer.await_args.args[0]
        assert "en:duel-anticheat-blocked" in sent

    async def test_private_no_reply_lock_already_held(self) -> None:
        msg = _msg(chat_type="private")
        challenge = _stub_challenge(
            error=LockAlreadyHeldError(actor_kind="player", actor_id=1),
        )

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("private"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-lock-already-held")

    async def test_group_no_reply_returns_usage(self) -> None:
        msg = _msg(chat_type="group")
        challenge = _stub_challenge()

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("group"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-usage")
        challenge.execute.assert_not_awaited()

    async def test_supergroup_no_reply_returns_usage(self) -> None:
        msg = _msg(chat_type="supergroup")
        challenge = _stub_challenge()

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("supergroup"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _EN,
        )

        msg.answer.assert_awaited_once_with("en:duel-usage")

    async def test_reply_in_private_returns_usage(self) -> None:
        # Reply на сообщение в ЛС — не поддерживаем (ЛС с ботом не имеет других
        # пользователей для reply, но защитный код всё равно вернёт usage).
        target = User(id=200, is_bot=False, first_name="Bob")
        msg = _msg(chat_type="private", reply_user=target)
        challenge = _stub_challenge()

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("private"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-usage")
        challenge.execute.assert_not_awaited()

    async def test_reply_to_bot_returns_target_is_bot(self) -> None:
        target = User(id=999, is_bot=True, first_name="Bot")
        msg = _msg(chat_type="group", reply_user=target)
        challenge = _stub_challenge()

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("group"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-target-is-bot")

    async def test_reply_to_self_returns_self_challenge(self) -> None:
        target = User(id=100, is_bot=False, first_name="Алиса")
        msg = _msg(chat_type="group", from_id=100, reply_user=target)
        challenge = _stub_challenge()

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("group", tg_user_id=100),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-self-challenge")

    async def test_chat_then_global_default_when_reply(self) -> None:
        target = User(id=200, is_bot=False, first_name="Bob", username="bob")
        msg = _msg(chat_type="group", reply_user=target)
        challenge = _stub_challenge(duel=_duel(mode=DuelMode.CHAT_THEN_GLOBAL))

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("group"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        called: ChallengeDuelInput = challenge.execute.await_args.args[0]
        assert called.mode == "chat_then_global"
        assert called.challenged_tg_id == 200

    async def test_chat_only_when_chat_arg(self) -> None:
        target = User(id=200, is_bot=False, first_name="Bob", username="bob")
        msg = _msg(chat_type="group", reply_user=target)
        challenge = _stub_challenge(duel=_duel(mode=DuelMode.CHAT_ONLY))

        await handle_duel(
            cast(Message, msg),
            _command(args="chat"),
            _identity("group"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        called: ChallengeDuelInput = challenge.execute.await_args.args[0]
        assert called.mode == "chat_only"

    async def test_self_challenge_error_via_use_case(self) -> None:
        target = User(id=200, is_bot=False, first_name="Bob")
        msg = _msg(chat_type="group", reply_user=target)
        challenge = _stub_challenge(error=SelfChallengeError(player_id=1))

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("group"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-self-challenge")

    async def test_reply_player_not_found_for_target(self) -> None:
        target = User(id=200, is_bot=False, first_name="Bob")
        msg = _msg(chat_type="group", reply_user=target)
        challenge = _stub_challenge(error=PlayerNotFoundError(tg_id=200))

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("group", tg_user_id=100),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-target-not-registered")

    async def test_reply_player_not_found_for_challenger(self) -> None:
        target = User(id=200, is_bot=False, first_name="Bob")
        msg = _msg(chat_type="group", reply_user=target)
        challenge = _stub_challenge(error=PlayerNotFoundError(tg_id=100))

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("group", tg_user_id=100),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-not-registered")

    async def test_reply_pvp_requirements_length(self) -> None:
        target = User(id=200, is_bot=False, first_name="Bob")
        msg = _msg(chat_type="group", reply_user=target)
        challenge = _stub_challenge(
            error=PvpRequirementsNotMetError(
                tg_id=100,
                requirement="length",
                required=20,
                actual=5,
            ),
        )

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("group"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        sent = msg.answer.await_args.args[0]
        assert "ru:duel-requirements-not-met" in sent

    async def test_reply_anticheat_blocked(self) -> None:
        target = User(id=200, is_bot=False, first_name="Bob")
        msg = _msg(chat_type="group", reply_user=target)
        until = _NOW + timedelta(hours=1)
        challenge = _stub_challenge(
            error=AnticheatSoftBanError(tg_id=100, banned_until=until),
        )

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("group"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        sent = msg.answer.await_args.args[0]
        assert "ru:duel-anticheat-blocked" in sent

    async def test_reply_lock_already_held(self) -> None:
        target = User(id=200, is_bot=False, first_name="Bob")
        msg = _msg(chat_type="group", reply_user=target)
        challenge = _stub_challenge(
            error=LockAlreadyHeldError(actor_kind="player", actor_id=1),
        )

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("group"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-lock-already-held")

    async def test_reply_success_emits_challenge_card(self) -> None:
        target = User(id=200, is_bot=False, first_name="Bob", username="bob")
        msg = _msg(chat_type="group", from_username="alice", reply_user=target)
        challenge = _stub_challenge(duel=_duel(mode=DuelMode.CHAT_THEN_GLOBAL))

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("group"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert "ru:duel-challenge-chat-then-global" in sent
        assert "challenger=@alice" in sent
        assert "challenged=@bob" in sent

    async def test_reply_success_chat_only_emits_chat_only_card(self) -> None:
        target = User(id=200, is_bot=False, first_name="Bob", username="bob")
        msg = _msg(chat_type="group", from_username="alice", reply_user=target)
        challenge = _stub_challenge(duel=_duel(mode=DuelMode.CHAT_ONLY))

        await handle_duel(
            cast(Message, msg),
            _command(args="chat"),
            _identity("group"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        sent = msg.answer.await_args.args[0]
        assert "ru:duel-challenge-chat" in sent

    async def test_reply_success_username_fallback_to_dash(self) -> None:
        target = User(id=200, is_bot=False, first_name="Bob", username=None)
        msg = _msg(chat_type="group", from_username=None, reply_user=target)
        challenge = _stub_challenge(duel=_duel(mode=DuelMode.CHAT_THEN_GLOBAL))

        await handle_duel(
            cast(Message, msg),
            _command(),
            _identity("group"),
            cast(ChallengeDuel, challenge),
            _balance(),
            _bundle(),
            _RU,
        )

        sent = msg.answer.await_args.args[0]
        assert "challenger=—" in sent
        assert "challenged=—" in sent


# ─────────────────────── /duel_global ───────────────────────


@pytest.mark.asyncio
class TestHandleDuelGlobal:
    async def test_no_identity_returns_silently(self) -> None:
        msg = _msg(chat_type="private")
        match = _stub_match()

        await handle_duel_global(
            cast(Message, msg),
            cast(Bot, _stub_bot()),
            None,
            cast(MatchFromLobby, match),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        match.execute.assert_not_awaited()
        msg.answer.assert_not_awaited()

    async def test_non_private_chat_returns_only_in_private(self) -> None:
        msg = _msg(chat_type="group")
        match = _stub_match()

        await handle_duel_global(
            cast(Message, msg),
            cast(Bot, _stub_bot()),
            _identity("group"),
            cast(MatchFromLobby, match),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-global-only-in-private")
        match.execute.assert_not_awaited()

    async def test_supergroup_returns_only_in_private(self) -> None:
        msg = _msg(chat_type="supergroup")
        match = _stub_match()

        await handle_duel_global(
            cast(Message, msg),
            cast(Bot, _stub_bot()),
            _identity("supergroup"),
            cast(MatchFromLobby, match),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _EN,
        )

        msg.answer.assert_awaited_once_with("en:duel-global-only-in-private")

    async def test_empty_lobby_returns_global_empty(self) -> None:
        msg = _msg(chat_type="private")
        match = _stub_match(result=EmptyLobby())

        await handle_duel_global(
            cast(Message, msg),
            cast(Bot, _stub_bot()),
            _identity("private"),
            cast(MatchFromLobby, match),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        match.execute.assert_awaited_once()
        called: MatchFromLobbyInput = match.execute.await_args.args[0]
        assert called.accepter_tg_id == 100
        msg.answer.assert_awaited_once_with("ru:duel-global-empty")

    async def test_lobby_entry_stale_returns_global_empty(self) -> None:
        msg = _msg(chat_type="private")
        match = _stub_match(result=LobbyEntryStale(reason="self_challenge"))

        await handle_duel_global(
            cast(Message, msg),
            cast(Bot, _stub_bot()),
            _identity("private"),
            cast(MatchFromLobby, match),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-global-empty")

    async def test_player_not_found_returns_not_registered(self) -> None:
        msg = _msg(chat_type="private")
        match = _stub_match(error=PlayerNotFoundError(tg_id=100))

        await handle_duel_global(
            cast(Message, msg),
            cast(Bot, _stub_bot()),
            _identity("private"),
            cast(MatchFromLobby, match),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-not-registered")

    async def test_pvp_requirements_returns_requirements(self) -> None:
        msg = _msg(chat_type="private")
        match = _stub_match(
            error=PvpRequirementsNotMetError(
                tg_id=100,
                requirement="length",
                required=20,
                actual=5,
            ),
        )

        await handle_duel_global(
            cast(Message, msg),
            cast(Bot, _stub_bot()),
            _identity("private"),
            cast(MatchFromLobby, match),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        sent = msg.answer.await_args.args[0]
        assert "ru:duel-requirements-not-met" in sent

    async def test_anticheat_blocked_returns_anticheat(self) -> None:
        msg = _msg(chat_type="private")
        until = _NOW + timedelta(hours=1)
        match = _stub_match(
            error=AnticheatSoftBanError(tg_id=100, banned_until=until),
        )

        await handle_duel_global(
            cast(Message, msg),
            cast(Bot, _stub_bot()),
            _identity("private"),
            cast(MatchFromLobby, match),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _EN,
        )

        sent = msg.answer.await_args.args[0]
        assert "en:duel-anticheat-blocked" in sent

    async def test_lock_already_held(self) -> None:
        msg = _msg(chat_type="private")
        match = _stub_match(
            error=LockAlreadyHeldError(actor_kind="player", actor_id=1),
        )

        await handle_duel_global(
            cast(Message, msg),
            cast(Bot, _stub_bot()),
            _identity("private"),
            cast(MatchFromLobby, match),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-lock-already-held")

    async def test_matched_sends_text_and_broadcasts_attack_prompt(self) -> None:
        msg = _msg(chat_type="private", from_id=200, from_username="bob")
        bot = _stub_bot()
        challenger = _player(pid=1, tg_id=100, username="alice")
        accepter = _player(pid=2, tg_id=200, username="bob")
        duel = _duel(
            challenger_id=1,
            challenged_id=2,
            mode=DuelMode.GLOBAL_ONLY,
            state=DuelState.IN_PROGRESS,
            pending=PendingRound(round_num=1, p1_choice=None, p2_choice=None),
        )
        match = _stub_match(result=DuelMatched(duel=duel))

        await handle_duel_global(
            cast(Message, msg),
            cast(Bot, bot),
            _identity("private", tg_user_id=200),
            cast(MatchFromLobby, match),
            _stub_players(challenger, accepter),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert "ru:duel-global-matched" in sent
        assert "challenger=@alice" in sent
        # broadcast: attack-prompt отправлен обоим (challenger + accepter)
        assert bot.send_message.await_count == 2


# ─────────────────────── /cancel_duel ───────────────────────


@pytest.mark.asyncio
class TestHandleCancelDuel:
    async def test_no_identity_returns_silently(self) -> None:
        msg = _msg(chat_type="private")
        cancel = _stub_cancel()

        await handle_cancel_duel(
            cast(Message, msg),
            _command(args="11"),
            None,
            cast(CancelDuel, cancel),
            _bundle(),
            _RU,
        )

        cancel.execute.assert_not_awaited()
        msg.answer.assert_not_awaited()

    async def test_no_args_returns_usage(self) -> None:
        msg = _msg(chat_type="private")
        cancel = _stub_cancel()

        await handle_cancel_duel(
            cast(Message, msg),
            _command(args=""),
            _identity("private"),
            cast(CancelDuel, cancel),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-cancel-usage")
        cancel.execute.assert_not_awaited()

    async def test_invalid_id_returns_usage(self) -> None:
        msg = _msg(chat_type="private")
        cancel = _stub_cancel()

        await handle_cancel_duel(
            cast(Message, msg),
            _command(args="abc"),
            _identity("private"),
            cast(CancelDuel, cancel),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-cancel-usage")

    async def test_negative_id_returns_usage(self) -> None:
        msg = _msg(chat_type="private")
        cancel = _stub_cancel()

        await handle_cancel_duel(
            cast(Message, msg),
            _command(args="-5"),
            _identity("private"),
            cast(CancelDuel, cancel),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-cancel-usage")

    async def test_duel_not_found_returns_usage(self) -> None:
        msg = _msg(chat_type="private")
        cancel = _stub_cancel(error=DuelNotFoundError(duel_id=11))

        await handle_cancel_duel(
            cast(Message, msg),
            _command(args="11"),
            _identity("private"),
            cast(CancelDuel, cancel),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-cancel-usage")

    async def test_not_participant_returns_usage(self) -> None:
        msg = _msg(chat_type="private")
        cancel = _stub_cancel(error=NotADuelParticipantError(player_id=1))

        await handle_cancel_duel(
            cast(Message, msg),
            _command(args="11"),
            _identity("private"),
            cast(CancelDuel, cancel),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-cancel-usage")

    async def test_invalid_state_returns_usage(self) -> None:
        msg = _msg(chat_type="private")
        cancel = _stub_cancel(
            error=InvalidDuelStateError(
                expected=DuelState.PENDING_ACCEPT,
                actual=DuelState.IN_PROGRESS,
                op="cancel",
            ),
        )

        await handle_cancel_duel(
            cast(Message, msg),
            _command(args="11"),
            _identity("private"),
            cast(CancelDuel, cancel),
            _bundle(),
            _RU,
        )

        msg.answer.assert_awaited_once_with("ru:duel-cancel-usage")

    async def test_success_returns_cancelled(self) -> None:
        msg = _msg(chat_type="private", from_username="alice")
        cancel = _stub_cancel()

        await handle_cancel_duel(
            cast(Message, msg),
            _command(args="11 garbage"),
            _identity("private"),
            cast(CancelDuel, cancel),
            _bundle(),
            _RU,
        )

        cancel.execute.assert_awaited_once()
        called: CancelDuelInput = cancel.execute.await_args.args[0]
        assert called.duel_id == 11
        sent = msg.answer.await_args.args[0]
        assert "ru:duel-cancelled" in sent
        assert "challenger=@alice" in sent


# ─────────────────────── pvp-accept callback ───────────────────────


@pytest.mark.asyncio
class TestHandlePvpAccept:
    async def test_no_data_returns_silently(self) -> None:
        cb = _callback(data=None)
        accept = _stub_accept()

        await handle_pvp_accept(
            cb,
            cast(Bot, _stub_bot()),
            _identity(),
            cast(AcceptDuel, accept),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        accept.execute.assert_not_awaited()

    async def test_invalid_callback_data_outdated(self) -> None:
        cb = _callback(data="pvp-accept:bad")
        accept = _stub_accept()

        await handle_pvp_accept(
            cb,
            cast(Bot, _stub_bot()),
            _identity(),
            cast(AcceptDuel, accept),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:duel-toast-outdated"
        accept.execute.assert_not_awaited()

    async def test_duel_not_found(self) -> None:
        cb = _callback(data="pvp-accept:11")
        accept = _stub_accept(error=DuelNotFoundError(duel_id=11))

        await handle_pvp_accept(
            cb,
            cast(Bot, _stub_bot()),
            _identity(),
            cast(AcceptDuel, accept),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:duel-toast-not-found"
        cb.message.edit_reply_markup.assert_awaited_once()

    async def test_not_participant(self) -> None:
        cb = _callback(data="pvp-accept:11")
        accept = _stub_accept(error=NotADuelParticipantError(player_id=1))

        await handle_pvp_accept(
            cb,
            cast(Bot, _stub_bot()),
            _identity(),
            cast(AcceptDuel, accept),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        cb.answer.assert_awaited_once()
        toast = cb.answer.await_args.args[0]
        assert toast == "ru:duel-toast-not-participant"
        cb.message.edit_reply_markup.assert_not_awaited()

    async def test_invalid_state(self) -> None:
        cb = _callback(data="pvp-accept:11")
        accept = _stub_accept(
            error=InvalidDuelStateError(
                expected=DuelState.PENDING_ACCEPT,
                actual=DuelState.CANCELLED,
                op="accept",
            ),
        )

        await handle_pvp_accept(
            cb,
            cast(Bot, _stub_bot()),
            _identity(),
            cast(AcceptDuel, accept),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:duel-toast-invalid-state"

    async def test_pvp_requirements_not_met(self) -> None:
        cb = _callback(data="pvp-accept:11")
        accept = _stub_accept(
            error=PvpRequirementsNotMetError(
                tg_id=100,
                requirement="length",
                required=20,
                actual=5,
            ),
        )

        await handle_pvp_accept(
            cb,
            cast(Bot, _stub_bot()),
            _identity(),
            cast(AcceptDuel, accept),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert "ru:duel-requirements-not-met" in toast

    async def test_lock_already_held(self) -> None:
        cb = _callback(data="pvp-accept:11")
        accept = _stub_accept(
            error=LockAlreadyHeldError(actor_kind="player", actor_id=1),
        )

        await handle_pvp_accept(
            cb,
            cast(Bot, _stub_bot()),
            _identity(),
            cast(AcceptDuel, accept),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:duel-lock-already-held"

    async def test_success_broadcasts_to_both_players(self) -> None:
        cb = _callback(data="pvp-accept:11")
        bot = _stub_bot()
        p1 = _player(pid=1, tg_id=100, username="alice")
        p2 = _player(pid=2, tg_id=200, username="bob")
        duel = _duel(
            challenger_id=1,
            challenged_id=2,
            state=DuelState.IN_PROGRESS,
            pending=PendingRound(round_num=1, p1_choice=None, p2_choice=None),
        )
        accept = _stub_accept(duel=duel)

        await handle_pvp_accept(
            cb,
            cast(Bot, bot),
            _identity(tg_user_id=200),
            cast(AcceptDuel, accept),
            _stub_players(p1, p2),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        accept.execute.assert_awaited_once()
        called: AcceptDuelInput = accept.execute.await_args.args[0]
        assert called.duel_id == 11
        toast = cb.answer.await_args.args[0]
        assert toast == "ru:duel-toast-accepted"
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        cb.message.edit_text.assert_awaited_once()
        # Broadcast to both players
        assert bot.send_message.await_count == 2


# ─────────────────────── pvp-reject callback ───────────────────────


@pytest.mark.asyncio
class TestHandlePvpReject:
    async def test_no_data_returns_silently(self) -> None:
        cb = _callback(data=None)

        await handle_pvp_reject(cb, _identity(), _bundle(), _RU)

        cb.answer.assert_not_awaited()

    async def test_invalid_data_returns_outdated(self) -> None:
        cb = _callback(data="pvp-reject:bad")

        await handle_pvp_reject(cb, _identity(), _bundle(), _RU)

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:duel-toast-outdated"

    async def test_success_toast(self) -> None:
        cb = _callback(data="pvp-reject:11")

        await handle_pvp_reject(cb, _identity(), _bundle(), _RU)

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:duel-toast-rejected"
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)


# ─────────────────────── pvp-attack callback ───────────────────────


@pytest.mark.asyncio
class TestHandlePvpAttack:
    async def test_no_data_returns_silently(self) -> None:
        cb = _callback(data=None)

        await handle_pvp_attack(cb, _identity(), _bundle(), _RU)

        cb.answer.assert_not_awaited()

    async def test_invalid_data_returns_outdated(self) -> None:
        cb = _callback(data="pvp-attack:bad")

        await handle_pvp_attack(cb, _identity(), _bundle(), _RU)

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:duel-toast-outdated"

    async def test_success_shows_block_keyboard(self) -> None:
        cb = _callback(data="pvp-attack:11:1:high")

        await handle_pvp_attack(cb, _identity(), _bundle(), _RU)

        cb.answer.assert_awaited_once()
        cb.message.edit_text.assert_awaited_once()
        sent = cb.message.edit_text.await_args.args[0]
        assert "ru:duel-round-block-prompt" in sent
        assert "round_num=1" in sent
        assert "attack=high" in sent
        cb.message.edit_reply_markup.assert_awaited_once()


# ─────────────────────── pvp-block callback ───────────────────────


@pytest.mark.asyncio
class TestHandlePvpBlock:
    async def test_no_data_returns_silently(self) -> None:
        cb = _callback(data=None)
        submit = _stub_submit()

        await handle_pvp_block(
            cb,
            cast(Bot, _stub_bot()),
            _identity(),
            cast(SubmitMove, submit),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        submit.execute.assert_not_awaited()

    async def test_invalid_data_returns_outdated(self) -> None:
        cb = _callback(data="pvp-block:bad")
        submit = _stub_submit()

        await handle_pvp_block(
            cb,
            cast(Bot, _stub_bot()),
            _identity(),
            cast(SubmitMove, submit),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:duel-toast-outdated"

    async def test_duel_not_found(self) -> None:
        cb = _callback(data="pvp-block:11:1:high:low")
        submit = _stub_submit(error=DuelNotFoundError(duel_id=11))

        await handle_pvp_block(
            cb,
            cast(Bot, _stub_bot()),
            _identity(),
            cast(SubmitMove, submit),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:duel-toast-not-found"

    async def test_not_participant(self) -> None:
        cb = _callback(data="pvp-block:11:1:high:low")
        submit = _stub_submit(
            error=NotADuelParticipantError(player_id=1),
        )

        await handle_pvp_block(
            cb,
            cast(Bot, _stub_bot()),
            _identity(),
            cast(SubmitMove, submit),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:duel-toast-not-participant"

    async def test_invalid_state(self) -> None:
        cb = _callback(data="pvp-block:11:1:high:low")
        submit = _stub_submit(
            error=InvalidDuelStateError(
                expected=DuelState.IN_PROGRESS,
                actual=DuelState.CANCELLED,
                op="submit",
            ),
        )

        await handle_pvp_block(
            cb,
            cast(Bot, _stub_bot()),
            _identity(),
            cast(SubmitMove, submit),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:duel-toast-invalid-state"

    async def test_already_submitted(self) -> None:
        cb = _callback(data="pvp-block:11:1:high:low")
        submit = _stub_submit(
            error=MoveAlreadySubmittedError(player_id=1, round_num=1),
        )

        await handle_pvp_block(
            cb,
            cast(Bot, _stub_bot()),
            _identity(),
            cast(SubmitMove, submit),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert toast == "ru:duel-toast-already-submitted"

    async def test_anticheat_blocked(self) -> None:
        cb = _callback(data="pvp-block:11:1:high:low")
        until = _NOW + timedelta(hours=1)
        submit = _stub_submit(
            error=AnticheatSoftBanError(tg_id=100, banned_until=until),
        )

        await handle_pvp_block(
            cb,
            cast(Bot, _stub_bot()),
            _identity(),
            cast(SubmitMove, submit),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        toast = cb.answer.await_args.args[0]
        assert "ru:duel-anticheat-blocked" in toast

    async def test_round_open_shows_waiting(self) -> None:
        cb = _callback(data="pvp-block:11:1:high:low")
        bot = _stub_bot()
        # Раунд ещё открыт: pending_round.round_num == 1 (не сдвинулся)
        duel = _duel(
            state=DuelState.IN_PROGRESS,
            pending=PendingRound(
                round_num=1,
                p1_choice=RoundChoice(attack=Position.HIGH, block=Position.LOW),
                p2_choice=None,
            ),
        )
        submit = _stub_submit(duel=duel, duel_completed=False)

        await handle_pvp_block(
            cb,
            cast(Bot, bot),
            _identity(),
            cast(SubmitMove, submit),
            _stub_players(),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        cb.message.edit_text.assert_awaited_once()
        sent = cb.message.edit_text.await_args.args[0]
        assert "ru:duel-round-waiting" in sent
        # broadcast не делался
        bot.send_message.assert_not_awaited()

    async def test_round_closed_broadcasts_next_attack(self) -> None:
        cb = _callback(data="pvp-block:11:1:high:low")
        bot = _stub_bot()
        p1 = _player(pid=1, tg_id=100, username="alice")
        p2 = _player(pid=2, tg_id=200, username="bob")
        # Раунд 1 закрыт → pending_round.round_num=2
        duel = _duel(
            challenger_id=1,
            challenged_id=2,
            state=DuelState.IN_PROGRESS,
            pending=PendingRound(round_num=2, p1_choice=None, p2_choice=None),
        )
        submit = _stub_submit(duel=duel, duel_completed=False)

        await handle_pvp_block(
            cb,
            cast(Bot, bot),
            _identity(),
            cast(SubmitMove, submit),
            _stub_players(p1, p2),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        # broadcast attack-prompt обоим
        assert bot.send_message.await_count == 2

    async def test_duel_completed_broadcasts_victory_for_p1(self) -> None:
        cb = _callback(data="pvp-block:11:1:high:low")
        bot = _stub_bot()
        p1 = _player(pid=1, tg_id=100, username="alice", length_cm=30)
        p2 = _player(pid=2, tg_id=200, username="bob", length_cm=20)
        duel = _duel(
            challenger_id=1,
            challenged_id=2,
            state=DuelState.COMPLETED,
            final=_outcome(p1_delta_cm=5, p2_delta_cm=-5, winner=DuelWinner.P1),
        )
        submit = _stub_submit(duel=duel, duel_completed=True)

        await handle_pvp_block(
            cb,
            cast(Bot, bot),
            _identity(),
            cast(SubmitMove, submit),
            _stub_players(p1, p2),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        # Оба DM получили текст: p1 — victory, p2 — defeat;
        # плюс публичная карточка с кнопкой «Поделиться» каждому (Спринт 2.1.H).
        assert bot.send_message.await_count == 4
        texts = [call.kwargs["text"] for call in bot.send_message.await_args_list]
        assert any("ru:duel-result-victory" in t for t in texts)
        assert any("ru:duel-result-defeat" in t for t in texts)
        assert sum("ru:duel-result-card-victory" in t for t in texts) == 2
        # Share-карточка идёт с inline-keyboard (один кнопочный ряд),
        # тогда как персональный result-DM — без markup.
        markups = [call.kwargs.get("reply_markup") for call in bot.send_message.await_args_list]
        assert sum(m is not None for m in markups) == 2

    async def test_duel_completed_broadcasts_draw(self) -> None:
        cb = _callback(data="pvp-block:11:1:high:low")
        bot = _stub_bot()
        p1 = _player(pid=1, tg_id=100, username="alice")
        p2 = _player(pid=2, tg_id=200, username="bob")
        duel = _duel(
            challenger_id=1,
            challenged_id=2,
            state=DuelState.COMPLETED,
            final=_outcome(p1_delta_cm=0, p2_delta_cm=0, winner=DuelWinner.DRAW),
        )
        submit = _stub_submit(duel=duel, duel_completed=True)

        await handle_pvp_block(
            cb,
            cast(Bot, bot),
            _identity(),
            cast(SubmitMove, submit),
            _stub_players(p1, p2),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
        )

        # 2 персональных result-DM (draw) + 2 публичных share-карточки.
        assert bot.send_message.await_count == 4
        texts = [call.kwargs["text"] for call in bot.send_message.await_args_list]
        assert sum("ru:duel-result-draw" in t for t in texts) == 2
        assert sum("ru:duel-result-card-draw" in t for t in texts) == 2


# ─────────────────── Pvp round flavour broadcast (2.1.H) ───────────────────


class _StubDuelLogTemplateProvider(IDuelLogTemplateProvider):
    """Минимальный провайдер: один шаблон на каждую `kind` per-locale."""

    __slots__ = ("_by_locale",)

    def __init__(self, by_locale: dict[str, list[DuelLogTemplate]] | None = None) -> None:
        self._by_locale = by_locale or {
            "ru": [
                DuelLogTemplate(
                    id="pvp.ru.both_hit.0001",
                    text="RU-BOTH-HIT {p1}/{p2}",
                    kind=RoundOutcomeKind.BOTH_HIT,
                ),
                DuelLogTemplate(
                    id="pvp.ru.single_hit.0001",
                    text="RU-SINGLE {attacker}>{defender}",
                    kind=RoundOutcomeKind.SINGLE_HIT,
                ),
                DuelLogTemplate(
                    id="pvp.ru.both_blocked.0001",
                    text="RU-BLOCKED {p1}-{p2}",
                    kind=RoundOutcomeKind.BOTH_BLOCKED,
                ),
            ],
            "en": [
                DuelLogTemplate(
                    id="pvp.en.both_hit.0001",
                    text="EN-BOTH-HIT {p1}/{p2}",
                    kind=RoundOutcomeKind.BOTH_HIT,
                ),
            ],
        }

    def get_templates(self, *, locale: str) -> list[DuelLogTemplate]:
        return list(self._by_locale.get(locale, self._by_locale["ru"]))


def _completed_round(
    *,
    p1_attack_blocked: bool = False,
    p2_attack_blocked: bool = False,
    p1_dmg: int = 0,
    p2_dmg: int = 0,
) -> RoundOutcome:
    return RoundOutcome(
        p1_choice=RoundChoice(attack=Position.HIGH, block=Position.LOW),
        p2_choice=RoundChoice(attack=Position.LOW, block=Position.HIGH),
        p1_attack_blocked=p1_attack_blocked,
        p2_attack_blocked=p2_attack_blocked,
        p1_damage_to_p2=p2_dmg,
        p2_damage_to_p1=p1_dmg,
    )


@pytest.mark.asyncio
class TestRoundFlavorBroadcast:
    async def test_round_closed_broadcasts_flavor_then_attack(self) -> None:
        cb = _callback(data="pvp-block:11:1:high:low")
        bot = _stub_bot()
        p1 = _player(pid=1, tg_id=100, username="alice")
        p2 = _player(pid=2, tg_id=200, username="bob")
        # Раунд 1 закрылся (both_hit) → pending_round.round_num=2
        duel = _duel(
            challenger_id=1,
            challenged_id=2,
            state=DuelState.IN_PROGRESS,
            pending=PendingRound(round_num=2, p1_choice=None, p2_choice=None),
            completed_rounds=(_completed_round(p1_dmg=2, p2_dmg=2),),
        )
        submit = _stub_submit(duel=duel, duel_completed=False)

        await handle_pvp_block(
            cb,
            cast(Bot, bot),
            _identity(),
            cast(SubmitMove, submit),
            _stub_players(p1, p2),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
            cast(IDuelLogTemplateProvider, _StubDuelLogTemplateProvider()),
            cast(IRandom, FakeRandom(seed=0)),
        )

        # 2 flavour DM + 2 attack-prompt DM = 4
        assert bot.send_message.await_count == 4
        texts = [call.kwargs["text"] for call in bot.send_message.await_args_list]
        # Первые два сообщения — flavour (RU-BOTH-HIT)
        assert sum("RU-BOTH-HIT" in t for t in texts) == 2

    async def test_completed_duel_broadcasts_flavor_for_last_round(self) -> None:
        cb = _callback(data="pvp-block:11:3:high:low")
        bot = _stub_bot()
        p1 = _player(pid=1, tg_id=100, username="alice", length_cm=30)
        p2 = _player(pid=2, tg_id=200, username="bob", length_cm=20)
        duel = _duel(
            challenger_id=1,
            challenged_id=2,
            state=DuelState.COMPLETED,
            final=_outcome(p1_delta_cm=5, p2_delta_cm=-5, winner=DuelWinner.P1),
            completed_rounds=(
                _completed_round(
                    p1_dmg=2, p2_dmg=0, p1_attack_blocked=False, p2_attack_blocked=True
                ),
            ),
        )
        submit = _stub_submit(duel=duel, duel_completed=True)

        await handle_pvp_block(
            cb,
            cast(Bot, bot),
            _identity(),
            cast(SubmitMove, submit),
            _stub_players(p1, p2),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
            cast(IDuelLogTemplateProvider, _StubDuelLogTemplateProvider()),
            cast(IRandom, FakeRandom(seed=0)),
        )

        # 2 flavour + 2 result + 2 share-card = 6
        assert bot.send_message.await_count == 6
        texts = [call.kwargs["text"] for call in bot.send_message.await_args_list]
        # SINGLE_HIT: p2 заблокирован, значит p1 — атакующий
        assert sum("RU-SINGLE @alice>@bob" in t for t in texts) == 2

    async def test_no_log_templates_skips_flavor_silently(self) -> None:
        cb = _callback(data="pvp-block:11:1:high:low")
        bot = _stub_bot()
        p1 = _player(pid=1, tg_id=100, username="alice")
        p2 = _player(pid=2, tg_id=200, username="bob")
        duel = _duel(
            challenger_id=1,
            challenged_id=2,
            state=DuelState.IN_PROGRESS,
            pending=PendingRound(round_num=2, p1_choice=None, p2_choice=None),
            completed_rounds=(_completed_round(p1_dmg=2, p2_dmg=2),),
        )
        submit = _stub_submit(duel=duel, duel_completed=False)

        await handle_pvp_block(
            cb,
            cast(Bot, bot),
            _identity(),
            cast(SubmitMove, submit),
            _stub_players(p1, p2),
            _bundle(),
            cast(IPlayerLocaleResolver, _stub_locale_resolver()),
            _RU,
            None,  # log_templates не подвязан → flavour skip
            None,
        )

        # Только attack-prompt: 2 DM, без flavour.
        assert bot.send_message.await_count == 2


# ─────────────────── handle_share_pvp_result (2.1.H) ───────────────────


@pytest.mark.asyncio
class TestHandleSharePvpResult:
    async def test_no_data_returns_silently(self) -> None:
        cb = _callback(data=None)
        bot = _stub_bot()
        await handle_share_pvp_result(
            cb,
            cast(Bot, bot),
            _identity(),
            FakeDuelRepository(),
            _stub_players(),
            _bundle(),
            _RU,
        )
        bot.send_message.assert_not_awaited()

    async def test_invalid_data_outdated_toast(self) -> None:
        cb = _callback(data="pvp-share:bad")
        bot = _stub_bot()
        await handle_share_pvp_result(
            cb,
            cast(Bot, bot),
            _identity(),
            FakeDuelRepository(),
            _stub_players(),
            _bundle(),
            _RU,
        )
        bot.send_message.assert_not_awaited()
        toast = cb.answer.await_args.args[0]
        assert "ru:duel-toast-outdated" in toast

    async def test_duel_not_found_returns_toast(self) -> None:
        cb = _callback(data="pvp-share:999")
        bot = _stub_bot()
        await handle_share_pvp_result(
            cb,
            cast(Bot, bot),
            _identity(),
            FakeDuelRepository(),
            _stub_players(),
            _bundle(),
            _RU,
        )
        bot.send_message.assert_not_awaited()
        toast = cb.answer.await_args.args[0]
        assert "ru:duel-toast-not-found" in toast

    async def test_success_posts_card_to_chat(self) -> None:
        cb = _callback(data="pvp-share:1")
        bot = _stub_bot()
        p1 = _player(pid=1, tg_id=100, username="alice", length_cm=30)
        p2 = _player(pid=2, tg_id=200, username="bob", length_cm=20)
        # Без `id` — `FakeDuelRepository.add()` сам присвоит id=1.
        duel_seed = Duel(
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
            final_outcome=_outcome(p1_delta_cm=5, p2_delta_cm=-5, winner=DuelWinner.P1),
        )
        duels = FakeDuelRepository()
        await duels.add(duel_seed)
        await handle_share_pvp_result(
            cb,
            cast(Bot, bot),
            _identity(),
            duels,
            _stub_players(p1, p2),
            _bundle(),
            _RU,
        )
        bot.send_message.assert_awaited_once()
        kwargs = bot.send_message.await_args.kwargs
        # Постим в чат, откуда пришёл callback (cb.message.chat.id == 42).
        assert kwargs["chat_id"] == 42
        assert "ru:duel-result-card-victory" in kwargs["text"]
        # Без клавиатуры (нельзя бесконечно расшаривать).
        assert kwargs.get("reply_markup") is None
        cb.answer.assert_awaited_once_with()
