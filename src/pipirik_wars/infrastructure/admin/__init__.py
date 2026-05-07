"""Инфраструктурные адаптеры расширенного админ-интерфейса (Спринт 2.5-A / D.6).

* `InMemoryAdminConfirmStore` — однократный TTL-store ожидающих
  TOTP-подтверждений (живёт в памяти бота, переживать рестарт смысла
  не имеет: 60-секундный токен после рестарта всё равно бесполезен).
* `PyOtpTotpVerifier` — обёртка над `pyotp.TOTP.verify()`. Допускает
  расхождение часов на ±1 шаг (30 секунд).
* `PyOtpTotpSecretGenerator` (Спринт 2.5-D.6) — генератор свежих
  BASE32-секретов поверх `pyotp.random_base32()`. Используется
  `SetupAdminTotp` для self-service-выдачи нового TOTP-секрета.
"""

from pipirik_wars.infrastructure.admin.in_memory_confirm_store import (
    InMemoryAdminConfirmStore,
)
from pipirik_wars.infrastructure.admin.pyotp_totp_secret_generator import (
    PyOtpTotpSecretGenerator,
)
from pipirik_wars.infrastructure.admin.pyotp_totp_verifier import PyOtpTotpVerifier

__all__ = [
    "InMemoryAdminConfirmStore",
    "PyOtpTotpSecretGenerator",
    "PyOtpTotpVerifier",
]
