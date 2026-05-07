"""`pyotp`-реализация `ITotpSecretGenerator` (Спринт 2.5-D.6, ГДД §18.6.5).

`pyotp.random_base32()` использует `secrets.choice()` поверх алфавита
RFC 4648 (`A-Z2-7`) и возвращает 32-символьный BASE32-секрет — это
160 бит энтропии, как и рекомендует RFC 6238 для HMAC-SHA1.

Никаких I/O / блокирующих вызовов нет — это чистый CPU-bound вызов
криптографического PRNG, поэтому метод `generate()` синхронный
(см. порт `ITotpSecretGenerator`).
"""

from __future__ import annotations

import pyotp

from pipirik_wars.domain.admin import ITotpSecretGenerator


class PyOtpTotpSecretGenerator(ITotpSecretGenerator):
    """Production-генератор BASE32 TOTP-секретов поверх `pyotp`."""

    __slots__ = ()

    def generate(self) -> str:
        # `pyotp.random_base32()` типизирован как `Any` — приводим явно к `str`,
        # чтобы у mypy не было `no-any-return`.
        secret: str = str(pyotp.random_base32())
        return secret


__all__ = ["PyOtpTotpSecretGenerator"]
