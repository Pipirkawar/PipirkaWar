"""Use-case `RegisterPlayer` (Спринт 1.1.3).

Регистрирует нового игрока с **стартовыми параметрами** ГДД §1.1:
длина = 2 см, толщина = 1, **титул = None**, **имя = None**.
Это закрытое в ГДД v8 решение: имя/титул выдаются позже геймплеем
(имя — выбивается дропом из леса в Спринте 1.3.5; первый титул —
после первого возвращения из леса в Спринте 1.3.8).

Acceptance criteria из `development_plan.md` Спринт 1.1.3:
> попытка регистрации из группы — отказ с подсказкой «напишите в ЛС»;
> начальные значения соответствуют ГДД §1.1.

**Контроль chat_kind = private** живёт **в bot-handler-е**, а не здесь:
use-case не должен знать про Telegram-чаты, только про доменные данные.
Handler делает раннюю фильтрацию и отдаёт пользователю helper-сообщение,
не доходя до БД.

Audit-запись пишется атомарно с INSERT-ом в `users` (правило ГДД §0):
`PLAYER_REGISTER`, `actor_id = tg_id` (самовыданное действие),
`target_kind = "player"`, `target_id = tg_id`.

Идемпотентность: при дубле `tg_id` репозиторий бросит
`PlayerAlreadyRegisteredError` (UNIQUE-violation). Use-case не глотает
эту ошибку — handler покажет «вы уже зарегистрированы».
"""

from __future__ import annotations

from pipirik_wars.application.dto.inputs import RegisterPlayerInput
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


class RegisterPlayer:
    """Use-case регистрации нового игрока через ЛС."""

    __slots__ = ("_audit", "_clock", "_players", "_uow")

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: RegisterPlayerInput) -> Player:
        """Зарегистрировать игрока и вернуть «канонический» инстанс с `id`.

        Бросает `PlayerAlreadyRegisteredError`, если `tg_id` уже занят.
        """
        username = Username(value=input_dto.username) if input_dto.username is not None else None
        async with self._uow:
            now = self._clock.now()
            player = Player.new(
                tg_id=input_dto.tg_id,
                username=username,
                now=now,
            )
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
            return saved
