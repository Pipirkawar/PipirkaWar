"""Юнит-тесты `/balance_reload` handler-а (Спринт 1.1.E, ГДД §18.6.5).

Покрываем:

1. Активный admin в ЛС → handler зовёт `ReloadBalance.execute(...)`
   и шлёт текст «✅ перечитан».
2. Тот же handler корректно обрабатывает кейс «версия не изменилась»:
   текст содержит явный маркер «не изменилась».
3. Не-админ → use-case кидает `AuthorizationError`, handler ловит
   и шлёт friendly-сообщение `REPLY_FORBIDDEN_RU`.
4. Невалидный YAML → use-case кидает `ConfigError`, handler ловит
   и шлёт `REPLY_INVALID_CONFIG_RU`.
5. Не-private chat → handler не зовёт use-case и шлёт
   `REPLY_NON_PRIVATE_RU`.
6. Без `tg_identity` (теоретически невозможно из-за middleware,
   но handler defensive) → тот же `REPLY_NON_PRIVATE_RU`.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.balance import ReloadBalance, ReloadBalanceResult
from pipirik_wars.bot.handlers.admin import (
    REPLY_FORBIDDEN_RU,
    REPLY_INVALID_CONFIG_RU,
    REPLY_NON_PRIVATE_RU,
    handle_balance_reload,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.shared.errors import ConfigError


def _build_message_mock(chat_type: str = "private") -> MagicMock:
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


def _stub(*, return_value: ReloadBalanceResult | None = None) -> MagicMock:
    use_case = MagicMock(spec=ReloadBalance)
    if return_value is not None:
        use_case.execute = AsyncMock(return_value=return_value)
    else:
        use_case.execute = AsyncMock()
    return use_case


@pytest.mark.asyncio
class TestHandleBalanceReload:
    async def test_admin_success_replies_with_versions(self) -> None:
        msg = _build_message_mock("private")
        reload_balance = _stub(
            return_value=ReloadBalanceResult(version_before=1, version_after=2),
        )

        await handle_balance_reload(
            cast(Message, msg),
            _identity("private", tg_user_id=42),
            cast(ReloadBalance, reload_balance),
        )

        reload_balance.execute.assert_awaited_once_with(actor_tg_id=42)
        sent = msg.answer.await_args.args[0]
        assert "✅" in sent
        assert "v1" in sent
        assert "v2" in sent

    async def test_admin_no_change_replies_with_same_version(self) -> None:
        msg = _build_message_mock("private")
        reload_balance = _stub(
            return_value=ReloadBalanceResult(version_before=3, version_after=3),
        )

        await handle_balance_reload(
            cast(Message, msg),
            _identity("private"),
            cast(ReloadBalance, reload_balance),
        )

        sent = msg.answer.await_args.args[0]
        assert "✅" in sent
        assert "v3" in sent
        assert "не изменилась" in sent

    async def test_non_admin_caught_authorization_error(self) -> None:
        msg = _build_message_mock("private")
        reload_balance = _stub()
        reload_balance.execute = AsyncMock(
            side_effect=AuthorizationError(
                requirement="admin_balance_write",
                detail="actor tg_id=42 cannot reload balance",
            ),
        )

        await handle_balance_reload(
            cast(Message, msg),
            _identity("private"),
            cast(ReloadBalance, reload_balance),
        )

        msg.answer.assert_awaited_once_with(REPLY_FORBIDDEN_RU)

    async def test_invalid_yaml_caught_config_error(self) -> None:
        msg = _build_message_mock("private")
        reload_balance = _stub()
        reload_balance.execute = AsyncMock(
            side_effect=ConfigError("yaml broken"),
        )

        await handle_balance_reload(
            cast(Message, msg),
            _identity("private"),
            cast(ReloadBalance, reload_balance),
        )

        msg.answer.assert_awaited_once_with(REPLY_INVALID_CONFIG_RU)

    async def test_group_chat_skips_use_case(self) -> None:
        msg = _build_message_mock("group")
        reload_balance = _stub()

        await handle_balance_reload(
            cast(Message, msg),
            _identity("group"),
            cast(ReloadBalance, reload_balance),
        )

        reload_balance.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)

    async def test_no_identity_skips_use_case(self) -> None:
        msg = _build_message_mock("private")
        reload_balance = _stub()

        await handle_balance_reload(
            cast(Message, msg),
            None,
            cast(ReloadBalance, reload_balance),
        )

        reload_balance.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
