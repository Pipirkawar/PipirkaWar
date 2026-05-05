"""Use-case `FinishForestRun` (Спринты 1.3.C, 1.6.F).

Срабатывает по APScheduler-job-у, запланированному `StartForestRun`-ом
на `ends_at`. Применяет уже сохранённый исход:

1. Находит `forest_runs` по `run_id`. Нет — `ForestRunNotFoundError`.
2. Если запись уже `FINISHED` — идемпотентный no-op (job мог стрельнуть
   повторно из-за рестарта воркера или ручного `cancel`/`reschedule`).
3. Загружает `Player` по `forest_runs.player_id`.
4. Применяет титул/имя (mutations без длины):
   - Если `title is None` → выдать `Title.NEWBIE` (ПД §1.3.8 / ГДД §8.2:
     «при первом успешном возвращении из леса»).
   - Если `run.drop is NameDrop` и `name is None` → выдать имя.
     Иначе — предложение остаётся на 1.3.D-handler-е.
   - `ItemDrop` — ручное «надеть/выбросить» в 1.3.6/1.3.D.
5. Прибавляет длину через `ILengthGranter` (Спринт 1.6.F):
   `length_granter.grant(source=FOREST, delta=run.length_delta_cm,
   reason="forest_run_finished", idempotency_key="add_length:forest_run:{id}")`.
   `AddLength` в ambient-UoW режиме проверяет anti-cheat soft-ban,
   клампит по cap-ам, пишет audit `LENGTH_GRANT`, взводит trip-wire.
6. Помечает `forest_runs.status = FINISHED, finished_at = now`.
7. Снимает `activity_lock` `(player, FOREST)` (NO-OP, если истёк).
8. Пишет audit опциональные `TITLE_GRANT` / `NAME_GRANT`
   («бизнес-события» леса). `LENGTH_GRANT` уже пишется из `AddLength`.

Транзакция: всё — внутри одного `IUnitOfWork` (`async with self._uow:`),
`AddLength.grant(...)` вызывается в ambient-режиме внутри этого контекста.
Любая ошибка откатывает все mutations (в т. ч. soft-ban-кик из trip-wire-а).
"""

from __future__ import annotations

from dataclasses import dataclass

from pipirik_wars.application.dto.inputs import FinishForestRunInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.forest import (
    ForestRun,
    ForestRunNotFoundError,
    ForestRunStatus,
    IForestRunRepository,
    ItemDrop,
    NameDrop,
    NoDrop,
)
from pipirik_wars.domain.player import (
    IPlayerRepository,
    Player,
    PlayerName,
    Title,
)
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IUnitOfWork,
)
from pipirik_wars.domain.shared.ports.audit import AuditSource


@dataclass(frozen=True, slots=True)
class ForestRunFinished:
    """Результат финиша. Используется bot-handler-ом (Спринт 1.3.D)
    для формирования сообщения «вернулся из леса» (ГДД §8.2).

    Поля:
    - `run` — финальная запись `forest_runs` (`status=FINISHED`).
    - `player_before` / `player_after` — снимки игрока до/после применения
      исхода. Handler смотрит на `player_before.length` vs
      `player_after.length`, на `player_after.title`, и т. д.
    - `granted_title` — `True`, если только что выдан `NEWBIE`.
    - `granted_name` — `True`, если только что записано `name` (auto-apply
      на новичке без имени).
    - `was_already_finished` — `True`, если повторный вызов на уже
      финишированном забеге (handler не отправляет сообщение второй раз).
    """

    run: ForestRun
    player_before: Player
    player_after: Player
    granted_title: bool
    granted_name: bool
    was_already_finished: bool


class FinishForestRun:
    """Use-case «применить результат похода и снять блок»."""

    __slots__ = (
        "_audit",
        "_clock",
        "_length_granter",
        "_locks",
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
        locks: ActivityLockService,
        length_granter: ILengthGranter,
        audit: IAuditLogger,
        clock: IClock,
    ) -> None:
        self._uow = uow
        self._players = players
        self._runs = runs
        self._locks = locks
        self._length_granter = length_granter
        self._audit = audit
        self._clock = clock

    async def execute(self, input_dto: FinishForestRunInput) -> ForestRunFinished:
        """Финишировать поход. Бросает `ForestRunNotFoundError`, если
        записи нет; `PlayerNotFoundError` — если ссылка на игрока «висит».
        """
        async with self._uow:
            run = await self._runs.get_by_id(run_id=input_dto.run_id)
            if run is None:
                raise ForestRunNotFoundError(run_id=input_dto.run_id)

            player = await self._players.get_by_id(player_id=run.player_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=run.player_id)

            if run.status is ForestRunStatus.FINISHED:
                return ForestRunFinished(
                    run=run,
                    player_before=player,
                    player_after=player,
                    granted_title=False,
                    granted_name=False,
                    was_already_finished=True,
                )

            now = self._clock.now()
            player_before = player

            # 1. Титул NEWBIE и имя — бизнес-мутации леса, не связанные с длиной.
            granted_title = player.title is None
            updated = player
            if granted_title:
                updated = updated.with_title(Title.NEWBIE, now=now)

            granted_name = isinstance(run.drop, NameDrop) and updated.name is None
            if granted_name:
                assert isinstance(run.drop, NameDrop)
                updated = updated.with_name(
                    PlayerName(value=run.drop.name.value),
                    now=now,
                )

            if granted_title or granted_name:
                await self._players.save(updated)

            # 2. Прибавка длины — через единый ILengthGranter (Спринт 1.6.F).
            # AddLength сам запишет audit `LENGTH_GRANT` и взведёт trip-wire
            # при превышении cap-ов.
            assert player.id is not None
            await self._length_granter.grant(
                player_id=player.id,
                delta_cm=run.length_delta_cm,
                source=AuditSource.FOREST,
                reason="forest_run_finished",
                idempotency_key=f"add_length:forest_run:{run.id}",
            )

            # 3. Финальный снимок игрока (с учётом title/name и прибавки).
            saved_player = await self._players.get_by_id(player_id=player.id) or updated
            finished_run = await self._runs.save(run.mark_finished(finished_at=now))

            await self._locks.release(actor_kind="player", actor_id=run.player_id)

            if granted_title:
                await self._audit.record(
                    AuditEntry(
                        action=AuditAction.TITLE_GRANT,
                        actor_id=player_before.tg_id,
                        target_kind="forest_run",
                        target_id=str(finished_run.id),
                        before={"title": None},
                        after={"title": Title.NEWBIE.value},
                        reason="first_forest_title",
                        idempotency_key=f"forest_run_finished:title:{finished_run.id}",
                        occurred_at=now,
                    )
                )
            if granted_name:
                assert isinstance(run.drop, NameDrop)
                await self._audit.record(
                    AuditEntry(
                        action=AuditAction.NAME_GRANT,
                        actor_id=player_before.tg_id,
                        target_kind="forest_run",
                        target_id=str(finished_run.id),
                        before={"name": None},
                        after={"name": run.drop.name.value},
                        reason="forest_name_drop_auto_apply",
                        idempotency_key=f"forest_run_finished:name:{finished_run.id}",
                        occurred_at=now,
                    )
                )
        return ForestRunFinished(
            run=finished_run,
            player_before=player_before,
            player_after=saved_player,
            granted_title=granted_title,
            granted_name=granted_name,
            was_already_finished=False,
        )


def drop_kind_label(run: ForestRun) -> str:
    """Сериализованное имя ADT-конструктора для bot/handler-а."""
    if isinstance(run.drop, NoDrop):
        return "none"
    if isinstance(run.drop, NameDrop):
        return "name"
    if isinstance(run.drop, ItemDrop):
        return "item"
    raise AssertionError(f"unknown drop variant: {run.drop!r}")
