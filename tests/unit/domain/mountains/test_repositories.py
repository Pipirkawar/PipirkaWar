"""Тесты порта `IMountainRunRepository` (Спринт 3.1-A).

Цель — зафиксировать сигнатуру протокола: реализации (in-memory fake
+ SqlAlchemy в 3.1-B) обязаны быть совместимы.
"""

from __future__ import annotations

import inspect

from pipirik_wars.domain.mountains.repositories import IMountainRunRepository


class TestPort:
    def test_is_abc(self) -> None:
        # Прямая инстанциация должна падать, как у любого ABC с
        # абстрактными методами.
        try:
            IMountainRunRepository()  # type: ignore[abstract]
        except TypeError:
            return
        msg = "IMountainRunRepository must be an abstract class"
        raise AssertionError(msg)

    def test_has_required_methods(self) -> None:
        for name in ("add", "get_by_id", "get_active_by_player", "save"):
            method = getattr(IMountainRunRepository, name, None)
            assert method is not None, f"missing method {name!r}"
            # Все методы — async (Coroutine-возвращающие).
            assert inspect.iscoroutinefunction(method), f"{name} must be async"

    def test_method_signatures_keyword_only(self) -> None:
        # `get_by_id` / `get_active_by_player` / `save` принимают
        # keyword-аргументы (защита от позиционной путаницы).
        sig = inspect.signature(IMountainRunRepository.get_by_id)
        params = list(sig.parameters.values())[1:]  # drop self
        for param in params:
            assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
                f"{param.name} must be KEYWORD_ONLY"
            )

        sig_active = inspect.signature(IMountainRunRepository.get_active_by_player)
        active_params = list(sig_active.parameters.values())[1:]
        for param in active_params:
            assert param.kind == inspect.Parameter.KEYWORD_ONLY
