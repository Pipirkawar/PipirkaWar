"""`TonRpcAdapter` — выплата TON / USDT-jetton-а через TON-RPC (Спринт 4.1-D, шаг D.5).

Реализует доменный порт `ITonPayoutAdapter` (см.
`domain/monetization/ports.py`). Принимает запрос на выплату
`(currency, amount_native, recipient_address)` и:

1. Маршрутизирует по валюте:
   * `TON_NANO` → сборка plain-TON-internal_message-а + публикация BOC-а;
   * `USDT_DECIMAL` → резолв jetton-wallet-а получателя через
     `JettonUsdtProvider` + сборка jetton-transfer-payload-а + публикация
     BOC-а;
   * `STARS` → `UnsupportedPayoutCurrencyError` (TG Stars-refund —
     через Bot API; отдельный адаптер появится позже).
2. Возвращает `PayoutResult(tx_hash, actual_fee_native)` —
   `actual_fee_native` берётся из `BocSendResult.actual_fee_native`.

**Что НЕ делает D.5:**
* Не подписывает BOC-message-ы — это задача отдельного порта
  `ITonMessageSigner` (будет в D.10 / D.7), здесь мы только формируем
  «логический payload» и доверяем sign-этап клиенту, который в D.5
  моделируется на FakeTonRpcClient.
* Не делает polling-а tx-hash-а: возвращает `tx_hash` сразу, caller
  (`ClaimPrize`-use-case, шаг D.2 уже на ветке) сам решает, ждать ли
  inclusion-а в блок (на D.5 это синхронный сценарий: считаем выплату
  успешной, как только TON-нода приняла BOC).
* Не подключается к composition root (`bot/main.py`) — на D.10.

Каждый вызов `payout(...)` идемпотентен только до сетевого слоя
(`ITonRpcClient.send_boc(...)`); если caller хочет защититься от
двойной публикации, он должен использовать `IIdempotencyKey` поверх
TonRpcAdapter (caller `ClaimPrize` уже так делает, см. D.2).
"""

from __future__ import annotations

from pipirik_wars.domain.monetization.ports import PayoutResult
from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.infrastructure.payments.ton_rpc.client import ITonRpcClient
from pipirik_wars.infrastructure.payments.ton_rpc.errors import (
    UnsupportedPayoutCurrencyError,
)
from pipirik_wars.infrastructure.payments.ton_rpc.jetton import JettonUsdtProvider
from pipirik_wars.infrastructure.payments.ton_rpc.settings import TonRpcSettings

__all__ = ["TonRpcAdapter"]


# Минимальный «прицеп» nano-TON, который мы крепим к jetton-transfer-у
# для оплаты forward-а получателю + газа jetton-wallet-контракта.
# Стандарт TEP-74 рекомендует ~0.05–0.1 TON; берём консервативный 0.05.
# Используется только при формировании логического payload-а — реальное
# списание идёт через `_settings.fallback_fee_buffer_ton_nano` /
# фактическую `BocSendResult.actual_fee_native`.
_JETTON_TRANSFER_FORWARD_TON_NANO = 50_000_000


class TonRpcAdapter:
    """Адаптер выплаты TON / USDT-jetton-а через TON-RPC.

    Реализует `ITonPayoutAdapter` (`pipirik_wars.domain.monetization.ports`):
    `payout(currency, amount_native, recipient_address) -> PayoutResult`.

    Зависимости (DI через конструктор; никакого глобального состояния):
    * `client: ITonRpcClient` — HTTP-обёртка TON-RPC (`client.py`).
    * `settings: TonRpcSettings` — конфигурация (адреса, sandbox, fallback).
    * `jetton_provider: JettonUsdtProvider` — резолв jetton-кошельков
      получателей + сборка jetton-transfer-payload-а.

    Stateless (`query_id`-counter тоже не держим — caller обязан
    передавать уникальный idempotency-id; на D.5 мы выводим `query_id`
    из последних 6 hex-символов `recipient_address`-а, что
    детерминировано и достаточно для unit-тестов; production `query_id`
    — отдельная задача D.10).

    Безопасно использовать как singleton.
    """

    __slots__ = ("_client", "_jetton_provider", "_settings")

    def __init__(
        self,
        *,
        client: ITonRpcClient,
        settings: TonRpcSettings,
        jetton_provider: JettonUsdtProvider,
    ) -> None:
        self._client = client
        self._settings = settings
        self._jetton_provider = jetton_provider

    async def payout(
        self,
        *,
        currency: Currency,
        amount_native: int,
        recipient_address: str,
    ) -> PayoutResult:
        """Выплатить приз получателю; возвращает `PayoutResult`.

        Параметры:
        * `currency` — валюта выплаты. `STARS` запрещён (см. docstring модуля).
        * `amount_native` — количество native-юнитов (`>= 1`).
        * `recipient_address` — TON-адрес получателя.

        Возвращает `PayoutResult(tx_hash, actual_fee_native)`.

        Поднимает:
        * `UnsupportedPayoutCurrencyError` — на `STARS` (TG Stars не
          через TON).
        * `ValueError` — на невалидных входных параметрах.
        * `TonRpcCallError` / `TonRpcTimeoutError` — пробрасываются из
          `client.send_boc(...)` / `client.run_get_method(...)`.
        * `JettonResolutionError` — при `USDT_DECIMAL`-выплате, если
          jetton-master отказался выдать jetton-wallet-а получателя.
        """
        if amount_native < 1:
            raise ValueError(
                f"TonRpcAdapter.payout: amount_native must be >= 1, got {amount_native}",
            )
        if not recipient_address:
            raise ValueError(
                "TonRpcAdapter.payout: recipient_address must be non-empty",
            )

        if currency is Currency.STARS:
            raise UnsupportedPayoutCurrencyError(
                "TonRpcAdapter handles TON_NANO / USDT_DECIMAL only; "
                "STARS payouts must go through the Telegram Bot API refund adapter.",
                currency=currency.value,
            )

        payout_wallet = self._settings.payout_wallet_address
        if not payout_wallet:
            # Fail-closed: невозможно выплатить без hot-wallet-а.
            raise ValueError(
                "TonRpcAdapter.payout: settings.payout_wallet_address is empty; "
                "configure TON_RPC_PAYOUT_WALLET_ADDRESS before issuing payouts.",
            )

        if currency is Currency.TON_NANO:
            signed_boc = self._build_ton_payout_boc(
                amount_native=amount_native,
                recipient_address=recipient_address,
                from_wallet=payout_wallet,
            )
        else:
            # USDT_DECIMAL — единственная оставшаяся валюта.
            destination_jetton_wallet = await self._jetton_provider.resolve_wallet(
                owner_address=recipient_address,
            )
            payload = self._jetton_provider.build_transfer_payload(
                query_id=self._derive_query_id(recipient_address),
                amount_native=amount_native,
                destination_jetton_wallet=destination_jetton_wallet,
                response_destination=payout_wallet,
                forward_ton_amount=_JETTON_TRANSFER_FORWARD_TON_NANO,
            )
            signed_boc = self._build_jetton_payout_boc(
                payload_op_code=payload.op_code,
                payload_query_id=payload.query_id,
                payload_amount_native=payload.amount_native,
                destination_jetton_wallet=payload.destination_jetton_wallet,
                response_destination=payload.response_destination,
                forward_ton_amount=payload.forward_ton_amount,
            )

        send_result = await self._client.send_boc(signed_boc_base64=signed_boc)
        return PayoutResult(
            tx_hash=send_result.tx_hash,
            actual_fee_native=send_result.actual_fee_native,
        )

    # ------------------------------------------------------------------
    # Internals.  «Сборка signed BOC» в D.5 — это **детерминированный
    # текстовый стаб**, описывающий payload в человекочитаемом виде.
    # Реальный TEP-74-compatible BOC-encoder + Ed25519-signature живёт в
    # `ITonMessageSigner`-имплементации (шаг D.10).  Стаб-формат
    # стабилен, чтобы caller (`ClaimPrize`) и тесты могли валидировать
    # «то, что мы отправили» без знаний криптографии.
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_query_id(recipient_address: str) -> int:
        """Детерминированный `query_id` из адреса получателя.

        Берём последние 8 hex-цифр sha-стиля-хэша адреса (мы не зовём
        hashlib, чтобы не платить за импорт — берём `hash`-int модуло
        2**32). Не подходит для криптографически-сильных идемпотент-id-ов,
        но достаточно стабилен для текущего стаба BOC-а.
        """
        # `hash` от строки в Python зависит от PYTHONHASHSEED; нам нужна
        # детерминированность между процессами, поэтому делаем сами:
        accumulator = 0
        for char in recipient_address:
            accumulator = (accumulator * 131 + ord(char)) & 0xFFFFFFFF
        return accumulator

    def _build_ton_payout_boc(
        self,
        *,
        amount_native: int,
        recipient_address: str,
        from_wallet: str,
    ) -> str:
        """Сериализовать TON-выплату в текстовый стаб-BOC.

        Формат стаба (детерминированный, человеко-читаемый): \
        ``ton-payout|from=<from_wallet>|to=<recipient>|amount=<n>``.

        В D.10 этот метод заменяется на реальный TEP-67-compatible
        BOC + Ed25519-подпись. Контракт `ITonRpcClient.send_boc(...)`
        не изменится — он принимает уже подписанный base64-BOC.
        """
        return f"ton-payout|from={from_wallet}|to={recipient_address}|amount={amount_native}"

    def _build_jetton_payout_boc(
        self,
        *,
        payload_op_code: int,
        payload_query_id: int,
        payload_amount_native: int,
        destination_jetton_wallet: str,
        response_destination: str,
        forward_ton_amount: int,
    ) -> str:
        """Сериализовать jetton-transfer в текстовый стаб-BOC.

        Формат стаба: \
        ``jetton-transfer|op=<op_code:#x>|query_id=<query_id>|\
amount=<amount_native>|dest=<destination_jetton_wallet>|\
resp=<response_destination>|fwd_ton=<forward_ton_amount>``.

        В D.10 — заменяется на реальный TEP-74-compatible BOC + подпись.
        """
        return (
            f"jetton-transfer|op={payload_op_code:#x}"
            f"|query_id={payload_query_id}"
            f"|amount={payload_amount_native}"
            f"|dest={destination_jetton_wallet}"
            f"|resp={response_destination}"
            f"|fwd_ton={forward_ton_amount}"
        )
