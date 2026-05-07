"""Сущность `MountainRun` — поход игрока в горы (ГДД §8, Спринт 3.1.1).

Поход — отдельная запись в `mountain_runs` (таблица появится в 3.1-B).
Имеет ровно два состояния: `IN_PROGRESS` (стартовали, ждём истечения
cooldown-а) и `FINISHED` (применили исход — прибавили/списали длину,
выдали дроп). **Outcome ролим один раз — на старте**: `branch_name` /
`length_delta_cm` (знаковая) / `drops` записываются в БД сразу. Это
устойчиво к рестарту воркера (`FinishMountainRun` ничего не катает,
а только применяет уже сохранённое) и к hot-reload-у баланса посреди
похода (новый баланс не должен ретроактивно менять исходы стартовавших
ранее запусков). Семантика идентична `ForestRun`, см.
`pipirik_wars.domain.forest.run`.

В отличие от леса:
- `length_delta_cm` **знаковая** (gain → положительная, loss → отрицательная);
- `drops` — упорядоченный кортеж от 0 до `balance.mountains.drop.max_drops`
  предметов (имена не дропаются — ГДД §2.5).

Сущность — `frozen=True, slots=True`. Мутации возвращают новый экземпляр
(см. `mark_finished`).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, replace
from datetime import datetime

from pipirik_wars.domain.pve.entities import PveItemDrop, PveRunOutcome


class MountainRunStatus(str, enum.Enum):
    """Жизненный цикл похода в горы.

    `IN_PROGRESS` — горы идут, активный лок взят, finish-job запланирован
    на `ends_at`.
    `FINISHED`    — `FinishMountainRun` применил исход (длина изменена,
    дроп положен в инвентарь, лок снят, audit записан).
    """

    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


@dataclass(frozen=True, slots=True)
class MountainRun:
    """Поход в горы.

    Поля времени:
    - `started_at` — момент `/mountains`.
    - `ends_at`    — момент, когда finish-job должен сработать
      (`started_at + cooldown_minutes`).
    - `finished_at`— момент применения исхода (Спринт 3.1-B). До тех пор
      `None`.

    Поля исхода (заранее сролленые `pick_pve_outcome`):
    - `branch_name` — имя ветки из `balance.mountains.outcomes`
      (`scarce_gain` / `normal_gain` / ... / `heavy_loss`).
    - `length_delta_cm` — **знаковая** дельта длины: `gain` → `≥ 0`,
      `loss` → `≤ 0`.
    - `drops` — упорядоченный кортеж дропов (от 0 до `max_drops` элементов).
    """

    id: int | None
    player_id: int
    status: MountainRunStatus
    started_at: datetime
    ends_at: datetime
    branch_name: str
    length_delta_cm: int
    drops: tuple[PveItemDrop, ...]
    finished_at: datetime | None

    def __post_init__(self) -> None:
        if not self.branch_name:
            raise ValueError("MountainRun.branch_name must be non-empty")

    @classmethod
    def starting(
        cls,
        *,
        player_id: int,
        outcome: PveRunOutcome,
        started_at: datetime,
        ends_at: datetime,
    ) -> MountainRun:
        """Свежая запись «вышел в горы» — `id=None`, `status=IN_PROGRESS`."""
        if ends_at <= started_at:
            raise ValueError("mountain run ends_at must be strictly after started_at")
        return cls(
            id=None,
            player_id=player_id,
            status=MountainRunStatus.IN_PROGRESS,
            started_at=started_at,
            ends_at=ends_at,
            branch_name=outcome.branch.name,
            length_delta_cm=outcome.length_delta_cm,
            drops=outcome.drops,
            finished_at=None,
        )

    @property
    def is_in_progress(self) -> bool:
        return self.status is MountainRunStatus.IN_PROGRESS

    def mark_finished(self, *, finished_at: datetime) -> MountainRun:
        """Перевести в `FINISHED`. Идемпотентность повторного финиша
        обеспечивает use-case (`FinishMountainRun`, Спринт 3.1-B).
        """
        if self.status is MountainRunStatus.FINISHED:
            return self
        return replace(
            self,
            status=MountainRunStatus.FINISHED,
            finished_at=finished_at,
        )


__all__ = [
    "MountainRun",
    "MountainRunStatus",
    "PveItemDrop",
]
