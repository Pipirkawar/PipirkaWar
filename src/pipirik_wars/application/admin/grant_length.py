"""Use-case `GrantLength` (Спринт 2.5-C.1, ГДД §16 / §6).

`/grant_length <tg_id> <±cm> <reason>` — ручная мутация длины игрока.
TOTP-обязательная (`Admin.role >= economist`). Запускается **только
после успешного `VerifyAdminConfirm`** (handler в `bot/handlers/admin_support`
зовёт `GrantLength.execute()` из `command_kind="grant_length"`-ветки
`/confirm`-dispatcher-а).

Контракт:

- Актор остаётся активным админом (защита-в-глубину: между request- и
  verify-фазами TOTP-flow актор мог быть `revoke`-нут).
- `delta_cm != 0` и `reason` непустой (UX-инварианты, handler уже
  валидирует, но дублируем — Container можно подменить).
- Цель существует — иначе `PlayerNotFoundError`.
- Цель не забанена — иначе `GrantLengthBlockedError(reason="player_banned")`
  (бан — последняя инстанция, длина мёртвому игроку не положена).

Алгоритм (один UoW, две audit-записи в одной транзакции):

1. Резолвим `Player.id` через `IPlayerRepository.get_by_tg_id(target_tg_id)`.
2. Открываем `async with uow:`.
3. Зовём `ILengthGranter.grant(player_id=player.id, delta_cm=delta,
   source=ADMIN_GRANT|ADMIN_REFUND, reason=reason, idempotency_key=...)`.
   - `delta_cm > 0` → `AuditSource.ADMIN_GRANT` (в anti-cheat-окно `3 000 см / сутки`).
   - `delta_cm < 0` → `AuditSource.ADMIN_REFUND` (clamp **не** применяется,
     но запись в окно идёт — для отчётов ГДД §6).
   - `AddLength` сам пишет `AuditAction.LENGTH_GRANT` в общий `audit_log`.
4. Пишем `AdminAuditAction.ADMIN_GRANT_LENGTH` в `admin_audit_log` —
   это «админская» запись (актор-админ, не игрок), параллельная
   общему `LENGTH_GRANT`. Обе записи нужны: первая отвечает на «кто
   вообще трогал длину», вторая — на «какие админ-действия совершал
   данный economist» (`/audit <admin>` в 2.5-D).

Идемпотентность: `idempotency_key` строится handler-ом из
`(admin_id, command="grant_length", target_tg_id, minute_floor(ts))` и
прокидывается в `AddLength.grant(idempotency_key=...)`. Это даёт
защиту от двойного нажатия в Telegram. Одновременно `AddLength` сам
кладёт ключ в `IIdempotencyKey` — повторный вызов в ту же минуту
вернёт `applied_delta_cm=0` и не запишет в `audit_log` (а наш
`ADMIN_GRANT_LENGTH` тоже не запишется — мы пропускаем audit при
`is_idempotent_replay`).
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import (
    AdminAuditAction,
    AdminAuditEntry,
    AdminAuditSource,
    IAdminAuditLogger,
    IAdminRepository,
)
from pipirik_wars.domain.player import IPlayerRepository, PlayerStatus
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.length_granter import (
    ILengthGranter,
    LengthGrantResult,
)
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork
from pipirik_wars.domain.shared.ports.audit import AuditSource


class GrantLengthBlockedError(Exception):
    """Грант длины невозможен (например, игрок забанен).

    Это бизнес-инвариант, а не ошибка валидации входа: handler ловит
    отдельным `except`-ом и сообщает «нельзя начислить — игрок забанен».
    """

    __slots__ = ("reason", "tg_id")

    def __init__(self, *, tg_id: int, reason: str) -> None:
        super().__init__(f"GrantLength blocked for tg_id={tg_id}: {reason}")
        self.tg_id = tg_id
        self.reason = reason


@dataclass(frozen=True, slots=True)
class GrantLengthInput:
    actor_tg_id: int
    target_tg_id: int
    delta_cm: int
    reason: str
    idempotency_key: str
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class GrantLengthOutput:
    target_tg_id: int
    applied_delta_cm: int
    clamped_from: int | None
    triggered_soft_ban: bool
    new_length_cm: int
    was_idempotent_replay: bool


class GrantLength:
    """Use-case ручной правки длины игрока (после TOTP-подтверждения)."""

    __slots__ = ("_admins", "_audit", "_clock", "_length_granter", "_players", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        players: IPlayerRepository,
        length_granter: ILengthGranter,
        audit: IAdminAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._players = players
        self._length_granter = length_granter
        self._audit = audit
        self._clock = clock

    async def execute(self, inp: GrantLengthInput) -> GrantLengthOutput:
        admin = await self._admins.get_by_tg_id(inp.actor_tg_id)
        if admin is None or not admin.is_active:
            raise AuthorizationError(
                requirement="admin_active",
                detail=f"actor tg_id={inp.actor_tg_id} is not an active admin",
            )
        admin_id = admin.id
        if admin_id is None:  # pragma: no cover
            raise RuntimeError("admin.id is None after get_by_tg_id")

        if inp.delta_cm == 0:
            raise ValueError("GrantLength.delta_cm must be non-zero")
        if not inp.reason or not inp.reason.strip():
            raise ValueError("GrantLength.reason must be a non-empty string")
        reason = inp.reason.strip()

        source = AuditSource.ADMIN_GRANT if inp.delta_cm > 0 else AuditSource.ADMIN_REFUND

        now = self._clock.now()
        async with self._uow:
            player = await self._players.get_by_tg_id(inp.target_tg_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=inp.target_tg_id)
            if player.status is PlayerStatus.BANNED:
                raise GrantLengthBlockedError(
                    tg_id=inp.target_tg_id,
                    reason="player_banned",
                )
            if player.id is None:  # pragma: no cover
                raise RuntimeError("player.id is None after get_by_tg_id")

            length_before_cm = player.length.cm
            grant_result: LengthGrantResult = await self._length_granter.grant(
                player_id=player.id,
                delta_cm=inp.delta_cm,
                source=source,
                reason=reason,
                idempotency_key=inp.idempotency_key,
            )

            was_idempotent_replay = (
                grant_result.applied_delta_cm == 0
                and grant_result.new_length_cm == length_before_cm
            )

            if not was_idempotent_replay:
                await self._audit.record(
                    AdminAuditEntry(
                        admin_id=admin_id,
                        action=AdminAuditAction.ADMIN_GRANT_LENGTH,
                        target_kind="player",
                        target_id=str(inp.target_tg_id),
                        before={"length_cm": length_before_cm},
                        after={"length_cm": grant_result.new_length_cm},
                        reason=reason,
                        idempotency_key=inp.idempotency_key,
                        source=AdminAuditSource.BOT,
                        tg_chat_id=inp.tg_chat_id,
                        ip=None,
                        occurred_at=now,
                    ),
                )

        return GrantLengthOutput(
            target_tg_id=inp.target_tg_id,
            applied_delta_cm=grant_result.applied_delta_cm,
            clamped_from=grant_result.clamped_from,
            triggered_soft_ban=grant_result.triggered_soft_ban,
            new_length_cm=grant_result.new_length_cm,
            was_idempotent_replay=was_idempotent_replay,
        )


__all__ = [
    "GrantLength",
    "GrantLengthBlockedError",
    "GrantLengthInput",
    "GrantLengthOutput",
]
