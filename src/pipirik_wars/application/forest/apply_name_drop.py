"""Use-case `ApplyForestNameDrop` (Спринт 1.3.D, ГДД §2.5 / §8.2).

Срабатывает по нажатию инлайн-кнопки «Заменить» под сообщением
«вернулся из леса», когда у игрока **уже есть имя** и из леса
выпал `NameDrop` (auto-apply невозможен — `FinishForestRun` оставляет
дроп, поскольку `player.name is not None`).

Ответственность:

1. Найти `forest_runs` по `run_id`. Нет — `ForestRunNotFoundError`.
2. Найти `Player` по `tg_id`. Нет — `PlayerNotFoundError`.
3. Сверить, что `run.player_id == player.id` (защита от чужих кнопок).
   Не совпадает — `ForestRunOwnershipError` (см. ниже).
4. Сверить, что `run.drop is NameDrop`. Иначе — `ForestDropMismatchError`.
5. Если `player.name == run.drop.name` — идемпотентный no-op
   (двойной клик / кнопка осталась после рестарта).
6. Иначе — заменить имя через `Player.with_name(...)`, сохранить,
   записать `NAME_GRANT`-аудит с `reason="forest_name_replacement"`.

Аудит идемпотентен через `idempotency_key=f"forest_name_replace:{run_id}"`
— если кто-то двинет двойной клик быстро (до того как `bot/handlers`
edit-нет клавиатуру), второй вызов `RecordForestDropDecision`-аудита
не пройдёт по уникальности.

Транзакция: всё внутри одного `IUnitOfWork`. Любая ошибка откатывает
все мутации.
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import ApplyForestNameDropInput
from pipirik_wars.domain.forest import (
    ForestRun,
    ForestRunNotFoundError,
    IForestRunRepository,
    NameDrop,
)
from pipirik_wars.domain.forest.errors import (
    ForestDropMismatchError,
    ForestRunOwnershipError,
)
from pipirik_wars.domain.player import (
    IPlayerRepository,
    Player,
    PlayerName,
)
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class ForestNameDropApplied:
    """Результат применения `NameDrop`.

    `was_already_applied=True` означает, что у игрока уже было ровно
    то имя, которое выпало (повторный клик / рестарт). В этом случае
    ни сохранения, ни аудита не происходит.
    """

    player_before: Player
    player_after: Player
    new_name: PlayerName
    was_already_applied: bool


class ApplyForestNameDrop:
    """Use-case «заменить активное имя на выпавшее в лесу»."""

    __slots__ = (
        "_audit",
        "_clock",
        "_players",
        "_runs",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        players: IPlayerRepository,
        runs: IForestRunRepository,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._runs = runs
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: ApplyForestNameDropInput) -> ForestNameDropApplied:
        """Применить выпавшее имя. Бросает `ForestRunNotFoundError`
        / `PlayerNotFoundError` / `ForestRunOwnershipError`
        / `ForestDropMismatchError` при нарушении инвариантов.
        """
        async with self._uow:
            run = await self._runs.get_by_id(run_id=input_dto.run_id)
            if run is None:
                raise ForestRunNotFoundError(run_id=input_dto.run_id)
            player = await self._players.get_by_tg_id(input_dto.tg_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=input_dto.tg_id)
            self._ensure_owner(run=run, player=player)

            drop = run.drop
            if not isinstance(drop, NameDrop):
                raise ForestDropMismatchError(
                    run_id=input_dto.run_id,
                    expected="name",
                    got=run.drop.__class__.__name__,
                )

            new_name = PlayerName(value=drop.name.value)
            if player.name == new_name:
                return ForestNameDropApplied(
                    player_before=player,
                    player_after=player,
                    new_name=new_name,
                    was_already_applied=True,
                )

            now = self._clock.now()
            updated = player.with_name(new_name, now=now)
            saved_player = await self._players.save(updated)

            assert run.id is not None  # repo returns persisted run
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.NAME_GRANT,
                    actor_id=player.tg_id,
                    target_kind="forest_run",
                    target_id=str(run.id),
                    before={"name": player.name.value if player.name is not None else None},
                    after={"name": saved_player.name.value if saved_player.name else None},
                    reason="forest_name_replacement",
                    idempotency_key=f"forest_name_replace:{run.id}",
                    occurred_at=now,
                )
            )
        return ForestNameDropApplied(
            player_before=player,
            player_after=saved_player,
            new_name=new_name,
            was_already_applied=False,
        )

    @staticmethod
    def _ensure_owner(*, run: ForestRun, player: Player) -> None:
        """Защита: чужой `tg_id` не может применить чужой `NameDrop`.

        В нормальной жизни кнопка приходит игроку в его ЛС, и Telegram
        гарантирует `from_user.id` совпадение. Но если пользователь
        форвардит сообщение или копирует callback_data в другой чат —
        это поймает доменная ошибка.
        """
        if player.id is None:
            raise RuntimeError(
                f"Player tg_id={player.tg_id} loaded without id; repository contract violation"
            )
        if run.player_id != player.id:
            raise ForestRunOwnershipError(
                run_id=run.id if run.id is not None else 0,
                run_player_id=run.player_id,
                actor_player_id=player.id,
            )


__all__ = [
    "ApplyForestNameDrop",
    "ForestNameDropApplied",
]
