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

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.balance import ReloadBalance, ReloadBalanceResult
from pipirik_wars.application.dau import (
    DauStats,
    GetDauStats,
    SetMaxDau,
    SetMaxDauResult,
)
from pipirik_wars.application.signup_queue import (
    PromoteFromQueue,
    PromoteFromQueueResult,
)
from pipirik_wars.bot.handlers.admin import (
    REPLY_DAU_FORBIDDEN_RU,
    REPLY_FORBIDDEN_RU,
    REPLY_INVALID_CONFIG_RU,
    REPLY_NON_PRIVATE_RU,
    REPLY_SET_MAX_DAU_USAGE_RU,
    handle_admin_stats,
    handle_balance_reload,
    handle_set_max_dau,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.player import Player
from pipirik_wars.domain.signup_queue import ISignupQueueRepository, SignupQueueEntry
from pipirik_wars.shared.errors import ConfigError
from tests.fakes import FakeSignupQueueRepository


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


def _stats_stub(*, current: int, max_dau: int) -> MagicMock:
    use_case = MagicMock(spec=GetDauStats)
    use_case.execute = AsyncMock(
        return_value=DauStats(current=current, max_dau=max_dau),
    )
    return use_case


def _set_max_stub(
    *,
    return_value: SetMaxDauResult | None = None,
    side_effect: BaseException | None = None,
) -> MagicMock:
    use_case = MagicMock(spec=SetMaxDau)
    if side_effect is not None:
        use_case.execute = AsyncMock(side_effect=side_effect)
    else:
        use_case.execute = AsyncMock(return_value=return_value)
    return use_case


def _make_promoted(count: int) -> tuple[Player, ...]:
    now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    return tuple(Player.new(tg_id=1000 + i, username=None, now=now) for i in range(count))


def _promote_stub(*, promoted_count: int = 0) -> MagicMock:
    use_case = MagicMock(spec=PromoteFromQueue)
    use_case.execute = AsyncMock(
        return_value=PromoteFromQueueResult(
            promoted=_make_promoted(promoted_count),
            skipped_already_registered=(),
            available_slots=promoted_count,
        ),
    )
    return use_case


@pytest.mark.asyncio
class TestHandleAdminStats:
    async def test_replies_with_current_and_max(self) -> None:
        msg = _build_message_mock("private")
        get_stats = _stats_stub(current=42, max_dau=200)
        queue = FakeSignupQueueRepository()

        await handle_admin_stats(
            cast(Message, msg),
            _identity("private"),
            cast(GetDauStats, get_stats),
            cast(ISignupQueueRepository, queue),
        )

        get_stats.execute.assert_awaited_once_with()
        sent = msg.answer.await_args.args[0]
        assert "42" in sent
        assert "200" in sent
        assert "21%" in sent
        assert "Очередь регистраций: 0" in sent

    async def test_at_capacity_renders_100_percent(self) -> None:
        msg = _build_message_mock("private")
        get_stats = _stats_stub(current=200, max_dau=200)
        queue = FakeSignupQueueRepository()

        await handle_admin_stats(
            cast(Message, msg),
            _identity("private"),
            cast(GetDauStats, get_stats),
            cast(ISignupQueueRepository, queue),
        )

        sent = msg.answer.await_args.args[0]
        assert "100%" in sent

    async def test_zero_dau_renders_0_percent(self) -> None:
        msg = _build_message_mock("private")
        get_stats = _stats_stub(current=0, max_dau=200)
        queue = FakeSignupQueueRepository()

        await handle_admin_stats(
            cast(Message, msg),
            _identity("private"),
            cast(GetDauStats, get_stats),
            cast(ISignupQueueRepository, queue),
        )

        sent = msg.answer.await_args.args[0]
        assert "0%" in sent

    async def test_renders_actual_queue_size(self) -> None:
        msg = _build_message_mock("private")
        get_stats = _stats_stub(current=200, max_dau=200)
        queue = FakeSignupQueueRepository()

        for tg_id in (101, 102, 103):
            await queue.enqueue(
                entry=SignupQueueEntry(
                    id=None,
                    tg_id=tg_id,
                    username=None,
                    locale=None,
                    position=0,
                    enqueued_at=datetime(2026, 5, 4, 12, tg_id % 60, tzinfo=UTC),
                ),
            )

        await handle_admin_stats(
            cast(Message, msg),
            _identity("private"),
            cast(GetDauStats, get_stats),
            cast(ISignupQueueRepository, queue),
        )

        sent = msg.answer.await_args.args[0]
        assert "Очередь регистраций: 3" in sent

    async def test_group_chat_skips_use_case(self) -> None:
        msg = _build_message_mock("group")
        get_stats = _stats_stub(current=10, max_dau=200)
        queue = FakeSignupQueueRepository()

        await handle_admin_stats(
            cast(Message, msg),
            _identity("group"),
            cast(GetDauStats, get_stats),
            cast(ISignupQueueRepository, queue),
        )

        get_stats.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)

    async def test_no_identity_skips_use_case(self) -> None:
        msg = _build_message_mock("private")
        get_stats = _stats_stub(current=10, max_dau=200)
        queue = FakeSignupQueueRepository()

        await handle_admin_stats(
            cast(Message, msg),
            None,
            cast(GetDauStats, get_stats),
            cast(ISignupQueueRepository, queue),
        )

        get_stats.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)


@pytest.mark.asyncio
class TestHandleSetMaxDau:
    async def test_admin_changes_max_dau(self) -> None:
        msg = _build_message_mock("private")
        msg.text = "/set_max_dau 1000"
        set_max = _set_max_stub(
            return_value=SetMaxDauResult(previous_max_dau=200, new_max_dau=1000),
        )
        promote = _promote_stub(promoted_count=0)

        await handle_set_max_dau(
            cast(Message, msg),
            _identity("private", tg_user_id=42),
            cast(SetMaxDau, set_max),
            cast(PromoteFromQueue, promote),
        )

        set_max.execute.assert_awaited_once_with(actor_tg_id=42, new_max_dau=1000)
        promote.execute.assert_awaited_once_with()
        sent = msg.answer.await_args.args[0]
        assert "✅" in sent
        assert "200" in sent
        assert "1000" in sent
        # Очередь была пуста — добавочной строки «↑ Из очереди поднято: ...» нет.
        assert "поднято" not in sent

    async def test_increase_promotes_from_queue_and_appends_count(self) -> None:
        msg = _build_message_mock("private")
        msg.text = "/set_max_dau 1000"
        set_max = _set_max_stub(
            return_value=SetMaxDauResult(previous_max_dau=200, new_max_dau=1000),
        )
        promote = _promote_stub(promoted_count=3)

        await handle_set_max_dau(
            cast(Message, msg),
            _identity("private", tg_user_id=42),
            cast(SetMaxDau, set_max),
            cast(PromoteFromQueue, promote),
        )

        promote.execute.assert_awaited_once_with()
        sent = msg.answer.await_args.args[0]
        assert "поднято" in sent
        assert "3" in sent

    async def test_decrease_does_not_call_promote(self) -> None:
        msg = _build_message_mock("private")
        msg.text = "/set_max_dau 100"
        set_max = _set_max_stub(
            return_value=SetMaxDauResult(previous_max_dau=200, new_max_dau=100),
        )
        promote = _promote_stub()

        await handle_set_max_dau(
            cast(Message, msg),
            _identity("private"),
            cast(SetMaxDau, set_max),
            cast(PromoteFromQueue, promote),
        )

        promote.execute.assert_not_awaited()
        sent = msg.answer.await_args.args[0]
        assert "✅" in sent
        assert "поднято" not in sent

    async def test_no_change_replies_with_unchanged_marker(self) -> None:
        msg = _build_message_mock("private")
        msg.text = "/set_max_dau 200"
        set_max = _set_max_stub(
            return_value=SetMaxDauResult(previous_max_dau=200, new_max_dau=200),
        )
        promote = _promote_stub()

        await handle_set_max_dau(
            cast(Message, msg),
            _identity("private"),
            cast(SetMaxDau, set_max),
            cast(PromoteFromQueue, promote),
        )

        promote.execute.assert_not_awaited()
        sent = msg.answer.await_args.args[0]
        assert "200" in sent
        assert "✅" in sent
        assert "не изменён" in sent

    async def test_command_with_bot_username_supported(self) -> None:
        msg = _build_message_mock("private")
        msg.text = "/set_max_dau@PipirkaTestBot 500"
        set_max = _set_max_stub(
            return_value=SetMaxDauResult(previous_max_dau=200, new_max_dau=500),
        )
        promote = _promote_stub()

        await handle_set_max_dau(
            cast(Message, msg),
            _identity("private"),
            cast(SetMaxDau, set_max),
            cast(PromoteFromQueue, promote),
        )

        set_max.execute.assert_awaited_once_with(actor_tg_id=42, new_max_dau=500)

    async def test_missing_argument_shows_usage(self) -> None:
        msg = _build_message_mock("private")
        msg.text = "/set_max_dau"
        set_max = _set_max_stub()
        promote = _promote_stub()

        await handle_set_max_dau(
            cast(Message, msg),
            _identity("private"),
            cast(SetMaxDau, set_max),
            cast(PromoteFromQueue, promote),
        )

        set_max.execute.assert_not_awaited()
        promote.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_SET_MAX_DAU_USAGE_RU)

    async def test_non_integer_argument_shows_usage(self) -> None:
        msg = _build_message_mock("private")
        msg.text = "/set_max_dau abc"
        set_max = _set_max_stub()
        promote = _promote_stub()

        await handle_set_max_dau(
            cast(Message, msg),
            _identity("private"),
            cast(SetMaxDau, set_max),
            cast(PromoteFromQueue, promote),
        )

        set_max.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_SET_MAX_DAU_USAGE_RU)

    async def test_zero_argument_shows_usage(self) -> None:
        msg = _build_message_mock("private")
        msg.text = "/set_max_dau 0"
        set_max = _set_max_stub()
        promote = _promote_stub()

        await handle_set_max_dau(
            cast(Message, msg),
            _identity("private"),
            cast(SetMaxDau, set_max),
            cast(PromoteFromQueue, promote),
        )

        set_max.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_SET_MAX_DAU_USAGE_RU)

    async def test_negative_argument_shows_usage(self) -> None:
        msg = _build_message_mock("private")
        msg.text = "/set_max_dau -1"
        set_max = _set_max_stub()
        promote = _promote_stub()

        await handle_set_max_dau(
            cast(Message, msg),
            _identity("private"),
            cast(SetMaxDau, set_max),
            cast(PromoteFromQueue, promote),
        )

        set_max.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_SET_MAX_DAU_USAGE_RU)

    async def test_non_admin_caught_authorization_error(self) -> None:
        msg = _build_message_mock("private")
        msg.text = "/set_max_dau 1000"
        set_max = _set_max_stub(
            side_effect=AuthorizationError(
                requirement="admin_runtime_config",
                detail="actor tg_id=42 cannot change MAX_DAU",
            ),
        )
        promote = _promote_stub()

        await handle_set_max_dau(
            cast(Message, msg),
            _identity("private"),
            cast(SetMaxDau, set_max),
            cast(PromoteFromQueue, promote),
        )

        promote.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_DAU_FORBIDDEN_RU)

    async def test_group_chat_skips_use_case(self) -> None:
        msg = _build_message_mock("group")
        msg.text = "/set_max_dau 1000"
        set_max = _set_max_stub()
        promote = _promote_stub()

        await handle_set_max_dau(
            cast(Message, msg),
            _identity("group"),
            cast(SetMaxDau, set_max),
            cast(PromoteFromQueue, promote),
        )

        set_max.execute.assert_not_awaited()
        promote.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)

    async def test_no_identity_skips_use_case(self) -> None:
        msg = _build_message_mock("private")
        msg.text = "/set_max_dau 1000"
        set_max = _set_max_stub()
        promote = _promote_stub()

        await handle_set_max_dau(
            cast(Message, msg),
            None,
            cast(SetMaxDau, set_max),
            cast(PromoteFromQueue, promote),
        )

        set_max.execute.assert_not_awaited()
        promote.execute.assert_not_awaited()
        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
