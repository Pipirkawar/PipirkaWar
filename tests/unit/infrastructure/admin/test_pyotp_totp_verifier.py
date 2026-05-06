"""Unit-тесты `PyOtpTotpVerifier` (Спринт 2.5-A.3)."""

from __future__ import annotations

import datetime as dt

import pyotp
import pytest

from pipirik_wars.infrastructure.admin.pyotp_totp_verifier import PyOtpTotpVerifier


class TestPyOtpTotpVerifier:
    SECRET = "JBSWY3DPEHPK3PXP"  # стандартный пример из RFC 6238.

    def test_verifies_current_code(self) -> None:
        verifier = PyOtpTotpVerifier()
        code = pyotp.TOTP(self.SECRET).now()
        assert verifier.verify(secret=self.SECRET, code=code) is True

    def test_rejects_invalid_code(self) -> None:
        verifier = PyOtpTotpVerifier()
        # 6 нулей — заведомо не совпадает (вероятность совпадения 10^-6
        # для конкретного шага; но даже если совпало бы — тест
        # стабилен, потому что мы передаём другой код, отличающийся
        # на 1 символ).
        valid = pyotp.TOTP(self.SECRET).now()
        # Берём код, гарантированно отличающийся от текущего:
        # сдвигаем первую цифру.
        wrong = ("9" if valid[0] != "9" else "0") + valid[1:]
        assert verifier.verify(secret=self.SECRET, code=wrong) is False

    def test_rejects_garbage_code(self) -> None:
        verifier = PyOtpTotpVerifier()
        assert verifier.verify(secret=self.SECRET, code="not-a-number") is False
        assert verifier.verify(secret=self.SECRET, code="") is False

    def test_valid_window_default_accepts_one_step_drift(self) -> None:
        """Дефолтное `valid_window=1` должно принимать соседний шаг."""
        verifier = PyOtpTotpVerifier()
        totp = pyotp.TOTP(self.SECRET)
        now = dt.datetime.now(dt.UTC)
        # `counter_offset=-1` — OTP для предыдущего 30-секундного шага.
        previous = totp.at(now, counter_offset=-1)
        assert verifier.verify(secret=self.SECRET, code=previous) is True

    def test_strict_window_rejects_one_step_drift(self) -> None:
        """С `valid_window=0` соседний шаг отклоняется."""
        strict = PyOtpTotpVerifier(valid_window=0)
        totp = pyotp.TOTP(self.SECRET)
        now = dt.datetime.now(dt.UTC)
        previous = totp.at(now, counter_offset=-1)
        # На границе шага (первая секунда после смены кода) предыдущий
        # код всё ещё равен текущему — на таких граничных моментах
        # пропускаем прогон, чтобы тест был стабильным.
        if previous == totp.now():
            pytest.skip("step boundary collision — пропустим этот прогон")
        assert strict.verify(secret=self.SECRET, code=previous) is False
