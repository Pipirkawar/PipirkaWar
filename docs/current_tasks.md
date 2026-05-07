# 🍆 Пипирик Варс — Текущие задачи

> Этот файл описывает **только то, что в работе сейчас**: активная feature-ветка, активный спринт/PR, чек-лист текущих шагов и их статусы. По мере выполнения шаги отмечаются `[x]`.
>
> **С 2026-05-08:** обновления `history.md` и `current_tasks.md` под следующий PR делаются **внутри самого фичевого PR** (последним коммитом перед мерджем). Отдельный postmerge-PR больше не открывается — см. [`../CONTRIBUTING.md`](../CONTRIBUTING.md) «Перед мерджем PR-а».
>
> **Длинный план** (фазы / спринты A→Z) — в [`development_plan.md`](development_plan.md).
> **Игровая спецификация** (механики, формулы, баланс) — в [`game_design.md`](game_design.md).
> **Журнал завершённых работ** — в [`history.md`](history.md).
> **Правила работы с документацией + протокол передачи задач между агентами** — в [`../CONTRIBUTING.md`](../CONTRIBUTING.md).
>
> ⚠️ **Перед каждым коммитом** обнови чек-лист ниже (отметь готовые шаги, обнови «текущая позиция»). Это нужно для непрерывности при смене агентов — следующий агент должен знать, где ты остановился.

---

## 📸 Снимок состояния проекта

> Эта секция отражает состояние проекта **на момент последнего обновления этого файла**. Она нужна для того, чтобы новый агент за 30 секунд понял, что происходит. Обновляй её при старте/завершении каждого PR-а.

**На `main`:** последний смерженный PR — **3.1-E** (этот PR; `<коммит_слияния>`) — bot-handlers `/mountains`, `/dungeon`, презентеры, локали `mountains-*`/`dungeon-*` (RU+EN parity), Telegram-нотификаторы PvE-finish-job-ов, APScheduler factory-wiring (`mountain_finish_factory`/`dungeon_finish_factory`), DI-wiring в `bot/main.py`. Закрытие Спринта 3.1.

Перед ним: **catch-up docs 3.1-D** (PR #106, `76af44a`). Перед ним: **3.1-D** (PR #105, `2208ae6`) — дроп скроллов skeleton. Перед ним: **3.1-C** (PR #103) — дроп оружия. Перед ним: **3.1-B** (PR #101) — use-cases + persistence. Перед ним: **3.1-A** (PR #99) — каркас доменов. Перед ним: PR-ы Спринта 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов: 3.1-A → 3.1-E + catch-up #106). Domain-слой PvE (mountains/dungeon), application use-cases `Start*Run`/`Finish*Run` с idempotency и activity-lock, persistence `0018_pve_runs`, drop-engine с items_catalog (40 предметов, 8 слотов) и скроллами заточки (skeleton, без use-механики), bot UX (handlers, presenters, локали, нотификаторы), APScheduler factory-wiring готовы. Скроллы пока не persist-ятся и без кнопок применения — это Спринт 3.4.

**Активная feature-ветка:** ещё не создана. После мерджа этого 3.1-E PR-а в `main` следующий агент создаёт `devin/<unix_ts>-sprint-3-2-caravans` от свежего `main` и стартует Спринт 3.2 (Караваны).

---

## 🎯 Активный спринт — Спринт 3.2 «Караваны (полная механика)»

> Цель спринта (по [`development_plan.md`](development_plan.md) §6.3.2 «Спринт 3.2 — Караваны (полная механика)»): полная механика караванов — создание каравана, лобби с тремя ролями (караванщики/рейдеры/защитники), боевая система через атаки/блоки, награды по итогу + Атаман-роль за лидерство.

**Скоуп — 7 задач из плана:**

- **3.2.1** — Создание каравана (lvl 7+), задание вклада + клан-получателя (5 рандомных или ручной ввод). **Критерий:** Юнит-тесты на правило «после взноса ≥ 20 см».
- **3.2.2** — Лобби 20 мин, кулдаун клана 12 ч. **Критерий:** E2E с 5 караванщиками + ≤ 4× рейдеров + ≤ 2× защитников.
- **3.2.3** — Роли при двойном членстве (см. ГДД §9.4). **Критерий:** Юнит-таблица всех 5 случаев.
- **3.2.4** — Запрет рейдерства членам обоих кланов. **Критерий:** Юнит-тест.
- **3.2.5** — Боевая механика: каждый рейдер — 1 удар, караванщики — 2 блока, защитники — 1 блок. **Критерий:** Симуляция 100 караванов; распределение результатов в норме.
- **3.2.6** — Завершение: победа/проигрыш, награды (×4 лидеру, ×3 караванщикам, ×1 защитникам, +1 см клану), Атаман. **Критерий:** Все множители из `balance.yaml`.
- **3.2.7** — Идемпотентность начислений, аудит-лог. **Критерий:** Повторный обработчик не выдаёт награды дважды.

**Декомпозиция Спринта 3.2 на фичевые PR-ы (предложение, нужно валидировать первым же PR-ом — `docs-prep 3.2`):**

- **3.2-prep — Подготовка docs (необязательный отдельный PR).** Если объём 3.2 потребует декомпозиции на 4+ PR-а, имеет смысл сделать docs-prep PR (как 3.1-prep): расписать раскладку 3.2-A → 3.2-X, обновить `development_plan.md` §6.3.2+ под-секцию «Декомпозиция Спринта 3.2 на PR-ы». Если 2-3 PR-а хватит — можно начать сразу с 3.2-A.
- **3.2-A — Каркас доменов: каравана, лобби, состояний, ролей.** Domain entities `Caravan`, `CaravanLobby`, `CaravanRole` enum (`leader`/`caravaneer`/`raider`/`defender`), `CaravanStatus` enum (`PENDING`/`LOBBY`/`IN_BATTLE`/`FINISHED`/`CANCELLED`), доменные ошибки (`AlreadyInCaravanError`, `CaravanFullError`, `CaravanCooldownError`, `WrongClanRoleError`), valid-объекты `CaravanContribution(cm)`. Балансовый конфиг `caravans:` в `config/balance.yaml` (lobby_minutes=20, clan_cooldown_hours=12, min_contribution_cm=20, reward_multipliers `leader=4`/`caravaneer=3`/`defender=1`/`clan_bonus_cm=1`).
- **3.2-B — Use-cases `CreateCaravan` + `JoinCaravanLobby` + persistence + миграция.** `application/caravans/`: `CreateCaravan` (lvl 7+ gate, ≥ 20 см после контрибьюта, выбор target-клана), `JoinCaravanLobby` (по ролям, через activity-lock как у леса/PvE), `LeaveCaravanLobby`. Миграция `0019_caravans` (таблицы `caravans`, `caravan_participants`). SQLAlchemy-репо. APScheduler-job `lobby_close_finish_factory` через тот же паттерн, что mountain/dungeon (Спринт 3.1-E).
- **3.2-C — Боевая механика + завершение.** `application/caravans/StartCaravanBattle` + `FinishCaravanBattle` use-cases. Доменный сервис `caravan_battle_resolution`: каждому участнику одна-две атаки/блока согласно роли, нормализация распределения через симуляцию 100 каравaнов в тестах. Награды через ленгт-дельту + clan +1 см. Атаман-роль (см. ГДД §13.3). Идемпотентность `(caravan_id, participant_id, action)` через `IIdempotencyService`.
- **3.2-D — Bot-handlers `/caravan` + лобби UI + презентеры + локали + APScheduler factory-wiring.** По образцу 3.1-E: handler `/caravan` (lvl 7+, ≥ 20 см); inline-кнопки «вступить как X» × 3 ролей; передача роли при двойном членстве (ГДД §9.4); `CaravanPresenter`; локали `caravans-*` (RU+EN parity); `caravan_lobby_close_factory` + `caravan_battle_finish_factory` в APScheduler; DI-wiring; Manual smoke-тест в боте.

**Открытые вопросы для согласования с user-ом до старта 3.2-A:**
1. **Двойное членство (ГДД §9.4) — детальная семантика.** Игрок состоит в двух кланах. Если он создаёт караван от клана X, а целевой клан = Y, и Y — его второй клан, то ГДД говорит «он автоматически становится защитником, не караванщиком». Распространяется ли этот правило только на «целевого клан»-сценарий, или на любые случаи двойного членства? Нужны примеры все 5 случаев из таблицы — у нас её пока нет в плане.
2. **`/caravan` — где стартует?** В личке (как `/forest`/`/mountains`/`/dungeon`)? Или это команда групп-чата клана (как `/clan_head`)? ГДД §9 говорит «лобби в чате клана», но `/caravan` в личке может быть удобнее для UX. Уточнить.
3. **APScheduler — два job-а на караван?** Сейчас планируем `lobby_close_job` (закрывает лобби через 20 мин и стартует бой) + `battle_finish_job` (раунды бой 20 сек – 1 мин — несколько APScheduler-tick-ов?). Или вся бой-логика синхронная в одном callback-е? Это влияет на UX (рассылка обновлений «начался раунд X» vs «бой завершился»).
4. **«Атаман» — отдельный VO в `domain/clans/` или поле в `Player.title`?** ГДД §13.3 говорит «титул Атаман — выдаётся за лидерство в успешном караване». Если это `Title`, нужно расширить `domain/player/Title` enum. Если это agg, нужен отдельный VO.

**Финальный коммит этого 3.2-A PR-а** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.2-A: каркас доменов каравана»), пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит-слияния-3.2-A>`, расписать чек-лист 3.2-B.

---

## 📝 Чек-лист текущего PR (Спринт 3.1-E)

> Это последний PR Спринта 3.1. После его мерджа Спринт 3.1 «PvE-Expeditions» закрыт; следующий агент стартует Спринт 3.2 «Караваны».

- [x] Мердж `main = 76af44a` (catch-up docs 3.1-D, PR #106).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778186720-sprint-3-1-E-bot-handlers-and-scheduler` от `main`.
- [x] **E.1 — Notifier-порты application** `application/{mountains,dungeon}/notifier.py` (`IMountainFinishNotifier`/`IDungeonFinishNotifier`).
- [x] **E.2 — Bot-presenters + общий `_pve.py`.** `bot/presenters/{mountains,dungeon,_pve}.py`.
- [x] **E.3 — Bot-handlers** `bot/handlers/{mountains,dungeon}.py` + регистрация роутеров в `__init__.py`.
- [x] **E.4 — Telegram-нотификаторы** `bot/notifications/{mountains,dungeon,_pve}.py`.
- [x] **E.5 — Локали** `locales/{ru,en}.ftl` +60+ ключей `mountains-*`/`dungeon-*` (parity автомат через lint-тест локалей).
- [x] **E.6 — APScheduler factory-wiring** `infrastructure/scheduler/aps.py` (`__init__` + 4 опц. параметра + реальные callback-и `_run_mountain_finish_job` / `_run_dungeon_finish_job`).
- [x] **E.7 — DI-wiring** `bot/main.py` (notifier-ы + late-bound factory-и в `APSchedulerDelayedJobScheduler.__init__`).
- [x] **E.8 — Тесты unit:** `tests/unit/bot/presenters/test_pve.py` (42 теста), `tests/unit/bot/handlers/test_mountains.py` (14), `tests/unit/bot/handlers/test_dungeon.py` (14), `tests/unit/bot/notifications/test_pve.py` (9), `tests/unit/infrastructure/scheduler/test_aps.py` +12 (PvE-callback-и). **91 новый unit-тест.**
- [x] `make ci` локально: ruff ✅, mypy --strict 754 файла ✅, import-linter 3 contracts kept ✅, **pytest 3707 passed / 1 skipped, coverage 95.90%** (gate 80%).
- [x] **E.9 — Финальный док-коммит:** `history.md` +запись 3.1-E (закрытие Спринта 3.1), `current_tasks.md` пересборка под старт **Спринта 3.2 (Караваны)**.
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Текущий PR — 3.1-E (закрытие Спринта 3.1):**
- 24 файла изменено, +3055 / −14 строк (excl. docs).
- **Application-слой:** добавлены notifier-порты `IMountainFinishNotifier`/`IDungeonFinishNotifier` (только Protocol, без реализаций).
- **Bot-слой:** новые модули `bot/presenters/{_pve,mountains,dungeon}.py`, `bot/handlers/{mountains,dungeon}.py`, `bot/notifications/{_pve,mountains,dungeon}.py`, register_routers расширен.
- **Infrastructure-слой:** `infrastructure/scheduler/aps.py` — `__init__` принимает 4 новых опциональных параметра; добавлены полноценные callback-и `_run_mountain_finish_job` / `_run_dungeon_finish_job` (зеркалят forest-callback).
- **`bot/main.py`:** DI-wiring — notifier-ы создаются если `bot is not None`; late-bound factory-и в `APSchedulerDelayedJobScheduler.__init__`.
- **Локали:** `locales/{ru,en}.ftl` +60+ ключей `mountains-*`/`dungeon-*` (parity автомат).
- **Тесты:** 91 новый unit-тест.
- **Скроллы в UX:** нейтральный дисплей в карточке возврата (ключ `*-finished-scroll-line`), без кнопок применения. Не persist-ятся (3.4).

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Скроллы не persist-ятся в Спринте 3.1.** Это **дизайн-решение** (см. 3.1-D), не блокер. Полная механика `EnchantItem` use-case + `scroll_inventory` таблица + UI применения — Спринт **3.4**. До 3.4 скроллы в горах/данжоне логируются и отображаются в карточке возврата нейтральным текстом, но не попадают в инвентарь.
- **Нет integration-тестов для handler-ов через `aiogram-test-helpers`.** В Спринте 3.1-E ограничились unit-тестами (handler-ы вызываются напрямую с замоканными dependencies). Это покрывает все ветки логики и достаточно для CI gate-а 80%. Если в Спринте 3.2 (Караваны) появится сложный inline-flow с многошаговым state-управлением, нужно будет завести `aiogram-test-helpers` зависимость и переделать handler-тесты на полноценные dispatcher-flow-тесты.
- **Manual smoke-тест в боте не выполнен.** В Спринте 3.1-E unit-тестов оказалось достаточно для CI gate-а; manual smoke-тест (`/mountains` → ждать cooldown → дождаться finish-job → получить карточку возврата) можно выполнить **после мерджа** при первом продакшен-деплое. Если до деплоя нужен smoke-тест на staging, это отдельная задача.
