"""Unit-тесты domain-ошибок леса (Спринт 1.3.B / 1.3.C / 1.5.G)."""

from __future__ import annotations

from pipirik_wars.domain.forest import (
    AlreadyInForestError,
    ForestError,
    ForestLogNoTemplatesError,
    ForestRunNotFoundError,
)


class TestAlreadyInForestError:
    def test_carries_player_id_and_message(self) -> None:
        exc = AlreadyInForestError(player_id=42)
        assert exc.player_id == 42
        assert "42" in str(exc)
        assert isinstance(exc, ForestError)


class TestForestRunNotFoundError:
    def test_carries_run_id_and_message(self) -> None:
        exc = ForestRunNotFoundError(run_id=777)
        assert exc.run_id == 777
        assert "777" in str(exc)
        assert isinstance(exc, ForestError)


class TestForestLogNoTemplatesError:
    def test_is_forest_error(self) -> None:
        exc = ForestLogNoTemplatesError()
        assert isinstance(exc, ForestError)
        assert "empty" in str(exc).lower() or "no" in str(exc).lower()
