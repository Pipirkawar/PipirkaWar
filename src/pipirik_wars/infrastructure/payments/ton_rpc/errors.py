"""Ошибки TON-RPC-адаптеров (Спринт 4.1-D, шаг D.5).

Иерархия:

```
Exception
└── TonRpcCallError          — общий контракт ошибки RPC-вызова
    ├── TonRpcTimeoutError   — таймаут до ответа TON-ноды
    └── JettonResolutionError — jetton-master не вернул валидный
                                 кошелёк-получатель (`get_wallet_address`-call)
                                 — это конкретный подвид RPC-ошибки и тоже
                                 наследует `TonRpcCallError`, чтобы caller
                                 мог поймать всё одной `except`-веткой.

UnsupportedPayoutCurrencyError — отдельная иерархия (`ValueError`-style),
    т.к. это ошибка использования API адаптера, а не сетевая (caller
    спросил `STARS`-выплату у TON-адаптера — это контрактная ошибка).
```

Все ошибки — namespace-чистые: ни одна не наследуется от `DomainError`
/ `MonetizationDomainError`, т.к. живут в infrastructure-слое. Use-case
`ClaimPrize` (4.1-D, D.2) при ловле этих ошибок будет конвертировать в
domain-ошибки (например, `PayoutTransientError`) — но это решение
принимается на стороне application-слоя, не здесь.
"""

from __future__ import annotations

__all__ = [
    "JettonResolutionError",
    "TonRpcCallError",
    "TonRpcTimeoutError",
    "UnsupportedPayoutCurrencyError",
]


class TonRpcCallError(Exception):
    """Базовая ошибка RPC-вызова к TON-ноде.

    Подразумевает, что произошёл общий network-/protocol-сбой
    (HTTP 5xx, malformed JSON, TON node вернула отрицательный exit_code
    в `runGetMethod`-результате, и т.п.). Caller (`TonRpcAdapter`,
    `TonRpcFeeEstimator`) может либо пробросить наверх, либо
    конвертировать в domain-ошибку.

    Атрибуты:
    * ``message: str`` — человеко-читаемое описание ситуации.
    * ``endpoint: str | None`` — URL TON-ноды (может быть `None`,
      если ошибка возникла до отправки запроса).
    * ``method: str | None`` — имя RPC-метода / endpoint-а
      (`"runGetMethod"`, `"sendBoc"`, …).
    """

    __slots__ = ("endpoint", "message", "method")

    def __init__(
        self,
        message: str,
        *,
        endpoint: str | None = None,
        method: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.endpoint = endpoint
        self.method = method


class TonRpcTimeoutError(TonRpcCallError):
    """Таймаут TON-RPC-вызова.

    Разновидность `TonRpcCallError` — caller, который хочет
    различать «таймаут (повторить через retry-backoff)» и
    «ответ пришёл, но валидно-ошибочный (не повторять)», ловит
    `TonRpcTimeoutError` отдельно. Иначе — общий `TonRpcCallError`.

    Атрибут ``timeout_seconds: float`` — таймаут, на котором мы оборвали
    ожидание.
    """

    __slots__ = ("timeout_seconds",)

    def __init__(
        self,
        message: str,
        *,
        timeout_seconds: float,
        endpoint: str | None = None,
        method: str | None = None,
    ) -> None:
        super().__init__(message, endpoint=endpoint, method=method)
        self.timeout_seconds = timeout_seconds


class JettonResolutionError(TonRpcCallError):
    """Не удалось зарезолвить jetton-кошелёк по jetton-master-у.

    Возникает, когда `runGetMethod('get_wallet_address', owner_address)`
    вернул не валидный `TonAddress`-формат, либо jetton-master отказался
    отвечать. На уровне `ClaimPrize` (4.1-D) это означает «нельзя
    выплатить лот на этот адрес» — лот возвращается в пул
    (`update_status(REFUNDED)` + `apply_increment`).

    Атрибуты:
    * ``master_address: str`` — адрес jetton-master-а, к которому делали
      запрос.
    * ``owner_address: str`` — адрес владельца, для которого пытались
      найти jetton-кошелёк.
    """

    __slots__ = ("master_address", "owner_address")

    def __init__(
        self,
        message: str,
        *,
        master_address: str,
        owner_address: str,
        endpoint: str | None = None,
    ) -> None:
        super().__init__(message, endpoint=endpoint, method="get_wallet_address")
        self.master_address = master_address
        self.owner_address = owner_address


class UnsupportedPayoutCurrencyError(ValueError):
    """`TonRpcAdapter` не умеет выплачивать запрошенную валюту.

    `TonRpcAdapter` обслуживает `TON_NANO` / `USDT_DECIMAL` — TG Stars
    (`STARS`) выплачивается через Bot API (refund-эндпоинт), это
    отдельный адаптер (он будет реализован отдельно от TON-RPC).
    Caller (`ClaimPrize`, D.2) обязан маршрутизировать по валюте.

    Атрибут ``currency: str`` — машинный id запрошенной валюты
    (значение `Currency.value`).
    """

    __slots__ = ("currency",)

    def __init__(self, message: str, *, currency: str) -> None:
        super().__init__(message)
        self.currency = currency
