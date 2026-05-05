"""Реализации доменных репозиториев поверх SQLAlchemy."""

from pipirik_wars.infrastructure.db.repositories.activity_lock import (
    SqlAlchemyActivityLockRepository,
)
from pipirik_wars.infrastructure.db.repositories.admin import (
    SqlAlchemyAdminRepository,
)
from pipirik_wars.infrastructure.db.repositories.anticheat import (
    SqlAlchemyAnticheatRepository,
)
from pipirik_wars.infrastructure.db.repositories.clan import (
    SqlAlchemyClanMembershipRepository,
    SqlAlchemyClanRepository,
)
from pipirik_wars.infrastructure.db.repositories.forest_run import (
    SqlAlchemyForestRunRepository,
)
from pipirik_wars.infrastructure.db.repositories.oracle_history import (
    SqlAlchemyOracleHistoryRepository,
)
from pipirik_wars.infrastructure.db.repositories.player import (
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.repositories.pvp_duel import (
    SqlAlchemyDuelRepository,
)
from pipirik_wars.infrastructure.db.repositories.signup_queue import (
    SqlAlchemySignupQueueRepository,
)

__all__ = [
    "SqlAlchemyActivityLockRepository",
    "SqlAlchemyAdminRepository",
    "SqlAlchemyAnticheatRepository",
    "SqlAlchemyClanMembershipRepository",
    "SqlAlchemyClanRepository",
    "SqlAlchemyDuelRepository",
    "SqlAlchemyForestRunRepository",
    "SqlAlchemyOracleHistoryRepository",
    "SqlAlchemyPlayerRepository",
    "SqlAlchemySignupQueueRepository",
]
