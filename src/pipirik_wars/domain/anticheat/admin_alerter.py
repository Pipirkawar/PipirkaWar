"""Порт `IAnticheatAdminAlerter` — алёрт админу при срабатывании trip-wire (Спринт 1.6.D).

Зачем выделен отдельный порт (а не `structlog.get_logger()` прямо
в use-case-е): use-case `AddLength` лежит в слое `application`, для
которого `import-linter` запрещает прямые I/O-зависимости. Текущая
реализация — `infrastructure/anticheat/admin_alerter.py::
StructlogAnticheatAdminAlerter` (просто `log.warning(...)`); в будущем
её можно расширить отправкой Telegram-уведомления админам или Slack —
без правки самого `AddLength`.

Идемпотентность «не алёртить дважды на тот же бан» **не** живёт
здесь: эмиттер тупой, его задача — отправить алёрт. За «слать или
нет» отвечает use-case (`AddLength` алёртит ровно один раз — при
переходе из «не в бане» в «в бане»).

Pattern скопирован из `IDauThresholdAlerter` (Спринт 1.2.D).
"""

from __future__ import annotations

import abc
from datetime import datetime

from pipirik_wars.domain.shared.ports.audit import AuditSource


class IAnticheatAdminAlerter(abc.ABC):
    """Эмиттер алёрта админу при срабатывании anti-cheat trip-wire (ГДД §3.3.5)."""

    @abc.abstractmethod
    async def emit(
        self,
        *,
        player_id: int,
        cap_kind: str,
        cap_cm: int,
        observed_sum_cm: int,
        source: AuditSource,
        banned_until: datetime,
        occurred_at: datetime,
    ) -> None:
        """Отправить одно событие алёрта.

        :param player_id: Внутренний `players.id` нарушителя.
        :param cap_kind: `"daily"` или `"weekly"` — какой лимит пробит.
        :param cap_cm: Значение лимита из `balance.yaml::anticheat.daily_cap_cm`/
            `weekly_cap_cm` на момент срабатывания.
        :param observed_sum_cm: Фактическая сумма organic-прироста в окне
            (строго > `cap_cm`, иначе trip-wire не срабатывает).
        :param source: `AuditSource`, на котором сработал trip-wire (та
            самая дельта, после применения которой окно ушло за лимит).
        :param banned_until: Момент истечения soft-ban-а (UTC, tz-aware).
        :param occurred_at: Момент срабатывания (UTC, tz-aware) — обычно
            совпадает с `clock.now()` use-case-а.
        """
