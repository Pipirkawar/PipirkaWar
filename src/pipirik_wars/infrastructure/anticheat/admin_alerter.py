"""Реализация `IAnticheatAdminAlerter` поверх `structlog`.

Алёрт уезжает обычным `log.warning(...)` со структурированными полями.
Stdout/JSON-формат настраивается на уровне приложения (см. `bot/main.py`
и `bot/middlewares/error_handler.py` — там же конфигурируется processors).

Когда понадобится дополнительный канал доставки (Telegram-уведомление
администраторам, Slack, e-mail), достаточно будет добавить второй
`IAnticheatAdminAlerter`-адаптер и собрать `CompositeAnticheatAdminAlerter`,
который раскидывает событие по списку — без правки use-case-а
`AddLength`.

Pattern скопирован из `StructlogDauThresholdAlerter` (Спринт 1.2.D).
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import structlog

from pipirik_wars.domain.anticheat import IAnticheatAdminAlerter
from pipirik_wars.domain.shared.ports.audit import AuditSource

_LOGGER_NAME: Final[str] = "pipirik_wars.anticheat.trip_wire"


class StructlogAnticheatAdminAlerter(IAnticheatAdminAlerter):
    """Пишет structlog-warning при срабатывании anti-cheat trip-wire.

    Тред-сэйф (boilerplate structlog), без локального состояния —
    идемпотентность «1 раз на бан» обеспечивается caller-ом
    (`AddLength` алёртит ровно один раз — на момент перехода игрока
    из «не в бане» в «в бане»; повторные `add_length`-вызовы
    стопаются soft-ban-гейтом раньше, до alert-а).
    """

    __slots__ = ("_logger",)

    def __init__(self, *, logger: structlog.stdlib.BoundLogger | None = None) -> None:
        self._logger = logger if logger is not None else structlog.get_logger(_LOGGER_NAME)

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
        self._logger.warning(
            "anticheat.trip_wire.fired",
            player_id=player_id,
            cap_kind=cap_kind,
            cap_cm=cap_cm,
            observed_sum_cm=observed_sum_cm,
            overflow_cm=observed_sum_cm - cap_cm,
            source=source.value,
            banned_until=banned_until.isoformat(),
            occurred_at=occurred_at.isoformat(),
        )
