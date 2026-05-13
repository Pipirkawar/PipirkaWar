"""Use-case `FinishBossFight` (Спринт 3.3-C, ГДД §10.5–§10.6).

Срабатывает либо по APScheduler-job-у `boss_fight_finish`
(safety-net, поставленному `CloseBossLobby` в момент `LOBBY → IN_BATTLE`
на `now + battle_minutes`), либо явным шедулом из `RunBossRound`-а
сразу после раунда, который закрыл бой (3.3-D). Контракт:

1. Загружает `boss_fight` (`IBossFightRepository.get_by_id`).
   Не найден → :class:`BossFightNotFoundError`.
2. Идемпотентность по статусу: если бой уже `FINISHED`/`CANCELLED` —
   no-op (`was_already_finished=True`), без аудита и без grant-ов.
   Защищает от повторного срабатывания callback-а после рестарта
   воркера или от race-а «`RunBossRound` уже финишнул в этом раунде +
   safety-net-job стрельнул чуть позже».
3. `LOBBY` (job не должен был сработать без `LOBBY → IN_BATTLE`-перехода,
   это инвариант `CloseBossLobby`) → :class:`InvalidBossFightStateError`.
4. Загружает живых рейдеров (`IBossParticipantRepository.list_by_boss_fight`).
   Если `current_boss_length_cm < bosses.victory_threshold_cm` —
   рейдеры победили (`raiders_won=True`); победа сохраняется даже
   при пустом списке рейдеров — это редкий corner-case
   «оба умерли в один раунд». Иначе — рейдеры проиграли.
5. **Победа рейдеров** (ГДД §10.5):
   * Каждый живой рейдер получает length-grant
     `+initial_boss_length_cm // N` см (N = число живых) через
     `ILengthGranter.grant(source=RAID_REWARD)` с idempotency-key
     `add_length:boss_fight_reward:{boss_fight_id}:{player_id}`.
     Деление целочисленное (остаток от деления съедается — это
     согласовано c cyan91, не критично для баланса; раунд `floor(/N)`
     даёт суммарно `initial_boss_length_cm − (initial_boss_length_cm % N)`
     см, остаток в `[0, N)` теряется).
   * Per-player ролл скроллов (regular + blessed, независимо) через
     `IRandom.uniform(0.0, 1.0) < cfg.regular|blessed`; на каждый
     успех пишется audit `SCROLL_DROP` с idempotency-key
     `boss_scroll_drop:{boss_fight_id}:{player_id}:{scroll_kind}`.
     Скролл сейчас (3.3-C) **не** записывается в инвентарь —
     только в audit-лог; реальная инвентарная инфраструктура —
     Спринт 3.4 «Заточка предметов».
   * Босс получает refund «не остаться ниже `victory_threshold_cm`»:
     его `Player.length` уменьшается на `initial_boss_length_cm`, но
     результат клампится снизу до `victory_threshold_cm` (т.е. боссу
     гарантирован минимум `victory_threshold_cm` после рейда). Это
     прямой `Player.with_length(...)` + audit `LENGTH_REVOKE` —
     refund к самому себе через own-length-recompute, не подпадающий
     под anti-cheat hardcap.
6. **Поражение рейдеров** (ГДД §10.5):
   * Каждый живой рейдер теряет «реально выеденную в бою» часть
     длины: `Δ = max(0, length_at_join_cm - current_length_cm)`
     (Спринт 3.3-D, согласовано с cyan91). У рейдеров без урона
     `Δ=0` — «выжил, но потерял время, не потерял по длине». Списание
     прямым `Player.with_length(current - Δ)` + audit
     `LENGTH_REVOKE(source=RAID_REWARD, delta_cm=-Δ)` с
     idempotency-key `boss_fight_raider_loss:{id}:{player_id}`.
     Это refund-к-самому-себе из «банка пользователя» (не grant) —
     anti-cheat hardcap не применяется (см. также `_revoke_boss_length`).
   * Босс получает length-grant `+sum(length_at_join_cm)` всех живых
     рейдеров (реалистичный «он съел всех»; снапшот длин на момент
     joined — стабилен; асимметрия с raider-loss-Δ намеренна — система
     не претендует на снятие длины, которой у рейдера уже нет, но
     боссу её «учитывает» из мирового банка) через
     `ILengthGranter.grant(source=RAID_REWARD)` с idempotency-key
     `add_length:boss_loss_grant:{boss_fight_id}`.
7. Снимает `activity_lock(player, *)` для всех живых рейдеров +
   босса (NO-OP, если уже снят/истёк).
8. `boss_fight.mark_finished(finished_at=now)`, сохраняет.
9. Cancel-ит pending-tick-job + safety-net-finish-job (best-effort
   cleanup; обычно один из них и есть текущий callback).
10. Audit `BOSS_FIGHT_FINISHED` (idempotency-key
    `boss_fight_finished:{boss_fight_id}`) + `BOSS_REWARDS_GRANTED`
    (агрегаты — `raiders_won`, `total_granted_cm`, `total_revoked_cm`,
    `scroll_drops_regular`, `scroll_drops_blessed`; idempotency-key
    `boss_rewards_granted:{boss_fight_id}`).

Транзакционность: всё внутри одного `IUnitOfWork`. Любая ошибка
откатывает все mutations + аудит — job-воркер ретраит позже.

Идемпотентность: на job-уровне — повторный вызов на `FINISHED` —
no-op (см. шаг 2). Внутри транзакции — все sub-вызовы
(`length_granter.grant`, `audit.record`, …) используют idempotency-keys,
так что дубль-апплая не будет даже если повторный вызов попадёт в
ту же секунду.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pipirik_wars.application.dto.inputs import FinishBossFightInput
from pipirik_wars.application.observability import IBusinessMetrics, NullBusinessMetrics
from pipirik_wars.application.security import ActivityLockService
from pipirik_wars.domain.balance.config import BossesConfig
from pipirik_wars.domain.bosses import (
    BossFight,
    BossFightNotFoundError,
    BossParticipant,
    IBossFightRepository,
    IBossParticipantRepository,
    InvalidBossFightStateError,
)
from pipirik_wars.domain.player import IPlayerRepository, Length
from pipirik_wars.domain.player.errors import PlayerNotFoundError
from pipirik_wars.domain.progression.length_granter import ILengthGranter
from pipirik_wars.domain.shared.ports import (
    AuditAction,
    AuditEntry,
    AuditSource,
    IAuditLogger,
    IClock,
    IDelayedJobScheduler,
    IRandom,
    IUnitOfWork,
)


@dataclass(frozen=True, slots=True)
class BossScrollDrop:
    """Per-player результат ролла скролла из рейд-боссы.

    Используется внутри `BossFightFinished.scroll_drops` для агрегации
    в audit + (в будущем 3.4) для записи в инвентарь.
    """

    player_id: int
    blessed: bool


@dataclass(frozen=True, slots=True)
class BossFightFinished:
    """Результат :class:`FinishBossFight`.

    Используется bot-handler-ом (Спринт 3.3-D) для рассылки итоговых
    карточек участникам.

    Поля:
    - `boss_fight` — финальное состояние (`status=FINISHED` или текущее,
      если `was_already_finished=True`).
    - `raiders_won` — `None`, если `was_already_finished=True`. Иначе —
      `True` при победе рейдеров, `False` при поражении.
    - `total_granted_cm` — сколько суммарно длины раздано рейдерам
      (победа) либо боссу (поражение).
    - `boss_revoked_cm` — сколько списано с босса (только победа,
      иначе `0`).
    - `raiders_revoked_cm` — сколько суммарно списано с живых рейдеров
      при поражении (= `sum(max(0, length_at_join_cm - current_length_cm))`,
      Спринт 3.3-D). При победе и при no-op-е — `0`.
    - `scroll_drops` — список выданных per-player-скроллов (только при
      победе и только для попавших в ролл; пуст в остальных случаях).
    - `was_already_finished` — `True` при идемпотентном no-op-е.
    """

    boss_fight: BossFight
    raiders_won: bool | None
    total_granted_cm: int
    boss_revoked_cm: int
    raiders_revoked_cm: int
    scroll_drops: tuple[BossScrollDrop, ...]
    was_already_finished: bool


class FinishBossFight:
    """Use-case «применить исход рейд-боя и распределить награды» (ГДД §10.5–§10.6)."""

    __slots__ = (
        "_audit",
        "_balance",
        "_boss_fights",
        "_boss_participants",
        "_business_metrics",
        "_clock",
        "_length_granter",
        "_locks",
        "_players",
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
        players: IPlayerRepository,
        length_granter: ILengthGranter,
        locks: ActivityLockService,
        audit: IAuditLogger,
        clock: IClock,
        scheduler: IDelayedJobScheduler,
        balance: BossesConfig,
        random_factory: Callable[[int], IRandom],
        business_metrics: IBusinessMetrics | None = None,
    ) -> None:
        self._uow = uow
        self._boss_fights = boss_fights
        self._boss_participants = boss_participants
        self._players = players
        self._length_granter = length_granter
        self._locks = locks
        self._audit = audit
        self._clock = clock
        self._scheduler = scheduler
        self._balance = balance
        self._random_factory = random_factory
        self._business_metrics: IBusinessMetrics = business_metrics or NullBusinessMetrics()

    async def execute(self, input_dto: FinishBossFightInput) -> BossFightFinished:
        """Финиш рейд-боя. См. docstring модуля для контракта."""
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
                return BossFightFinished(
                    boss_fight=boss_fight,
                    raiders_won=None,
                    total_granted_cm=0,
                    boss_revoked_cm=0,
                    raiders_revoked_cm=0,
                    scroll_drops=(),
                    was_already_finished=True,
                )

            if not boss_fight.is_in_battle:
                # LOBBY → инвариант шедулера нарушен.
                raise InvalidBossFightStateError(
                    boss_fight_id=boss_fight_id,
                    expected="IN_BATTLE",
                    actual=boss_fight.status.value,
                )

            now = self._clock.now()

            alive_raiders = await self._boss_participants.list_by_boss_fight(
                boss_fight_id=boss_fight_id,
            )

            raiders_won = boss_fight.current_boss_length_cm < self._balance.victory_threshold_cm

            total_granted_cm = 0
            boss_revoked_cm = 0
            raiders_revoked_cm = 0
            scroll_drops: list[BossScrollDrop] = []

            if raiders_won:
                # 1. Раздача наград живым рейдерам.
                total_granted_cm = await self._grant_raider_rewards(
                    boss_fight=boss_fight,
                    alive_raiders=alive_raiders,
                )

                # 2. Per-player ролл скроллов.
                round_seed = boss_fight.random_seed * 1_000_003 + boss_fight.current_round
                scroll_random = self._random_factory(round_seed)
                scroll_drops = list(
                    self._roll_scroll_drops(
                        alive_raiders=alive_raiders,
                        random=scroll_random,
                    )
                )
                await self._record_scroll_drops(
                    boss_fight_id=boss_fight_id,
                    drops=scroll_drops,
                    now=now,
                )

                # 3. Списание длины с босса (refund-floor: не ниже
                # `victory_threshold_cm`).
                boss_revoked_cm = await self._revoke_boss_length(
                    boss_fight=boss_fight,
                    now=now,
                )
            else:
                # Поражение рейдеров: босс получает grant +sum(length_at_join_cm).
                total_granted_cm = await self._grant_boss_loss_reward(
                    boss_fight=boss_fight,
                    alive_raiders=alive_raiders,
                )
                # Каждый живой рейдер «отдаёт» только реально потерянную в
                # бою часть длины (Δ = max(0, length_at_join - current));
                # рейдеры без урона теряют 0 (см. docstring модуля §6).
                raiders_revoked_cm = await self._revoke_raider_losses(
                    boss_fight=boss_fight,
                    alive_raiders=alive_raiders,
                    now=now,
                )

            # 4. Снимаем activity-lock-и всех живых рейдеров + босса.
            for raider in alive_raiders:
                await self._locks.release(
                    actor_kind="player",
                    actor_id=raider.player_id,
                )
            await self._locks.release(
                actor_kind="player",
                actor_id=boss_fight.boss_player_id,
            )

            # 5. Финальный transition статуса.
            finished_boss_fight = await self._boss_fights.save(
                boss_fight.mark_finished(finished_at=now),
            )

            # 6. Best-effort cleanup pending-job-ов.
            await self._scheduler.cancel_boss_round_tick(boss_fight_id=boss_fight_id)
            await self._scheduler.cancel_boss_fight_finish(boss_fight_id=boss_fight_id)

            # 7. Audit-записи: state-transition + agregates-наград.
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.BOSS_FIGHT_FINISHED,
                    actor_id=None,
                    target_kind="boss_fight",
                    target_id=str(boss_fight_id),
                    before={"status": boss_fight.status.value},
                    after={
                        "status": finished_boss_fight.status.value,
                        "raiders_won": raiders_won,
                        "alive_raiders": len(alive_raiders),
                        "current_boss_length_cm": boss_fight.current_boss_length_cm,
                        "current_round": boss_fight.current_round,
                    },
                    reason="boss_fight_finished",
                    idempotency_key=f"boss_fight_finished:{boss_fight_id}",
                    occurred_at=now,
                )
            )
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.BOSS_REWARDS_GRANTED,
                    actor_id=None,
                    target_kind="boss_fight",
                    target_id=str(boss_fight_id),
                    before=None,
                    after={
                        "raiders_won": raiders_won,
                        "total_granted_cm": total_granted_cm,
                        "boss_revoked_cm": boss_revoked_cm,
                        "raiders_revoked_cm": raiders_revoked_cm,
                        "scroll_drops_regular": sum(1 for d in scroll_drops if not d.blessed),
                        "scroll_drops_blessed": sum(1 for d in scroll_drops if d.blessed),
                        "alive_raiders": len(alive_raiders),
                    },
                    reason="boss_rewards_granted",
                    idempotency_key=f"boss_rewards_granted:{boss_fight_id}",
                    occurred_at=now,
                )
            )

        self._business_metrics.dec_raid_active()
        self._business_metrics.inc_raid_outcome("raiders_win" if raiders_won else "boss_win")
        return BossFightFinished(
            boss_fight=finished_boss_fight,
            raiders_won=raiders_won,
            total_granted_cm=total_granted_cm,
            boss_revoked_cm=boss_revoked_cm,
            raiders_revoked_cm=raiders_revoked_cm,
            scroll_drops=tuple(scroll_drops),
            was_already_finished=False,
        )

    # -------- helpers --------

    async def _grant_raider_rewards(
        self,
        *,
        boss_fight: BossFight,
        alive_raiders: tuple[BossParticipant, ...],
    ) -> int:
        """Раздать живым рейдерам `+initial_boss_length_cm // N` см каждому.

        Возвращает суммарную выданную дельту (= per_raider × N).
        Пустой список рейдеров → 0 (corner-case «оба умерли в один раунд»).
        """
        assert boss_fight.id is not None
        if not alive_raiders:
            return 0
        per_raider_cm = boss_fight.initial_boss_length_cm // len(alive_raiders)
        if per_raider_cm <= 0:
            return 0
        total = 0
        for raider in alive_raiders:
            await self._length_granter.grant(
                player_id=raider.player_id,
                delta_cm=per_raider_cm,
                source=AuditSource.RAID_REWARD,
                reason="boss_fight_reward",
                idempotency_key=(
                    f"add_length:boss_fight_reward:{boss_fight.id}:{raider.player_id}"
                ),
            )
            total += per_raider_cm
        return total

    def _roll_scroll_drops(
        self,
        *,
        alive_raiders: tuple[BossParticipant, ...],
        random: IRandom,
    ) -> list[BossScrollDrop]:
        """Per-player ролл скроллов (regular + blessed, независимо).

        Бросает 2 ролла на каждого рейдера; на каждый успех — отдельный
        :class:`BossScrollDrop` (рейдер может получить и regular, и
        blessed одновременно — это by design, ГДД §10.5).
        """
        cfg = self._balance.scroll_drop
        drops: list[BossScrollDrop] = []
        for raider in alive_raiders:
            if cfg.regular > 0.0 and random.uniform(0.0, 1.0) < cfg.regular:
                drops.append(BossScrollDrop(player_id=raider.player_id, blessed=False))
            if cfg.blessed > 0.0 and random.uniform(0.0, 1.0) < cfg.blessed:
                drops.append(BossScrollDrop(player_id=raider.player_id, blessed=True))
        return drops

    async def _record_scroll_drops(
        self,
        *,
        boss_fight_id: int,
        drops: list[BossScrollDrop],
        now: datetime,
    ) -> None:
        """Записать audit-эвенты `SCROLL_DROP` для каждого выпавшего скролла.

        Скролл в инвентарь не пишется (3.3-C — skeleton); это сделает
        Спринт 3.4 «Заточка предметов».
        """
        for drop in drops:
            scroll_kind = "blessed" if drop.blessed else "regular"
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.SCROLL_DROP,
                    actor_id=None,
                    target_kind="player",
                    target_id=str(drop.player_id),
                    before=None,
                    after={
                        "scroll_kind": scroll_kind,
                        "boss_fight_id": boss_fight_id,
                    },
                    reason="boss_scroll_drop",
                    idempotency_key=(
                        f"boss_scroll_drop:{boss_fight_id}:{drop.player_id}:{scroll_kind}"
                    ),
                    occurred_at=now,
                )
            )

    async def _revoke_boss_length(
        self,
        *,
        boss_fight: BossFight,
        now: datetime,
    ) -> int:
        """Списать длину с босса при победе рейдеров.

        Боссу резется `initial_boss_length_cm` см, но floor —
        `victory_threshold_cm` (refund: «не остаться ниже минимума»).
        Возвращает фактически списанную дельту (>= 0).

        Прямой `Player.with_length(...)` без `ILengthGranter` —
        это refund-к-себе, anti-cheat hardcap не применим (см.
        также `apply_outcome.py` / `apply_mass_outcome.py`).
        """
        assert boss_fight.id is not None
        boss = await self._players.get_by_id(player_id=boss_fight.boss_player_id)
        if boss is None:
            raise PlayerNotFoundError(tg_id=boss_fight.boss_player_id)
        assert boss.id is not None

        floor_cm = self._balance.victory_threshold_cm
        target_cm = max(floor_cm, boss.length.cm - boss_fight.initial_boss_length_cm)
        revoked_cm = boss.length.cm - target_cm
        if revoked_cm <= 0:
            # Босс уже ниже floor-а или потеря не нужна — no-op.
            return 0
        new_length = Length(cm=target_cm)
        after = boss.with_length(new_length, now=now)
        saved = await self._players.save(after)
        await self._audit.record(
            AuditEntry(
                action=AuditAction.LENGTH_REVOKE,
                actor_id=boss.tg_id,
                target_kind="player",
                target_id=str(boss.id),
                before={"length_cm": boss.length.cm},
                after={"length_cm": saved.length.cm},
                reason="boss_fight_loss",
                idempotency_key=(f"boss_fight_loss_revoke:{boss_fight.id}"),
                occurred_at=now,
                source=AuditSource.RAID_REWARD,
                delta_cm=-revoked_cm,
            )
        )
        return revoked_cm

    async def _revoke_raider_losses(
        self,
        *,
        boss_fight: BossFight,
        alive_raiders: tuple[BossParticipant, ...],
        now: datetime,
    ) -> int:
        """При поражении рейдеров — списать у каждого `Δ = max(0, length_at_join - current)` см.

        Это «реально выеденная» в бою часть длины (Спринт 3.3-D, ГДД §10.5).
        У рейдеров без урона `Δ=0` — пропускаем без аудита и без mutate-а
        Player-а. Списание прямым `Player.with_length(current - Δ)` +
        audit `LENGTH_REVOKE(source=RAID_REWARD, delta_cm=-Δ)` — refund-к-самому-себе,
        anti-cheat hardcap не применяется (см. также `_revoke_boss_length`).

        Idempotency-key per-player: `boss_fight_raider_loss:{id}:{player_id}`.

        Возвращает суммарную списанную дельту (>= 0).
        :raises PlayerNotFoundError: если у живого рейдера нет Player-а
            (инвариантно нарушено — рейд-репо ссылается на отсутствующий
            `players.id`; ретрай не поможет).
        """
        assert boss_fight.id is not None
        if not alive_raiders:
            return 0
        total = 0
        for raider in alive_raiders:
            player = await self._players.get_by_id(player_id=raider.player_id)
            if player is None:
                raise PlayerNotFoundError(tg_id=raider.player_id)
            assert player.id is not None
            delta_cm = max(0, raider.length_at_join_cm - player.length.cm)
            if delta_cm == 0:
                continue
            new_length = Length(cm=player.length.cm - delta_cm)
            after = player.with_length(new_length, now=now)
            saved = await self._players.save(after)
            await self._audit.record(
                AuditEntry(
                    action=AuditAction.LENGTH_REVOKE,
                    actor_id=player.tg_id,
                    target_kind="player",
                    target_id=str(player.id),
                    before={"length_cm": player.length.cm},
                    after={"length_cm": saved.length.cm},
                    reason="boss_fight_raider_loss",
                    idempotency_key=(f"boss_fight_raider_loss:{boss_fight.id}:{raider.player_id}"),
                    occurred_at=now,
                    source=AuditSource.RAID_REWARD,
                    delta_cm=-delta_cm,
                )
            )
            total += delta_cm
        return total

    async def _grant_boss_loss_reward(
        self,
        *,
        boss_fight: BossFight,
        alive_raiders: tuple[BossParticipant, ...],
    ) -> int:
        """При поражении рейдеров — выдать боссу `+sum(length_at_join_cm)`.

        Длина — снапшот `length_at_join_cm` каждого живого рейдера на
        момент вступления (стабилен; не зависит от текущей длины,
        чтобы рейдер не мог «уйти из боя» через `/forest` параллельно).
        Через `ILengthGranter.grant(...)` — anti-cheat hardcap
        применяется как обычно.
        """
        assert boss_fight.id is not None
        total = sum(raider.length_at_join_cm for raider in alive_raiders)
        if total <= 0:
            return 0
        await self._length_granter.grant(
            player_id=boss_fight.boss_player_id,
            delta_cm=total,
            source=AuditSource.RAID_REWARD,
            reason="boss_loss_grant",
            idempotency_key=f"add_length:boss_loss_grant:{boss_fight.id}",
        )
        return total


__all__ = [
    "BossFightFinished",
    "BossScrollDrop",
    "FinishBossFight",
]
