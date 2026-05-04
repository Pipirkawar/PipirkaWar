"""Use-case `RegisterPlayer` (Спринт 1.1.3 + DAU Gate в 1.2.4).

Регистрирует нового игрока с **стартовыми параметрами** ГДД §1.1:
длина = 2 см, толщина = 1, **титул = None**, **имя = None**.
Это закрытое в ГДД v8 решение: имя/титул выдаются позже геймплеем
(имя — выбивается дропом из леса в Спринте 1.3.5; первый титул —
после первого возвращения из леса в Спринте 1.3.8).

DAU Gate (Спринт 1.2.4, ГДД §18):
- Если `IDauCounter.current() < IDauLimit.get()` — регистрируем сразу
  и возвращаем `PlayerRegistered`.
- Если ёмкость исчерпана — ставим в `signup_queue` и возвращаем
  `PlayerQueued(entry)` с уже посчитанной позицией. Handler покажет
  игроку «серверы переполнены, позиция #N».

Идемпотентность:
- Дубль `tg_id` в `users` → `PlayerAlreadyRegisteredError` (handler
  покажет «вы уже зарегистрированы»).
- Дубль `tg_id` в `signup_queue` → `AlreadyQueuedError` (handler
  покажет текущую позицию вместо «вы уже стояли в очереди»).

Audit-запись пишется атомарно с действием:
- успешная регистрация → `PLAYER_REGISTER`;
- постановка в очередь → `PLAYER_QUEUED` с позицией.

`record_active(...)` зовём только при успешной регистрации, чтобы
очередники не «съедали» лимит и не блокировали себя же.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pipirik_wars.application.dau import CheckDauThreshold
from pipirik_wars.application.dto.inputs import RegisterPlayerInput
from pipirik_wars.domain.dau import IDauCounter, IDauLimit
from pipirik_wars.domain.player import (
    IPlayerRepository,
    Player,
    Username,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)
from pipirik_wars.domain.signup_queue import (
    AlreadyQueuedError,
    ISignupQueueRepository,
    SignupQueueEntry,
)


@dataclass(frozen=True, slots=True)
class PlayerRegistered:
    """Результат успешной регистрации (ёмкость DAU была свободна)."""

    player: Player


@dataclass(frozen=True, slots=True)
class PlayerQueued:
    """Результат постановки в очередь (DAU >= MAX_DAU)."""

    entry: SignupQueueEntry


RegisterPlayerResult = PlayerRegistered | PlayerQueued


class RegisterPlayer:
    """Use-case регистрации нового игрока через ЛС с DAU-гейтом."""

    __slots__ = (
        "_audit",
        "_check_threshold",
        "_clock",
        "_dau_counter",
        "_dau_limit",
        "_players",
        "_signup_queue",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        signup_queue: ISignupQueueRepository,
        dau_counter: IDauCounter,
        dau_limit: IDauLimit,
        audit: IAuditLogger,
        clock: IClock,
        check_threshold: CheckDauThreshold,
    ) -> None:
        self._uow = uow
        self._players = players
        self._signup_queue = signup_queue
        self._dau_counter = dau_counter
        self._dau_limit = dau_limit
        self._audit = audit
        self._clock = clock
        self._check_threshold = check_threshold

    async def execute(self, input_dto: RegisterPlayerInput) -> RegisterPlayerResult:
        """Зарегистрировать игрока **или** поставить его в очередь.

        Бросает `PlayerAlreadyRegisteredError`, если игрок уже в `users`,
        или `AlreadyQueuedError`, если он уже в `signup_queue`.
        """
        username = Username(value=input_dto.username) if input_dto.username is not None else None
        async with self._uow:
            now = self._clock.now()
            current_dau = await self._dau_counter.current()
            max_dau = await self._dau_limit.get()
            if current_dau >= max_dau:
                queued = await self._enqueue(
                    tg_id=input_dto.tg_id,
                    username=input_dto.username,
                    locale=input_dto.locale,
                    now=now,
                )
                return PlayerQueued(entry=queued)
            player = Player.new(tg_id=input_dto.tg_id, username=username, now=now)
            saved = await self._players.add(player)
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.PLAYER_REGISTER,
                    actor_id=saved.tg_id,
                    target_kind="player",
                    target_id=str(saved.tg_id),
                    before=None,
                    after={
                        "tg_id": saved.tg_id,
                        "length_cm": saved.length.cm,
                        "thickness_level": saved.thickness.level,
                        "username": (saved.username.value if saved.username is not None else None),
                    },
                    reason="register_player",
                    idempotency_key=f"register_player:{saved.tg_id}",
                    occurred_at=now,
                )
            )
        await self._dau_counter.record_active(tg_user_id=saved.tg_id)
        await self._check_threshold.execute()
        return PlayerRegistered(player=saved)

    async def _enqueue(
        self,
        *,
        tg_id: int,
        username: str | None,
        locale: str | None,
        now: datetime,
    ) -> SignupQueueEntry:
        existing = await self._signup_queue.get_by_tg_id(tg_id)
        if existing is not None:
            raise AlreadyQueuedError(tg_id=tg_id)
        candidate = SignupQueueEntry(
            id=None,
            tg_id=tg_id,
            username=username,
            locale=locale,
            position=0,  # перепишется после INSERT-а
            enqueued_at=now,
        )
        queued = await self._signup_queue.enqueue(entry=candidate)
        await self._audit.record(
            AuditEntry(
                action=AuditAction.PLAYER_QUEUED,
                actor_id=tg_id,
                target_kind="player",
                target_id=str(tg_id),
                before=None,
                after={
                    "tg_id": tg_id,
                    "username": username,
                    "locale": locale,
                    "position": queued.position,
                },
                reason="dau_gate_full",
                idempotency_key=f"queue_player:{tg_id}",
                occurred_at=now,
            )
        )
        return queued
