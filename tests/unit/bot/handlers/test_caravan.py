"""Юнит-тесты `/caravan`-handler-а (Спринт 3.2-D, ГДД §9.2).

Покрытие:
- chat_kind: private → success / group / supergroup → instruction / channel → other.
- Парсинг аргументов: usage / receiver-invalid / contribution-invalid (non-int + ≤ 0).
- Pre-check: not-registered / no-clan / not-a-leader / dangling FK.
- Маппинг доменных ошибок `CreateCaravan` → локализованные ответы.
- Happy-path: подтверждение лидеру + объявление в чате клана-отправителя
  с инлайн-клавиатурой `caravan:show_lobby:<id>`; при `TelegramAPIError`
  на отправке объявления handler не падает.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Chat, InlineKeyboardMarkup, Message

from pipirik_wars.application.caravans import CaravanCreated, CreateCaravan
from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.player import GetProfile, ProfileView
from pipirik_wars.bot.handlers.caravan import handle_caravan
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.caravan import (
    AlreadyInCaravanError,
    Caravan,
    CaravanContribution,
    CaravanCooldownError,
    CaravanParticipant,
    CaravanRequirementError,
    CaravanRoleConflictError,
    CaravanStatus,
)
from pipirik_wars.domain.clan import (
    ChatKind,
    Clan,
    ClanFrozenError,
    ClanMember,
    ClanMemberRole,
    ClanStatus,
    ClanTitle,
)
from pipirik_wars.domain.player import (
    DisplayName,
    Length,
    Player,
    PlayerFrozenError,
    PlayerNotFoundError,
    PlayerStatus,
    Thickness,
    Username,
)
from pipirik_wars.shared.errors import IntegrityError
from tests.fakes import (
    FakeClanMembershipRepository,
    FakeClanRepository,
    FakeMessageBundle,
    FakePlayerRepository,
)
from tests.unit.domain.balance.factories import build_valid_balance

_NOW = datetime(2026, 5, 8, 12, 0, tzinfo=UTC)
_RU = Locale("ru")
_LEADER_TG_ID = 100
_SENDER_CHAT_ID = -1001
_RECEIVER_CHAT_ID = -1002
_CARAVAN_ID = 7

_BalanceFake = MagicMock  # типизация ниже — для краткости


# ───────────────────── фикстуры / помощники ─────────────────────


def _bundle() -> IMessageBundle:
    return FakeMessageBundle()


def _balance() -> MagicMock:
    """`IBalanceConfig` с реальным `BalanceConfig`-снимком.

    Используем `MagicMock` (а не `FakeBalanceConfig`), чтобы проверять
    в тестах, что handler действительно зовёт `get()` (а не клеит
    статичные числа).
    """
    snapshot = build_valid_balance()
    cfg = MagicMock()
    cfg.get = MagicMock(return_value=snapshot)
    return cfg


def _identity(
    *,
    chat_kind: str = "private",
    tg_user_id: int = _LEADER_TG_ID,
    chat_id: int = _LEADER_TG_ID,
) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=chat_id,
        chat_kind=chat_kind,
        language_code=None,
    )


def _msg(
    *,
    text: str = f"/caravan {_RECEIVER_CHAT_ID} 30",
    chat_type: str = "private",
    chat_id: int = _LEADER_TG_ID,
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
    pid: int = 1,
    tg_id: int = _LEADER_TG_ID,
    length_cm: int = 80,
    thickness_level: int = 8,
) -> Player:
    return Player(
        id=pid,
        tg_id=tg_id,
        username=Username(value="leader"),
        length=Length(cm=length_cm),
        thickness=Thickness(level=thickness_level),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _sender_clan(*, clan_id: int = 1, chat_id: int = _SENDER_CHAT_ID) -> Clan:
    return Clan(
        id=clan_id,
        chat_id=chat_id,
        chat_kind=ChatKind.GROUP,
        title=ClanTitle(value="Клан-Отправитель"),
        status=ClanStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _receiver_clan(*, clan_id: int = 2, chat_id: int = _RECEIVER_CHAT_ID) -> Clan:
    return Clan(
        id=clan_id,
        chat_id=chat_id,
        chat_kind=ChatKind.GROUP,
        title=ClanTitle(value="Клан-Получатель"),
        status=ClanStatus.ACTIVE,
        created_at=_NOW,
        updated_at=_NOW,
    )


async def _seeded_repos(
    *,
    leader_in_clan: bool = True,
    leader_role: ClanMemberRole = ClanMemberRole.LEADER,
    seed_receiver: bool = True,
) -> tuple[FakePlayerRepository, FakeClanMembershipRepository, FakeClanRepository]:
    players = FakePlayerRepository()
    clan_members = FakeClanMembershipRepository()
    clans = FakeClanRepository()
    leader_player = _player()
    await players.add(
        Player.new(
            tg_id=leader_player.tg_id,
            username=Username(value="leader"),
            now=_NOW,
        )
    )
    sender = await clans.add(_sender_clan(clan_id=None))  # type: ignore[arg-type]
    if seed_receiver:
        await clans.add(_receiver_clan(clan_id=None))  # type: ignore[arg-type]
    if leader_in_clan:
        assert sender.id is not None
        # Игрок только что добавлен — у него `id=1`.
        await clan_members.add(
            ClanMember(
                clan_id=sender.id,
                player_id=1,
                role=leader_role,
                joined_at=_NOW,
            )
        )
    return players, clan_members, clans


def _stub_create_caravan(
    *,
    success_caravan: Caravan | None = None,
    error: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=CreateCaravan)
    if error is not None:
        use_case.execute = AsyncMock(side_effect=error)
        return use_case
    caravan = success_caravan or Caravan(
        id=_CARAVAN_ID,
        sender_clan_id=1,
        receiver_clan_id=2,
        leader_player_id=1,
        status=CaravanStatus.LOBBY,
        started_at=_NOW,
        lobby_ends_at=_NOW + timedelta(minutes=20),
        battle_ends_at=_NOW + timedelta(minutes=80),
        random_seed=12345,
        finished_at=None,
    )
    leader_part = CaravanParticipant.caravaneer(
        caravan_id=cast(int, caravan.id),
        player_id=1,
        contribution=CaravanContribution(cm=30),
        is_leader=True,
        joined_at=_NOW,
    )
    use_case.execute = AsyncMock(
        return_value=CaravanCreated(caravan=caravan, leader_participant=leader_part),
    )
    return use_case


def _stub_get_profile(*, view: ProfileView | None = None) -> MagicMock:
    use_case = MagicMock(spec=GetProfile)
    use_case.execute = AsyncMock(
        return_value=view
        if view is not None
        else ProfileView(player=_player(), display_name=DisplayName(value="Пипирик")),
    )
    return use_case


async def _invoke(
    msg: MagicMock,
    *,
    identity: TgIdentity | None,
    create_caravan: MagicMock | None = None,
    get_profile: MagicMock | None = None,
    players: FakePlayerRepository | None = None,
    clan_members: FakeClanMembershipRepository | None = None,
    clans: FakeClanRepository | None = None,
    bot: MagicMock | None = None,
) -> MagicMock:
    """Запустить handler с дефолтами; возвращает `bot`-stub для проверок."""
    if players is None or clan_members is None or clans is None:
        players, clan_members, clans = await _seeded_repos()
    bot = bot or _stub_bot()
    await handle_caravan(
        cast(Message, msg),
        identity,
        cast(CreateCaravan, create_caravan or _stub_create_caravan()),
        cast(GetProfile, get_profile or _stub_get_profile()),
        players,
        clan_members,
        clans,
        _balance(),
        cast(Bot, bot),
        _bundle(),
        _RU,
    )
    return bot


# ───────────────────────── chat_kind gate ─────────────────────────


@pytest.mark.asyncio
class TestChatKindGate:
    async def test_group_chat_uses_group_key(self) -> None:
        msg = _msg(chat_type="group")
        await _invoke(msg, identity=_identity(chat_kind="group"))
        msg.answer.assert_awaited_once_with("ru:caravans-group")

    async def test_supergroup_chat_uses_group_key(self) -> None:
        msg = _msg(chat_type="supergroup")
        await _invoke(msg, identity=_identity(chat_kind="supergroup"))
        msg.answer.assert_awaited_once_with("ru:caravans-group")

    async def test_no_identity_uses_other_key(self) -> None:
        msg = _msg(chat_type="private")
        await _invoke(msg, identity=None)
        msg.answer.assert_awaited_once_with("ru:caravans-other")

    async def test_channel_chat_uses_other_key(self) -> None:
        # `chat_kind` приходит из `TgIdentity`, не из `message.chat.type`.
        msg = _msg(chat_type="channel")
        identity = _identity(chat_kind="channel")
        await _invoke(msg, identity=identity)
        msg.answer.assert_awaited_once_with("ru:caravans-other")


# ───────────────────────── argument parsing ─────────────────────────


@pytest.mark.asyncio
class TestArgumentParsing:
    async def test_no_args_returns_usage(self) -> None:
        msg = _msg(text="/caravan")
        await _invoke(msg, identity=_identity())
        msg.answer.assert_awaited_once_with("ru:caravans-usage")

    async def test_one_arg_returns_usage(self) -> None:
        msg = _msg(text="/caravan -1001")
        await _invoke(msg, identity=_identity())
        msg.answer.assert_awaited_once_with("ru:caravans-usage")

    async def test_three_args_returns_usage(self) -> None:
        # Третий аргумент → handler должен сказать «не два аргумента».
        msg = _msg(text="/caravan -1001 30 extra")
        await _invoke(msg, identity=_identity())
        msg.answer.assert_awaited_once_with("ru:caravans-usage")

    async def test_receiver_not_int_returns_invalid(self) -> None:
        msg = _msg(text="/caravan abc 30")
        await _invoke(msg, identity=_identity())
        sent = msg.answer.await_args.args[0]
        assert "caravans-receiver-invalid" in sent
        assert "value=abc" in sent

    async def test_contribution_not_int_returns_invalid(self) -> None:
        msg = _msg(text="/caravan -1001 thirty")
        await _invoke(msg, identity=_identity())
        sent = msg.answer.await_args.args[0]
        assert "caravans-contribution-invalid" in sent
        assert "value=thirty" in sent

    async def test_contribution_zero_returns_invalid(self) -> None:
        msg = _msg(text="/caravan -1001 0")
        await _invoke(msg, identity=_identity())
        sent = msg.answer.await_args.args[0]
        assert "caravans-contribution-invalid" in sent
        assert "value=0" in sent

    async def test_contribution_negative_returns_invalid(self) -> None:
        msg = _msg(text="/caravan -1001 -5")
        await _invoke(msg, identity=_identity())
        sent = msg.answer.await_args.args[0]
        assert "caravans-contribution-invalid" in sent
        assert "value=-5" in sent

    async def test_message_text_none_returns_usage(self) -> None:
        msg = _msg()
        msg.text = None
        await _invoke(msg, identity=_identity())
        msg.answer.assert_awaited_once_with("ru:caravans-usage")


# ───────────────────────── handler-level pre-check ─────────────────────────


@pytest.mark.asyncio
class TestPreCheck:
    async def test_player_not_registered(self) -> None:
        # Игрока нет в `players`-репо → handler не зовёт use-case.
        players = FakePlayerRepository()
        clan_members = FakeClanMembershipRepository()
        clans = FakeClanRepository()
        msg = _msg()
        create_uc = _stub_create_caravan()
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        msg.answer.assert_awaited_once_with("ru:caravans-not-registered")
        create_uc.execute.assert_not_called()

    async def test_player_without_clan(self) -> None:
        players, clan_members, clans = await _seeded_repos(leader_in_clan=False)
        msg = _msg()
        create_uc = _stub_create_caravan()
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        msg.answer.assert_awaited_once_with("ru:caravans-no-clan")
        create_uc.execute.assert_not_called()

    async def test_player_is_member_not_leader(self) -> None:
        players, clan_members, clans = await _seeded_repos(
            leader_role=ClanMemberRole.MEMBER,
        )
        msg = _msg()
        create_uc = _stub_create_caravan()
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        msg.answer.assert_awaited_once_with("ru:caravans-not-a-leader")
        create_uc.execute.assert_not_called()


# ─────────────────────── domain-error mapping ───────────────────────


@pytest.mark.asyncio
class TestDomainErrorMapping:
    async def test_player_not_found_from_use_case(self) -> None:
        # Pre-check прошёл (membership резолвится), но use-case бросил
        # `PlayerNotFoundError` (например, между pre-check и UoW игрок исчез).
        players, clan_members, clans = await _seeded_repos()
        msg = _msg()
        create_uc = _stub_create_caravan(error=PlayerNotFoundError(tg_id=_LEADER_TG_ID))
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        msg.answer.assert_awaited_once_with("ru:caravans-not-registered")

    async def test_player_frozen(self) -> None:
        players, clan_members, clans = await _seeded_repos()
        msg = _msg()
        create_uc = _stub_create_caravan(error=PlayerFrozenError(tg_id=_LEADER_TG_ID))
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        msg.answer.assert_awaited_once_with("ru:caravans-player-frozen")

    async def test_receiver_not_registered(self) -> None:
        # `CreateCaravan._fetch_clan` бросает `IntegrityError` если
        # receiver-чата нет в `clans`. Handler маппит это на
        # `caravans-receiver-not-found` (sender мы уже резолвили сами).
        players, clan_members, clans = await _seeded_repos(seed_receiver=False)
        msg = _msg()
        create_uc = _stub_create_caravan(
            error=IntegrityError(f"chat_id={_RECEIVER_CHAT_ID} is not a registered clan"),
        )
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        sent = msg.answer.await_args.args[0]
        assert "caravans-receiver-not-found" in sent
        assert f"chat_id={_RECEIVER_CHAT_ID}" in sent

    async def test_clan_frozen_sender(self) -> None:
        players, clan_members, clans = await _seeded_repos()
        msg = _msg()
        create_uc = _stub_create_caravan(
            error=ClanFrozenError(chat_id=_SENDER_CHAT_ID),
        )
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        msg.answer.assert_awaited_once_with("ru:caravans-clan-frozen-sender")

    async def test_clan_frozen_receiver(self) -> None:
        players, clan_members, clans = await _seeded_repos()
        msg = _msg()
        create_uc = _stub_create_caravan(
            error=ClanFrozenError(chat_id=_RECEIVER_CHAT_ID),
        )
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        msg.answer.assert_awaited_once_with("ru:caravans-clan-frozen-receiver")

    async def test_role_conflict_maps_to_not_a_leader(self) -> None:
        # Между pre-check-ом и UoW лидерство пересело — use-case бросит
        # `CaravanRoleConflictError`. Handler выдаёт общий «не лидер».
        players, clan_members, clans = await _seeded_repos()
        msg = _msg()
        create_uc = _stub_create_caravan(
            error=CaravanRoleConflictError(
                player_id=1,
                attempted_role="leader",
                reason="player is not the clan leader",
            ),
        )
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        msg.answer.assert_awaited_once_with("ru:caravans-not-a-leader")

    async def test_already_in_caravan(self) -> None:
        players, clan_members, clans = await _seeded_repos()
        msg = _msg()
        create_uc = _stub_create_caravan(error=AlreadyInCaravanError(player_id=1))
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        msg.answer.assert_awaited_once_with("ru:caravans-already-in")

    async def test_cooldown_rounds_seconds_up_to_minutes(self) -> None:
        players, clan_members, clans = await _seeded_repos()
        msg = _msg()
        # 61 секунда → ceil(61/60) = 2 минуты.
        create_uc = _stub_create_caravan(
            error=CaravanCooldownError(clan_id=1, actual_remaining_seconds=61),
        )
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        sent = msg.answer.await_args.args[0]
        assert "caravans-cooldown" in sent
        assert "remaining_minutes=2" in sent

    async def test_cooldown_floor_is_at_least_one_minute(self) -> None:
        players, clan_members, clans = await _seeded_repos()
        msg = _msg()
        create_uc = _stub_create_caravan(
            error=CaravanCooldownError(clan_id=1, actual_remaining_seconds=1),
        )
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        sent = msg.answer.await_args.args[0]
        assert "remaining_minutes=1" in sent

    async def test_requirement_thickness(self) -> None:
        players, clan_members, clans = await _seeded_repos()
        msg = _msg()
        create_uc = _stub_create_caravan(
            error=CaravanRequirementError(
                player_id=1,
                requirement="thickness",
                required=7,
                actual=5,
            ),
        )
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        sent = msg.answer.await_args.args[0]
        assert "caravans-requirement-thickness" in sent
        assert "required=7" in sent
        assert "actual=5" in sent

    async def test_requirement_length_total(self) -> None:
        players, clan_members, clans = await _seeded_repos()
        msg = _msg()
        create_uc = _stub_create_caravan(
            error=CaravanRequirementError(
                player_id=1,
                requirement="length_total",
                required=20,
                actual=15,
            ),
        )
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        sent = msg.answer.await_args.args[0]
        assert "caravans-requirement-length" in sent
        assert "required_cm=20" in sent
        assert "actual_cm=15" in sent

    async def test_requirement_length_after_contribution(self) -> None:
        players, clan_members, clans = await _seeded_repos()
        msg = _msg()
        create_uc = _stub_create_caravan(
            error=CaravanRequirementError(
                player_id=1,
                requirement="length_after_contribution",
                required=20,
                actual=18,
            ),
        )
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        sent = msg.answer.await_args.args[0]
        assert "caravans-requirement-length" in sent
        assert "required_cm=20" in sent
        assert "actual_cm=18" in sent


# ──────────────────────────── happy path ────────────────────────────


@pytest.mark.asyncio
class TestHappyPath:
    async def test_success_sends_private_confirmation_and_announcement(self) -> None:
        players, clan_members, clans = await _seeded_repos()
        msg = _msg()
        create_uc = _stub_create_caravan()
        bot = await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        # Личное подтверждение лидеру.
        msg.answer.assert_awaited_once()
        private_text = msg.answer.await_args.args[0]
        assert "caravans-created-private" in private_text
        assert "receiver_clan_name=Клан-Получатель" in private_text
        assert "contribution_cm=30" in private_text
        assert "lobby_minutes=20" in private_text
        # Объявление в чате клана-отправителя.
        bot.send_message.assert_awaited_once()
        kwargs = bot.send_message.await_args.kwargs
        assert kwargs["chat_id"] == _SENDER_CHAT_ID
        assert "caravans-created-announcement" in kwargs["text"]
        assert "receiver_clan_name=Клан-Получатель" in kwargs["text"]
        markup = kwargs["reply_markup"]
        assert isinstance(markup, InlineKeyboardMarkup)
        # Единственная кнопка: «Показать лобби» с callback `caravan:show_lobby:<id>`.
        assert len(markup.inline_keyboard) == 1
        assert len(markup.inline_keyboard[0]) == 1
        button = markup.inline_keyboard[0][0]
        assert button.callback_data == f"caravan:show_lobby:{_CARAVAN_ID}"
        assert "caravans-button-show-lobby" in (button.text or "")

    async def test_use_case_input_dto_uses_resolved_sender_chat_id(self) -> None:
        players, clan_members, clans = await _seeded_repos()
        msg = _msg(text=f"/caravan {_RECEIVER_CHAT_ID} 30")
        create_uc = _stub_create_caravan()
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
        )
        # Use-case получил DTO с резолвленным `sender_chat_id`
        # (handler не доверяет введённому, берёт из membership лидера).
        ((dto,), _kwargs) = create_uc.execute.await_args
        assert dto.initiator_tg_id == _LEADER_TG_ID
        assert dto.sender_chat_id == _SENDER_CHAT_ID
        assert dto.receiver_chat_id == _RECEIVER_CHAT_ID
        assert dto.contribution_cm == 30

    async def test_announcement_failure_does_not_propagate(self) -> None:
        players, clan_members, clans = await _seeded_repos()
        msg = _msg()
        bot = _stub_bot()
        bot.send_message.side_effect = TelegramAPIError(
            method=MagicMock(),
            message="bot kicked",
        )
        create_uc = _stub_create_caravan()
        # Не должно бросить — handler ловит `TelegramAPIError`.
        await _invoke(
            msg,
            identity=_identity(),
            players=players,
            clan_members=clan_members,
            clans=clans,
            create_caravan=create_uc,
            bot=bot,
        )
        # Личное подтверждение всё равно ушло.
        msg.answer.assert_awaited_once()
