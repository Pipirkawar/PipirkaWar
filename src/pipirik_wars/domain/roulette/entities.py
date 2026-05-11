"""Доменные сущности рулетки (ГДД §12.4, Спринт 3.5-A/B).

`RouletteOutcomeKind` живёт в `domain/balance/config.py` (стабильные
машинные id попадают в `audit_log.target_id` Спринта 3.5-C). Этот
модуль ре-экспортирует его, чтобы доменный код мог импортировать
«одной строкой» из `domain.roulette` (по аналогии с
`domain/inventory/entities.py`, который ре-экспортирует `Slot` из
`domain/balance/config`).

`RouletteOutcome` — frozen-VO с распакованным результатом одного спина:
тип исхода + (для `LENGTH`) разыгранное количество сантиметров +
(для `CRYPTO_LOT`, Спринт 4.1-C) id выбранного `PrizeLot`-а. Для
остальных типов (`ITEM` / `SCROLL_REGULAR` / `SCROLL_BLESSED`)
каталог-зависимый резолв конкретного приза откладывается в use-case
(Спринт 3.5-C/D), picker возвращает только тип. Это сделано, чтобы
picker оставался чистой функцией от `(config, random, active_lots)`
без зависимостей от каталога предметов / пула скроллов / внешних
крипто-API.

`RouletteSpin` (Спринт 3.5-B) — иммутабельная запись одной прокрутки
для аудит-таблицы `roulette_spins`: `(player_id, occurred_at, outcome,
idempotency_key)`. Доменное представление одной строки event-log-а,
которое use-case `SpinFreeRoulette` (Спринт 3.5-C) кладёт через
`IRouletteSpinRepository.record(...)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Self

from pipirik_wars.domain.balance.config import RouletteOutcomeKind

__all__ = [
    "RouletteOutcome",
    "RouletteOutcomeKind",
    "RouletteSpin",
    "RouletteVariant",
]


class RouletteVariant(StrEnum):
    """Вариант рулетки (free / paid).

    Спринт 3.5: только `FREE`. Спринт 4.1-A: добавлен `PAID` под платную
    рулетку (Telegram Stars, ГДД §12.5). Стабильные машинные id —
    попадают в `audit_log.payload.roulette_variant` и в будущую колонку
    `roulette_spins.variant` (планируется в Спринте 4.1-B вместе с
    persistence-расширением). На 4.1-A `RouletteSpin`-сущность пока
    не несёт `variant`-поля — use-case `SpinPaidRoulette` (4.1-A)
    использует `RouletteVariant.PAID` только в audit-payload-е и в
    логах. Расширение `RouletteSpin` будет в 4.1-B миграцией с дефолтом
    `'free'` для исторических записей.

    Не менять без миграции.
    """

    FREE = "free"
    PAID = "paid"


@dataclass(frozen=True, slots=True)
class RouletteOutcome:
    """Результат одного спина рулетки (ГДД §12.4.2 / §12.5.2).

    Возвращается чистой функцией `pick_roulette_outcome(...)` /
    `pick_paid_outcome(...)`. Поля:

    * `kind` — тип исхода (`LENGTH` / `ITEM` / `SCROLL_REGULAR` /
      `SCROLL_BLESSED` / `CRYPTO_LOT`).
    * `length_cm` — для `kind == LENGTH` обязан быть положительным `int`
      (бакет уже выбран и `randint` уже разыгран); для остальных типов —
      `None`.
    * `lot_id` — для `kind == CRYPTO_LOT` обязан быть `int >= 1`
      (id выбранного `PrizeLot`-а из активного пула, Спринт 4.1-C);
      для остальных типов — `None`. Конкретный приз/скролл/предмет
      для других типов резолвится в use-case-е (Спринт 3.5-C/D).

    Инварианты `__post_init__`:
    - `kind == LENGTH` ⇒ `length_cm is not None and length_cm >= 1`
      and `lot_id is None`;
    - `kind == CRYPTO_LOT` ⇒ `lot_id is not None and lot_id >= 1`
      and `length_cm is None`;
    - иначе — оба поля `None`.

    Frozen + slots — VO без identity, безопасно сравнивать `==` / хэшировать.
    """

    kind: RouletteOutcomeKind
    length_cm: int | None = None
    lot_id: int | None = None

    def __post_init__(self) -> None:
        if self.kind is RouletteOutcomeKind.LENGTH:
            if self.length_cm is None:
                raise ValueError(
                    "RouletteOutcome(kind=LENGTH) requires length_cm to be set",
                )
            if self.length_cm < 1:
                raise ValueError(
                    f"RouletteOutcome(kind=LENGTH).length_cm must be >= 1, got {self.length_cm}",
                )
            if self.lot_id is not None:
                raise ValueError(
                    f"RouletteOutcome(kind=LENGTH) must have lot_id=None, got {self.lot_id}",
                )
        elif self.kind is RouletteOutcomeKind.CRYPTO_LOT:
            if self.lot_id is None:
                raise ValueError(
                    "RouletteOutcome(kind=CRYPTO_LOT) requires lot_id to be set",
                )
            if self.lot_id < 1:
                raise ValueError(
                    f"RouletteOutcome(kind=CRYPTO_LOT).lot_id must be >= 1, got {self.lot_id}",
                )
            if self.length_cm is not None:
                raise ValueError(
                    f"RouletteOutcome(kind=CRYPTO_LOT) must have length_cm=None, "
                    f"got {self.length_cm}",
                )
        else:
            if self.length_cm is not None:
                raise ValueError(
                    f"RouletteOutcome(kind={self.kind.value!r}) must have "
                    f"length_cm=None, got {self.length_cm}",
                )
            if self.lot_id is not None:
                raise ValueError(
                    f"RouletteOutcome(kind={self.kind.value!r}) must have "
                    f"lot_id=None, got {self.lot_id}",
                )

    @classmethod
    def crypto_lot(cls, *, lot_id: int) -> Self:
        """Фабрика `RouletteOutcome(kind=CRYPTO_LOT, lot_id=...)` (Спринт 4.1-C).

        Используется в picker-е (`domain.roulette.services`) и в callers-ах,
        которые хотят выразить «крипто-приз с конкретным лотом» одной
        строкой. Стандартный конструктор тоже разрешён, но эта фабрика
        строже типизирована: `lot_id: int` обязателен (а не
        `int | None`), что снимает один runtime-check у вызывающих.
        """
        return cls(kind=RouletteOutcomeKind.CRYPTO_LOT, lot_id=lot_id)


@dataclass(frozen=True, slots=True)
class RouletteSpin:
    """Иммутабельная запись одной прокрутки рулетки (ГДД §12.4, Спринт 3.5-B).

    Доменное представление строки `roulette_spins`-таблицы. Хранит
    «кто-когда-что» одной прокрутки + `idempotency_key` для надёжной
    дедупликации (двойной клик `[Прокрутить]`-кнопки → одна запись).

    Поля:

    * `player_id: int` — id игрока (FK → `users.id`).
    * `occurred_at: datetime` — момент прокрутки (TZ-aware).
    * `outcome: RouletteOutcome` — результат пика (`kind` + `length_cm`).
      `kind` денормализуется в ORM-колонку `kind VARCHAR(32)` для
      быстрых фильтров и audit-выгрузок. `length_cm` идёт в
      ORM-колонку `length_cm INT NULL` (только для `kind=LENGTH`).
    * `idempotency_key: str` — стабильный ключ дедупликации (в
      Спринте 3.5-C use-case будет генерировать вид
      `f"roulette_free:{player_id}:{tg_message_id}"`). На уровне БД
      хранится в `idempotency_key VARCHAR(128) UNIQUE` — повтор
      `record(...)`-вызова с тем же ключом приводит к no-op (см.
      `IRouletteSpinRepository.record`).

    Frozen + slots — VO без identity (на уровне домена две
    идентичные `RouletteSpin`-VO неотличимы; identity у строки в БД
    обеспечивается автоинкрементной `id`-колонкой ORM).
    """

    player_id: int
    occurred_at: datetime
    outcome: RouletteOutcome
    idempotency_key: str

    def __post_init__(self) -> None:
        if self.player_id <= 0:
            raise ValueError(
                f"RouletteSpin.player_id must be > 0, got {self.player_id}",
            )
        if self.occurred_at.tzinfo is None:
            raise ValueError(
                "RouletteSpin.occurred_at must be timezone-aware "
                "(naïve datetime would lose UTC offset on persistence)",
            )
        if not self.idempotency_key:
            raise ValueError(
                "RouletteSpin.idempotency_key must be a non-empty string",
            )

    @property
    def kind(self) -> RouletteOutcomeKind:
        """Удобный shortcut для `spin.outcome.kind` (используется ORM-репо)."""
        return self.outcome.kind

    @property
    def length_cm(self) -> int | None:
        """Удобный shortcut для `spin.outcome.length_cm` (используется ORM-репо)."""
        return self.outcome.length_cm
