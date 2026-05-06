"""Юнит-тесты `/start` handler-а.

Acceptance:
- 1.1.1 — отвечает в ЛС, в группе и в супергруппе.
- 1.1.3 — регистрация игрока **только через ЛС**.
- 1.2.4 — при `DAU >= MAX_DAU` показываем «серверы переполнены, позиция #N».
- 1.5.B — все ответы через `StartPresenter`/`IMessageBundle`.
- 2.4.D — парсинг `start=ref_<id>` payload-а в ЛС, привязка реферальной
  связи и начисление signup-бонуса; в группе/супергруппе payload игнорируется.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters import CommandObject
from aiogram.types import Chat, Message

from pipirik_wars.application.dto.inputs import RegisterPlayerInput
from pipirik_wars.application.i18n import IMessageBundle, Locale
from pipirik_wars.application.player import (
    PlayerQueued,
    PlayerRegistered,
    RegisterPlayer,
)
from pipirik_wars.application.referral import (
    GrantReferralSignupBonus,
    ReferralSignupBonusGranted,
    RegisterReferral,
)
from pipirik_wars.bot.handlers.start import handle_start
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.player import (
    Player,
    PlayerAlreadyRegisteredError,
    PlayerStatus,
)
from pipirik_wars.domain.player.value_objects import Length, Thickness
from pipirik_wars.domain.referral import (
    Referral,
    ReferrerNotRegisteredError,
    SignupBonusAlreadyGrantedError,
)
from pipirik_wars.domain.signup_queue import (
    AlreadyQueuedError,
    ISignupQueueRepository,
    SignupQueueEntry,
)
from tests.fakes import FakeMessageBundle, FakeSignupQueueRepository


def _bundle() -> IMessageBundle:
    return cast(IMessageBundle, FakeMessageBundle())


def _build_message_mock(
    chat_type: str = "private",
    *,
    username: str | None = None,
) -> MagicMock:
    msg = MagicMock()
    msg.chat = Chat(id=42, type=chat_type)
    msg.answer = AsyncMock()
    if username is None:
        msg.from_user = None
    else:
        msg.from_user = MagicMock()
        msg.from_user.username = username
    return msg


def _identity(
    chat_kind: str = "private",
    tg_user_id: int = 100,
    *,
    language_code: str | None = None,
) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=42,
        chat_kind=chat_kind,
        language_code=language_code,
    )


def _player(tg_id: int = 100) -> Player:
    return Player(
        id=1,
        tg_id=tg_id,
        username=None,
        length=Length(cm=2),
        thickness=Thickness(level=1),
        title=None,
        name=None,
        status=PlayerStatus.ACTIVE,
        created_at=datetime(2026, 5, 4, tzinfo=UTC),
        updated_at=datetime(2026, 5, 4, tzinfo=UTC),
    )


def _stub_register_player(
    *,
    return_value: PlayerRegistered | PlayerQueued | None = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=RegisterPlayer)
    if side_effect is not None:
        use_case.execute = AsyncMock(side_effect=side_effect)
    else:
        use_case.execute = AsyncMock(
            return_value=return_value or PlayerRegistered(player=_player()),
        )
    return use_case


def _stub_register_referral(
    *,
    side_effect: Exception | None = None,
) -> MagicMock:
    """Stub `RegisterReferral`. По умолчанию — успешная привязка
    (возвращает `Referral` placeholder). Не используется тестами,
    которые не проверяют реферальный путь."""
    use_case = MagicMock(spec=RegisterReferral)
    if side_effect is not None:
        use_case.execute = AsyncMock(side_effect=side_effect)
    else:
        referral = Referral(
            id=1,
            referrer_id=1,
            referred_id=2,
            created_at=datetime(2026, 5, 4, tzinfo=UTC),
        )
        use_case.execute = AsyncMock(return_value=referral)
    return use_case


def _stub_grant_signup_bonus(
    *,
    newbie_bonus_cm: int = 5,
    side_effect: Exception | None = None,
) -> MagicMock:
    """Stub `GrantReferralSignupBonus`. По умолчанию — успешное
    начисление с дефолтным бонусом 5 см новичку (балансовый дефолт)."""
    use_case = MagicMock(spec=GrantReferralSignupBonus)
    if side_effect is not None:
        use_case.execute = AsyncMock(side_effect=side_effect)
    else:
        referral = Referral(
            id=1,
            referrer_id=1,
            referred_id=2,
            created_at=datetime(2026, 5, 4, tzinfo=UTC),
            signup_granted_at=datetime(2026, 5, 4, tzinfo=UTC),
        )
        use_case.execute = AsyncMock(
            return_value=ReferralSignupBonusGranted(
                referral=referral,
                newbie_bonus_cm=newbie_bonus_cm,
                referrer_bonus_cm=1,
            )
        )
    return use_case


def _queue() -> FakeSignupQueueRepository:
    return FakeSignupQueueRepository()


_DEFAULT_LOCALE_RU = Locale("ru")


def _kwargs(
    *,
    register_player: MagicMock,
    register_referral: MagicMock | None = None,
    grant_referral_signup_bonus: MagicMock | None = None,
    queue: ISignupQueueRepository | None = None,
    locale: Locale | None = _DEFAULT_LOCALE_RU,
    command: CommandObject | None = None,
) -> dict[str, object]:
    """Собрать kwargs для `handle_start(...)` — устойчиво к будущим
    добавлениям параметров (порядок positional уже не важен)."""
    return {
        "register_player": cast(RegisterPlayer, register_player),
        "register_referral": cast(
            RegisterReferral,
            register_referral if register_referral is not None else _stub_register_referral(),
        ),
        "grant_referral_signup_bonus": cast(
            GrantReferralSignupBonus,
            grant_referral_signup_bonus
            if grant_referral_signup_bonus is not None
            else _stub_grant_signup_bonus(),
        ),
        "signup_queue": queue if queue is not None else _queue(),
        "bundle": _bundle(),
        "command": command,
        "locale": locale,
    }


@pytest.mark.asyncio
class TestHandleStart:
    async def test_private_calls_register_player_and_replies_success(self) -> None:
        msg = _build_message_mock("private", username="alice")
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            _identity("private", tg_user_id=100),
            **_kwargs(register_player=register_player),
        )

        register_player.execute.assert_awaited_once()
        actual_input = register_player.execute.await_args.args[0]
        assert isinstance(actual_input, RegisterPlayerInput)
        assert actual_input.tg_id == 100
        assert actual_input.username == "alice"
        assert actual_input.locale == "ru"
        assert actual_input.referrer_tg_id is None
        msg.answer.assert_awaited_once_with("ru:start-registered")

    async def test_private_calls_register_player_with_resolved_locale_en(self) -> None:
        msg = _build_message_mock("private", username="bob")
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            _identity("private"),
            **_kwargs(register_player=register_player, locale=Locale("en")),
        )

        actual_input = register_player.execute.await_args.args[0]
        assert actual_input.locale == "en"
        msg.answer.assert_awaited_once_with("en:start-registered")

    async def test_private_already_registered_replies_already(self) -> None:
        msg = _build_message_mock("private")
        register_player = _stub_register_player(
            side_effect=PlayerAlreadyRegisteredError(tg_id=100),
        )

        await handle_start(
            cast(Message, msg),
            _identity("private"),
            **_kwargs(register_player=register_player),
        )

        msg.answer.assert_awaited_once_with("ru:start-already")

    async def test_private_queued_replies_with_position(self) -> None:
        msg = _build_message_mock("private", username="bob")
        entry = SignupQueueEntry(
            id=7,
            tg_id=100,
            username="bob",
            locale="ru",
            position=42,
            enqueued_at=datetime(2026, 5, 4, tzinfo=UTC),
        )
        register_player = _stub_register_player(return_value=PlayerQueued(entry=entry))

        await handle_start(
            cast(Message, msg),
            _identity("private"),
            **_kwargs(register_player=register_player),
        )

        msg.answer.assert_awaited_once_with("ru:start-queued[position=42]")

    async def test_private_already_queued_reads_current_position_and_replies(
        self,
    ) -> None:
        msg = _build_message_mock("private")
        register_player = _stub_register_player(
            side_effect=AlreadyQueuedError(tg_id=100),
        )
        queue = _queue()
        await queue.enqueue(
            entry=SignupQueueEntry(
                id=None,
                tg_id=100,
                username=None,
                locale=None,
                position=0,
                enqueued_at=datetime(2026, 5, 4, tzinfo=UTC),
            )
        )

        await handle_start(
            cast(Message, msg),
            _identity("private"),
            **_kwargs(register_player=register_player, queue=queue),
        )

        msg.answer.assert_awaited_once_with("ru:start-queued[position=1]")

    async def test_group_skips_registration_and_replies_instructions(self) -> None:
        msg = _build_message_mock("group")
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            _identity("group"),
            **_kwargs(register_player=register_player),
        )

        register_player.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:start-group")

    async def test_supergroup_skips_registration(self) -> None:
        msg = _build_message_mock("supergroup")
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            _identity("supergroup"),
            **_kwargs(register_player=register_player, locale=Locale("en")),
        )

        register_player.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("en:start-group")

    async def test_channel_replies_other(self) -> None:
        msg = _build_message_mock("channel")
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            _identity("channel"),
            **_kwargs(register_player=register_player),
        )

        register_player.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:start-other")

    async def test_private_without_identity_replies_other(self) -> None:
        msg = _build_message_mock("private")
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            None,
            **_kwargs(register_player=register_player),
        )

        register_player.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:start-other")

    async def test_no_identity_falls_back_to_message_chat_type(self) -> None:
        msg = _build_message_mock("group")
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            None,
            **_kwargs(register_player=register_player),
        )

        msg.answer.assert_awaited_once_with("ru:start-group")

    async def test_username_none_when_no_from_user(self) -> None:
        msg = _build_message_mock("private", username=None)
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            _identity("private"),
            **_kwargs(register_player=register_player),
        )

        actual_input = register_player.execute.await_args.args[0]
        assert actual_input.username is None

    async def test_locale_none_falls_back_to_default_en(self) -> None:
        """Если middleware не сработал, handler берёт `DEFAULT_LOCALE = en`."""
        msg = _build_message_mock("private", username="dave")
        register_player = _stub_register_player()

        await handle_start(
            cast(Message, msg),
            _identity("private"),
            **_kwargs(register_player=register_player, locale=None),
        )

        actual_input = register_player.execute.await_args.args[0]
        assert actual_input.locale == "en"


@pytest.mark.asyncio
class TestHandleStartReferral:
    """Спринт 2.4.D — реферальный flow на `/start ref_<id>`."""

    async def test_private_with_valid_ref_passes_referrer_and_replies_with_bonus(
        self,
    ) -> None:
        msg = _build_message_mock("private", username="newbie")
        register_player = _stub_register_player()
        register_referral = _stub_register_referral()
        grant_signup = _stub_grant_signup_bonus(newbie_bonus_cm=5)

        await handle_start(
            cast(Message, msg),
            _identity("private", tg_user_id=100),
            **_kwargs(
                register_player=register_player,
                register_referral=register_referral,
                grant_referral_signup_bonus=grant_signup,
                command=CommandObject(prefix="/", command="start", args="ref_42"),
            ),
        )

        # Реферер прокинулся в RegisterPlayer.
        actual_input = register_player.execute.await_args.args[0]
        assert actual_input.referrer_tg_id == 42
        # Use-case-ы рефки вызваны последовательно.
        register_referral.execute.assert_awaited_once()
        grant_signup.execute.assert_awaited_once()
        # Ответ содержит specifically реферальный ключ + bonus_cm.
        msg.answer.assert_awaited_once()
        sent_text = msg.answer.await_args.args[0]
        assert sent_text.startswith("ru:start-registered-with-referral[")
        assert "bonus_cm=5" in sent_text

    async def test_private_without_ref_payload_replies_plain_registered(self) -> None:
        msg = _build_message_mock("private", username="alice")
        register_player = _stub_register_player()
        register_referral = _stub_register_referral()
        grant_signup = _stub_grant_signup_bonus()

        await handle_start(
            cast(Message, msg),
            _identity("private", tg_user_id=100),
            **_kwargs(
                register_player=register_player,
                register_referral=register_referral,
                grant_referral_signup_bonus=grant_signup,
                command=CommandObject(prefix="/", command="start", args=None),
            ),
        )

        actual_input = register_player.execute.await_args.args[0]
        assert actual_input.referrer_tg_id is None
        register_referral.execute.assert_not_awaited()
        grant_signup.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:start-registered")

    async def test_private_with_self_referral_ignored(self) -> None:
        msg = _build_message_mock("private", username="alice")
        register_player = _stub_register_player()
        register_referral = _stub_register_referral()
        grant_signup = _stub_grant_signup_bonus()

        await handle_start(
            cast(Message, msg),
            _identity("private", tg_user_id=100),
            **_kwargs(
                register_player=register_player,
                register_referral=register_referral,
                grant_referral_signup_bonus=grant_signup,
                command=CommandObject(prefix="/", command="start", args="ref_100"),
            ),
        )

        actual_input = register_player.execute.await_args.args[0]
        assert actual_input.referrer_tg_id is None
        register_referral.execute.assert_not_awaited()
        grant_signup.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:start-registered")

    async def test_private_with_invalid_ref_payload_ignored(self) -> None:
        msg = _build_message_mock("private", username="alice")
        register_player = _stub_register_player()

        for invalid_payload in ("ref_abc", "ref_-1", "ref_0", "ref_", "garbage"):
            register_player.reset_mock()
            await handle_start(
                cast(Message, msg),
                _identity("private", tg_user_id=100),
                **_kwargs(
                    register_player=register_player,
                    command=CommandObject(prefix="/", command="start", args=invalid_payload),
                ),
            )
            actual_input = register_player.execute.await_args.args[0]
            assert actual_input.referrer_tg_id is None, (
                f"payload={invalid_payload!r} should be ignored"
            )

    async def test_private_with_ref_but_referrer_not_registered_silent(self) -> None:
        """ReferrerNotRegisteredError swallow-ится: игрок видит обычное
        приветствие без +5 см."""
        msg = _build_message_mock("private", username="newbie")
        register_player = _stub_register_player()
        register_referral = _stub_register_referral(
            side_effect=ReferrerNotRegisteredError(referrer_tg_id=42),
        )
        grant_signup = _stub_grant_signup_bonus()

        await handle_start(
            cast(Message, msg),
            _identity("private", tg_user_id=100),
            **_kwargs(
                register_player=register_player,
                register_referral=register_referral,
                grant_referral_signup_bonus=grant_signup,
                command=CommandObject(prefix="/", command="start", args="ref_42"),
            ),
        )

        register_referral.execute.assert_awaited_once()
        grant_signup.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:start-registered")

    async def test_private_with_ref_but_signup_bonus_already_granted_silent(
        self,
    ) -> None:
        """SignupBonusAlreadyGrantedError swallow-ится (re-delivery)."""
        msg = _build_message_mock("private", username="newbie")
        register_player = _stub_register_player()
        register_referral = _stub_register_referral()
        grant_signup = _stub_grant_signup_bonus(
            side_effect=SignupBonusAlreadyGrantedError(referred_id=2),
        )

        await handle_start(
            cast(Message, msg),
            _identity("private", tg_user_id=100),
            **_kwargs(
                register_player=register_player,
                register_referral=register_referral,
                grant_referral_signup_bonus=grant_signup,
                command=CommandObject(prefix="/", command="start", args="ref_42"),
            ),
        )

        register_referral.execute.assert_awaited_once()
        grant_signup.execute.assert_awaited_once()
        msg.answer.assert_awaited_once_with("ru:start-registered")

    async def test_group_with_ref_payload_ignored(self) -> None:
        """В группе/супергруппе payload `ref_<id>` игнорируется (acceptance 2.4.D)."""
        msg = _build_message_mock("group")
        register_player = _stub_register_player()
        register_referral = _stub_register_referral()
        grant_signup = _stub_grant_signup_bonus()

        await handle_start(
            cast(Message, msg),
            _identity("group", tg_user_id=100),
            **_kwargs(
                register_player=register_player,
                register_referral=register_referral,
                grant_referral_signup_bonus=grant_signup,
                command=CommandObject(prefix="/", command="start", args="ref_42"),
            ),
        )

        register_player.execute.assert_not_awaited()
        register_referral.execute.assert_not_awaited()
        grant_signup.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with("ru:start-group")
