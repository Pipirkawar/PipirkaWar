"""Тестовые двойники TON-RPC-клиента (Спринт 4.1-D, шаг D.5).

`FakeTonRpcClient` — программируемая in-memory имплементация
`ITonRpcClient`. Поддерживает:

* `queue_run_get_method(...)` — заранее «забить» ответ на следующий
  вызов `run_get_method(...)`. Можно сделать FIFO для нескольких
  вызовов подряд.
* `queue_send_boc(...)` — то же для `send_boc(...)`.
* `set_recent_fees(...)` — установить выборку, которую вернёт
  `recent_fees(...)` для заданного адреса.
* `raise_on_*` — программировать исключения (например, для тестов
  таймаутов / RPC-ошибок).
* `calls` — список (DTO) всех вызовов, сделанных клиенту, для
  проверки «адаптер запросил то, что мы ожидали».

`FakeTonRpcClient` намеренно НЕ имитирует TON-протокол на уровне
байтов — это unit-test-уровень, а не integration-уровень. Его
задача — позволить написать тесты `TonRpcAdapter` /
`TonRpcFeeEstimator` / `JettonUsdtProvider` без сетевого слоя.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from pipirik_wars.infrastructure.payments.ton_rpc.client import (
    BocSendResult,
    RecentFee,
    RunGetMethodResult,
)
from pipirik_wars.infrastructure.payments.ton_rpc.errors import (
    TonRpcCallError,
    TonRpcTimeoutError,
)

__all__ = [
    "FakeTonRpcClient",
    "RecordedRunGetMethodCall",
    "RecordedSendBocCall",
]


@dataclass(frozen=True, slots=True)
class RecordedRunGetMethodCall:
    """Запись одного вызова `run_get_method`."""

    address: str
    method: str
    stack: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecordedSendBocCall:
    """Запись одного вызова `send_boc`."""

    signed_boc_base64: str


class FakeTonRpcClient:
    """Программируемый стаб `ITonRpcClient` для unit-тестов D.5.

    Семантика:
    * `run_get_method` / `send_boc` пишут вызов в `calls_*` и возвращают
      следующий запрограммированный ответ. Если очередь пуста — кидаем
      `RuntimeError` (это тест-баг, а не контракт API).
    * `recent_fees` возвращает ранее установленную через `set_recent_fees`
      выборку. Если для адреса ничего не установлено — пустой кортеж
      (контракт `ITonRpcClient.recent_fees` это явно разрешает).
    * `raise_on_*` принудительно бросает указанное исключение на
      следующем вызове (одноразово).
    """

    def __init__(self) -> None:
        self._run_get_method_queue: deque[RunGetMethodResult] = deque()
        self._send_boc_queue: deque[BocSendResult] = deque()
        self._recent_fees_by_address: dict[str, tuple[RecentFee, ...]] = {}
        self.calls_run_get_method: list[RecordedRunGetMethodCall] = []
        self.calls_send_boc: list[RecordedSendBocCall] = []
        self.calls_recent_fees: list[tuple[str, int]] = []
        self._raise_on_run_get_method: TonRpcCallError | None = None
        self._raise_on_send_boc: TonRpcCallError | None = None
        self._raise_on_recent_fees: TonRpcCallError | None = None

    # ---- programming API -------------------------------------------------

    def queue_run_get_method(
        self,
        *,
        exit_code: int = 0,
        stack: Sequence[str] = (),
    ) -> None:
        """Добавить ответ в FIFO `run_get_method`."""
        self._run_get_method_queue.append(
            RunGetMethodResult(exit_code=exit_code, stack=tuple(stack)),
        )

    def queue_send_boc(
        self,
        *,
        tx_hash: str = "fake-tx-hash",
        actual_fee_native: int = 0,
    ) -> None:
        """Добавить ответ в FIFO `send_boc`."""
        self._send_boc_queue.append(
            BocSendResult(tx_hash=tx_hash, actual_fee_native=actual_fee_native),
        )

    def set_recent_fees(
        self,
        *,
        address: str,
        fees: Iterable[RecentFee],
    ) -> None:
        """Запрограммировать ответ `recent_fees` для конкретного адреса."""
        self._recent_fees_by_address[address] = tuple(fees)

    def raise_on_run_get_method(self, error: TonRpcCallError) -> None:
        """Заставить следующий `run_get_method` бросить `error`."""
        self._raise_on_run_get_method = error

    def raise_on_send_boc(self, error: TonRpcCallError) -> None:
        """Заставить следующий `send_boc` бросить `error`."""
        self._raise_on_send_boc = error

    def raise_on_recent_fees(self, error: TonRpcCallError) -> None:
        """Заставить следующий `recent_fees` бросить `error`."""
        self._raise_on_recent_fees = error

    def raise_timeout_on_recent_fees(self, *, timeout_seconds: float = 10.0) -> None:
        """Удобный shortcut: бросить `TonRpcTimeoutError` на следующем `recent_fees`."""
        self._raise_on_recent_fees = TonRpcTimeoutError(
            "fake timeout",
            timeout_seconds=timeout_seconds,
            method="recent_fees",
        )

    # ---- ITonRpcClient implementation -----------------------------------

    async def run_get_method(
        self,
        *,
        address: str,
        method: str,
        stack: Sequence[str] = (),
    ) -> RunGetMethodResult:
        self.calls_run_get_method.append(
            RecordedRunGetMethodCall(address=address, method=method, stack=tuple(stack)),
        )
        if self._raise_on_run_get_method is not None:
            error = self._raise_on_run_get_method
            self._raise_on_run_get_method = None
            raise error
        if not self._run_get_method_queue:
            raise RuntimeError(
                "FakeTonRpcClient: run_get_method queue is empty; queue an answer "
                "via queue_run_get_method(...) before calling.",
            )
        return self._run_get_method_queue.popleft()

    async def send_boc(self, *, signed_boc_base64: str) -> BocSendResult:
        self.calls_send_boc.append(RecordedSendBocCall(signed_boc_base64=signed_boc_base64))
        if self._raise_on_send_boc is not None:
            error = self._raise_on_send_boc
            self._raise_on_send_boc = None
            raise error
        if not self._send_boc_queue:
            raise RuntimeError(
                "FakeTonRpcClient: send_boc queue is empty; queue an answer "
                "via queue_send_boc(...) before calling.",
            )
        return self._send_boc_queue.popleft()

    async def recent_fees(
        self,
        *,
        address: str,
        days: int,
    ) -> Sequence[RecentFee]:
        self.calls_recent_fees.append((address, days))
        if self._raise_on_recent_fees is not None:
            error = self._raise_on_recent_fees
            self._raise_on_recent_fees = None
            raise error
        return self._recent_fees_by_address.get(address, ())
