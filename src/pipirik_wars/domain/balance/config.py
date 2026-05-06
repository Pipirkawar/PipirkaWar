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
    """6 слотов экипировки (ГДД §2.6).

    Тип общий для каталога (`items_catalog`) и для рантайм-сущностей в
    `domain/forest/` (потом — `domain/items/`, когда подключим горы /
    данжон). Живёт здесь, чтобы pydantic-схема `BalanceConfig` могла
    типизировать слот без обратного импорта в forest-пакет.
    """

    HAT = "hat"
    BODY = "body"
    LEGS = "legs"
    BOOTS = "boots"
    RING = "ring"
    CHAIN = "chain"


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


class ForestDropConfig(_Frozen):
    """Параметры дропа за поход в лес (ГДД §1.3.5).

    `probability_percent` — целочисленный шанс ЛЮБОГО дропа за поход
    (0 — лес ничего не даёт, 100 — каждый поход с дропом).
    `name_share_percent` — внутри дропов: доля «имя» vs «предмет
    экипировки» (имя — единственный путь его получить, ГДД §2.5).
    Оба значения — в `[0, 100]`.
    """

    probability_percent: int = Field(ge=0, le=100)
    name_share_percent: int = Field(ge=0, le=100)
    rarity_weights: ForestRarityWeights


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


_MIN_ITEMS_CATALOG_SIZE: int = 30
"""Минимальный размер `items_catalog` (ГДД §1.3.5: «≥ 30 предметов на 6 слотов»)."""

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
    oracle: OracleConfig
    referral: ReferralConfig
    thickness: ThicknessConfig
    dau_gate: DauGateConfig
    daily_head: DailyHeadConfig
    anticheat: AnticheatConfig
    pvp: PvpConfig
    content_policy: ContentPolicy
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
