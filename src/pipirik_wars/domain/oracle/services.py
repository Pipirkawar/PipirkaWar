"""Чистая функция розыгрыша одного `/oracle` (ГДД §11, ПД 1.4.4).

`roll_oracle(*, balance, random, templates)` — единственная точка, где
розыгрывается:

1. Прибавка длины — ``random.randint(balance.oracle.bonus_min,
   balance.oracle.bonus_max)`` (`distribution="uniform"`, ГДД §11).
2. Шаблон предсказания — `random.choice(templates)`.

Никаких side-эффектов: запись в `oracle_invocations` и начисление длины
выполняет use-case `InvokeOracle`.

Параметры передаются явно, без внутреннего состояния — функция тривиально
тестируется на детерминированном `FakeRandom(seed=...)` и валидном
`BalanceConfig`. Acceptance из ПД §3 / 1.4.4: на 10000 прогонов средняя
прибавка ≈ 10.5 см ±0.5 (см. `tests/unit/domain/oracle/test_services.py`).
"""

from __future__ import annotations

from collections.abc import Sequence

from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.oracle.entities import OracleResult, OracleTemplate
from pipirik_wars.domain.oracle.errors import OracleNoTemplatesError
from pipirik_wars.domain.shared.ports import IRandom


def roll_oracle(
    *,
    balance: BalanceConfig,
    random: IRandom,
    templates: Sequence[OracleTemplate],
) -> OracleResult:
    """Разыграть один `/oracle`. Без I/O.

    Pre: `templates` непуст (иначе `OracleNoTemplatesError` — это
    ошибка деплоя, а не баг геймплея). Прибавка длины всегда строго
    положительна, потому что `BalanceConfig.oracle` валидирует
    ``bonus_min > 0`` и ``bonus_min <= bonus_max``.
    """
    if not templates:
        raise OracleNoTemplatesError()

    bonus_cm = random.randint(balance.oracle.bonus_min, balance.oracle.bonus_max)
    template = random.choice(list(templates))
    return OracleResult(bonus_cm=bonus_cm, template=template)


__all__ = ["roll_oracle"]
