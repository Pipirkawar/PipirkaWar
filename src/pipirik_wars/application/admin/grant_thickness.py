"""Use-case `GrantThickness` (Спринт 2.5-C.2, ГДД §16 / §3.2).

`/grant_thickness <tg_id> <new_level> <reason>` — ручная установка
уровня толщины. TOTP-обязательная, исполняется после
`VerifyAdminConfirm` через `command_kind="grant_thickness"`-ветку
`/confirm`-dispatcher-а.

Ключевые отличия от `GrantLength`:

- **Абсолютное значение**, не дельта (ГДД §16 — «выставить уровень»).
- **Не идёт через `ILengthGranter`** — толщина и длина — независимые
  оси прогрессии (ГДД §3.2). Прямая мутация `Player.with_thickness(...)`
  + `repo.save(...)`.
- **Ограничения**:
  - снизу: 1 (доменный инвариант `Thickness.level >= 1`);
  - сверху: `max(BalanceConfig.thickness.unlock_levels.values())` —
    если попросили выше — `ThicknessLevelInvalidError(reason="above_max")`.
- Идемпотентность через `IIdempotencyKey` (защита от двойного
  нажатия в Telegram). Дополнительная domain-уровневая идемпотентность:
  если игрок и так уже на запрашиваемом уровне → `was_already_at_level=True`,
  без mutate, без audit-записи.

Алгоритм (один UoW, две развилки):

1. Резолвим `Player` через `IPlayerRepository.get_by_tg_id`.
2. Открываем `async with uow:`.
3. Idempotency check: если ключ уже видели → no-op (вернуть текущий
   уровень, `was_idempotent_replay=True`).
4. Если игрок забанен → `GrantThicknessBlockedError(reason="player_banned")`.
5. Если запрошенный уровень = текущему → no-op (`was_already_at_level=True`,
   audit **не** пишется).
6. Иначе — `player.with_thickness(Thickness(level=new_level), now=now)` →
   `players.save(updated)` → `audit.record(ADMIN_GRANT_THICKNESS, before/after)`
   → `idempotency.mark(...)`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    AdminCommandKind,
    IAdminAuditLogger,
    IAdminAuthorizationPolicy,
    IAdminRepository,
)
from pipirik_wars.domain.balance.ports import IBalanceConfig
from pipirik_wars.domain.player import IPlayerRepository, PlayerStatus, Thickness
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import IClock, IIdempotencyKey, IUnitOfWork

_IDEMPOTENCY_NAMESPACE = "admin_grant_thickness"


class GrantThicknessBlockedError(Exception):
    """Изменение толщины невозможно (игрок забанен)."""

    __slots__ = ("reason", "tg_id")

    def __init__(self, *, tg_id: int, reason: str) -> None:
        super().__init__(f"GrantThickness blocked for tg_id={tg_id}: {reason}")
        self.tg_id = tg_id
        self.reason = reason


class ThicknessLevelInvalidError(Exception):
    """Запрошенный уровень толщины вне допустимого диапазона.

    `reason_code`: `"below_min"` (level < 1) или `"above_max"`
    (level > `max(unlock_levels.values())`).
    """

    __slots__ = ("level", "max_level", "reason_code")

    def __init__(self, *, level: int, max_level: int, reason_code: str) -> None:
        super().__init__(
            f"thickness level={level} invalid: {reason_code} (allowed range 1..{max_level})"
        )
        self.level = level
        self.max_level = max_level
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class GrantThicknessInput:
    actor_tg_id: int
    target_tg_id: int
    new_level: int
    reason: str
    idempotency_key: str
    tg_chat_id: int | None = None
    source: AdminAuditSource = AdminAuditSource.BOT
    ip: str | None = None


@dataclass(frozen=True, slots=True)
class GrantThicknessOutput:
    target_tg_id: int
    previous_level: int
    new_level: int
    was_already_at_level: bool
    was_idempotent_replay: bool


class GrantThickness:
    """Use-case ручной установки уровня толщины (после TOTP-подтверждения)."""

    __slots__ = (
        "_admins",
        "_audit",
        "_authz",
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
        admins: IAdminRepository,
        players: IPlayerRepository,
        balance: IBalanceConfig,
        idempotency: IIdempotencyKey,
        audit: IAdminAuditLogger,
        clock: IClock,
        authz: IAdminAuthorizationPolicy,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._players = players
        self._balance = balance
        self._idempotency = idempotency
        self._audit = audit
        self._clock = clock
        self._authz = authz

    async def execute(self, inp: GrantThicknessInput) -> GrantThicknessOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover
            raise RuntimeError("admin.id is None after get_by_tg_id")

        if not inp.reason or not inp.reason.strip():
            raise ValueError("GrantThickness.reason must be a non-empty string")
        reason = inp.reason.strip()

        unlock_levels = self._balance.get().thickness.unlock_levels
        max_level = max(unlock_levels.values())
        if inp.new_level < 1:
            raise ThicknessLevelInvalidError(
                level=inp.new_level,
                max_level=max_level,
                reason_code="below_min",
            )
        if inp.new_level > max_level:
            raise ThicknessLevelInvalidError(
                level=inp.new_level,
                max_level=max_level,
                reason_code="above_max",
            )

        now = self._clock.now()
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.GRANT_THICKNESS,
            policy=self._authz,
            audit=self._audit,
            uow=self._uow,
            target_kind="player",
            target_id=str(inp.target_tg_id),
            tg_chat_id=inp.tg_chat_id,
            occurred_at=now,
            source=inp.source,
            ip=inp.ip,
        )
        async with self._uow:
            if await self._idempotency.is_seen(inp.idempotency_key):
                player = await self._players.get_by_tg_id(inp.target_tg_id)
                if player is None:
                    raise PlayerNotFoundError(tg_id=inp.target_tg_id)
                return GrantThicknessOutput(
                    target_tg_id=inp.target_tg_id,
                    previous_level=player.thickness.level,
                    new_level=player.thickness.level,
                    was_already_at_level=False,
                    was_idempotent_replay=True,
                )

            player = await self._players.get_by_tg_id(inp.target_tg_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=inp.target_tg_id)
            if player.status is PlayerStatus.BANNED:
                raise GrantThicknessBlockedError(
                    tg_id=inp.target_tg_id,
                    reason="player_banned",
                )

            previous_level = player.thickness.level
            if previous_level == inp.new_level:
                # Domain-уровневая идемпотентность — игрок и так на этом уровне.
                # Audit не пишем (запись отражает «состоявшуюся мутацию»), но
                # ключ ставим — чтобы повтор уже шёл по replay-ветке.
                await self._idempotency.mark(
                    inp.idempotency_key,
                    namespace=_IDEMPOTENCY_NAMESPACE,
                )
                return GrantThicknessOutput(
                    target_tg_id=inp.target_tg_id,
                    previous_level=previous_level,
                    new_level=previous_level,
                    was_already_at_level=True,
                    was_idempotent_replay=False,
                )

            updated = player.with_thickness(
                Thickness(level=inp.new_level),
                now=now,
            )
            await self._players.save(updated)
            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_GRANT_THICKNESS,
                    target_kind="player",
                    target_id=str(inp.target_tg_id),
                    before={"thickness_level": previous_level},
                    after={"thickness_level": inp.new_level},
                    reason=reason,
                    idempotency_key=inp.idempotency_key,
                    source=inp.source,
                    tg_chat_id=inp.tg_chat_id,
                    ip=inp.ip,
                    occurred_at=now,
                ),
            )
            await self._idempotency.mark(
                inp.idempotency_key,
                namespace=_IDEMPOTENCY_NAMESPACE,
            )

        return GrantThicknessOutput(
            target_tg_id=inp.target_tg_id,
            previous_level=previous_level,
            new_level=inp.new_level,
            was_already_at_level=False,
            was_idempotent_replay=False,
        )


__all__ = [
    "GrantThickness",
    "GrantThicknessBlockedError",
    "GrantThicknessInput",
    "GrantThicknessOutput",
    "ThicknessLevelInvalidError",
]
