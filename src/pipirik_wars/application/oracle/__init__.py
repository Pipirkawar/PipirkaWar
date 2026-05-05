"""Use-cases предсказателя (Спринт 1.4.B)."""

from pipirik_wars.application.oracle.invoke import (
    InvokeOracle,
    OracleInvoked,
)
from pipirik_wars.application.oracle.templates import IOracleTemplateProvider

__all__ = [
    "IOracleTemplateProvider",
    "InvokeOracle",
    "OracleInvoked",
]
