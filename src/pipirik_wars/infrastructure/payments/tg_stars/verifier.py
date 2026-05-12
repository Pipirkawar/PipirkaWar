"""HMAC-SHA256-верификатор Telegram Stars `invoice_payload` (4.1-D, шаг D.8.b).

Реализация порта `ITgStarsPayloadVerifier` (domain) — фактическая
криптографическая проверка целостности и подлинности
`successful_payment.invoice_payload`. См. doctring порта в
`pipirik_wars.domain.monetization.ports` — там описана семантика
ошибок и контракт.

## Формат payload-а (`v1`)

Сериализуется при выпуске инвойса как ASCII-строка через `serialize(...)`:

```text
<version>:<pack_value>:<idempotency_seed>:<hmac_b64url>
```

* ``version`` — фиксированная константа `"v1"` (`TgStarsSettings.payload_version`).
* ``pack_value`` — машинный id `PaidRoulettePack` (`"single"` / `"pack_10"`),
  только `[A-Za-z0-9_-]`, без двоеточий.
* ``idempotency_seed`` — серверный 16–32-байтовый nonce из
  `[A-Za-z0-9_-]`. Обеспечивает уникальность HMAC-входа даже при
  одинаковых пользовательских параметрах.
* ``hmac_b64url`` — base64url-без-паддинга HMAC-SHA256 (43 символа)
  поверх контекста — см. `_hmac_input(...)` ниже.

Общая длина payload-а: `2 + 1 + 7 + 1 + 32 + 1 + 43 = 87` байт
максимум. Лимит Telegram — 128 байт.

## HMAC-вход

Контекст, поверх которого считается HMAC-SHA256, фиксирован и
известен **как на момент выпуска инвойса**, так и **на момент
`successful_payment`**:

```text
b"<version>\x00<pack_value>\x00<idempotency_seed>\x00<amount_native>\x00<currency_value>"
```

* ``provider_payment_id`` в HMAC **не входит** — он становится
  известен только после успешного списания (Telegram присылает
  `telegram_payment_charge_id` в `successful_payment`). Сверяется
  отдельной non-empty-проверкой как защита от replay-аттак с пустым
  charge_id.
* ``amount_native`` и ``currency`` — известны при выпуске инвойса
  (мы сами их задаём в `bot.send_invoice(prices=..., currency=...)`),
  они же приходят обратно в `successful_payment.total_amount /
  successful_payment.currency`. Несовпадение даёт `hmac_mismatch`.

Эта конструкция блокирует следующие классы атак:

* подмена `invoice_payload`-а (другой `pack_value` / `idempotency_seed`)
  — HMAC не совпадёт;
* подмена `amount_native` (другая сумма Stars) — HMAC не совпадёт;
* подмена `currency` — HMAC не совпадёт;
* replay через нулевой `provider_payment_id` — `bad_provider_id`.

## Сравнение HMAC

Используется `hmac.compare_digest(...)` — constant-time-сравнение,
устойчивое к timing-аттакам.

## Сериализация (для D.8.c)

Метод `serialize(*, pack_value, idempotency_seed, amount_native,
currency)` собирает payload по тому же контракту. Используется
в `bot.send_invoice(...)`-flow на шаге D.8.c — handler шага D.8.c
вызывает `serialize(...)` ровно один раз, потом
`verify(raw_payload, ...)` на `successful_payment`.
"""

from __future__ import annotations

import base64
import binascii
import hmac
from hashlib import sha256
from typing import Final

from pipirik_wars.domain.monetization.errors import InvalidStarsPayloadError
from pipirik_wars.domain.monetization.value_objects import Currency, StarsPayload
from pipirik_wars.infrastructure.payments.tg_stars.settings import TgStarsSettings

__all__ = ["HmacTgStarsPayloadVerifier"]


_HMAC_FIELD_SEPARATOR: Final[bytes] = b"\x00"
_PAYLOAD_PART_SEPARATOR: Final[str] = ":"
_HMAC_BYTES: Final[int] = 32  # sha256 digest size
_HMAC_B64URL_LEN: Final[int] = 43  # base64url(32 bytes) без паддинга


def _b64url_encode(raw: bytes) -> str:
    """Base64url-кодирование без паддинга (`=`)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(encoded: str) -> bytes:
    """Base64url-декодирование без паддинга. Бросает `ValueError` на мусоре."""
    # `urlsafe_b64decode` ожидает корректный паддинг — добавим его обратно.
    padded = encoded + "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


class HmacTgStarsPayloadVerifier:
    """HMAC-SHA256-реализация `ITgStarsPayloadVerifier` (4.1-D, шаг D.8.b).

    Конструктор принимает `TgStarsSettings`. Никаких I/O — все
    операции локальны (HMAC-SHA256 + base64url + split). Поэтому
    метод `verify(...)` — синхронный.

    Используется в:

    * `bot.handlers.roulette_paid::handle_send_invoice` (D.8.c) —
      вызовом `serialize(...)` собирает payload для
      `bot.send_invoice(payload=...)`.
    * `bot.handlers.roulette_paid::handle_successful_payment` (D.8.c) —
      вызовом `verify(...)` сверяет HMAC до `SpinPaidRoulette.execute(...)`.
    """

    def __init__(self, settings: TgStarsSettings) -> None:
        self._settings = settings
        # Кэшируем сырой байт-секрет один раз — `SecretStr.get_secret_value()`
        # не дешёвый при каждом вызове, но конструктор зовётся один раз
        # на старте процесса (через DI), поэтому это безопасно.
        self._secret_bytes = settings.secret.get_secret_value().encode("utf-8")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def serialize(
        self,
        *,
        pack_value: str,
        idempotency_seed: str,
        amount_native: int,
        currency: Currency,
    ) -> str:
        """Собрать подписанный `invoice_payload` для `bot.send_invoice(...)`.

        Возвращает строку формата
        ``<version>:<pack_value>:<idempotency_seed>:<hmac_b64url>``.
        Длина результата — не больше `settings.max_payload_bytes` (D.8.c).

        Вызывающая сторона (handler шага D.8.c) обязана:

        * передать тот же `idempotency_seed`, что будет позже
          использован для построения `IdempotencyKey` use-case-а;
        * передать `amount_native` и `currency`, которые фактически
          уйдут в `bot.send_invoice(prices=..., currency=...)`.

        Никаких проверок входа здесь нет (фактически — adapter-level
        primitive), потому что вход известен серверу и считается
        доверенным. VO-инварианты `StarsPayload` (формат
        `idempotency_seed`, etc.) проверяются на стороне `verify(...)`,
        а на стороне `serialize(...)` — на стороне caller-а.
        """
        digest = self._compute_hmac(
            pack_value=pack_value,
            idempotency_seed=idempotency_seed,
            amount_native=amount_native,
            currency=currency,
        )
        return _PAYLOAD_PART_SEPARATOR.join(
            [
                self._settings.payload_version,
                pack_value,
                idempotency_seed,
                _b64url_encode(digest),
            ],
        )

    def verify(
        self,
        *,
        raw_payload: str | None,
        provider_payment_id: str,
        amount_native: int,
        currency: Currency,
    ) -> StarsPayload:
        """Серверная HMAC-верификация `successful_payment.invoice_payload`.

        Контракт см. в docstring-е порта
        `pipirik_wars.domain.monetization.ports.ITgStarsPayloadVerifier`.

        Цепочка проверок (любая упавшая → `InvalidStarsPayloadError`):

        1. ``raw_payload`` не `None`, не пустой → иначе `reason="empty"`.
        2. ``len(raw_payload) <= settings.max_payload_bytes`` →
           иначе `reason="too_long"`.
        3. ``provider_payment_id`` не пустой → иначе
           `reason="bad_provider_id"`.
        4. Структура `"v:pack:seed:hmac"` (ровно 4 части) →
           иначе `reason="malformed"`.
        5. ``version == settings.payload_version`` →
           иначе `reason="bad_version"`.
        6. ``pack_value`` непустой (VO-инвариант) →
           иначе `reason="bad_pack"`.
        7. ``idempotency_seed`` валидный (VO-инвариант,
           `[A-Za-z0-9_-]{16,32}`) → иначе `reason="bad_seed"`.
        8. ``hmac_b64url`` декодируется в 32 байта →
           иначе `reason="bad_hmac"`.
        9. ``hmac.compare_digest(actual, expected)`` →
           иначе `reason="hmac_mismatch"`.
        """
        payload_len = len(raw_payload) if raw_payload is not None else 0

        if raw_payload is None or raw_payload == "":
            raise InvalidStarsPayloadError(reason="empty", payload_len=payload_len)

        if payload_len > self._settings.max_payload_bytes:
            raise InvalidStarsPayloadError(reason="too_long", payload_len=payload_len)

        if not provider_payment_id:
            raise InvalidStarsPayloadError(
                reason="bad_provider_id",
                payload_len=payload_len,
            )

        parts = raw_payload.split(_PAYLOAD_PART_SEPARATOR)
        if len(parts) != 4:
            raise InvalidStarsPayloadError(
                reason="malformed",
                payload_len=payload_len,
            )

        version, pack_value, idempotency_seed, hmac_b64 = parts

        if version != self._settings.payload_version:
            raise InvalidStarsPayloadError(
                reason="bad_version",
                payload_len=payload_len,
            )

        # Декодируем HMAC до VO-валидации `StarsPayload` — длинная
        # base64-строка с мусором не должна свалиться в `bad_seed`.
        try:
            actual_hmac = _b64url_decode(hmac_b64)
        except (ValueError, binascii.Error):
            raise InvalidStarsPayloadError(
                reason="bad_hmac",
                payload_len=payload_len,
            ) from None
        if len(actual_hmac) != _HMAC_BYTES:
            raise InvalidStarsPayloadError(
                reason="bad_hmac",
                payload_len=payload_len,
            )

        # VO-валидация формата `pack_value` / `idempotency_seed` —
        # перекладывает регексы / type-checks на domain-VO.
        try:
            payload_vo = StarsPayload(
                pack_value=pack_value,
                idempotency_seed=idempotency_seed,
            )
        except (TypeError, ValueError) as exc:
            # `pack_value` падает на пустой строке → "bad_pack".
            # `idempotency_seed` — на формате → "bad_seed".
            reason = "bad_pack" if "pack_value" in str(exc) else "bad_seed"
            raise InvalidStarsPayloadError(
                reason=reason,
                payload_len=payload_len,
            ) from None

        expected_hmac = self._compute_hmac(
            pack_value=pack_value,
            idempotency_seed=idempotency_seed,
            amount_native=amount_native,
            currency=currency,
        )

        # `hmac.compare_digest` — constant-time, устойчиво к timing.
        if not hmac.compare_digest(actual_hmac, expected_hmac):
            raise InvalidStarsPayloadError(
                reason="hmac_mismatch",
                payload_len=payload_len,
            )

        return payload_vo

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_hmac(
        self,
        *,
        pack_value: str,
        idempotency_seed: str,
        amount_native: int,
        currency: Currency,
    ) -> bytes:
        """Собрать HMAC-SHA256 поверх фиксированного контекста.

        Контекст — `version|pack_value|seed|amount|currency`,
        разделитель — `NUL`-байт (`\\x00`). `NUL` выбран потому, что
        ни одно из полей не может содержать `\\x00` в текстовом
        формате, и разделение однозначно.
        """
        context = _HMAC_FIELD_SEPARATOR.join(
            [
                self._settings.payload_version.encode("ascii"),
                pack_value.encode("ascii"),
                idempotency_seed.encode("ascii"),
                str(amount_native).encode("ascii"),
                currency.value.encode("ascii"),
            ],
        )
        return hmac.new(self._secret_bytes, context, sha256).digest()
