"""ORM-модели проекта.

Подсистема безопасности (Спринт 0.2):
- `IdempotencyKeyORM` — таблица `idempotency_keys`.
- `AuditLogORM` — таблица `audit_log`.
- `ActivityLockORM` — таблица `activity_locks`.
- `AdminORM` — таблица `admins`.

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
"""

from pipirik_wars.infrastructure.db.models.admin import AdminORM
from pipirik_wars.infrastructure.db.models.clan import ClanMemberORM, ClanORM
from pipirik_wars.infrastructure.db.models.forest import ForestRunORM
from pipirik_wars.infrastructure.db.models.oracle import OracleInvocationORM
from pipirik_wars.infrastructure.db.models.player import UserORM
from pipirik_wars.infrastructure.db.models.pvp import (
    PvpDuelORM,
    PvpDuelRoundORM,
    PvpGlobalLobbyORM,
)
from pipirik_wars.infrastructure.db.models.security import (
    ActivityLockORM,
    AuditLogORM,
    IdempotencyKeyORM,
)
from pipirik_wars.infrastructure.db.models.signup_queue import SignupQueueORM

__all__ = [
    "ActivityLockORM",
    "AdminORM",
    "AuditLogORM",
    "ClanMemberORM",
    "ClanORM",
    "ForestRunORM",
    "IdempotencyKeyORM",
    "OracleInvocationORM",
    "PvpDuelORM",
    "PvpDuelRoundORM",
    "PvpGlobalLobbyORM",
    "SignupQueueORM",
    "UserORM",
]
