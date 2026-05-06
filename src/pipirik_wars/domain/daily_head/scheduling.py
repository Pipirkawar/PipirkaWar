"""Детерминированный per-clan offset для cron-а «Главы клана дня».

Спринт 2.3.F.2 / ПД §6.2.3.3 / ГДД §6.1.

Cron-шедулер APScheduler не может одновременно выстрелить во все кланы
в 00:00 МСК — это создаст шторм нагрузки на БД и Telegram API. Поэтому
для каждого клана вычисляется уникальный offset 0..24h от 00:00 МСК,
детерминированный по паре `(clan_id, moscow_date)`:

* воспроизводимость — тесты могут проверить точное время срабатывания;
* стабильность по дням — каждый день у клана новый offset (нет паттерна
  «ровно в 14:37 каждый день»);
* равномерное распределение — sha256 модуло 24*60 даёт практически
  uniform-распределение по минутам суток.

Используется application-use-case-ом, который при старте бота и при
ежесуточном перепланировании регистрирует APScheduler-job-ы.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Final

_MINUTES_IN_DAY: Final[int] = 24 * 60


def compute_daily_head_cron_offset_minutes(
    *,
    clan_id: int,
    moscow_date: date,
) -> int:
    """Вернуть offset в минутах от 00:00 МСК для данной пары `(clan_id, date)`.

    Алгоритм: `sha256(f"{clan_id}:{moscow_date.isoformat()}").digest()` →
    первые 8 байт как big-endian unsigned int → modulo `24 * 60`.

    :param clan_id: внутренний id клана (положительный, как и в БД).
    :param moscow_date: календарная дата в `Europe/Moscow` (`IClock.moscow_date()`).
    :return: целое число в диапазоне `[0, 24*60)` — минут от 00:00 МСК.
    """
    if clan_id <= 0:
        raise ValueError(f"clan_id must be positive, got {clan_id}")
    payload = f"{clan_id}:{moscow_date.isoformat()}".encode()
    digest = hashlib.sha256(payload).digest()
    bucket = int.from_bytes(digest[:8], byteorder="big", signed=False)
    return bucket % _MINUTES_IN_DAY


__all__ = ["compute_daily_head_cron_offset_minutes"]
