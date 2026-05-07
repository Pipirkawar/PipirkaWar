"""Доменный пакет «заточка экипировки» (ГДД §2.8).

Спринт 3.1-D — **скелет**: VO `Scroll(category, blessed)` + категории,
без use-механики применения. Полная имплементация (use-case
`EnchantItem`, picker `pick_enchant_outcome`, лестница уровней
`+0..+30`, тиры сложности safe/easy/hard/very_hard/extreme/almost_impossible
с весами per-level из `balance.yaml`, инвариант `MaxLevelReached` на
`+30`, специальное правило для `+29`, blessed-исходы `success_2`/
`drop_1`/`drop_2`) — **Спринт 3.4** (см. `docs/development_plan.md`
§7 Спринт 3.4).

В 3.1-D мы лишь:
- вводим VO `Scroll` в инвентаре;
- расширяем drop-engine, чтобы горы и данжон роллили дроп скроллов
  (mountains: только `regular`; dungeon: `regular` + `blessed`);
- не трогаем enchant-механику и not-yet-existing инвентарь скроллов
  (то, как игрок "копит" скроллы, появится в 3.4).

Категории скроллов (ГДД §2.8.1):
- `weapon_scroll` — точит `right_hand` / `left_hand`.
- `armor_scroll` — точит `hat` / `body` / `legs` / `boots`.
- `jewelry_scroll` — точит `ring` / `chain`.

Скролл одной категории нельзя применить на предмет другой категории
(валидируется в use-case `EnchantItem` в 3.4); сейчас связь категория↔
слот существует только концептуально.
"""

from pipirik_wars.domain.enchantment.entities import Scroll, ScrollCategory

__all__ = ["Scroll", "ScrollCategory"]
