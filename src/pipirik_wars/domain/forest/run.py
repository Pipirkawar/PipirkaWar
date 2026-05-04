"""Сущность `ForestRun` — конкретный поход игрока в лес.

Поход — отдельная запись в `forest_runs`. Имеет ровно два состояния:
`IN_PROGRESS` (стартовали, ждём истечения cooldown-а) и `FINISHED`
(применили исход, выдали дроп). **Outcome ролим один раз — на старте**:
`branch` / `length_delta_cm` / `drop_*` записываются в БД сразу. Это
устойчиво к рестарту воркера (`FinishForestRun` ничего не катает,
а только применяет уже сохранённое) и к hot-reload-у баланса посреди
похода (новый баланс не должен ретроактивно менять исходы стартовавших
ранее запусков).

Сущность — `frozen=True, slots=True`. Мутации возвращают новый
экземпляр (см. `mark_finished`).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, replace
from datetime import datetime

from pipirik_wars.domain.forest.entities import (
    Drop,
    ForestRunOutcome,
    ItemDrop,
    NameDrop,
    NoDrop,
)


class ForestRunStatus(str, enum.Enum):
    """Жизненный цикл похода.

    `IN_PROGRESS` — лес идёт, активный лок взят, finish-job запланирован
    на `ends_at` (планировка job-а появится в Спринте 1.3.C).
    `FINISHED`    — `FinishForestRun` применил исход (длина начислена,
    дроп положен в инвентарь, лок снят, audit записан).
    """

    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


@dataclass(frozen=True, slots=True)
class ForestRun:
    """Поход в лес.

    Поля времени:
    - `started_at` — момент `/forest`.
    - `ends_at`    — момент, когда finish-job должен сработать
      (`started_at + cooldown_minutes`).
    - `finished_at`— момент применения исхода (Спринт 1.3.C). До тех пор
      `None`.

    Поля исхода (заранее сролленые `compute_forest_outcome`):
    - `branch_name` — `scarce | normal | abundant`.
    - `length_delta_cm` — фактический +Δ длины ∈ `[branch.min, branch.max]`.
    - `drop` — ADT (`NoDrop`/`ItemDrop`/`NameDrop`); реализация репозитория
      сериализует в три колонки `drop_kind / drop_item_id / drop_name`.
    """

    id: int | None
    player_id: int
    status: ForestRunStatus
    started_at: datetime
    ends_at: datetime
    branch_name: str
    length_delta_cm: int
    drop: Drop
    finished_at: datetime | None

    @classmethod
    def starting(
        cls,
        *,
        player_id: int,
        outcome: ForestRunOutcome,
        started_at: datetime,
        ends_at: datetime,
    ) -> ForestRun:
        """Свежая запись «вышел в лес» — `id=None`, `status=IN_PROGRESS`."""
        if ends_at <= started_at:
            raise ValueError("forest run ends_at must be strictly after started_at")
        return cls(
            id=None,
            player_id=player_id,
            status=ForestRunStatus.IN_PROGRESS,
            started_at=started_at,
            ends_at=ends_at,
            branch_name=outcome.branch.name,
            length_delta_cm=outcome.length_cm,
            drop=outcome.drop,
            finished_at=None,
        )

    @property
    def is_in_progress(self) -> bool:
        return self.status is ForestRunStatus.IN_PROGRESS

    def mark_finished(self, *, finished_at: datetime) -> ForestRun:
        """Перевести в `FINISHED`. Идемпотентность повторного финиша
        обеспечивает use-case (`FinishForestRun`, Спринт 1.3.C).
        """
        if self.status is ForestRunStatus.FINISHED:
            return self
        return replace(
            self,
            status=ForestRunStatus.FINISHED,
            finished_at=finished_at,
        )


__all__ = [
    "Drop",
    "ForestRun",
    "ForestRunStatus",
    "ItemDrop",
    "NameDrop",
    "NoDrop",
]
