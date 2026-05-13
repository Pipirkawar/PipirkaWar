"""Use-case `RunBroadcastAnnouncement` — фаза 2 `/announce` (Спринт 2.5-D.4).

Эта корутина — «фоновая задача рассылки» из спецификации D.4. Запускается
из `_dispatch_announce` (после успешной TOTP-верификации) через
`IBroadcastTaskSpawner.spawn(...)`. Внутри:

1. Перепроверяет, что админ всё ещё активный и имеет роль `SUPER_ADMIN`
   (защита-в-глубину: между `/announce` и `/confirm` админа могли
   `revoke`-нуть; mid-broadcast мутацию выполнять нельзя).
2. Вызывает `IPlayerRepository.list_active_for_broadcast(...)` ещё раз —
   адресатов могло прибыть / убыть, фаза 1 могла дать устаревший снимок.
3. Итерирует получателей **батчами** размера `BROADCAST_BATCH_SIZE` (25
   адресатов на тик). Внутри батча шлёт сообщения параллельно через
   `IBroadcastSender.send(...)` (он сам ловит транспортные ошибки и
   возвращает `BroadcastSendResult`-литерал). Между батчами — sleep
   на `BROADCAST_BATCH_INTERVAL_SECONDS` (1.0 по умолчанию). Это
   даёт устойчивые ~25 msg/sec, что заметно ниже Telegram-лимита
   ~30 msg/sec для bot-API (ПД §5, риск «rate-limit на массовые
   рассылки»). Sleep-реализация прокидывается через `_sleep`-аргумент,
   чтобы integration-тесты могли подменить её на trace-функцию и
   проверить throttle без реального ожидания.
4. Аггрегирует исходы (sent / failed / blocked) и пишет
   `ADMIN_BROADCAST_SENT` в `admin_audit_log`. Пишется один раз по
   итогам всей рассылки, в отдельной короткоживущей `IUnitOfWork`-
   транзакции (та же схема, что в `ensure_admin_authorized` —
   audit-запись остаётся в БД даже если что-то ещё пойдёт не так).
   `target_kind="locale_filter"`, `target_id=<ru|en|all>`,
   `before={"recipient_count": N}`, `after={"sent_count": ..., ...,
   "message_preview": <first 200 chars>}`.

Ошибки внутри корутины подавляются (логируются) — иначе фоновая task
закроется с исключением и super-admin никогда не узнает, что рассылка
не прошла. Аудит фиксирует факт попытки даже при partial-сбое.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
from pipirik_wars.application.admin._broadcast_ports import (
    BroadcastSendResult,
    IBroadcastSender,
)
from pipirik_wars.application.admin.broadcast_announcement import BroadcastLocaleFilter
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    AdminCommandKind,
    IAdminAuditLogger,
    IAdminAuthorizationPolicy,
    IAdminRepository,
)
from pipirik_wars.domain.player import BroadcastRecipient, IPlayerRepository
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork

#: Сколько сообщений шлём за один «тик» (батч). На тик мы делаем
#: `asyncio.gather(...)` внутри батча — параллельно, чтобы tcp-latency
#: до Telegram не складывалась последовательно. Лимит выбран из расчёта
#: `BROADCAST_BATCH_SIZE / BROADCAST_BATCH_INTERVAL_SECONDS = 25 msg/sec`,
#: что ниже Telegram-лимита ~30 msg/sec для bot-API (см. ПД §5).
BROADCAST_BATCH_SIZE: Final[int] = 25

#: Интервал между батчами в секундах. См. формулу выше.
BROADCAST_BATCH_INTERVAL_SECONDS: Final[float] = 1.0

#: Длина превью сообщения в audit-after-словаре. Достаточно, чтобы
#: super-admin в `/audit` понял «о, это была реклама нового сезона»,
#: и не превышает 200-байтовый предел индексирования аудит-таблицы.
BROADCAST_AUDIT_MESSAGE_PREVIEW_LEN: Final[int] = 200

#: Тип callable-а sleep, прокидываемого тестами (по дефолту — `asyncio.sleep`).
SleepFn = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RunBroadcastAnnouncementInput:
    """Параметры фоновой задачи broadcast-а."""

    actor_tg_id: int
    locale_filter: BroadcastLocaleFilter
    message: str
    tg_chat_id: int | None = None
    source: AdminAuditSource = AdminAuditSource.BOT
    ip: str | None = None


@dataclass(frozen=True, slots=True)
class RunBroadcastAnnouncementOutput:
    """Итог рассылки. Возвращается из `execute(...)` для тестов и логов;
    в production-flow handler уже отчитался админу первой фазы, и
    результат фиксируется только в admin-аудите.
    """

    recipient_count: int
    sent_count: int
    failed_count: int
    blocked_count: int


def _build_message_preview(message: str) -> str:
    """Обрезать сообщение до `BROADCAST_AUDIT_MESSAGE_PREVIEW_LEN` для аудита.

    Превью добавляется в `after.message_preview` audit-записи; полный
    текст в audit намеренно не логируем — он может быть длинный, а
    подзаголовок «что разослали» в /audit важнее точной копии.
    """
    if len(message) <= BROADCAST_AUDIT_MESSAGE_PREVIEW_LEN:
        return message
    return message[: BROADCAST_AUDIT_MESSAGE_PREVIEW_LEN - 1] + "…"


class RunBroadcastAnnouncement:
    """Фоновая задача рассылки `/announce` после успешного TOTP-confirm."""

    __slots__ = (
        "_admins",
        "_audit",
        "_authz",
        "_batch_interval_seconds",
        "_batch_size",
        "_clock",
        "_logger",
        "_players",
        "_sender",
        "_sleep",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        players: IPlayerRepository,
        sender: IBroadcastSender,
        audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
        sleep: SleepFn | None = None,
        batch_size: int = BROADCAST_BATCH_SIZE,
        batch_interval_seconds: float = BROADCAST_BATCH_INTERVAL_SECONDS,
        logger: logging.Logger | None = None,
    ) -> None:
        if batch_size <= 0:
            raise ValueError(f"batch_size must be positive, got {batch_size}")
        if batch_interval_seconds < 0:
            raise ValueError(
                f"batch_interval_seconds must be non-negative, got {batch_interval_seconds}",
            )
        self._uow = uow
        self._admins = admins
        self._players = players
        self._sender = sender
        self._audit = audit
        self._clock = clock
        self._authz = authz
        self._sleep = sleep or asyncio.sleep
        self._batch_size = batch_size
        self._batch_interval_seconds = batch_interval_seconds
        self._logger = logger or logging.getLogger(__name__)

    async def execute(
        self,
        inp: RunBroadcastAnnouncementInput,
    ) -> RunBroadcastAnnouncementOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        if admin.id is None:  # pragma: no cover — invariant of the repo
            raise RuntimeError("admin.id is None after get_by_tg_id")

        now = self._clock.now()
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.BROADCAST_ANNOUNCEMENT,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind="locale_filter",
            target_id=inp.locale_filter.value,
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
            source=inp.source,
            ip=inp.ip,
        )

        recipients = await self._players.list_active_for_broadcast(
            locale_filter=inp.locale_filter.value,
        )

        sent = 0
        failed = 0
        blocked = 0
        for batch_index, batch in enumerate(_chunked(recipients, self._batch_size)):
            if batch_index > 0 and self._batch_interval_seconds > 0:
                # Throttle: между батчами обязательная пауза, чтобы итоговый
                # rate сообщений в секунду не превышал TG-лимит. Перед
                # **первым** батчем не ждём — рассылка должна стартовать
                # сразу, иначе первая партия будет ждать пустого тика.
                await self._sleep(self._batch_interval_seconds)
            results = await asyncio.gather(
                *(self._sender.send(tg_id=r.tg_id, text=inp.message) for r in batch),
                return_exceptions=False,
            )
            sent_b, failed_b, blocked_b = _count(results)
            sent += sent_b
            failed += failed_b
            blocked += blocked_b

        await self._record_audit(
            admin_id=admin.id,
            input_=inp,
            recipient_count=len(recipients),
            sent_count=sent,
            failed_count=failed,
            blocked_count=blocked,
            now=now,
        )

        return RunBroadcastAnnouncementOutput(
            recipient_count=len(recipients),
            sent_count=sent,
            failed_count=failed,
            blocked_count=blocked,
        )

    async def _record_audit(
        self,
        *,
        admin_id: int,
        input_: RunBroadcastAnnouncementInput,
        recipient_count: int,
        sent_count: int,
        failed_count: int,
        blocked_count: int,
        now: datetime,
    ) -> None:
        # `IClock.now()` проброшен из `execute(...)` — фиксируем единый
        # `occurred_at` на всю аудит-запись (а не пересчитываем «сейчас»
        # после возможно долгой рассылки): super-admin в `/audit` увидит
        # время начала рассылки, что точнее «время записи аудита».
        async with self._uow:
            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_BROADCAST_SENT,
                    target_kind="locale_filter",
                    target_id=input_.locale_filter.value,
                    before={"recipient_count": recipient_count},
                    after={
                        "sent_count": sent_count,
                        "failed_count": failed_count,
                        "blocked_count": blocked_count,
                        "message_preview": _build_message_preview(input_.message),
                    },
                    reason=(
                        f"broadcast: locale={input_.locale_filter.value} "
                        f"recipients={recipient_count} sent={sent_count} "
                        f"failed={failed_count} blocked={blocked_count}"
                    ),
                    idempotency_key=None,
                    source=input_.source,
                    tg_chat_id=input_.tg_chat_id,
                    ip=input_.ip,
                    occurred_at=now,
                ),
            )


def _chunked(
    items: Sequence[BroadcastRecipient],
    size: int,
) -> list[Sequence[BroadcastRecipient]]:
    """Разбить `items` на батчи длины `size`. Последний может быть короче."""
    return [items[i : i + size] for i in range(0, len(items), size)]


def _count(results: Sequence[BroadcastSendResult]) -> tuple[int, int, int]:
    """Посчитать `(sent, failed, blocked)` в батче."""
    sent = sum(1 for r in results if r == "sent")
    failed = sum(1 for r in results if r == "failed")
    blocked = sum(1 for r in results if r == "blocked")
    return sent, failed, blocked


__all__ = [
    "BROADCAST_AUDIT_MESSAGE_PREVIEW_LEN",
    "BROADCAST_BATCH_INTERVAL_SECONDS",
    "BROADCAST_BATCH_SIZE",
    "RunBroadcastAnnouncement",
    "RunBroadcastAnnouncementInput",
    "RunBroadcastAnnouncementOutput",
    "SleepFn",
]
