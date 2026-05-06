"""Use-case `BanPlayer` (Спринт 2.5-B.4, ГДД §18.6).

`/ban <tg_id> <reason>` — необратимый бан игрока. Запускается **только
после успешного `VerifyAdminConfirm`** (TOTP-подтверждение). Сама
`BanPlayer.execute()` повторно проверяет:

1. Актор всё ещё активный админ (защита-в-глубину: между `RequestAdminConfirm`
   и `VerifyAdminConfirm` мог быть `revoke`).
2. Цель существует — иначе `PlayerNotFoundError`.
3. Цель ещё не забанена — иначе `was_already_banned=True` (handler покажет
   «уже забанен», audit не пишется).

Аудит `ADMIN_PLAYER_BANNED` обязателен и идёт в одной транзакции UoW
вместе с `IPlayerRepository.save(banned)`. `before/after` фиксируют
`status` (active|frozen → banned).
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
from pipirik_wars.domain.shared.ports import IClock, IUnitOfWork


@dataclass(frozen=True, slots=True)
class BanPlayerInput:
    actor_tg_id: int
    target_tg_id: int
    reason: str
    tg_chat_id: int | None = None


@dataclass(frozen=True, slots=True)
class BanPlayerOutput:
    target_tg_id: int
    was_already_banned: bool


class BanPlayer:
    """Use-case необратимого бана игрока (после TOTP-подтверждения)."""

    __slots__ = ("_admins", "_audit", "_clock", "_players", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        players: IPlayerRepository,
        audit: IAdminAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._players = players
        self._audit = audit
        self._clock = clock

    async def execute(self, inp: BanPlayerInput) -> BanPlayerOutput:
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
            # Бан без причины — нонсенс. Доменно — ValueError, чтобы
            # не вылилось в полноценное исключение из application
            # (handler контролирует, что reason заполнен).
            raise ValueError("BanPlayer.reason must be a non-empty string")
        reason = inp.reason.strip()

        now = self._clock.now()
        async with self._uow:
            player = await self._players.get_by_tg_id(inp.target_tg_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=inp.target_tg_id)

            if player.status is PlayerStatus.BANNED:
                # Идемпотентный no-op. В audit ничего — операция уже
                # отражена предыдущим ADMIN_PLAYER_BANNED-ом.
                return BanPlayerOutput(
                    target_tg_id=inp.target_tg_id,
                    was_already_banned=True,
                )

            banned = player.ban(now=now)
            await self._players.save(banned)

            await self._audit.record(
                AdminAuditEntry(
                    admin_id=admin_id,
                    action=AdminAuditAction.ADMIN_PLAYER_BANNED,
                    target_kind="player",
                    target_id=str(inp.target_tg_id),
                    before={"status": player.status.value},
                    after={"status": banned.status.value},
                    reason=reason,
                    idempotency_key=None,
                    source=AdminAuditSource.BOT,
                    tg_chat_id=inp.tg_chat_id,
                    ip=None,
                    occurred_at=now,
                ),
            )

        return BanPlayerOutput(
            target_tg_id=inp.target_tg_id,
            was_already_banned=False,
        )


__all__ = ["BanPlayer", "BanPlayerInput", "BanPlayerOutput"]
