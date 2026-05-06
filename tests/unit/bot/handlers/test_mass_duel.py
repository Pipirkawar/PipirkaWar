"""Юнит-тесты `/clan_attack`-handler-а и масс-PvP-callback-ов (Спринт 2.2.F часть 2).

Покрывают `handle_clan_attack`, `handle_mass_attack`, `handle_mass_block` —
все ошибочные ветки use-case-ов конвертятся в локализованные сообщения /
toast-ы, успех — старт боя + рассылка DM участникам, а после блока — резолв
и broadcast итогов в чаты-кланов.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.types import CallbackQuery, Chat, Message, User

from pipirik_wars.application.dto.inputs import (
    ResolveMassDuelInput,
    StartMassDuelInput,
    SubmitMassMoveInput,
)
from pipirik_wars.application.i18n import IPlayerLocaleResolver, Locale
from pipirik_wars.application.pvp import (
    ResolveMassDuel,
    StartMassDuel,
    SubmitMassMove,
)
from pipirik_wars.application.pvp.resolve_mass_duel import MassDuelResolved
from pipirik_wars.application.pvp.start_mass_duel import MassDuelStarted
from pipirik_wars.application.pvp.submit_mass_move import MassMoveSubmitted
from pipirik_wars.bot.handlers.mass_duel import (
    handle_clan_attack,
    handle_mass_attack,
    handle_mass_block,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.balance import (
    PvpConfig,
    PvpDuel1v1Config,
    PvpMassDuelConfig,
)
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanFrozenError,
    ClanStatus,
    ClanTitle,
    IClanRepository,
)
from pipirik_wars.domain.player import (
    Length,
    Player,
    PlayerStatus,
    Thickness,
    Username,
)
from pipirik_wars.domain.pvp import (
    InvalidMassDuelStateError,
    MassDuel,
    MassDuelCooldownError,
    MassDuelNoParticipantsError,
    MassDuelNotFoundError,
    MassDuelOutcome,
    MassDuelState,
    MassDuelWinner,
    MassMoveAlreadySubmittedError,
    NotAMassDuelParticipantError,
    Position,
)
from pipirik_wars.domain.pvp.mass import (
    MassDamageEntry,
    MassRoundOutcome,
)
from pipirik_wars.domain.security import LockAlreadyHeldError
from pipirik_wars.shared.errors import IntegrityError
from tests.fakes import FakeBalanceConfig, FakeMessageBundle
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 5, 9, 0, tzinfo=UTC)
_RU = Locale("ru")


# ─────────────────────── фикстуры/билдеры ───────────────────────


def _bundle() -> FakeMessageBundle:
    return FakeMessageBundle()


def _balance(
    *,
    cooldown_hours: int = 6,
    min_length_cm: int = 20,
    min_thickness_level: int = 2,
    move_timer_seconds: int = 180,
) -> IBalanceConfig:
    base = build_valid_balance()
    cfg = base.model_copy(
        update={
            "pvp": PvpConfig(
                duel_1v1=PvpDuel1v1Config(
                    rounds=3,
                    hit_pct=10,
                    min_length_cm=20,
                    min_thickness_level=2,
                    global_lobby_ttl_minutes=10,
                    chat_to_global_promotion_minutes=3,
                    round_timer_seconds=45,
                ),
                mass_duel=PvpMassDuelConfig(
                    cooldown_hours=cooldown_hours,
                    min_length_cm=min_length_cm,
                    min_thickness_level=min_thickness_level,
                    min_clan_members=1,
                    move_timer_seconds=move_timer_seconds,
                ),
            ),
        }
    )
    return FakeBalanceConfig(cfg)


def _identity(
    *,
    chat_kind: str = "supergroup",
    chat_id: int = -1001,
    tg_user_id: int = 100,
) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=chat_id,
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


def _clan(
    *,
    clan_id: int,
    chat_id: int,
    title: str,
) -> Clan:
    return Clan(
        id=clan_id,
        chat_id=chat_id,
        chat_kind=ChatKind.SUPERGROUP,
        title=ClanTitle(value=title),
        status=ClanStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _mass_duel(
    *,
    duel_id: int = 11,
    clan1_id: int = 100,
    clan2_id: int = 200,
    clan1_member_ids: tuple[int, ...] = (1, 2),
    clan2_member_ids: tuple[int, ...] = (3, 4),
    state: MassDuelState = MassDuelState.IN_PROGRESS,
    final: MassDuelOutcome | None = None,
) -> MassDuel:
    n1 = len(clan1_member_ids)
    n2 = len(clan2_member_ids)
    return MassDuel(
        id=duel_id,
        clan1_id=clan1_id,
        clan2_id=clan2_id,
        state=state,
        hit_pct=10,
        clan1_member_ids=clan1_member_ids,
        clan2_member_ids=clan2_member_ids,
        clan1_initial_lengths=tuple(25 for _ in range(n1)),
        clan2_initial_lengths=tuple(25 for _ in range(n2)),
        clan1_choices=tuple(None for _ in range(n1)),
        clan2_choices=tuple(None for _ in range(n2)),
        created_at=_NOW,
        completed_at=_NOW if state is MassDuelState.COMPLETED else None,
        cancelled_at=None,
        final_outcome=final,
    )


def _outcome(
    *,
    winner: MassDuelWinner = MassDuelWinner.CLAN1,
    clan1_total_dealt: int = 5,
    clan2_total_dealt: int = 0,
    clan1_delta_cm: int = 5,
    clan2_delta_cm: int = -5,
) -> MassDuelOutcome:
    entries = (
        MassDamageEntry(
            attacker_id=1,
            defender_id=3,
            attacker_attack=Position.HIGH,
            defender_block=Position.LOW,
            blocked=False,
            damage_cm=clan1_total_dealt,
        ),
    )
    round_outcome = MassRoundOutcome(
        damage_entries=entries,
        clan1_total_dealt=clan1_total_dealt,
        clan2_total_dealt=clan2_total_dealt,
    )
    return MassDuelOutcome(
        outcome=round_outcome,
        clan1_total_dealt=clan1_total_dealt,
        clan2_total_dealt=clan2_total_dealt,
        clan1_delta_cm=clan1_delta_cm,
        clan2_delta_cm=clan2_delta_cm,
        winner=winner,
    )


def _msg(
    *,
    chat_type: str = "supergroup",
    chat_id: int = -1001,
    from_id: int = 100,
    forward_chat_id: int | None = None,
) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.chat = Chat(id=chat_id, type=chat_type)
    msg.answer = AsyncMock()
    msg.from_user = User(id=from_id, is_bot=False, first_name="Алиса")
    if forward_chat_id is not None:
        reply = MagicMock(spec=Message)
        reply.forward_from_chat = Chat(id=forward_chat_id, type="supergroup")
        msg.reply_to_message = reply
    else:
        msg.reply_to_message = None
    return msg


def _command(args: str | None = None) -> MagicMock:
    obj = MagicMock()
    obj.args = args
    return obj


def _stub_start(
    *,
    duel: MassDuel | None = None,
    error: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=StartMassDuel)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    duel = duel or _mass_duel()
    use_case.execute = AsyncMock(return_value=MassDuelStarted(duel=duel))
    return use_case


def _stub_submit(
    *,
    duel: MassDuel | None = None,
    is_ready_to_resolve: bool = False,
    error: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=SubmitMassMove)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    duel = duel or _mass_duel()
    use_case.execute = AsyncMock(
        return_value=MassMoveSubmitted(
            duel=duel,
            is_ready_to_resolve=is_ready_to_resolve,
        ),
    )
    return use_case


def _stub_resolve(
    *,
    duel: MassDuel | None = None,
    error: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=ResolveMassDuel)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    duel = duel or _mass_duel(
        state=MassDuelState.COMPLETED,
        final=_outcome(),
    )
    use_case.execute = AsyncMock(return_value=MassDuelResolved(duel=duel))
    return use_case


def _stub_clans(*clans: Clan) -> MagicMock:
    repo = MagicMock(spec=IClanRepository)
    by_id = {c.id: c for c in clans if c.id is not None}
    by_chat = {c.chat_id: c for c in clans}

    async def _by_id(clan_id: int) -> Clan | None:
        return by_id.get(clan_id)

    async def _by_chat(chat_id: int) -> Clan | None:
        return by_chat.get(chat_id)

    repo.get_by_id = AsyncMock(side_effect=_by_id)
    repo.get_by_chat_id = AsyncMock(side_effect=_by_chat)
    return repo


def _stub_players(*players: Player) -> MagicMock:
    repo = MagicMock()
    by_id = {p.id: p for p in players if p.id is not None}
    by_tg = {p.tg_id: p for p in players}

    async def _by_id(*, player_id: int) -> Player | None:
        return by_id.get(player_id)

    async def _by_tg_id(tg_id: int) -> Player | None:
        return by_tg.get(tg_id)

    repo.get_by_id = AsyncMock(side_effect=_by_id)
    repo.get_by_tg_id = AsyncMock(side_effect=_by_tg_id)
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


# ─────────────────────── /clan_attack ───────────────────────


@pytest.mark.asyncio
class TestHandleClanAttack:
    async def test_no_identity_silent(self) -> None:
        msg = _msg()
        start = _stub_start()
        await handle_clan_attack(
            cast(Message, msg),
            _command("-2002"),
            cast(Bot, _stub_bot()),
            None,
            cast(StartMassDuel, start),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _balance(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        msg.answer.assert_not_awaited()
        start.execute.assert_not_awaited()

    async def test_private_chat_rejected(self) -> None:
        msg = _msg(chat_type="private", chat_id=42)
        start = _stub_start()
        await handle_clan_attack(
            cast(Message, msg),
            _command("-2002"),
            cast(Bot, _stub_bot()),
            _identity(chat_kind="private", chat_id=42),
            cast(StartMassDuel, start),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _balance(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        msg.answer.assert_awaited_once_with("ru:pvp-mass-needs-group-chat")
        start.execute.assert_not_awaited()

    async def test_no_target_arg_or_reply_shows_usage(self) -> None:
        msg = _msg()
        start = _stub_start()
        await handle_clan_attack(
            cast(Message, msg),
            _command(None),
            cast(Bot, _stub_bot()),
            _identity(),
            cast(StartMassDuel, start),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _balance(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        msg.answer.assert_awaited_once_with("ru:pvp-mass-target-needed")
        start.execute.assert_not_awaited()

    async def test_invalid_target_arg_shows_usage(self) -> None:
        msg = _msg()
        start = _stub_start()
        await handle_clan_attack(
            cast(Message, msg),
            _command("not-a-number"),
            cast(Bot, _stub_bot()),
            _identity(),
            cast(StartMassDuel, start),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _balance(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        msg.answer.assert_awaited_once_with("ru:pvp-mass-target-needed")
        start.execute.assert_not_awaited()

    async def test_self_attack_rejected_via_arg(self) -> None:
        msg = _msg(chat_id=-1001)
        start = _stub_start()
        await handle_clan_attack(
            cast(Message, msg),
            _command("-1001"),
            cast(Bot, _stub_bot()),
            _identity(chat_id=-1001),
            cast(StartMassDuel, start),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _balance(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        msg.answer.assert_awaited_once_with("ru:pvp-mass-self-attack")
        start.execute.assert_not_awaited()

    async def test_target_resolved_from_forward_reply(self) -> None:
        msg = _msg(chat_id=-1001, forward_chat_id=-2002)
        attacker = _clan(clan_id=100, chat_id=-1001, title="Атакующие")
        defender = _clan(clan_id=200, chat_id=-2002, title="Защитники")
        duel = _mass_duel(clan1_id=100, clan2_id=200)
        start = _stub_start(duel=duel)
        bot = _stub_bot()
        await handle_clan_attack(
            cast(Message, msg),
            _command(None),
            cast(Bot, bot),
            _identity(chat_id=-1001),
            cast(StartMassDuel, start),
            cast(IClanRepository, _stub_clans(attacker, defender)),
            _stub_players(
                _player(pid=1, tg_id=1001),
                _player(pid=2, tg_id=1002),
                _player(pid=3, tg_id=1003),
                _player(pid=4, tg_id=1004),
            ),
            _balance(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        start.execute.assert_awaited_once()
        called: StartMassDuelInput = start.execute.await_args.args[0]
        assert called.attacker_chat_id == -1001
        assert called.defender_chat_id == -2002
        assert called.initiator_tg_id == 100

    async def test_integrity_error_target_not_found(self) -> None:
        msg = _msg()
        start = _stub_start(error=IntegrityError("no clan"))
        await handle_clan_attack(
            cast(Message, msg),
            _command("-2002"),
            cast(Bot, _stub_bot()),
            _identity(),
            cast(StartMassDuel, start),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _balance(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        msg.answer.assert_awaited_once_with("ru:pvp-mass-target-not-found")

    async def test_clan_frozen_error(self) -> None:
        msg = _msg()
        start = _stub_start(error=ClanFrozenError(chat_id=-2002))
        await handle_clan_attack(
            cast(Message, msg),
            _command("-2002"),
            cast(Bot, _stub_bot()),
            _identity(),
            cast(StartMassDuel, start),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _balance(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        msg.answer.assert_awaited_once_with("ru:pvp-mass-clan-frozen")

    async def test_cooldown_error(self) -> None:
        msg = _msg()
        start = _stub_start(
            error=MassDuelCooldownError(clan_id=100, cooldown_hours=6),
        )
        await handle_clan_attack(
            cast(Message, msg),
            _command("-2002"),
            cast(Bot, _stub_bot()),
            _identity(),
            cast(StartMassDuel, start),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _balance(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        msg.answer.assert_awaited_once_with("ru:pvp-mass-cooldown[cooldown_hours=6]")

    async def test_no_participants_error(self) -> None:
        msg = _msg()
        start = _stub_start(error=MassDuelNoParticipantsError(clan_id=100))
        await handle_clan_attack(
            cast(Message, msg),
            _command("-2002"),
            cast(Bot, _stub_bot()),
            _identity(),
            cast(StartMassDuel, start),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _balance(min_length_cm=25, min_thickness_level=3),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        msg.answer.assert_awaited_once_with(
            "ru:pvp-mass-no-participants[min_length_cm=25,min_thickness_level=3]"
        )

    async def test_lock_already_held_error(self) -> None:
        msg = _msg()
        start = _stub_start(
            error=LockAlreadyHeldError(actor_kind="player", actor_id=1),
        )
        await handle_clan_attack(
            cast(Message, msg),
            _command("-2002"),
            cast(Bot, _stub_bot()),
            _identity(),
            cast(StartMassDuel, start),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _balance(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        msg.answer.assert_awaited_once_with("ru:pvp-mass-lock-already-held")

    async def test_success_publishes_card_and_dms_participants(self) -> None:
        msg = _msg(chat_id=-1001)
        attacker = _clan(clan_id=100, chat_id=-1001, title="Atk")
        defender = _clan(clan_id=200, chat_id=-2002, title="Def")
        duel = _mass_duel(
            clan1_id=100,
            clan2_id=200,
            clan1_member_ids=(1, 2),
            clan2_member_ids=(3, 4),
        )
        start = _stub_start(duel=duel)
        bot = _stub_bot()
        await handle_clan_attack(
            cast(Message, msg),
            _command("-2002"),
            cast(Bot, bot),
            _identity(chat_id=-1001),
            cast(StartMassDuel, start),
            cast(IClanRepository, _stub_clans(attacker, defender)),
            _stub_players(
                _player(pid=1, tg_id=1001),
                _player(pid=2, tg_id=1002),
                _player(pid=3, tg_id=1003),
                _player(pid=4, tg_id=1004),
            ),
            _balance(move_timer_seconds=180),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        msg.answer.assert_awaited_once()
        sent = msg.answer.await_args.args[0]
        assert "ru:pvp-mass-started" in sent
        assert "attacker=Atk" in sent
        assert "defender=Def" in sent
        assert "timer_seconds=180" in sent
        # 4 DM-промпта (по одному на каждого участника).
        assert bot.send_message.await_count == 4
        called_chat_ids = {call.kwargs["chat_id"] for call in bot.send_message.await_args_list}
        assert called_chat_ids == {1001, 1002, 1003, 1004}


# ─────────────────────── pvpm-attack ───────────────────────


@pytest.mark.asyncio
class TestHandleMassAttack:
    async def test_no_identity_silent(self) -> None:
        cb = _callback(data="pvpm-attack:1:high")
        await handle_mass_attack(
            cast(CallbackQuery, cb),
            None,
            _bundle(),
            _RU,
        )
        cb.answer.assert_not_awaited()

    async def test_no_data_silent(self) -> None:
        cb = _callback(data=None)
        await handle_mass_attack(
            cast(CallbackQuery, cb),
            _identity(),
            _bundle(),
            _RU,
        )
        cb.answer.assert_not_awaited()

    async def test_invalid_callback_data_outdated_toast(self) -> None:
        cb = _callback(data="pvpm-attack:not-a-number:high")
        await handle_mass_attack(
            cast(CallbackQuery, cb),
            _identity(),
            _bundle(),
            _RU,
        )
        cb.answer.assert_awaited_once_with("ru:pvp-mass-toast-outdated", show_alert=False)
        cb.message.edit_reply_markup.assert_awaited_once()

    async def test_valid_attack_shows_block_keyboard(self) -> None:
        cb = _callback(data="pvpm-attack:11:mid")
        await handle_mass_attack(
            cast(CallbackQuery, cb),
            _identity(),
            _bundle(),
            _RU,
        )
        cb.answer.assert_awaited_once_with("ru:pvp-mass-toast-attack-selected", show_alert=False)
        cb.message.edit_text.assert_awaited_once()
        edited = cb.message.edit_text.await_args.args[0]
        assert "ru:pvp-mass-prompt-block" in edited
        assert "attack=mid" in edited
        cb.message.edit_reply_markup.assert_awaited_once()


# ─────────────────────── pvpm-block ───────────────────────


@pytest.mark.asyncio
class TestHandleMassBlock:
    async def test_no_identity_silent(self) -> None:
        cb = _callback(data="pvpm-block:1:high:low")
        submit = _stub_submit()
        await handle_mass_block(
            cast(CallbackQuery, cb),
            cast(Bot, _stub_bot()),
            None,
            cast(SubmitMassMove, submit),
            cast(ResolveMassDuel, _stub_resolve()),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        submit.execute.assert_not_awaited()

    async def test_invalid_callback_data_toast(self) -> None:
        cb = _callback(data="pvpm-block:abc:high:low")
        submit = _stub_submit()
        await handle_mass_block(
            cast(CallbackQuery, cb),
            cast(Bot, _stub_bot()),
            _identity(chat_kind="private", chat_id=100),
            cast(SubmitMassMove, submit),
            cast(ResolveMassDuel, _stub_resolve()),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        cb.answer.assert_awaited_once_with("ru:pvp-mass-toast-outdated", show_alert=False)
        submit.execute.assert_not_awaited()

    async def test_duel_not_found_toast(self) -> None:
        cb = _callback(data="pvpm-block:11:high:low")
        submit = _stub_submit(error=MassDuelNotFoundError(duel_id=11))
        await handle_mass_block(
            cast(CallbackQuery, cb),
            cast(Bot, _stub_bot()),
            _identity(chat_kind="private", chat_id=100),
            cast(SubmitMassMove, submit),
            cast(ResolveMassDuel, _stub_resolve()),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        cb.answer.assert_awaited_once_with("ru:pvp-mass-toast-not-found", show_alert=False)

    async def test_not_participant_toast(self) -> None:
        cb = _callback(data="pvpm-block:11:high:low")
        submit = _stub_submit(error=NotAMassDuelParticipantError(player_id=99))
        await handle_mass_block(
            cast(CallbackQuery, cb),
            cast(Bot, _stub_bot()),
            _identity(chat_kind="private", chat_id=100),
            cast(SubmitMassMove, submit),
            cast(ResolveMassDuel, _stub_resolve()),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        cb.answer.assert_awaited_once_with("ru:pvp-mass-toast-not-participant", show_alert=True)

    async def test_invalid_state_toast(self) -> None:
        cb = _callback(data="pvpm-block:11:high:low")
        submit = _stub_submit(
            error=InvalidMassDuelStateError(
                expected=MassDuelState.IN_PROGRESS,
                actual=MassDuelState.COMPLETED,
                op="submit_move",
            ),
        )
        await handle_mass_block(
            cast(CallbackQuery, cb),
            cast(Bot, _stub_bot()),
            _identity(chat_kind="private", chat_id=100),
            cast(SubmitMassMove, submit),
            cast(ResolveMassDuel, _stub_resolve()),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        cb.answer.assert_awaited_once_with("ru:pvp-mass-toast-invalid-state", show_alert=False)

    async def test_already_submitted_toast(self) -> None:
        cb = _callback(data="pvpm-block:11:high:low")
        submit = _stub_submit(error=MassMoveAlreadySubmittedError(player_id=1))
        await handle_mass_block(
            cast(CallbackQuery, cb),
            cast(Bot, _stub_bot()),
            _identity(chat_kind="private", chat_id=100),
            cast(SubmitMassMove, submit),
            cast(ResolveMassDuel, _stub_resolve()),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        cb.answer.assert_awaited_once_with("ru:pvp-mass-toast-already-submitted", show_alert=False)

    async def test_submit_not_ready_shows_waiting(self) -> None:
        cb = _callback(data="pvpm-block:11:high:low")
        submit = _stub_submit(is_ready_to_resolve=False)
        resolve = _stub_resolve()
        bot = _stub_bot()
        await handle_mass_block(
            cast(CallbackQuery, cb),
            cast(Bot, bot),
            _identity(chat_kind="private", chat_id=100),
            cast(SubmitMassMove, submit),
            cast(ResolveMassDuel, resolve),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        cb.answer.assert_awaited_once_with("ru:pvp-mass-toast-move-accepted", show_alert=False)
        submit.execute.assert_awaited_once()
        called: SubmitMassMoveInput = submit.execute.await_args.args[0]
        assert called.duel_id == 11
        assert called.attack == "high"
        assert called.block == "low"
        cb.message.edit_text.assert_awaited_once()
        edited = cb.message.edit_text.await_args.args[0]
        assert "ru:pvp-mass-waiting" in edited
        resolve.execute.assert_not_awaited()
        bot.send_message.assert_not_awaited()

    async def test_submit_ready_to_resolve_calls_resolve(self) -> None:
        cb = _callback(data="pvpm-block:11:high:low")
        completed = _mass_duel(
            duel_id=11,
            clan1_id=100,
            clan2_id=200,
            clan1_member_ids=(1, 2),
            clan2_member_ids=(3, 4),
            state=MassDuelState.COMPLETED,
            final=_outcome(winner=MassDuelWinner.CLAN1),
        )
        submit = _stub_submit(is_ready_to_resolve=True)
        resolve = _stub_resolve(duel=completed)
        attacker = _clan(clan_id=100, chat_id=-1001, title="Atk")
        defender = _clan(clan_id=200, chat_id=-2002, title="Def")
        bot = _stub_bot()
        await handle_mass_block(
            cast(CallbackQuery, cb),
            cast(Bot, bot),
            _identity(chat_kind="private", chat_id=100),
            cast(SubmitMassMove, submit),
            cast(ResolveMassDuel, resolve),
            cast(IClanRepository, _stub_clans(attacker, defender)),
            _stub_players(
                _player(pid=1, tg_id=1001),
                _player(pid=2, tg_id=1002),
                _player(pid=3, tg_id=1003),
                _player(pid=4, tg_id=1004),
            ),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        resolve.execute.assert_awaited_once()
        called: ResolveMassDuelInput = resolve.execute.await_args.args[0]
        assert called.duel_id == 11
        # 4 персональных DM + 2 публичных карточки в чаты-кланов = 6 send_message.
        assert bot.send_message.await_count == 6
        chat_ids = [call.kwargs["chat_id"] for call in bot.send_message.await_args_list]
        assert sorted(chat_ids) == [-2002, -1001, 1001, 1002, 1003, 1004]

    async def test_submit_ready_resolve_not_found_no_broadcast(self) -> None:
        cb = _callback(data="pvpm-block:11:high:low")
        submit = _stub_submit(is_ready_to_resolve=True)
        resolve = _stub_resolve(error=MassDuelNotFoundError(duel_id=11))
        bot = _stub_bot()
        await handle_mass_block(
            cast(CallbackQuery, cb),
            cast(Bot, bot),
            _identity(chat_kind="private", chat_id=100),
            cast(SubmitMassMove, submit),
            cast(ResolveMassDuel, resolve),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        bot.send_message.assert_not_awaited()

    async def test_submit_ready_resolve_invalid_state_no_broadcast(self) -> None:
        cb = _callback(data="pvpm-block:11:high:low")
        submit = _stub_submit(is_ready_to_resolve=True)
        resolve = _stub_resolve(
            error=InvalidMassDuelStateError(
                expected=MassDuelState.IN_PROGRESS,
                actual=MassDuelState.COMPLETED,
                op="resolve",
            ),
        )
        bot = _stub_bot()
        await handle_mass_block(
            cast(CallbackQuery, cb),
            cast(Bot, bot),
            _identity(chat_kind="private", chat_id=100),
            cast(SubmitMassMove, submit),
            cast(ResolveMassDuel, resolve),
            cast(IClanRepository, _stub_clans()),
            _stub_players(),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        bot.send_message.assert_not_awaited()

    async def test_resolve_draw_winner_uses_clan1_dealt(self) -> None:
        cb = _callback(data="pvpm-block:11:high:low")
        completed = _mass_duel(
            duel_id=11,
            clan1_id=100,
            clan2_id=200,
            clan1_member_ids=(1,),
            clan2_member_ids=(3,),
            state=MassDuelState.COMPLETED,
            final=_outcome(
                winner=MassDuelWinner.DRAW,
                clan1_total_dealt=3,
                clan2_total_dealt=3,
                clan1_delta_cm=0,
                clan2_delta_cm=0,
            ),
        )
        submit = _stub_submit(is_ready_to_resolve=True)
        resolve = _stub_resolve(duel=completed)
        attacker = _clan(clan_id=100, chat_id=-1001, title="Atk")
        defender = _clan(clan_id=200, chat_id=-2002, title="Def")
        bot = _stub_bot()
        await handle_mass_block(
            cast(CallbackQuery, cb),
            cast(Bot, bot),
            _identity(chat_kind="private", chat_id=100),
            cast(SubmitMassMove, submit),
            cast(ResolveMassDuel, resolve),
            cast(IClanRepository, _stub_clans(attacker, defender)),
            _stub_players(
                _player(pid=1, tg_id=1001),
                _player(pid=3, tg_id=1003),
            ),
            _bundle(),
            _stub_locale_resolver(),
            _RU,
        )
        # 2 DM игрокам (draw на каждой стороне) + 2 карточки в чаты.
        assert bot.send_message.await_count == 4
        # DM-тексты должны содержать draw-ключ.
        dm_texts = [
            call.kwargs["text"]
            for call in bot.send_message.await_args_list
            if call.kwargs["chat_id"] in (1001, 1003)
        ]
        for text in dm_texts:
            assert "ru:pvp-mass-result-draw" in text
        # Чат-карточки должны содержать draw-ключ.
        chat_texts = [
            call.kwargs["text"]
            for call in bot.send_message.await_args_list
            if call.kwargs["chat_id"] in (-1001, -2002)
        ]
        for text in chat_texts:
            assert "ru:pvp-mass-result-chat-draw" in text
