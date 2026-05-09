"""Application-слой инвентаря (Спринт 3.4-C).

Use-case `EnchantItem` (заточка предмета) + DTO `EnchantAttemptResult`.
Опирается на доменные порты `IItemRepository` / `IScrollRepository` /
`IEnchantHistoryReader` (для trip-wire анти-чита) и на чистый picker
`pick_enchant_outcome`.
"""

from pipirik_wars.application.inventory.enchant_item import (
    EnchantAttemptResult,
    EnchantItem,
)

__all__ = ["EnchantAttemptResult", "EnchantItem"]
