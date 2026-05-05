"""Доменные value object-ы анти-чит-окна.

`AnticheatWindow` — иммутабельный снимок rolling-агрегации organic-прироста
длины игрока за заданный временной отрезок. Создаётся репозиторием
(`IAnticheatRepository.sum_organic_in_window`) и потребляется use-case-ом
`progression.add_length` (Спринт 1.6.D) для clamp-логики и trip-wire-проверки.

Сам объект иммутабельный и не имеет I/O — арифметика clamp-а выражена
явно через методы `remaining_cap_cm` / `is_exceeded`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AnticheatWindow:
    """Снимок anti-cheat rolling-окна для конкретного игрока.

    Все datetime'ы — timezone-aware UTC. `since` — момент старта окна
    (включительно: события с `occurred_at >= since` агрегируются).
    `organic_sum_cm` — сумма всех **положительных** дельт organic-источников
    (whitelist из `balance.anticheat.organic_sources`) за окно. Сюда НЕ
    попадают: donate-источники, `admin_refund` (отрицательные дельты),
    источник `unknown` (backfill-маркер до Спринта 1.6.A), события без
    `delta_cm` (не-длиновые мутации).
    """

    player_id: int
    since: datetime
    organic_sum_cm: int

    def __post_init__(self) -> None:
        if self.player_id <= 0:
            raise ValueError(f"player_id must be > 0, got {self.player_id}")
        if self.since.tzinfo is None:
            raise ValueError(
                f"AnticheatWindow.since must be timezone-aware (UTC), got naive {self.since!r}"
            )
        if self.organic_sum_cm < 0:
            raise ValueError(
                f"organic_sum_cm must be >= 0 (we sum only positive deltas), "
                f"got {self.organic_sum_cm}"
            )

    def remaining_cap_cm(self, *, cap_cm: int) -> int:
        """Сколько ещё organic-длины игрок может получить в окне до `cap_cm`.

        Возвращает 0, если лимит исчерпан или превышен. Никогда не отрицательное.
        Вызывается из `progression.add_length` для clamp-а: фактическая
        дельта = `min(requested_delta, remaining_cap_cm(cap_cm=cap))`.
        """
        if cap_cm < 0:
            raise ValueError(f"cap_cm must be >= 0, got {cap_cm}")
        return max(0, cap_cm - self.organic_sum_cm)

    def is_exceeded(self, *, cap_cm: int) -> bool:
        """`True`, если суммарный organic-прирост уже строго превысил `cap_cm`.

        Используется для trip-wire-логики: если после применения дельты
        окно вышло за `cap_cm`, ставим soft-ban (1.6.D). Это ловит обходы
        clamp-а — прямые `repo.save(player)` минуя `progression.add_length`.
        """
        if cap_cm < 0:
            raise ValueError(f"cap_cm must be >= 0, got {cap_cm}")
        return self.organic_sum_cm > cap_cm
