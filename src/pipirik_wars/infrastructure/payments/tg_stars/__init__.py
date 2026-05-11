"""Telegram Stars `invoice_payload` HMAC-верификатор (Спринт 4.1-D, шаг D.8.b).

Реализация порта `ITgStarsPayloadVerifier` (domain) поверх HMAC-SHA256.
Используется как защита целостности `invoice_payload`-а между
`bot.send_invoice(...)` и `successful_payment`-handler-ом — без неё
злоумышленник мог бы подменить `pack_value` или `amount_native`
между шагами, провести «дёшево, спин получи дорогой».

Композиционный root (`bot/main.py`, шаг D.10.c) делает
`TgStarsSettings()` (env `TG_STARS_*`) + `HmacTgStarsPayloadVerifier(settings)`
и пробрасывает в handler шага D.8.c. До D.8.c этот класс в проде
не используется — D.8.b — отдельный шаг с unit-тестами на golden HMAC.

Логически разнесено по подмодулям:

* `settings` — `TgStarsSettings` (`pydantic-settings`, prefix `TG_STARS_`),
  поле `secret: SecretStr` обязательно.
* `verifier` — `HmacTgStarsPayloadVerifier` (`ITgStarsPayloadVerifier`)
  с метод-парой `serialize(...)` / `verify(...)`.
"""

from pipirik_wars.infrastructure.payments.tg_stars.settings import TgStarsSettings
from pipirik_wars.infrastructure.payments.tg_stars.verifier import (
    HmacTgStarsPayloadVerifier,
)

__all__ = [
    "HmacTgStarsPayloadVerifier",
    "TgStarsSettings",
]
