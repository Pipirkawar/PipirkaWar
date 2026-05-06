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
