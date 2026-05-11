"""Абстракция TON-RPC HTTP-клиента (Спринт 4.1-D, шаг D.5).

`ITonRpcClient` — это infra-слойный Protocol, изолирующий конкретный
HTTP-клиент (`aiohttp` / `httpx` / native TON SDK) от логики
`TonRpcAdapter` / `TonRpcFeeEstimator` / `JettonUsdtProvider`. Все три
эти класса говорят с TON-нодой только через этот контракт; реальная
HTTP-реализация (`AiohttpTonRpcClient`) появится в шаге **D.10** —
тогда же мы её подключим в `bot/main.py::Container`.

Контракт намеренно тонкий — три метода:

* ``run_get_method`` — вызов `runGetMethod` смарт-контракта.
  Используется `JettonUsdtProvider` для `get_wallet_address`-резолва
  jetton-кошелька и (опционально, в перспективе) `TonRpcFeeEstimator`
  для запроса конфигурационных параметров сети.
* ``send_boc`` — публикация подписанного BOC-message-а. Возвращает
  `tx_hash` (hex-string) для последующего polling-а. Опционально
  возвращает фактическую комиссию (`actual_fee_native`) — обычно
  TON-нода отдаёт её в ответе на `sendBocReturnHash` / в логе
  account-state-а после mine-инга, но для D.5-API это просто
  поле в `BocSendResult`.
* ``recent_fees`` — суррогат для P95-оценки: возвращает фактические
  газы за последние ``days`` дней по нашему hot-wallet-адресу (т.е.
  на ``TonRpcFeeEstimator`` ложится только расчёт P95 из массива,
  а сбор истории — задача HTTP-имплементации). У ``RecentFee``
  есть и сумма газа (``fee_native``), и таймштамп — каждый фий
  попадает в окно ``[now - days, now]``.

Имплементация `FakeTonRpcClient` живёт в `tests/.../_fakes.py` и
используется во всех D.5-unit-тестах.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

__all__ = [
    "BocSendResult",
    "ITonRpcClient",
    "RecentFee",
    "RunGetMethodResult",
]


@dataclass(frozen=True, slots=True)
class RecentFee:
    """Одно историческое значение газа per транзакция (Спринт 4.1-D, D.5).

    Используется `TonRpcFeeEstimator` для P95-оценки за окно
    `fee_window_days` дней.

    * ``fee_native: int`` — комиссия в native-юнитах валюты вызова
      (для TON-trans-а — нано-TON; для USDT-jetton-trans-а — USDT-decimal,
      т.к. caller знает, в каком домене считает).
    * ``occurred_at: datetime`` — момент мине-инга транзакции (TZ-aware).
      Используется только для фильтрации «вне окна» в неблагоприятных
      случаях, когда клиент вернул больше, чем `days` дней. P95-расчёт
      внутри окна не зависит от времени — берётся nearest-rank-метод.
    """

    fee_native: int
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class RunGetMethodResult:
    """Результат вызова смарт-контракта `runGetMethod` (Спринт 4.1-D, D.5).

    Контракт TON-RPC-а: возвращает стек значений (списки разнородных
    типов). Мы сводим к словарю по имени поля — caller знает по сигнатуре
    метода, какие поля ожидать.

    * ``exit_code: int`` — TVM exit code. `0` — успех, любое другое —
      ошибка контракта (например, `get_wallet_address` не сработал
      для невалидного owner-а).
    * ``stack: tuple[str, ...]`` — сырой стек из RPC-ответа,
      string-encoded (toncenter возвращает hex / boc-cell / number).
      Caller декодирует.
    """

    exit_code: int
    stack: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BocSendResult:
    """Результат публикации подписанного BOC-message-а (Спринт 4.1-D, D.5).

    * ``tx_hash: str`` — base64url / hex hash-а транзакции. На него
      caller подписывается, polling-ом дожидается inclusion-а в блок.
    * ``actual_fee_native: int`` — фактическая комиссия. На D.5 мы
      просим адаптер вернуть её сразу (часть TON-нод поддерживают
      `sendBocReturnHash`-эндпоинт, который отдаёт hash + estimated
      fee; реальное значение становится известно после mine-инга и
      хранится в `account_state.last_transaction_fee` — D.10 / D.7
      могут поллить и обновлять).
    """

    tx_hash: str
    actual_fee_native: int


class ITonRpcClient(Protocol):
    """Тонкая HTTP-обёртка над TON-RPC (Спринт 4.1-D, шаг D.5).

    Реальная HTTP-имплементация — отдельный шаг (D.10). До тех пор
    `TonRpcAdapter` / `TonRpcFeeEstimator` / `JettonUsdtProvider`
    говорят с этим Protocol-ом, а тесты подсовывают `FakeTonRpcClient`.

    Все методы — асинхронные. Реализация может бросать
    `TonRpcTimeoutError` / `TonRpcCallError` (из `errors.py`)
    при сетевых сбоях; caller'ы D.5-классов их пробрасывают / ловят.
    """

    async def run_get_method(
        self,
        *,
        address: str,
        method: str,
        stack: Sequence[str] = (),
    ) -> RunGetMethodResult:
        """Вызвать `runGetMethod` смарт-контракта.

        Параметры:
        * ``address`` — TON-адрес смарт-контракта (raw или friendly).
        * ``method`` — имя method-а внутри контракта
          (`"get_wallet_address"`, `"get_jetton_data"`, …).
        * ``stack`` — входной стек значений (опциональный; для
          `get_wallet_address` — `(owner_address_cell,)`).

        Возвращает `RunGetMethodResult` с `exit_code` и сырым стеком.
        Поднимает `TonRpcCallError` при network-/protocol-сбое;
        `TonRpcTimeoutError` при таймауте.
        """
        ...

    async def send_boc(
        self,
        *,
        signed_boc_base64: str,
    ) -> BocSendResult:
        """Опубликовать подписанный BOC-message в TON-сеть.

        Параметры:
        * ``signed_boc_base64`` — base64-encoded BOC сообщения,
          подписанный ключом hot-wallet-а. Сборка / подпись — забота
          caller-а (`TonRpcAdapter` пользуется отдельным портом
          подписи, который появится в D.10 / D.7).

        Возвращает `BocSendResult` с `tx_hash` + `actual_fee_native`.
        Поднимает `TonRpcCallError` при network-/protocol-сбое;
        `TonRpcTimeoutError` при таймауте.
        """
        ...

    async def recent_fees(
        self,
        *,
        address: str,
        days: int,
    ) -> Sequence[RecentFee]:
        """История фактических комиссий по адресу за последние `days`-дней.

        Параметры:
        * ``address`` — наш hot-wallet-адрес (для TON-trans-а) либо
          jetton-master / jetton-wallet (для USDT-trans-а).
        * ``days`` — окно в днях (`>= 1`). Реализация может вернуть
          и больше, и меньше элементов: P95-расчёт внутри
          `TonRpcFeeEstimator` устойчив к любому `N >= 0`.

        Возвращает кортеж `RecentFee`-точек в хронологическом порядке
        (новые — последние). При пустой истории — пустой кортеж.

        Поднимает `TonRpcCallError` при network-/protocol-сбое;
        `TonRpcTimeoutError` при таймауте.
        """
        ...


# Маппинг ответных полей для toncenter-style-ответов. Не используется в
# D.5-классах (они говорят на язык DTO выше); вынесен в заголовок
# модуля как public-контракт для будущего `AiohttpTonRpcClient` (D.10).
_TONCENTER_STACK_FIELD: Mapping[str, str] = {
    "address": "value",
    "int": "value",
    "cell": "value",
}
