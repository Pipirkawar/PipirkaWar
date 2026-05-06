"""Unit-тесты handler-ов `/find_player`, `/player`, `/freeze`, `/unfreeze`,
`/ban`, `/confirm` (Спринт 2.5-B). Раскручиваются по мере появления
соответствующих use-case-ов; каждый тест-блок изолирован по команде.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters.command import CommandObject
from aiogram.types import Chat, Message

from pipirik_wars.application.admin import (
    ClanCardInfo,
    FindPlayers,
    FindPlayersOutput,
    ForestCardInfo,
    FreezePlayer,
    FreezePlayerOutput,
    GetPlayerCard,
    GetPlayerCardOutput,
    PlayerCard,
    PlayerSummary,
    UnfreezePlayer,
    UnfreezePlayerOutput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.bot.handlers.admin_support import (
    REPLY_NON_PRIVATE_RU,
    handle_find_player,
    handle_freeze,
    handle_player,
    handle_unfreeze,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.clan import ClanMemberRole, ClanStatus
from pipirik_wars.domain.forest import ForestRunStatus
from pipirik_wars.domain.player import PlayerStatus
from pipirik_wars.domain.player.errors import PlayerNotFoundError

_RU = Locale("ru")


def _msg_mock(chat_type: str = "private") -> MagicMock:
    msg = MagicMock()
    msg.chat = Chat(id=42, type=chat_type)
    msg.answer = AsyncMock()
    return msg


def _identity(chat_kind: str = "private", tg_user_id: int = 42) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=42,
        chat_kind=chat_kind,
        language_code=None,
    )


def _command(args: str | None) -> CommandObject:
    return CommandObject(prefix="/", command="find_player", mention=None, args=args)


class _StubBundle(IMessageBundle):
    """Минимальный stub `IMessageBundle` без I/O.

    Возвращает строку вида `"<key>:<sorted kwargs as 'k=v'>"`. Позволяет
    проверить, что handler выбрал правильный ключ и передал нужные
    параметры, без зависимости от `.ftl`-файлов на диске.
    """

    def format(
        self,
        key: MessageKey,
        *,
        locale: Locale,
        **kwargs: object,
    ) -> str:
        params = ",".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return f"{key}|{locale.code}|{params}"


@pytest.fixture
def bundle() -> IMessageBundle:
    return _StubBundle()


def _stub_find_players(*, output: FindPlayersOutput | None = None) -> FindPlayers:
    fake = MagicMock(spec=FindPlayers)
    if output is not None:
        fake.execute = AsyncMock(return_value=output)
    else:
        fake.execute = AsyncMock()
    return cast(FindPlayers, fake)


@pytest.mark.asyncio
class TestHandleFindPlayer:
    async def test_non_private_chat_replies_only_dm(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="group")
        find = _stub_find_players()

        await handle_find_player(
            message=cast(Message, msg),
            command=_command("ivan"),
            tg_identity=_identity(chat_kind="group"),
            find_players=find,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        find.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_missing_identity_replies_only_dm(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="private")
        find = _stub_find_players()

        await handle_find_player(
            message=cast(Message, msg),
            command=_command("ivan"),
            tg_identity=None,
            find_players=find,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        find.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_empty_query_replies_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        find = _stub_find_players()

        await handle_find_player(
            message=cast(Message, msg),
            command=_command("   "),
            tg_identity=_identity(),
            find_players=find,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once()
        text = msg.answer.await_args.args[0]
        assert "admin-find-player-usage" in text
        find.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_authorization_error_replies_not_authorized(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        find = _stub_find_players()
        find.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=AuthorizationError(requirement="x", detail="y"),
        )

        await handle_find_player(
            message=cast(Message, msg),
            command=_command("ivan"),
            tg_identity=_identity(),
            find_players=find,
            bundle=bundle,
            locale=_RU,
        )

        text = msg.answer.await_args.args[0]
        assert "admin-find-player-not-authorized" in text

    async def test_empty_results_replies_empty(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        find = _stub_find_players(
            output=FindPlayersOutput(query="ghost", results=()),
        )

        await handle_find_player(
            message=cast(Message, msg),
            command=_command("ghost"),
            tg_identity=_identity(),
            find_players=find,
            bundle=bundle,
            locale=_RU,
        )

        text = msg.answer.await_args.args[0]
        assert "admin-find-player-empty" in text
        assert "query=ghost" in text

    async def test_results_renders_header_and_rows(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        results = (
            PlayerSummary(
                tg_id=100,
                username="ivan",
                name="Иванушка",
                title=None,
                length_cm=2,
                thickness_level=1,
                status=PlayerStatus.ACTIVE,
                anticheat_ban_until=None,
            ),
            PlayerSummary(
                tg_id=101,
                username=None,
                name=None,
                title=None,
                length_cm=10,
                thickness_level=2,
                status=PlayerStatus.FROZEN,
                anticheat_ban_until=None,
            ),
        )
        find = _stub_find_players(
            output=FindPlayersOutput(query="ivan", results=results),
        )

        await handle_find_player(
            message=cast(Message, msg),
            command=_command("ivan"),
            tg_identity=_identity(),
            find_players=find,
            bundle=bundle,
            locale=_RU,
        )

        text = msg.answer.await_args.args[0]
        # Заголовок + 2 строки.
        assert "admin-find-player-header" in text
        assert "count=2" in text
        # Первая строка: tg_id=100, username=ivan
        assert "tg_id=100" in text
        # Для пропущенных полей (`username=None`, `name=None`) отрисуется тире.
        assert "username=—" in text
        assert "name=—" in text
        # Статусы локализуются.
        assert "status=активен" in text
        assert "status=заморожен" in text

    async def test_use_case_called_with_normalized_query(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        find = _stub_find_players(
            output=FindPlayersOutput(query="ivan", results=()),
        )

        await handle_find_player(
            message=cast(Message, msg),
            command=_command("  ivan  "),
            tg_identity=_identity(),
            find_players=find,
            bundle=bundle,
            locale=_RU,
        )

        find.execute.assert_awaited_once()  # type: ignore[attr-defined]
        inp = find.execute.await_args.kwargs.get("inp") or find.execute.await_args.args[0]  # type: ignore[attr-defined]
        assert inp.query == "ivan"
        assert inp.actor_tg_id == 42
        assert inp.tg_chat_id == 42


# ── /player ─────────────────────────────────────────────────────────────────


def _stub_get_player_card(*, output: GetPlayerCardOutput | None = None) -> GetPlayerCard:
    fake = MagicMock(spec=GetPlayerCard)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(GetPlayerCard, fake)


def _command_player(args: str | None) -> CommandObject:
    return CommandObject(prefix="/", command="player", mention=None, args=args)


@pytest.mark.asyncio
class TestHandlePlayer:
    async def test_non_private_chat_replies_only_dm(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="group")
        get_card = _stub_get_player_card()

        await handle_player(
            message=cast(Message, msg),
            command=_command_player("100"),
            tg_identity=_identity(chat_kind="group"),
            get_player_card=get_card,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        get_card.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_empty_args_replies_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        get_card = _stub_get_player_card()

        await handle_player(
            message=cast(Message, msg),
            command=_command_player("   "),
            tg_identity=_identity(),
            get_player_card=get_card,
            bundle=bundle,
            locale=_RU,
        )

        text = msg.answer.await_args.args[0]
        assert "admin-player-usage" in text

    async def test_non_integer_arg_replies_bad_id(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        get_card = _stub_get_player_card()

        await handle_player(
            message=cast(Message, msg),
            command=_command_player("not-an-int"),
            tg_identity=_identity(),
            get_player_card=get_card,
            bundle=bundle,
            locale=_RU,
        )

        text = msg.answer.await_args.args[0]
        assert "admin-player-bad-id" in text
        assert "value=not-an-int" in text

    async def test_authorization_error_replies_not_authorized(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        get_card = _stub_get_player_card()
        get_card.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=AuthorizationError(requirement="x", detail="y"),
        )

        await handle_player(
            message=cast(Message, msg),
            command=_command_player("100"),
            tg_identity=_identity(),
            get_player_card=get_card,
            bundle=bundle,
            locale=_RU,
        )

        text = msg.answer.await_args.args[0]
        assert "admin-player-not-authorized" in text

    async def test_not_found_replies_not_found(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        get_card = _stub_get_player_card(
            output=GetPlayerCardOutput(target_tg_id=999, card=None),
        )

        await handle_player(
            message=cast(Message, msg),
            command=_command_player("999"),
            tg_identity=_identity(),
            get_player_card=get_card,
            bundle=bundle,
            locale=_RU,
        )

        text = msg.answer.await_args.args[0]
        assert "admin-player-not-found" in text
        assert "tg_id=999" in text

    async def test_card_renders_summary_clan_and_forest(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        now = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)
        summary = PlayerSummary(
            tg_id=100,
            username="ivan",
            name="Иванушка",
            title=None,
            length_cm=10,
            thickness_level=2,
            status=PlayerStatus.ACTIVE,
            anticheat_ban_until=None,
        )
        clan = ClanCardInfo(
            clan_id=7,
            chat_id=-100500,
            title="The Pipiriks",
            status=ClanStatus.ACTIVE,
            role=ClanMemberRole.LEADER,
            joined_at=now,
        )
        forest = ForestCardInfo(
            run_id=42,
            started_at=now,
            ends_at=now + timedelta(minutes=30),
            status=ForestRunStatus.IN_PROGRESS,
        )
        card = PlayerCard(summary=summary, clan=clan, forest_active_run=forest)
        get_card = _stub_get_player_card(
            output=GetPlayerCardOutput(target_tg_id=100, card=card),
        )

        await handle_player(
            message=cast(Message, msg),
            command=_command_player("100"),
            tg_identity=_identity(),
            get_player_card=get_card,
            bundle=bundle,
            locale=_RU,
        )

        text = msg.answer.await_args.args[0]
        assert "admin-player-card-summary" in text
        assert "tg_id=100" in text
        assert "admin-player-card-clan" in text
        assert "title=The Pipiriks" in text
        assert "role=лидер" in text
        assert "admin-player-card-forest-active" in text
        assert "run_id=42" in text
        assert "admin-player-card-no-anticheat" in text


# ── /freeze ─────────────────────────────────────────────────────────────────


def _stub_freeze(*, output: FreezePlayerOutput | None = None) -> FreezePlayer:
    fake = MagicMock(spec=FreezePlayer)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(FreezePlayer, fake)


def _stub_unfreeze(*, output: UnfreezePlayerOutput | None = None) -> UnfreezePlayer:
    fake = MagicMock(spec=UnfreezePlayer)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(UnfreezePlayer, fake)


def _command_freeze(args: str | None) -> CommandObject:
    return CommandObject(prefix="/", command="freeze", mention=None, args=args)


def _command_unfreeze(args: str | None) -> CommandObject:
    return CommandObject(prefix="/", command="unfreeze", mention=None, args=args)


@pytest.mark.asyncio
class TestHandleFreeze:
    async def test_non_private_chat(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="group")
        uc = _stub_freeze()
        await handle_freeze(
            message=cast(Message, msg),
            command=_command_freeze("100"),
            tg_identity=_identity(chat_kind="group"),
            freeze_player=uc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_empty_args_replies_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_freeze()
        await handle_freeze(
            message=cast(Message, msg),
            command=_command_freeze(""),
            tg_identity=_identity(),
            freeze_player=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-freeze-usage" in text

    async def test_bad_id(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_freeze()
        await handle_freeze(
            message=cast(Message, msg),
            command=_command_freeze("not-an-int"),
            tg_identity=_identity(),
            freeze_player=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-freeze-bad-id" in text

    async def test_authorization_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_freeze()
        uc.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=AuthorizationError(requirement="x", detail="y"),
        )
        await handle_freeze(
            message=cast(Message, msg),
            command=_command_freeze("100"),
            tg_identity=_identity(),
            freeze_player=uc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-freeze-not-authorized" in msg.answer.await_args.args[0]

    async def test_player_not_found(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_freeze()
        uc.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=PlayerNotFoundError(tg_id=999),
        )
        await handle_freeze(
            message=cast(Message, msg),
            command=_command_freeze("999"),
            tg_identity=_identity(),
            freeze_player=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-freeze-not-found" in text
        assert "tg_id=999" in text

    async def test_already_frozen(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_freeze(
            output=FreezePlayerOutput(target_tg_id=100, was_already_frozen=True),
        )
        await handle_freeze(
            message=cast(Message, msg),
            command=_command_freeze("100"),
            tg_identity=_identity(),
            freeze_player=uc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-freeze-already" in msg.answer.await_args.args[0]

    async def test_ok_with_reason(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_freeze(
            output=FreezePlayerOutput(target_tg_id=100, was_already_frozen=False),
        )
        await handle_freeze(
            message=cast(Message, msg),
            command=_command_freeze("100 макрос пойман"),
            tg_identity=_identity(),
            freeze_player=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-freeze-ok" in text
        assert "tg_id=100" in text
        # use-case получил reason
        execute = cast(AsyncMock, uc.execute)
        await_args = execute.await_args
        assert await_args is not None
        inp = await_args.args[0]
        assert inp.target_tg_id == 100
        assert inp.reason == "макрос пойман"


@pytest.mark.asyncio
class TestHandleUnfreeze:
    async def test_empty_args_replies_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_unfreeze()
        await handle_unfreeze(
            message=cast(Message, msg),
            command=_command_unfreeze(""),
            tg_identity=_identity(),
            unfreeze_player=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-unfreeze-usage" in text

    async def test_already_active(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_unfreeze(
            output=UnfreezePlayerOutput(target_tg_id=100, was_already_active=True),
        )
        await handle_unfreeze(
            message=cast(Message, msg),
            command=_command_unfreeze("100"),
            tg_identity=_identity(),
            unfreeze_player=uc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-unfreeze-already" in msg.answer.await_args.args[0]

    async def test_ok(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_unfreeze(
            output=UnfreezePlayerOutput(target_tg_id=100, was_already_active=False),
        )
        await handle_unfreeze(
            message=cast(Message, msg),
            command=_command_unfreeze("100"),
            tg_identity=_identity(),
            unfreeze_player=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-unfreeze-ok" in text
        assert "tg_id=100" in text

    async def test_player_not_found(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_unfreeze()
        uc.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=PlayerNotFoundError(tg_id=999),
        )
        await handle_unfreeze(
            message=cast(Message, msg),
            command=_command_unfreeze("999"),
            tg_identity=_identity(),
            unfreeze_player=uc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-unfreeze-not-found" in msg.answer.await_args.args[0]
