"""Порты подсистемы TOTP-подтверждения (Спринт 2.5-A.3, ГДД §18.6).

`IAdminConfirmStore` — однократный TTL-store для ожидающих подтверждений.
   Реализация — `InMemoryAdminConfirmStore` (live-state бота, не БД:
   токены живут 60 секунд, переживать рестарт смысла не имеет).

`ITotpVerifier` — обёртка над библиотекой `pyotp`. Вынесена в порт,
   чтобы:

   * use-case-ы можно было тестировать без вычисления реального TOTP-кода
     (через `FakeTotpVerifier`);
   * можно было заменить алгоритм (например, на RFC 6238 с другим
     period-ом) без правки use-case-а.
"""

from __future__ import annotations

import abc

from pipirik_wars.domain.admin.confirm import AdminConfirmEntry


class IAdminConfirmStore(abc.ABC):
    """Однократный store ожидающих TOTP-подтверждений."""

    @abc.abstractmethod
    async def save(self, *, token: str, entry: AdminConfirmEntry) -> None:
        """Сохранить запись под токеном.

        Если запись с таким токеном уже есть — поведение store-specific
        (in-memory просто перезатирает; коллизия маловероятна, токен
        128-битный).
        """

    @abc.abstractmethod
    async def pop(self, *, token: str) -> AdminConfirmEntry | None:
        """Атомарно достать и удалить запись.

        Возвращает `None`, если токена нет (никогда не выдавался,
        уже отработал, либо удалён фоновой очисткой просроченных).
        """


class ITotpVerifier(abc.ABC):
    """Проверка 6-значного TOTP-кода против BASE32-секрета."""

    @abc.abstractmethod
    def verify(self, *, secret: str, code: str) -> bool:
        """`True`, если `code` валиден для `secret` в текущий момент времени.

        Реализации обычно допускают окно `±1` шаг (30 секунд) — это
        страхует от рассинхрона часов между сервером и устройством.
        """


__all__ = ["IAdminConfirmStore", "ITotpVerifier"]
