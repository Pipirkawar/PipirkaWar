"""Use-case `PromoteFromQueue` (Спринт 1.2.5).

Когда появляется свободное место в DAU-ёмкости (админ поднял `MAX_DAU`,
наступил новый день и счётчик обнулился, и т.п.) — забираем первых N
из `signup_queue` и регистрируем их в `users`.

Триггеры:
- Внутри `SetMaxDau` после успешного увеличения лимита (вызов в той
  же aiogram-итерации, без задержки).
- В Спринте 1.2.D — периодический cron-tick (раз в минуту), на случай
  смены дня и снижения DAU.

Уведомление игроков «ваш пипирик готов» — отдельная ответственность
notifier-а (1.2.D); use-case возвращает список повышенных, чтобы
caller мог их оповестить.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.domain.dau import IDauCounter, IDauLimit
from pipirik_wars.domain.player import (
    IPlayerRepository,
    Player,
    PlayerAlreadyRegisteredError,
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
    ISignupQueueRepository,
    SignupQueueEntry,
)


@dataclass(frozen=True, slots=True)
class PromoteFromQueueResult:
    """Что сделал `PromoteFromQueue.execute()`."""

    promoted: tuple[Player, ...]
    skipped_already_registered: tuple[int, ...]
    available_slots: int

    @property
    def promoted_count(self) -> int:
        return len(self.promoted)


class PromoteFromQueue:
    """Перевод первых из очереди в зарегистрированных игроков."""

    __slots__ = (
        "_audit",
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
    ) -> None:
        self._uow = uow
        self._players = players
        self._signup_queue = signup_queue
        self._dau_counter = dau_counter
        self._dau_limit = dau_limit
        self._audit = audit
        self._clock = clock

    async def execute(self) -> PromoteFromQueueResult:
        """Поднять из очереди столько, сколько влезает по `MAX_DAU - DAU`.

        Если очередь пуста или ёмкость нулевая — `promoted` пустой.
        Регистрация и удаление из очереди — в одной транзакции UoW;
        `record_active(...)` зовём вне транзакции (in-memory счётчик).
        """
        async with self._uow:
            current_dau = await self._dau_counter.current()
            max_dau = await self._dau_limit.get()
            slots = max(0, max_dau - current_dau)
            if slots == 0:
                return PromoteFromQueueResult(
                    promoted=(),
                    skipped_already_registered=(),
                    available_slots=0,
                )
            entries = await self._signup_queue.pop_front(limit=slots)
            if not entries:
                return PromoteFromQueueResult(
                    promoted=(),
                    skipped_already_registered=(),
                    available_slots=slots,
                )
            promoted: list[Player] = []
            skipped: list[int] = []
            for entry in entries:
                saved = await self._register_one(entry)
                if saved is None:
                    skipped.append(entry.tg_id)
                else:
                    promoted.append(saved)
        for saved in promoted:
            await self._dau_counter.record_active(tg_user_id=saved.tg_id)
        return PromoteFromQueueResult(
            promoted=tuple(promoted),
            skipped_already_registered=tuple(skipped),
            available_slots=slots,
        )

    async def _register_one(self, entry: SignupQueueEntry) -> Player | None:
        username = Username(value=entry.username) if entry.username is not None else None
        now = self._clock.now()
        player = Player.new(tg_id=entry.tg_id, username=username, now=now)
        try:
            saved = await self._players.add(player)
        except PlayerAlreadyRegisteredError:
            # Игрок уже в `users` (странный кейс — ставился в очередь
            # ещё до регистрации, но успел зарегаться через другой путь).
            # Тихо пропускаем без аудита.
            return None
        await self._audit.record(
            AuditEntry(
                action=AuditAction.PLAYER_PROMOTED,
                actor_id=saved.tg_id,
                target_kind="player",
                target_id=str(saved.tg_id),
                before={
                    "queued_position": entry.position,
                    "queued_at": entry.enqueued_at.isoformat(),
                },
                after={
                    "tg_id": saved.tg_id,
                    "length_cm": saved.length.cm,
                    "thickness_level": saved.thickness.level,
                    "username": (saved.username.value if saved.username is not None else None),
                },
                reason="promote_from_queue",
                idempotency_key=f"promote_player:{saved.tg_id}",
                occurred_at=now,
            )
        )
        return saved
