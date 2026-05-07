"""Сущность `DungeonRun` — поход игрока в данжон (ГДД §8, Спринт 3.1.2).

Поход — отдельная запись в `dungeon_runs` (таблица появится в 3.1-B).
Имеет ровно два состояния: `IN_PROGRESS` (стартовали, ждём истечения
cooldown-а) и `FINISHED` (применили исход — прибавили/списали длину,
выдали 0..3 предмета). **Outcome ролим один раз — на старте**:
`branch_name` / `length_delta_cm` (знаковая) / `drops` записываются в
БД сразу. Это устойчиво к рестарту воркера и к hot-reload-у баланса
посреди похода. Семантика идентична `MountainRun` и `ForestRun`.

Отличия от гор: больше слотов дропа (`balance.dungeon.drop.max_drops = 3`,
ГДД §8 «0–3 предмета»), больше разброс `min..max` для обоих знаков.

Сущность — `frozen=True, slots=True`. Мутации возвращают новый экземпляр
(см. `mark_finished`).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, replace
from datetime import datetime

from pipirik_wars.domain.pve.entities import PveItemDrop, PveRunOutcome


class DungeonRunStatus(str, enum.Enum):
    """Жизненный цикл похода в данжон.

    `IN_PROGRESS` — данжон идёт, активный лок взят, finish-job запланирован
    на `ends_at`.
    `FINISHED`    — `FinishDungeonRun` применил исход (длина изменена,
    дроп положен в инвентарь, лок снят, audit записан).
    """

    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


@dataclass(frozen=True, slots=True)
class DungeonRun:
    """Поход в данжон.

    Поля времени:
    - `started_at` — момент `/dungeon`.
    - `ends_at`    — момент, когда finish-job должен сработать
      (`started_at + cooldown_minutes`, 40–60 мин по ГДД §8).
    - `finished_at`— момент применения исхода (Спринт 3.1-B). До тех пор
      `None`.

    Поля исхода (заранее сролленые `pick_pve_outcome`):
    - `branch_name` — имя ветки из `balance.dungeon.outcomes`.
    - `length_delta_cm` — **знаковая** дельта длины: `gain` → `≥ 0`,
      `loss` → `≤ 0`.
    - `drops` — упорядоченный кортеж дропов (от 0 до 3 элементов).
    """

    id: int | None
    player_id: int
    status: DungeonRunStatus
    started_at: datetime
    ends_at: datetime
    branch_name: str
    length_delta_cm: int
    drops: tuple[PveItemDrop, ...]
    finished_at: datetime | None

    def __post_init__(self) -> None:
        if not self.branch_name:
            raise ValueError("DungeonRun.branch_name must be non-empty")

    @classmethod
    def starting(
        cls,
        *,
        player_id: int,
        outcome: PveRunOutcome,
        started_at: datetime,
        ends_at: datetime,
    ) -> DungeonRun:
        """Свежая запись «вошёл в данжон» — `id=None`, `status=IN_PROGRESS`."""
        if ends_at <= started_at:
            raise ValueError("dungeon run ends_at must be strictly after started_at")
        return cls(
            id=None,
            player_id=player_id,
            status=DungeonRunStatus.IN_PROGRESS,
            started_at=started_at,
            ends_at=ends_at,
            branch_name=outcome.branch.name,
            length_delta_cm=outcome.length_delta_cm,
            drops=outcome.drops,
            finished_at=None,
        )

    @property
    def is_in_progress(self) -> bool:
        return self.status is DungeonRunStatus.IN_PROGRESS

    def mark_finished(self, *, finished_at: datetime) -> DungeonRun:
        """Перевести в `FINISHED`. Идемпотентность повторного финиша
        обеспечивает use-case (`FinishDungeonRun`, Спринт 3.1-B).
        """
        if self.status is DungeonRunStatus.FINISHED:
            return self
        return replace(
            self,
            status=DungeonRunStatus.FINISHED,
            finished_at=finished_at,
        )


__all__ = [
    "DungeonRun",
    "DungeonRunStatus",
    "PveItemDrop",
]
