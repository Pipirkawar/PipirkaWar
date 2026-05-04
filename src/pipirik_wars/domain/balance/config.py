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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipirik_wars.shared.errors import IntegrityError


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
                f"forest outcome {self.name!r}: min ({self.min}) " f"must be <= max ({self.max})"
            )
        return self


class ForestConfig(_Frozen):
    """Конфиг похода в лес (ГДД §8.2)."""

    outcomes: tuple[ForestOutcome, ...] = Field(min_length=1)
    cooldown_min_minutes: int = Field(gt=0)
    cooldown_max_minutes: int = Field(gt=0)

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
                f"oracle.bonus_min ({self.bonus_min}) " f"must be <= bonus_max ({self.bonus_max})"
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
                f"referral.on_thickness_milestones: duplicate thickness " f"in {thicknesses}"
            )
        if thicknesses != sorted(thicknesses):
            raise ValueError(
                f"referral.on_thickness_milestones must be sorted by thickness, "
                f"got {thicknesses}"
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
                f"daily_head.bonus_min ({self.bonus_min}) "
                f"must be <= bonus_max ({self.bonus_max})"
            )
        return self


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


class BalanceConfig(_Frozen):
    """Корневая конфигурация баланса игры.

    Источник правды для ГДД §2.3 (display_names), §8.2 (лес),
    §11 (оракул), §13.1 (рефералка), §3.2 (толщина), §0.5 (DAU-Gate),
    §6.1 (Глава клана дня).

    Целостность display_names проверяется здесь же: первый ряд
    стартует с 0, ряды примыкают друг к другу без дыр и пересечений,
    последний ряд имеет ``to=null`` (бесконечный хвост).
    """

    version: int = Field(ge=1)
    display_names: tuple[DisplayNameRange, ...] = Field(min_length=1)
    forest: ForestConfig
    oracle: OracleConfig
    referral: ReferralConfig
    thickness: ThicknessConfig
    dau_gate: DauGateConfig
    daily_head: DailyHeadConfig
    content_policy: ContentPolicy

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
