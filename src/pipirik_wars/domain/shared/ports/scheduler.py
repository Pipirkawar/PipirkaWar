"""Порт отложенных задач (`IDelayedJobScheduler`).

Use-case-ы с таймером (`/forest`, `/mountain`, `/dungeon`, `/caravan`)
ставят job на «вернуть игрока» через несколько минут. Реализация
живёт в `infrastructure/scheduler/` — production использует
`AsyncIOScheduler` от APScheduler (ПД §3 / Спринт 1.3.3); в тестах
работает `FakeDelayedJobScheduler` (in-memory список запланированных
job-ов).

Контракты:
- `schedule(...)` идемпотентен по `job_id` (повторный вызов с тем же
  `job_id` перезаписывает существующий job — это нужно для
  recovery-сценариев на старте бота).
- `cancel(...)` — NO-OP, если job-а нет.
- Сам job не получает контекст (uow / repos / etc.) — это
  ответственность infrastructure-адаптера: он замыкает callable вокруг
  contianer-а и при срабатывании вызывает use-case `FinishForestRun`
  с правильными зависимостями.

Спринт 2.1.F.2: добавлены 4 метода для глобального лобби PvP —
escalation `CHAT_THEN_GLOBAL → GLOBAL_ONLY` через 3 мин и expiration
`GLOBAL_ONLY` после 10 мин в лобби (см. ГДД §7.1, balance
`pvp.duel_1v1.{chat_to_global_promotion_minutes,
global_lobby_ttl_minutes}`).

Спринт 2.1.G: добавлен AFK-таймер раунда —
`schedule_round_afk_resolution(*, duel_id, round_num, run_at)`
ставит job, который через 30..60 сек дёрнет `ResolveAfkRound` для
конкретного раунда (если хотя бы один игрок не отправил `submit_move`).
Job-id-ы — per-(duel_id, round_num), потому что в активной дуэли
ровно один pending раунд за раз, но cancel должен быть точечным
(чтобы не задеть таймер следующего раунда, если он уже запланирован).

Спринт 2.2.F: добавлен AFK-таймер массового PvP —
`schedule_mass_duel_afk_resolution(*, duel_id, run_at)` ставит job,
который через `pvp.mass_duel.move_timer_seconds` дёрнет
`ForceResolveMassDuel(duel_id=...)` (если хотя бы один участник не
отправил `SubmitMassMove`). В отличие от 1×1, масс-бой одно-тиковый —
job всего один на бой, ключ — просто `duel_id`. Cancel вызывается из
`ResolveMassDuel` (когда все успели сами), `CancelMassDuel`
(административная отмена) и из самого `_run_mass_duel_afk_job` (best-
effort cleanup).

Спринт 2.3.F.2: добавлен per-clan cron «Главы клана дня» —
`schedule_daily_head_cron(*, clan_id, run_at)` ставит job, который в
`run_at` (00:00 МСК + per-clan детерминированный offset 0..24h) дёрнет
`RunDailyHeadCron(clan_id=...)`. Идемпотентно по `clan_id`: повторный
вызов перезаписывает job (для recovery / ежесуточного перепланирования).
"""

from __future__ import annotations

import abc
from datetime import datetime


class IDelayedJobScheduler(abc.ABC):
    """Планировщик отложенных задач (минимально нужный набор)."""

    @abc.abstractmethod
    async def schedule_finish_forest_run(
        self,
        *,
        run_id: int,
        run_at: datetime,
    ) -> None:
        """Запланировать `FinishForestRun(run_id=...)` на `run_at` (UTC).

        Идемпотентно по `run_id`: повторный вызов перезаписывает job.
        """

    @abc.abstractmethod
    async def cancel_finish_forest_run(self, *, run_id: int) -> None:
        """Снять запланированный finish-job (NO-OP, если его нет)."""

    # ── Спринт 2.1.F.2: глобальное лобби PvP ──

    @abc.abstractmethod
    async def schedule_chat_to_global_escalation(
        self,
        *,
        duel_id: int,
        run_at: datetime,
    ) -> None:
        """Запланировать `EscalateChatToGlobal(duel_id=...)` на `run_at` (UTC).

        Срабатывает через `pvp.duel_1v1.chat_to_global_promotion_minutes`
        после создания `mode=CHAT_THEN_GLOBAL`-вызова (ГДД §7.1).
        Идемпотентно по `duel_id` (повторный вызов перезаписывает job).
        """

    @abc.abstractmethod
    async def cancel_chat_to_global_escalation(self, *, duel_id: int) -> None:
        """Снять запланированный escalation-job (NO-OP, если его нет).

        Вызывается из `AcceptDuel` (chat-accept успел) и `CancelDuel`.
        """

    @abc.abstractmethod
    async def schedule_global_lobby_expiration(
        self,
        *,
        duel_id: int,
        run_at: datetime,
    ) -> None:
        """Запланировать `ExpireLobbyEntry(duel_id=...)` на `run_at` (UTC).

        Срабатывает через `pvp.duel_1v1.global_lobby_ttl_minutes` после
        попадания вызова в глобальное лобби (либо сразу при
        `mode=GLOBAL_ONLY`, либо после escalation-job-а из chat-режима).
        Идемпотентно по `duel_id`.
        """

    @abc.abstractmethod
    async def cancel_global_lobby_expiration(self, *, duel_id: int) -> None:
        """Снять запланированный expiration-job (NO-OP, если его нет).

        Вызывается из `MatchFromLobby` (вызов забран другим игроком),
        `CancelDuel` (челленджер отменил вручную).
        """

    # ── Спринт 2.1.G: AFK-таймер раунда PvP ──

    @abc.abstractmethod
    async def schedule_round_afk_resolution(
        self,
        *,
        duel_id: int,
        round_num: int,
        run_at: datetime,
    ) -> None:
        """Запланировать `ResolveAfkRound(duel_id, round_num)` на `run_at` (UTC).

        Срабатывает через `pvp.duel_1v1.round_timer_seconds` после
        начала раунда (`accept` для раунда 1; закрытие предыдущего —
        для раундов 2..N). Идемпотентно по паре `(duel_id, round_num)`:
        повторный вызов перезаписывает job.
        """

    @abc.abstractmethod
    async def cancel_round_afk_resolution(
        self,
        *,
        duel_id: int,
        round_num: int,
    ) -> None:
        """Снять AFK-таймер для конкретного раунда (NO-OP, если его нет).

        Вызывается из `SubmitMove` / `CancelDuel` / `ResolveAfkRound`,
        когда раунд закрылся реальными ходами или дуэль отменена.
        """

    # ── Спринт 2.2.F: AFK-таймер массового PvP ──

    @abc.abstractmethod
    async def schedule_mass_duel_afk_resolution(
        self,
        *,
        duel_id: int,
        run_at: datetime,
    ) -> None:
        """Запланировать `ForceResolveMassDuel(duel_id=...)` на `run_at` (UTC).

        Срабатывает через `pvp.mass_duel.move_timer_seconds` после
        `StartMassDuel`. Идемпотентно по `duel_id`: повторный вызов
        перезаписывает job (нужно для recovery-сценариев на старте бота).
        """

    @abc.abstractmethod
    async def cancel_mass_duel_afk_resolution(
        self,
        *,
        duel_id: int,
    ) -> None:
        """Снять AFK-таймер масс-боя (NO-OP, если job-а нет).

        Вызывается из `ResolveMassDuel` (все участники успели сами),
        `CancelMassDuel` (админ отменил), `ForceResolveMassDuel`
        (best-effort cleanup на случай повторного срабатывания).
        """

    # ── Спринт 2.3.F.2: per-clan cron «Главы клана дня» ──

    @abc.abstractmethod
    async def schedule_daily_head_cron(
        self,
        *,
        clan_id: int,
        run_at: datetime,
    ) -> None:
        """Запланировать `RunDailyHeadCron(clan_id=...)` на `run_at` (UTC).

        `run_at` — конкретный момент `00:00 МСК + offset(clan_id, date)`,
        вычисленный через `compute_daily_head_cron_offset_minutes(...)`
        (см. `domain/daily_head/scheduling.py`).

        Идемпотентно по `clan_id`: повторный вызов перезаписывает job —
        нужно для recovery-сценариев на старте бота и ежесуточного
        перепланирования (на следующие сутки offset другой). Per-clan
        ключ означает, что одновременно у клана может быть только один
        запланированный cron-job, что соответствует «один глава в сутки».
        """

    @abc.abstractmethod
    async def cancel_daily_head_cron(self, *, clan_id: int) -> None:
        """Снять daily-head-cron-job для клана (NO-OP, если его нет).

        Вызывается при заморозке клана (frozen-кланы не должны получать
        главу дня — ГДД §6.1.8) и из самого callback-а после успешного
        выполнения, чтобы не мешать перепланированию следующего дня.
        """

    # ── Спринт 3.1-B: PvE-походы (горы и данжон, ГДД §8) ──

    @abc.abstractmethod
    async def schedule_finish_mountain_run(
        self,
        *,
        run_id: int,
        run_at: datetime,
    ) -> None:
        """Запланировать `FinishMountainRun(run_id=...)` на `run_at` (UTC).

        Идемпотентно по `run_id`: повторный вызов перезаписывает job
        (recovery-сценарий после рестарта воркера).
        """

    @abc.abstractmethod
    async def cancel_finish_mountain_run(self, *, run_id: int) -> None:
        """Снять запланированный mountain-finish-job (NO-OP, если его нет)."""

    @abc.abstractmethod
    async def schedule_finish_dungeon_run(
        self,
        *,
        run_id: int,
        run_at: datetime,
    ) -> None:
        """Запланировать `FinishDungeonRun(run_id=...)` на `run_at` (UTC).

        Идемпотентно по `run_id` (тот же recovery-контракт, что у леса
        и гор).
        """

    @abc.abstractmethod
    async def cancel_finish_dungeon_run(self, *, run_id: int) -> None:
        """Снять запланированный dungeon-finish-job (NO-OP, если его нет)."""

    # ── Спринт 3.2-B: караваны (lobby-close, ГДД §9) ──

    @abc.abstractmethod
    async def schedule_caravan_lobby_close(
        self,
        *,
        caravan_id: int,
        run_at: datetime,
    ) -> None:
        """Запланировать `CloseCaravanLobby(caravan_id=...)` на `run_at` (UTC).

        Срабатывает через `caravans.lobby_minutes` после создания
        каравана и переводит его из `LOBBY → IN_BATTLE`. Идемпотентно
        по `caravan_id`: повторный вызов перезаписывает job
        (recovery-сценарий после рестарта воркера).

        Сам resolve боя и `caravan_battle_finish`-job ставятся в 3.2-C
        внутри `CloseCaravanLobby` use-case-а.
        """

    @abc.abstractmethod
    async def cancel_caravan_lobby_close(self, *, caravan_id: int) -> None:
        """Снять lobby-close-job каравана (NO-OP, если его нет).

        Вызывается, когда лобби закрывается раньше срока (ручная отмена
        каравана лидером в 3.2-C) или из самого callback-а после
        успешного перевода в `IN_BATTLE` (best-effort cleanup).
        """

    # ── Спринт 3.2-C: караваны (battle-finish, ГДД §9.5–§9.6) ──

    @abc.abstractmethod
    async def schedule_caravan_battle_finish(
        self,
        *,
        caravan_id: int,
        run_at: datetime,
    ) -> None:
        """Запланировать `FinishCaravanBattle(caravan_id=...)` на `run_at` (UTC).

        Срабатывает через `caravans.battle_minutes` после перехода
        каравана `LOBBY → IN_BATTLE` (ставится в `CloseCaravanLobby` use-case-е
        при mark_in_battle). Идемпотентно по `caravan_id`: повторный
        вызов перезаписывает job (recovery-сценарий после рестарта
        воркера).

        Сам resolve боя — синхронный в callback-е, без раунд-tick-ов
        (см. ГДД §9.5: каждый рейдер — 1 удар, караванщики — 2 блока,
        защитники — 1 блок, детерминистично от `random_seed`).
        """

    @abc.abstractmethod
    async def cancel_caravan_battle_finish(self, *, caravan_id: int) -> None:
        """Снять battle-finish-job каравана (NO-OP, если его нет).

        Вызывается, когда бой завершается раньше срока (например, при
        ручной отмене каравана лидером — но это сценарий из `LOBBY`,
        где battle-finish ещё не запланирован) или из самого callback-а
        после успешного завершения боя (best-effort cleanup).
        """

    # ── Спринт 2.4.E: еженедельная сводка рефералов клана ──

    @abc.abstractmethod
    async def schedule_weekly_clan_referral_summary_cron(self) -> None:
        """Запланировать глобальный cron «еженедельная сводка рефералов клана».

        В отличие от per-clan-`schedule_daily_head_cron(...)`, это один
        APScheduler-job-cron — `CronTrigger(day_of_week='sun', hour=18,
        minute=0, timezone='UTC')`. Внутри callback-а реализация
        итерирует `IClanRepository.list_active()` и зовёт
        `RunWeeklyClanReferralSummary` на каждый клан.

        Идемпотентно: повторный вызов перезаписывает job (нужно для
        старта бота — мы каждый раз перевешиваем cron заново, чтобы
        не плодить дубликаты).
        """
