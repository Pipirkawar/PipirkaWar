"""Pydantic-схема `config/balance.yaml`.

Все балансовые числа игры. Любой невалидный файл (дыра в display_names,
отрицательный вес исхода леса, oracle.min > oracle.max и т. п.) → отказ
загрузки на старте процесса. Это ГДД §0: «никаких магических чисел в
коде», и Спринт 0.2.9: «Файл валидируется на старте».

Все модели — `frozen=True, extra="forbid"`. После валидации `BalanceConfig`
неизменяем. Hot-reload в `YamlBalanceLoader.reload()` атомарно создаёт
новый объект; старые ссылки остаются валидными.
"""

from __future__ import annotations

import itertools
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipirik_wars.domain.shared.ports.audit import AuditSource
from pipirik_wars.shared.errors import IntegrityError


class Slot(StrEnum):
    """8 слотов экипировки (ГДД §2.6).

    Слоты `right_hand` / `left_hand` (оружие) добавлены в Спринте 3.1-C
    как отдельные слоты от 6 слотов «обвеса» (`hat`/`body`/`legs`/
    `boots`/`ring`/`chain`). Веса дропа per-location задаются
    отдельно — `BaseDropConfig.slot_weights` (см. ниже): `forest`
    оружие не дропает (вес `right_hand`/`left_hand` = 0), а
    `mountains`/`dungeon` дают оружие согласно ГДД §8.

    Тип общий для каталога (`items_catalog`) и для рантайм-сущностей
    в `domain/forest/` (потом — `domain/items/`, когда подключим
    горы / данжон). Живёт здесь, чтобы pydantic-схема `BalanceConfig`
    могла типизировать слот без обратного импорта в forest-пакет.
    """

    HAT = "hat"
    BODY = "body"
    LEGS = "legs"
    BOOTS = "boots"
    RING = "ring"
    CHAIN = "chain"
    RIGHT_HAND = "right_hand"
    LEFT_HAND = "left_hand"


class Rarity(StrEnum):
    """3 уровня редкости предметов экипировки (ГДД §2.6, §1.3.5)."""

    COMMON = "common"
    RARE = "rare"
    EPIC = "epic"


class _Frozen(BaseModel):
    """Базовый класс для frozen-моделей баланса.

    `populate_by_name=True` нужен, чтобы поле с алиасом (`from_cm` ↔ `from`)
    можно было задавать и из YAML (по алиасу), и из Python-кода в тестах
    (по имени).
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )


class DisplayNameRange(_Frozen):
    """Один ряд таблицы «длина → название» (ГДД §2.3).

    Полуоткрытый интервал ``[from_cm, to_cm)``. Для последней записи
    ``to_cm = None`` означает «до бесконечности».
    """

    from_cm: int = Field(alias="from", ge=0)
    to_cm: int | None = Field(alias="to")
    name: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def _validate_range(self) -> DisplayNameRange:
        if self.to_cm is not None and self.from_cm >= self.to_cm:
            raise ValueError(
                f"display_name range {self.name!r}: from ({self.from_cm}) "
                f"must be < to ({self.to_cm})"
            )
        return self


class ForestOutcome(_Frozen):
    """Одна ветка исхода леса (scarce / normal / abundant)."""

    name: str = Field(min_length=1, max_length=32)
    weight: int = Field(gt=0)
    min: int = Field(ge=0)
    max: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_min_max(self) -> ForestOutcome:
        if self.min > self.max:
            raise ValueError(
                f"forest outcome {self.name!r}: min ({self.min}) must be <= max ({self.max})"
            )
        return self


class ForestRarityWeights(_Frozen):
    """Распределение редкости предметов в дропе леса (ГДД §1.3.5).

    Дефолтное распределение по ГДД — 70/25/5, но веса могут быть любыми
    положительными целыми. Все 3 уровня обязательны: иначе при rarity-roll
    мы получили бы недостижимый pool для отсутствующей ветки.
    """

    common: int = Field(gt=0)
    rare: int = Field(gt=0)
    epic: int = Field(gt=0)


class SlotWeights(_Frozen):
    """Веса дропа предметов по слотам per-location (ГДД §2.6, Спринт 3.1-C).

    Каждое поле — целое неотрицательное число; `weighted_choice` на этих
    весах выбирает слот предмета при дропе. Сумма весов должна быть `> 0`,
    иначе `weighted_choice` упадёт. Слоты с весом `0` дропать в этой
    локации не будут (например, `right_hand`/`left_hand` для леса).

    Кросс-валидируется в `BalanceConfig` на старте: для каждого слота
    с положительным весом и каждой `rarity` из `rarity_weights` локации
    в `items_catalog` обязан быть ≥ 1 предмет — иначе rarity-roll даст
    непустой rarity-pool, но `slot+rarity`-фильтр окажется пустым.
    """

    hat: int = Field(ge=0)
    body: int = Field(ge=0)
    legs: int = Field(ge=0)
    boots: int = Field(ge=0)
    ring: int = Field(ge=0)
    chain: int = Field(ge=0)
    right_hand: int = Field(ge=0)
    left_hand: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_sum_positive(self) -> SlotWeights:
        total = (
            self.hat
            + self.body
            + self.legs
            + self.boots
            + self.ring
            + self.chain
            + self.right_hand
            + self.left_hand
        )
        if total <= 0:
            raise ValueError(
                "slot_weights: at least one slot must have weight > 0 "
                "(otherwise weighted_choice on slots is undefined)"
            )
        return self

    def as_pairs(self) -> tuple[tuple[Slot, int], ...]:
        """Список `(Slot, weight)` в стабильном порядке (для `weighted_choice`)."""
        return (
            (Slot.HAT, self.hat),
            (Slot.BODY, self.body),
            (Slot.LEGS, self.legs),
            (Slot.BOOTS, self.boots),
            (Slot.RING, self.ring),
            (Slot.CHAIN, self.chain),
            (Slot.RIGHT_HAND, self.right_hand),
            (Slot.LEFT_HAND, self.left_hand),
        )


class ForestDropConfig(_Frozen):
    """Параметры дропа за поход в лес (ГДД §1.3.5).

    `probability_percent` — целочисленный шанс ЛЮБОГО дропа за поход
    (0 — лес ничего не даёт, 100 — каждый поход с дропом).
    `name_share_percent` — внутри дропов: доля «имя» vs «предмет
    экипировки» (имя — единственный путь его получить, ГДД §2.5).
    Оба значения — в `[0, 100]`.
    `slot_weights` — распределение слотов внутри дропа предметов
    (Спринт 3.1-C). Для леса `right_hand`/`left_hand` обычно `0`
    (оружие в лесу не дропает, ГДД §8).
    """

    probability_percent: int = Field(ge=0, le=100)
    name_share_percent: int = Field(ge=0, le=100)
    rarity_weights: ForestRarityWeights
    slot_weights: SlotWeights


class ForestConfig(_Frozen):
    """Конфиг похода в лес (ГДД §8.2)."""

    outcomes: tuple[ForestOutcome, ...] = Field(min_length=1)
    cooldown_min_minutes: int = Field(gt=0)
    cooldown_max_minutes: int = Field(gt=0)
    drop: ForestDropConfig

    @model_validator(mode="after")
    def _validate(self) -> ForestConfig:
        if self.cooldown_min_minutes > self.cooldown_max_minutes:
            raise ValueError(
                f"forest.cooldown_min_minutes ({self.cooldown_min_minutes}) "
                f"must be <= cooldown_max_minutes ({self.cooldown_max_minutes})"
            )
        names = [o.name for o in self.outcomes]
        if len(set(names)) != len(names):
            raise ValueError(f"forest.outcomes have duplicate names: {names}")
        return self


class ItemEntry(_Frozen):
    """Одна запись каталога экипировки `items_catalog` (ГДД §1.3.5, §2.6).

    `id` — стабильный машинный идентификатор (`item.<slot>.<short>`).
    Используется в `equipment.item_id` и `audit_log.target_id`. Не
    меняется без миграции.
    """

    id: str = Field(min_length=1, max_length=64)
    slot: Slot
    display_name: str = Field(min_length=1, max_length=64)
    rarity: Rarity


class PveSign(StrEnum):
    """Знак исхода PvE-локации с ±-механикой (ГДД §8: горы / данжон).

    В отличие от леса, где исход всегда положительный (`+Δ` длины),
    горы и данжон имеют ветви и `gain` (награда), и `loss` (потеря).
    Знак — отдельное поле ветки, чтобы баланс мог независимо тюнить
    «как часто горы дают штраф» (вес `loss`-веток) и «насколько
    больно» (диапазон `min..max` каждой ветки). Сами `min`/`max`
    хранятся как **абсолютные неотрицательные** числа; знак к ним
    применяется domain-сервисом `pick_pve_outcome`.
    """

    GAIN = "gain"
    LOSS = "loss"


class PveOutcomeConfig(_Frozen):
    """Одна ветка исхода PvE-локации (горы / данжон) (ГДД §8).

    Отличия от `ForestOutcome`:
    - Дополнительное поле `sign: PveSign` (`gain` / `loss`).
    - `min`/`max` остаются абсолютными значениями `≥ 0`; реальный
      `Δ длины` = `±randint(min, max)` в зависимости от `sign`.

    Имя ветки уникально внутри секции локации (валидируется
    `_PveLocationConfig._validate_outcomes`).
    """

    name: str = Field(min_length=1, max_length=32)
    weight: int = Field(gt=0)
    sign: PveSign
    min: int = Field(ge=0)
    max: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_min_max(self) -> PveOutcomeConfig:
        if self.min > self.max:
            raise ValueError(
                f"pve outcome {self.name!r}: min ({self.min}) must be <= max ({self.max})"
            )
        return self


class ScrollCategoryWeights(_Frozen):
    """Веса категорий скроллов в дропе скроллов (ГДД §2.8.1, Спринт 3.1-D).

    После того, как Bernoulli-ролл `regular_chance_percent` /
    `blessed_chance_percent` решил «дропается ли скролл», эти веса
    выбирают конкретную категорию (`weapon`/`armor`/`jewelry`).

    Сумма весов должна быть `> 0`, иначе `weighted_choice` упал бы.
    Веса категорий с нулём из выборки выпадают (что нормально,
    если, например, новой категории ещё нет в каталоге предметов).
    """

    weapon: int = Field(ge=0)
    armor: int = Field(ge=0)
    jewelry: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_sum_positive(self) -> ScrollCategoryWeights:
        if self.weapon + self.armor + self.jewelry <= 0:
            raise ValueError("scroll category_weights: at least one category must have weight > 0")
        return self


class ScrollDropConfig(_Frozen):
    """Параметры дропа скроллов заточки за поход PvE (ГДД §2.8.5, Спринт 3.1-D).

    Дроп скроллов — две **независимые** Bernoulli-попытки за поход
    (поверх дропа предметов, не вместо него):

    - `regular_chance_percent` — шанс дропа обычного скролла
      (`blessed=False`). По ГДД §2.8.5 — «очень-очень малый» в горах,
      «очень малый» в данжоне; конкретные числа в `balance.yaml`.
    - `blessed_chance_percent` — шанс дропа благословлённого скролла
      (`blessed=True`). По ГДД §2.8.5 — `0` в горах (горы blessed
      не дают), «очень-очень малый» в данжоне.
    - `category_weights` — после того, как Bernoulli решил «дропается»,
      выбирается категория (`weapon`/`armor`/`jewelry`). Лес скроллы
      не дропает в принципе (поэтому `ForestDropConfig.scroll_drops`
      нет — это сделано через отсутствие поля, а не нулевые шансы).

    Семантика «0..2 скролла за поход»: и regular, и blessed —
    независимые роллы; в один поход можно получить и regular, и
    blessed, или только один, или ни одного.
    """

    regular_chance_percent: int = Field(ge=0, le=100)
    blessed_chance_percent: int = Field(ge=0, le=100)
    category_weights: ScrollCategoryWeights


class PveDropConfig(_Frozen):
    """Параметры дропа за один поход PvE (горы / данжон) (ГДД §8.2 / §1.3.5).

    Отличия от `ForestDropConfig`:
    - **Нет** `name_share_percent` — имена дропаются только из леса
      (ГДД §2.5).
    - Добавлено `max_drops` — максимальное число предметов за поход
      (горы: `1`, данжон: `3` по ГДД §8). Для каждого «слота дропа»
      ролится отдельно (`probability_percent` per-slot Bernoulli),
      что даёт распределение `Binomial(max_drops, p)` для итогового
      числа предметов: `0..max_drops`. Семантика **«до N предметов»**
      из ГДД §8 («0–1 шт» / «0–3 шт») реализуется именно так.
    - `scroll_drops` (Спринт 3.1-D) — параметры дропа скроллов
      заточки. Бернулли-роллы независимы от дропа предметов: в один
      поход можно одновременно получить предмет и скролл, или только
      одно, или ничего.

    `slot_weights` (Спринт 3.1-C) — распределение слотов внутри
    каждого дропа: для каждого «слота дропа» сначала ролится слот
    (`weighted_choice` на `slot_weights`), затем редкость, затем
    конкретный предмет из `(slot, rarity)`-pool. Для гор/данжона
    `right_hand`/`left_hand` имеют положительные веса (оружие
    дропает); для леса — ноль (см. `ForestDropConfig`).
    """

    probability_percent: int = Field(ge=0, le=100)
    max_drops: int = Field(ge=1, le=10)
    rarity_weights: ForestRarityWeights
    slot_weights: SlotWeights
    scroll_drops: ScrollDropConfig


class _PveLocationConfig(_Frozen):
    """Базовая модель PvE-локации с ±-исходами (ГДД §8).

    Конкретные подклассы (`MountainsConfig`, `DungeonConfig`) добавляют
    только docstring — структура полей и инварианты у обоих локаций
    идентичны. Балансовые числа разные (см. `config/balance.yaml`),
    но схема общая, чтобы не дублировать валидаторы.
    """

    outcomes: tuple[PveOutcomeConfig, ...] = Field(min_length=2)
    cooldown_min_minutes: int = Field(gt=0)
    cooldown_max_minutes: int = Field(gt=0)
    drop: PveDropConfig

    @model_validator(mode="after")
    def _validate(self) -> _PveLocationConfig:
        if self.cooldown_min_minutes > self.cooldown_max_minutes:
            raise ValueError(
                f"pve.cooldown_min_minutes ({self.cooldown_min_minutes}) "
                f"must be <= cooldown_max_minutes ({self.cooldown_max_minutes})"
            )
        names = [o.name for o in self.outcomes]
        if len(set(names)) != len(names):
            raise ValueError(f"pve.outcomes have duplicate names: {names}")
        signs = {o.sign for o in self.outcomes}
        if PveSign.GAIN not in signs:
            raise ValueError(
                "pve.outcomes must contain at least one outcome with sign=gain "
                f"(got signs: {sorted(s.value for s in signs)})"
            )
        if PveSign.LOSS not in signs:
            raise ValueError(
                "pve.outcomes must contain at least one outcome with sign=loss "
                f"(got signs: {sorted(s.value for s in signs)})"
            )
        return self


class MountainsConfig(_PveLocationConfig):
    """Конфиг похода в горы (ГДД §8, Спринт 3.1.1).

    По ГДД §8: уровень `3+`, длина `≥ 20 см`, кулдаун `20–40 мин`,
    `± длина`, дроп `0–1 шт`. Конкретные числа ставятся в
    `config/balance.yaml` и могут крутиться без релиза кода.
    """


class DungeonConfig(_PveLocationConfig):
    """Конфиг похода в данжон (ГДД §8, Спринт 3.1.2).

    По ГДД §8: уровень `6+`, длина `≥ 20 см`, кулдаун `40–60 мин`,
    `± длина`, дроп `0–3 шт`. Конкретные числа ставятся в
    `config/balance.yaml` и могут крутиться без релиза кода.
    """


class CaravanRewardMultipliers(_Frozen):
    """Множители наград за победу в караване (ГДД §9.6, Спринт 3.2.6).

    `leader=4` означает, что лидер успешного каравана получает в 4 раза
    больше длины, чем «базовая» награда (`base_reward_cm` ниже).
    Все множители — целые ≥ 0 (можно поставить 0, чтобы выключить
    награды конкретной роли).

    `ataman_bonus_share` (Спринт 3.2-C, ГДД §9.6) — множитель «доли
    от системы», которую дополнительно получает один случайный рейдер
    (Атаман) при разграблении каравана: его итоговая длина-награда =
    `base_share_per_raider_cm + ataman_bonus_share × base_share_per_raider_cm`,
    где `base_share_per_raider_cm = ceil(total_cargo_cm / num_raiders)`.
    Дефолт `4` (ГДД §9.6 «×4 к доле от системы»). Заодно выдаётся
    `Title.ATAMAN`. `0` — отключить бонус Атамана (никто не выделяется
    из общей доли).
    """

    leader: int = Field(ge=0)
    caravaneer: int = Field(ge=0)
    defender: int = Field(ge=0)
    raider: int = Field(ge=0)
    ataman_bonus_share: int = Field(ge=0)


class CaravansConfig(_Frozen):
    """Конфиг караванов (ГДД §9, Спринт 3.2-A).

    Все балансовые числа караванной механики:
    - `min_thickness_level_leader=7` — минимальный уровень для создания
      каравана (ГДД §9.1).
    - `min_thickness_level_raider=5` — для участия рейдером (ГДД §9.5).
    - Остальные роли (`caravaneer` / `defender`) — без минимального
      уровня (только длина).
    - `min_length_cm=20` / `min_length_after_contribution_cm=20` — ГДД §9.2 / §9.3
      (после взноса остаётся ≥ 20 см).
    - `lobby_minutes=20`, `battle_minutes=60` — ГДД §9.3 / §9.5.
    - `clan_cooldown_hours=12` — ГДД §9.3.
    - Capacity-предели (`max_raiders_per_caravaneer=4`,
      `max_defenders_per_caravaneer=2`) — ГДД §9.5.
    - `base_reward_cm` — базовая награда за победу. Конкретные
      выплаты считаются как `base_reward_cm * reward_multipliers.<role>`.
      ГДД §9.6: ×4 / ×3 / ×1 / -.
    - `clan_bonus_cm=1` — клан-получатель получает ровно +1 см к
      «общей длине клана» при успешном получении каравана (ГДД §9.6).
    - `unblocked_strike_damage_cm` (Спринт 3.2-C, ГДД §9.5) — «немного
      −длины», которое теряет караванщик/защитник, когда удар рейдера
      пришёлся не в его блок (он также погибает). Дефолт `1`.
    - `blocked_strike_damage_cm` (Спринт 3.2-C, ГДД §9.5) — «немного
      −длины», которое теряет рейдер, когда его удар пришёлся в блок
      цели. Дефолт `1`.

    Подсекции `lobby_minutes`/`battle_minutes` НЕ объединены в единый
    `cooldown_min/max` (как у PvE), потому что у каравана это две
    разные фазы, не два конца окна.
    """

    min_thickness_level_leader: int = Field(ge=1)
    min_thickness_level_raider: int = Field(ge=1)
    min_length_cm: int = Field(gt=0)
    min_length_after_contribution_cm: int = Field(gt=0)
    lobby_minutes: int = Field(gt=0)
    battle_minutes: int = Field(gt=0)
    clan_cooldown_hours: int = Field(ge=0)
    max_raiders_per_caravaneer: int = Field(ge=0)
    max_defenders_per_caravaneer: int = Field(ge=0)
    base_reward_cm: int = Field(ge=0)
    reward_multipliers: CaravanRewardMultipliers
    clan_bonus_cm: int = Field(ge=0)
    unblocked_strike_damage_cm: int = Field(ge=0)
    blocked_strike_damage_cm: int = Field(ge=0)


class BossScrollDropConfig(_Frozen):
    """Шансы дропа скроллов при победе рейдеров над боссом (ГДД §10.5, §2.8.5).

    Применяется per-player (каждому выжившему рейдеру независимо ролится
    свой ролл). Шансы — `Decimal[0..1]`, валидируются на пересечения
    нет (regular и blessed — независимые роллы).

    `regular` — обычный скролл (ГДД §2.8.5: «небольшой шанс»). Дефолт
    `0.05` (5%) — стартовое значение, уточнится по альфа-метрикам.

    `blessed` — благословлённый скролл (ГДД §2.8.5: «очень небольшой
    шанс»). Дефолт `0.005` (0.5%).
    """

    regular: float = Field(ge=0.0, le=1.0)
    blessed: float = Field(ge=0.0, le=1.0)


class BossesConfig(_Frozen):
    """Конфиг рейд-боссов (ГДД §10, Спринт 3.3-A).

    Все балансовые числа рейд-механики:

    - `min_thickness_level_summoner=9` — минимальный уровень толщины для
      призыва босса (ГДД §10.1: «Кинуть вызов — lvl 9+»).
    - `min_thickness_level_raider=4` — для участия рейдером (ГДД §10.1:
      «Участвовать — lvl 4+»).
    - `min_length_cm=20` — минимальная длина саммонера / рейдера (ГДД
      §10.1: «≥ 20 см» — для обеих ролей).
    - `lobby_minutes=20` — длина фазы лобби (ГДД §10.3).
    - `summon_cooldown_hours=4` — глобальный кулдаун между призывами
      (ГДД §10.1: «1 раз в 4 часа (глобальный)»). По решению cyan91 на
      старте 3.3-A — это кулдаун на весь сервер, не per-clan и не
      per-player. Реализация — распределённый lock в Спринте 3.3-B.
    - `top_n_pool=30` — размер пула кандидатов в боссы. Босс выбирается
      случайно из топ-N игроков по `length_cm` (ГДД §10.1: «Босс =
      случайный из топ-30»). По решению cyan91 — топ-30 **игроков**, не
      кланов.
    - `victory_threshold_cm=10` — длина босса, при `current_boss_length_cm
      < victory_threshold_cm` рейдеры побеждают (ГДД §10.5: «победа =
      босс < 10 см»).
    - `round_min_seconds=20` / `round_max_seconds=60` — длина раунда
      (timer внутри которого собираются ходы). Один раунд — это
      `min..max` интервал; конкретное число выбирается раунд-резолверем
      (3.3-C). Раундов в бою — до победы/поражения, без фиксированного N.
    - `base_damage_cm=5` — базовый урон в раунде (ГДД §10.4). Применяется
      одинаково в обе стороны: босс пробивает блок → рейдер -5 см и
      выбывает; рейдер блокирует → босс -5 см.
    - `bot_play_chance` (Спринт 3.3-C) — вероятность, что бот сыграет
      за саммонера, если он AFK на ход дольше `round_max_seconds`.
      Реалистично 1.0 (всегда), оставляем поле для тонкой настройки.
    - `scroll_drop` — шансы дропа скроллов (см. `BossScrollDropConfig`).

    Раунд-резолверная логика (`boss_round_resolution`) — Спринт 3.3-C.
    """

    min_thickness_level_summoner: int = Field(ge=1)
    min_thickness_level_raider: int = Field(ge=1)
    min_length_cm: int = Field(gt=0)
    lobby_minutes: int = Field(gt=0)
    summon_cooldown_hours: int = Field(ge=0)
    top_n_pool: int = Field(gt=0)
    victory_threshold_cm: int = Field(gt=0)
    round_min_seconds: int = Field(gt=0)
    round_max_seconds: int = Field(gt=0)
    base_damage_cm: int = Field(ge=0)
    bot_play_chance: float = Field(ge=0.0, le=1.0)
    scroll_drop: BossScrollDropConfig

    @model_validator(mode="after")
    def _validate(self) -> BossesConfig:
        if self.round_min_seconds > self.round_max_seconds:
            raise ValueError(
                f"bosses.round_min_seconds ({self.round_min_seconds}) "
                f"must be <= round_max_seconds ({self.round_max_seconds})"
            )
        if self.min_thickness_level_summoner < self.min_thickness_level_raider:
            raise ValueError(
                f"bosses.min_thickness_level_summoner "
                f"({self.min_thickness_level_summoner}) must be >= "
                f"min_thickness_level_raider ({self.min_thickness_level_raider})"
            )
        return self


class OracleConfig(_Frozen):
    """Конфиг предсказателя `/oracle` (ГДД §11)."""

    cooldown_tz: str = Field(min_length=1)
    bonus_min: int = Field(gt=0)
    bonus_max: int = Field(gt=0)
    distribution: Literal["uniform"] = "uniform"

    @model_validator(mode="after")
    def _validate(self) -> OracleConfig:
        if self.bonus_min > self.bonus_max:
            raise ValueError(
                f"oracle.bonus_min ({self.bonus_min}) must be <= bonus_max ({self.bonus_max})"
            )
        return self


class ReferralOnSignup(_Frozen):
    """Бонусы при регистрации новичка по рефке (ГДД §13.1)."""

    newbie_bonus_cm: int = Field(ge=0)
    referrer_bonus_cm: int = Field(ge=0)


class ReferralMilestone(_Frozen):
    """Бонус рефереру за достижение реферальным определённой толщины."""

    thickness: int = Field(ge=1)
    referrer_bonus_cm: int = Field(ge=0)


class ReferralConfig(_Frozen):
    """Конфиг реферальной системы (ГДД §13.1)."""

    on_signup: ReferralOnSignup
    on_thickness_milestones: tuple[ReferralMilestone, ...] = Field(default=())

    @model_validator(mode="after")
    def _validate_milestones(self) -> ReferralConfig:
        thicknesses = [m.thickness for m in self.on_thickness_milestones]
        if len(set(thicknesses)) != len(thicknesses):
            raise ValueError(
                f"referral.on_thickness_milestones: duplicate thickness in {thicknesses}"
            )
        if thicknesses != sorted(thicknesses):
            raise ValueError(
                f"referral.on_thickness_milestones must be sorted by thickness, got {thicknesses}"
            )
        return self


class ThicknessConfig(_Frozen):
    """Конфиг толщины: формула цены и unlock-уровни активностей (ГДД §3.2)."""

    cost_base: int = Field(gt=0)
    cost_exponent: int = Field(ge=1)
    unlock_levels: dict[str, int] = Field(min_length=1)

    @field_validator("unlock_levels")
    @classmethod
    def _validate_levels(cls, value: dict[str, int]) -> dict[str, int]:
        for activity, level in value.items():
            if not activity:
                raise ValueError("thickness.unlock_levels: empty activity name")
            if level < 1:
                raise ValueError(f"thickness.unlock_levels[{activity!r}] must be >= 1, got {level}")
        return value


class DauGateConfig(_Frozen):
    """DAU-Gate — лимит активных за сутки (ГДД §0.5)."""

    max_dau: int = Field(gt=0)
    alert_threshold: float = Field(gt=0.0, le=1.0)


class DailyHeadConfig(_Frozen):
    """Конфиг «Главы клана дня» (ГДД §6.1, Q4 v9 — гибридный триггер)."""

    bonus_min: int = Field(gt=0)
    bonus_max: int = Field(gt=0)
    cooldown_tz: str = Field(min_length=1)
    schedule_mode: Literal["button", "cron", "hybrid"]
    cron_random_offset_hours: int = Field(gt=0, le=48)
    min_active_members: int = Field(ge=1)
    active_within_days: int = Field(ge=1)
    avoid_last_n: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate(self) -> DailyHeadConfig:
        if self.bonus_min > self.bonus_max:
            raise ValueError(
                f"daily_head.bonus_min ({self.bonus_min}) must be <= bonus_max ({self.bonus_max})"
            )
        return self


class AnticheatConfig(_Frozen):
    """Конфиг анти-чит хардкапа (ГДД §3.3.5, Спринт 1.6.B).

    Параметры rolling-окон (24 ч / 7 дн) и длительности soft-ban-а, плюс
    whitelist organic-источников (попадают в агрегацию хардкапа) и
    blacklist donate-источников (платный канал — без ограничений).

    Источники, отсутствующие в обоих списках (`admin_refund`, `unknown`),
    вообще не учитываются в агрегации: первый — служебная отрицательная
    дельта при сторно, второй — backfill для исторических записей.
    """

    daily_cap_cm: int = Field(gt=0)
    weekly_cap_cm: int = Field(gt=0)
    soft_ban_duration_days: int = Field(gt=0)
    organic_sources: tuple[AuditSource, ...] = Field(min_length=1)
    donate_sources: tuple[AuditSource, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate(self) -> AnticheatConfig:
        if self.daily_cap_cm > self.weekly_cap_cm:
            raise ValueError(
                f"anticheat.daily_cap_cm ({self.daily_cap_cm}) must be <= "
                f"weekly_cap_cm ({self.weekly_cap_cm})"
            )
        organic_set = set(self.organic_sources)
        donate_set = set(self.donate_sources)
        if len(organic_set) != len(self.organic_sources):
            raise ValueError(
                f"anticheat.organic_sources contains duplicates: {self.organic_sources}"
            )
        if len(donate_set) != len(self.donate_sources):
            raise ValueError(f"anticheat.donate_sources contains duplicates: {self.donate_sources}")
        intersection = organic_set & donate_set
        if intersection:
            raise ValueError(
                "anticheat: organic_sources and donate_sources must be disjoint, "
                f"intersection: {sorted(s.value for s in intersection)}"
            )
        if AuditSource.UNKNOWN in organic_set or AuditSource.UNKNOWN in donate_set:
            raise ValueError(
                "anticheat: AuditSource.UNKNOWN must not appear in organic_sources "
                "or donate_sources (it is a backfill marker, not a real source)"
            )
        if AuditSource.ADMIN_REFUND in organic_set:
            raise ValueError(
                "anticheat: AuditSource.ADMIN_REFUND must not appear in organic_sources "
                "(refunds are negative deltas, never aggregated as positive growth)"
            )
        return self


# --------------------------------------------------------------------------- #
# Заточка предметов (ГДД §2.8, Спринт 3.4-A)
# --------------------------------------------------------------------------- #


# Жёсткий потолок лестницы заточки. Дублируется с
# `domain/inventory/entities.MAX_ENCHANT_LEVEL` намеренно (defence-in-depth).
# Совпадение проверяется тестом A.7. Менять — только согласованно
# (см. ГДД §2.8.2).
_ENCHANT_HARD_MAX_LEVEL: int = 30
# Эпсилон для проверки «сумма весов в строке == 1.0». Веса в ГДД §2.8.6
# заданы с тремя знаками после запятой; FP-погрешность сложения не
# должна превышать `1e-6`.
_ENCHANT_WEIGHT_SUM_EPSILON: float = 1e-6


class RegularLevelWeights(_Frozen):
    """Веса 4 исходов обычной заточки на одном уровне (ГДД §2.8.3, §2.8.6).

    Сумма `success + no_effect + drop + destroy == 1.0` (± ε) — invariant
    `_validate_sum_to_one`. На уровнях `< safe_zone_max_level` веса
    `drop` и `destroy` обязаны быть нулевыми (ГДД §2.8.6) — это
    проверяется на уровне `EnchantmentConfig` (cross-row invariant).
    """

    success: float = Field(ge=0.0, le=1.0)
    no_effect: float = Field(ge=0.0, le=1.0)
    drop: float = Field(ge=0.0, le=1.0)
    destroy: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_sum_to_one(self) -> RegularLevelWeights:
        total = self.success + self.no_effect + self.drop + self.destroy
        if abs(total - 1.0) > _ENCHANT_WEIGHT_SUM_EPSILON:
            raise ValueError(
                f"regular enchant weights must sum to 1.0, got {total} "
                f"(success={self.success}, no_effect={self.no_effect}, "
                f"drop={self.drop}, destroy={self.destroy})",
            )
        return self


class BlessedLevelWeights(_Frozen):
    """Веса 5 исходов благословлённой заточки на одном уровне (ГДД §2.8.4, §2.8.6).

    Сумма `success_1 + success_2 + no_effect + drop_1 + drop_2 == 1.0`
    (± ε) — invariant `_validate_sum_to_one`.

    Жёсткое правило `+29` (ГДД §2.8.4): на `level == max_level - 1` поле
    `success_2` обязано быть `0.0` (запрет `+2 → +31`). Эта cross-level
    проверка делается в `EnchantmentConfig._validate_blessed_last_level_no_success_2`.
    """

    success_1: float = Field(ge=0.0, le=1.0)
    success_2: float = Field(ge=0.0, le=1.0)
    no_effect: float = Field(ge=0.0, le=1.0)
    drop_1: float = Field(ge=0.0, le=1.0)
    drop_2: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_sum_to_one(self) -> BlessedLevelWeights:
        total = self.success_1 + self.success_2 + self.no_effect + self.drop_1 + self.drop_2
        if abs(total - 1.0) > _ENCHANT_WEIGHT_SUM_EPSILON:
            raise ValueError(
                f"blessed enchant weights must sum to 1.0, got {total} "
                f"(success_1={self.success_1}, success_2={self.success_2}, "
                f"no_effect={self.no_effect}, drop_1={self.drop_1}, "
                f"drop_2={self.drop_2})",
            )
        return self


class EnchantmentTier(_Frozen):
    """Один тир сложности заточки (ГДД §2.8.6).

    Тиры — чисто **презентационная** группировка для UI emoji /
    локализации (`enchant-tier-*`). Покрытие диапазона `[0, max_level]`
    без дыр и пересечений — invariant
    `EnchantmentConfig._validate_tiers_cover_range`.
    """

    name: str = Field(min_length=1)
    from_level: int = Field(ge=0, le=_ENCHANT_HARD_MAX_LEVEL, alias="from")
    to_level: int = Field(ge=0, le=_ENCHANT_HARD_MAX_LEVEL, alias="to")
    description_key: str = Field(min_length=1)
    emoji: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_range(self) -> EnchantmentTier:
        if self.from_level >= self.to_level:
            raise ValueError(
                f"enchant tier {self.name!r}: from ({self.from_level}) must be "
                f"< to ({self.to_level})",
            )
        return self


class EnchantmentConfig(_Frozen):
    """Конфиг лестницы заточки `+0..+30` (ГДД §2.8, Спринт 3.4-A).

    Содержит все вероятности исходов на каждом уровне `0..29` для regular
    и blessed-скроллов, плюс safe-zone и тиры сложности.
    """

    max_level: int = Field(ge=1, le=_ENCHANT_HARD_MAX_LEVEL)
    safe_zone_max_level: int = Field(ge=0, le=_ENCHANT_HARD_MAX_LEVEL)
    tiers: tuple[EnchantmentTier, ...] = Field(min_length=1)
    regular_outcomes_per_level: dict[int, RegularLevelWeights]
    blessed_outcomes_per_level: dict[int, BlessedLevelWeights]

    @field_validator(
        "regular_outcomes_per_level",
        "blessed_outcomes_per_level",
        mode="before",
    )
    @classmethod
    def _coerce_string_keys(cls, value: object) -> object:
        """YAML mapping-keys могут читаться как `str`. Превращаем в `int`."""
        if isinstance(value, dict):
            return {int(k) if isinstance(k, str) else k: v for k, v in value.items()}
        return value

    @model_validator(mode="after")
    def _validate_max_level_hard(self) -> EnchantmentConfig:
        if self.max_level != _ENCHANT_HARD_MAX_LEVEL:
            raise ValueError(
                f"enchantment.max_level must be {_ENCHANT_HARD_MAX_LEVEL}, got {self.max_level}",
            )
        return self

    @model_validator(mode="after")
    def _validate_safe_zone_within_max(self) -> EnchantmentConfig:
        if self.safe_zone_max_level > self.max_level:
            raise ValueError(
                f"enchantment.safe_zone_max_level ({self.safe_zone_max_level}) must be "
                f"<= max_level ({self.max_level})",
            )
        return self

    @model_validator(mode="after")
    def _validate_outcomes_keys_full(self) -> EnchantmentConfig:
        """Каждый уровень `0..max_level-1` должен быть в обеих картах."""
        expected: set[int] = set(range(self.max_level))
        regular_keys = set(self.regular_outcomes_per_level)
        if regular_keys != expected:
            missing = sorted(expected - regular_keys)
            extra = sorted(regular_keys - expected)
            raise ValueError(
                f"enchantment.regular_outcomes_per_level keys must be "
                f"0..{self.max_level - 1}: missing={missing}, extra={extra}",
            )
        blessed_keys = set(self.blessed_outcomes_per_level)
        if blessed_keys != expected:
            missing = sorted(expected - blessed_keys)
            extra = sorted(blessed_keys - expected)
            raise ValueError(
                f"enchantment.blessed_outcomes_per_level keys must be "
                f"0..{self.max_level - 1}: missing={missing}, extra={extra}",
            )
        return self

    @model_validator(mode="after")
    def _validate_safe_zone_zero_drops(self) -> EnchantmentConfig:
        """На уровнях `< safe_zone_max_level` `drop`/`destroy` обязаны быть `0.0`."""
        for level in range(self.safe_zone_max_level):
            reg = self.regular_outcomes_per_level[level]
            if reg.drop != 0.0 or reg.destroy != 0.0:
                raise ValueError(
                    f"enchantment.regular_outcomes_per_level[{level}]: "
                    f"drop/destroy must be 0.0 in safe zone "
                    f"(level < safe_zone_max_level={self.safe_zone_max_level}), "
                    f"got drop={reg.drop}, destroy={reg.destroy}",
                )
            bls = self.blessed_outcomes_per_level[level]
            if bls.drop_1 != 0.0 or bls.drop_2 != 0.0:
                raise ValueError(
                    f"enchantment.blessed_outcomes_per_level[{level}]: "
                    f"drop_1/drop_2 must be 0.0 in safe zone "
                    f"(level < safe_zone_max_level={self.safe_zone_max_level}), "
                    f"got drop_1={bls.drop_1}, drop_2={bls.drop_2}",
                )
        return self

    @model_validator(mode="after")
    def _validate_blessed_last_level_no_success_2(self) -> EnchantmentConfig:
        """ГДД §2.8.4: на `level == max_level - 1` blessed `success_2 == 0.0`."""
        last_level = self.max_level - 1
        bls_last = self.blessed_outcomes_per_level[last_level]
        if bls_last.success_2 != 0.0:
            raise ValueError(
                f"enchantment.blessed_outcomes_per_level[{last_level}]."
                f"success_2 must be 0.0 (would push enchant_level past "
                f"max_level={self.max_level}), got {bls_last.success_2}",
            )
        return self

    @model_validator(mode="after")
    def _validate_tiers_cover_range(self) -> EnchantmentConfig:
        """Тиры покрывают `[0, max_level]` без дыр/пересечений."""
        tiers = self.tiers
        if tiers[0].from_level != 0:
            raise ValueError(
                f"enchantment.tiers must start at 0, got {tiers[0].from_level} "
                f"(tier {tiers[0].name!r})",
            )
        if tiers[-1].to_level != self.max_level:
            raise ValueError(
                f"enchantment.tiers must end at max_level={self.max_level}, "
                f"got {tiers[-1].to_level} (tier {tiers[-1].name!r})",
            )
        for prev, nxt in itertools.pairwise(tiers):
            if prev.to_level != nxt.from_level:
                raise ValueError(
                    f"enchantment.tiers: hole/overlap between {prev.name!r} "
                    f"(to={prev.to_level}) and {nxt.name!r} "
                    f"(from={nxt.from_level})",
                )
        return self


class PvpDuel1v1Config(_Frozen):
    """Конфиг боя PvP 1×1 (ГДД §7.1, Спринт 2.1.A).

    * `rounds` — количество раундов в одном бою. По ГДД §7.1 — `3`,
      но параметр оставлен балансируемым для будущих режимов
      («блиц 1 раунд», «epic 5 раундов»).
    * `hit_pct` — целочисленный процент урона от длины защитника при
      успешном попадании (`floor(L * pct / 100)`). Целочисленный, чтобы
      исключить float-drift в тестах: 10% от 100 см = 10 см ровно.
    * `min_length_cm` — порог входа в PvP по длине (ГДД §7.1: «≥ 20 см»).
    * `min_thickness_level` — порог входа по толщине (ГДД §3.2: «PvP 1×1
      разблокируется на уровне 2»). Дублируется в `thickness.unlock_levels`
      для обратной совместимости и table-driven-проверок, но конфиг
      хранит «локальную» копию для прямого читаемого `balance.pvp.duel_1v1`-доступа.
    """

    rounds: int = Field(ge=1, le=10)
    hit_pct: int = Field(ge=0, le=100)
    min_length_cm: int = Field(ge=0)
    min_thickness_level: int = Field(ge=1)
    # Спринт 2.1.F: глобальное лобби FIFO + auto-escalation chat→global.
    # `global_lobby_ttl_minutes` — сколько pending-вызов в `GLOBAL_ONLY`
    # ждёт оппонента в общем лобби, прежде чем будет отменён шедулером
    # (ГДД §7.1: 10 мин). `chat_to_global_promotion_minutes` — сколько
    # `CHAT_THEN_GLOBAL`-вызов ждёт `accept` в чате до авто-промоута в
    # глобальное лобби (ГДД §7.1: 3 мин). Оба значения целочисленные;
    # верхняя граница — 60 мин (час), чтобы DAU-gate не флапал на
    # «вечно зависших» вызовах при балансовом ляпе.
    global_lobby_ttl_minutes: int = Field(ge=1, le=60)
    chat_to_global_promotion_minutes: int = Field(ge=1, le=60)
    # Спринт 2.1.G: AFK-таймер раунда. По ГДД §7.1 — 30..60 секунд:
    # после `accept`-а / закрытия раунда даём игрокам ~minute на
    # выбор атаки+блока, иначе шедулер вызывает `ResolveAfkRound`,
    # который роллит случайные ходы за молчаливых через `IRandom`.
    round_timer_seconds: int = Field(ge=30, le=60)


class PvpMassDuelConfig(_Frozen):
    """Конфиг массового PvP клан×клан (ГДД §7.2, Спринт 2.2.B).

    «Один тик» (ГДД §7.2 / 2.2.4): каждый участник заявляет 1 атаку
    + 1 блок, RNG случайно строит две перестановки атакующих →
    защитников (A→B и B→A), все удары разрешаются одновременно по той
    же 3×3-матрице атака×блок (`Position`), что и в 1×1.

    * `cooldown_hours` — кулдаун между двумя клановыми вызовами одного
      и того же клана-инициатора (ГДД §7.2 / 2.2.2). Целочисленный,
      `Field(ge=1, le=72)` — нижняя граница 1 ч (ниже теряется смысл
      «кулдауна»), верхняя 72 ч (3 дня — крайний разумный кейс).
    * `min_length_cm` — порог входа по длине для авто-записи участника
      (ГДД §7.2 / 2.2.2: «все участники с длиной ≥ 20 см
      автозаписываются»). Дублирует значение из 1×1, но разнесён
      сознательно — у game-design могут появиться причины поднять
      масс-PvP-минимум независимо.
    * `min_thickness_level` — порог входа по толщине (ГДД §3.2: масс-PvP
      разблокируется на уровне 2 толщины, как и 1×1).
    * `min_clan_members` — минимальный размер клана-инициатора и
      клана-цели для запуска боя. По ГДД §7.2 — `1` (бой в принципе
      возможен и при 1 на 1, главное чтобы хотя бы один участник
      на каждой стороне). Параметризовано на случай балансировки.
    * `move_timer_seconds` — общий AFK-таймер боя: время с момента
      `StartMassDuel` до автоматического `ForceResolveMassDuel`
      шедулером. В отличие от 1×1 PvP (per-round 30..60 сек), масс-бой
      одно-тиковый — все участники должны успеть прислать `submit_move`
      до этого дедлайна, иначе их выборы заполнятся случайно. Нижняя
      граница 60 сек (минимум на UI), верхняя 600 сек (10 минут —
      крайний разумный кейс для большой клановой битвы).
    """

    cooldown_hours: int = Field(ge=1, le=72)
    min_length_cm: int = Field(ge=0)
    min_thickness_level: int = Field(ge=1)
    min_clan_members: int = Field(ge=1, le=100)
    move_timer_seconds: int = Field(ge=60, le=600)


class PvpConfig(_Frozen):
    """Корневой PvP-конфиг (ГДД §7).

    Содержит:

    * `duel_1v1` — конфиг боя 1×1 (Спринт 2.1.A).
    * `mass_duel` — конфиг массового клан×клан-боя (Спринт 2.2.B,
      ГДД §7.2). Раздельная секция, чтобы `balance.pvp.duel_1v1` и
      `balance.pvp.mass_duel` имели независимые параметры (rounds,
      hit_pct, кулдауны) и валидировались каждый своей pydantic-моделью.
    """

    duel_1v1: PvpDuel1v1Config
    mass_duel: PvpMassDuelConfig


class ContentPolicyClanQuotes(_Frozen):
    """Контент-полиси для каталога цитат главы клана (ГДД §6.1, Q9 v9)."""

    mild_profanity: bool
    politics: bool
    ethnic_insults: bool
    violence_advocacy: bool
    advertising: bool
    sexual_explicit: bool


class ContentPolicy(_Frozen):
    """Корневая контент-полиси (пока — только цитаты главы клана)."""

    clan_quotes: ContentPolicyClanQuotes


_MIN_ITEMS_CATALOG_SIZE: int = 40
"""Минимальный размер `items_catalog` (ГДД §1.3.5).

С Спринта 3.1-C — 8 слотов (добавлены `right_hand`/`left_hand`) ×
5 предметов минимум на слот = 40. Порог `≥1 предмет на слот` —
в `_validate_items_catalog`, чтобы `slot+rarity`-фильтр drop-engine'а
никогда не выдавал пустой pool.
Исторически до 3.1-C было 30 предметов на 6 слотов."""

_MIN_NAMES_CATALOG_SIZE: int = 30
"""Минимальный размер `names_catalog` (ГДД §1.3.5: «≥ 30 имён в каталоге»)."""


class BalanceConfig(_Frozen):
    """Корневая конфигурация баланса игры.

    Источник правды для ГДД §2.3 (display_names), §8.2 (лес),
    §1.3.5 / §2.6 (items_catalog), §1.3.5 / §2.5 (names_catalog),
    §11 (оракул), §13.1 (рефералка), §3.2 (толщина), §0.5 (DAU-Gate),
    §6.1 (Глава клана дня).

    Целостность display_names проверяется здесь же: первый ряд
    стартует с 0, ряды примыкают друг к другу без дыр и пересечений,
    последний ряд имеет ``to=null`` (бесконечный хвост).

    Каталоги (`items_catalog` / `names_catalog`) проверяются на размер,
    уникальность и покрытие всех редкостей — иначе при rolle дропа
    можно было бы получить пустой pool.
    """

    version: int = Field(ge=1)
    display_names: tuple[DisplayNameRange, ...] = Field(min_length=1)
    forest: ForestConfig
    mountains: MountainsConfig
    dungeon: DungeonConfig
    caravans: CaravansConfig
    bosses: BossesConfig
    oracle: OracleConfig
    referral: ReferralConfig
    thickness: ThicknessConfig
    dau_gate: DauGateConfig
    daily_head: DailyHeadConfig
    anticheat: AnticheatConfig
    pvp: PvpConfig
    content_policy: ContentPolicy
    enchantment: EnchantmentConfig
    items_catalog: tuple[ItemEntry, ...] = Field(min_length=_MIN_ITEMS_CATALOG_SIZE)
    names_catalog: tuple[str, ...] = Field(min_length=_MIN_NAMES_CATALOG_SIZE)

    @model_validator(mode="after")
    def _validate_display_names_cover_axis(self) -> BalanceConfig:
        ranges = self.display_names
        if ranges[0].from_cm != 0:
            raise ValueError(f"display_names must start at 0 cm, got {ranges[0].from_cm}")
        for prev, nxt in itertools.pairwise(ranges):
            if prev.to_cm is None:
                raise ValueError(
                    f"display_names: only the last range may have to=null, "
                    f"but {prev.name!r} (not the last) has it"
                )
            if prev.to_cm != nxt.from_cm:
                raise ValueError(
                    f"display_names: hole/overlap between {prev.name!r} "
                    f"(to={prev.to_cm}) and {nxt.name!r} (from={nxt.from_cm})"
                )
        if ranges[-1].to_cm is not None:
            raise ValueError(
                f"display_names: last range {ranges[-1].name!r} must have "
                f"to=null, got to={ranges[-1].to_cm}"
            )
        return self

    @model_validator(mode="after")
    def _validate_items_catalog(self) -> BalanceConfig:
        ids = [e.id for e in self.items_catalog]
        if len(set(ids)) != len(ids):
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"items_catalog: duplicate item ids: {duplicates}")
        present_rarities: set[Rarity] = {e.rarity for e in self.items_catalog}
        all_rarities: set[Rarity] = {Rarity.COMMON, Rarity.RARE, Rarity.EPIC}
        missing: set[Rarity] = all_rarities - present_rarities
        if missing:
            raise ValueError(
                "items_catalog must contain at least one item per rarity, "
                f"missing: {sorted(r.value for r in missing)}"
            )
        present_slots: set[Slot] = {Slot(e.slot) for e in self.items_catalog}
        all_slots: set[Slot] = set(Slot)
        missing_slots: set[Slot] = all_slots - present_slots
        if missing_slots:
            raise ValueError(
                "items_catalog must contain at least one item per slot, "
                f"missing: {sorted(s.value for s in missing_slots)}"
            )
        return self

    @model_validator(mode="after")
    def _validate_drop_slot_rarity_coverage(self) -> BalanceConfig:
        """Кросс-валидация drop-секций против `items_catalog` (Спринт 3.1-C).

        Для каждой локации (`forest`, `mountains`, `dungeon`):
        для каждого слота с `slot_weights[slot] > 0` — в каталоге
        должен быть ≥ 1 предмет этого слота каждой редкости (`common`,
        `rare`, `epic`). Иначе drop-engine может выкатить пустой
        `(slot, rarity)`-pool и random.choice упадёт.

        Редкость взята из `Rarity` целиком, тк `rarity_weights` в
        реальной схеме всегда покрывает все 3 левела (поля
        `common`/`rare`/`epic` обязательные).
        """
        all_rarities: tuple[Rarity, ...] = (Rarity.COMMON, Rarity.RARE, Rarity.EPIC)
        catalog_index: dict[tuple[Slot, Rarity], int] = {}
        for e in self.items_catalog:
            key = (Slot(e.slot), Rarity(e.rarity))
            catalog_index[key] = catalog_index.get(key, 0) + 1

        location_to_drop: tuple[tuple[str, ForestDropConfig | PveDropConfig], ...] = (
            ("forest", self.forest.drop),
            ("mountains", self.mountains.drop),
            ("dungeon", self.dungeon.drop),
        )
        for location_name, drop_cfg in location_to_drop:
            for slot, weight in drop_cfg.slot_weights.as_pairs():
                if weight <= 0:
                    continue
                for rarity in all_rarities:
                    if catalog_index.get((slot, rarity), 0) <= 0:
                        raise ValueError(
                            f"items_catalog: location {location_name!r} has "
                            f"slot_weights[{slot.value!r}] > 0 but no item with "
                            f"slot={slot.value!r} and rarity={rarity.value!r}"
                        )
        return self

    @model_validator(mode="after")
    def _validate_names_catalog(self) -> BalanceConfig:
        for name in self.names_catalog:
            if not name or not name.strip():
                raise ValueError("names_catalog: empty or whitespace-only name")
        if len(set(self.names_catalog)) != len(self.names_catalog):
            duplicates = sorted({n for n in self.names_catalog if self.names_catalog.count(n) > 1})
            raise ValueError(f"names_catalog: duplicate names: {duplicates}")
        return self

    def display_name_for(self, length_cm: int) -> str:
        """Найти название по длине игрока.

        Длина — целое число сантиметров ≥ 0. Возвращает имя ряда,
        в чей полуоткрытый интервал ``[from, to)`` попадает ``length_cm``.
        Если валидация прошла, метод всегда возвращает строку.
        """
        if length_cm < 0:
            raise ValueError(f"length_cm must be >= 0, got {length_cm}")
        for r in self.display_names:
            if r.from_cm <= length_cm and (r.to_cm is None or length_cm < r.to_cm):
                return r.name
        # pragma: no cover — недостижимо при валидной конфигурации
        raise IntegrityError(f"display_names not covering length_cm={length_cm}")
