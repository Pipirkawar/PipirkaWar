"""Порт генерации новых TOTP-секретов (Спринт 2.5-D.6, ГДД §18.6.5).

Отделён от `ITotpVerifier` (Спринт 2.5-A.3) по ISP: верификация
кода нужна **внутри** transport-чувствительных опасных команд
(`/ban`, `/grant_*`, `/balance_set`, `/announce`), а генерация
свежего secret-а нужна только в `/admin_setup_totp` (Спринт 2.5-D.6).
Никакой дополнительной логики у use-case-а нет — это узкая обёртка
над `pyotp.random_base32()`, вынесенная в порт, чтобы:

- use-case `SetupAdminTotp` можно было тестировать с
  детерминированным `FakeTotpSecretGenerator` (предсказуемый secret
  → предсказуемая audit-запись);
- production-реализация могла менять источник энтропии (например,
  на `secrets.token_bytes(...)` + явный BASE32-кодинг) без правки
  use-case-а.
"""

from __future__ import annotations

import abc


class ITotpSecretGenerator(abc.ABC):
    """Генерация нового BASE32 TOTP-секрета.

    Реализации:

    - `infrastructure.admin.PyOtpTotpSecretGenerator` (production,
      `pyotp.random_base32()`);
    - `tests.fakes.FakeTotpSecretGenerator` (детерминированный
      возврат предзаданного secret-а для unit-тестов).

    Метод **не** асинхронный: генерация secret-а — чистый CPU-bound
    вызов криптографического PRNG, никаких I/O нет.
    """

    @abc.abstractmethod
    def generate(self) -> str:
        """Сгенерировать новый BASE32-секрет (RFC 4648, alphabet
        `A-Z2-7`). Возврат — непустая строка длиной не меньше 16
        символов; точная длина — на усмотрение реализации (`pyotp`
        возвращает 32 символа = 160 бит энтропии, как и рекомендует
        RFC 6238 для SHA-1)."""


__all__ = ["ITotpSecretGenerator"]
