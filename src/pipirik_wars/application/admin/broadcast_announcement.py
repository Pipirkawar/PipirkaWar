"""Use-case `BroadcastAnnouncement` — фаза 1 `/announce` (Спринт 2.5-D.4, ГДД §18.6.5).

`/announce <ru|en|all> <message>` — глобальная рассылка от super-admin-а.
TOTP-обязательная (только роль `SUPER_ADMIN`). Идёт двухфазно:

* Фаза 1 (этот модуль): handler `/announce` зовёт `BroadcastAnnouncement.execute(...)`,
  use-case проверяет RBAC, валидирует `locale_filter` / `message`, считает
  предварительное количество получателей и возвращает «контракт»
  (`BroadcastAnnouncementOutput`). Handler сохраняет результат в
  `IAdminConfirmStore` через `RequestAdminConfirm` и отвечает админу:
  «введи /confirm <code>; будет отправлено N игрокам».
* Фаза 2 (`run_broadcast_announcement.py`): `_dispatch_announce`-handler
  (после успешной TOTP-верификации) запускает `RunBroadcastAnnouncement`
  в фоновой задаче через `IBroadcastTaskSpawner`. Эта задача
  итерирует получателей с throttling, отправляет сообщения и фиксирует
  итог в `ADMIN_BROADCAST_SENT` admin-аудите.

Разделение на две фазы позволяет:

* пораньше отказать тем, у кого нет роли `SUPER_ADMIN` (audit
  `ADMIN_AUTHORIZATION_DENIED` пишется до `/confirm`-токена);
* показать админу количество получателей до подтверждения, чтобы он мог
  оценить масштаб рассылки и не отправил «случайно всем 50k игрокам»;
* атомарно зафиксировать payload в `IAdminConfirmStore` (TOTP-флоу), —
  чтобы между фазами не было гонки «таргеты поменялись», и админ
  увидел в фазе-2 ровно тот текст и ту локаль, которые сам выбрал.

`recipient_count` — это снимок выборки на момент фазы 1. В фазе 2
выборка делается ещё раз (могли подтянуться новые регистрации,
кто-то заморозился), и `ADMIN_BROADCAST_SENT.before.recipient_count`
будет содержать **фактическое** число (фазы 2). Расхождение в `/audit`
видно явно — это нормально для асинхронной рассылки.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminCommandKind,
    IAdminAuditLogger,
    IAdminAuthorizationPolicy,
    IAdminRepository,
)
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork
from pipirik_wars.shared.errors import DomainError

#: Максимальная длина текста объявления в символах.
#: Telegram limit для `send_message` — 4096; оставляем ровно лимит,
#: префиксы / форматирование `BroadcastPresenter` добавит при доставке.
BROADCAST_MESSAGE_MAX_LEN: Final[int] = 4096

#: Минимальная длина (после `strip()`). Пустые объявления — UX-ошибка.
BROADCAST_MESSAGE_MIN_LEN: Final[int] = 1


class BroadcastLocaleFilter(str, enum.Enum):
    """Фильтр получателей по локали.

    Семантика — см. `IPlayerRepository.list_active_for_broadcast`.
    Закрытый whitelist; handler сам нормализует ввод (case-insensitive,
    `*` → `ALL`).
    """

    RU = "ru"
    EN = "en"
    ALL = "all"


class BroadcastValidationError(DomainError):
    """Базовый класс ошибок валидации `/announce`.

    Конкретные подклассы handler-у нужны, чтобы показать пользователю
    адресный текст («слишком длинное сообщение», «неизвестный фильтр
    локали») вместо общего «неверный формат».
    """


class BroadcastLocaleFilterInvalidError(BroadcastValidationError):
    """`locale_filter` не из whitelist `BroadcastLocaleFilter`."""

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        super().__init__(f"unsupported locale_filter={value!r}; expected one of: ru, en, all")
        self.value = value


class BroadcastMessageEmptyError(BroadcastValidationError):
    """Текст объявления пустой (после `strip()`)."""

    def __init__(self) -> None:
        super().__init__("broadcast message must be non-empty")


class BroadcastMessageTooLongError(BroadcastValidationError):
    """Текст объявления длиннее `BROADCAST_MESSAGE_MAX_LEN`."""

    __slots__ = ("length",)

    def __init__(self, length: int) -> None:
        super().__init__(
            f"broadcast message is too long: got {length} chars, max {BROADCAST_MESSAGE_MAX_LEN}",
        )
        self.length = length


def parse_locale_filter(raw: str) -> BroadcastLocaleFilter:
    """Распарсить пользовательский ввод в `BroadcastLocaleFilter`.

    Допустимые формы (case-insensitive):

    * `"ru"` → `RU`
    * `"en"` → `EN`
    * `"all"` или `"*"` → `ALL`

    Любое другое значение → `BroadcastLocaleFilterInvalidError`. Парсер
    лежит здесь (а не в handler-е), чтобы той же логикой пользовалась
    web-панель из Спринта 4.5, если когда-нибудь появится.
    """
    normalized = raw.strip().lower()
    if normalized == "*":
        return BroadcastLocaleFilter.ALL
    try:
        return BroadcastLocaleFilter(normalized)
    except ValueError as exc:
        raise BroadcastLocaleFilterInvalidError(value=raw) from exc


def normalize_broadcast_message(raw: str) -> str:
    """Нормализовать текст объявления и провалидировать длину.

    * `strip()` — обрезаем хвостовые пробелы / переводы строк (Telegram
      их и так визуально игнорирует, а нам в audit-`reason` нужны
      «чистые» данные для фильтра).
    * Длина в символах считается **после** strip-а. Под `min < len <= max`
      падаем явными ошибками.
    """
    stripped = raw.strip()
    if len(stripped) < BROADCAST_MESSAGE_MIN_LEN:
        raise BroadcastMessageEmptyError()
    if len(stripped) > BROADCAST_MESSAGE_MAX_LEN:
        raise BroadcastMessageTooLongError(length=len(stripped))
    return stripped


@dataclass(frozen=True, slots=True)
class BroadcastAnnouncementInput:
    """Параметры запроса на broadcast (фаза 1)."""

    actor_tg_id: int
    locale_filter_raw: str
    message_raw: str
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class BroadcastAnnouncementOutput:
    """Результат фазы 1: всё, что нужно сохранить в `IAdminConfirmStore`-payload-е."""

    locale_filter: BroadcastLocaleFilter
    message: str
    recipient_count: int


class BroadcastAnnouncement:
    """Use-case фазы 1 `/announce` (валидация + RBAC + предварительный счёт)."""

    __slots__ = (
        "_admins",
        "_audit",
        "_authz",
        "_clock",
        "_players",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        players: IPlayerRepository,
        audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._players = players
        self._audit = audit
        self._clock = clock
        self._authz = authz

    async def execute(self, inp: BroadcastAnnouncementInput) -> BroadcastAnnouncementOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        if admin.id is None:  # pragma: no cover — invariant of the repo
            raise RuntimeError("admin.id is None after get_by_tg_id")

        locale_filter = parse_locale_filter(inp.locale_filter_raw)
        message = normalize_broadcast_message(inp.message_raw)

        now = self._clock.now()
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.BROADCAST_ANNOUNCEMENT,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind="locale_filter",
            target_id=locale_filter.value,
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
        )

        recipients = await self._players.list_active_for_broadcast(
            locale_filter=locale_filter.value,
        )
        return BroadcastAnnouncementOutput(
            locale_filter=locale_filter,
            message=message,
            recipient_count=len(recipients),
        )


__all__ = [
    "BROADCAST_MESSAGE_MAX_LEN",
    "BROADCAST_MESSAGE_MIN_LEN",
    "BroadcastAnnouncement",
    "BroadcastAnnouncementInput",
    "BroadcastAnnouncementOutput",
    "BroadcastLocaleFilter",
    "BroadcastLocaleFilterInvalidError",
    "BroadcastMessageEmptyError",
    "BroadcastMessageTooLongError",
    "BroadcastValidationError",
    "normalize_broadcast_message",
    "parse_locale_filter",
]
