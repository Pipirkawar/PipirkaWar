"""Domain-сущности предсказателя (ГДД §11).

`OracleTemplate` — иммутабельная запись каталога предсказаний:
стабильный `id` (используется в audit-логе и для idempotency-проверок)
и текст с опциональным плейсхолдером `{user}`.

`OracleResult` — результат одной чистой функции `roll_oracle(...)`:
выбранный шаблон + прибавка длины. Никаких side-эффектов: запись в
`oracle_invocations`, начисление длины и audit пишет use-case
`InvokeOracle` (Спринт 1.4.B).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OracleTemplate:
    """Один шаблон предсказания из каталога.

    Поля:
    - `id` — стабильный машинный идентификатор (например,
      ``"oracle.ru.0007"``). Сохраняется в `oracle_invocations.template_id`,
      используется для аналитики «какие шаблоны выпадают чаще» и для
      audit-логов.
    - `text` — текст предсказания. Может содержать плейсхолдер
      ``{user}`` для подстановки имени/ника.
    """

    id: str
    text: str

    def __post_init__(self) -> None:
        if not self.id or self.id != self.id.strip():
            raise ValueError(f"OracleTemplate.id must be non-empty, got {self.id!r}")
        if not self.text or self.text != self.text.strip():
            raise ValueError(f"OracleTemplate.text must be non-empty, got {self.text!r}")


@dataclass(frozen=True, slots=True)
class OracleResult:
    """Результат розыгрыша одного `/oracle` (без I/O).

    `bonus_cm` — прибавка длины (∈ `[balance.oracle.bonus_min,
    balance.oracle.bonus_max]`). Use-case `InvokeOracle` применит её
    к `Player.length`.

    `template` — выбранный шаблон из каталога. Use-case передаёт `template.id`
    в репозиторий истории и в audit-payload, а `template.text` — handler-у
    для рендера ответа игроку.
    """

    bonus_cm: int
    template: OracleTemplate


__all__ = [
    "OracleResult",
    "OracleTemplate",
]
