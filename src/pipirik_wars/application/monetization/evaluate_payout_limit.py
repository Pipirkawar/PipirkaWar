"""Use-case ``EvaluatePayoutLimit`` (Спринт 4.1-E / Шаг E.6, ГДД §12.6.5).

Реализация порта :class:`IPayoutLimitChecker` (доменный Protocol из
``domain/monetization/ports.py``) поверх:

* :class:`IBalanceConfig` — даёт `monetization.payout_limit` (per-currency
  `window_days` / `max_amount_native`);
* :class:`IPrizeLotRepository.sum_claimed_in_window` /
  :class:`IPrizeLotRepository.oldest_claimed_at_in_window` —
  rolling-window-агрегаты по CLAIMED-лотам игрока.

Семантика (см. ГДД §12.6.5 «KYC / антифрод / лимиты»):

1. Из :class:`IBalanceConfig.get().monetization.payout_limit.get(currency)`
   достаём конфиг лимита для валюты. Если ``None`` (currency не
   перечислена в `per_currency`) — это семантика *unlimited*, возвращаем
   ``PayoutLimitWithin(remaining_native=sys.maxsize)``.
2. Иначе вычисляем `since = now - timedelta(days=window_days)`, тянем
   `already_claimed = repo.sum_claimed_in_window(...)`, вычисляем
   `would_be = already_claimed + amount_native`.
3. Если ``would_be <= max_amount_native`` — игрок умещается в лимит:
   возвращаем ``PayoutLimitWithin(remaining_native = max - would_be)``.
4. Иначе игрок не умещается: тянем ``oldest = repo.oldest_claimed_at_in_window(
   ...)``. ``retry_after`` — момент, в который самый ранний CLAIMED-лот
   выпадет из окна (`oldest + timedelta(days=window_days)`). Это
   гарантирует: после этого момента сумма в окне станет
   ``would_be - oldest.amount_native`` (или меньше), и проверка может
   пройти. Если ``oldest is None`` (теоретически невозможный fallback
   при ``already_claimed > 0`` — может означать гонку выплат) —
   фолбекаемся на ``Within(remaining = max)``, чтобы не запирать игрока
   из-за inconsistency в хранилище.

Use-case **не** изменяет состояние (read-only) — не требует UoW,
audit-логирования (это сторона `ClaimPrize`-flow, шаг E.10).

Параметры контракта (`IPayoutLimitChecker.check`):

* ``player_id: int`` — id игрока (`> 0`, валидирует caller).
* ``currency: Currency`` — крипто-валюта выплаты. Для STARS контракт
  допускает любую реализацию; данная реализация возвращает то, что
  предписывает конфиг (если STARS-лимит когда-то будет добавлен — пока
  pydantic-схема `PayoutLimitConfig` отвергает STARS).
* ``amount_native: int`` — потенциальная новая выплата. Должен быть `>= 1`.
* ``now: datetime`` — TZ-aware момент-проверки (caller передаёт
  ``IClock.now()``; use-case использует для вычисления `since = now - window`).

Возврат — sum-type ``PayoutLimitCheckResult`` (Within | OverLimit).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.monetization.ports import (
    IPayoutLimitChecker,
    IPrizeLotRepository,
)
from pipirik_wars.domain.monetization.value_objects import (
    Currency,
    PayoutLimitCheckResult,
    PayoutLimitOverLimit,
    PayoutLimitWithin,
)

__all__ = ["EvaluatePayoutLimit"]


class EvaluatePayoutLimit(IPayoutLimitChecker):
    """Rolling-window-проверка лимита выплат (per-currency, per-player).

    Зависимости:

    * ``lot_repo: IPrizeLotRepository`` — даёт ``sum_claimed_in_window`` и
      ``oldest_claimed_at_in_window`` по CLAIMED-лотам.
    * ``balance_config: IBalanceConfig`` — даёт текущий снимок
      `monetization.payout_limit` (per-currency window/max).

    Конструируется в composition root (шаг E.15) и пробрасывается в
    ``ClaimPrize`` (шаг E.10) как реализация :class:`IPayoutLimitChecker`.
    """

    __slots__ = ("_balance_config", "_lot_repo")

    def __init__(
        self,
        *,
        lot_repo: IPrizeLotRepository,
        balance_config: IBalanceConfig,
    ) -> None:
        self._lot_repo = lot_repo
        self._balance_config = balance_config

    async def check(
        self,
        *,
        player_id: int,
        currency: Currency,
        amount_native: int,
        now: datetime,
    ) -> PayoutLimitCheckResult:
        """Проверить, умещается ли потенциальная выплата в rolling-окно.

        Возвращает :class:`PayoutLimitWithin` либо
        :class:`PayoutLimitOverLimit`. Не изменяет состояние.
        """
        cfg = self._balance_config.get().monetization.payout_limit.get(currency)
        if cfg is None:
            # Валюта не перечислена в конфиге → unlimited (по контракту
            # `IPayoutLimitChecker.check` docstring + ГДД §12.6.5: «KYC-
            # лимиты только для крипто-выплат TON / USDT; STARS — TG-
            # рефанд»).
            return PayoutLimitWithin(remaining_native=sys.maxsize)

        since = now - timedelta(days=cfg.window_days)
        already_claimed = await self._lot_repo.sum_claimed_in_window(
            player_id=player_id,
            currency=currency,
            since=since,
        )
        would_be = already_claimed + amount_native
        if would_be <= cfg.max_amount_native:
            return PayoutLimitWithin(
                remaining_native=cfg.max_amount_native - would_be,
            )

        # Over-limit: вычисляем `retry_after`.
        oldest = await self._lot_repo.oldest_claimed_at_in_window(
            player_id=player_id,
            currency=currency,
            since=since,
        )
        if oldest is None:
            # Inconsistency в repo: `sum_claimed > 0` но `oldest is None` —
            # теоретически невозможно. Фолбекаемся на `Within`, чтобы не
            # блокировать игрока из-за ошибки хранилища.
            return PayoutLimitWithin(
                remaining_native=cfg.max_amount_native,
            )

        retry_after = oldest + timedelta(days=cfg.window_days)
        return PayoutLimitOverLimit(
            retry_after=retry_after,
            exceeded_by_native=would_be - cfg.max_amount_native,
        )
