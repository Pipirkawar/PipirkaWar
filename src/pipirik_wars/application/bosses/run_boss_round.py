"""Use-case `RunBossRound` (Спринт 3.3-C, ГДД §10.4).

Срабатывает по APScheduler-job-у `boss_round_tick` (поставленному
`CloseBossLobby` в момент `LOBBY → IN_BATTLE` в 3.3-D, либо самим
`RunBossRound`-use-case-ом для последующих раундов). Контракт:

1. Загружает `boss_fight` (`IBossFightRepository.get_by_id`).
   Не найден → :class:`BossFightNotFoundError`.
2. Идемпотентность по статусу:
   - `FINISHED` / `CANCELLED` → no-op (`was_already_finished=True`),
     без аудита и без шедула;
   - не-`IN_BATTLE` (например, `LOBBY`, что — bug шедулера) →
     :class:`InvalidBossFightStateError`.
3. Загружает живых рейдеров (`IBossParticipantRepository.list_by_boss_fight`)
   и фильтрует саммонера — он остаётся в выборке как обычный рейдер
   (саммонер всегда первый рейдер, ГДД §10.3).
4. Если живых рейдеров **нет** (corner-case: предыдущий раунд выкосил
   всех, но `mark_finished` не успел стрельнуть) — переводим бой в
   `FINISHED` без вызова resolve-сервиса. Раздачу штрафных длин
   рейдерам (если у них что-то осталось) и refund босса делает C.3
   `FinishBossFight`.
5. Иначе — конструируем :class:`IRandom` через `random_factory(seed)`,
   где `seed = boss_fight.random_seed × 1_000_003 + current_round`.
   Это даёт уникальный seed per (boss_fight, round) — ровно то, что
   нужно для post-mortem-воспроизведения и unit-тестов.
6. Резолвим раунд через :func:`resolve_boss_round` (Спринт 3.3-C / C.1).
7. Применяем `BossRoundResult` в одной транзакции (`IUnitOfWork`):
   - `boss_fight.with_boss_length(...)` — обновление HP босса
     (`max(0, current - boss_damage_taken_cm)` уже учтён доменной
     entity-методом `with_boss_length`, который кидает на отриц.);
   - `IBossParticipantRepository.remove(...)` для каждого выбывшего;
   - `ActivityLockService.release(...)` для каждого выбывшего —
     чтобы выбывший игрок мог сразу войти в `/forest` или `/caravan`;
   - `boss_fight.with_round_advanced()` — инкремент счётчика раунда
     **до** записи аудит-эвента (round_number в idempotency-key —
     это новый, post-increment-`current_round`).
8. Решает, продолжается ли бой:
   - `current_boss_length_cm < bosses.victory_threshold_cm` — рейдеры
     победили → `mark_finished`;
   - все рейдеры выбыли (`alive_raiders` после удаления пуст) — босс
     победил → `mark_finished`;
   - иначе — бой продолжается, шедулим следующий `boss_round_tick`
     на `now + bosses.round_max_seconds`.
9. Записывает audit `BOSS_FIGHT_ROUND_RESOLVED` с idempotency-key
   `boss_fight_round_resolved:{boss_fight_id}:{round_number}`.
10. Best-effort cleanup при финиш-в-этом-раунде: cancel pending
    `boss_round_tick`-job (на случай, если он был перешедулен; обычно
    это no-op, т. к. данный callback и есть тот самый job). C.3
    `FinishBossFight` отдельно отшедулит финиш-callback из этого же
    use-case-а — пока что в C.2 финиш только status-transition + audit.

В C.2 саммонер-mode-стаб: всегда AFK (`is_summoner_online=False`),
все ходы за рейдеров и босса генерирует `IRandom`. UI выбора блоков
и атак саммонером — Спринт 3.3-D.

Транзакционность: всё внутри одного `IUnitOfWork`. Любая ошибка
откатывает все mutations + аудит — job-воркер ретраит позже.

Идемпотентность: повторный вызов на `FINISHED`/`CANCELLED` — no-op
(см. шаг 2). Audit-запись использует
`idempotency_key=boss_fight_round_resolved:{id}:{round}` — БД-инвариант
`UNIQUE(idempotency_key)` в `audit_log` гарантирует от дублей при
ретрае job-а.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from pipirik_wars.application.dto.inputs import RunBossRoundInput
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.balance.config import BossesConfig
from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightNotFoundError,
    BossParticipant,
    BossRoundResult,
    IBossFightRepository,
    IBossParticipantRepository,
    InvalidBossFightStateError,
    resolve_boss_round,
)
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    IAuditLogger,
    IClock,
    IDelayedJobScheduler,
    IRandom,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class BossRoundResolved:
    """Результат :class:`RunBossRound`.

    Используется bot-handler-ом (Спринт 3.3-D) для рассылки итоговых
    карточек раунда участникам.

    Поля:
    - `boss_fight` — финальное состояние после раунда (`current_round`
      инкрементирован, `current_boss_length_cm` обновлён, при финише
      `status=FINISHED`).
    - `result` — `None`, если `was_already_finished=True` или живых
      рейдеров не было на входе. Иначе — полный
      :class:`BossRoundResult` с per-raider-исходами.
    - `is_finished` — `True`, если этот раунд завершил бой (победа
      рейдеров: `current_boss_length_cm < victory_threshold_cm`;
      или поражение: все рейдеры выбыли).
    - `was_already_finished` — `True` при идемпотентном no-op-е на
      уже терминальном бою (повторный вызов callback-а после
      рестарта воркера).
    """

    boss_fight: BossFight
    result: BossRoundResult | None
    is_finished: bool
    was_already_finished: bool


class RunBossRound:
    """Use-case «провести один раунд боя с боссом» (ГДД §10.4)."""

    __slots__ = (
        "_audit",
        "_balance",
        "_boss_fights",
        "_boss_participants",
        "_clock",
        "_locks",
        "_random_factory",
        "_scheduler",
        "_uow",
    )

    def __init__(
        self,
        *,
        uow: IUnitOfWork,
        boss_fights: IBossFightRepository,
        boss_participants: IBossParticipantRepository,
        locks: ActivityLockService,
        audit: IAuditLogger,
        clock: IClock,
        scheduler: IDelayedJobScheduler,
        balance: BossesConfig,
        random_factory: Callable[[int], IRandom],
    ) -> None:
        self._uow = uow
        self._boss_fights = boss_fights
        self._boss_participants = boss_participants
        self._locks = locks
        self._audit = audit
        self._clock = clock
        self._scheduler = scheduler
        self._balance = balance
        self._random_factory = random_factory

    async def execute(self, input_dto: RunBossRoundInput) -> BossRoundResolved:
        """Резолв одного раунда боя. См. docstring модуля для контракта."""
        async with self._uow:
            boss_fight = await self._boss_fights.get_by_id(
                boss_fight_id=input_dto.boss_fight_id,
            )
            if boss_fight is None:
                raise BossFightNotFoundError(boss_fight_id=input_dto.boss_fight_id)
            assert boss_fight.id is not None
            boss_fight_id: int = boss_fight.id

            if boss_fight.is_terminal:
                # Идемпотентный no-op: бой уже завершён или отменён.
                # Возвращаем текущее состояние, ничего не пишем.
                return BossRoundResolved(
                    boss_fight=boss_fight,
                    result=None,
                    is_finished=True,
                    was_already_finished=True,
                )

            if not boss_fight.is_in_battle:
                # LOBBY → инвариант нарушен: round-tick-job не должен
                # был сработать без LOBBY → IN_BATTLE-перехода.
                raise InvalidBossFightStateError(
                    boss_fight_id=boss_fight_id,
                    expected="IN_BATTLE",
                    actual=boss_fight.status.value,
                )

            now = self._clock.now()

            alive_raiders = await self._boss_participants.list_by_boss_fight(
                boss_fight_id=boss_fight_id,
            )

            # Corner-case: предыдущий раунд выкосил всех рейдеров, но
            # `mark_finished` не успел стрельнуть (например, баг или
            # хирургическое вмешательство админа). Переводим бой в
            # FINISHED без вызова resolve-сервиса.
            if not alive_raiders:
                finished = await self._finish_fight(
                    boss_fight=boss_fight,
                    now=now,
                    boss_damage_taken_cm=0,
                    eliminated_player_ids=(),
                )
                return BossRoundResolved(
                    boss_fight=finished,
                    result=None,
                    is_finished=True,
                    was_already_finished=False,
                )

            # 1. Резолв раунда (детерминистично от seed-а раунда).
            round_seed = boss_fight.random_seed * 1_000_003 + boss_fight.current_round
            random_source = self._random_factory(round_seed)
            result = resolve_boss_round(
                boss_fight=boss_fight,
                alive_raiders=alive_raiders,
                balance=self._balance,
                random=random_source,
            )

            # 2. Применяем урон боссу (clamp 0 снизу).
            new_boss_length_cm = max(
                0,
                boss_fight.current_boss_length_cm - result.boss_damage_taken_cm,
            )
            transitioned = boss_fight.with_boss_length(length_cm=new_boss_length_cm)

            # 3. Удаляем выбывших рейдеров + снимаем activity-locks.
            for player_id in result.eliminated_player_ids:
                await self._boss_participants.remove(
                    boss_fight_id=boss_fight_id,
                    player_id=player_id,
                )
                await self._locks.release(
                    actor_kind="player",
                    actor_id=player_id,
                )

            # 4. Инкремент счётчика раунда. Делается до сохранения,
            # чтобы и `current_round` (новый), и `current_boss_length_cm`
            # ушли в одну `save(...)`.
            transitioned = transitioned.with_round_advanced()
            round_number = transitioned.current_round

            # 5. Решаем, продолжается ли бой.
            raiders_won = transitioned.current_boss_length_cm < self._balance.victory_threshold_cm
            num_alive_after = len(alive_raiders) - len(result.eliminated_player_ids)
            boss_won = num_alive_after <= 0
            is_finished = raiders_won or boss_won

            if is_finished:
                # Финиш этим раундом: status-transition + cleanup tick-job.
                # Полное распределение наград — C.3 `FinishBossFight`.
                transitioned = transitioned.mark_finished(finished_at=now)

            saved = await self._boss_fights.save(transitioned)

            # 6. Audit `BOSS_FIGHT_ROUND_RESOLVED` (per-round idempotency).
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.BOSS_FIGHT_ROUND_RESOLVED,
                    actor_id=None,
                    target_kind="boss_fight",
                    target_id=str(boss_fight_id),
                    before={
                        "current_round": boss_fight.current_round,
                        "current_boss_length_cm": boss_fight.current_boss_length_cm,
                        "alive_raiders": len(alive_raiders),
                    },
                    after={
                        "current_round": saved.current_round,
                        "current_boss_length_cm": saved.current_boss_length_cm,
                        "alive_raiders": num_alive_after,
                        "boss_damage_taken_cm": result.boss_damage_taken_cm,
                        "eliminated_player_ids": list(result.eliminated_player_ids),
                        "is_finished": is_finished,
                        "raiders_won": raiders_won if is_finished else None,
                    },
                    reason="boss_fight_round_resolved",
                    idempotency_key=(f"boss_fight_round_resolved:{boss_fight_id}:{round_number}"),
                    occurred_at=now,
                )
            )

            # 7. Шедул следующего тика / cleanup-а.
            if is_finished:
                # Best-effort cleanup pending-job-а (обычно это и есть
                # сам callback, но защищаемся от перешедула).
                await self._scheduler.cancel_boss_round_tick(boss_fight_id=boss_fight_id)
                # Safety-net fight-finish-job снимет C.3 в момент
                # FinishBossFight; здесь мы его не трогаем, чтобы
                # FinishBossFight-job сам себе перевёл боя в FINISHED
                # (если его поставили на меньший таймаут, чем рейд
                # длился — он стрельнёт, увидит is_terminal и сделает
                # no-op). В 3.3-D добавится ещё немедленный шедул
                # FinishBossFight на `now`, чтобы handler-ы получили
                # карточки наград; в C.2 это пока TODO.
            else:
                next_tick_at = now + timedelta(
                    seconds=self._balance.round_max_seconds,
                )
                await self._scheduler.schedule_boss_round_tick(
                    boss_fight_id=boss_fight_id,
                    run_at=next_tick_at,
                )

        return BossRoundResolved(
            boss_fight=saved,
            result=result,
            is_finished=is_finished,
            was_already_finished=False,
        )

    async def _finish_fight(
        self,
        *,
        boss_fight: BossFight,
        now: datetime,
        boss_damage_taken_cm: int,
        eliminated_player_ids: tuple[int, ...],
    ) -> BossFight:
        """Закрыть бой в corner-case-е (живых рейдеров нет на входе).

        Без resolve-сервиса: только status-transition в FINISHED, audit
        и cleanup pending-job-а. Используется когда `list_by_boss_fight`
        вернул пустой набор — рейдеры выкошены до этого тика, но
        `mark_finished` не сработал. Распределение длин и scroll-drops
        делает C.3 `FinishBossFight`.
        """
        assert boss_fight.id is not None
        boss_fight_id: int = boss_fight.id
        transitioned = boss_fight.with_round_advanced()
        round_number = transitioned.current_round
        transitioned = transitioned.mark_finished(finished_at=now)
        saved = await self._boss_fights.save(transitioned)

        await self._audit.record(
            AuditEntry(
                action=AuditAction.BOSS_FIGHT_ROUND_RESOLVED,
                actor_id=None,
                target_kind="boss_fight",
                target_id=str(boss_fight_id),
                before={
                    "current_round": boss_fight.current_round,
                    "current_boss_length_cm": boss_fight.current_boss_length_cm,
                    "alive_raiders": 0,
                },
                after={
                    "current_round": saved.current_round,
                    "current_boss_length_cm": saved.current_boss_length_cm,
                    "alive_raiders": 0,
                    "boss_damage_taken_cm": boss_damage_taken_cm,
                    "eliminated_player_ids": list(eliminated_player_ids),
                    "is_finished": True,
                    "raiders_won": False,
                },
                reason="boss_fight_round_resolved",
                idempotency_key=(f"boss_fight_round_resolved:{boss_fight_id}:{round_number}"),
                occurred_at=now,
            )
        )
        await self._scheduler.cancel_boss_round_tick(boss_fight_id=boss_fight_id)
        return saved


# Re-exported for convenience in unit tests + bot-handler-ов:
__all__ = [
    "BossParticipant",
    "BossRoundResolved",
    "RunBossRound",
]
