"""`pyotp`-реализация `ITotpVerifier` (Спринт 2.5-A.3).

`pyotp.TOTP.verify()` принимает `valid_window`: сколько 30-секундных
шагов считать валидными до и после текущего шага. Дефолт — 0
(только текущий шаг). Мы используем `1` — разрешаем ±30 секунд от
момента ввода. Это страхует от рассинхрона часов между сервером и
телефоном админа.

Алгоритм TOTP детерминирован — здесь нет случайности; единственная
зависимость — текущее время, которое `pyotp` берёт из `time.time()`.
"""

from __future__ import annotations

import pyotp

from pipirik_wars.domain.admin import ITotpVerifier


class PyOtpTotpVerifier(ITotpVerifier):
    """TOTP-верификация поверх `pyotp` (RFC 6238)."""

    __slots__ = ("_valid_window",)

    def __init__(self, *, valid_window: int = 1) -> None:
        self._valid_window = valid_window

    def verify(self, *, secret: str, code: str) -> bool:
        result = pyotp.TOTP(secret).verify(code, valid_window=self._valid_window)
        return bool(result)


__all__ = ["PyOtpTotpVerifier"]
