"""ORM-модели проекта.

Подсистема безопасности (Спринт 0.2):
- `IdempotencyKeyORM` — таблица `idempotency_keys`.
- `AuditLogORM` — таблица `audit_log`.
- `ActivityLockORM` — таблица `activity_locks`.
- `AdminORM` — таблица `admins`.
- `AdminAuditLogORM` — таблица `admin_audit_log` (Спринт 2.5-A.1).

Игрок/клан (Спринт 1.1):
- `UserORM` — таблица `users`.
- `ClanORM` — таблица `clans`.
- `ClanMemberORM` — таблица `clan_members`.

Регистрация (Спринт 1.2):
- `SignupQueueORM` — таблица `signup_queue`.

Лес (Спринт 1.3):
- `ForestRunORM` — таблица `forest_runs`.

Предсказатель (Спринт 1.4.B):
- `OracleInvocationORM` — таблица `oracle_invocations`.

PvP 1×1 (Спринт 2.1.C):
- `PvpDuelORM` — таблица `pvp_duels`.
- `PvpDuelRoundORM` — таблица `pvp_duel_rounds`.

PvP global lobby (Спринт 2.1.F):
- `PvpGlobalLobbyORM` — таблица `pvp_global_lobby` (FIFO-очередь pending-вызовов GLOBAL_ONLY).

PvP массовый клан×клан (Спринт 2.2.D):
- `PvpMassDuelORM` — таблица `pvp_mass_duels`.
- `PvpMassDuelChoiceORM` — таблица `pvp_mass_duel_choices`.
- `PvpMassDuelDamageEntryORM` — таблица `pvp_mass_duel_damage_entries`.

Глава клана дня (Спринт 2.3.B):
- `DailyHeadAssignmentORM` — таблица `daily_heads`.
- `DailyActiveORM` — таблица `daily_active`.

Реферальная система (Спринт 2.4.B):
- `ReferralORM` — таблица `referrals`.
"""

from pipirik_wars.infrastructure.db.models.admin import AdminORM
from pipirik_wars.infrastructure.db.models.admin_audit import AdminAuditLogORM
from pipirik_wars.infrastructure.db.models.boss import (
    BossFightORM,
    BossParticipantORM,
)
from pipirik_wars.infrastructure.db.models.caravan import (
    CaravanORM,
    CaravanParticipantORM,
)
from pipirik_wars.infrastructure.db.models.clan import ClanMemberORM, ClanORM
from pipirik_wars.infrastructure.db.models.daily_active import DailyActiveORM
from pipirik_wars.infrastructure.db.models.daily_head import DailyHeadAssignmentORM
from pipirik_wars.infrastructure.db.models.forest import ForestRunORM
from pipirik_wars.infrastructure.db.models.oracle import OracleInvocationORM
from pipirik_wars.infrastructure.db.models.player import UserORM
from pipirik_wars.infrastructure.db.models.pve_runs import (
    DungeonRunORM,
    MountainRunORM,
)
from pipirik_wars.infrastructure.db.models.pvp import (
    PvpDuelORM,
    PvpDuelRoundORM,
    PvpGlobalLobbyORM,
    PvpMassDuelChoiceORM,
    PvpMassDuelDamageEntryORM,
    PvpMassDuelORM,
)
from pipirik_wars.infrastructure.db.models.referral import ReferralORM
from pipirik_wars.infrastructure.db.models.security import (
    ActivityLockORM,
    AuditLogORM,
    IdempotencyKeyORM,
)
from pipirik_wars.infrastructure.db.models.signup_queue import SignupQueueORM

__all__ = [
    "ActivityLockORM",
    "AdminAuditLogORM",
    "AdminORM",
    "AuditLogORM",
    "BossFightORM",
    "BossParticipantORM",
    "CaravanORM",
    "CaravanParticipantORM",
    "ClanMemberORM",
    "ClanORM",
    "DailyActiveORM",
    "DailyHeadAssignmentORM",
    "DungeonRunORM",
    "ForestRunORM",
    "IdempotencyKeyORM",
    "MountainRunORM",
    "OracleInvocationORM",
    "PvpDuelORM",
    "PvpDuelRoundORM",
    "PvpGlobalLobbyORM",
    "PvpMassDuelChoiceORM",
    "PvpMassDuelDamageEntryORM",
    "PvpMassDuelORM",
    "ReferralORM",
    "SignupQueueORM",
    "UserORM",
]
