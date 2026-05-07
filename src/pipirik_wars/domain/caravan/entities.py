"""Сущности домена «Караван» (Спринт 3.2-A, ГДД §9 «Караваны»).

`Caravan` — агрегат-«поход»: один караван от клана X в клан Y,
жизненный цикл `LOBBY → IN_BATTLE → FINISHED|CANCELLED`. Отличия
от PvE-походов:

- Двухфазный цикл — сначала **лобби 20 мин** (ГДД §9.3), потом
  **бой 60 мин** (ГДД §9.5). Каждая фаза имеет свой APScheduler-job
  (см. Спринт 3.2-B/C). У PvE — одна фаза.
- Многоучастниковый: один караван — N участников через ассоциативную
  таблицу `caravan_participants`.
- Outcome **не ролится на старте** (как у PvE). Бой каравана —
  honest симуляция в момент `FinishCaravanBattle` (детерминистично
  по `random_seed`-у, чтобы можно было воспроизвести при бале-аудите).
  В 3.2-A это поле — `random_seed: int` без логики; собственно
  resolve — Спринт 3.2-C.

`CaravanParticipant` — слабый агрегат «игрок ↔ караван ↔ роль».
Один игрок — одна роль на один караван. Контролируется БД-ограничением
+ `ICaravanRepository` (миграция в Спринте 3.2-B).

В 3.2-A здесь только структура и базовые конструкторы — мутаторы
(`mark_in_battle` / `mark_finished` / `mark_cancelled`) реализованы,
но use-case-ы для них приходят в 3.2-B/C.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from pipirik_wars.domain.caravan.value_objects import (
    CaravanContribution,
    CaravanRole,
    CaravanStatus,
)


@dataclass(frozen=True, slots=True)
class Caravan:
    """Караван — поход одного клана в другой.

    Поля времени:
    - `started_at` — момент `/caravan_create` (вход в `LOBBY`).
    - `lobby_ends_at` — `started_at + lobby_minutes` (по ГДД §9.3 — 20 мин).
      Когда APScheduler-job `caravan_lobby_close` срабатывает в
      `lobby_ends_at`, лобби переходит в `IN_BATTLE`.
    - `battle_ends_at` — момент завершения боя
      (`lobby_ends_at + battle_minutes`, по ГДД §9.5 — 60 мин).
      `caravan_battle_finish` job-а срабатывает в этот момент.
    - `finished_at` — момент применения исхода (Спринт 3.2-C).

    `random_seed` — детерминистичный seed для resolve-а боя в
    Спринте 3.2-C. Сохраняется на старте, чтобы при auditing-е
    можно было воспроизвести roll. На уровне 3.2-A — просто int.

    Ключевые поля состояния:
    - `sender_clan_id` — id клана, который высылает караван.
    - `receiver_clan_id` — id клана, в который везут.
    - `leader_player_id` — id создателя (всегда участник как
      `CARAVANEER` + `LEADER`-флаг в `CaravanParticipant`).

    Сущность frozen=True, slots=True. Мутации возвращают новый экземпляр.
    """

    id: int | None
    sender_clan_id: int
    receiver_clan_id: int
    leader_player_id: int
    status: CaravanStatus
    started_at: datetime
    lobby_ends_at: datetime
    battle_ends_at: datetime
    random_seed: int
    finished_at: datetime | None

    def __post_init__(self) -> None:
        if self.sender_clan_id == self.receiver_clan_id:
            raise ValueError(
                f"Caravan: sender_clan_id ({self.sender_clan_id}) and receiver_clan_id must differ"
            )
        if self.lobby_ends_at <= self.started_at:
            raise ValueError(
                f"Caravan: lobby_ends_at ({self.lobby_ends_at}) "
                f"must be strictly after started_at ({self.started_at})"
            )
        if self.battle_ends_at <= self.lobby_ends_at:
            raise ValueError(
                f"Caravan: battle_ends_at ({self.battle_ends_at}) "
                f"must be strictly after lobby_ends_at ({self.lobby_ends_at})"
            )

    @classmethod
    def starting(
        cls,
        *,
        sender_clan_id: int,
        receiver_clan_id: int,
        leader_player_id: int,
        started_at: datetime,
        lobby_ends_at: datetime,
        battle_ends_at: datetime,
        random_seed: int,
    ) -> Caravan:
        """Свежесозданный караван — `id=None`, `status=LOBBY`."""
        return cls(
            id=None,
            sender_clan_id=sender_clan_id,
            receiver_clan_id=receiver_clan_id,
            leader_player_id=leader_player_id,
            status=CaravanStatus.LOBBY,
            started_at=started_at,
            lobby_ends_at=lobby_ends_at,
            battle_ends_at=battle_ends_at,
            random_seed=random_seed,
            finished_at=None,
        )

    @property
    def is_in_lobby(self) -> bool:
        return self.status is CaravanStatus.LOBBY

    @property
    def is_in_battle(self) -> bool:
        return self.status is CaravanStatus.IN_BATTLE

    @property
    def is_terminal(self) -> bool:
        return self.status in (CaravanStatus.FINISHED, CaravanStatus.CANCELLED)

    def mark_in_battle(self) -> Caravan:
        """Перевести в `IN_BATTLE` (лобби закрыто, бой начинается).

        Идемпотентно при уже `IN_BATTLE`. Из `FINISHED`/`CANCELLED`
        бросает `ValueError`.
        """
        if self.status is CaravanStatus.IN_BATTLE:
            return self
        if self.is_terminal:
            raise ValueError(
                f"Caravan id={self.id} cannot transition LOBBY→IN_BATTLE "
                f"from terminal status {self.status.value!r}"
            )
        return replace(self, status=CaravanStatus.IN_BATTLE)

    def mark_finished(self, *, finished_at: datetime) -> Caravan:
        """Перевести в `FINISHED`. Идемпотентно при уже `FINISHED`.

        Из `LOBBY` / `CANCELLED` бросает `ValueError` — финиш
        возможен только из `IN_BATTLE`.
        """
        if self.status is CaravanStatus.FINISHED:
            return self
        if self.status is not CaravanStatus.IN_BATTLE:
            raise ValueError(
                f"Caravan id={self.id} cannot finish from status "
                f"{self.status.value!r} (must be IN_BATTLE)"
            )
        return replace(
            self,
            status=CaravanStatus.FINISHED,
            finished_at=finished_at,
        )

    def mark_cancelled(self, *, cancelled_at: datetime) -> Caravan:
        """Перевести в `CANCELLED`. Идемпотентно. Из `FINISHED` бросает.

        Возможно из `LOBBY` (лидер вышел / клан заморозили).
        Из `IN_BATTLE` тоже разрешено (например, клан-получатель
        заморозился посреди боя; но это редкий case — обычно бой идёт
        до конца). `finished_at` помечается `cancelled_at`-ом.
        """
        if self.status is CaravanStatus.CANCELLED:
            return self
        if self.status is CaravanStatus.FINISHED:
            raise ValueError(f"Caravan id={self.id} cannot cancel: already FINISHED")
        return replace(
            self,
            status=CaravanStatus.CANCELLED,
            finished_at=cancelled_at,
        )


@dataclass(frozen=True, slots=True)
class CaravanParticipant:
    """Запись об участии игрока в караване.

    Один игрок — один караван — одна роль. Уникальность
    `(caravan_id, player_id)` контролируется БД-ограничением
    (`UNIQUE INDEX` в миграции 3.2-B).

    `is_leader` — true только у создателя каравана. Если он есть,
    его `role` ВСЕГДА `CARAVANEER` (правило ГДД §9: лидер —
    караванщик). На уровне сущности это инвариант.

    `contribution` — есть только у `CARAVANEER`-ов (включая лидера).
    У `DEFENDER` и `RAIDER` `contribution=None`. На уровне сущности
    это инвариант.

    `joined_at` — момент вступления (для отладки и аналитики; в
    бой-механике не используется).
    """

    caravan_id: int
    player_id: int
    role: CaravanRole
    is_leader: bool
    contribution: CaravanContribution | None
    joined_at: datetime

    def __post_init__(self) -> None:
        if self.is_leader and self.role is not CaravanRole.CARAVANEER:
            raise ValueError(
                f"CaravanParticipant: leader must have role=CARAVANEER, got {self.role.value!r}"
            )
        if self.role is CaravanRole.CARAVANEER:
            if self.contribution is None:
                raise ValueError("CaravanParticipant: CARAVANEER must have contribution")
        elif self.contribution is not None:
            raise ValueError(
                f"CaravanParticipant: role {self.role.value!r} must NOT have contribution"
            )

    @classmethod
    def caravaneer(
        cls,
        *,
        caravan_id: int,
        player_id: int,
        contribution: CaravanContribution,
        is_leader: bool,
        joined_at: datetime,
    ) -> CaravanParticipant:
        """Свежий караванщик (или лидер). Обязательно с `contribution`."""
        return cls(
            caravan_id=caravan_id,
            player_id=player_id,
            role=CaravanRole.CARAVANEER,
            is_leader=is_leader,
            contribution=contribution,
            joined_at=joined_at,
        )

    @classmethod
    def defender(
        cls,
        *,
        caravan_id: int,
        player_id: int,
        joined_at: datetime,
    ) -> CaravanParticipant:
        """Свежий защитник. Без `contribution`, не лидер."""
        return cls(
            caravan_id=caravan_id,
            player_id=player_id,
            role=CaravanRole.DEFENDER,
            is_leader=False,
            contribution=None,
            joined_at=joined_at,
        )

    @classmethod
    def raider(
        cls,
        *,
        caravan_id: int,
        player_id: int,
        joined_at: datetime,
    ) -> CaravanParticipant:
        """Свежий рейдер. Без `contribution`, не лидер."""
        return cls(
            caravan_id=caravan_id,
            player_id=player_id,
            role=CaravanRole.RAIDER,
            is_leader=False,
            contribution=None,
            joined_at=joined_at,
        )


__all__ = [
    "Caravan",
    "CaravanParticipant",
]
