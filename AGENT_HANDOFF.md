# HANDOFF — Спринт 2.2.F часть 2 (bot-слой массового PvP)

> ⚠️ Удали этот файл сразу как только продолжишь работу и убедишься, что задача
> понятна. Финальный merge PR-ов должен быть **без** этого файла.

## Контекст

* Репозиторий: `Pipirkawar/PipirkaWar`.
* Основной язык: Python 3.12, аиграм + APScheduler + SQLAlchemy. Pre-commit и `.venv` уже настроены.
* Сейчас идёт **Спринт 2.2.F** — bot-слой массового PvP клан×клан (ГДД §7.2).

### Что уже сделано (часть 1)

PR #65 (`devin/1778051724-sprint-2-2-f-mass-duel-handlers`): AFK-таймер
infrastructure. Уже:

* `IDelayedJobScheduler.schedule_mass_duel_afk_resolution(...)` /
  `cancel_mass_duel_afk_resolution(...)`.
* `APSchedulerDelayedJobScheduler` с `mass_duel_afk_factory`.
* `PvpMassDuelConfig.move_timer_seconds: int = Field(ge=60, le=600)` (default 180).
* Use-case-ы 2.2.E (`Start/Resolve/Force/Cancel MassDuel`) расширены `scheduler:
  IDelayedJobScheduler | None = None` параметром.
* DI `bot/main.py`: `mass_duel_afk_factory=lambda: force_resolve_mass_duel`,
  `scheduler=delayed_jobs` во все 4 use-case-а.
* `FakeDelayedJobScheduler` с полями `scheduled_mass_duel_afk` /
  `cancelled_mass_duel_afk`.
* +22 unit-теста (4 на конфиг, 7 на use-case-integration, 11 на APScheduler).
* `make ci` зелёный (2245 passed, coverage 95.93%).

**Если PR #65 уже смержён** — этот HANDOFF делается из `main`. Если ещё нет —
ветка для части 2 должна быть **с базой `devin/1778051724-sprint-2-2-f-mass-duel-handlers`**, не с main.

### Текущая ветка

`devin/<ts>-sprint-2-2-f-mass-duel-bot` (создана от ветки PR #65 или от main,
смотри выше).

## Что делать (часть 2 спринта 2.2.F)

### 1. Локали `pvp-mass-*` (RU + EN)

В `locales/ru.ftl` и `locales/en.ftl` — добавить новые ключи (не путай с существующими `duel-*` для 1×1):

* `pvp-mass-not-in-clan` — игрок не состоит в клане (для `/clan_attack` без аргумента).
* `pvp-mass-needs-target` — нет target-клана (handler: usage).
* `pvp-mass-target-not-found` — целевой клан не найден.
* `pvp-mass-self-attack` — нельзя атаковать свой клан.
* `pvp-mass-cooldown` — кулдаун (`{ NUMBER($hours_left, useGrouping: 0) } ч`).
* `pvp-mass-no-eligible-roster` — нет участников ≥ требований.
* `pvp-mass-started` — карточка старта в чате (с упоминаниями обоих кланов и таймером).
* `pvp-mass-prompt-attack` — DM участнику: «Раунд масс-боя. Куда бьёшь?».
* `pvp-mass-prompt-block` — DM: «Что блокируешь?».
* `pvp-mass-waiting` — ход принят, ждём остальных.
* `pvp-mass-result-victory` — итог: «Клан X выиграл, +N см на сторону».
* `pvp-mass-result-defeat` — итог проигравшим.
* `pvp-mass-result-draw` — ничья.
* `pvp-mass-button-attack-{high,mid,low}` — кнопки атаки.
* `pvp-mass-button-block-{high,mid,low}` — кнопки блока.
* `pvp-mass-toast-*` — toast-уведомления (not-participant, foreign-button, invalid-state, already-submitted, outdated).

Пример (ru.ftl):
```
# /clan_attack — масс-PvP клан×клан (Спринт 2.2.F).
pvp-mass-needs-target = Использование: `/clan_attack` в чате клана-противника. Команда работает только в групповых чатах.
pvp-mass-self-attack = Нельзя атаковать свой клан.
pvp-mass-cooldown = Атака отбита: кулдаун { NUMBER($hours_left, useGrouping: 0) } ч.
pvp-mass-started = ⚔️Битва кланов: { $clan1 } × { $clan2 }! Все участники получили инструкции в ЛС. Время на ход: { NUMBER($timer_seconds, useGrouping: 0) } сек.
pvp-mass-prompt-attack = ⚔️Раунд масс-боя клан×клан. Твой выбор атаки:
pvp-mass-prompt-block = 🛡 Куда блокируешь? Атака: { $attack }.
pvp-mass-waiting = ⏳Твой ход принят. Ждём остальных…
pvp-mass-result-victory = 🏆Победа! Клан { $clan } выиграл бой и забрал { NUMBER($total_dealt, useGrouping: 0) } см.
pvp-mass-result-defeat = 💀Поражение. Клан { $clan } проиграл и потерял { NUMBER($total_lost, useGrouping: 0) } см.
pvp-mass-result-draw = 🤝Ничья. Никто не нанёс больше другого.
pvp-mass-button-attack-high = ⬆️ Голова
pvp-mass-button-attack-mid = ⬄ Корпус
pvp-mass-button-attack-low = ⬇️ Ноги
pvp-mass-button-block-high = 🛡⬆️ Голова
pvp-mass-button-block-mid = 🛡⬄ Корпус
pvp-mass-button-block-low = 🛡⬇️ Ноги
```

EN — параллельные строки. Оба файла должны быть синхронизированы по ключам
(чтобы `IMessageBundle.format` не падал в fallback).

### 2. MassDuelPresenter (`src/pipirik_wars/bot/presenters/mass_duel.py`)

Шаблон — `src/pipirik_wars/bot/presenters/duel.py` (788 строк). Структура:

* **Префиксы callback_data** (≤ 64 байт):
  * `pvpm-attack:{duel_id}:{position}` — выбор атаки (используется в DM).
  * `pvpm-block:{duel_id}:{attack}:{position}` — выбор блока.
* **Frozen dataclasses** для парсенных callback_data:
  `MassAttackCallbackData(duel_id, position)`,
  `MassBlockCallbackData(duel_id, attack, position)`.
* **Сериализаторы** `mass_attack_callback_data(...)`, `mass_block_callback_data(...)`.
* **Парсеры** `parse_mass_attack_callback_data(data: str)`,
  `parse_mass_block_callback_data(data: str)` — бросают `ValueError` для невалидных
  строк (handler ловит и шлёт `toast_outdated`).
* **MessageKey-константы** (`MessageKey("pvp-mass-...")`) для всех текстов.
* **Класс `MassDuelPresenter`** с методами:
  * `started_card(*, clan1_title, clan2_title, timer_seconds, locale) -> str` — карточка для чата.
  * `prompt_attack(*, locale) -> str` — текст DM-промпта атаки.
  * `prompt_block(*, attack, locale) -> str` — текст DM-промпта блока.
  * `waiting(*, locale) -> str`.
  * `result_victory(*, clan_title, total_dealt, locale) -> str`.
  * `result_defeat(*, clan_title, total_lost, locale) -> str`.
  * `result_draw(*, locale) -> str`.
  * `attack_keyboard(*, duel_id, locale) -> InlineKeyboardMarkup` — `[High] [Mid] [Low]`.
  * `block_keyboard(*, duel_id, attack, locale) -> InlineKeyboardMarkup`.
  * `not_in_clan(*, locale)`, `needs_target(*, locale)`, и т. д. — error-методы.
  * `toast_*` — toast-методы.

Не путай ключи с `duel-*` (1×1 PvP).

### 3. Bot-handler (`src/pipirik_wars/bot/handlers/mass_duel.py`)

Шаблон — `src/pipirik_wars/bot/handlers/duel.py` (1100 строк). Регистрируется в
`bot/composition.py` или прямо в `build_dispatcher` (см. `duel.py`).

#### `/clan_attack` команда

Только в групповых чатах (group/supergroup), `chat_type filter`.

```
async def handle_clan_attack(message: Message, ...) -> None:
    # 1. Проверить chat_type — только group/supergroup.
    # 2. Резолвить attacker_clan по message.chat.id (это атакующий клан).
    # 3. Из аргументов команды резолвить target_clan (chat_id или chat-link).
    #    Альтернатива: команда работает только если бот в обоих чатах,
    #    тогда target резолвится по mention/forward.
    # 4. Вызвать start_mass_duel.execute(StartMassDuelInput(
    #        attacker_clan_chat_id=message.chat.id,
    #        defender_clan_chat_id=target_chat_id,
    #        now=clock.now(),
    #    )).
    # 5. Поймать domain-ошибки (ClanNotFoundError, MassDuelCooldownError,
    #    NoEligibleRosterError, SelfClanAttackError) → presenter.error_*.
    # 6. На успех:
    #    - presenter.started_card(...) → reply в групповой чат.
    #    - Для каждого участника обоих кланов: послать DM с
    #      presenter.prompt_attack + presenter.attack_keyboard.
    #      Использовать bot.send_message(chat_id=tg_id, ...).
```

**Важно**: handler — тонкая обёртка над use-case-ом. Все доменные проверки уже
делаются в `StartMassDuel`. Handler только парсит, форматирует, рассылает DM.

#### Callback-handler для атаки

```
async def handle_mass_attack(callback: CallbackQuery, ...) -> None:
    # 1. parse_mass_attack_callback_data(callback.data).
    # 2. Резолвить tg_id игрока через middleware/auth.
    # 3. Вызвать submit_mass_move (но в нашем случае атака — это просто
    #    сохранение state-промпта; нам нужно показать второй экран
    #    "выбор блока").
    # 4. callback.message.edit_text(presenter.prompt_block + block_keyboard).
    # 5. callback.answer() (toast).
```

> **NB:** в текущем `SubmitMassMove` UC принимает уже готовый `MassRoundChoice`
> (атака+блок). Поэтому атака+блок — это два экрана inline-кнопок, и `SubmitMassMove`
> вызывается **только после блока**. Атака просто переключает экран.

#### Callback-handler для блока

```
async def handle_mass_block(callback: CallbackQuery, ...) -> None:
    # 1. parse_mass_block_callback_data(callback.data) → duel_id, attack, position.
    # 2. Сборка MassRoundChoice(player_id=resolve_tg(...), attack=attack, block=position).
    # 3. submit_mass_move.execute(SubmitMassMoveInput(duel_id, choice, now)).
    # 4. На is_ready_to_resolve=True → resolve_mass_duel.execute(
    #        ResolveMassDuelInput(duel_id, now)).
    #    На успех — разослать всем участникам result_* DM.
    # 5. На False — callback.message.edit_text(presenter.waiting(...)).
    # 6. Поймать domain-ошибки (NotAMassDuelParticipantError,
    #    MassMoveAlreadySubmittedError, InvalidMassDuelStateError) →
    #    callback.answer(toast, show_alert=True).
```

#### Доменные ошибки (импортировать из `domain/pvp`):

```python
from pipirik_wars.domain.pvp import (
    InvalidMassDuelStateError,
    MassDuelNotFoundError,
    MassMoveAlreadySubmittedError,
    NotAMassDuelParticipantError,
)
```

И из application: `MassDuelCooldownError`, `NoEligibleRosterError` и т. д. —
поищи через `grep "class.*Error" src/pipirik_wars/application/pvp/*.py`.

### 4. DI-провязка в `bot/main.py`

В `Container`:
```python
mass_duel_presenter: MassDuelPresenter
```

В `build_container(...)`:
```python
mass_duel_presenter = MassDuelPresenter(bundle=bundle)
```

И в `Container(...)` финал — `mass_duel_presenter=mass_duel_presenter`.

В `build_dispatcher(...)` (или `bot/composition.py`):
```python
register_mass_duel_handlers(
    dp=dp,
    container=container,
    presenter=container.mass_duel_presenter,
    ...
)
```

### 5. Unit-тесты

* `tests/unit/bot/presenters/test_mass_duel.py` — каждый метод presenter-а
  (callback_data round-trip, format strings для всех ошибок, keyboards).
  Шаблон: `tests/unit/bot/presenters/test_duel.py`.
* `tests/unit/bot/handlers/test_mass_duel.py` — happy paths + error paths
  (через AsyncMock для bot и фейки use-case-ов). Шаблон: `tests/unit/bot/handlers/test_duel.py`.

Цель: **+30…40 тестов**. Coverage не должен упасть ниже 95%.

### 6. Документация

* `docs/current_tasks.md` — добавить строку про часть 2 со статусом «🔄 в работе» (потом «✅ смержено» когда PR смержат).
* `docs/history.md` — полная запись о том, что вошло.

### 7. CI и PR

```bash
make ci  # должен быть зелёным
git add -A
git commit -m "feat(pvp): mass-duel bot-handler + presenter + локали [Спринт 2.2.F часть 2]

* Локали pvp-mass-* (RU+EN).
* MassDuelPresenter с форматерами и keyboards.
* /clan_attack handler + inline callbacks атаки/блока.
* DI-провязка в bot/main.py.
* +X unit-тестов (presenter + handler).

make ci зелёный (XXXX passed, coverage XX.XX%)."
git push -u origin <branch>
```

PR template: `git_pr(action="fetch_template")`, потом `git_pr(action="create")`.
**База PR**: либо `main` (если #65 уже смержён), либо `devin/1778051724-sprint-2-2-f-mass-duel-handlers` (если #65 ещё нет).

Жди CI: `git(action="pr_checks", wait_mode="all")`. Если CI красный — фиксить
итерациями (не более 3 попыток автономно).

## Запреты

* НЕ force-push в main/master.
* НЕ коммить `.env` / секреты.
* НЕ ходи в `--no-verify` (pre-commit hooks обязательны).
* НЕ удаляй существующие тесты, чтобы пройти CI — это нарушение Code Quality.
* НЕ путай локали `duel-*` (1×1) и `pvp-mass-*` (масс-PvP).

## Полезные ссылки

* [PR #65 — часть 1](https://github.com/Pipirkawar/PipirkaWar/pull/65)
* `src/pipirik_wars/bot/presenters/duel.py` — шаблон presenter-а 1×1
* `src/pipirik_wars/bot/handlers/duel.py` — шаблон handler-а 1×1
* `src/pipirik_wars/application/pvp/start_mass_duel.py` и сосeди — use-case-ы 2.2.E с готовым `scheduler`-параметром
* `tests/unit/application/pvp/test_mass_duel_scheduler_integration.py` — пример
  use-case-теста с FakeDelayedJobScheduler

## Удаление этого файла

```bash
git rm AGENT_HANDOFF.md
git commit -m "chore: drop AGENT_HANDOFF.md after resuming work"
```

— или включить в финальный коммит спринта 2.2.F часть 2.
