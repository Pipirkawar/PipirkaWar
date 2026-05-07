"""Тесты порта `IDungeonRunRepository` (Спринт 3.1-A)."""

from __future__ import annotations

import inspect

from pipirik_wars.domain.dungeon.repositories import IDungeonRunRepository


class TestPort:
    def test_is_abc(self) -> None:
        try:
            IDungeonRunRepository()  # type: ignore[abstract]
        except TypeError:
            return
        msg = "IDungeonRunRepository must be an abstract class"
        raise AssertionError(msg)

    def test_has_required_methods(self) -> None:
        for name in ("add", "get_by_id", "get_active_by_player", "save"):
            method = getattr(IDungeonRunRepository, name, None)
            assert method is not None, f"missing method {name!r}"
            assert inspect.iscoroutinefunction(method), f"{name} must be async"

    def test_method_signatures_keyword_only(self) -> None:
        sig = inspect.signature(IDungeonRunRepository.get_by_id)
        params = list(sig.parameters.values())[1:]
        for param in params:
            assert param.kind == inspect.Parameter.KEYWORD_ONLY

        sig_active = inspect.signature(IDungeonRunRepository.get_active_by_player)
        active_params = list(sig_active.parameters.values())[1:]
        for param in active_params:
            assert param.kind == inspect.Parameter.KEYWORD_ONLY
