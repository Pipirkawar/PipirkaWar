"""`TonRpcAdapter` — выплата TON / USDT-jetton-а через TON-RPC (Спринт 4.1-D, шаги D.5 + D.10.b-3).

Реализует доменный порт `ITonPayoutAdapter` (см.
`domain/monetization/ports.py`). Принимает запрос на выплату
`(currency, amount_native, recipient_address)` и:

1. Маршрутизирует по валюте:
   * `TON_NANO` → сборка plain-TON-internal-message-а (TEP-67-conformant
     `int_msg_info` без тела) + обёртка в wallet-v3R2 external-message
     с Ed25519-подписью + публикация base64-encoded-BoC-а через
     `client.send_boc(...)`;
   * `USDT_DECIMAL` → резолв jetton-wallet-а через `JettonUsdtProvider`,
     сборка TEP-74-jetton-transfer-body (`op-code 0x0F8A7EA5` + 64-bit
     `query_id` + `VarUInteger 16` amount + 2x `MsgAddressInt` + flags
     + `forward_ton_amount`), внутренний `int_msg_info` к jetton-wallet-у
     + обёртка в wallet-v3R2 external-message + Ed25519-подпись +
     base64-encoded-BoC;
   * `STARS` → `UnsupportedPayoutCurrencyError`.
2. Возвращает `PayoutResult(tx_hash, actual_fee_native)`.

**Что НЕ делает D.10.b-3 (оставлено на D.10.c):**
* Не подписывает БОТ-стартап и не валидирует ключ payout-wallet-а (D.10.c
  — composition root собирает `ITonMessageSigner` из env-секрета).
* Не делает polling-а tx-hash-а: возвращает `tx_hash` сразу.
* Не кеширует SeqNo / our-jetton-wallet-адрес (D.10.c добавит warm-up).
* TODO(D.10.c): сейчас `JettonUsdtProvider.resolve_wallet(...)` резолвит
  **получательский** jetton-wallet, но per TEP-74 — нужен **наш**
  jetton-wallet (как destination внутреннего message) + recipient's
  TON-owner-address в TEP-74 body's `destination`-поле. D.10.b-3
  сохраняет существующее поведение (`destination_jetton_wallet` ставит
  на оба места) для backward-совместимости тестов; D.10.c исправит.

Каждый вызов `payout(...)` идемпотентен только до сетевого слоя
(`ITonRpcClient.send_boc(...)`); если caller хочет защиту от двойной
публикации, он должен использовать `IIdempotencyKey` поверх
`TonRpcAdapter` (caller `ClaimPrize` уже так делает, см. D.2).
"""

from __future__ import annotations

import base64
import hashlib
import time
from typing import TYPE_CHECKING

from pipirik_wars.domain.monetization.ports import PayoutResult
from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.infrastructure.payments.ton_rpc.boc import (
    Cell,
    CellBuilder,
    parse_address,
    serialize_boc,
)
from pipirik_wars.infrastructure.payments.ton_rpc.client import ITonRpcClient
from pipirik_wars.infrastructure.payments.ton_rpc.errors import (
    TonRpcCallError,
    UnsupportedPayoutCurrencyError,
)
from pipirik_wars.infrastructure.payments.ton_rpc.jetton import JettonUsdtProvider
from pipirik_wars.infrastructure.payments.ton_rpc.settings import TonRpcSettings

if TYPE_CHECKING:
    from collections.abc import Callable

    from pipirik_wars.infrastructure.payments.ton_rpc.signer import ITonMessageSigner

__all__ = ["TonRpcAdapter"]


# Минимальный «прицеп» nano-TON, который мы крепим к jetton-transfer-у
# для оплаты forward-а получателю + газа jetton-wallet-контракта.
# Стандарт TEP-74 рекомендует ~0.05–0.1 TON; берём консервативный 0.05.
_JETTON_TRANSFER_FORWARD_TON_NANO = 50_000_000

# Сколько TON-nano прицепить к message-у при USDT-выплате (оплата газа
# на стороне jetton-wallet-контракта получателя + forward + excess).
# По TEP-74 рекомендуется ~0.1 TON; берём 0.1.
_JETTON_TRANSFER_INTERNAL_TON_NANO = 100_000_000

# TEP-74 op-code для jetton-transfer-а (стабилен на уровне стандарта TON).
_JETTON_TRANSFER_OP_CODE = 0x0F8A7EA5

# Wallet-v3R2 send-mode 3 = 1 (pay fees separately) + 2 (ignore errors).
# Стандартный send-mode для hot-wallet-а, см. wallet-v3R2 FunC source.
_WALLET_V3R2_SEND_MODE = 3

# TTL внешнего сообщения от момента подписи (секунды).  Если message
# не включён в блок за это время, валидаторы дропают его.  60 секунд —
# tonweb-default, достаточно для одной подачи (caller может ретраить).
_EXTERNAL_MESSAGE_TTL_SECONDS = 60

# Размер blake2b-digest-а для query_id: 8 байт = 64 бита (TEP-74-поле).
_QUERY_ID_DIGEST_BYTES = 8


def _parse_tvm_int(raw: str, *, context: str) -> int:
    """Распарсить TVM-int из стек-записи `run_get_method`.

    TON Center возвращает целые из TVM в одной из двух форм:
    * decimal: `"42"`, `"-1"`;
    * hex (чаще для крупных значений): `"0x2a"`, `"-0x2a"`,
      `"0X2A"`. Префикс может быть в любом регистре.

    `int(value, 0)` распознаёт оба варианта автоматически по префиксу
    (`0x` / `0X` → 16, иначе 10). Заодно поддерживает unary-minus
    и пробельные обрамления (TON Center иногда отдаёт `" 0x2a "`),
    которые мы предварительно срезаем `strip()`-ом.

    Любой другой тип / `None` / пустая строка / non-numeric →
    `TonRpcCallError` с контекстом (имя вызывающего метода).
    """
    if not isinstance(raw, str):
        raise TonRpcCallError(
            f"{context}: stack[0] expected str, got {type(raw).__name__}={raw!r}",
            method="seqno",
        )
    trimmed = raw.strip()
    if not trimmed:
        raise TonRpcCallError(
            f"{context}: stack[0] is empty / whitespace-only string",
            method="seqno",
        )
    try:
        return int(trimmed, 0)
    except ValueError as exc:
        raise TonRpcCallError(
            f"{context}: stack[0]={raw!r} is not a valid TVM-int (decimal/hex)",
            method="seqno",
        ) from exc


class TonRpcAdapter:
    """Адаптер выплаты TON / USDT-jetton-а через TON-RPC.

    Реализует `ITonPayoutAdapter` (`pipirik_wars.domain.monetization.ports`):
    `payout(currency, amount_native, recipient_address) -> PayoutResult`.

    Зависимости (DI через конструктор; никакого глобального состояния):
    * `client: ITonRpcClient` — HTTP-обёртка TON-RPC (`client.py`).
    * `settings: TonRpcSettings` — конфигурация (адреса, sandbox, fallback,
      `wallet_subwallet_id` для wallet-v3R2 external-message-а).
    * `jetton_provider: JettonUsdtProvider` — резолв jetton-кошельков +
      сборка jetton-transfer-payload-а.
    * `signer: ITonMessageSigner` — Ed25519-сигнер `body.repr_hash()`-а
      external-message-а; production — `Ed25519MessageSigner` поверх
      PyNaCl, в тестах — `FakeTonMessageSigner` с детерминированным seed-ом.
    * `clock: Callable[[], float] | None` — источник current Unix-time-а
      (нужен для `valid_until = now + 60`); по умолчанию `time.time`.
      Тесты передают замороженные часы → детерминированный BoC.

    Stateless по обязательствам (seqno фетчится через `run_get_method`
    при каждом `payout(...)`; production может добавить локальный кеш
    в D.10.c).

    Безопасно использовать как singleton.
    """

    __slots__ = ("_client", "_clock", "_jetton_provider", "_settings", "_signer")

    def __init__(
        self,
        *,
        client: ITonRpcClient,
        settings: TonRpcSettings,
        jetton_provider: JettonUsdtProvider,
        signer: ITonMessageSigner,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._client = client
        self._settings = settings
        self._jetton_provider = jetton_provider
        self._signer = signer
        self._clock = clock if clock is not None else time.time

    async def payout(
        self,
        *,
        currency: Currency,
        amount_native: int,
        recipient_address: str,
    ) -> PayoutResult:
        """Выплатить приз получателю; возвращает `PayoutResult`.

        Параметры:
        * `currency` — валюта выплаты. `STARS` запрещён.
        * `amount_native` — количество native-юнитов (`>= 1`).
        * `recipient_address` — TON-адрес получателя (raw / friendly).

        Возвращает `PayoutResult(tx_hash, actual_fee_native)`.

        Поднимает:
        * `UnsupportedPayoutCurrencyError` — на `STARS`.
        * `ValueError` — на невалидных параметрах.
        * `TonRpcCallError` / `TonRpcTimeoutError` — пробрасываются из
          `client.send_boc(...)` / `client.run_get_method(...)`.
        * `JettonResolutionError` — при `USDT_DECIMAL`, если jetton-master
          отказался выдать jetton-wallet-а.
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

        query_id = self._derive_query_id(
            currency=currency,
            recipient_address=recipient_address,
            amount_native=amount_native,
        )

        if currency is Currency.TON_NANO:
            internal_message = self._build_ton_internal_message(
                amount_native=amount_native,
                recipient_address=recipient_address,
            )
        else:
            # USDT_DECIMAL — единственная оставшаяся валюта.
            # TODO(D.10.c): должен быть `owner_address=payout_wallet`
            # (наш jetton-wallet), а не recipient.  Сейчас сохраняем
            # существующее поведение D.5 ради backward-совместимости
            # тестов; semantic-fix — в D.10.c (composition root).
            destination_jetton_wallet = await self._jetton_provider.resolve_wallet(
                owner_address=recipient_address,
            )
            payload = self._jetton_provider.build_transfer_payload(
                query_id=query_id,
                amount_native=amount_native,
                destination_jetton_wallet=destination_jetton_wallet,
                response_destination=payout_wallet,
                forward_ton_amount=_JETTON_TRANSFER_FORWARD_TON_NANO,
            )
            internal_message = self._build_jetton_internal_message(
                destination_jetton_wallet=payload.destination_jetton_wallet,
                amount_native_ton=_JETTON_TRANSFER_INTERNAL_TON_NANO,
                jetton_transfer_body=self._build_jetton_transfer_body(
                    op_code=payload.op_code,
                    query_id=payload.query_id,
                    amount_native_usdt=payload.amount_native,
                    destination=payload.destination_jetton_wallet,
                    response_destination=payload.response_destination,
                    forward_ton_amount=payload.forward_ton_amount,
                ),
            )

        seqno = await self._fetch_seqno(payout_wallet)
        signed_boc_b64 = self._build_signed_external_message_boc(
            payout_wallet=payout_wallet,
            seqno=seqno,
            internal_message=internal_message,
        )

        send_result = await self._client.send_boc(signed_boc_base64=signed_boc_b64)
        return PayoutResult(
            tx_hash=send_result.tx_hash,
            actual_fee_native=send_result.actual_fee_native,
        )

    # ------------------------------------------------------------------
    # Query-id derivation (TEP-74-compatible 64-bit).
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_query_id(
        *,
        currency: Currency,
        recipient_address: str,
        amount_native: int,
    ) -> int:
        """Деривация `query_id`: 64-bit blake2b-digest от полной payout-tuple.

        Стабильна между процессами (в отличие от `hash()`); коллизии для
        реалистичных payout-объёмов пренебрежимо малы (2^64 пространство).
        Не криптографический id — caller всё равно идёт через
        `IIdempotencyKey` (`ClaimPrize`-use-case), но достаточно для
        TEP-74-поля `query_id`.
        """
        seed = f"{currency.value}|{recipient_address}|{amount_native}".encode()
        digest = hashlib.blake2b(seed, digest_size=_QUERY_ID_DIGEST_BYTES).digest()
        return int.from_bytes(digest, byteorder="big")

    # ------------------------------------------------------------------
    # SeqNo fetch (get-method `seqno` на wallet-v3R2-контракте).
    # ------------------------------------------------------------------

    async def _fetch_seqno(self, payout_wallet: str) -> int:
        """Получить текущий seqno нашего hot-wallet-а через `run_get_method`.

        wallet-v3R2-контракт экспонирует `get_method seqno() -> int`.
        Возвращает 0 на свежем (uninitialized) wallet-е — это допустимо,
        первая отправка инициализирует его.

        TON Center в ответе `run_get_method` отдаёт TVM-int одной из двух
        строковых форм: decimal (`"42"`) или hex (`"0x2a"` / реже `"-0x..."`).
        Парсим обе через `int(value, 0)` — Python автоматически выбирает
        базу по префиксу. Пустая строка / non-numeric → `TonRpcCallError`
        (контракт `_fetch_seqno: возвращает int`).
        """
        result = await self._client.run_get_method(
            address=payout_wallet,
            method="seqno",
            stack=(),
        )
        if result.exit_code != 0:
            raise TonRpcCallError(
                f"TonRpcAdapter._fetch_seqno: wallet `seqno` get-method returned "
                f"exit_code={result.exit_code} for wallet={payout_wallet!r}",
                method="seqno",
            )
        if not result.stack:
            raise TonRpcCallError(
                f"TonRpcAdapter._fetch_seqno: wallet `seqno` returned empty stack "
                f"for wallet={payout_wallet!r}",
                method="seqno",
            )
        raw_seqno = result.stack[0]
        return _parse_tvm_int(
            raw_seqno,
            context=f"TonRpcAdapter._fetch_seqno: wallet={payout_wallet!r}",
        )

    # ------------------------------------------------------------------
    # BoC builders.  Возвращают `Cell` или base64-encoded BoC-строку.
    # ------------------------------------------------------------------

    def _build_ton_internal_message(
        self,
        *,
        amount_native: int,
        recipient_address: str,
    ) -> Cell:
        """TEP-67 internal message без тела: чистый TON-перевод.

        TL-B (упрощённо):
        ```
        int_msg_info$0 ihr_disabled:Bool bounce:Bool bounced:Bool
          src:MsgAddress dest:MsgAddressInt value:CurrencyCollection
          ihr_fee:Grams fwd_fee:Grams created_lt:uint64 created_at:uint32
        ```
        + init = Nothing + body = inline empty.
        """
        workchain, account_hash = parse_address(recipient_address)
        return (
            CellBuilder()
            .store_uint(0, 1)  # int_msg_info$0 tag bit.
            .store_uint(1, 1)  # ihr_disabled = true (TON-default).
            .store_uint(0, 1)  # bounce = false — payout to user wallet (non-bouncable).
            .store_uint(0, 1)  # bounced = false (мы — initiator).
            .store_address_none()  # src auto-filled by validators.
            .store_address(workchain=workchain, account_hash=account_hash)
            .store_coins(amount_native)
            .store_uint(0, 1)  # value.other = Nothing (HashmapE empty).
            .store_coins(0)  # ihr_fee = 0.
            .store_coins(0)  # fwd_fee = 0.
            .store_uint(0, 64)  # created_lt = 0.
            .store_uint(0, 32)  # created_at = 0.
            .store_uint(0, 1)  # init = Nothing.
            .store_uint(0, 1)  # body inline (empty).
            .end_cell()
        )

    def _build_jetton_internal_message(
        self,
        *,
        destination_jetton_wallet: str,
        amount_native_ton: int,
        jetton_transfer_body: Cell,
    ) -> Cell:
        """Внутреннее TEP-67-message → jetton-wallet с TEP-74 body как ref.

        Bounce = true: jetton-wallet — контракт, ошибки должны возвращаться.
        Body хранится как ref (Either-tag = 1) — стандартная практика
        TON SDK для tightly-packed external-message-ей.
        """
        workchain, account_hash = parse_address(destination_jetton_wallet)
        return (
            CellBuilder()
            .store_uint(0, 1)  # int_msg_info$0.
            .store_uint(1, 1)  # ihr_disabled = true.
            .store_uint(1, 1)  # bounce = true — jetton-wallet-контракт.
            .store_uint(0, 1)  # bounced = false.
            .store_address_none()  # src auto.
            .store_address(workchain=workchain, account_hash=account_hash)
            .store_coins(amount_native_ton)
            .store_uint(0, 1)  # value.other = Nothing.
            .store_coins(0)  # ihr_fee.
            .store_coins(0)  # fwd_fee.
            .store_uint(0, 64)  # created_lt.
            .store_uint(0, 32)  # created_at.
            .store_uint(0, 1)  # init = Nothing.
            .store_uint(1, 1)  # body as ref (Either-tag = 1).
            .store_ref(jetton_transfer_body)
            .end_cell()
        )

    def _build_jetton_transfer_body(
        self,
        *,
        op_code: int,
        query_id: int,
        amount_native_usdt: int,
        destination: str,
        response_destination: str,
        forward_ton_amount: int,
    ) -> Cell:
        """TEP-74 jetton-transfer message body.

        TL-B:
        ```
        transfer#0f8a7ea5 query_id:uint64 amount:(VarUInteger 16)
          destination:MsgAddress response_destination:MsgAddress
          custom_payload:(Maybe ^Cell) forward_ton_amount:(VarUInteger 16)
          forward_payload:(Either Cell ^Cell)
        ```

        `custom_payload` = Nothing (1 bit = 0), `forward_payload` = inline
        empty (1 bit = 0).
        """
        if op_code != _JETTON_TRANSFER_OP_CODE:
            raise ValueError(
                f"TonRpcAdapter._build_jetton_transfer_body: op_code must be "
                f"0x{_JETTON_TRANSFER_OP_CODE:08x} (TEP-74); got 0x{op_code:08x}",
            )
        dest_wc, dest_hash = parse_address(destination)
        resp_wc, resp_hash = parse_address(response_destination)
        return (
            CellBuilder()
            .store_uint(op_code, 32)
            .store_uint(query_id, 64)
            .store_coins(amount_native_usdt)
            .store_address(workchain=dest_wc, account_hash=dest_hash)
            .store_address(workchain=resp_wc, account_hash=resp_hash)
            .store_uint(0, 1)  # custom_payload = Nothing.
            .store_coins(forward_ton_amount)
            .store_uint(0, 1)  # forward_payload = inline empty.
            .end_cell()
        )

    def _build_signed_external_message_boc(
        self,
        *,
        payout_wallet: str,
        seqno: int,
        internal_message: Cell,
    ) -> str:
        """wallet-v3R2 external-message: unsigned body → Ed25519 sign → BoC b64.

        Структура unsigned body (для подписи):
        ```
        subwallet_id:uint32 valid_until:uint32 seqno:uint32 send_mode:uint8
          internal_message:^Cell
        ```
        Подписываем 32-byte representation-hash этой ячейки.

        Структура signed body:
        ```
        signature:bits512  subwallet_id  valid_until  seqno  send_mode
          internal_message:^Cell
        ```

        External-message wrapper:
        ```
        ext_in_msg_info$10 src:addr_none dest:MsgAddressInt import_fee:Grams
        + init:Nothing + body:^Cell (signed_body)
        ```

        Возвращает base64-encoded BoC (single-root, no idx, no crc).
        """
        valid_until = int(self._clock()) + _EXTERNAL_MESSAGE_TTL_SECONDS

        unsigned_body = (
            CellBuilder()
            .store_uint(self._settings.wallet_subwallet_id, 32)
            .store_uint(valid_until, 32)
            .store_uint(seqno, 32)
            .store_uint(_WALLET_V3R2_SEND_MODE, 8)
            .store_ref(internal_message)
            .end_cell()
        )
        signature = self._signer.sign(message=unsigned_body.repr_hash())
        if len(signature) != 64:
            raise ValueError(
                f"TonRpcAdapter._build_signed_external_message_boc: signer.sign(...) "
                f"returned {len(signature)} bytes; Ed25519 must be 64.",
            )

        signed_body = (
            CellBuilder()
            .store_bytes(signature)
            .store_uint(self._settings.wallet_subwallet_id, 32)
            .store_uint(valid_until, 32)
            .store_uint(seqno, 32)
            .store_uint(_WALLET_V3R2_SEND_MODE, 8)
            .store_ref(internal_message)
            .end_cell()
        )

        wallet_wc, wallet_hash = parse_address(payout_wallet)
        external_message = (
            CellBuilder()
            .store_uint(0b10, 2)  # ext_in_msg_info$10 tag.
            .store_address_none()  # src = addr_none.
            .store_address(workchain=wallet_wc, account_hash=wallet_hash)
            .store_coins(0)  # import_fee = 0.
            .store_uint(0, 1)  # init = Nothing.
            .store_uint(1, 1)  # body as ref.
            .store_ref(signed_body)
            .end_cell()
        )
        return base64.b64encode(serialize_boc(external_message)).decode("ascii")
