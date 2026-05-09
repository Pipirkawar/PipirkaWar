"""Application-слой free-to-play рулетки (ГДД §12.4, Спринт 3.5-C).

Use-case `SpinFreeRoulette` оркестрирует одну прокрутку: гейты, списание
стоимости (100 см), pick исхода через `pick_roulette_outcome`-picker,
запись в event-log `roulette_spins` и audit. Для LENGTH-исхода —
дополнительный `ILengthGranter.grant(...)` по `ROULETTE_FREE_REWARD`.

Не-LENGTH исходы (`item` / `scroll_regular` / `scroll_blessed` / `crypto_lot`)
в Спринте 3.5-C остаются стабами на уровне audit-payload — их резолюция
(каталог предметов / пул скроллов / крипто-API) попадает в Спринт 3.5-D
и Phase 4 (см. `development_plan.md` §6.3.5).
"""

from __future__ import annotations

from pipirik_wars.application.roulette.spin_free_roulette import (
    SpinFreeRoulette,
    SpinFreeRouletteCommand,
    SpinResult,
)

__all__ = [
    "SpinFreeRoulette",
    "SpinFreeRouletteCommand",
    "SpinResult",
]
