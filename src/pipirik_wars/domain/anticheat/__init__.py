"""Anti-cheat hardcap — domain (ГДД §3.3 / Спринт 1.6).

Содержит чистую rolling-агрегацию (`AnticheatWindow`) и порт репозитория
(`IAnticheatRepository.sum_organic_in_window`). Реализация репозитория —
в `infrastructure/db/repositories/anticheat.py`. Use-case
`progression.add_length` (Спринт 1.6.D) сам читает `balance.yaml`
и решает, клампить или пускать дельту насквозь.
"""

from pipirik_wars.domain.anticheat.entities import AnticheatWindow
from pipirik_wars.domain.anticheat.repositories import IAnticheatRepository

__all__ = [
    "AnticheatWindow",
    "IAnticheatRepository",
]
