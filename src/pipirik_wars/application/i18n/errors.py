"""Ошибки `application.i18n` (Спринт 1.5.A)."""

from __future__ import annotations

from pipirik_wars.shared.errors import PipirikError


class I18nError(PipirikError):
    """Базовая ошибка локализации."""


class MessageKeyError(I18nError, KeyError):
    """Запрошен ключ, отсутствующий и в выбранной локали, и в fallback."""

    def __init__(self, key: str) -> None:
        super().__init__(f"message key {key!r} not found in any locale")
        self.key = key


__all__ = [
    "I18nError",
    "MessageKeyError",
]
