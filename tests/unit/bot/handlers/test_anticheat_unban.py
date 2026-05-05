"""Юнит-тесты handler-а `/anticheat_unban` (Спринт 1.6.G).

Покрываем:

1. Не из ЛС → стандартный «только в ЛС»; use-case НЕ вызывается.
2. ЛС без аргументов → ключ `anticheat-unban-usage`.
3. ЛС с одним аргументом (без reason) → ключ `anticheat-unban-usage`.
4. ЛС с tg_id=0 → ключ `anticheat-unban-usage` (защита от опечатки).
5. ЛС с не-int tg_id → ключ `anticheat-unban-usage`.
6. Не super_admin (`AuthorizationError`) → ключ `anticheat-unban-not-authorized`.
7. Игрок не найден (`PlayerNotFoundError`) → ключ `anticheat-unban-player-not-found`
   с параметром `tg_id`.
8. Бан не активен → ключ `anticheat-unban-not-banned` с параметром `tg_id`.
9. Happy-path: бан снят → ключ `anticheat-unban-success` с параметрами
   `tg_id`, `banned-until-before`, `reason`.
10. Без локали в data — fallback на `DEFAULT_LOCALE` (en).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters.command import CommandObject
from aiogram.types import Chat

from pipirik_wars.application.anticheat import LiftAnticheatBan, LiftAnticheatBanResult
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import Locale
from pipirik_wars.bot.handlers.admin import handle_anticheat_unban
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.player import PlayerNotFoundError
from tests.fakes import FakeMessageBundle


def _msg(chat_type: str = "private") -> MagicMock:
    m = MagicMock()
    m.chat = Chat(id=42, type=chat_type)
    m.answer = AsyncMock()
    return m


def _identity(chat_kind: str = "private", tg_user_id: int = 555) -> TgIdentity:
    return TgIdentity(
        tg_user_id=tg_user_id,
        chat_id=42,
        chat_kind=chat_kind,
        language_code=None,
    )


def _cmd(args: str | None) -> CommandObject:
    return CommandObject(prefix="/", command="anticheat_unban", args=args)


def _stub_use_case(
    *,
    raises: Exception | None = None,
    result: LiftAnticheatBanResult | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=LiftAnticheatBan)
    if raises is not None:
        use_case.execute = AsyncMock(side_effect=raises)
    else:
        use_case.execute = AsyncMock(return_value=result)
    return use_case


@pytest.mark.asyncio
async def test_non_private_chat_replies_only_in_dm() -> None:
    msg = _msg(chat_type="group")
    use_case = _stub_use_case()

    await handle_anticheat_unban(
        message=msg,
        command=_cmd("100 reason"),
        tg_identity=_identity(chat_kind="group"),
        lift_anticheat_ban=use_case,
        bundle=FakeMessageBundle(),
        locale=Locale(code="ru"),
    )

    msg.answer.assert_awaited_once()
    answer_text = msg.answer.call_args.args[0]
    assert "Админ-команды доступны только в ЛС" in answer_text
    use_case.execute.assert_not_awaited()


@pytest.mark.parametrize(
    "args",
    [None, "", "  ", "100", "  100  ", "abc reason", "0 some reason"],
)
@pytest.mark.asyncio
async def test_invalid_args_renders_usage(args: str | None) -> None:
    msg = _msg()
    use_case = _stub_use_case()

    await handle_anticheat_unban(
        message=msg,
        command=_cmd(args),
        tg_identity=_identity(),
        lift_anticheat_ban=use_case,
        bundle=FakeMessageBundle(),
        locale=Locale(code="ru"),
    )

    msg.answer.assert_awaited_once()
    rendered = msg.answer.call_args.args[0]
    assert "anticheat-unban-usage" in rendered
    use_case.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_authorization_error_renders_not_authorized() -> None:
    msg = _msg()
    use_case = _stub_use_case(
        raises=AuthorizationError(requirement="x", detail="y"),
    )

    await handle_anticheat_unban(
        message=msg,
        command=_cmd("100 reason"),
        tg_identity=_identity(),
        lift_anticheat_ban=use_case,
        bundle=FakeMessageBundle(),
        locale=Locale(code="ru"),
    )

    msg.answer.assert_awaited_once()
    rendered = msg.answer.call_args.args[0]
    assert "anticheat-unban-not-authorized" in rendered


@pytest.mark.asyncio
async def test_player_not_found_renders_with_tg_id() -> None:
    msg = _msg()
    use_case = _stub_use_case(raises=PlayerNotFoundError(tg_id=100))

    await handle_anticheat_unban(
        message=msg,
        command=_cmd("100 reason"),
        tg_identity=_identity(),
        lift_anticheat_ban=use_case,
        bundle=FakeMessageBundle(),
        locale=Locale(code="ru"),
    )

    rendered = msg.answer.call_args.args[0]
    assert "anticheat-unban-player-not-found" in rendered
    assert "tg_id=100" in rendered


@pytest.mark.asyncio
async def test_idempotent_no_op_renders_not_banned() -> None:
    msg = _msg()
    use_case = _stub_use_case(
        result=LiftAnticheatBanResult(
            target_tg_id=100,
            was_banned=False,
            banned_until_before=None,
            reason="reason",
        ),
    )

    await handle_anticheat_unban(
        message=msg,
        command=_cmd("100 reason"),
        tg_identity=_identity(),
        lift_anticheat_ban=use_case,
        bundle=FakeMessageBundle(),
        locale=Locale(code="ru"),
    )

    rendered = msg.answer.call_args.args[0]
    assert "anticheat-unban-not-banned" in rendered
    assert "tg_id=100" in rendered


@pytest.mark.asyncio
async def test_success_renders_with_all_params() -> None:
    msg = _msg()
    banned_until = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)
    use_case = _stub_use_case(
        result=LiftAnticheatBanResult(
            target_tg_id=100,
            was_banned=True,
            banned_until_before=banned_until,
            reason="manual review",
        ),
    )

    await handle_anticheat_unban(
        message=msg,
        command=_cmd("100 manual review"),
        tg_identity=_identity(),
        lift_anticheat_ban=use_case,
        bundle=FakeMessageBundle(),
        locale=Locale(code="ru"),
    )

    rendered = msg.answer.call_args.args[0]
    assert "anticheat-unban-success" in rendered
    assert "tg_id=100" in rendered
    assert f"banned-until-before={banned_until.isoformat()}" in rendered
    assert "reason=manual review" in rendered


@pytest.mark.asyncio
async def test_locale_fallback_to_default_when_none() -> None:
    msg = _msg()
    use_case = _stub_use_case(
        result=LiftAnticheatBanResult(
            target_tg_id=100,
            was_banned=False,
            banned_until_before=None,
            reason="r",
        ),
    )

    await handle_anticheat_unban(
        message=msg,
        command=_cmd("100 reason"),
        tg_identity=_identity(),
        lift_anticheat_ban=use_case,
        bundle=FakeMessageBundle(),
        locale=None,
    )

    rendered = msg.answer.call_args.args[0]
    # FakeMessageBundle ставит "<locale>:..." в начале — DEFAULT_LOCALE = en.
    assert rendered.startswith("en:")
