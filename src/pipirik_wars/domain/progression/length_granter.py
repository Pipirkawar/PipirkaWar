"""Порт `ILengthGranter` — единая точка прибавки длины игроку (Спринт 1.6.D).

Зачем порт нужен:

- ГДД §3.3 / ПД §4 / Спринт 1.6: anti-cheat hardcap на organic-прирост
  длины. Хардкап пропускает дельту насквозь только если суммарный
  organic-прирост в текущем rolling-окне (24 ч / 7 дн) + новая дельта
  ≤ `daily_cap_cm` / `weekly_cap_cm`. Иначе — clamp до остатка лимита,
  audit с `clamped_from`, и при пробитии лимита — soft-ban на
  `soft_ban_duration_days`.
- Все use-cases, которые **дают** длину (`FinishForestRun`, `InvokeOracle`,
  `RegisterPlayer` с реферальным бонусом, `/admin_grant`, в будущем —
  PvP-награды, караван, рейды), будут переведены в Спринте 1.6.F на
  вызов этого порта вместо прямого `player.with_length(...)` +
  `repo.save(player)` + `audit.record(LENGTH_GRANT)`. До 1.6.F они
  работают по-старому — порт уже есть, но никто из старых use-cases
  его пока не зовёт. Это сделано намеренно: 1.6.D вводит ИСКЛЮЧИТЕЛЬНО
  механизм; миграция точек вызова — отдельным узким PR-ом.

Реализация порта — `application/progression/add_length.py::AddLength`.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass

from pipirik_wars.domain.shared.ports.audit import AuditSource


@dataclass(frozen=True, slots=True)
class LengthGrantResult:
    """Итог одного вызова `ILengthGranter.grant(...)`.

    Использует caller — handler / другой use-case — чтобы понять,
    сработал ли clamp (для UX-сообщения «вам выдали Y вместо запрошенных
    X из-за хардкапа») и сработал ли trip-wire (для UX «вы были
    забанены за подозрительную активность»).

    Поля:
    - `applied_delta_cm` — фактически применённая дельта в см. Знаковая.
      Может быть `0` — если организм исчерпал лимит, или если caller
      запросил `delta_cm=0` (no-op). Для donate-источников — всегда
      равно запрошенной дельте.
    - `clamped_from` — `None`, если clamp не срабатывал; иначе исходная
      запрошенная дельта (в см) до подрезки. UX рендерит «выдано
      `applied_delta_cm` см вместо `clamped_from`».
    - `triggered_soft_ban` — `True`, если этот вызов перевёл игрока
      в soft-ban (после save суммарное окно превысило `cap_cm` строго).
      Значит `Player.anticheat_ban_until` теперь `now + soft_ban_duration_days`.
    - `new_length_cm` — длина игрока после применения дельты (в см).
      Caller использует для рендера «новая длина: N см».
    """

    applied_delta_cm: int
    clamped_from: int | None
    triggered_soft_ban: bool
    new_length_cm: int

    def __post_init__(self) -> None:
        if self.new_length_cm < 0:
            raise ValueError(f"new_length_cm must be >= 0, got {self.new_length_cm}")
        if self.clamped_from is not None and self.clamped_from < self.applied_delta_cm:
            raise ValueError(
                f"clamped_from ({self.clamped_from}) must be >= applied_delta_cm "
                f"({self.applied_delta_cm}) — clamp всегда уменьшает дельту"
            )


class ILengthGranter(abc.ABC):
    """Контракт «прибавить длину игроку через anti-cheat hardcap».

    Реализация (`AddLength` use-case) гарантирует:

    1. **Soft-ban-гейт**: если игрок в активном soft-ban-е на момент
       `clock.now()` → `AnticheatSoftBanError`, мутаций не делается.
    2. **Clamp**: для organic-источников (whitelist в `balance.yaml::
       anticheat.organic_sources`) дельта подрезается до
       `min(remaining_cap_cm(daily_cap_cm), remaining_cap_cm(weekly_cap_cm))`.
       Для donate-источников clamp не применяется. Для `admin_refund`
       (отрицательные дельты) clamp тоже не применяется.
    3. **Audit**: `AuditAction.LENGTH_GRANT` с `source` / `delta_cm` /
       `clamped_from` записывается в той же UoW-транзакции.
    4. **Trip-wire**: после save рекомпьютим окна; если строго
       превысили (защита от обходов прямым `repo.save(player)`)
       → soft-ban на `soft_ban_duration_days` + audit
       `ANTICHEAT_DAILY_CAP_EXCEEDED` / `ANTICHEAT_WEEKLY_CAP_EXCEEDED`
       + alert админу через `IAnticheatAdminAlerter`.

    `idempotency_key` (опциональный): если передан и уже встречался —
    повторный вызов возвращает кэшированный результат **без** mutate
    и **без** второго audit-а. Реализация использует
    `IIdempotencyKey.is_seen` / `mark` в той же транзакции.

    `delta_cm` должна быть положительной для organic / donate-источников.
    Для `admin_refund` допустима отрицательная — это сторно. Ноль и
    отрицательная для других источников → `LengthDeltaInvalidError`.
    `unknown` источник запрещён вовсе (это backfill-маркер, не реальный
    источник) — также `LengthDeltaInvalidError`.
    """

    @abc.abstractmethod
    async def grant(
        self,
        *,
        player_id: int,
        delta_cm: int,
        source: AuditSource,
        reason: str,
        idempotency_key: str | None = None,
    ) -> LengthGrantResult:
        """Применить дельту длины игроку с anti-cheat-обработкой.

        :raises AnticheatSoftBanError: если игрок в soft-ban-е сейчас.
        :raises LengthDeltaInvalidError: если `delta_cm` некорректна
            для указанного `source`.
        :raises PlayerNotFoundError: если игрока с таким `player_id` нет.
        """
