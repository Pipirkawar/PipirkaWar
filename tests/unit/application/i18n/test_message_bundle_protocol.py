"""Структурный смок-тест для `IMessageBundle` (Спринт 1.5.A).

Проверяет, что протокол реально совместим с типичной реализацией —
ловим случаи, когда Protocol-сигнатура «уехала» от реализации.
"""

from __future__ import annotations

from typing import cast

from pipirik_wars.application.i18n import IMessageBundle, Locale, MessageKey


class _FakeBundle:
    """Минимальная in-memory реализация для проверки протокола."""

    def __init__(self, data: dict[tuple[str, str], str]) -> None:
        self._data = data

    def format(
        self,
        key: MessageKey,
        *,
        locale: Locale,
        **params: object,
    ) -> str:
        return self._data[(locale.code, key)].format(**params)


def test_fake_satisfies_protocol() -> None:
    fake = _FakeBundle({("ru", "hello"): "Привет {name}"})
    # mypy/runtime: Protocol.satisfies — структурно
    bundle: IMessageBundle = cast(IMessageBundle, fake)
    assert bundle.format(MessageKey("hello"), locale=Locale("ru"), name="Игрок") == "Привет Игрок"


def test_message_key_is_distinct_type_from_str() -> None:
    # NewType — у MessageKey есть собственный type-hint, но в runtime это str.
    key = MessageKey("greeting")
    assert isinstance(key, str)
    assert key == "greeting"
