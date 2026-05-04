"""Реализация `IDauThresholdAlerter` поверх `structlog`.

Алёрт уезжает обычным `log.warning(...)` со структурированными полями.
Stdout/JSON-формат настраивается на уровне приложения (см. `bot/main.py`
и `bot/middlewares/error_handler.py` — там же конфигурируется processors).

Когда понадобится дополнительный канал доставки (Telegram-уведомление
администраторам, Slack, e-mail), достаточно будет добавить второй
`IDauThresholdAlerter`-адаптер и собрать `CompositeDauThresholdAlerter`,
который раскидывает событие по списку — без правки use-case-а.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import structlog

from pipirik_wars.domain.dau import IDauThresholdAlerter

_LOGGER_NAME: Final[str] = "pipirik_wars.dau.threshold"


class StructlogDauThresholdAlerter(IDauThresholdAlerter):
    """Пишет structlog-warning при пересечении порога DAU.

    Тред-сэйф (бOilерплейт structlog), без локального состояния —
    идемпотентность «1 раз в сутки» обеспечивается caller-ом
    (`CheckDauThreshold`).
    """

    __slots__ = ("_logger",)

    def __init__(self, *, logger: structlog.stdlib.BoundLogger | None = None) -> None:
        self._logger = logger if logger is not None else structlog.get_logger(_LOGGER_NAME)

    async def emit(
        self,
        *,
        current_dau: int,
        max_dau: int,
        percent: int,
        occurred_at: datetime,
    ) -> None:
        self._logger.warning(
            "dau.threshold.reached",
            current_dau=current_dau,
            max_dau=max_dau,
            percent=percent,
            occurred_at=occurred_at.isoformat(),
        )
