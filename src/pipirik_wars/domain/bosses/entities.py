"""Сущности домена «Рейд-боссы» (Спринт 3.3-A, ГДД §10).

`BossFight` — агрегат-«рейд-бой»: один вызов босса (саммонер уровня 9+
кинул вызов случайному игроку из топ-30 по длине). Жизненный цикл
`LOBBY → IN_BATTLE → FINISHED|CANCELLED`. Отличия от каравана:

- **Один босс, много рейдеров.** В караване два клана + рейдеры извне
  (3 роли). Здесь — один босс (целевой top-30 игрок) + N рейдеров
  (все из общего пула). Босс хранится **на агрегате** (`boss_player_id`,
  `current_boss_length_cm`), не в `BossParticipant` — это упрощает
  модель и даёт O(1) доступ к HP босса в раунд-резолверe (3.3-C).
- **Глобальный кулдаун.** Кулдаун между рейдами — 4 часа на весь
  сервер (ГДД §10.1: «1 раз в 4 часа (глобальный)»). Не per-clan и
  не per-player — это распределённый lock. Реализация — Спринт 3.3-B.
- **Outcome не ролится на старте.** Бой — раундовая симуляция
  через `boss_round_resolution` (3.3-C); раунды записывают `current_round`
  и `current_boss_length_cm`. Финиш = `current_boss_length_cm <
  victory_threshold_cm` (рейдеры победили) или все рейдеры выбыли
  (босс победил). Идемпотентность — на уровне use-case через
  `was_already_finished`.

`BossParticipant` — слабый агрегат «рейдер ↔ рейд-бой». Босс в
`BossParticipant`-таблицу **не пишется** (он на `BossFight`). Один
саммонер per-bоят (помечен `is_summoner=True`); саммонер всегда
первый рейдер (вступает атомарно с `SummonBoss`-use-case-ом, 3.3-B).

В 3.3-A здесь только структура и базовые конструкторы — мутаторы
(`mark_in_battle` / `mark_finished` / `mark_cancelled` /
`with_boss_length` / `with_round_advanced`) реализованы, но
use-case-ы для них приходят в 3.3-B/C.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from pipirik_wars.domain.bosses.value_objects import BossFightStatus, BossKind


@dataclass(frozen=True, slots=True)
class BossFight:
    """Рейд-бой — агрегат «вызов босса».

    Поля времени:
    - `started_at` — момент `/boss`-вызова (вход в `LOBBY`).
    - `lobby_ends_at` — `started_at + lobby_minutes` (ГДД §10.3 —
      20 мин). Когда APScheduler-job `boss_lobby_close` срабатывает в
      `lobby_ends_at`, лобби переходит в `IN_BATTLE`.
    - `finished_at` — момент применения исхода (Спринт 3.3-C).

    Поля состояния боя:
    - `kind` — тип босса. На старте 3.3 — только `BossKind.RAID`.
    - `summoner_player_id` — id саммонера (lvl 9+, ≥20 см). Также
      первый рейдер (вступает атомарно).
    - `boss_player_id` — id босса (случайный из топ-30). Босс **не
      хранится в `BossParticipant`** — он на агрегате; HP босса —
      `current_boss_length_cm`.
    - `initial_boss_length_cm` — снапшот длины босса в момент призыва
      (для расчёта дроп-наград и audit-а). Не дренируется по раундам.
    - `current_boss_length_cm` — динамическое HP босса. Стартует
      равным `initial_boss_length_cm`, дренируется домен-сервисом
      `boss_round_resolution` (3.3-C). При `< victory_threshold_cm` —
      босс побеждён.
    - `current_round` — счётчик раундов. Стартует с `0` (до первого
      раунда). Инкрементируется в `RunBossRound` (3.3-C).
    - `random_seed` — детерминистичный seed для resolve-а раундов.
      Сохраняется на старте, чтобы при auditing-е можно было
      воспроизвести roll. На уровне 3.3-A — просто int.

    Сущность frozen=True, slots=True. Мутации возвращают новый экземпляр.
    """

    id: int | None
    kind: BossKind
    summoner_player_id: int
    boss_player_id: int
    status: BossFightStatus
    started_at: datetime
    lobby_ends_at: datetime
    finished_at: datetime | None
    random_seed: int
    initial_boss_length_cm: int
    current_boss_length_cm: int
    current_round: int

    def __post_init__(self) -> None:
        if self.summoner_player_id == self.boss_player_id:
            raise ValueError(
                f"BossFight: summoner_player_id ({self.summoner_player_id}) "
                f"and boss_player_id must differ"
            )
        if self.lobby_ends_at <= self.started_at:
            raise ValueError(
                f"BossFight: lobby_ends_at ({self.lobby_ends_at}) "
                f"must be strictly after started_at ({self.started_at})"
            )
        if self.initial_boss_length_cm <= 0:
            raise ValueError(
                f"BossFight: initial_boss_length_cm ({self.initial_boss_length_cm}) must be > 0"
            )
        if self.current_boss_length_cm < 0:
            raise ValueError(
                f"BossFight: current_boss_length_cm ({self.current_boss_length_cm}) must be >= 0"
            )
        if self.current_round < 0:
            raise ValueError(f"BossFight: current_round ({self.current_round}) must be >= 0")

    @classmethod
    def starting(
        cls,
        *,
        kind: BossKind,
        summoner_player_id: int,
        boss_player_id: int,
        started_at: datetime,
        lobby_ends_at: datetime,
        random_seed: int,
        initial_boss_length_cm: int,
    ) -> BossFight:
        """Свежесозданный рейд-бой — `id=None`, `status=LOBBY`,
        `current_boss_length_cm=initial_boss_length_cm`, `current_round=0`."""
        return cls(
            id=None,
            kind=kind,
            summoner_player_id=summoner_player_id,
            boss_player_id=boss_player_id,
            status=BossFightStatus.LOBBY,
            started_at=started_at,
            lobby_ends_at=lobby_ends_at,
            finished_at=None,
            random_seed=random_seed,
            initial_boss_length_cm=initial_boss_length_cm,
            current_boss_length_cm=initial_boss_length_cm,
            current_round=0,
        )

    @property
    def is_in_lobby(self) -> bool:
        return self.status is BossFightStatus.LOBBY

    @property
    def is_in_battle(self) -> bool:
        return self.status is BossFightStatus.IN_BATTLE

    @property
    def is_terminal(self) -> bool:
        return self.status in (BossFightStatus.FINISHED, BossFightStatus.CANCELLED)

    def mark_in_battle(self) -> BossFight:
        """Перевести в `IN_BATTLE` (лобби закрыто, бой начинается).

        Идемпотентно при уже `IN_BATTLE`. Из `FINISHED`/`CANCELLED`
        бросает `ValueError`.
        """
        if self.status is BossFightStatus.IN_BATTLE:
            return self
        if self.is_terminal:
            raise ValueError(
                f"BossFight id={self.id} cannot transition LOBBY→IN_BATTLE "
                f"from terminal status {self.status.value!r}"
            )
        return replace(self, status=BossFightStatus.IN_BATTLE)

    def mark_finished(self, *, finished_at: datetime) -> BossFight:
        """Перевести в `FINISHED`. Идемпотентно при уже `FINISHED`.

        Из `LOBBY` / `CANCELLED` бросает `ValueError` — финиш возможен
        только из `IN_BATTLE`.
        """
        if self.status is BossFightStatus.FINISHED:
            return self
        if self.status is not BossFightStatus.IN_BATTLE:
            raise ValueError(
                f"BossFight id={self.id} cannot finish from status "
                f"{self.status.value!r} (must be IN_BATTLE)"
            )
        return replace(
            self,
            status=BossFightStatus.FINISHED,
            finished_at=finished_at,
        )

    def mark_cancelled(self, *, cancelled_at: datetime) -> BossFight:
        """Перевести в `CANCELLED`. Идемпотентно. Из `FINISHED` бросает.

        Возможно из `LOBBY` (саммонер вышел / клан саммонера заморозили /
        никто не пришёл) и из `IN_BATTLE` (редкий case — админ-вмешательство).
        `finished_at` помечается `cancelled_at`-ом.
        """
        if self.status is BossFightStatus.CANCELLED:
            return self
        if self.status is BossFightStatus.FINISHED:
            raise ValueError(f"BossFight id={self.id} cannot cancel: already FINISHED")
        return replace(
            self,
            status=BossFightStatus.CANCELLED,
            finished_at=cancelled_at,
        )

    def with_boss_length(self, *, length_cm: int) -> BossFight:
        """Обновить `current_boss_length_cm` после раунда (Спринт 3.3-C).

        `length_cm` clamp-ится снизу до 0 (HP босса не уходит в минус).
        Используется `boss_round_resolution`-сервисом, когда блокированная
        атака рейдера «забирает у босса» некоторую длину.
        """
        if length_cm < 0:
            raise ValueError(f"BossFight.with_boss_length: length_cm ({length_cm}) must be >= 0")
        return replace(self, current_boss_length_cm=length_cm)

    def with_round_advanced(self) -> BossFight:
        """Инкрементировать `current_round` (Спринт 3.3-C).

        Используется `RunBossRound`-use-case-ом после применения
        раунд-резолюции. Идемпотентность — на уровне use-case (через
        отдельный `idempotency_key` per-(boss_fight_id, round_number)).
        """
        return replace(self, current_round=self.current_round + 1)


@dataclass(frozen=True, slots=True)
class BossParticipant:
    """Запись об участии рейдера в рейд-бою.

    Один игрок — один рейд — одна запись. Уникальность
    `(boss_fight_id, player_id)` контролируется БД-ограничением
    (`UNIQUE INDEX` в миграции 3.3-B).

    `is_summoner` — `True` ровно у одного из рейдеров (саммонер,
    тот, кто кинул вызов с lvl 9+). На уровне сущности это инвариант:
    все рейдеры в одном бое — все могут иметь `is_summoner=False`,
    кроме одного. БД-ограничение `UNIQUE` на partial-WHERE (`is_summoner`)
    гарантирует только-один-саммонер.

    `length_at_join_cm` — снапшот длины рейдера в момент вступления.
    Используется `FinishBossFight`-use-case-ом (3.3-C) для расчёта
    потерь длины («босс забирает длину рейдеров») — клампится снизу
    до `min_length_after_loss_cm` (см. ГДД §3.1, тоже 20 см).

    `joined_at` — момент вступления (для упорядочивания UI и аналитики).

    Босс в `BossParticipant`-таблице **не хранится** — он на
    `BossFight.boss_player_id`. Это упрощает модель и даёт O(1)
    доступ к HP босса в раунд-резолверe (3.3-C).
    """

    boss_fight_id: int
    player_id: int
    is_summoner: bool
    length_at_join_cm: int
    joined_at: datetime

    def __post_init__(self) -> None:
        if self.length_at_join_cm <= 0:
            raise ValueError(
                f"BossParticipant: length_at_join_cm ({self.length_at_join_cm}) must be > 0"
            )

    @classmethod
    def raider(
        cls,
        *,
        boss_fight_id: int,
        player_id: int,
        is_summoner: bool,
        length_at_join_cm: int,
        joined_at: datetime,
    ) -> BossParticipant:
        """Свежий рейдер. `is_summoner=True` — для саммонера-инициатора."""
        return cls(
            boss_fight_id=boss_fight_id,
            player_id=player_id,
            is_summoner=is_summoner,
            length_at_join_cm=length_at_join_cm,
            joined_at=joined_at,
        )


__all__ = [
    "BossFight",
    "BossParticipant",
]
