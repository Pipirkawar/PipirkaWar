"""`TonRpcFeeEstimator` — P95-оценка газа за последние N дней (Спринт 4.1-D, шаг D.5).

Реализует доменный порт `IFeeEstimator` (см. `domain/monetization/ports.py`).
Заменяет `InMemoryFeeEstimator` (4.1-C) в проде — но **подключение
к composition root отложено на шаг D.10**. До D.10 `TonRpcFeeEstimator`
живёт «в коробке» и тестируется на `FakeTonRpcClient`; cron-у
`GeneratePrizeLots` пока продолжает обслуживать константный
`InMemoryFeeEstimator`.

Алгоритм:

* `STARS` → возврат `0` (TG-сторона не берёт gas-а; та же семантика,
  что у `InMemoryFeeEstimator`).
* `TON_NANO` / `USDT_DECIMAL` → `client.recent_fees(address, days)`
  + nearest-rank P95 от полученной выборки.
  * Адрес — `settings.payout_wallet_address` для TON_NANO,
    `settings.usdt_jetton_master` для USDT_DECIMAL.
  * Пустая выборка (`N == 0`) → возврат `settings.fallback_fee_buffer_*`
    (по дефолту совпадает с `InMemoryFeeEstimator`).

Nearest-rank P95 — это `sorted_asc[ceil(0.95 * N) - 1]`. На `N == 1`
это просто этот единственный элемент. Стабилен в integer-арифметике,
не требует floating-point-конверсии.

Контракт `IFeeEstimator.estimate_fee` асинхронный: `recent_fees` —
сетевой вызов. Сетевые ошибки (`TonRpcCallError` / `TonRpcTimeoutError`)
**пробрасываются наверх** — caller (`GeneratePrizeLots`) знает, что
делать при таймауте (например, пропустить cron-tick и подождать
следующего). Conservative fallback на ошибке здесь намеренно не
реализован: молча подменять P95-оценку константой опасно, лучше
fail-loud + retry.
"""

from __future__ import annotations

import math

from pipirik_wars.domain.monetization.value_objects import Currency
from pipirik_wars.infrastructure.payments.ton_rpc.client import (
    ITonRpcClient,
    RecentFee,
)
from pipirik_wars.infrastructure.payments.ton_rpc.settings import TonRpcSettings

__all__ = ["TonRpcFeeEstimator"]


# Перцентиль для nearest-rank-расчёта. P95 — соответствует ГДД §12.6.3.
_PERCENTILE = 0.95


def _percentile_nearest_rank(samples: list[int], *, percentile: float) -> int:
    """Nearest-rank-метод оценки перцентиля для дискретной выборки.

    `sorted_asc[ceil(p * N) - 1]`. Стабилен на пустой выборке (мы её
    отсекаем в caller-е), на `N == 1` возвращает единственный элемент.

    Параметры:
    * ``samples`` — выборка (не обязана быть отсортирована); ``len >= 1``.
    * ``percentile`` — `(0, 1]`. Для нас всегда `0.95`.

    Returns:
    * Перцентиль из выборки (int, native-юниты валюты).
    """
    if not samples:
        raise ValueError("_percentile_nearest_rank: samples must be non-empty")
    if not 0.0 < percentile <= 1.0:
        raise ValueError(
            f"_percentile_nearest_rank: percentile must be in (0, 1], got {percentile}",
        )
    sorted_samples = sorted(samples)
    rank = max(1, math.ceil(percentile * len(sorted_samples)))
    return sorted_samples[rank - 1]


class TonRpcFeeEstimator:
    """Оценщик буфера комиссии на базе исторических газов из TON-RPC.

    Реализует `IFeeEstimator` (`pipirik_wars.domain.monetization.ports`):
    `estimate_fee(currency, target_amount_native) -> int`.

    Поля:
    * `_client: ITonRpcClient` — HTTP-клиент TON-RPC (см. `client.py`).
    * `_settings: TonRpcSettings` — конфигурация (адреса, окно, fallback).

    Stateless по сути (никаких внутренних кэшей в D.5; ожидается, что
    `GeneratePrizeLots`-cron вызывается раз в час, история TON-RPC-вызовов
    — это нагрузка ровно на эти вызовы).

    Безопасно использовать как singleton.
    """

    __slots__ = ("_client", "_settings")

    def __init__(
        self,
        *,
        client: ITonRpcClient,
        settings: TonRpcSettings,
    ) -> None:
        self._client = client
        self._settings = settings

    async def estimate_fee(
        self,
        *,
        currency: Currency,
        target_amount_native: int,
    ) -> int:
        """Вернуть P95-буфер комиссии для будущей выплаты лота.

        Параметры:
        * ``currency`` — валюта будущей выплаты.
        * ``target_amount_native`` — потенциальный размер лота
          (игнорируется в D.5; задел на D.7+, когда оценка станет
          амортизирована по объёму).

        Returns:
        * `int >= 0` — оценка буфера в native-юнитах валюты.

        Поднимает: `TonRpcCallError` / `TonRpcTimeoutError` —
        пробрасывается из `client.recent_fees(...)`.

        Семантика по валюте:
        * `STARS` → `0` (TG-сторона без gas-а).
        * `TON_NANO` → P95 истории по `settings.payout_wallet_address`.
        * `USDT_DECIMAL` → P95 истории по `settings.usdt_jetton_master`.

        На пустой истории — fallback из `settings`.
        """
        if currency is Currency.STARS:
            # TG Stars-refund — Bot API без gas-а. Та же семантика, что у
            # `InMemoryFeeEstimator`.
            return 0

        if currency is Currency.TON_NANO:
            address = self._settings.payout_wallet_address
            fallback = self._settings.fallback_fee_buffer_ton_nano
        else:
            # USDT_DECIMAL — единственная оставшаяся валюта (StrEnum-инвариант
            # — три варианта; первые два обработаны выше).
            address = self._settings.usdt_jetton_master
            fallback = self._settings.fallback_fee_buffer_usdt_decimal

        if not address:
            # Конфигурация неполная (payout_wallet_address пуст для TON_NANO,
            # либо jetton-master пуст для USDT_DECIMAL). Fail-soft → fallback.
            # Логично, потому что отказ от cron-а из-за пустой конфигурации
            # был бы громким, а fallback-у мы доверяем (он совпадает с
            # `InMemoryFeeEstimator`).
            return fallback

        history: list[RecentFee] = list(
            await self._client.recent_fees(
                address=address,
                days=self._settings.fee_window_days,
            )
        )

        if not history:
            return fallback

        fees = [point.fee_native for point in history if point.fee_native >= 0]
        if not fees:
            return fallback

        return _percentile_nearest_rank(fees, percentile=_PERCENTILE)
