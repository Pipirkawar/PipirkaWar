"""Use-case `LiftAnticheatBan` (Спринт 1.6.G → 2.5-D.7; ГДД §3.3, §18.6).

Снимает `Player.anticheat_ban_until` вручную — для случаев, когда
trip-wire 1.6.D отработал «false-positive» (например, легитимная
донат-конверсия не была классифицирована как donate-источник, или
админ уже разобрался в `audit_log` и подтвердил, что прирост
был правомерным).

Доступ — через RBAC-матрицу `IAdminAuthorizationPolicy.is_authorized(
admin, AdminCommandKind.LIFT_ANTICHEAT_BAN)` (по умолчанию — только
`super_admin`, см. `RoleBasedAdminAuthorizationPolicy`).

Поведение:

1. Загрузка `Admin` + проверка `is_active` → `AuthorizationError`.
2. `ensure_admin_authorized(...)` (Спринт 2.5-D.8) — RBAC; при отказе
   пишет `ADMIN_AUTHORIZATION_DENIED` в admin-audit-логе и поднимает
   `AdminAuthorizationDeniedError`. Намеренно: попытка эскалации
   привилегий фиксируется в аудите — в отличие от 1.6.G,
   где «inactive-non-super_admin» не светился.
3. Загрузка `Player` по `tg_id` → `PlayerNotFoundError`.
4. Если игрок не в soft-ban-е — возвращаем результат
   `was_banned=False` без мутаций и без записи в audit.
5. Иначе: `player.with_anticheat_ban_lifted(now=now)` →
   `players.save(...)` → audit `ANTICHEAT_BAN_LIFTED`.

Транзакция: проверки и RBAC — до основного UoW; сама мутация +
системный audit — внутри одного `async with self._uow:`. Неуспех
save/audit откатывает снятие бана.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pipirik_wars.application.admin._authorization import ensure_admin_authorized
from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminCommandKind,
    IAdminAuditLogger,
    IAdminAuthorizationPolicy,
    IAdminRepository,
)
from pipirik_wars.domain.player import IPlayerRepository
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class LiftAnticheatBanResult:
    """Что получилось.

    Поля:
    - `target_tg_id` — `tg_id` целевого игрока (повтор для удобства handler-а).
    - `was_banned` — `True`, если бан был активен на момент вызова
      (т. е. реально сняли). `False` — идемпотентный no-op.
    - `banned_until_before` — значение `anticheat_ban_until` до снятия,
      или `None`, если был не в бане.
    - `reason` — причина, переданная админом (для answer-сообщения).
    """

    target_tg_id: int
    was_banned: bool
    banned_until_before: datetime | None
    reason: str


class LiftAnticheatBan:
    """Use-case ручного снятия anti-cheat soft-ban-а (super_admin only по дефолту)."""

    __slots__ = (
        "_admin_audit",
        "_admins",
        "_audit",
        "_authz",
        "_clock",
        "_players",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        players: IPlayerRepository,
        audit: IAuditLogger,
        admin_audit: IAdminAuditLogger,
        authz: IAdminAuthorizationPolicy,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._players = players
        self._audit = audit
        self._admin_audit = admin_audit
        self._authz = authz
        self._clock = clock

    async def execute(
        self,
        *,
        actor_tg_id: int,
        target_tg_id: int,
        reason: str,
    ) -> LiftAnticheatBanResult:
        """Снять soft-ban с игрока `target_tg_id`.

        Бросает:

        - `AuthorizationError` — если актор не активный `super_admin`.
        - `PlayerNotFoundError` — если игрока с таким `tg_id` нет.
        - `ValueError` — если `reason` пустой/whitespace.
        """
        cleaned_reason = reason.strip()
        if not cleaned_reason:
            raise ValueError("reason must be non-empty (admin must justify the unban)")

        # Админ-lookup и RBAC — до основного UoW. `ensure_admin_authorized`
        # сам открывает свой короткий UoW для записи ADMIN_AUTHORIZATION_DENIED;
        # это важно именно для случая deny — иначе обёрнув в общий UoW,
        # мы потеряли бы фиксацию попытки эскалации при rollback-е.
        admin = await self._admins.get_by_tg_id(actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_lift_anticheat_ban",
                detail=f"actor tg_id={actor_tg_id} is not an active admin",
            )

        now = self._clock.now()
        await ensure_admin_authorized(
            admin=admin,
            command_kind=AdminCommandKind.LIFT_ANTICHEAT_BAN,
            policy=self._authz,
            audit=self._admin_audit,
            uow=self._uow,
            target_kind="player",
            target_id=str(target_tg_id),
            tg_chat_id=None,
            occurred_at=now,
        )

        async with self._uow:
            player = await self._players.get_by_tg_id(target_tg_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=target_tg_id)

            if not player.is_anticheat_banned(now=now):
                # Идемпотентный no-op: бан и так не активен (None или истёк).
                # Audit не пишем — сохраняем минимальный шум в логе.
                return LiftAnticheatBanResult(
                    target_tg_id=target_tg_id,
                    was_banned=False,
                    banned_until_before=player.anticheat_ban_until,
                    reason=cleaned_reason,
                )

            banned_until_before = player.anticheat_ban_until
            updated = player.with_anticheat_ban_lifted(now=now)
            await self._players.save(updated)

            assert player.id is not None
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.ANTICHEAT_BAN_LIFTED,
                    actor_id=admin.id,
                    target_kind="player",
                    target_id=str(player.id),
                    before={
                        "anticheat_ban_until": (
                            banned_until_before.isoformat()
                            if banned_until_before is not None
                            else None
                        ),
                    },
                    after={"anticheat_ban_until": None},
                    reason=cleaned_reason,
                    idempotency_key=(
                        f"anticheat_unban:{actor_tg_id}:{target_tg_id}:{int(now.timestamp())}"
                    ),
                    occurred_at=now,
                )
            )

        return LiftAnticheatBanResult(
            target_tg_id=target_tg_id,
            was_banned=True,
            banned_until_before=banned_until_before,
            reason=cleaned_reason,
        )
