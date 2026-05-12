"""Jetton-USDT-провайдер (Спринт 4.1-D, шаг D.5).

`JettonUsdtProvider` решает две связанные задачи:

1. **Резолв jetton-кошелька получателя.** USDT на TON — это jetton:
   у каждого holder-а есть отдельный jetton-wallet-контракт. Чтобы
   отправить USDT, нужно знать адрес именно этого jetton-wallet-а,
   а не адрес TON-кошелька holder-а. Резолв делается через
   `runGetMethod('get_wallet_address', owner_address)` на
   jetton-master-контракте. Метод возвращает `(slice address)`-стек
   с адресом jetton-wallet-а.

2. **Сборка payload-а jetton-transfer-а.** TON-протокол jetton-а
   определяет `transfer`-message с фиксированной структурой (op-code
   `0x0f8a7ea5`, query_id, amount, destination, response_destination,
   custom_payload, forward_ton_amount, forward_payload). Здесь мы
   собираем только метаданные (op-code + поля) — реальная сериализация
   в BOC-cell делается в `TonRpcAdapter` через message-builder-порт
   (вне скоупа D.5; будет в D.10/D.7).

Контракт: всё что нужно от внешнего мира — `ITonRpcClient`, потому
что `runGetMethod` — единственный сетевой вызов в этом модуле.
Тесты подсовывают `FakeTonRpcClient`.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass

from pipirik_wars.infrastructure.payments.ton_rpc.boc import (
    deserialize_boc,
    format_raw_address,
    parse_address,
    parse_msgaddress_int_from_cell,
)
from pipirik_wars.infrastructure.payments.ton_rpc.client import ITonRpcClient
from pipirik_wars.infrastructure.payments.ton_rpc.errors import JettonResolutionError

__all__ = ["JettonTransferPayload", "JettonUsdtProvider"]


# Op-code TEP-74 jetton-transfer-а. Стабилен на уровне стандарта TON
# jetton (см. https://github.com/ton-blockchain/TEPs/blob/master/text/0074-jettons-standard.md).
_JETTON_TRANSFER_OP_CODE = 0x0F8A7EA5


def _b64_decode_permissive(raw: str) -> bytes:
    """Декодировать base64 с возможным `-_`-алфавитом + опциональным padding-ом.

    TON Center иногда отдаёт base64url-стрингу без padding-а (`=`),
    иногда стандартный base64. Делаем permissive-decode для обоих случаев.
    """
    normalized = raw.replace("-", "+").replace("_", "/")
    padding = (-len(normalized)) % 4
    return base64.b64decode(normalized + "=" * padding, validate=True)


@dataclass(frozen=True, slots=True)
class JettonTransferPayload:
    """Метаданные jetton-transfer-сообщения (Спринт 4.1-D, шаг D.5).

    Поля совпадают с TEP-74-стандартом jetton-transfer (минус сама
    сериализация в BOC, которая делается отдельным message-builder-ом).

    * ``op_code: int`` — всегда `0x0f8a7ea5` (TEP-74 jetton-transfer).
    * ``query_id: int`` — uniquifier (`>= 0`); ставит caller
      (`TonRpcAdapter`) перед сборкой BOC-а.
    * ``amount_native: int`` — сколько jetton-минор-юнит-ов перевести
      (`>= 1`). Для USDT это USDT-decimal-юниты (decimals=6).
    * ``destination_jetton_wallet: str`` — адрес jetton-wallet-а
      получателя. Резолвится через ``JettonUsdtProvider.resolve_wallet(...)``.
    * ``response_destination: str`` — адрес, куда вернётся `excess_ton`
      после оплаты газа. Обычно это адрес нашего hot-wallet-а.
    * ``forward_ton_amount: int`` — сколько nano-TON прицепить к
      forward-message (`>= 0`). Для простого USDT-перевода без
      нотификации получателю — `0`.
    """

    op_code: int
    query_id: int
    amount_native: int
    destination_jetton_wallet: str
    response_destination: str
    forward_ton_amount: int


class JettonUsdtProvider:
    """Провайдер jetton-USDT-операций (Спринт 4.1-D, шаг D.5).

    Stateless-объект. Хранит ссылку на `ITonRpcClient` (для
    `runGetMethod`) и адрес jetton-master-USDT (из `TonRpcSettings`).
    Не имплементит никакого порта — это вспомогательный класс
    `TonRpcAdapter`-а.

    Безопасно использовать как singleton.
    """

    __slots__ = ("_client", "_jetton_master_address")

    def __init__(
        self,
        *,
        client: ITonRpcClient,
        jetton_master_address: str,
    ) -> None:
        if not jetton_master_address:
            raise ValueError(
                "JettonUsdtProvider.jetton_master_address must be non-empty",
            )
        self._client = client
        self._jetton_master_address = jetton_master_address

    @property
    def jetton_master_address(self) -> str:
        """Адрес USDT-jetton-master-контракта (read-only)."""
        return self._jetton_master_address

    async def resolve_wallet(self, *, owner_address: str) -> str:
        """Зарезолвить jetton-wallet-адрес для `owner_address`.

        Делает `runGetMethod('get_wallet_address', owner)` на
        jetton-master-контракте. Поднимает `JettonResolutionError`,
        если контракт вернул `exit_code != 0` или пустой стек.

        Параметры:
        * ``owner_address`` — TON-адрес владельца (raw / friendly).
          Обычно — `recipient_address` из `ClaimPrize`-вызова.

        Возвращает: jetton-wallet-адрес (строка). Caller передаст
        его в `JettonTransferPayload.destination_jetton_wallet`.
        """
        if not owner_address:
            raise JettonResolutionError(
                "owner_address must be non-empty",
                master_address=self._jetton_master_address,
                owner_address=owner_address,
            )

        result = await self._client.run_get_method(
            address=self._jetton_master_address,
            method="get_wallet_address",
            stack=(owner_address,),
        )

        if result.exit_code != 0:
            raise JettonResolutionError(
                f"jetton-master returned non-zero exit_code={result.exit_code} "
                f"for owner_address={owner_address!r}",
                master_address=self._jetton_master_address,
                owner_address=owner_address,
            )

        if not result.stack:
            raise JettonResolutionError(
                f"jetton-master returned empty stack for owner_address={owner_address!r}",
                master_address=self._jetton_master_address,
                owner_address=owner_address,
            )

        jetton_wallet_raw = result.stack[0]
        if not jetton_wallet_raw:
            raise JettonResolutionError(
                "jetton-master returned empty jetton-wallet address for "
                f"owner_address={owner_address!r}",
                master_address=self._jetton_master_address,
                owner_address=owner_address,
            )
        return self._decode_jetton_wallet_address(
            jetton_wallet_raw,
            owner_address=owner_address,
        )

    def _decode_jetton_wallet_address(
        self,
        raw: str,
        *,
        owner_address: str,
    ) -> str:
        """Распарсить ``stack[0]`` ответа ``get_wallet_address`` в TON-адрес.

        TON Center отдаёт результат ``get_wallet_address`` как
        slice-/cell-stack-entry: ``["slice"|"cell", {"bytes": "<base64-BoC>"}]``.
        Http-client flattens это в base64-строку (см.
        ``http_client._stack_entry_to_str``). Здесь мы:

        1. Если ``raw`` уже выглядит как готовый TON-адрес (raw ``"<wc>:<hex>"``
           или friendly base64url-48-chars-с-CRC) — возвращаем как есть
           (это путь для ``FakeTonRpcClient`` и для backward-compat-сценариев).
        2. Иначе пробуем ``base64-decode → deserialize_boc → parse_msgaddress_int``
           → ``format_raw_address``. На любую ошибку парсинга →
           ``JettonResolutionError`` с диагностикой.
        """
        # 1. Try direct address parsing (raw "wc:hex" / friendly base64url).
        try:
            workchain, account_hash = parse_address(raw)
        except ValueError:
            pass
        else:
            return format_raw_address(workchain, account_hash)

        # 2. Try BoC deserialization (base64-encoded slice/cell from TON Center).
        try:
            boc_bytes = _b64_decode_permissive(raw)
        except (binascii.Error, ValueError) as exc:
            raise JettonResolutionError(
                f"jetton-master returned non-address non-base64-BoC string for "
                f"owner_address={owner_address!r}: stack[0]={raw!r}",
                master_address=self._jetton_master_address,
                owner_address=owner_address,
            ) from exc

        try:
            cell = deserialize_boc(boc_bytes)
            workchain, account_hash = parse_msgaddress_int_from_cell(cell)
        except ValueError as exc:
            raise JettonResolutionError(
                f"jetton-master returned base64-BoC that does not decode to "
                f"MsgAddressInt for owner_address={owner_address!r}: "
                f"stack[0]={raw!r}, decode-error={exc}",
                master_address=self._jetton_master_address,
                owner_address=owner_address,
            ) from exc

        return format_raw_address(workchain, account_hash)

    def build_transfer_payload(
        self,
        *,
        query_id: int,
        amount_native: int,
        destination_jetton_wallet: str,
        response_destination: str,
        forward_ton_amount: int = 0,
    ) -> JettonTransferPayload:
        """Собрать метаданные jetton-transfer-message-а (TEP-74).

        Параметры — см. поля `JettonTransferPayload`. Проверяет
        инварианты:
        * ``query_id >= 0``;
        * ``amount_native >= 1``;
        * ``forward_ton_amount >= 0``;
        * ``destination_jetton_wallet`` и ``response_destination`` —
          непустые строки.

        Возвращает `JettonTransferPayload` с op-code `0x0f8a7ea5`.
        """
        if query_id < 0:
            raise ValueError(
                f"JettonUsdtProvider.build_transfer_payload: query_id must be >= 0, got {query_id}",
            )
        if amount_native < 1:
            raise ValueError(
                f"JettonUsdtProvider.build_transfer_payload: amount_native must "
                f"be >= 1, got {amount_native}",
            )
        if forward_ton_amount < 0:
            raise ValueError(
                f"JettonUsdtProvider.build_transfer_payload: forward_ton_amount "
                f"must be >= 0, got {forward_ton_amount}",
            )
        if not destination_jetton_wallet:
            raise ValueError(
                "JettonUsdtProvider.build_transfer_payload: "
                "destination_jetton_wallet must be non-empty",
            )
        if not response_destination:
            raise ValueError(
                "JettonUsdtProvider.build_transfer_payload: response_destination must be non-empty",
            )

        return JettonTransferPayload(
            op_code=_JETTON_TRANSFER_OP_CODE,
            query_id=query_id,
            amount_native=amount_native,
            destination_jetton_wallet=destination_jetton_wallet,
            response_destination=response_destination,
            forward_ton_amount=forward_ton_amount,
        )
