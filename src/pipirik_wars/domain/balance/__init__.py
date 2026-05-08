"""Доменная балансовая конфигурация.

Чистая (domain-only) схема `config/balance.yaml`:
- `BalanceConfig` (агрегат) и его подмодели — иммутабельные frozen-pydantic
  value objects с правилами целостности (display_names покрывают [0, +∞)
  без дыр, веса исходов леса > 0, oracle.min ≤ oracle.max, и т. п.).
- `IBalanceConfig` — порт для `application/`-use-cases. Реальная реализация
  (`YamlBalanceLoader` с hot-reload) живёт в `infrastructure/balance/`.

Содержит ТОЛЬКО типы и валидацию — никакого I/O. См. ГДД §0 и
`development_plan.md` Спринт 0.2.9 / 0.2.10.
"""

from pipirik_wars.domain.balance.config import (
    AnticheatConfig,
    BalanceConfig,
    CaravansConfig,
    ContentPolicy,
    ContentPolicyClanQuotes,
    DailyHeadConfig,
    DauGateConfig,
    DisplayNameRange,
    ForestConfig,
    ForestDropConfig,
    ForestOutcome,
    ForestRarityWeights,
    ItemEntry,
    OracleConfig,
    PvpConfig,
    PvpDuel1v1Config,
    PvpMassDuelConfig,
    ReferralConfig,
    ReferralMilestone,
    ReferralOnSignup,
    ScrollCategoryWeights,
    ScrollDropConfig,
    ThicknessConfig,
)
from pipirik_wars.domain.balance.errors import BalanceKeyError
from pipirik_wars.domain.balance.ports import (
    IBalanceConfig,
    IBalanceReloader,
    IBalanceWriter,
)

__all__ = [
    "AnticheatConfig",
    "BalanceConfig",
    "BalanceKeyError",
    "CaravansConfig",
    "ContentPolicy",
    "ContentPolicyClanQuotes",
    "DailyHeadConfig",
    "DauGateConfig",
    "DisplayNameRange",
    "ForestConfig",
    "ForestDropConfig",
    "ForestOutcome",
    "ForestRarityWeights",
    "IBalanceConfig",
    "IBalanceReloader",
    "IBalanceWriter",
    "ItemEntry",
    "OracleConfig",
    "PvpConfig",
    "PvpDuel1v1Config",
    "PvpMassDuelConfig",
    "ReferralConfig",
    "ReferralMilestone",
    "ReferralOnSignup",
    "ScrollCategoryWeights",
    "ScrollDropConfig",
    "ThicknessConfig",
]
