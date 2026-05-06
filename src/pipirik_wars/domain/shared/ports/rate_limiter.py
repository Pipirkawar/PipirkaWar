"""Порт rate-limiter-а (Спринт 2.4.F).

Интерфейс для token-bucket-а / Redis-rate-limiter-а / любого другого
«ключ-в-ведро»-механизма. Используется в:

- `bot/middlewares/throttle.py` — глобальный per-user-throttle aiogram-update-ов
  (Спринт 1.1.C, key = `f"player:{tg_user_id}"`);
- `application/referral/register.py` — антифрод per-`referrer_tg_id` (Спринт 2.4.F,
  key = `f"referral:{referrer_tg_id}"`).

Sync-интерфейс (а не async) — token-bucket-логика in-memory работает за
константное время, и оборачивать в `await` бессмысленно. Redis-backend
для multi-worker-deploy-а (будущий Спринт 2.x) добавит `aioredis.eval(...)`
внутри той же sync-сигнатуры (через `loop.run_until_complete`) или даст
отдельный `IAsyncRateLimiter` — это будет решено при необходимости.
"""

from __future__ import annotations

import abc


class IRateLimiter(abc.ABC):
    """Порт rate-limiter-а: «дай токен по ключу или откажи»."""

    @abc.abstractmethod
    def try_acquire(self, *, key: str) -> bool:
        """Попытаться «взять» токен. `True` — пропускаем; `False` — отказ.

        Reference-реализация — token-bucket
        (`infrastructure/rate_limit/token_bucket.py`). Конкретные параметры
        (capacity, refill_per_second) задаются на уровне DI; sами use-cases /
        middleware-ы ничего про них не знают.
        """


__all__ = ["IRateLimiter"]
