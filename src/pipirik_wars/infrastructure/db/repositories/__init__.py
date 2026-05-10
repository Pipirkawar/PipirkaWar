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
from pipirik_wars.infrastructure.db.repositories.boss_fight import (
    SqlAlchemyBossFightRepository,
)
from pipirik_wars.infrastructure.db.repositories.boss_participant import (
    SqlAlchemyBossParticipantRepository,
)
from pipirik_wars.infrastructure.db.repositories.caravan import (
    SqlAlchemyCaravanRepository,
)
from pipirik_wars.infrastructure.db.repositories.caravan_participant import (
    SqlAlchemyCaravanParticipantRepository,
)
from pipirik_wars.infrastructure.db.repositories.clan import (
    SqlAlchemyClanMembershipRepository,
    SqlAlchemyClanRepository,
)
from pipirik_wars.infrastructure.db.repositories.clan_mass_duel_history_query import (
    SqlAlchemyClanMassDuelHistoryQuery,
)
from pipirik_wars.infrastructure.db.repositories.daily_activity import (
    SqlAlchemyDailyActivityRepository,
)
from pipirik_wars.infrastructure.db.repositories.daily_head import (
    SqlAlchemyDailyHeadRepository,
)
from pipirik_wars.infrastructure.db.repositories.dungeon_run import (
    SqlAlchemyDungeonRunRepository,
)
from pipirik_wars.infrastructure.db.repositories.enchant_history import (
    SqlAlchemyEnchantHistoryReader,
)
from pipirik_wars.infrastructure.db.repositories.forest_run import (
    SqlAlchemyForestRunRepository,
)
from pipirik_wars.infrastructure.db.repositories.global_lobby import (
    SqlAlchemyGlobalLobbyRepository,
)
from pipirik_wars.infrastructure.db.repositories.items import (
    SqlAlchemyItemRepository,
)
from pipirik_wars.infrastructure.db.repositories.mountain_run import (
    SqlAlchemyMountainRunRepository,
)
from pipirik_wars.infrastructure.db.repositories.oracle_history import (
    SqlAlchemyOracleHistoryRepository,
)
from pipirik_wars.infrastructure.db.repositories.payments import (
    SqlAlchemyPaymentLedger,
)
from pipirik_wars.infrastructure.db.repositories.player import (
    SqlAlchemyPlayerRepository,
)
from pipirik_wars.infrastructure.db.repositories.pvp_duel import (
    SqlAlchemyDuelRepository,
)
from pipirik_wars.infrastructure.db.repositories.pvp_mass_duel import (
    SqlAlchemyMassDuelRepository,
)
from pipirik_wars.infrastructure.db.repositories.referral import (
    SqlAlchemyReferralRepository,
)
from pipirik_wars.infrastructure.db.repositories.roulette import (
    SqlAlchemyRouletteSpinRepository,
)
from pipirik_wars.infrastructure.db.repositories.scrolls import (
    SqlAlchemyScrollRepository,
)
from pipirik_wars.infrastructure.db.repositories.signup_queue import (
    SqlAlchemySignupQueueRepository,
)

__all__ = [
    "SqlAlchemyActivityLockRepository",
    "SqlAlchemyAdminRepository",
    "SqlAlchemyAnticheatRepository",
    "SqlAlchemyBossFightRepository",
    "SqlAlchemyBossParticipantRepository",
    "SqlAlchemyCaravanParticipantRepository",
    "SqlAlchemyCaravanRepository",
    "SqlAlchemyClanMassDuelHistoryQuery",
    "SqlAlchemyClanMembershipRepository",
    "SqlAlchemyClanRepository",
    "SqlAlchemyDailyActivityRepository",
    "SqlAlchemyDailyHeadRepository",
    "SqlAlchemyDuelRepository",
    "SqlAlchemyDungeonRunRepository",
    "SqlAlchemyEnchantHistoryReader",
    "SqlAlchemyForestRunRepository",
    "SqlAlchemyGlobalLobbyRepository",
    "SqlAlchemyItemRepository",
    "SqlAlchemyMassDuelRepository",
    "SqlAlchemyMountainRunRepository",
    "SqlAlchemyOracleHistoryRepository",
    "SqlAlchemyPaymentLedger",
    "SqlAlchemyPlayerRepository",
    "SqlAlchemyReferralRepository",
    "SqlAlchemyRouletteSpinRepository",
    "SqlAlchemyScrollRepository",
    "SqlAlchemySignupQueueRepository",
]
