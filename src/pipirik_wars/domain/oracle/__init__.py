"""Домен «Предсказатель» (`/oracle`, Спринт 1.4.B, ГДД §11).

Игрок раз в сутки по `Europe/Moscow` зовёт `/oracle` и получает:

- прибавку длины ``uniform(oracle.bonus_min, oracle.bonus_max)`` см
  (по балансу `oracle.distribution = "uniform"`);
- предсказание из каталога `templates/oracle_<locale>.json` (≥ 200
  шаблонов на локаль, ГДД §11 / ПД §3 / Спринт 1.4.5).

Кулдаун — суточный, считается по календарной дате `Europe/Moscow`
(а не UTC): сброс ровно в 00:00 МСК. Это важно для ночных игроков —
01:00 UTC = 04:00 МСК уже «новый день», 22:00 UTC = 01:00 МСК
следующего дня тоже «новый день».
"""

from __future__ import annotations

from pipirik_wars.domain.oracle.entities import (
    OracleResult,
    OracleTemplate,
)
from pipirik_wars.domain.oracle.errors import (
    OracleAlreadyUsedTodayError,
    OracleError,
    OracleNoTemplatesError,
)
from pipirik_wars.domain.oracle.repositories import (
    IOracleHistoryRepository,
    OracleInvocation,
)
from pipirik_wars.domain.oracle.services import roll_oracle

__all__ = [
    "IOracleHistoryRepository",
    "OracleAlreadyUsedTodayError",
    "OracleError",
    "OracleInvocation",
    "OracleNoTemplatesError",
    "OracleResult",
    "OracleTemplate",
    "roll_oracle",
]
