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
    FOREST_RUN_STARTED = "forest_run_started"
    ADMIN_COMMAND = "admin_command"


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """Запись аудит-лога.

    `before`/`after` хранятся как сериализуемые dict-ы (или None для
    «не применимо»). Реализация конвертирует их в JSONB-колонку.
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


class IAuditLogger(abc.ABC):
    """Интерфейс аудит-логгера."""

    @abc.abstractmethod
    async def record(self, entry: AuditEntry) -> None:
        """Записать одно событие.

        Вызывается из use-case **внутри** транзакции (`IUnitOfWork`).
        Любая ошибка записи аудита откатывает всю операцию — это by design.
        """
