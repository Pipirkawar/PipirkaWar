# Sprint 2.1.E — Continuation Instructions for Next Agent

> **DELETE THIS FILE BEFORE CREATING THE PR.** It exists only as a hand-off
> note in case the previous agent ran out of tokens mid-task. It must NOT
> appear in the final PR diff.

## Что уже сделано

### 1. Доменная база (предыдущие саб-спринты — НЕ ТРОГАТЬ)
- 2.1.A: чистый движок боя 1×1 (`domain/pvp/`).
- 2.1.B: агрегат `Duel` со всем lifecycle.
- 2.1.C: persistence `SqlAlchemyDuelRepository` + миграция `0009_pvp_duels`.
- 2.1.D: 5 application use-cases — `ChallengeDuel`, `AcceptDuel`, `CancelDuel`,
  `SubmitMove`, `ResolveAfkRound` (PR #49 смержен в main).

### 2. Сделано в текущей ветке `devin/1778005211-sprint-2-1-e-pvp-handlers`
- **`src/pipirik_wars/bot/presenters/duel.py`** — `DuelPresenter`:
  * 4 dataclass-а callback-data: `AcceptCallbackData`, `RejectCallbackData`,
    `AttackCallbackData`, `BlockCallbackData`.
  * 4 пары serialize/parse функций с валидацией на `_parse_positive_int`
    и `_parse_position`.
  * `DuelPresenter` с методами: `private_needs_global`, `usage`,
    `not_registered`, `target_not_registered`, `target_is_bot`,
    `self_challenge`, `challenge_chat_only`, `challenge_chat_then_global`,
    `challenge_global`, `chat_accepted`, `cancelled`, `cancel_usage`,
    `round_attack_prompt`, `round_block_prompt`, `round_waiting`,
    `result_victory`, `result_defeat`, `result_draw`, `requirements_not_met`,
    `anticheat_blocked`, `lock_already_held`, и 9 toast-методов:
    `toast_accepted`, `toast_rejected`, `toast_cancelled`,
    `toast_duel_not_found`, `toast_not_participant`, `toast_foreign_button`,
    `toast_invalid_state`, `toast_already_submitted`, `toast_outdated`.
  * 3 keyboard-метода: `challenge_keyboard`, `attack_keyboard`,
    `block_keyboard`.
- **`src/pipirik_wars/bot/presenters/__init__.py`** — экспорты обновлены.

## Что осталось сделать

### Шаг 1. Создать `src/pipirik_wars/bot/handlers/duel.py`

Паттерн — как в `bot/handlers/forest.py` и `bot/handlers/upgrade.py`.
Список handler-ов:

#### A. `@router.message(Command("duel"))` → `handle_duel`
- Параметры: `message`, `command: CommandObject`, `tg_identity`,
  `challenge_duel: ChallengeDuel`, `bundle: IMessageBundle`,
  `locale: Locale | None = None`.
- Логика:
  - В private chat (нет reply): `global_only` mode (не требует
    `challenged_tg_id`).
  - В group/supergroup без `reply_to_message`: показать
    `presenter.usage(...)`.
  - В group/supergroup с `reply_to_message`:
    - Если `reply_to_message.from_user.is_bot` → `presenter.target_is_bot(...)`
    - Если reply на собственное сообщение → `presenter.self_challenge(...)`
    - Иначе:
      - Парсим аргумент: `command.args == "chat"` → `chat_only`,
        иначе → `chat_then_global`.
      - Зовём `ChallengeDuel.execute(ChallengeDuelInput(
          challenger_tg_id=tg_identity.tg_user_id,
          challenged_tg_id=reply_to_message.from_user.id,
          mode=...,
        ))`.
  - Ловим:
    - `PlayerNotFoundError` (где `tg_id == challenger`) →
      `presenter.not_registered(...)`.
    - `PlayerNotFoundError` (где `tg_id == challenged`) →
      `presenter.target_not_registered(...)`. Различить по `exc.tg_id`.
    - `SelfChallengeError` → `presenter.self_challenge(...)`.
    - `PvpRequirementsNotMetError` → `presenter.requirements_not_met(...)`.
    - `AnticheatSoftBanError` → `presenter.anticheat_blocked(...)`.
    - `LockAlreadyHeldError` → `presenter.lock_already_held(...)`.
  - При успехе:
    - Для `chat_only`/`chat_then_global`: `message.answer(presenter.challenge_chat_*(),
      reply_markup=presenter.challenge_keyboard(duel_id, locale))`.
    - Для `global_only`: `message.answer(presenter.challenge_global(...))`.

#### B. `@router.callback_query(F.data.startswith("pvp-accept:"))` → `handle_pvp_accept`
- Параметры: `callback`, `bot: Bot`, `tg_identity`, `accept_duel: AcceptDuel`,
  `players: IPlayerRepository`, `bundle: IMessageBundle`,
  `locale: Locale | None = None`.
- Парсим: `parse_accept_callback_data(callback.data)`.
- Зовём `AcceptDuel.execute(AcceptDuelInput(duel_id, tg_id))`.
- Ловим: `DuelNotFoundError` → `toast_duel_not_found`,
  `NotADuelParticipantError` → `toast_not_participant`,
  `InvalidDuelStateError` → `toast_invalid_state`,
  `LockAlreadyHeldError` → `lock_already_held`,
  `PvpRequirementsNotMetError` → `requirements_not_met`.
- При успехе:
  - `callback.answer(presenter.toast_accepted(...))`.
  - `_strip_keyboard(callback)`, `_set_message_text(callback,
    presenter.chat_accepted(...))`.
  - Загружаем обоих игроков по `Duel.challenger_id` / `Duel.challenged_id`
    через `players.get_by_id()`.
  - Шлём DM **обоим**: `bot.send_message(chat_id=player.tg_id,
    text=presenter.round_attack_prompt(round_num=1, locale),
    reply_markup=presenter.attack_keyboard(duel_id=result.duel.id,
    round_num=1, locale))`.

#### C. `@router.callback_query(F.data.startswith("pvp-reject:"))` → `handle_pvp_reject`
- Парсим. Только toast `toast_rejected` + `_strip_keyboard`. Без мутации
  состояния — opponent просто не принял; pending duel останется до
  TTL-cleanup в 2.1.F.

#### D. `@router.callback_query(F.data.startswith("pvp-attack:"))` → `handle_pvp_attack`
- Парсим: `parse_attack_callback_data(callback.data)`.
- Без вызова use-case! Просто edit message: «Раунд N: атака — X. Выбери блок»
  + `presenter.block_keyboard(duel_id, round_num, attack=parsed.position, locale)`.
- `callback.answer()` без текста.

#### E. `@router.callback_query(F.data.startswith("pvp-block:"))` → `handle_pvp_block`
- Парсим: `parse_block_callback_data(callback.data)`.
- Зовём `SubmitMove.execute(SubmitMoveInput(duel_id, tg_id, attack, block))`.
- Ловим: `DuelNotFoundError`, `NotADuelParticipantError`,
  `InvalidDuelStateError`, `MoveAlreadySubmittedError`, `AnticheatSoftBanError`.
- При успехе:
  - `_strip_keyboard(callback)`.
  - Если `result.duel.is_completed`:
    - Загружаем обоих игроков (нужны их **новые** длины — после
      `apply_duel_outcome`).
    - Шлём DM с результатом: `result_victory` / `result_defeat` /
      `result_draw` обоим (по `result.duel.final_outcome.winner`).
    - Edit chat-message: дополнить `chat_accepted` финальным результатом
      (опционально — можно ничего не редактировать).
  - Иначе если раунд закрыт (advanced): сравниваем
    `result.duel.pending_round.round_num > parsed.round_num`:
    - Шлём DM-промпт `round_attack_prompt` обоим с `round_num=новый`.
  - Иначе (раунд НЕ закрыт — оппонент не походил):
    - Edit message → `round_waiting(round_num=parsed.round_num)`.

#### F. `@router.message(Command("cancel_duel"))` → `handle_cancel_duel`
- Параметры: `message`, `command: CommandObject`, `tg_identity`,
  `cancel_duel: CancelDuel`, `bundle`, `locale`.
- Парсим `command.args` (целое число `duel_id`). Если нет — `cancel_usage`.
- Зовём `CancelDuel.execute(CancelDuelInput(duel_id, tg_id))`.
- Ловим: `DuelNotFoundError`, `NotADuelParticipantError`,
  `InvalidDuelStateError`.
- При успехе: `message.answer(presenter.cancelled(challenger_username, locale))`.

### Шаг 2. Зарегистрировать в `__init__.py` и `bot/main.py`

#### `src/pipirik_wars/bot/handlers/__init__.py`
```python
from pipirik_wars.bot.handlers.duel import router as duel_router
# ...
def register_routers(dispatcher: Dispatcher) -> None:
    # ... существующее
    dispatcher.include_router(duel_router)  # после upgrade_router
```

#### `src/pipirik_wars/bot/main.py`
- В `Container @dataclass` добавить поля:
  ```python
  challenge_duel: ChallengeDuel
  accept_duel: AcceptDuel
  cancel_duel: CancelDuel
  submit_move: SubmitMove
  resolve_afk_round: ResolveAfkRound  # понадобится в 2.1.G, но регистрируем сейчас
  ```
- В `build_container()` нужен `IDuelRepository`:
  ```python
  duels = SqlAlchemyDuelRepository(session_factory)  # или просто session
  ```
  Проверить, как другие репо подключены — `players`, `forest_runs` —
  это даст шаблон.
- Конструировать use-cases:
  ```python
  challenge_duel = ChallengeDuel(uow=uow, players=players, duels=duels,
      locks=activity_lock_service, balance=balance, audit=audit, clock=clock)
  accept_duel = AcceptDuel(uow=uow, players=players, duels=duels,
      locks=activity_lock_service, balance=balance, audit=audit, clock=clock)
  cancel_duel = CancelDuel(uow=uow, players=players, duels=duels,
      locks=activity_lock_service, audit=audit, clock=clock)
  submit_move = SubmitMove(uow=uow, players=players, duels=duels,
      locks=activity_lock_service, length_granter=add_length,
      audit=audit, clock=clock)
  resolve_afk_round = ResolveAfkRound(uow=uow, players=players, duels=duels,
      locks=activity_lock_service, length_granter=add_length, audit=audit,
      clock=clock, random=RealRandom())
  ```
  Дополнительно нужен `players: IPlayerRepository` в dispatcher — он там
  уже может быть; если нет, добавить.
- В `build_dispatcher()`:
  ```python
  dispatcher["challenge_duel"] = container.challenge_duel
  dispatcher["accept_duel"] = container.accept_duel
  dispatcher["cancel_duel"] = container.cancel_duel
  dispatcher["submit_move"] = container.submit_move
  dispatcher["resolve_afk_round"] = container.resolve_afk_round
  dispatcher["players"] = container.players  # для handler-а pvp-accept
  ```

### Шаг 3. Локали `duel-*`

Добавить в `locales/ru.ftl` и `locales/en.ftl` (СОДЕРЖАТЬ ОДИНАКОВЫЕ КЛЮЧИ).
Список ключей (из `presenters/duel.py`):

| Key | RU placeholder | EN placeholder |
|---|---|---|
| `duel-private-needs-global` | "🍆 Чтобы вызвать кого-то на дуэль, ответь /duel на сообщение оппонента в общем чате клана. Глобальный пул откроется в Фазе 2.1.F." | "🍆 To challenge someone, reply /duel to their message in your clan chat. Global pool opens in Phase 2.1.F." |
| `duel-usage` | "🍆 Использование: ответь `/duel` на сообщение оппонента. По умолчанию — режим «Чат → Глобал». Для «Только чат» — `/duel chat`." | "🍆 Usage: reply `/duel` to opponent's message. Default mode is chat→global. For chat-only — `/duel chat`." |
| `duel-not-registered` | "🍆 Похоже, ты ещё не зарегистрирован. Нажми /start." | "🍆 You're not registered yet. Tap /start first." |
| `duel-target-not-registered` | "🍆 Соперник ещё не зарегистрирован в боте — попроси его нажать /start в ЛС." | "🍆 Opponent isn't registered yet — ask them to /start the bot." |
| `duel-target-is-bot` | "🍆 На дуэль можно вызвать только живого пипирика, не бота." | "🍆 You can only challenge a real player, not a bot." |
| `duel-self-challenge` | "🍆 Сам с собой? Найди реального оппонента." | "🍆 Challenging yourself? Find a real opponent." |
| `duel-challenge-chat` | "⚔️ { $challenger } вызывает { $challenged } на дуэль (только в этом чате)! Принять?" | "⚔️ { $challenger } challenges { $challenged } to a duel (chat only)! Accept?" |
| `duel-challenge-chat-then-global` | "⚔️ { $challenger } вызывает { $challenged } на дуэль! Если оппонент не примет за 3 минуты — вызов уплывёт в глобальное лобби." | "⚔️ { $challenger } challenges { $challenged } to a duel! If not accepted within 3 minutes, the challenge will move to the global pool." |
| `duel-challenge-global` | "⚔️ { $challenger }, твой вызов отправлен в глобальное лобби (открывается в 2.1.F)." | "⚔️ { $challenger }, your challenge has been sent to the global pool (opening in 2.1.F)." |
| `duel-button-accept` | "Принять" | "Accept" |
| `duel-button-reject` | "Отклонить" | "Decline" |
| `duel-button-attack-high` | "Атака: ⬆ верх" | "Attack: ⬆ high" |
| `duel-button-attack-mid` | "Атака: ➡ центр" | "Attack: ➡ mid" |
| `duel-button-attack-low` | "Атака: ⬇ низ" | "Attack: ⬇ low" |
| `duel-button-block-high` | "Блок: ⬆ верх" | "Block: ⬆ high" |
| `duel-button-block-mid` | "Блок: ➡ центр" | "Block: ➡ mid" |
| `duel-button-block-low` | "Блок: ⬇ низ" | "Block: ⬇ low" |
| `duel-round-attack-prompt` | "🥊 Раунд { $round_num } из 3. Куда бьёшь?" | "🥊 Round { $round_num } of 3. Where do you strike?" |
| `duel-round-block-prompt` | "🛡 Раунд { $round_num } из 3. Атака: { $attack }. Что блокируешь?" | "🛡 Round { $round_num } of 3. Attack: { $attack }. What do you block?" |
| `duel-round-waiting` | "⏳ Раунд { $round_num } — твой ход принят. Ждём оппонента..." | "⏳ Round { $round_num } — move accepted. Waiting for opponent..." |
| `duel-result-victory` | "🏆 Победа! +{ NUMBER($delta_cm, useGrouping: 0) } см. Длина теперь { NUMBER($new_length_cm, useGrouping: 0) } см." | "🏆 Victory! +{ NUMBER($delta_cm, useGrouping: 0) } cm. Length is now { NUMBER($new_length_cm, useGrouping: 0) } cm." |
| `duel-result-defeat` | "💀 Поражение. { NUMBER($delta_cm, useGrouping: 0) } см. Длина теперь { NUMBER($new_length_cm, useGrouping: 0) } см." | "💀 Defeat. { NUMBER($delta_cm, useGrouping: 0) } cm. Length is now { NUMBER($new_length_cm, useGrouping: 0) } cm." |
| `duel-result-draw` | "🤝 Ничья. Длина не изменилась — { NUMBER($length_cm, useGrouping: 0) } см." | "🤝 Draw. Length unchanged — { NUMBER($length_cm, useGrouping: 0) } cm." |
| `duel-cancelled` | "❌ Вызов отменён челленджером { $challenger }." | "❌ Challenge cancelled by { $challenger }." |
| `duel-cancel-usage` | "Использование: `/cancel_duel <duel_id>`. ID можно найти в карточке вызова." | "Usage: `/cancel_duel <duel_id>`. ID is shown in the challenge card." |
| `duel-chat-accepted` | "✅ { $challenged } принял вызов { $challenger }. Бой идёт в ЛС бота." | "✅ { $challenged } accepted { $challenger }'s challenge. Fight in progress (private)." |
| `duel-toast-accepted` | "Вызов принят!" | "Challenge accepted!" |
| `duel-toast-rejected` | "Спасибо, не интересно." | "Thanks, not interested." |
| `duel-toast-cancelled` | "Вызов отменён." | "Challenge cancelled." |
| `duel-toast-not-found` | "Эта дуэль уже неактивна." | "This duel is no longer active." |
| `duel-toast-not-participant` | "Эта дуэль не для тебя." | "This duel isn't yours." |
| `duel-toast-foreign-button` | "Эта кнопка не для тебя." | "This button isn't for you." |
| `duel-toast-invalid-state` | "Дуэль уже не в той фазе." | "Duel is no longer in that phase." |
| `duel-toast-already-submitted` | "Ты уже сделал ход в этом раунде." | "You've already moved in this round." |
| `duel-toast-outdated` | "Кнопка устарела." | "Button is outdated." |
| `duel-requirements-not-met` | "📏 Для дуэлей нужны длина ≥ { NUMBER($min_length_cm, useGrouping: 0) } см и толщина ≥ { $min_thickness_level }." | "📏 Duels require length ≥ { NUMBER($min_length_cm, useGrouping: 0) } cm and thickness ≥ { $min_thickness_level }." |
| `duel-anticheat-blocked` | "Антибот-проверка активна до { $banned-until }. Дуэли временно заморожены." | "Anti-cheat check is active until { $banned-until }. Duels are temporarily frozen." |
| `duel-lock-already-held` | "🔒 Сейчас занят (например, в /forest). Сначала закончи активность." | "🔒 You're busy (e.g., in /forest). Finish the current activity first." |

### Шаг 4. Тесты

#### `tests/unit/bot/presenters/test_duel.py`
- Тесты на `accept_callback_data`/`parse_accept_callback_data` (round-trip,
  validation errors).
- Аналогично для reject/attack/block.
- Тесты на каждый метод `DuelPresenter` через `FakeMessageBundle` (как в
  `test_upgrade.py`):
  ```python
  def test_round_attack_prompt():
      p = DuelPresenter(bundle=FakeMessageBundle())
      assert p.round_attack_prompt(round_num=1, locale=Locale("ru")) == \
          "ru:duel-round-attack-prompt[round_num=1]"
  ```
- Тесты на keyboards: проверить, что callback_data deterministic, что
  text — это `<locale>:<key>`.

#### `tests/unit/bot/handlers/test_duel.py`
- Использовать `MagicMock(spec=Message)`, `MagicMock(spec=CallbackQuery)`,
  `AsyncMock` для `bot.send_message`, `MagicMock(spec=ChallengeDuel)`,
  `AsyncMock` для use-case-ов и `players.get_by_id`.
- Тесты:
  - `/duel` в private chat → `private_needs_global`.
  - `/duel` в group без reply → `usage`.
  - `/duel` в group reply на бота → `target_is_bot`.
  - `/duel` reply на себя → `self_challenge`.
  - `/duel` reply на игрока → ChallengeDuel вызвался с правильными
    параметрами, `mode == "chat_then_global"`.
  - `/duel chat` reply на игрока → ChallengeDuel вызвался с
    `mode == "chat_only"`.
  - PlayerNotFoundError для challenger → `not_registered`.
  - PvpRequirementsNotMetError → `requirements_not_met`.
  - Аналогично остальные эксепшены.
  - `pvp-accept:N` callback → AcceptDuel вызван, обоим игрокам отправлен
    DM с `attack_keyboard`.
  - `pvp-reject:N` → toast only.
  - `pvp-attack:N:1:high` → edit message → block_keyboard.
  - `pvp-block:N:1:high:mid` → SubmitMove вызван. Если
    `MoveSubmitted(duel, duel_completed=True)` → result DM обоим.
    Если round advanced → attack-prompt обоим. Если round still pending →
    edit message → `round_waiting`.
  - `/cancel_duel 42` → CancelDuel вызван.
- Цель: 30+ тестов, покрыть все ветки исключений.

### Шаг 5. Документация

#### `docs/current_tasks.md`
Найти строку `**2.1.E**` и заменить:
```
| **2.1.E** | ... | ⚪бэклог | 2.1.2 |
```
на:
```
| **2.1.E** | ... | 🟡 готово к ревью | 2.1.2 |
```
И в текстовой части добавить параграф о том, что сделано (см. как
оформлено для 2.1.A, 2.1.B, 2.1.C, 2.1.D).

#### `docs/history.md`
Добавить в начало (или в раздел Sprint 2.1):
```markdown
## Sprint 2.1.E — bot-handler-ы PvP (бой 1×1 в Telegram-UI)

**Дата:** YYYY-MM-DD
**PR:** TBD

### Что сделано
... (формулировки — см. как оформлены 2.1.B, 2.1.C, 2.1.D)
```

### Шаг 6. Удалить `AGENT_HANDOFF.md`!!!
```bash
git rm AGENT_HANDOFF.md
```

### Шаг 7. CI и PR

```bash
make ci  # ожидается: lint OK, mypy OK, lint-imports OK, pytest OK
git add -A && git commit -m "..." && git push
# Затем git_pr(action="fetch_template") + git_pr(action="create")
# Затем git(action="pr_checks", wait_mode="all")
```

## Полезные референсы

- Handler-pattern: `src/pipirik_wars/bot/handlers/upgrade.py` (270 строк) —
  ровно такой же стиль, что нужен для duel.
- Notifier-pattern: `src/pipirik_wars/bot/notifications/forest.py` —
  показывает, как `Bot.send_message(chat_id=tg_id)` используется для DM.
  Но для 2.1.E проще использовать `bot.send_message(...)` прямо в handler-е
  без отдельного notifier-а.
- Тесты handler-ов: `tests/unit/bot/handlers/test_upgrade.py` (517 строк) —
  паттерн моков и assertion-ов.
- Тесты presenter-ов: `tests/unit/bot/presenters/test_upgrade.py` (290 строк).
- DI registration: `src/pipirik_wars/bot/main.py` строки 400–541. Ищи
  упоминания `players`, `forest_runs`, чтобы понять, как репо
  инстанцируется (по `session_factory` или другому).

## Ловушки

1. **mypy-strict**: `Locale | None = None` в сигнатурах, `effective_locale =
   locale or DEFAULT_LOCALE`. Не пиши `locale: Locale = DEFAULT_LOCALE`.
2. **`PlayerNotFoundError`**: имеет поле `tg_id`. В handler-е `/duel` нужно
   различить challenger vs challenged по `exc.tg_id`.
3. **`callback.message`** может быть `None` или `InaccessibleMessage` (старое
   сообщение). Защищаться `try/except` в helpers `_strip_keyboard` /
   `_set_message_text` (см. `forest.py:252`).
4. **`bot.send_message(chat_id=tg_id)`** для DM — `chat_id` равен `tg_id`
   игрока (в Telegram у личного чата `chat_id == user_id`).
5. **Тесты `mock.assert_awaited_once_with(...)`** — для `bot.send_message`
   с `reply_markup=...` — клавиатура содержит `InlineKeyboardMarkup`,
   сравнивать через `kwargs["reply_markup"].inline_keyboard[...]`.
6. **`SqlAlchemyDuelRepository`** — посмотри его конструктор, скорее
   всего принимает `AsyncSession` или `sessionmaker`. Wire-up в
   `build_container()` должен совпадать с тем, как сделан
   `SqlAlchemyForestRunRepository` или `SqlAlchemyPlayerRepository`.

Удачи!
