"""In-memory реализация `IFeeEstimator` (Спринт 4.1-C, шаг C.7.a).

Возвращает фиксированную константу per currency. Контракт порта
(`pipirik_wars.domain.monetization.ports.IFeeEstimator`) предписывает
P95-оценку газа за 7 дней — это требует обращения к TON RPC и
скользящего окна. На 4.1-C такой телеметрии ещё нет: реализация
константная, значения подобраны как консервативный upper-bound по
публично доступным данным сети TON на конец 2025 — начало 2026.

| Currency | Константа | Эквивалент | Обоснование |
|---|---|---|---|
| `STARS` | `0` | 0 ⭐ | TG-сторона не берёт gas — Stars-refund в Bot API без комиссии (см. ГДД §12.6.3 / §12.6.4 п. 4). |
| `TON_NANO` | `10_000_000` | 0.01 TON | Plain-TON-перевод (`internal_message`) типично 0.0033–0.006 TON. Запас ~2× от среднего → ~P95. |
| `USDT_DECIMAL` | `200_000` | 0.2 USDT | USDT-jetton-перевод на TON стоит ~0.05–0.1 TON газа (~$0.10–$0.20). Буфер хранится в native-юнитах USDT для удобства декремента из самого лота; на 4.1-D `ClaimPrize` конвертирует в TON по spot-курсу. Запас ~2× от среднего → ~P95. |

TODO(balance): зафиксировать конкретные значения после того, как
4.1-D реальный `TonRpcFeeEstimator` соберёт ≥ 7 суток исторических
газовых данных. Тогда константы либо переедут в `balance.yaml`
(hot-reload), либо целиком замещаются RPC-имплементацией. Сейчас
константы — единственная имплементация в проде; cron-у
`GeneratePrizeLots` (4.1-C / C.7.b) их хватает.

См. также ГДД §12.6.3 «Лоты: как пул превращается в призы»
и контракт `IFeeEstimator.estimate_fee` в
`domain/monetization/ports.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from pipirik_wars.domain.monetization.value_objects import Currency

__all__ = ["InMemoryFeeEstimator"]

# Константные оценки газового буфера per currency. Все значения — в
# native-юнитах валюты (см. `Currency` docstring). См. таблицу в
# module-docstring-е выше для обоснования.
_FEE_BUFFER_NATIVE: Mapping[Currency, int] = MappingProxyType(
    {
        # STARS: TG-сторона не берёт gas-а. Stars-refund в Bot API
        # бесплатен, поэтому буфер = 0.
        Currency.STARS: 0,
        # TON_NANO: 0.01 TON ≈ ~P95 plain-TON-перевода.
        # TODO(balance): подтвердить P95 на 7 днях после 4.1-D RPC-сбора.
        Currency.TON_NANO: 10_000_000,
        # USDT_DECIMAL: 0.2 USDT-decimal — буфер для покрытия TON-газа
        # jetton-перевода (~0.05–0.1 TON ≈ $0.10–0.20). Native-юниты USDT
        # ради простоты декремента из самого лота; конверсия в TON на
        # выплате — забота `ClaimPrize` (4.1-D).
        # TODO(balance): подтвердить P95 на 7 днях после 4.1-D RPC-сбора.
        Currency.USDT_DECIMAL: 200_000,
    }
)


class InMemoryFeeEstimator:
    """Константный `IFeeEstimator` (Спринт 4.1-C).

    Возвращает фиксированную оценку per currency, игнорируя
    `target_amount_native`. На 4.1-D реализация заменяется на
    `TonRpcFeeEstimator` (P95 за 7 дней через TON RPC); контракт
    порта остаётся прежним, реализация подменяется в composition
    root (`bot/main.py`).

    Класс — stateless и без зависимостей: всё, что нужно, —
    словарь констант на уровне модуля. Безопасно использовать как
    singleton.
    """

    __slots__ = ()

    async def estimate_fee(
        self,
        *,
        currency: Currency,
        target_amount_native: int,
    ) -> int:
        """Вернуть константную оценку буфера комиссии для `currency`.

        Параметры:
        - `currency` — валюта будущей выплаты лота.
        - `target_amount_native` — потенциальный размер лота в native-
          юнитах. На 4.1-C игнорируется (константная оценка); на 4.1-D
          используется реальным `TonRpcFeeEstimator` (jetton-комиссия
          USDT-перевода зависит от суммы).

        Returns:
        - `int >= 0` — буфер в native-юнитах валюты. Для `STARS` —
          всегда `0`; для `TON_NANO` / `USDT_DECIMAL` — позитивный
          (см. константы в module-docstring-е).

        Не поднимает исключений: `currency` — `StrEnum`, все три значения
        покрыты словарём `_FEE_BUFFER_NATIVE`. `target_amount_native`
        не валидируется (контракт порта оставляет валидацию caller-у —
        `GeneratePrizeLots`).
        """
        return _FEE_BUFFER_NATIVE[currency]
