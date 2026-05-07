"""bot/presenters package.

Тонкие классы/функции рендеринга `ProfileView`/`ClanCard`/… в строки
для `message.answer(...)`. Не содержат I/O и не работают с aiogram-объектами
напрямую — это делает handler.

С 1.5.E все презентеры — `*Presenter`-классы с DI `IMessageBundle`
(см. `application/i18n/`). Pure-функции остались только для
`callback_data`-сериализации (она не зависит от локали — см.
`forest_callback_data` / `upgrade_callback_data`).
"""

from pipirik_wars.bot.presenters._pve import (
    PveCallbackAction,
    PveCallbackData,
    PvePresenter,
    is_pve_callback,
    parse_pve_callback_data,
    pve_callback_data,
)
from pipirik_wars.bot.presenters.clan_head import ClanHeadPresenter
from pipirik_wars.bot.presenters.clan_history import ClanHistoryPresenter
from pipirik_wars.bot.presenters.clantop import ClanTopPresenter
from pipirik_wars.bot.presenters.duel import (
    AcceptCallbackData,
    AttackCallbackData,
    BlockCallbackData,
    DuelPresenter,
    RejectCallbackData,
    ShareCallbackData,
    accept_callback_data,
    attack_callback_data,
    block_callback_data,
    parse_accept_callback_data,
    parse_attack_callback_data,
    parse_block_callback_data,
    parse_reject_callback_data,
    parse_share_callback_data,
    reject_callback_data,
    share_callback_data,
)
from pipirik_wars.bot.presenters.dungeon import DungeonPresenter
from pipirik_wars.bot.presenters.forest import (
    ForestCallbackAction,
    ForestCallbackData,
    ForestPresenter,
    forest_callback_data,
    parse_forest_callback_data,
)
from pipirik_wars.bot.presenters.mass_duel import (
    MassAttackCallbackData,
    MassBlockCallbackData,
    MassDuelPresenter,
    mass_attack_callback_data,
    mass_block_callback_data,
    parse_mass_attack_callback_data,
    parse_mass_block_callback_data,
)
from pipirik_wars.bot.presenters.mountains import MountainsPresenter
from pipirik_wars.bot.presenters.oracle import OraclePresenter
from pipirik_wars.bot.presenters.profile import ProfilePresenter
from pipirik_wars.bot.presenters.referral_share import (
    ReferralShareCallbackData,
    ReferralSharePresenter,
    ShareKind,
    parse_referral_share_callback_data,
    referral_share_callback_data,
)
from pipirik_wars.bot.presenters.top import TopPresenter
from pipirik_wars.bot.presenters.upgrade import (
    UpgradeCallbackAction,
    UpgradeCallbackData,
    UpgradePresenter,
    parse_upgrade_callback_data,
    upgrade_callback_data,
)

__all__ = [
    "AcceptCallbackData",
    "AttackCallbackData",
    "BlockCallbackData",
    "ClanHeadPresenter",
    "ClanHistoryPresenter",
    "ClanTopPresenter",
    "DuelPresenter",
    "DungeonPresenter",
    "ForestCallbackAction",
    "ForestCallbackData",
    "ForestPresenter",
    "MassAttackCallbackData",
    "MassBlockCallbackData",
    "MassDuelPresenter",
    "MountainsPresenter",
    "OraclePresenter",
    "ProfilePresenter",
    "PveCallbackAction",
    "PveCallbackData",
    "PvePresenter",
    "ReferralShareCallbackData",
    "ReferralSharePresenter",
    "RejectCallbackData",
    "ShareCallbackData",
    "ShareKind",
    "TopPresenter",
    "UpgradeCallbackAction",
    "UpgradeCallbackData",
    "UpgradePresenter",
    "accept_callback_data",
    "attack_callback_data",
    "block_callback_data",
    "forest_callback_data",
    "is_pve_callback",
    "mass_attack_callback_data",
    "mass_block_callback_data",
    "parse_accept_callback_data",
    "parse_attack_callback_data",
    "parse_block_callback_data",
    "parse_forest_callback_data",
    "parse_mass_attack_callback_data",
    "parse_mass_block_callback_data",
    "parse_pve_callback_data",
    "parse_referral_share_callback_data",
    "parse_reject_callback_data",
    "parse_share_callback_data",
    "parse_upgrade_callback_data",
    "pve_callback_data",
    "referral_share_callback_data",
    "reject_callback_data",
    "share_callback_data",
    "upgrade_callback_data",
]
