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
    # ── Спринт 3.1-B (PvE: горы и данжон, ГДД §8) ──
    MOUNTAIN_RUN_STARTED = "mountain_run_started"
    MOUNTAIN_RUN_FINISHED = "mountain_run_finished"
    DUNGEON_RUN_STARTED = "dungeon_run_started"
    DUNGEON_RUN_FINISHED = "dungeon_run_finished"
    ADMIN_COMMAND = "admin_command"
    # ── Спринт 1.6 (anti-cheat hardcap, ГДД §3.3) ──
    ANTICHEAT_DAILY_CAP_EXCEEDED = "anticheat_daily_cap_exceeded"
    ANTICHEAT_WEEKLY_CAP_EXCEEDED = "anticheat_weekly_cap_exceeded"
    ANTICHEAT_BAN_LIFTED = "anticheat_ban_lifted"
    # ── Спринт 2.1 (PvP 1×1, ГДД §7.1) ──
    PVP_DUEL_CREATED = "pvp_duel_created"
    PVP_DUEL_ACCEPTED = "pvp_duel_accepted"
    PVP_DUEL_CANCELLED = "pvp_duel_cancelled"
    PVP_DUEL_COMPLETED = "pvp_duel_completed"
    # ── Спринт 2.1.F.2 (глобальное лобби PvP) ──
    PVP_LOBBY_ENQUEUED = "pvp_lobby_enqueued"
    PVP_LOBBY_MATCHED = "pvp_lobby_matched"
    PVP_LOBBY_ESCALATED = "pvp_lobby_escalated"
    PVP_LOBBY_EXPIRED = "pvp_lobby_expired"
    # ── Спринт 2.2 (масс-PvP клан×клан, ГДД §7.2) ──
    PVP_MASS_DUEL_CREATED = "pvp_mass_duel_created"
    PVP_MASS_DUEL_COMPLETED = "pvp_mass_duel_completed"
    PVP_MASS_DUEL_CANCELLED = "pvp_mass_duel_cancelled"
    # ── Спринт 2.4 (реферальная система, ГДД §13.1) ──
    REFERRAL_REGISTERED = "referral_registered"
    REFERRAL_RATE_LIMITED = "referral_rate_limited"
    # ── Спринт 3.2-B (караваны, ГДД §9) ──
    CARAVAN_CREATED = "caravan_created"
    CARAVAN_PLAYER_JOINED = "caravan_player_joined"
    CARAVAN_PLAYER_LEFT = "caravan_player_left"
    CARAVAN_LOBBY_CLOSED = "caravan_lobby_closed"
    # ── Спринт 3.2-C (караваны: бой + награды + отмена, ГДД §9.5–§9.6) ──
    CARAVAN_BATTLE_FINISHED = "caravan_battle_finished"
    CARAVAN_REWARDS_GRANTED = "caravan_rewards_granted"
    CARAVAN_CANCELLED = "caravan_cancelled"


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
    MOUNTAINS = "mountains"
    DUNGEON = "dungeon"
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
    # ── Спринт 2.3 (Глава клана дня, ГДД §6.1) ──
    DAILY_HEAD = "daily_head"
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

    `delta_cm` — фактически применённая дельта длины (знаковая, в см).
    `None` для не-длиновых событий (`clan_register`, `balance_reload`,
    `player_locale_set` и т. п.). Anti-cheat rolling-окно (Спринт 1.6.C)
    суммирует `delta_cm > 0` с фильтром по `source IN organic_sources`.
    Заполняется в Спринте 1.6.D через `progression.add_length`; до того
    момента старые `LENGTH_GRANT`-вызовы в `RegisterPlayer`/`InvokeOracle`/
    `FinishForestRun` явно прокидывают `delta_cm` для интеграции с anti-cheat.
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
    delta_cm: int | None = None


class IAuditLogger(abc.ABC):
    """Интерфейс аудит-логгера."""

    @abc.abstractmethod
    async def record(self, entry: AuditEntry) -> None:
        """Записать одно событие.

        Вызывается из use-case **внутри** транзакции (`IUnitOfWork`).
        Любая ошибка записи аудита откатывает всю операцию — это by design.
        """
