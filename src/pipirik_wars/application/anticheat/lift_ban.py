"""Use-case `LiftAnticheatBan` (Спринт 1.6.G; ГДД §3.3, §18.6).

Снимает `Player.anticheat_ban_until` вручную — для случаев, когда
trip-wire 1.6.D отработал «false-positive» (например, легитимная
донат-конверсия не была классифицирована как donate-источник, или
админ уже разобрался в `audit_log` и подтвердил, что прирост
был правомерным).

Доступно **только активному `super_admin`** (см.
`Admin.can_lift_anticheat_ban()`). Поведение:

1. Проверка прав → `AuthorizationError` (без state change, без
   audit-записи: мы не светим попытку нелегитимному пользователю).
2. Загрузка `Player` по `tg_id` → `PlayerNotFoundError`, если такого
   игрока нет (handler сконвертирует в дружелюбный текст).
3. Если игрок не в soft-ban-е (`anticheat_ban_until is None` ИЛИ
   уже истёк) — возвращаем результат `was_banned=False` без
   мутаций и без записи в audit. Идемпотентно.
4. Иначе: `player.with_anticheat_ban_lifted(now=now)` →
   `players.save(...)` → audit `ANTICHEAT_BAN_LIFTED` с обязательной
   `reason`-причиной от админа (`/anticheat_unban <tg_id> <reason>`),
   `target_kind="player"`, `target_id=str(player_id)`,
   `idempotency_key="anticheat_unban:{actor}:{target}:{ts}"` (на
   случай повторного клика — отдельная запись на каждое действие).

Транзакция: вся мутация + audit — внутри одного `IUnitOfWork`
(`async with self._uow:`). Неуспех audit-записи откатывает снятие
бана, иначе мы потеряли бы важнейший след для расследования.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pipirik_wars.application.auth.decorators import AuthorizationError
from pipirik_wars.domain.admin import IAdminRepository
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
    """Use-case ручного снятия anti-cheat soft-ban-а (super_admin only)."""

    __slots__ = ("_admins", "_audit", "_clock", "_players", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        admins: IAdminRepository,
        players: IPlayerRepository,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._admins = admins
        self._players = players
        self._audit = audit
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

        # `IAdminRepository` (SqlAlchemy) и `IPlayerRepository` оба тянут
        # `uow.session` — открываем транзакцию заранее, чтобы и authz, и
        # последующая мутация выполнились в одном snapshot-е (защита от
        # гонки «админа деактивировали между authz и мутацией»).
        async with self._uow:
            admin = await self._admins.get_by_tg_id(actor_tg_id)
            if admin is None or not admin.can_lift_anticheat_ban():
                raise AuthorizationError(
                    requirement="admin_lift_anticheat_ban",
                    detail=(
                        f"actor tg_id={actor_tg_id} cannot lift anti-cheat ban "
                        "(super_admin required)"
                    ),
                )

            now = self._clock.now()
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
