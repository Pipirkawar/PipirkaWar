"""Domain-ошибки леса.

Сейчас здесь только базовый `ForestError` для будущих use-case-ов
(Спринт 1.3.B/C) — например, `AlreadyInForestError` будет
наследоваться отсюда. На уровне 1.3.A (домен + расчёт исхода)
никаких дополнительных ошибок не возникает: catalog-инварианты
ловятся pydantic-валидатором `BalanceConfig`, а сам расчёт
`compute_forest_outcome` детерминирован относительно входов.
"""

from __future__ import annotations

from pipirik_wars.shared.errors import DomainError


class ForestError(DomainError):
    """Базовая ошибка леса. Конкретные наследники появятся в 1.3.B/C."""
