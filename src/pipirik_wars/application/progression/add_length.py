"""Use-case `AddLength` — реализация `ILengthGranter` (Спринт 1.6.D, ГДД §3.3).

Единая точка прибавки длины игроку с anti-cheat hardcap-ом. Вызывается
другими use-case-ами (`FinishForestRun`, `InvokeOracle`, `RegisterPlayer`
с реферальным бонусом и т. п.) через DI-порт `ILengthGranter`. Перевод
существующих use-cases на `AddLength` — отдельная задача (Спринт 1.6.F).

Алгоритм (всё внутри одной `IUnitOfWork`-транзакции):

1. **Валидация входа** (вне транзакции, до `__aenter__`):
   * `source = AuditSource.UNKNOWN` → `LengthDeltaInvalidError`
     (backfill-маркер, не реальный источник).
   * `delta_cm = 0` → `LengthDeltaInvalidError` (no-op симптом бага).
   * `delta_cm < 0` для не-`admin_refund` → `LengthDeltaInvalidError`.
   * `delta_cm > 0` для `admin_refund` → `LengthDeltaInvalidError`
     (refund — это сторно, должно быть отрицательным).

2. **Идемпотентность**: если `idempotency_key` передан и уже виден
   у `IIdempotencyKey` → возврат no-op результата без mutate
   (`applied_delta_cm=0`, `clamped_from=None`, `triggered_soft_ban=False`,
   `new_length_cm` = текущая длина игрока).

3. **Загрузка игрока**: `players.get_by_id(player_id)`. Нет → `PlayerNotFoundError`.

4. **Soft-ban-гейт**: `player.is_anticheat_banned(now=clock.now())` →
   `AnticheatSoftBanError`. Мутаций нет, транзакция откатывается
   автоматически через `__aexit__`.

5. **Определение фактической дельты**:
   * Если `source ∈ balance.anticheat.organic_sources` (whitelist):
     - `daily = anticheat.sum_organic_in_window(since=now-24h, ...)`
     - `weekly = anticheat.sum_organic_in_window(since=now-7d, ...)`
     - `remaining = min(daily.remaining_cap_cm(daily_cap), weekly.remaining_cap_cm(weekly_cap))`
     - `applied = min(delta_cm, remaining)` (≥ 0)
     - `clamped_from = delta_cm if applied < delta_cm else None`
   * Иначе (`donate_sources`, `admin_refund`, прочее) → clamp не применяется,
     `applied = delta_cm`, `clamped_from = None`.

6. **Mutate**: если `applied != 0` →
   `player.with_length(Length(player.length + applied))` → `players.save(...)`.

7. **Audit `LENGTH_GRANT`** в той же транзакции:
   `AuditEntry(action=LENGTH_GRANT, source=source, delta_cm=applied,
   clamped_from=clamped_from, idempotency_key=idempotency_key, ...)`.

8. **`IIdempotencyKey.mark`** (если `idempotency_key`).

9. **Trip-wire** (только для organic-источников и только если `applied > 0`):
   * Рекомпьют `daily_after` / `weekly_after` (включая только что записанный delta).
   * Если `daily_after.is_exceeded(cap)` или `weekly_after.is_exceeded(cap)` →
     - `player.with_anticheat_ban(until=now + soft_ban_duration_days)` → `save`.
     - Audit `ANTICHEAT_DAILY_CAP_EXCEEDED` / `ANTICHEAT_WEEKLY_CAP_EXCEEDED`
       (без `delta_cm`/`clamped_from` — это бан-событие, не прибавка).
     - `IAnticheatAdminAlerter.emit(...)` (best-effort алёрт админу).
   * Иначе — `triggered_soft_ban = False`.

10. Возврат `LengthGrantResult`.

Важные инварианты:

- **Все `IAnticheatRepository.sum_organic_in_window`-запросы внутри одной
  транзакции** — это позволяет, при `REPEATABLE READ`-уровне изоляции
  Postgres-а, гарантировать, что параллельные `add_length`-вызовы
  одного игрока не «прорвутся» через cap (race-test проверяет это
  на 100 параллельных вызовах).
- **Audit пишется ДО trip-wire-проверки** — иначе trip-wire не увидит
  только что применённую дельту в окне. Audit и trip-wire — в одной
  транзакции, всё откатится при ошибке.
- **`triggered_soft_ban` не выставляется для повторных вызовов** на
  уже-забаненного игрока: они стопаются на soft-ban-гейте в шаге 4.
  Соответственно admin-alerter эмитится **ровно один раз** — на момент
  перехода из «не в бане» в «в бане».
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final

from pipirik_wars.domain.anticheat import IAnticheatAdminAlerter, IAnticheatRepository
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import IPlayerRepository, Length, Player
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.errors import (
    AnticheatSoftBanError,
    LengthDeltaInvalidError,
)
from pipirik_wars.domain.progression.length_granter import (
    ILengthGranter,
    LengthGrantResult,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IIdempotencyKey,
    IUnitOfWork,
)
from pipirik_wars.domain.shared.ports.audit import AuditSource

_IDEMPOTENCY_NAMESPACE: Final[str] = "add_length"
"""Namespace для `IIdempotencyKey`-меток, чтобы ключи `add_length` не
конфликтовали с другими use-case-ами (forest_run, oracle, и т. п.).

Caller передаёт сырой ключ; `AddLength` внутри использует `is_seen` /
`mark` без префикса (caller отвечает за уникальность сам)."""


class AddLength(ILengthGranter):
    """Реализация `ILengthGranter` через UoW-транзакцию + clamp + trip-wire."""

    __slots__ = (
        "_admin_alerter",
        "_anticheat",
        "_audit",
        "_balance",
        "_clock",
        "_idempotency",
        "_players",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        anticheat: IAnticheatRepository,
        audit: IAuditLogger,
        balance: IBalanceConfig,
        clock: IClock,
        idempotency: IIdempotencyKey,
        admin_alerter: IAnticheatAdminAlerter,
    ) -> None:
        self._uow = uow
        self._players = players
        self._anticheat = anticheat
        self._audit = audit
        self._balance = balance
        self._clock = clock
        self._idempotency = idempotency
        self._admin_alerter = admin_alerter

    async def grant(
        self,
        *,
        player_id: int,
        delta_cm: int,
        source: AuditSource,
        reason: str,
        idempotency_key: str | None = None,
    ) -> LengthGrantResult:
        """См. `ILengthGranter.grant`."""
        # 1. Validate input (вне транзакции — это инварианты вызова).
        self._validate_input(delta_cm=delta_cm, source=source)

        async with self._uow:
            # 2. Idempotency check.
            if idempotency_key is not None and await self._idempotency.is_seen(idempotency_key):
                player = await self._players.get_by_id(player_id=player_id)
                if player is None:
                    raise PlayerNotFoundError(tg_id=player_id)
                return LengthGrantResult(
                    applied_delta_cm=0,
                    clamped_from=None,
                    triggered_soft_ban=False,
                    new_length_cm=player.length.cm,
                )

            # 3. Load player.
            player = await self._players.get_by_id(player_id=player_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=player_id)

            # 4. Soft-ban gate.
            now = self._clock.now()
            if player.is_anticheat_banned(now=now):
                assert player.anticheat_ban_until is not None
                raise AnticheatSoftBanError(
                    tg_id=player.tg_id,
                    banned_until=player.anticheat_ban_until,
                )

            anticheat_cfg = self._balance.get().anticheat
            organic_sources = anticheat_cfg.organic_sources
            is_organic = source in organic_sources

            # 5. Determine applied delta.
            if is_organic:
                applied_delta, clamped_from = await self._compute_clamp(
                    player_id=player_id,
                    delta_cm=delta_cm,
                    daily_cap_cm=anticheat_cfg.daily_cap_cm,
                    weekly_cap_cm=anticheat_cfg.weekly_cap_cm,
                    organic_sources=organic_sources,
                    now=now,
                )
            else:
                applied_delta = delta_cm
                clamped_from = None

            # 6. Mutate (если есть что применять).
            length_before_cm = player.length.cm
            if applied_delta != 0:
                new_length = Length(cm=length_before_cm + applied_delta)
                player_after = player.with_length(new_length, now=now)
                saved = await self._players.save(player_after)
            else:
                saved = player

            # 7. Audit LENGTH_GRANT.
            assert player.id is not None
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.LENGTH_GRANT,
                    actor_id=player.tg_id,
                    target_kind="player",
                    target_id=str(player.id),
                    before={"length_cm": length_before_cm},
                    after={"length_cm": saved.length.cm},
                    reason=reason,
                    idempotency_key=idempotency_key,
                    occurred_at=now,
                    source=source,
                    clamped_from=clamped_from,
                    delta_cm=applied_delta,
                )
            )

            # 8. Mark idempotency.
            if idempotency_key is not None:
                await self._idempotency.mark(idempotency_key, namespace=_IDEMPOTENCY_NAMESPACE)

            # 9. Trip-wire (только для organic + applied > 0).
            triggered_soft_ban = False
            if is_organic and applied_delta > 0:
                triggered_soft_ban = await self._maybe_trip_wire(
                    player_id=player_id,
                    daily_cap_cm=anticheat_cfg.daily_cap_cm,
                    weekly_cap_cm=anticheat_cfg.weekly_cap_cm,
                    soft_ban_duration_days=anticheat_cfg.soft_ban_duration_days,
                    organic_sources=organic_sources,
                    source=source,
                    saved_player=saved,
                    now=now,
                )
                if triggered_soft_ban:
                    saved = await self._players.get_by_id(player_id=player_id) or saved

            return LengthGrantResult(
                applied_delta_cm=applied_delta,
                clamped_from=clamped_from,
                triggered_soft_ban=triggered_soft_ban,
                new_length_cm=saved.length.cm,
            )

    @staticmethod
    def _validate_input(*, delta_cm: int, source: AuditSource) -> None:
        if source is AuditSource.UNKNOWN:
            raise LengthDeltaInvalidError(
                delta_cm=delta_cm,
                source=source.value,
                reason_code="unknown_source",
            )
        if delta_cm == 0:
            raise LengthDeltaInvalidError(
                delta_cm=delta_cm,
                source=source.value,
                reason_code="zero",
            )
        if delta_cm < 0 and source is not AuditSource.ADMIN_REFUND:
            raise LengthDeltaInvalidError(
                delta_cm=delta_cm,
                source=source.value,
                reason_code="negative_for_non_refund",
            )
        if delta_cm > 0 and source is AuditSource.ADMIN_REFUND:
            raise LengthDeltaInvalidError(
                delta_cm=delta_cm,
                source=source.value,
                reason_code="positive_for_refund",
            )

    async def _compute_clamp(
        self,
        *,
        player_id: int,
        delta_cm: int,
        daily_cap_cm: int,
        weekly_cap_cm: int,
        organic_sources: tuple[AuditSource, ...],
        now: datetime,
    ) -> tuple[int, int | None]:
        daily_window = await self._anticheat.sum_organic_in_window(
            player_id=player_id,
            since=now - timedelta(hours=24),
            organic_sources=organic_sources,
        )
        weekly_window = await self._anticheat.sum_organic_in_window(
            player_id=player_id,
            since=now - timedelta(days=7),
            organic_sources=organic_sources,
        )
        remaining = min(
            daily_window.remaining_cap_cm(cap_cm=daily_cap_cm),
            weekly_window.remaining_cap_cm(cap_cm=weekly_cap_cm),
        )
        applied = min(delta_cm, remaining)
        clamped_from = delta_cm if applied < delta_cm else None
        return applied, clamped_from

    async def _maybe_trip_wire(
        self,
        *,
        player_id: int,
        daily_cap_cm: int,
        weekly_cap_cm: int,
        soft_ban_duration_days: int,
        organic_sources: tuple[AuditSource, ...],
        source: AuditSource,
        saved_player: Player,
        now: datetime,
    ) -> bool:
        daily_after = await self._anticheat.sum_organic_in_window(
            player_id=player_id,
            since=now - timedelta(hours=24),
            organic_sources=organic_sources,
        )
        weekly_after = await self._anticheat.sum_organic_in_window(
            player_id=player_id,
            since=now - timedelta(days=7),
            organic_sources=organic_sources,
        )

        cap_kind: str | None = None
        cap_cm: int = 0
        observed_sum_cm: int = 0
        if daily_after.is_exceeded(cap_cm=daily_cap_cm):
            cap_kind = "daily"
            cap_cm = daily_cap_cm
            observed_sum_cm = daily_after.organic_sum_cm
        elif weekly_after.is_exceeded(cap_cm=weekly_cap_cm):
            cap_kind = "weekly"
            cap_cm = weekly_cap_cm
            observed_sum_cm = weekly_after.organic_sum_cm

        if cap_kind is None:
            return False

        ban_until = now + timedelta(days=soft_ban_duration_days)
        banned_player = saved_player.with_anticheat_ban(until=ban_until, now=now)
        await self._players.save(banned_player)

        action = (
            AuditAction.ANTICHEAT_DAILY_CAP_EXCEEDED
            if cap_kind == "daily"
            else AuditAction.ANTICHEAT_WEEKLY_CAP_EXCEEDED
        )
        assert saved_player.id is not None
        await self._audit.record(
            AuditEntry(
                action=action,
                actor_id=None,
                target_kind="player",
                target_id=str(saved_player.id),
                before={"anticheat_ban_until": None},
                after={"anticheat_ban_until": ban_until.isoformat()},
                reason=f"anticheat_trip_wire_{cap_kind}",
                idempotency_key=None,
                occurred_at=now,
                source=source,
                clamped_from=None,
                delta_cm=None,
            )
        )

        await self._admin_alerter.emit(
            player_id=saved_player.id,
            cap_kind=cap_kind,
            cap_cm=cap_cm,
            observed_sum_cm=observed_sum_cm,
            source=source,
            banned_until=ban_until,
            occurred_at=now,
        )

        return True
