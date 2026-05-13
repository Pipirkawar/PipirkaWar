"""Use-case: собрать агрегированную статистику для дашборда (Спринт 4.5-C, ПД §7 задача 4.5.4).

Виджеты:
- DAU / MAU / concurrent (из ``daily_active`` + ``users``)
- Очередь регистраций (из ``signup_queue``)
- Активные караваны / рейды (из ``caravans`` / ``boss_fights``)
- Последние ошибки (из ``admin_audit_log``)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


@dataclass(frozen=True, slots=True)
class DashboardStats:
    """DTO с виджетами дашборда."""

    dau: int
    mau: int
    total_players: int
    signup_queue_size: int
    active_caravans: int
    active_raids: int
    recent_errors: tuple[ErrorEntry, ...]


@dataclass(frozen=True, slots=True)
class ErrorEntry:
    """Запись ошибки / админ-действия для виджета «Последние ошибки»."""

    occurred_at: datetime
    action: str
    admin_id: int
    target_kind: str
    target_id: str
    reason: str


def today_msk() -> date:
    """Текущая дата по московскому времени (UTC+3)."""
    msk = timezone(timedelta(hours=3))
    return datetime.now(tz=msk).date()


def thirty_days_ago_msk() -> date:
    """Дата 30 дней назад по МСК."""
    return today_msk() - timedelta(days=30)
