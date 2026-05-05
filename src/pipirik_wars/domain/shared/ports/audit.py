"""Audit-лог. Каждая мутация состояния пишется атомарно вместе с самой
операцией.

ГДД §0 (политика разработки) и §18.6.4 (безопасность админки) делают
аудит обязательным:

- любое изменение длины/толщины/титула игрока;
- любое назначение Главы клана дня;
- любое реферальное начисление;
- любая админ-команда (`/admin_*`).

Запись в `audit_log` идёт **в той же транзакции**, что и сама мутация
(см. `IUnitOfWork`). Это исключает «потерянный аудит» при сбое после
коммита бизнес-таблицы.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass
from datetime import datetime


class AuditAction(str, enum.Enum):
    """Категории аудит-событий.

    Расширяется по мере появления новых use-cases. Пока — только
    общие категории, конкретные `reason` передаются отдельным полем.
    """

    LENGTH_GRANT = "length_grant"
    LENGTH_REVOKE = "length_revoke"
    THICKNESS_UPGRADE = "thickness_upgrade"
    TITLE_GRANT = "title_grant"
    NAME_GRANT = "name_grant"
    DAILY_HEAD_ASSIGN = "daily_head_assign"
    REFERRAL_MILESTONE = "referral_milestone"
    PLAYER_REGISTER = "player_register"
    CLAN_REGISTER = "clan_register"
    CLAN_MIGRATE = "clan_migrate"
    CLAN_MEMBER_JOIN = "clan_member_join"
    CLAN_FREEZE = "clan_freeze"
    CLAN_UNFREEZE = "clan_unfreeze"
    BALANCE_RELOAD = "balance_reload"
    DAU_LIMIT_CHANGE = "dau_limit_change"
    DAU_THRESHOLD_REACHED = "dau_threshold_reached"
    PLAYER_QUEUED = "player_queued"
    PLAYER_PROMOTED = "player_promoted"
    PLAYER_LOCALE_SET = "player_locale_set"
    FOREST_RUN_STARTED = "forest_run_started"
    ADMIN_COMMAND = "admin_command"
    # ── Спринт 1.6 (anti-cheat hardcap, ГДД §3.3) ──
    ANTICHEAT_DAILY_CAP_EXCEEDED = "anticheat_daily_cap_exceeded"
    ANTICHEAT_WEEKLY_CAP_EXCEEDED = "anticheat_weekly_cap_exceeded"
    ANTICHEAT_BAN_LIFTED = "anticheat_ban_lifted"


class AuditSource(str, enum.Enum):
    """Источник аудит-записи (ГДД §3.3.4 / development_plan.md §4 ПД 1.6.1).

    Anti-cheat hardcap различает «органические» источники (forest, oracle,
    referral_*) от «донатных» (stars/ton/usdt) и админских (admin_grant,
    admin_refund) — клампятся **только** organic-источники. Whitelist
    жёстко зашит здесь и в БД-CHECK-инвариант, чтобы случайная опечатка
    в `source="forst"` не вывалила запись из агрегации anti-cheat-окна.

    `UNKNOWN` — маркер для записей до Спринта 1.6.A; миграция backfill-ит
    им все исторические строки. Новые записи в норме должны указывать
    конкретный источник; сейчас (1.6.A) дефолт — `UNKNOWN`, чтобы старые
    use-cases работали без правок до миграции в Спринте 1.6.F.
    """

    FOREST = "forest"
    ORACLE = "oracle"
    REFERRAL_SIGNUP = "referral_signup"
    REFERRAL_THICKNESS = "referral_thickness"
    PVP_REWARD = "pvp_reward"
    CARAVAN_REWARD = "caravan_reward"
    RAID_REWARD = "raid_reward"
    ADMIN_GRANT = "admin_grant"
    ADMIN_REFUND = "admin_refund"
    STARS_PAYMENT = "stars_payment"
    TON_PAYMENT = "ton_payment"
    USDT_PAYMENT = "usdt_payment"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """Запись аудит-лога.

    `before`/`after` хранятся как сериализуемые dict-ы (или None для
    «не применимо»). Реализация конвертирует их в JSONB-колонку.

    `source` — добавлен в Спринте 1.6.A (anti-cheat hardcap). Дефолт
    `AuditSource.UNKNOWN` — для бэк-совместимости со старыми вызовами;
    в Спринте 1.6.F все use-cases будут переведены на явное указание
    источника через `progression.add_length(...)`.

    `clamped_from` — `None`, если дельта не клампилась; число (исходная
    запрошенная дельта в см), если `progression.add_length` подрезал
    её под `daily_cap_cm` / `weekly_cap_cm`. Заполняется только в
    Спринте 1.6.D; до этого всегда `None`.
    """

    action: AuditAction
    actor_id: int | None
    target_kind: str
    target_id: str
    before: dict[str, object] | None
    after: dict[str, object] | None
    reason: str
    idempotency_key: str | None
    occurred_at: datetime
    source: AuditSource = AuditSource.UNKNOWN
    clamped_from: int | None = None


class IAuditLogger(abc.ABC):
    """Интерфейс аудит-логгера."""

    @abc.abstractmethod
    async def record(self, entry: AuditEntry) -> None:
        """Записать одно событие.

        Вызывается из use-case **внутри** транзакции (`IUnitOfWork`).
        Любая ошибка записи аудита откатывает всю операцию — это by design.
        """
