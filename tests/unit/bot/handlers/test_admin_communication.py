"""Unit-тесты handler-а `admin_communication` (Спринт 2.5-D.4 `/announce`).

Покрывает:
- handle_announce (фаза 1) — парсинг `/announce <locale> <text>`,
  RBAC-deny, TOTP-not-configured, валидация локали, валидация длины,
  выдача `/confirm`-токена, реакция на не-private-чат.
- dispatch_announce (фаза 2) — sanity-проверки payload-а, запуск фоновой
  задачи через `IBroadcastTaskSpawner.spawn(...)`, отправка
  «отправляю N игрокам» в чат админа.
- Регистрация `dispatch_announce` в registry `CONFIRM_DISPATCHERS` под
  ключом `COMMAND_KIND_BROADCAST_ANNOUNCEMENT`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.filters.command import CommandObject
from aiogram.types import Chat, Message

from pipirik_wars.application.admin import (
    BROADCAST_MESSAGE_MAX_LEN,
    BanPlayer,
    BroadcastAnnouncement,
    BroadcastAnnouncementOutput,
    BroadcastLocaleFilter,
    BroadcastLocaleFilterInvalidError,
    BroadcastMessageEmptyError,
    BroadcastMessageTooLongError,
    GrantLength,
    GrantThickness,
    IBroadcastTaskSpawner,
    RequestAdminConfirm,
    RequestAdminConfirmOutput,
    RunBroadcastAnnouncement,
    SetBalanceValue,
    VerifyAdminConfirmOutput,
)
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey
from pipirik_wars.bot.handlers.admin_communication import (
    COMMAND_KIND_BROADCAST_ANNOUNCEMENT,
    REPLY_NON_PRIVATE_RU,
    dispatch_announce,
    handle_announce,
)
from pipirik_wars.bot.handlers.admin_economy import (
    CONFIRM_DISPATCHERS,
    ConfirmDispatchDeps,
)
from pipirik_wars.bot.middlewares.auth import TgIdentity
from pipirik_wars.domain.admin import TotpNotConfiguredError
from pipirik_wars.domain.shared.ports import IClock

_RU = Locale("ru")


class _StubBundle(IMessageBundle):
    """Mини-бандл, отдающий `key|locale|kw1=v1,kw2=v2` для assert-ов."""

    def format(self, key: MessageKey, *, locale: Locale, **kwargs: object) -> str:
        params = ",".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return f"{key}|{locale.code}|{params}"


@pytest.fixture
def bundle() -> IMessageBundle:
    return _StubBundle()


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
    return CommandObject(prefix="/", command="announce", mention=None, args=args)


def _stub_broadcast_announcement(
    *,
    output: BroadcastAnnouncementOutput | None = None,
    raises: Exception | None = None,
) -> BroadcastAnnouncement:
    fake = MagicMock(spec=BroadcastAnnouncement)
    if raises is not None:
        fake.execute = AsyncMock(side_effect=raises)
    elif output is not None:
        fake.execute = AsyncMock(return_value=output)
    else:
        fake.execute = AsyncMock()
    return cast(BroadcastAnnouncement, fake)


def _stub_request_confirm(
    *,
    output: RequestAdminConfirmOutput | None = None,
    raises: Exception | None = None,
) -> RequestAdminConfirm:
    fake = MagicMock(spec=RequestAdminConfirm)
    if raises is not None:
        fake.execute = AsyncMock(side_effect=raises)
    elif output is not None:
        fake.execute = AsyncMock(return_value=output)
    else:
        fake.execute = AsyncMock()
    return cast(RequestAdminConfirm, fake)


def _stub_run_broadcast() -> RunBroadcastAnnouncement:
    fake = MagicMock(spec=RunBroadcastAnnouncement)
    fake.execute = AsyncMock()
    return cast(RunBroadcastAnnouncement, fake)


class _SpyTaskSpawner(IBroadcastTaskSpawner):
    """Запоминает `spawn(coro)`-вызов; не запускает coro немедленно."""

    def __init__(self) -> None:
        self.spawned: list[object] = []

    def spawn(self, coro: object) -> None:  # type: ignore[override]
        self.spawned.append(coro)


def _fixed_clock() -> IClock:
    fake = MagicMock(spec=IClock)
    fake.now = MagicMock(return_value=datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC))
    return cast(IClock, fake)


def _deps(
    *,
    spawner: IBroadcastTaskSpawner | None = None,
    runner: RunBroadcastAnnouncement | None = None,
) -> ConfirmDispatchDeps:
    """Фабрика `ConfirmDispatchDeps` для dispatch-тестов.

    Поля «не-broadcast» (grant_length, ban_player, ...) — полные
    `MagicMock`-spec-и, dispatch_announce их не использует, но
    `ConfirmDispatchDeps` обязывает их предоставить.
    """
    return ConfirmDispatchDeps(
        grant_length=cast(GrantLength, MagicMock(spec=GrantLength)),
        grant_thickness=cast(GrantThickness, MagicMock(spec=GrantThickness)),
        set_balance_value=cast(SetBalanceValue, MagicMock(spec=SetBalanceValue)),
        ban_player=cast(BanPlayer, MagicMock(spec=BanPlayer)),
        run_broadcast_announcement=runner or _stub_run_broadcast(),
        broadcast_task_spawner=spawner or _SpyTaskSpawner(),
        clock=_fixed_clock(),
    )


# ── Фаза 1: handle_announce ───────────────────────────────────────────────


@pytest.mark.asyncio
class TestHandleAnnounceParsing:
    """Парсинг `/announce <locale> <text>` и контроль не-private-чата."""

    async def test_non_private_chat_replies_with_ru_hint(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock(chat_type="group")
        announce_uc = _stub_broadcast_announcement()
        confirm_uc = _stub_request_confirm()

        await handle_announce(
            message=cast(Message, msg),
            command=_command("ru hi"),
            tg_identity=_identity(chat_kind="group"),
            broadcast_announcement=announce_uc,
            request_admin_confirm=confirm_uc,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once_with(REPLY_NON_PRIVATE_RU)
        announce_uc.execute.assert_not_awaited()
        confirm_uc.execute.assert_not_awaited()

    async def test_no_args_replies_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        announce_uc = _stub_broadcast_announcement()
        confirm_uc = _stub_request_confirm()

        await handle_announce(
            message=cast(Message, msg),
            command=_command(""),
            tg_identity=_identity(),
            broadcast_announcement=announce_uc,
            request_admin_confirm=confirm_uc,
            bundle=bundle,
            locale=_RU,
        )

        # Usage-сообщение содержит ключ admin-announce-usage.
        msg.answer.assert_awaited_once()
        assert "admin-announce-usage" in msg.answer.await_args.args[0]
        announce_uc.execute.assert_not_awaited()

    async def test_only_locale_no_message_replies_usage(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        announce_uc = _stub_broadcast_announcement()
        confirm_uc = _stub_request_confirm()

        await handle_announce(
            message=cast(Message, msg),
            command=_command("ru"),  # только locale-фильтр, без текста
            tg_identity=_identity(),
            broadcast_announcement=announce_uc,
            request_admin_confirm=confirm_uc,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once()
        assert "admin-announce-usage" in msg.answer.await_args.args[0]
        announce_uc.execute.assert_not_awaited()


@pytest.mark.asyncio
class TestHandleAnnounceAuthorization:
    """RBAC-отказы и TOTP-not-configured (фаза 1)."""

    async def test_authorization_error_replies_not_authorized(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        announce_uc = _stub_broadcast_announcement(
            raises=AuthorizationError(requirement="rbac", detail="deny"),
        )
        confirm_uc = _stub_request_confirm()

        await handle_announce(
            message=cast(Message, msg),
            command=_command("ru hi"),
            tg_identity=_identity(),
            broadcast_announcement=announce_uc,
            request_admin_confirm=confirm_uc,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once()
        assert "admin-announce-not-authorized" in msg.answer.await_args.args[0]
        confirm_uc.execute.assert_not_awaited()

    async def test_totp_not_configured_replies_locale_string(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        announce_uc = _stub_broadcast_announcement(
            output=BroadcastAnnouncementOutput(
                locale_filter=BroadcastLocaleFilter.RU,
                message="hi",
                recipient_count=10,
            ),
        )
        confirm_uc = _stub_request_confirm(raises=TotpNotConfiguredError())

        await handle_announce(
            message=cast(Message, msg),
            command=_command("ru hi"),
            tg_identity=_identity(),
            broadcast_announcement=announce_uc,
            request_admin_confirm=confirm_uc,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once()
        assert "admin-announce-totp-not-configured" in msg.answer.await_args.args[0]


@pytest.mark.asyncio
class TestHandleAnnounceValidation:
    """Доменные ошибки валидации (фаза 1)."""

    async def test_bad_locale_filter_replies_locale_string(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        announce_uc = _stub_broadcast_announcement(
            raises=BroadcastLocaleFilterInvalidError("xx"),
        )
        confirm_uc = _stub_request_confirm()

        await handle_announce(
            message=cast(Message, msg),
            command=_command("xx hi"),
            tg_identity=_identity(),
            broadcast_announcement=announce_uc,
            request_admin_confirm=confirm_uc,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once()
        rendered = msg.answer.await_args.args[0]
        assert "admin-announce-bad-locale" in rendered
        assert "value=xx" in rendered  # параметр пробрасывается в bundle.format

    async def test_empty_message_replies_locale_string(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        announce_uc = _stub_broadcast_announcement(
            raises=BroadcastMessageEmptyError(),
        )
        confirm_uc = _stub_request_confirm()

        await handle_announce(
            message=cast(Message, msg),
            command=_command("ru placeholder"),
            tg_identity=_identity(),
            broadcast_announcement=announce_uc,
            request_admin_confirm=confirm_uc,
            bundle=bundle,
            locale=_RU,
        )

        # use-case замокан как `raises=BroadcastMessageEmptyError()` —
        # handler ловит исключение и отвечает локалью empty-message.
        msg.answer.assert_awaited_once()
        assert "admin-announce-empty-message" in msg.answer.await_args.args[0]

    async def test_message_too_long_passes_length_to_bundle(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        too_long = BROADCAST_MESSAGE_MAX_LEN + 100
        announce_uc = _stub_broadcast_announcement(
            raises=BroadcastMessageTooLongError(length=too_long),
        )
        confirm_uc = _stub_request_confirm()

        await handle_announce(
            message=cast(Message, msg),
            command=_command(f"ru {'А' * too_long}"),
            tg_identity=_identity(),
            broadcast_announcement=announce_uc,
            request_admin_confirm=confirm_uc,
            bundle=bundle,
            locale=_RU,
        )

        msg.answer.assert_awaited_once()
        rendered = msg.answer.await_args.args[0]
        assert "admin-announce-too-long" in rendered
        assert f"length={too_long}" in rendered
        assert f"max_length={BROADCAST_MESSAGE_MAX_LEN}" in rendered


@pytest.mark.asyncio
class TestHandleAnnounceHappyPath:
    """Успешный путь фазы 1: pre-flight count → confirm-токен."""

    async def test_issues_confirm_token_with_recipient_count(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        announce_uc = _stub_broadcast_announcement(
            output=BroadcastAnnouncementOutput(
                locale_filter=BroadcastLocaleFilter.RU,
                message="hello",
                recipient_count=42,
            ),
        )
        confirm_uc = _stub_request_confirm(
            output=RequestAdminConfirmOutput(token="TOK", ttl_seconds=120),
        )

        await handle_announce(
            message=cast(Message, msg),
            command=_command("ru hello"),
            tg_identity=_identity(),
            broadcast_announcement=announce_uc,
            request_admin_confirm=confirm_uc,
            bundle=bundle,
            locale=_RU,
        )

        # Phase 1 должна вызвать use-case с правильным input-ом.
        announce_uc.execute.assert_awaited_once()
        announce_call = announce_uc.execute.await_args.args[0]
        assert announce_call.actor_tg_id == 42
        assert announce_call.locale_filter_raw == "ru"
        assert announce_call.message_raw == "hello"

        # И затем — выдать `/confirm`-токен с тем же payload-ом.
        confirm_uc.execute.assert_awaited_once()
        confirm_call = confirm_uc.execute.await_args.args[0]
        assert confirm_call.command_kind == COMMAND_KIND_BROADCAST_ANNOUNCEMENT
        assert confirm_call.target_kind == "locale_filter"
        assert confirm_call.target_id == "ru"
        assert confirm_call.payload["locale_filter"] == "ru"
        assert confirm_call.payload["message"] == "hello"
        assert confirm_call.payload["recipient_count"] == 42

        # Финальный ответ — confirm-issued со всеми параметрами.
        msg.answer.assert_awaited_once()
        rendered = msg.answer.await_args.args[0]
        assert "admin-announce-confirm-issued" in rendered
        assert "token=TOK" in rendered
        assert "ttl_seconds=120" in rendered
        assert "recipient_count=42" in rendered
        assert "locale_filter=ru" in rendered


# ── Фаза 2: dispatch_announce ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestDispatchAnnounce:
    """Phase 2 — после `/confirm` запускает фоновую задачу."""

    def _verify_output(
        self,
        *,
        locale_filter: str = "ru",
        message: str = "hello",
        recipient_count: int = 42,
    ) -> VerifyAdminConfirmOutput:
        return VerifyAdminConfirmOutput(
            command_kind=COMMAND_KIND_BROADCAST_ANNOUNCEMENT,
            target_kind="locale_filter",
            target_id=locale_filter,
            payload=MappingProxyType(
                {
                    "locale_filter": locale_filter,
                    "message": message,
                    "recipient_count": recipient_count,
                },
            ),
        )

    async def test_payload_invalid_replies_not_authorized(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        spawner = _SpyTaskSpawner()
        deps = _deps(spawner=spawner)
        # `locale_filter` отсутствует в payload-е — sanity-check валит фазу 2.
        result = VerifyAdminConfirmOutput(
            command_kind=COMMAND_KIND_BROADCAST_ANNOUNCEMENT,
            target_kind="locale_filter",
            target_id="ru",
            payload=MappingProxyType({"message": "hi"}),
        )

        await dispatch_announce(
            result=result,
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=deps,
        )

        msg.answer.assert_awaited_once()
        assert "admin-announce-not-authorized" in msg.answer.await_args.args[0]
        # Без задачи в фоне.
        assert spawner.spawned == []

    async def test_invalid_locale_filter_value_replies_not_authorized(
        self, bundle: IMessageBundle
    ) -> None:
        msg = _msg_mock()
        spawner = _SpyTaskSpawner()
        deps = _deps(spawner=spawner)
        # Хорошие типы, но `locale_filter` не из BroadcastLocaleFilter-а.
        result = VerifyAdminConfirmOutput(
            command_kind=COMMAND_KIND_BROADCAST_ANNOUNCEMENT,
            target_kind="locale_filter",
            target_id="zz",
            payload=MappingProxyType(
                {"locale_filter": "zz", "message": "hi", "recipient_count": 1},
            ),
        )

        await dispatch_announce(
            result=result,
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=deps,
        )

        msg.answer.assert_awaited_once()
        assert "admin-announce-not-authorized" in msg.answer.await_args.args[0]
        assert spawner.spawned == []

    async def test_happy_path_spawns_background_task(self, bundle: IMessageBundle) -> None:
        msg = _msg_mock()
        spawner = _SpyTaskSpawner()
        runner = _stub_run_broadcast()
        deps = _deps(spawner=spawner, runner=runner)

        await dispatch_announce(
            result=self._verify_output(),
            message=cast(Message, msg),
            identity=_identity(),
            locale=_RU,
            bundle=bundle,
            deps=deps,
        )

        # Сначала отправлено progress-start с recipient_count.
        msg.answer.assert_awaited_once()
        rendered = msg.answer.await_args.args[0]
        assert "admin-announce-progress-start" in rendered
        assert "recipient_count=42" in rendered
        assert "locale_filter=ru" in rendered

        # И ровно один фоновый task-coro поставлен в spawner.
        assert len(spawner.spawned) == 1


# ── Регистрация в CONFIRM_DISPATCHERS ─────────────────────────────────────


def test_confirm_dispatchers_registered_for_broadcast() -> None:
    """`dispatch_announce` доступен по ключу `broadcast_announcement`.

    Импорт `admin_communication`-модуля (выше — в этом же файле) уже
    мутирует `CONFIRM_DISPATCHERS`; проверяем, что под нужным command_kind
    лежит наш callable.
    """
    assert COMMAND_KIND_BROADCAST_ANNOUNCEMENT == "broadcast_announcement"
    assert CONFIRM_DISPATCHERS[COMMAND_KIND_BROADCAST_ANNOUNCEMENT] is dispatch_announce
