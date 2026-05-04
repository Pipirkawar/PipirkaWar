"""Тесты иерархии исключений."""

from __future__ import annotations

import pytest

from pipirik_wars.shared import (
    ConcurrencyError,
    ConfigError,
    DomainError,
    IntegrityError,
    PipirikError,
)


@pytest.mark.parametrize(
    "exc_cls",
    [DomainError, ConcurrencyError, IntegrityError, ConfigError],
)
def test_all_errors_inherit_from_pipirik_error(
    exc_cls: type[PipirikError],
) -> None:
    assert issubclass(exc_cls, PipirikError)
    assert issubclass(exc_cls, Exception)


def test_pipirik_error_is_exception() -> None:
    assert issubclass(PipirikError, Exception)


def test_can_be_raised_and_caught() -> None:
    with pytest.raises(PipirikError):
        raise DomainError("rule violated")
