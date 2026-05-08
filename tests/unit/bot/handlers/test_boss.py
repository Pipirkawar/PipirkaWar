"""Юнит-тесты `/boss`-handler-а (Спринт 3.3-D, ГДД §10).

Покрытие:
- Команда `/boss`:
  - chat-kind gate (private only — group/supergroup/channel/no-identity → silent);
  - args parsing (`/boss` без аргументов → success; любой хвост → usage);
  - маппинг доменных ошибок `SummonBoss` → локализованные ответы;
  - happy-path: подтверждение саммонеру + объявление с инлайн-клавиатурой.
- Callback `boss:`:
  - no identity / no message / no data → silent;
  - invalid `callback_data` → generic error toast;
  - `show_lobby` (read-only): fight-not-found / not-in-lobby / success;
  - `join`: success → toast + refresh; ошибки → toast-ы; различие
    «уже босс» vs «уже участник» через `_resolve_already_in_toast`;
  - `leave`: fight-not-found / lobby-closed / summoner-self-leave /
    NotInBossFight / success → toast + refresh;
  - `cancel`: ошибки → toast-ы; success / already-cancelled → toast +
    замена сообщения.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Chat, InlineKeyboardMarkup, Message

from pipirik_wars.application.bosses import (
    BossFightCancelled,
    BossLobbyJoined,
    BossLobbyLeft,
    BossSummoned,
    CancelBossFight,
    JoinBossLobby,
    LeaveBossLobby,
    SummonBoss,
)
from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.bot.handlers.boss import handle_boss, handle_boss_callback
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.bosses import (
    AlreadyInBossFightError,
    BossFight,
    BossFightLobbyClosedError,
    BossFightNotFoundError,
    BossFightRequirementError,
    BossFightStatus,
    BossKind,
    BossParticipant,
    BossPlayerPoolEmptyError,
    BossSummonOnGlobalCooldownError,
    IBossFightRepository,
    IBossParticipantRepository,
    InvalidBossFightStateError,
    NotAuthorizedToCancelBossError,
    NotInBossFightError,
)
from pipirik_wars.domain.player import (
    DisplayName,
    IPlayerRepository,
    Length,
    Player,
    PlayerFrozenError,
    PlayerNotFoundError,
    PlayerStatus,
    Thickness,
    Username,
)
from pipirik_wars.domain.shared.ports import IClock
from tests.fakes import (
    FakeBossFightRepository,
    FakeBossParticipantRepository,
    FakeClock,
    FakeMessageBundle,
    FakePlayerRepository,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_RU = Locale("ru")
_SUMMONER_TG_ID = 1001
_SUMMONER_PLAYER_ID = 1
_BOSS_PLAYER_ID = 2
_RAIDER_TG_ID = 1002
_BOSS_FIGHT_ID = 7


# ───────────────────── фикстуры / помощники ─────────────────────


def _bundle() -> IMessageBundle:
    return FakeMessageBundle()


def _balance() -> MagicMock:
    """`IBalanceConfig` с реальным `BalanceConfig`-снимком."""
    snapshot = build_valid_balance()
    cfg = MagicMock()
    cfg.get = MagicMock(return_value=snapshot)
    return cfg


def _identity(
    *,
    chat_kind: str = "private",
    tg_user_id: int = _SUMMONER_TG_ID,
    chat_id: int = _SUMMONER_TG_ID,
) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=chat_id,
        chat_kind=chat_kind,
        language_code=None,
    )


def _msg(
    *,
    text: str = "/boss",
    chat_type: str = "private",
    chat_id: int = _SUMMONER_TG_ID,
) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.chat = Chat(id=chat_id, type=chat_type)
    msg.answer = AsyncMock()
    return msg


def _stub_bot() -> MagicMock:
    bot = MagicMock(spec=Bot)
    bot.send_message = AsyncMock()
    return bot


def _player(
    *,
    pid: int = _SUMMONER_PLAYER_ID,
    tg_id: int = _SUMMONER_TG_ID,
    length_cm: int = 30,
    thickness_level: int = 9,
    username: str = "summoner",
) -> Player:
    return Player(
        id=pid,
        tg_id=tg_id,
        username=Username(value=username),
        length=Length(cm=length_cm),
        thickness=Thickness(level=thickness_level),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _boss_fight(
    *,
    bf_id: int = _BOSS_FIGHT_ID,
    summoner_id: int = _SUMMONER_PLAYER_ID,
    boss_id: int = _BOSS_PLAYER_ID,
    status: BossFightStatus = BossFightStatus.LOBBY,
    boss_length_cm: int = 100,
    lobby_minutes: int = 20,
) -> BossFight:
    return BossFight(
        id=bf_id,
        kind=BossKind.RAID,
        summoner_player_id=summoner_id,
        boss_player_id=boss_id,
        status=status,
        started_at=_NOW,
        lobby_ends_at=_NOW + timedelta(minutes=lobby_minutes),
        finished_at=None,
        random_seed=42,
        initial_boss_length_cm=boss_length_cm,
        current_boss_length_cm=boss_length_cm,
        current_round=0,
    )


def _stub_summon_boss(
    *,
    success_fight: BossFight | None = None,
    error: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=SummonBoss)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    fight = success_fight or _boss_fight()
    summoner_part = BossParticipant.raider(
        boss_fight_id=cast(int, fight.id),
        player_id=fight.summoner_player_id,
        is_summoner=True,
        length_at_join_cm=30,
        joined_at=_NOW,
    )
    use_case.execute = AsyncMock(
        return_value=BossSummoned(boss_fight=fight, summoner_participant=summoner_part),
    )
    return use_case


def _stub_get_profile(
    *,
    summoner_view: ProfileView | None = None,
    boss_view: ProfileView | None = None,
    none_for_tg_ids: tuple[int, ...] = (),
) -> MagicMock:
    """`GetProfile`-stub с разными `ProfileView` per `tg_id`.

    `summoner_view` — для `_SUMMONER_TG_ID`; `boss_view` — для остальных
    (handler ищет босса через `_profile_by_player_id`, который сначала
    идёт в `IPlayerRepository.get_by_id` и потом сюда уже с tg_id босса).
    """
    use_case = MagicMock(spec=GetProfile)
    summoner_default = summoner_view or ProfileView(
        player=_player(),
        display_name=DisplayName(value="Саммонер"),
    )
    boss_default = boss_view or ProfileView(
        player=_player(pid=_BOSS_PLAYER_ID, tg_id=2002, username="boss", length_cm=80),
        display_name=DisplayName(value="Босс"),
    )

    async def _execute(*, tg_id: int) -> ProfileView | None:
        if tg_id in none_for_tg_ids:
            return None
        if tg_id == _SUMMONER_TG_ID:
            return summoner_default
        return boss_default

    use_case.execute = AsyncMock(side_effect=_execute)
    return use_case


async def _seeded_players() -> FakePlayerRepository:
    """Заведём двух игроков: саммонер и босс."""
    repo = FakePlayerRepository()
    await repo.add(
        Player.new(
            tg_id=_SUMMONER_TG_ID,
            username=Username(value="summoner"),
            now=_NOW,
        ),
    )
    await repo.add(
        Player.new(
            tg_id=2002,
            username=Username(value="boss"),
            now=_NOW,
        ),
    )
    return repo


async def _invoke(
    msg: MagicMock,
    *,
    identity: TgIdentity | None,
    summon_boss: MagicMock | None = None,
    get_profile: MagicMock | None = None,
    players: FakePlayerRepository | None = None,
) -> None:
    """Запустить `/boss` handler с дефолтами."""
    await handle_boss(
        cast(Message, msg),
        identity,
        cast(SummonBoss, summon_boss or _stub_summon_boss()),
        cast(GetProfile, get_profile or _stub_get_profile()),
        players or await _seeded_players(),
        _balance(),
        _bundle(),
        _RU,
    )


# ───────────────────── Команда /boss — chat-kind gate ─────────────────────


@pytest.mark.asyncio
class TestCommandChatKindGate:
    async def test_group_chat_silently_ignores(self) -> None:
        msg = _msg(chat_type="group", chat_id=-100)
        summon_uc = _stub_summon_boss()
        await _invoke(
            msg, identity=_identity(chat_kind="group", chat_id=-100), summon_boss=summon_uc
        )
        msg.answer.assert_not_called()
        summon_uc.execute.assert_not_called()

    async def test_supergroup_chat_silently_ignores(self) -> None:
        msg = _msg(chat_type="supergroup", chat_id=-100)
        summon_uc = _stub_summon_boss()
        await _invoke(
            msg,
            identity=_identity(chat_kind="supergroup", chat_id=-100),
            summon_boss=summon_uc,
        )
        msg.answer.assert_not_called()
        summon_uc.execute.assert_not_called()

    async def test_channel_chat_silently_ignores(self) -> None:
        msg = _msg(chat_type="channel", chat_id=-100)
        summon_uc = _stub_summon_boss()
        await _invoke(
            msg,
            identity=_identity(chat_kind="channel", chat_id=-100),
            summon_boss=summon_uc,
        )
        msg.answer.assert_not_called()
        summon_uc.execute.assert_not_called()

    async def test_no_identity_silently_ignores(self) -> None:
        msg = _msg()
        summon_uc = _stub_summon_boss()
        await _invoke(msg, identity=None, summon_boss=summon_uc)
        msg.answer.assert_not_called()
        summon_uc.execute.assert_not_called()


# ───────────────────── Команда /boss — args parsing ─────────────────────


@pytest.mark.asyncio
class TestCommandArgumentParsing:
    async def test_extra_arg_returns_usage(self) -> None:
        msg = _msg(text="/boss extra")
        summon_uc = _stub_summon_boss()
        await _invoke(msg, identity=_identity(), summon_boss=summon_uc)
        summon_uc.execute.assert_not_called()
        msg.answer.assert_awaited_once()
        text = msg.answer.await_args.args[0]
        assert "bosses-usage" in text

    async def test_two_extra_args_returns_usage(self) -> None:
        msg = _msg(text="/boss foo bar")
        summon_uc = _stub_summon_boss()
        await _invoke(msg, identity=_identity(), summon_boss=summon_uc)
        summon_uc.execute.assert_not_called()
        msg.answer.assert_awaited_once()

    async def test_text_none_treated_as_no_args(self) -> None:
        msg = _msg()
        msg.text = None
        await _invoke(msg, identity=_identity())
        # Нет аргументов → use-case вызывается → handler идёт в success-ветку.
        msg.answer.assert_awaited()  # private + announcement


# ───────────────────── Команда /boss — маппинг доменных ошибок ─────────────────────


@pytest.mark.asyncio
class TestCommandDomainErrorMapping:
    async def test_player_not_found_returns_not_registered(self) -> None:
        msg = _msg()
        summon_uc = _stub_summon_boss(error=PlayerNotFoundError(tg_id=_SUMMONER_TG_ID))
        await _invoke(msg, identity=_identity(), summon_boss=summon_uc)
        text = msg.answer.await_args.args[0]
        assert "bosses-not-registered" in text

    async def test_player_frozen_returns_player_frozen(self) -> None:
        msg = _msg()
        summon_uc = _stub_summon_boss(error=PlayerFrozenError(tg_id=_SUMMONER_TG_ID))
        await _invoke(msg, identity=_identity(), summon_boss=summon_uc)
        text = msg.answer.await_args.args[0]
        assert "bosses-player-frozen" in text

    async def test_requirement_thickness(self) -> None:
        msg = _msg()
        summon_uc = _stub_summon_boss(
            error=BossFightRequirementError(
                player_id=_SUMMONER_PLAYER_ID,
                requirement="thickness",
                required=9,
                actual=5,
            ),
        )
        await _invoke(msg, identity=_identity(), summon_boss=summon_uc)
        text = msg.answer.await_args.args[0]
        assert "bosses-requirement-thickness" in text
        assert "required=9" in text
        assert "actual=5" in text

    async def test_requirement_length(self) -> None:
        msg = _msg()
        summon_uc = _stub_summon_boss(
            error=BossFightRequirementError(
                player_id=_SUMMONER_PLAYER_ID,
                requirement="length",
                required=20,
                actual=15,
            ),
        )
        await _invoke(msg, identity=_identity(), summon_boss=summon_uc)
        text = msg.answer.await_args.args[0]
        assert "bosses-requirement-length" in text
        assert "required_cm=20" in text
        assert "actual_cm=15" in text

    async def test_summon_cooldown_rounds_up_to_minutes(self) -> None:
        msg = _msg()
        summon_uc = _stub_summon_boss(
            error=BossSummonOnGlobalCooldownError(actual_remaining_seconds=121),
        )
        await _invoke(msg, identity=_identity(), summon_boss=summon_uc)
        text = msg.answer.await_args.args[0]
        assert "bosses-cooldown" in text
        # 121 sec → ceil(121/60) = 3 мин
        assert "remaining_minutes=3" in text

    async def test_summon_cooldown_floor_is_one_minute(self) -> None:
        msg = _msg()
        summon_uc = _stub_summon_boss(
            error=BossSummonOnGlobalCooldownError(actual_remaining_seconds=10),
        )
        await _invoke(msg, identity=_identity(), summon_boss=summon_uc)
        text = msg.answer.await_args.args[0]
        assert "remaining_minutes=1" in text

    async def test_already_in_boss_fight(self) -> None:
        msg = _msg()
        summon_uc = _stub_summon_boss(
            error=AlreadyInBossFightError(player_id=_SUMMONER_PLAYER_ID),
        )
        await _invoke(msg, identity=_identity(), summon_boss=summon_uc)
        text = msg.answer.await_args.args[0]
        assert "bosses-already-in" in text

    async def test_pool_empty(self) -> None:
        msg = _msg()
        summon_uc = _stub_summon_boss(error=BossPlayerPoolEmptyError(pool_size=0))
        await _invoke(msg, identity=_identity(), summon_boss=summon_uc)
        text = msg.answer.await_args.args[0]
        assert "bosses-pool-empty" in text


# ───────────────────── Команда /boss — happy-path ─────────────────────


@pytest.mark.asyncio
class TestCommandHappyPath:
    async def test_success_sends_private_confirmation_and_announcement(self) -> None:
        msg = _msg()
        summon_uc = _stub_summon_boss()
        await _invoke(msg, identity=_identity(), summon_boss=summon_uc)
        summon_uc.execute.assert_awaited_once()
        # Два сообщения: подтверждение + объявление с клавиатурой.
        assert msg.answer.await_count == 2
        priv_text = msg.answer.await_args_list[0].args[0]
        assert "bosses-summoned-private" in priv_text
        announcement_call = msg.answer.await_args_list[1]
        announcement_text = announcement_call.kwargs.get("text") or announcement_call.args[0]
        assert "bosses-summoned-announcement" in announcement_text
        keyboard = announcement_call.kwargs["reply_markup"]
        assert isinstance(keyboard, InlineKeyboardMarkup)
        # Под объявлением одна кнопка «Показать лобби».
        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 1
        assert keyboard.inline_keyboard[0][0].callback_data == f"boss:show_lobby:{_BOSS_FIGHT_ID}"

    async def test_use_case_input_dto_carries_summoner_tg_id(self) -> None:
        msg = _msg()
        summon_uc = _stub_summon_boss()
        await _invoke(msg, identity=_identity(), summon_boss=summon_uc)
        input_dto = summon_uc.execute.await_args.args[0]
        assert input_dto.summoner_tg_id == _SUMMONER_TG_ID

    async def test_announcement_failure_does_not_propagate(self) -> None:
        msg = _msg()
        # Первый answer (private) ок, второй (announcement) — падает.
        msg.answer = AsyncMock(
            side_effect=[
                None,
                TelegramAPIError(method=SendMessage(chat_id=1, text="x"), message="oops"),
            ]
        )
        summon_uc = _stub_summon_boss()
        await _invoke(msg, identity=_identity(), summon_boss=summon_uc)
        # Handler не падает наружу.
        assert msg.answer.await_count == 2


# ───────────────────── Callback boss:* — общие ─────────────────────


def _callback(
    *,
    data: str = f"boss:show_lobby:{_BOSS_FIGHT_ID}",
    chat_type: str = "private",
    chat_id: int = _SUMMONER_TG_ID,
    message_present: bool = True,
) -> MagicMock:
    callback = MagicMock(spec=CallbackQuery)
    callback.data = data
    callback.answer = AsyncMock()
    if not message_present:
        callback.message = None
        return callback
    msg = MagicMock(spec=Message)
    msg.chat = Chat(id=chat_id, type=chat_type)
    msg.edit_text = AsyncMock()
    callback.message = msg
    return callback


_UNSET: object = object()


async def _invoke_callback(
    callback: MagicMock,
    *,
    identity: TgIdentity | None | object = _UNSET,
    join_boss_lobby: MagicMock | None = None,
    leave_boss_lobby: MagicMock | None = None,
    cancel_boss_fight: MagicMock | None = None,
    boss_fights: IBossFightRepository | None = None,
    boss_participants: IBossParticipantRepository | None = None,
    players: IPlayerRepository | None = None,
    get_profile: MagicMock | None = None,
    clock: IClock | None = None,
) -> None:
    """Запустить callback-handler с дефолтами."""
    effective_identity = _identity() if identity is _UNSET else cast(TgIdentity | None, identity)
    await handle_boss_callback(
        cast(CallbackQuery, callback),
        effective_identity,
        cast(JoinBossLobby, join_boss_lobby or MagicMock(spec=JoinBossLobby)),
        cast(LeaveBossLobby, leave_boss_lobby or MagicMock(spec=LeaveBossLobby)),
        cast(CancelBossFight, cancel_boss_fight or MagicMock(spec=CancelBossFight)),
        boss_fights or FakeBossFightRepository(),
        boss_participants or FakeBossParticipantRepository(),
        players or FakePlayerRepository(),
        cast(GetProfile, get_profile or _stub_get_profile()),
        clock or FakeClock(_NOW),
        _bundle(),
        _RU,
    )


@pytest.mark.asyncio
class TestCallbackGuardClauses:
    async def test_no_identity_returns_silently(self) -> None:
        callback = _callback()
        await _invoke_callback(callback, identity=None)
        callback.answer.assert_not_called()

    async def test_no_message_returns_silently(self) -> None:
        callback = _callback(message_present=False)
        await _invoke_callback(callback)
        callback.answer.assert_not_called()

    async def test_no_data_returns_silently(self) -> None:
        callback = _callback()
        callback.data = None
        await _invoke_callback(callback)
        callback.answer.assert_not_called()

    async def test_invalid_callback_data_emits_generic_toast(self) -> None:
        callback = _callback(data="boss:bogus:7")
        await _invoke_callback(callback)
        callback.answer.assert_awaited_once()
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-generic-error" in toast


# ───────────────────── Callback boss:show_lobby ─────────────────────


@pytest.mark.asyncio
class TestShowLobbyCallback:
    async def test_fight_not_found_emits_toast(self) -> None:
        callback = _callback(data=f"boss:show_lobby:{_BOSS_FIGHT_ID}")
        await _invoke_callback(callback, boss_fights=FakeBossFightRepository())
        callback.answer.assert_awaited_once()
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-fight-not-found" in toast
        callback.message.edit_text.assert_not_called()

    async def test_fight_not_in_lobby_emits_invalid_state_toast(self) -> None:
        callback = _callback(data=f"boss:show_lobby:{_BOSS_FIGHT_ID}")
        boss_fights = FakeBossFightRepository(
            rows=[_boss_fight(status=BossFightStatus.IN_BATTLE)],
        )
        await _invoke_callback(callback, boss_fights=boss_fights)
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-invalid-state" in toast
        callback.message.edit_text.assert_not_called()

    async def test_success_renders_lobby_state_with_keyboard(self) -> None:
        callback = _callback(data=f"boss:show_lobby:{_BOSS_FIGHT_ID}")
        boss_fights = FakeBossFightRepository(rows=[_boss_fight()])
        players = FakePlayerRepository(
            rows=[
                _player(),
                _player(pid=_BOSS_PLAYER_ID, tg_id=2002, username="boss", length_cm=80),
            ],
        )
        await _invoke_callback(
            callback,
            boss_fights=boss_fights,
            players=players,
        )
        # Сначала ack без текста, затем edit_text с lobby-state.
        callback.answer.assert_awaited_once_with()
        callback.message.edit_text.assert_awaited_once()
        edit_call = callback.message.edit_text.await_args
        edit_text = edit_call.kwargs["text"]
        assert "bosses-lobby-state" in edit_text
        keyboard = edit_call.kwargs["reply_markup"]
        assert isinstance(keyboard, InlineKeyboardMarkup)
        # Лобби-клавиатура: 1×3 (join, leave, cancel).
        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 3
        callback_data_set = {btn.callback_data for btn in keyboard.inline_keyboard[0]}
        assert callback_data_set == {
            f"boss:join:{_BOSS_FIGHT_ID}",
            f"boss:leave:{_BOSS_FIGHT_ID}",
            f"boss:cancel:{_BOSS_FIGHT_ID}",
        }


# ───────────────────── Callback boss:join ─────────────────────


def _stub_join_boss_lobby(
    *,
    error: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=JoinBossLobby)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    fight = _boss_fight()
    participant = BossParticipant.raider(
        boss_fight_id=_BOSS_FIGHT_ID,
        player_id=99,
        is_summoner=False,
        length_at_join_cm=25,
        joined_at=_NOW,
    )
    use_case.execute = AsyncMock(
        return_value=BossLobbyJoined(boss_fight=fight, participant=participant),
    )
    return use_case


@pytest.mark.asyncio
class TestJoinCallback:
    async def test_fight_not_found_maps_to_toast(self) -> None:
        callback = _callback(data=f"boss:join:{_BOSS_FIGHT_ID}")
        join_uc = _stub_join_boss_lobby(
            error=BossFightNotFoundError(boss_fight_id=_BOSS_FIGHT_ID),
        )
        await _invoke_callback(callback, join_boss_lobby=join_uc)
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-fight-not-found" in toast

    async def test_lobby_closed_maps_to_toast(self) -> None:
        callback = _callback(data=f"boss:join:{_BOSS_FIGHT_ID}")
        join_uc = _stub_join_boss_lobby(
            error=BossFightLobbyClosedError(boss_fight_id=_BOSS_FIGHT_ID, status="IN_BATTLE"),
        )
        await _invoke_callback(callback, join_boss_lobby=join_uc)
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-lobby-closed" in toast

    async def test_player_not_found_maps_to_toast(self) -> None:
        callback = _callback(data=f"boss:join:{_BOSS_FIGHT_ID}")
        join_uc = _stub_join_boss_lobby(error=PlayerNotFoundError(tg_id=_RAIDER_TG_ID))
        await _invoke_callback(
            callback,
            identity=_identity(tg_user_id=_RAIDER_TG_ID),
            join_boss_lobby=join_uc,
        )
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-player-not-found" in toast

    async def test_player_frozen_maps_to_toast(self) -> None:
        callback = _callback(data=f"boss:join:{_BOSS_FIGHT_ID}")
        join_uc = _stub_join_boss_lobby(error=PlayerFrozenError(tg_id=_RAIDER_TG_ID))
        await _invoke_callback(
            callback,
            identity=_identity(tg_user_id=_RAIDER_TG_ID),
            join_boss_lobby=join_uc,
        )
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-player-frozen" in toast

    async def test_already_in_when_player_is_boss_uses_cannot_join_as_boss_toast(self) -> None:
        callback = _callback(data=f"boss:join:{_BOSS_FIGHT_ID}")
        join_uc = _stub_join_boss_lobby(
            error=AlreadyInBossFightError(player_id=_BOSS_PLAYER_ID),
        )
        boss_fights = FakeBossFightRepository(rows=[_boss_fight()])
        # Идентичность игрока, который пытается вступить, — id=2 (это босс).
        boss_player = _player(pid=_BOSS_PLAYER_ID, tg_id=2002, username="boss")
        boss_view = ProfileView(
            player=boss_player,
            display_name=DisplayName(value="Босс"),
        )

        # GetProfile возвращает ProfileView с player.id == boss_player_id.
        async def _execute(*, tg_id: int) -> ProfileView | None:
            return boss_view

        get_profile = MagicMock(spec=GetProfile)
        get_profile.execute = AsyncMock(side_effect=_execute)
        await _invoke_callback(
            callback,
            identity=_identity(tg_user_id=2002),
            join_boss_lobby=join_uc,
            boss_fights=boss_fights,
            get_profile=get_profile,
        )
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-cannot-join-as-boss" in toast

    async def test_already_in_when_player_is_raider_uses_already_in_fight_toast(self) -> None:
        callback = _callback(data=f"boss:join:{_BOSS_FIGHT_ID}")
        join_uc = _stub_join_boss_lobby(
            error=AlreadyInBossFightError(player_id=99),  # не равен boss_player_id
        )
        boss_fights = FakeBossFightRepository(rows=[_boss_fight()])
        # GetProfile возвращает ProfileView с player.id != boss_player_id.
        raider_view = ProfileView(
            player=_player(pid=99, tg_id=_RAIDER_TG_ID, username="raider"),
            display_name=DisplayName(value="Рейдер"),
        )

        async def _execute(*, tg_id: int) -> ProfileView | None:
            return raider_view

        get_profile = MagicMock(spec=GetProfile)
        get_profile.execute = AsyncMock(side_effect=_execute)
        await _invoke_callback(
            callback,
            identity=_identity(tg_user_id=_RAIDER_TG_ID),
            join_boss_lobby=join_uc,
            boss_fights=boss_fights,
            get_profile=get_profile,
        )
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-already-in-fight" in toast

    async def test_requirement_thickness_maps_to_toast(self) -> None:
        callback = _callback(data=f"boss:join:{_BOSS_FIGHT_ID}")
        join_uc = _stub_join_boss_lobby(
            error=BossFightRequirementError(
                player_id=_RAIDER_TG_ID,
                requirement="thickness",
                required=5,
                actual=3,
            ),
        )
        await _invoke_callback(callback, join_boss_lobby=join_uc)
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-requirement-thickness" in toast
        assert "required=5" in toast

    async def test_requirement_length_maps_to_toast(self) -> None:
        callback = _callback(data=f"boss:join:{_BOSS_FIGHT_ID}")
        join_uc = _stub_join_boss_lobby(
            error=BossFightRequirementError(
                player_id=_RAIDER_TG_ID,
                requirement="length",
                required=20,
                actual=15,
            ),
        )
        await _invoke_callback(callback, join_boss_lobby=join_uc)
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-requirement-length" in toast
        assert "required_cm=20" in toast

    async def test_success_emits_toast_and_refreshes_lobby(self) -> None:
        callback = _callback(data=f"boss:join:{_BOSS_FIGHT_ID}")
        join_uc = _stub_join_boss_lobby()
        boss_fights = FakeBossFightRepository(rows=[_boss_fight()])
        players = FakePlayerRepository(
            rows=[
                _player(),
                _player(pid=_BOSS_PLAYER_ID, tg_id=2002, username="boss", length_cm=80),
            ],
        )
        await _invoke_callback(
            callback,
            join_boss_lobby=join_uc,
            boss_fights=boss_fights,
            players=players,
        )
        # Toast «успех» отдан.
        toast = callback.answer.await_args.args[0]
        assert "bosses-join-toast-success" in toast
        # Refresh — edit_text c lobby-state.
        callback.message.edit_text.assert_awaited_once()
        edit_text = callback.message.edit_text.await_args.kwargs["text"]
        assert "bosses-lobby-state" in edit_text


# ───────────────────── Callback boss:leave ─────────────────────


def _stub_leave_boss_lobby(
    *,
    error: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=LeaveBossLobby)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    fight = _boss_fight()
    participant = BossParticipant.raider(
        boss_fight_id=_BOSS_FIGHT_ID,
        player_id=99,
        is_summoner=False,
        length_at_join_cm=25,
        joined_at=_NOW,
    )
    use_case.execute = AsyncMock(
        return_value=BossLobbyLeft(boss_fight=fight, removed_participant=participant),
    )
    return use_case


@pytest.mark.asyncio
class TestLeaveCallback:
    async def test_fight_not_found_emits_toast(self) -> None:
        callback = _callback(data=f"boss:leave:{_BOSS_FIGHT_ID}")
        # Пустой репо boss_fights — fight not found на pre-check.
        await _invoke_callback(callback)
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-fight-not-found" in toast

    async def test_fight_not_in_lobby_emits_lobby_closed_toast(self) -> None:
        callback = _callback(data=f"boss:leave:{_BOSS_FIGHT_ID}")
        boss_fights = FakeBossFightRepository(
            rows=[_boss_fight(status=BossFightStatus.IN_BATTLE)],
        )
        await _invoke_callback(callback, boss_fights=boss_fights)
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-lobby-closed" in toast

    async def test_player_not_found_on_pre_check(self) -> None:
        callback = _callback(data=f"boss:leave:{_BOSS_FIGHT_ID}")
        boss_fights = FakeBossFightRepository(rows=[_boss_fight()])
        # GetProfile возвращает None — игрок не найден.
        get_profile = MagicMock(spec=GetProfile)
        get_profile.execute = AsyncMock(return_value=None)
        await _invoke_callback(
            callback,
            boss_fights=boss_fights,
            get_profile=get_profile,
        )
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-player-not-found" in toast

    async def test_summoner_self_leave_emits_summoner_leaves_toast(self) -> None:
        callback = _callback(data=f"boss:leave:{_BOSS_FIGHT_ID}")
        boss_fights = FakeBossFightRepository(rows=[_boss_fight()])
        leave_uc = _stub_leave_boss_lobby()
        await _invoke_callback(
            callback,
            boss_fights=boss_fights,
            leave_boss_lobby=leave_uc,
        )
        # Use-case НЕ вызывается; toast — «нажми Отменить рейд».
        leave_uc.execute.assert_not_called()
        toast = callback.answer.await_args.args[0]
        assert "bosses-leave-toast-summoner-leaves" in toast

    async def test_not_in_boss_fight_maps_to_not_a_participant_toast(self) -> None:
        callback = _callback(
            data=f"boss:leave:{_BOSS_FIGHT_ID}",
        )
        boss_fights = FakeBossFightRepository(rows=[_boss_fight()])
        # GetProfile отдаёт игрока с id != summoner_player_id.
        raider_view = ProfileView(
            player=_player(pid=99, tg_id=_RAIDER_TG_ID, username="raider"),
            display_name=DisplayName(value="Рейдер"),
        )
        get_profile = MagicMock(spec=GetProfile)
        get_profile.execute = AsyncMock(return_value=raider_view)
        leave_uc = _stub_leave_boss_lobby(
            error=NotInBossFightError(boss_fight_id=_BOSS_FIGHT_ID, player_id=99),
        )
        await _invoke_callback(
            callback,
            identity=_identity(tg_user_id=_RAIDER_TG_ID),
            boss_fights=boss_fights,
            leave_boss_lobby=leave_uc,
            get_profile=get_profile,
        )
        toast = callback.answer.await_args.args[0]
        assert "bosses-leave-toast-not-a-participant" in toast

    async def test_success_emits_toast_and_refreshes_lobby(self) -> None:
        callback = _callback(data=f"boss:leave:{_BOSS_FIGHT_ID}")
        boss_fights = FakeBossFightRepository(rows=[_boss_fight()])
        players = FakePlayerRepository(
            rows=[
                _player(),
                _player(pid=_BOSS_PLAYER_ID, tg_id=2002, username="boss", length_cm=80),
                _player(pid=99, tg_id=_RAIDER_TG_ID, username="raider"),
            ],
        )
        # GetProfile отдаёт рейдера на pre-check.
        raider_view = ProfileView(
            player=_player(pid=99, tg_id=_RAIDER_TG_ID, username="raider"),
            display_name=DisplayName(value="Рейдер"),
        )

        async def _execute(*, tg_id: int) -> ProfileView | None:
            if tg_id == _RAIDER_TG_ID:
                return raider_view
            if tg_id == _SUMMONER_TG_ID:
                return ProfileView(
                    player=_player(),
                    display_name=DisplayName(value="Саммонер"),
                )
            return ProfileView(
                player=_player(pid=_BOSS_PLAYER_ID, tg_id=2002, username="boss"),
                display_name=DisplayName(value="Босс"),
            )

        get_profile = MagicMock(spec=GetProfile)
        get_profile.execute = AsyncMock(side_effect=_execute)
        leave_uc = _stub_leave_boss_lobby()
        await _invoke_callback(
            callback,
            identity=_identity(tg_user_id=_RAIDER_TG_ID),
            boss_fights=boss_fights,
            players=players,
            leave_boss_lobby=leave_uc,
            get_profile=get_profile,
        )
        toast = callback.answer.await_args.args[0]
        assert "bosses-leave-toast-success" in toast
        # Refresh — edit_text c lobby-state.
        callback.message.edit_text.assert_awaited_once()


# ───────────────────── Callback boss:cancel ─────────────────────


def _stub_cancel_boss_fight(
    *,
    error: BaseException | None = None,
    was_already_cancelled: bool = False,
) -> MagicMock:
    use_case = MagicMock(spec=CancelBossFight)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    fight = _boss_fight(status=BossFightStatus.CANCELLED)
    use_case.execute = AsyncMock(
        return_value=BossFightCancelled(
            boss_fight=fight,
            was_already_cancelled=was_already_cancelled,
        ),
    )
    return use_case


@pytest.mark.asyncio
class TestCancelCallback:
    async def test_fight_not_found_emits_toast_no_edit(self) -> None:
        callback = _callback(data=f"boss:cancel:{_BOSS_FIGHT_ID}")
        cancel_uc = _stub_cancel_boss_fight(
            error=BossFightNotFoundError(boss_fight_id=_BOSS_FIGHT_ID),
        )
        await _invoke_callback(callback, cancel_boss_fight=cancel_uc)
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-fight-not-found" in toast
        callback.message.edit_text.assert_not_called()

    async def test_invalid_state_emits_toast_no_edit(self) -> None:
        callback = _callback(data=f"boss:cancel:{_BOSS_FIGHT_ID}")
        cancel_uc = _stub_cancel_boss_fight(
            error=InvalidBossFightStateError(
                boss_fight_id=_BOSS_FIGHT_ID,
                expected="LOBBY",
                actual="FINISHED",
            ),
        )
        await _invoke_callback(callback, cancel_boss_fight=cancel_uc)
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-invalid-state" in toast
        callback.message.edit_text.assert_not_called()

    async def test_not_authorized_emits_not_summoner_toast(self) -> None:
        callback = _callback(data=f"boss:cancel:{_BOSS_FIGHT_ID}")
        cancel_uc = _stub_cancel_boss_fight(
            error=NotAuthorizedToCancelBossError(
                boss_fight_id=_BOSS_FIGHT_ID,
                player_id=99,
                summoner_player_id=_SUMMONER_PLAYER_ID,
            ),
        )
        await _invoke_callback(callback, cancel_boss_fight=cancel_uc)
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-not-summoner" in toast

    async def test_player_not_found_emits_toast(self) -> None:
        callback = _callback(data=f"boss:cancel:{_BOSS_FIGHT_ID}")
        cancel_uc = _stub_cancel_boss_fight(
            error=PlayerNotFoundError(tg_id=_SUMMONER_TG_ID),
        )
        await _invoke_callback(callback, cancel_boss_fight=cancel_uc)
        toast = callback.answer.await_args.args[0]
        assert "bosses-callback-toast-player-not-found" in toast

    async def test_success_emits_toast_and_replaces_message(self) -> None:
        callback = _callback(data=f"boss:cancel:{_BOSS_FIGHT_ID}")
        cancel_uc = _stub_cancel_boss_fight()
        await _invoke_callback(callback, cancel_boss_fight=cancel_uc)
        toast = callback.answer.await_args.args[0]
        assert "bosses-cancel-toast-success" in toast
        callback.message.edit_text.assert_awaited_once()
        edit_args = callback.message.edit_text.await_args
        edit_text = edit_args.kwargs.get("text") or edit_args.args[0]
        assert "bosses-cancel-message" in edit_text

    async def test_already_cancelled_uses_idempotent_toast(self) -> None:
        callback = _callback(data=f"boss:cancel:{_BOSS_FIGHT_ID}")
        cancel_uc = _stub_cancel_boss_fight(was_already_cancelled=True)
        await _invoke_callback(callback, cancel_boss_fight=cancel_uc)
        toast = callback.answer.await_args.args[0]
        assert "bosses-cancel-toast-already-cancelled" in toast
        # Сообщение всё равно заменяется на «рейд отменён».
        callback.message.edit_text.assert_awaited_once()

    async def test_use_case_input_dto_carries_boss_fight_id_and_tg_id(self) -> None:
        callback = _callback(data=f"boss:cancel:{_BOSS_FIGHT_ID}")
        cancel_uc = _stub_cancel_boss_fight()
        await _invoke_callback(callback, cancel_boss_fight=cancel_uc)
        input_dto = cancel_uc.execute.await_args.args[0]
        assert input_dto.boss_fight_id == _BOSS_FIGHT_ID
        assert input_dto.tg_id == _SUMMONER_TG_ID
