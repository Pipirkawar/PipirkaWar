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
from datetime import UTC, date, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

_MINUTES_IN_DAY: Final[int] = 24 * 60
_MOSCOW_TZ: Final[ZoneInfo] = ZoneInfo("Europe/Moscow")


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


def compute_daily_head_cron_run_at_utc(
    *,
    clan_id: int,
    moscow_date: date,
) -> datetime:
    """Вернуть момент срабатывания cron-а в UTC для данного клана и даты.

    Equivalent to ``00:00 Europe/Moscow + offset_minutes`` переведённое в UTC.
    Учитывает DST-сдвиги внутри `Europe/Moscow` (через `zoneinfo`); так как
    Москва перешла на постоянное `+03:00` в 2014 году, фактически это
    всегда `(midnight_msk - 3h)` в UTC, но мы держим обобщённый расчёт
    для совместимости с возможными правками IANA.

    :param clan_id: внутренний id клана.
    :param moscow_date: календарная дата в `Europe/Moscow`.
    :return: tz-aware `datetime` в UTC.
    """
    offset_minutes = compute_daily_head_cron_offset_minutes(
        clan_id=clan_id,
        moscow_date=moscow_date,
    )
    msk_midnight = datetime(
        moscow_date.year,
        moscow_date.month,
        moscow_date.day,
        tzinfo=_MOSCOW_TZ,
    )
    return (msk_midnight + timedelta(minutes=offset_minutes)).astimezone(UTC)


__all__ = [
    "compute_daily_head_cron_offset_minutes",
    "compute_daily_head_cron_run_at_utc",
]
