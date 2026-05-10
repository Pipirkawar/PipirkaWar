"""Value-объекты доменного слоя монетизации (ГДД §12.5–§12.6, Спринт 4.1-A).

Иммутабельные VO:

* `Currency` (StrEnum) — три валюты приёма платежей: Telegram Stars
  (`STARS`), TON (`TON_NANO` — нано-тонкоины как `int`), USDT
  (`USDT_DECIMAL` — `Decimal`-минор-юниты, jetton-decimals=6 на TON).
  `value` — машинный id, попадает в `payments.currency` и в
  `audit_log.payload.currency` (Спринт 4.1-A migration `0026`). Не менять
  без миграции.
* `StarsAmount(int, > 0)` — вокруг положительного `int` (TG Stars
  всегда целое количество ⭐, дробных нет; ГДД §12.5.1: `1⭐` /
  `9⭐`-pack). Frozen-VO; защищает от случайного «0 ⭐» / «-1 ⭐»
  на доменной границе и гарантирует сохранность инварианта при
  сериализации в `payments.amount_native`.
* `IdempotencyKey` — строковый VO с валидируемым форматом
  `[A-Za-z0-9_-]{1,64}` (защита от инъекций в SQL и от чрезмерно
  длинных ключей в `UNIQUE`-индексе `payments.idempotency_key`).
  Конкретный формат генерации ключа — на стороне application-слоя
  (use-case `SpinPaidRoulette` использует `"paid_roulette:{player}:
  {tg_payment_charge_id}"`), но валидация формата живёт здесь, ближе
  к VO, чтобы invariant держался независимо от вызывающего кода.

Все VO — `frozen=True, slots=True` (см. конвенцию
`domain/roulette/entities.py::RouletteOutcome`). Frozen + slots даёт
нам неизменяемость, hashability и нулевой `__dict__`-overhead;
сравнение по полям — «два одинаковых ключа == друг другу».
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "Currency",
    "IdempotencyKey",
    "StarsAmount",
]


class Currency(StrEnum):
    """Поддерживаемые валюты приёма платежей (ГДД §12.5.1, §12.6).

    `STARS` — Telegram Stars, целочисленные единицы (`int >= 1`).
    `TON_NANO` — TON, нано-тонкоины (`int >= 1`; 1 TON = 10**9 nano-TON).
    `USDT_DECIMAL` — USDT через TON-сеть (jetton-decimals=6;
    1 USDT = 10**6 минор-юнит). На уровне БД хранится как
    `NUMERIC(38, 0)` без потери точности (Спринт 4.1-A migration `0026`).

    Стабильные машинные id, попадают в `payments.currency` (CHECK-constraint
    `payments_currency_whitelist`) и в `audit_log.payload.currency`. Не
    менять без миграции.
    """

    STARS = "stars"
    TON_NANO = "ton_nano"
    USDT_DECIMAL = "usdt_decimal"


@dataclass(frozen=True, slots=True)
class StarsAmount:
    """Положительное целое количество Telegram Stars (ГДД §12.5.1).

    Поле `value: int` — количество ⭐ (`>= 1`). VO защищает от случайных
    нулевых / отрицательных значений на доменной границе и гарантирует
    инвариант при сериализации в `payments.amount_native: NUMERIC(38, 0)`.

    Использование: `StarsAmount(1)` (single spin), `StarsAmount(9)`
    (10-pack). Любое значение `<= 0` → `ValueError` в `__post_init__`.

    Frozen + slots → VO без identity, hashable, безопасно сравнивать `==`.
    """

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TypeError(
                f"StarsAmount.value must be int, got {type(self.value).__name__}",
            )
        if self.value < 1:
            raise ValueError(
                f"StarsAmount.value must be >= 1, got {self.value}",
            )


_IDEMPOTENCY_KEY_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_\-:]{1,64}$")


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    """Идемпотентный ключ платежа (ГДД §12.5.1, антифрод 4.1.4).

    Поле `value: str` — `[A-Za-z0-9_\\-:]{1,64}`. Запрещает SQL-инъекции
    и слишком длинные ключи в `UNIQUE (player_id, idempotency_key)`-
    индексе `payments`-таблицы (Спринт 4.1-A migration `0026`).

    Двоеточие `:` в whitelist-е оставлено намеренно: application-слой
    генерирует ключи вида `"paid_roulette:{player_id}:{tg_payment_charge_id}"`
    (use-case `SpinPaidRoulette`).

    Use-case `SpinPaidRoulette` (Спринт 4.1-A) при повторном вызове с
    тем же `IdempotencyKey` возвращает существующий receipt без
    повторного списания (антифрод; ГДД §12.5.1, плана 4.1.4). Если ключ
    есть, но с другой суммой / игроком — `IdempotencyConflictError`
    (см. `errors.py`).

    Frozen + slots → VO без identity, hashable, безопасно сравнивать `==`.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(
                f"IdempotencyKey.value must be str, got {type(self.value).__name__}",
            )
        if not _IDEMPOTENCY_KEY_RE.fullmatch(self.value):
            raise ValueError(
                f"IdempotencyKey.value must match [A-Za-z0-9_-:]{{1,64}}, got {self.value!r}",
            )
