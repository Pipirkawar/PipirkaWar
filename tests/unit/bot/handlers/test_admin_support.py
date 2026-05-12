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
    BanPlayer,
    BanPlayerOutput,
    ClanCardInfo,
    FindPlayers,
    FindPlayersOutput,
    ForestCardInfo,
    FreezePlayer,
    FreezePlayerOutput,
    GetPlayerCard,
    GetPlayerCardOutput,
    GrantLength,
    GrantThickness,
    IBroadcastTaskSpawner,
    PlayerCard,
    PlayerSummary,
    RequestAdminConfirm,
    RequestAdminConfirmOutput,
    RunBroadcastAnnouncement,
    SetBalanceValue,
    UnfreezePlayer,
    UnfreezePlayerOutput,
    VerifyAdminConfirm,
    VerifyAdminConfirmOutput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.application.monetization import RefundLot
from pipirik_wars.bot.handlers.admin_support import (
    REPLY_NON_PRIVATE_RU,
    handle_ban,
    handle_confirm,
    handle_find_player,
    handle_freeze,
    handle_player,
    handle_unfreeze,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.admin import (
    ConfirmAdminMismatchError,
    ConfirmCodeInvalidError,
    ConfirmTokenExpiredError,
    ConfirmTokenNotFoundError,
    TotpNotConfiguredError,
)
from pipirik_wars.domain.clan import ClanMemberRole, ClanStatus
from pipirik_wars.domain.forest import ForestRunStatus
from pipirik_wars.domain.player import PlayerStatus
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import IClock

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


# ── /ban (B.4) ──────────────────────────────────────────────────────────────


def _stub_request_confirm(
    *, output: RequestAdminConfirmOutput | None = None
) -> RequestAdminConfirm:
    fake = MagicMock(spec=RequestAdminConfirm)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(RequestAdminConfirm, fake)


def _stub_verify_confirm(*, output: VerifyAdminConfirmOutput | None = None) -> VerifyAdminConfirm:
    fake = MagicMock(spec=VerifyAdminConfirm)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(VerifyAdminConfirm, fake)


def _stub_ban(*, output: BanPlayerOutput | None = None) -> BanPlayer:
    fake = MagicMock(spec=BanPlayer)
    fake.execute = AsyncMock(return_value=output) if output is not None else AsyncMock()
    return cast(BanPlayer, fake)


def _stub_grant_length() -> GrantLength:
    fake = MagicMock(spec=GrantLength)
    fake.execute = AsyncMock()
    return cast(GrantLength, fake)


def _stub_grant_thickness() -> GrantThickness:
    fake = MagicMock(spec=GrantThickness)
    fake.execute = AsyncMock()
    return cast(GrantThickness, fake)


def _stub_set_balance_value() -> SetBalanceValue:
    fake = MagicMock(spec=SetBalanceValue)
    fake.execute = AsyncMock()
    return cast(SetBalanceValue, fake)


def _stub_clock() -> object:
    fake = MagicMock(spec=IClock)
    fake.now = MagicMock(return_value=datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    return fake


def _stub_run_broadcast_announcement() -> RunBroadcastAnnouncement:
    fake = MagicMock(spec=RunBroadcastAnnouncement)
    fake.execute = AsyncMock()
    return cast(RunBroadcastAnnouncement, fake)


def _stub_broadcast_task_spawner() -> IBroadcastTaskSpawner:
    fake = MagicMock(spec=IBroadcastTaskSpawner)
    return cast(IBroadcastTaskSpawner, fake)


def _stub_refund_lot() -> RefundLot:
    fake = MagicMock(spec=RefundLot)
    fake.execute = AsyncMock()
    return cast(RefundLot, fake)


def _confirm_extra_kwargs() -> dict[str, object]:
    """Дефолты новых параметров `handle_confirm` (Спринт 2.5-C/D.4 + 4.1-E.13)."""
    return {
        "grant_length": _stub_grant_length(),
        "grant_thickness": _stub_grant_thickness(),
        "set_balance_value": _stub_set_balance_value(),
        "run_broadcast_announcement": _stub_run_broadcast_announcement(),
        "broadcast_task_spawner": _stub_broadcast_task_spawner(),
        "clock": _stub_clock(),
        "refund_lot": _stub_refund_lot(),
    }


def _command_ban(args: str | None) -> CommandObject:
    return CommandObject(prefix="/", command="ban", mention=None, args=args)


def _command_confirm(args: str | None) -> CommandObject:
    return CommandObject(prefix="/", command="confirm", mention=None, args=args)


@pytest.mark.asyncio
class TestHandleBan:
    async def test_non_private_chat(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="group")
        uc = _stub_request_confirm()
        await handle_ban(
            message=cast(Message, msg),
            command=_command_ban("100 макрос"),
            tg_identity=_identity(chat_kind="group"),
            request_admin_confirm=uc,
            bundle=bundle,
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        uc.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_empty_args(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_request_confirm()
        await handle_ban(
            message=cast(Message, msg),
            command=_command_ban(""),
            tg_identity=_identity(),
            request_admin_confirm=uc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-ban-usage" in msg.answer.await_args.args[0]

    async def test_bad_id(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_request_confirm()
        await handle_ban(
            message=cast(Message, msg),
            command=_command_ban("not-int reason here"),
            tg_identity=_identity(),
            request_admin_confirm=uc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-ban-bad-id" in msg.answer.await_args.args[0]

    async def test_no_reason(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_request_confirm()
        await handle_ban(
            message=cast(Message, msg),
            command=_command_ban("100"),
            tg_identity=_identity(),
            request_admin_confirm=uc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-ban-no-reason" in msg.answer.await_args.args[0]

    async def test_authorization_error(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_request_confirm()
        uc.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=AuthorizationError(requirement="x", detail="y"),
        )
        await handle_ban(
            message=cast(Message, msg),
            command=_command_ban("100 макрос"),
            tg_identity=_identity(),
            request_admin_confirm=uc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-ban-not-authorized" in msg.answer.await_args.args[0]

    async def test_totp_not_configured(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_request_confirm()
        uc.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=TotpNotConfiguredError("no totp"),
        )
        await handle_ban(
            message=cast(Message, msg),
            command=_command_ban("100 макрос"),
            tg_identity=_identity(),
            request_admin_confirm=uc,
            bundle=bundle,
            locale=_RU,
        )
        assert "admin-ban-totp-not-configured" in msg.answer.await_args.args[0]

    async def test_confirm_issued(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        uc = _stub_request_confirm(
            output=RequestAdminConfirmOutput(token="TOKEN_X", ttl_seconds=60),
        )
        await handle_ban(
            message=cast(Message, msg),
            command=_command_ban("100 макрос-обнаружен"),
            tg_identity=_identity(),
            request_admin_confirm=uc,
            bundle=bundle,
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-ban-confirm-issued" in text
        assert "token=TOKEN_X" in text
        assert "ttl_seconds=60" in text

        execute = cast(AsyncMock, uc.execute)
        await_args = execute.await_args
        assert await_args is not None
        inp = await_args.args[0]
        assert inp.target_id == "100"
        assert inp.command_kind == "ban"
        assert inp.payload["target_tg_id"] == 100
        assert inp.payload["reason"] == "макрос-обнаружен"


# ── /confirm (B.5) ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestHandleConfirm:
    async def test_non_private_chat(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="group")
        await handle_confirm(
            message=cast(Message, msg),
            command=_command_confirm("TOK 123456"),
            tg_identity=_identity(chat_kind="group"),
            verify_admin_confirm=_stub_verify_confirm(),
            ban_player=_stub_ban(),
            bundle=bundle,
            **_confirm_extra_kwargs(),
            locale=_RU,
        )
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)

    async def test_empty_args(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_confirm(
            message=cast(Message, msg),
            command=_command_confirm(""),
            tg_identity=_identity(),
            verify_admin_confirm=_stub_verify_confirm(),
            ban_player=_stub_ban(),
            bundle=bundle,
            **_confirm_extra_kwargs(),
            locale=_RU,
        )
        assert "admin-confirm-usage" in msg.answer.await_args.args[0]

    async def test_one_arg_returns_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        await handle_confirm(
            message=cast(Message, msg),
            command=_command_confirm("TOK"),
            tg_identity=_identity(),
            verify_admin_confirm=_stub_verify_confirm(),
            ban_player=_stub_ban(),
            bundle=bundle,
            **_confirm_extra_kwargs(),
            locale=_RU,
        )
        assert "admin-confirm-usage" in msg.answer.await_args.args[0]

    async def test_token_not_found(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        verify = _stub_verify_confirm()
        verify.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=ConfirmTokenNotFoundError("nope"),
        )
        await handle_confirm(
            message=cast(Message, msg),
            command=_command_confirm("TOK 123456"),
            tg_identity=_identity(),
            verify_admin_confirm=verify,
            ban_player=_stub_ban(),
            bundle=bundle,
            **_confirm_extra_kwargs(),
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-confirm-token-not-found" in text
        assert "token=TOK" in text

    async def test_token_expired(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        verify = _stub_verify_confirm()
        verify.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=ConfirmTokenExpiredError("expired"),
        )
        await handle_confirm(
            message=cast(Message, msg),
            command=_command_confirm("TOK 123456"),
            tg_identity=_identity(),
            verify_admin_confirm=verify,
            ban_player=_stub_ban(),
            bundle=bundle,
            **_confirm_extra_kwargs(),
            locale=_RU,
        )
        assert "admin-confirm-token-expired" in msg.answer.await_args.args[0]

    async def test_admin_mismatch(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        verify = _stub_verify_confirm()
        verify.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=ConfirmAdminMismatchError("other admin"),
        )
        await handle_confirm(
            message=cast(Message, msg),
            command=_command_confirm("TOK 123456"),
            tg_identity=_identity(),
            verify_admin_confirm=verify,
            ban_player=_stub_ban(),
            bundle=bundle,
            **_confirm_extra_kwargs(),
            locale=_RU,
        )
        assert "admin-confirm-admin-mismatch" in msg.answer.await_args.args[0]

    async def test_code_invalid(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        verify = _stub_verify_confirm()
        verify.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=ConfirmCodeInvalidError("bad code"),
        )
        await handle_confirm(
            message=cast(Message, msg),
            command=_command_confirm("TOK 000000"),
            tg_identity=_identity(),
            verify_admin_confirm=verify,
            ban_player=_stub_ban(),
            bundle=bundle,
            **_confirm_extra_kwargs(),
            locale=_RU,
        )
        assert "admin-confirm-code-invalid" in msg.answer.await_args.args[0]

    async def test_totp_not_configured(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        verify = _stub_verify_confirm()
        verify.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=TotpNotConfiguredError("no"),
        )
        await handle_confirm(
            message=cast(Message, msg),
            command=_command_confirm("TOK 123456"),
            tg_identity=_identity(),
            verify_admin_confirm=verify,
            ban_player=_stub_ban(),
            bundle=bundle,
            **_confirm_extra_kwargs(),
            locale=_RU,
        )
        assert "admin-confirm-totp-not-configured" in msg.answer.await_args.args[0]

    async def test_confirm_dispatches_ban_success(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        verify = _stub_verify_confirm(
            output=VerifyAdminConfirmOutput(
                command_kind="ban",
                target_kind="player",
                target_id="100",
                payload={"target_tg_id": 100, "reason": "макрос"},
            ),
        )
        ban = _stub_ban(
            output=BanPlayerOutput(target_tg_id=100, was_already_banned=False),
        )
        await handle_confirm(
            message=cast(Message, msg),
            command=_command_confirm("TOK 123456"),
            tg_identity=_identity(),
            verify_admin_confirm=verify,
            ban_player=ban,
            bundle=bundle,
            **_confirm_extra_kwargs(),
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-confirm-success-ban" in text
        assert "tg_id=100" in text
        # use-case вызвался с правильными данными
        execute = cast(AsyncMock, ban.execute)
        await_args = execute.await_args
        assert await_args is not None
        inp = await_args.args[0]
        assert inp.target_tg_id == 100
        assert inp.reason == "макрос"

    async def test_confirm_dispatches_ban_already_banned(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        verify = _stub_verify_confirm(
            output=VerifyAdminConfirmOutput(
                command_kind="ban",
                target_kind="player",
                target_id="100",
                payload={"target_tg_id": 100, "reason": "макрос"},
            ),
        )
        ban = _stub_ban(
            output=BanPlayerOutput(target_tg_id=100, was_already_banned=True),
        )
        await handle_confirm(
            message=cast(Message, msg),
            command=_command_confirm("TOK 123456"),
            tg_identity=_identity(),
            verify_admin_confirm=verify,
            ban_player=ban,
            bundle=bundle,
            **_confirm_extra_kwargs(),
            locale=_RU,
        )
        assert "admin-confirm-success-ban-already" in msg.answer.await_args.args[0]

    async def test_confirm_unknown_command_kind(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        verify = _stub_verify_confirm(
            output=VerifyAdminConfirmOutput(
                command_kind="something-new",
                target_kind="player",
                target_id="100",
                payload={},
            ),
        )
        ban = _stub_ban()
        await handle_confirm(
            message=cast(Message, msg),
            command=_command_confirm("TOK 123456"),
            tg_identity=_identity(),
            verify_admin_confirm=verify,
            ban_player=ban,
            bundle=bundle,
            **_confirm_extra_kwargs(),
            locale=_RU,
        )
        text = msg.answer.await_args.args[0]
        assert "admin-confirm-unknown-command-kind" in text
        assert "command_kind=something-new" in text
        ban.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_confirm_ban_payload_typo_falls_to_unknown(self, bundle: IMessageBundle) -> None:
        """payload не содержит ожидаемых ключей — `unknown_command_kind`."""
        msg = _msg_mock()
        verify = _stub_verify_confirm(
            output=VerifyAdminConfirmOutput(
                command_kind="ban",
                target_kind="player",
                target_id="100",
                payload={"wrong_key": "x"},
            ),
        )
        ban = _stub_ban()
        await handle_confirm(
            message=cast(Message, msg),
            command=_command_confirm("TOK 123456"),
            tg_identity=_identity(),
            verify_admin_confirm=verify,
            ban_player=ban,
            bundle=bundle,
            **_confirm_extra_kwargs(),
            locale=_RU,
        )
        assert "admin-confirm-unknown-command-kind" in msg.answer.await_args.args[0]
        ban.execute.assert_not_awaited()  # type: ignore[attr-defined]

    async def test_confirm_ban_player_disappeared(self, bundle: IMessageBundle) -> None:
        """После успешного TOTP игрока всё-таки нет (удалили): show ban-not-found."""
        msg = _msg_mock()
        verify = _stub_verify_confirm(
            output=VerifyAdminConfirmOutput(
                command_kind="ban",
                target_kind="player",
                target_id="100",
                payload={"target_tg_id": 100, "reason": "макрос"},
            ),
        )
        ban = _stub_ban()
        ban.execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=PlayerNotFoundError(tg_id=100),
        )
        await handle_confirm(
            message=cast(Message, msg),
            command=_command_confirm("TOK 123456"),
            tg_identity=_identity(),
            verify_admin_confirm=verify,
            ban_player=ban,
            bundle=bundle,
            **_confirm_extra_kwargs(),
            locale=_RU,
        )
        assert "admin-ban-not-found" in msg.answer.await_args.args[0]
