"""In-process token-bucket rate-limiter.

Подходит как «первая защита» от спама. Production-вариант (Redis-backed)
появится в Спринте 2.x — здесь мы готовим Protocol-интерфейс, чтобы
переключение было прозрачным.
"""

from pipirik_wars.infrastructure.rate_limit.token_bucket import (
    InMemoryTokenBucketRateLimiter,
    IRateLimiter,
)

__all__ = ["IRateLimiter", "InMemoryTokenBucketRateLimiter"]
