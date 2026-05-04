"""Use-case `CheckDauThreshold` (Спринт 1.2.7 / 1.2.D).

Когда счётчик активных игроков пересекает 80 % от `MAX_DAU` — пишем
audit-запись `DAU_THRESHOLD_REACHED` и эмитим алёрт через
`IDauThresholdAlerter`. Для аудита и операторской видимости (см.
`development_plan.md` §8.3) этого достаточно: в JSON-логе появится
структурированное событие, его можно превратить в triger для
Telegram-уведомления / Slack-алёрта без правки use-case-а.

Идемпотентность — «1 раз в сутки»:
- Ключ: `dau_threshold_alert:{moscow_date}` (день по `Europe/Moscow`,
  совпадает с дневным окном `IDauCounter`).
- Перед записью use-case проверяет `IIdempotencyKey.is_seen(key)`;
  если уже отмечен — не пишет ничего и не зовёт алёрт.

Точки вызова:
- `RegisterPlayer` — после успешного `record_active(...)`.
- `PromoteFromQueue` — после поднятия игроков и `record_active(...)`.

Use-case возвращает `CheckDauThresholdResult`, чтобы caller мог понять,
сработал алёрт в этом вызове или нет (для тестов и опционального
подсчёта).
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.dau import IDauCounter, IDauLimit, IDauThresholdAlerter
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IIdempotencyKey,
    IUnitOfWork,
)

DAU_THRESHOLD_PERCENT = 80
DAU_THRESHOLD_NAMESPACE = "dau_threshold_alert"


def _is_threshold_reached(*, current: int, max_dau: int) -> bool:
    """`current >= 80 % * max_dau` без потери точности на float-ах.

    Для `max_dau=1` алёрт сработает уже при первом игроке (1 >= 0.8 → True),
    что соответствует семантике «лимит на 80 % исчерпан».
    """
    return 5 * current >= 4 * max_dau and max_dau >= 1


@dataclass(frozen=True, slots=True)
class CheckDauThresholdResult:
    """Что сделал `CheckDauThreshold.execute()`."""

    triggered: bool
    current_dau: int
    max_dau: int

    @property
    def percent(self) -> int:
        if self.max_dau == 0:
            return 0
        return self.current_dau * 100 // self.max_dau


class CheckDauThreshold:
    """Проверка порога DAU и эмиссия алёрта (1×в сутки)."""

    __slots__ = (
        "_alerter",
        "_audit",
        "_clock",
        "_dau_counter",
        "_dau_limit",
        "_idempotency",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        dau_counter: IDauCounter,
        dau_limit: IDauLimit,
        idempotency: IIdempotencyKey,
        audit: IAuditLogger,
        alerter: IDauThresholdAlerter,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._dau_counter = dau_counter
        self._dau_limit = dau_limit
        self._idempotency = idempotency
        self._audit = audit
        self._alerter = alerter
        self._clock = clock

    async def execute(self) -> CheckDauThresholdResult:
        """Проверить порог и при необходимости отправить алёрт.

        В одной транзакции UoW: проверка-пометка ключа +
        запись в `audit_log`. Сам алёрт (`IDauThresholdAlerter.emit`) —
        **после** коммита, чтобы side-effect не выполнялся при rollback-е
        транзакции (например, при упавшем INSERT в audit).
        """
        current = await self._dau_counter.current()
        max_dau = await self._dau_limit.get()
        if not _is_threshold_reached(current=current, max_dau=max_dau):
            return CheckDauThresholdResult(
                triggered=False,
                current_dau=current,
                max_dau=max_dau,
            )
        moscow_date = self._clock.moscow_date()
        key = self._idempotency.build(
            DAU_THRESHOLD_NAMESPACE,
            [moscow_date.isoformat()],
        )
        now = self._clock.now()
        async with self._uow:
            if await self._idempotency.is_seen(key):
                return CheckDauThresholdResult(
                    triggered=False,
                    current_dau=current,
                    max_dau=max_dau,
                )
            await self._idempotency.mark(key, namespace=DAU_THRESHOLD_NAMESPACE)
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.DAU_THRESHOLD_REACHED,
                    actor_id=None,
                    target_kind="dau",
                    target_id=moscow_date.isoformat(),
                    before=None,
                    after={
                        "current_dau": current,
                        "max_dau": max_dau,
                        "percent": DAU_THRESHOLD_PERCENT,
                    },
                    reason="dau_threshold_alert",
                    idempotency_key=key,
                    occurred_at=now,
                )
            )
        await self._alerter.emit(
            current_dau=current,
            max_dau=max_dau,
            percent=DAU_THRESHOLD_PERCENT,
            occurred_at=now,
        )
        return CheckDauThresholdResult(
            triggered=True,
            current_dau=current,
            max_dau=max_dau,
        )
