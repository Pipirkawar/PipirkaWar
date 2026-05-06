"""Стаб `ITotpVerifier` для unit-тестов composition-root-а и handler-ов."""

from __future__ import annotations

from pipirik_wars.domain.admin import ITotpVerifier


class FakeTotpVerifier(ITotpVerifier):
    """Возвращает заранее заданный bool, считает вызовы `verify()`."""

    __slots__ = ("calls", "result")

    def __init__(self, *, result: bool = True) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def verify(self, *, secret: str, code: str) -> bool:
        self.calls.append((secret, code))
        return self.result


__all__ = ["FakeTotpVerifier"]
