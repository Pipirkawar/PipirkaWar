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
    "FeeBufferAmount",
    "IdempotencyKey",
    "StarsAmount",
    "StarsPoolBalance",
    "TonAddress",
    "TonNanoAmount",
    "UsdtDecimalAmount",
    "UsdtJettonAddress",
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


@dataclass(frozen=True, slots=True)
class StarsPoolBalance:
    """Неотрицательный баланс пула Telegram Stars (ГДД §12.6, Спринт 4.1-B).

    Поле `value: int` — сколько ⋆ лежит в призовом пуле (`>= 0`,
    пустой пул — это ок). Почему отдельный VO, а не `StarsAmount`:
    `StarsAmount.value >= 1` по своей семантике (размер одного
    платежа — не может быть нулевым, Спринт 4.1-A); «cуммарный баланс
    пула» имеет другую семантику и разрешает ноль (свежезаведённый
    seed-row в `prize_pool_balance` — 0 ⋆).

    Frozen + slots → VO без identity, hashable, безопасно сравнивать `==`.
    """

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TypeError(
                f"StarsPoolBalance.value must be int, got {type(self.value).__name__}",
            )
        if self.value < 0:
            raise ValueError(
                f"StarsPoolBalance.value must be >= 0, got {self.value}",
            )


@dataclass(frozen=True, slots=True)
class TonNanoAmount:
    """Неотрицательное целое число нано-тонкоинов (ГДД §12.6, Спринт 4.1-B).

    Поле `value: int` — количество нано-тонкоинов (`>= 0`;
    `1 TON = 10**9 nano-TON`). Используется как баланс пула
    (`PrizePool.ton_nano`) и как входная сумма инкремента. На
    уровне БД хранится как `NUMERIC(38, 0)` без потери точности
    (Спринт 4.1-B миграция `0027`).

    Разрешает ноль (пустой пул / нулевой инкремент = noop). Для «размера
    платежа» — введём в 4.1-D свой VO с `>= 1`-инвариантом
    (аналогично `StarsAmount`).

    Frozen + slots → VO без identity, hashable, безопасно сравнивать `==`.
    """

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TypeError(
                f"TonNanoAmount.value must be int, got {type(self.value).__name__}",
            )
        if self.value < 0:
            raise ValueError(
                f"TonNanoAmount.value must be >= 0, got {self.value}",
            )


@dataclass(frozen=True, slots=True)
class UsdtDecimalAmount:
    """Неотрицательное целое число минор-юнит USDT (ГДД §12.6, Спринт 4.1-B).

    Поле `value: int` — количество минор-юнит USDT-jetton (`>= 0`;
    `1 USDT = 10**6` юнит при `decimals=6`). Используется как баланс
    пула (`PrizePool.usdt_decimal`) и как входная сумма инкремента.
    На уровне БД хранится как `NUMERIC(38, 0)` без потери точности.

    Разрешает ноль (пустой пул / нулевой инкремент = noop). Для «размера
    платежа» — введём в 4.1-D свой VO с `>= 1`-инвариантом.

    Frozen + slots → VO без identity, hashable, безопасно сравнивать `==`.
    """

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TypeError(
                f"UsdtDecimalAmount.value must be int, got {type(self.value).__name__}",
            )
        if self.value < 0:
            raise ValueError(
                f"UsdtDecimalAmount.value must be >= 0, got {self.value}",
            )


@dataclass(frozen=True, slots=True)
class FeeBufferAmount:
    """Неотрицательный целочисленный буфер комиссии лота (ГДД §12.6.3, Спринт 4.1-C).

    Поле `value: int` — заложенный в `PrizeLot` буфер на оплату сетевой
    комиссии (`>= 0`; для STARS-лотов обычно `0`, для TON / USDT —
    P95-аппроксимация газа за последние 7 дней, источник —
    `IFeeEstimator.estimate_fee(...)`).

    Семантика на уровне `PrizeLot`: invariant
    `amount_native > fee_buffer_native >= 0` гарантирует, что при
    выводе приза в 4.1-D на руки игроку остаётся `amount_native -
    fee_buffer_native >= 1`-натив-юнит после удержания комиссии.

    Frozen + slots → VO без identity, hashable, безопасно сравнивать `==`.
    """

    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TypeError(
                f"FeeBufferAmount.value must be int, got {type(self.value).__name__}",
            )
        if self.value < 0:
            raise ValueError(
                f"FeeBufferAmount.value must be >= 0, got {self.value}",
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


# ---------------------------------------------------------------------------
# TON-адреса  (ГДД §12.6.4, Спринт 4.1-D)
# ---------------------------------------------------------------------------

# User-friendly TON-address: 48 base64url characters (0:[32 bytes hex] raw
# form is 66 chars, but user-friendly is always 48 chars base64url, starting
# with 'E' / 'U' / '0' etc.).  We accept both raw (`0:hex{64}`) and
# user-friendly (48-char base64url) formats.
_TON_RAW_RE: re.Pattern[str] = re.compile(r"^-?[0-9]+:[0-9a-fA-F]{64}$")
_TON_FRIENDLY_RE: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_\-+/]{48}$")


@dataclass(frozen=True, slots=True)
class TonAddress:
    """Адрес TON-кошелька игрока (ГДД §12.6.4, Спринт 4.1-D).

    Принимает два формата:
    * Raw — ``<workchain>:<hex64>`` (e.g. ``0:abcdef...``);
    * User-friendly — 48-символьный base64url (e.g.
      ``EQD...``).

    Frozen + slots → VO без identity, hashable, безопасно сравнивать ``==``.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(
                f"TonAddress.value must be str, got {type(self.value).__name__}",
            )
        if not (_TON_RAW_RE.fullmatch(self.value) or _TON_FRIENDLY_RE.fullmatch(self.value)):
            raise ValueError(
                f"TonAddress.value must be a valid TON address "
                f"(raw or user-friendly), got {self.value!r}",
            )


@dataclass(frozen=True, slots=True)
class UsdtJettonAddress:
    """Адрес USDT-jetton-кошелька на сети TON (ГДД §12.6.4, Спринт 4.1-D).

    Формат идентичен ``TonAddress`` (USDT на TON — это jetton, кошелёк
    которого адресуется стандартным TON-адресом). Отдельный VO для
    type-safety: caller не может случайно подставить ``TonAddress``
    вместо ``UsdtJettonAddress`` (Liskov violation предотвращён).

    Frozen + slots → VO без identity, hashable, безопасно сравнивать ``==``.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(
                f"UsdtJettonAddress.value must be str, got {type(self.value).__name__}",
            )
        if not (_TON_RAW_RE.fullmatch(self.value) or _TON_FRIENDLY_RE.fullmatch(self.value)):
            raise ValueError(
                f"UsdtJettonAddress.value must be a valid TON address "
                f"(raw or user-friendly), got {self.value!r}",
            )
