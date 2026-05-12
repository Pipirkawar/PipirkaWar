"""In-memory `ITgStarsPayloadVerifier` для тестов (Спринт 4.1-D, шаг D.8.c).

Используется в `tests/unit/bot/handlers/test_roulette_paid.py` для
изоляции handler-логики от реальной HMAC-криптографии: handler-у
важно только, что `verify(...)` либо возвращает `StarsPayload`, либо
бросает `InvalidStarsPayloadError`. Сам HMAC-крипто-контракт
покрывается отдельными тестами `HmacTgStarsPayloadVerifier` в
`tests/unit/infrastructure/payments/tg_stars/test_verifier.py`.

Контракт `FakeTgStarsPayloadVerifier`:

* `serialize(...)` — детерминированно собирает строку формата
  ``<version>:<pack_value>:<seed>:fake-hmac``. Используется в
  `handle_roulette_paid_buy`-тестах, чтобы assert-ить факт вызова
  `verifier.serialize(...)` и форму payload-а.
* `verify(...)` — по умолчанию возвращает `StarsPayload(pack_value,
  idempotency_seed)`, парся `raw_payload` так же, как реальный
  верификатор. Можно зарядить `error=InvalidStarsPayloadError(...)`,
  чтобы тестировать ветки отказа в `handle_successful_payment`.
"""

from __future__ import annotations

from pipirik_wars.domain.monetization.errors import InvalidStarsPayloadError
from pipirik_wars.domain.monetization.value_objects import Currency, StarsPayload


class FakeTgStarsPayloadVerifier:
    """Маркерная in-memory реализация `ITgStarsPayloadVerifier`.

    Args:
    * ``payload_version`` — версия, которую кладёт `serialize(...)` в
      первую часть payload-а. По умолчанию ``"v1"``.
    * ``serialize_calls`` — list, в который дописывается каждый вызов
      `serialize(...)` (в порядке вызовов). Тест может проверить
      `len(verifier.serialize_calls) == 1` и поля параметров.
    * ``verify_calls`` — аналогично для `verify(...)`.
    * ``error`` — если задан, `verify(...)` его поднимает вместо
      возврата `StarsPayload`. Используется для тестов отказа.
    """

    def __init__(
        self,
        *,
        payload_version: str = "v1",
        error: InvalidStarsPayloadError | None = None,
    ) -> None:
        self._payload_version = payload_version
        self._error = error
        self.serialize_calls: list[dict[str, object]] = []
        self.verify_calls: list[dict[str, object]] = []

    def serialize(
        self,
        *,
        pack_value: str,
        idempotency_seed: str,
        amount_native: int,
        currency: Currency,
    ) -> str:
        """Собрать детерминированный fake-payload `<v>:<pack>:<seed>:fake-hmac`."""
        self.serialize_calls.append(
            {
                "pack_value": pack_value,
                "idempotency_seed": idempotency_seed,
                "amount_native": amount_native,
                "currency": currency,
            },
        )
        return f"{self._payload_version}:{pack_value}:{idempotency_seed}:fake-hmac"

    def verify(
        self,
        *,
        raw_payload: str | None,
        provider_payment_id: str,
        amount_native: int,
        currency: Currency,
    ) -> StarsPayload:
        """Распарсить fake-payload в `StarsPayload`, либо бросить
        заряженный `error`.
        """
        self.verify_calls.append(
            {
                "raw_payload": raw_payload,
                "provider_payment_id": provider_payment_id,
                "amount_native": amount_native,
                "currency": currency,
            },
        )
        if self._error is not None:
            raise self._error
        # Парсим fake-формат `<v>:<pack>:<seed>:<hmac>` как реальный
        # верификатор — на любой mismatch это сигнал, что тест передал
        # не fake-payload, а что-то другое.
        if raw_payload is None or raw_payload == "":
            raise InvalidStarsPayloadError(reason="empty", payload_len=0)
        parts = raw_payload.split(":")
        if len(parts) != 4:
            raise InvalidStarsPayloadError(
                reason="malformed",
                payload_len=len(raw_payload),
            )
        _, pack_value, idempotency_seed, _ = parts
        return StarsPayload(
            pack_value=pack_value,
            idempotency_seed=idempotency_seed,
        )


__all__ = ["FakeTgStarsPayloadVerifier"]
