"""Unit-тесты иерархии ошибок `/oracle`."""

from __future__ import annotations

from datetime import date

from pipirik_wars.domain.oracle import (
    OracleAlreadyUsedTodayError,
    OracleError,
    OracleNoTemplatesError,
)


def test_already_used_today_inherits_oracle_error() -> None:
    exc = OracleAlreadyUsedTodayError(player_id=42, moscow_date=date(2026, 5, 5))
    assert isinstance(exc, OracleError)
    assert exc.player_id == 42
    assert exc.moscow_date == date(2026, 5, 5)
    assert "2026-05-05" in str(exc)


def test_no_templates_with_locale() -> None:
    exc = OracleNoTemplatesError(locale="fr")
    assert exc.locale == "fr"
    assert "fr" in str(exc)


def test_no_templates_without_locale() -> None:
    exc = OracleNoTemplatesError()
    assert exc.locale is None
