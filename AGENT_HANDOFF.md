# AGENT_HANDOFF — Спринт 2.1.F.2 (PvP global lobby — use-cases + scheduler)

> **Этот файл — временный.** Удалить отдельным коммитом перед открытием PR
> (см. шаг «Финал» внизу). Не должен попасть на main.

## Контекст

- **PR 2.1.F.1** — domain + persistence слой глобального лобби PvP **— ✅ смержен (#52)**.
  Появилось:
  - `LobbyEntry` VO + `IGlobalLobbyRepository` (`enqueue` идемпотентно, `pop_oldest` атомарный FIFO, `remove`, `is_in_lobby`)
  - `Duel.escalate_to_global(*, now)` — переход `CHAT_THEN_GLOBAL → GLOBAL_ONLY`, обнуляет `challenged_id`. Не идемпотентен.
  - `SqlAlchemyGlobalLobbyRepository`, `FakeGlobalLobbyRepository`
  - `pvp.duel_1v1.global_lobby_ttl_minutes` (default 10) и `chat_to_global_promotion_minutes` (default 3) в Pydantic-схеме баланса
  - Миграция `0010_pvp_global_lobby`

- **PR 2.1.F.2** (текущая ветка `devin/1778009003-sprint-2-1-f-2-pvp-lobby-usecases`) — use-cases + scheduler.
  Это саб-PR 2 из 3 в саб-спринте 2.1.F.

- **PR 2.1.F.3** — bot-handlers + DI (последний саб-PR серии). Не трогать в этой ветке.

## Цель F.2 (~600 LoC)

1. **Расширить порт `IDelayedJobScheduler`**:
   - `schedule_chat_to_global_escalation(*, duel_id: int, run_at: datetime)` — job вызовет `EscalateChatToGlobal(duel_id=...)`.
   - `cancel_chat_to_global_escalation(*, duel_id: int)` — best-effort cancel (NO-OP, если job-а нет).
   - `schedule_global_lobby_expiration(*, duel_id: int, run_at: datetime)` — job вызовет `ExpireLobbyEntry(duel_id=...)`.
   - `cancel_global_lobby_expiration(*, duel_id: int)`.

2. **Адаптеры**:
   - `APSchedulerDelayedJobScheduler` — добавить новые методы + 2 новых job-а (`_run_chat_escalation_job`, `_run_lobby_expiration_job`). Каждый принимает `factory`-callable (по аналогии с `finish_factory`) для создания свежего use-case с зависимостями.
   - `FakeDelayedJobScheduler` (в `tests/fakes/delayed_job_scheduler.py`) — добавить отдельные dict-ы `scheduled_escalations`, `cancelled_escalations`, `scheduled_expirations`, `cancelled_expirations`.

3. **4 новых use-case-а** в `application/pvp/`:
   - `EnqueueGlobalDuel(uow, duels_repo, lobby_repo, scheduler, balance, clock)`:
     - Берёт `duel_id`, проверяет что дуэль существует и `mode == GLOBAL_ONLY` и `state == PENDING_ACCEPT`.
     - `lobby_repo.enqueue(duel_id=..., enqueued_at=clock.now())` (идемпотентно).
     - `scheduler.schedule_global_lobby_expiration(duel_id=..., run_at=now + ttl_minutes)`.
     - Если уже в лобби — это нормально (идемпотентно), но тогда expiration-job не пере-запланируется (опционально — для DX оставить замену через `replace_existing=True` на APScheduler-стороне).
     - Audit `PVP_LOBBY_ENQUEUED` (новый AuditAction).
   - `MatchFromLobby(uow, duels_repo, lobby_repo, players_repo, anticheat_guard, length_validator, lock_service, scheduler, balance, audit, clock)`:
     - Принимает `accepter_tg_id` из `/duel_global`-handler-а.
     - `accepter` ищется → проверка регистрации/anti-cheat/PvP-eligibility (длина/толщина из balance).
     - `lobby_repo.pop_oldest()` — если `None`, возвращает «empty lobby».
     - Если выбранная дуэль = self-challenge (`challenger_id == accepter.id`), кладём обратно (либо просто берём следующую — это race-edge case, обсуждается в коде).
     - `Duel.accept(...)` через стандартный `AcceptDuel`-флоу (lock, snapshot lengths, scheduler.cancel_global_lobby_expiration, scheduler.cancel_chat_to_global_escalation).
     - Audit `PVP_LOBBY_MATCHED`.
   - `EscalateChatToGlobal(uow, duels_repo, lobby_repo, scheduler, balance, audit, clock)`:
     - Вызывается job-ом через 3 мин после `mode=CHAT_THEN_GLOBAL`-вызова.
     - Если дуэль уже не `PENDING_ACCEPT` — NO-OP (например, accept или cancel уже сработали).
     - `Duel.escalate_to_global(now=clock.now())` → `save`.
     - `lobby_repo.enqueue(...)` + `schedule_global_lobby_expiration(...)`.
     - Audit `PVP_LOBBY_ESCALATED`.
   - `ExpireLobbyEntry(uow, duels_repo, lobby_repo, scheduler, audit, clock)`:
     - Вызывается job-ом через 10 мин после enqueue.
     - Если уже не в лобби (accept или cancel сработали раньше) — NO-OP.
     - `Duel.cancel(now=clock.now())` (idempotent на уже cancelled) + release lock.
     - `lobby_repo.remove(duel_id=...)`.
     - Audit `PVP_LOBBY_EXPIRED` + `PVP_DUEL_CANCELLED`.

4. **Интеграция в существующие use-case-ы**:
   - `ChallengeDuel`:
     - Если `mode == CHAT_THEN_GLOBAL` → `scheduler.schedule_chat_to_global_escalation(duel_id, now + 3 min)`.
     - Если `mode == GLOBAL_ONLY` → сразу call `EnqueueGlobalDuel(duel_id)` (или inline-логика — посмотреть существующий стиль).
   - `AcceptDuel`:
     - На chat-accept: `scheduler.cancel_chat_to_global_escalation(duel_id)`.
     - На global-accept (через MatchFromLobby): `scheduler.cancel_global_lobby_expiration(duel_id)` + `lobby_repo.remove(...)`.
   - `CancelDuel`:
     - `scheduler.cancel_chat_to_global_escalation(duel_id)` + `scheduler.cancel_global_lobby_expiration(duel_id)`.
     - Если дуэль была в лобби → `lobby_repo.remove(...)`.

5. **Аудит-actions** (если ещё не добавлены — посмотри `domain/audit/actions.py`):
   - `PVP_LOBBY_ENQUEUED`, `PVP_LOBBY_MATCHED`, `PVP_LOBBY_ESCALATED`, `PVP_LOBBY_EXPIRED`.

6. **Тесты** (~50 unit + 0 integration в этом PR — integration-тесты scheduler поверх APScheduler сложно гонять в CI; integration придёт в F.3):
   - `tests/unit/application/pvp/test_enqueue_global_duel.py` (5–7)
   - `tests/unit/application/pvp/test_match_from_lobby.py` (8–10)
   - `tests/unit/application/pvp/test_escalate_chat_to_global.py` (5–7)
   - `tests/unit/application/pvp/test_expire_lobby_entry.py` (5–7)
   - Расширения `test_challenge_duel.py` / `test_accept_duel.py` / `test_cancel_duel.py` — проверка, что нужные `schedule_*` / `cancel_*` вызваны.

## Стратегия выполнения по шагам (с коммитом в конце каждого)

### Step 1: расширить порт + Fake (~50 LoC, без логики)
- [ ] Добавить 4 метода в `domain/shared/ports/scheduler.py`.
- [ ] Расширить `FakeDelayedJobScheduler` в `tests/fakes/delayed_job_scheduler.py`.
- [ ] `make ci` (только что новые методы — старые тесты должны пройти).
- [ ] `git commit -m "feat(scheduler): extend IDelayedJobScheduler ports for PvP lobby (Спринт 2.1.F.2 step 1)"`

### Step 2: APScheduler-адаптер (~80 LoC)
- [ ] Добавить новые методы и 2 job-callback-а в `infrastructure/scheduler/aps.py`. Принять 2 новых `factory: Callable[[], EscalateChatToGlobal]` / `Callable[[], ExpireLobbyEntry]` через конструктор (Optional, т.к. могут не быть собраны до F.3).
- [ ] `make ci` (но без use-case-ов factory будет падать; сделать factory Optional с фоллбэком на `NotImplementedError` — тогда composition-root в F.2 ещё не обязан их подсовывать).
- [ ] Лучше: factory принимает строго типизированный Protocol, но пока — `Callable[[], Any] | None`, и если None — лог + return.
- [ ] `git commit -m "feat(scheduler): APScheduler adapter — escalation + expiration jobs (Спринт 2.1.F.2 step 2)"`

### Step 3: 4 use-case-а + unit-тесты (~250 LoC + 200 тестов = 450)
- [ ] `application/pvp/enqueue_global_duel.py`
- [ ] `application/pvp/match_from_lobby.py`
- [ ] `application/pvp/escalate_chat_to_global.py`
- [ ] `application/pvp/expire_lobby_entry.py`
- [ ] Обновить `application/pvp/__init__.py`.
- [ ] Тесты для каждого.
- [ ] `make ci`.
- [ ] `git commit -m "feat(pvp): 4 lobby use-cases (Enqueue/Match/Escalate/Expire) (Спринт 2.1.F.2 step 3)"`

### Step 4: интеграция в ChallengeDuel/AcceptDuel/CancelDuel + расширения тестов (~150 LoC)
- [ ] Подсунуть `scheduler` (если ещё не было) и `lobby_repo` в эти use-case-ы.
- [ ] Обновить тесты.
- [ ] `make ci`.
- [ ] `git commit -m "feat(pvp): integrate global lobby into ChallengeDuel/AcceptDuel/CancelDuel (Спринт 2.1.F.2 step 4)"`

### Step 5: composition-root + удаление HANDOFF + PR
- [ ] `bot/main.py` Container — добавить `lobby_repo`, новые use-case-ы, прокинуть в scheduler factory.
- [ ] Обновить `tests/unit/bot/test_composition_root.py` (`Container(...)` с новыми полями).
- [ ] Обновить `docs/current_tasks.md` (F.1 → ✅ #52, F.2 → 🟢 в работе) и `docs/history.md` (новая запись).
- [ ] `make ci`.
- [ ] `rm AGENT_HANDOFF.md && git add AGENT_HANDOFF.md && git commit -m "chore: remove HANDOFF before PR"`
- [ ] `git push -u origin <branch>`
- [ ] `git_pr(action="fetch_template")` → `git_pr(action="create")`.
- [ ] `git(action="pr_checks", wait_mode="all")`.

## Ключевые контракты для следующего агента

### IGlobalLobbyRepository (уже есть, не трогать)

```python
class IGlobalLobbyRepository(abc.ABC):
    async def enqueue(self, *, duel_id: int, enqueued_at: datetime) -> bool: ...
    async def pop_oldest(self) -> LobbyEntry | None: ...
    async def remove(self, *, duel_id: int) -> bool: ...
    async def is_in_lobby(self, *, duel_id: int) -> bool: ...
```

### Duel.escalate_to_global (уже есть, не трогать)

```python
def escalate_to_global(self, *, now: datetime) -> Duel:
    """Переход CHAT_THEN_GLOBAL → GLOBAL_ONLY. Не идемпотентен.

    Raises InvalidDuelStateError если state != PENDING_ACCEPT
    или mode != CHAT_THEN_GLOBAL.
    """
```

### Конвенции из PR-ов 2.1.A–E (паттерн use-case)

- Все use-case-ы — frozen-dataclass-ы (slots) с `__init__` и async `execute(input: ...) -> Output`.
- Транзакции — через `async with self._uow:`.
- Audit пишется только при реальном изменении (`audit.log(...)` внутри транзакции).
- Idempotency-keys для length-grant: `add_length:pvp_duel:{id}:{side}` (см. `application/pvp/apply_outcome.py`).
- Fake-объекты — pure dataclass-ы, без MagicMock.

### Файлы, на которые опираться при копировании паттерна

- `application/pvp/challenge_duel.py` — паттерн use-case с balance/anticheat/lock.
- `application/pvp/accept_duel.py` — паттерн lock + snapshot.
- `application/pvp/cancel_duel.py` — паттерн idempotent cancel.
- `application/forest/finish_run.py` — паттерн scheduler-fired use-case (NO-OP если уже завершён).

## Финал PR-а — обязательно

После того как тесты зелёные и PR создан:

1. `git`/`pr_checks` дождаться 3-х зелёных чеков (py3.11, py3.12, pip-audit).
2. После мерджа PR-а — обновить `docs/current_tasks.md` (F.2 → ✅смержено) и `docs/history.md` (новая запись сверху — формат см. в существующих записях за 2026-05-05).
3. Сразу стартовать F.3 (новая ветка `devin/$(date +%s)-sprint-2-1-f-3-pvp-lobby-handlers`).

## Если в F.2 что-то не получается

- **mypy ругается на factory без типа** → используй TypeAlias `EscalationUseCaseFactory = Callable[[], EscalateChatToGlobal]`, импорт под `if TYPE_CHECKING:` чтобы не ловить циклы.
- **Тест падает на «scheduler отлично заскедулил, но cancel не сработал»** → проверь, что в Fake-е cancel вычищает из `scheduled`-dict-а и пишет в `cancelled`-list (двунаправленно).
- **race-condition self-challenge через MatchFromLobby** → не пытайся починить «правильно»; в первом проходе достаточно вернуть пользователю «empty lobby» (попадёт обратно если не дёрнул).
- **Audit-actions не определены** → создай отдельным маленьким коммитом + тестом на `AuditAction`-enum.
