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

**На `main`:** последний смерженный PR — **3.5-D** (PR #125, `ba0b769`) — bot-UI free-to-play рулетки: команда `/roulette_free` (личка-only) + pre-spin gate (warning `roulette-free-warn-thickness` при `thickness_level < 2`, `roulette-free-warn-length` при `length_cm < 100`) + spin-кнопка → callback `roulette_free:spin` → 3-кадровая анимация-крутилка (`asyncio.sleep(1.0)` × 3 + `bot.edit_message_text` с best-effort `contextlib.suppress(TelegramAPIError)`) → result-card по `RouletteOutcomeKind` (LENGTH × 4 buckets `small[10..50]/medium[50..150]/good[150..300]/big[300..500]` + ITEM/SCROLL_REGULAR/SCROLL_BLESSED/CRYPTO_LOT). `RoulettePresenter` (`bot/presenters/roulette.py`, ~115 строк) — locale-driven рендер всех карточек. Локали `roulette-free-*` (~50 ключей × RU+EN parity). DI: `Container.spin_free_roulette` + `roulette_router` зарегистрирован в `bot/handlers/__init__.py`. 24 unit-теста handler-а + 18 snapshot-тестов presenter-а. **Закрывает Спринт 3.5 «Free-to-play рулетка»**. Перед ним: **fix(load-tests)** (PR #124, `4baca4b`) — `poolclass=NullPool` в `tests/integration/load/conftest.py::shared_engine` (test-only фикс flaky-падения `test_100_parallel_grants_for_same_player_respect_daily_cap` на py3.11; не относится к скоупу Спринта 3.5). **3.5-C** (PR #123, `7085e51`) — application use-case `SpinFreeRoulette` с 8-шаговым flow + audit `ROULETTE_SPIN` + `AuditSource.ROULETTE_FREE_{COST,REWARD}` (миграция `0024_audit_source_roulette_free`); 13 unit + 7 integration-тестов. **3.5-B** (PR #122, `3505e83`) — persistence-слой (`IRouletteSpinRepository` + ORM + миграция `0023_roulette_spins`). **3.5-A** (PR #121, `792a366`) — каркас домена + балансовый конфиг. Перед ними: **3.4-D** (PR #120, `9ebbf15`); **3.4-C** (PR #119, `e490095`); **3.4-B** (PR #118, `7259fad`); **3.4-A** (PR #117, `5c21d4e`). **Закрыты Спринты 3.1 «PvE-Expeditions»**, **3.2 «Караваны»**, **3.3 «Рейд-боссы»**, **3.4 «Заточка предметов»**, **3.5 «Free-to-play рулетка»**. **В работе Спринт 3.6 «Бонус-за-племена в Предсказателе»** ([`development_plan.md`](development_plan.md) §6.3.6, ГДД §11.1) — активный PR **3.6-A** «Доменный запрос + конфиг + use-case + anti-cheat» (domain-side, без UI).

**Текущая ветка** — `devin/1778391635-sprint-3-6-A-tribe-bonus-domain` (от свежего `main = ba0b769` после мерджа PR #125) под **Спринт 3.6-A «Доменный запрос + конфиг + use-case + anti-cheat»**.

Перед `3.5-D` (PR #125, `ba0b769`): **fix(load-tests)** (PR #124, `4baca4b`); **3.5-C** (PR #123, `7085e51`); **3.5-B** (PR #122, `3505e83`); **3.5-A** (PR #121, `792a366`); **3.4-D** (PR #120, `9ebbf15`); **3.4-C** (PR #119, `e490095`); **3.4-B** (PR #118, `7259fad`); **3.4-A** (PR #117, `5c21d4e`); **3.6 design doc** (PR #116, `f7d671f`); **3.3-D** (PR #115, `5d6c9a3`); **3.3-C** (PR #114, `d08985e`); **3.3-B** (PR #113, `9c859b7`), **3.3-A** (PR #112, `dbb9b1c`); **3.2-A→D** (#108–#111); **3.1-E** (PR #107, `5c1b26f`) и PR-ы Спринтов 3.1 (#99–#106) и 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а). **Закрыт Спринт 3.3 «Рейд-боссы»** (4 PR-а). **Закрыт Спринт 3.4 «Заточка предметов»** (4 PR-а: 3.4-A/B/C/D). **Закрыт Спринт 3.5 «Free-to-play рулетка»** (4 PR-а: 3.5-A/B/C/D). **В работе Спринт 3.6 «Бонус-за-племена в Предсказателе»** ([`development_plan.md`](development_plan.md) §6.3.6) — активный PR **3.6-A**.

**Roadmap (после Спринта 3.6 → далее):**
- **Спринт 3.6 «Бонус-за-племена в Предсказателе»** 🎯 ([`development_plan.md`](development_plan.md) §6.3.6, ГДД §11.1) — **активный**, 1–2 PR-а: 3.6-A (domain + config + use-case + anti-cheat — **активный**) → 3.6-B (bot UI + локали + закрытие).
- **Фаза 4 «Монетизация и масштаб»** ([`development_plan.md`](development_plan.md) §7) — после Спринта 3.6. Telegram Stars + TON Connect + USDT + крипто-приз в рулетке + лот-генератор + админ-команды (`/prize_pool`, `/refund_lot`, `/freeze_payouts`).

---

## 🎯 Активный спринт — Спринт 3.6 «Бонус-за-племена в Предсказателе» 🎯

> Цель спринта (по [`development_plan.md`](development_plan.md) §6.3.6 «Спринт 3.6 — Бонус-за-племена в Предсказателе», ГДД §11.1 «Бонус за племена»): виральная мини-механика — расширение `/predict`. За каждое **активное** племя, в котором состоит игрок, начисляется `+1 см` к базовому `uniform(1, 20)`. Cap = `+131 см` за вызов (итого `/predict` ≤ `+151 см` вместе с базой). Активным считается племя со `status="active"`, **числом участников `> 3`**, где игрок — член. Anti-cheat: **отдельный лимит** (`source = "oracle_tribe_bonus"` НЕ входит в organic 24h/7d). Display: явная строка `+N см за племена` в результате `/predict`. Снапшот — **live** в момент вызова `/predict`.

**Скоуп — задачи плана 3.6.* (детали — в [`development_plan.md`](development_plan.md) §6.3.6):**

- Domain: `IClanRepository.count_active_for_player(player_id, *, min_tribe_size: int) -> int` (или симметричный сервис в `application/clan/services/`). Активное племя = `status='active'`, members > min_tribe_size, игрок — член.
- Config: pydantic `OracleTribeBonusConfig` с полями `enabled: bool`, `cm_per_tribe: int >= 0`, `cap_cm: int >= 0`, `min_tribe_size: int >= 1`. Дефолты: `enabled=true`, `cm_per_tribe=1`, `cap_cm=131`, `min_tribe_size=4`.
- Application: расширение use-case `RequestOracle` — после рандома `uniform(bonus_min, bonus_max)` считаем `n_active_tribes`, прибавляем `min(n_active_tribes * cm_per_tribe, cap_cm)`. **Две** проводки `add_length(...)`: `oracle_base` (source=`oracle`) + `oracle_tribe_bonus` (source=`oracle_tribe_bonus`). Один idempotency-key `oracle:{player_id}:{moscow_date}`.
- Anti-cheat: `oracle_tribe_bonus` в **новый** whitelist `tribe_bonus_sources` в `balance.yaml::anticheat`; `IAnticheatChecker` игнорирует эти источники при rolling-окне.
- Bot UI (3.6-B, не входит в 3.6-A): `OraclePresenter` — две строки прироста + локали с Fluent-плюрал-формами.

**Декомпозиция Спринта 3.6 на фичевые PR-ы:**

- **3.6-A — Доменный запрос + конфиг + use-case + anti-cheat (активный).** `IClanRepository.count_active_for_player`, pydantic `OracleTribeBonusConfig`, расширение `RequestOracle` use-case-а (две проводки `add_length`), `tribe_bonus_sources` в `balance.yaml` + `IAnticheatChecker`. Юнит + integration-тесты. **Без** UI-изменений. Покрывает задачи 3.6.1, 3.6.2, 3.6.3, 3.6.4.
- **3.6-B — Bot UI + локали + закрытие Спринта 3.6.** Расширение `OraclePresenter` строками `+N за племена`, локали RU+EN с Fluent-плюрал-формами, snapshot-тесты, manual smoke + финальный док-коммит. Покрывает задачи 3.6.5, 3.6.6, 3.6.7, 3.6.8.

**Финальный коммит каждого PR-а Спринта 3.6** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.6-X: ...») + пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит_слияния>`, передвинуть чек-лист на следующий PR (или закрыть Спринт 3.6 на 3.6-B и расписать чек-лист **первого PR-а Фазы 4** «Монетизация и масштаб»).

---

## 📝 Чек-лист следующего PR (Спринт 3.6-A — Доменный запрос + конфиг + use-case + anti-cheat)

> Этот PR — первый PR Спринта 3.6. Расширяет `/predict` на бонус-за-племена: новый доменный запрос `IClanRepository.count_active_for_player`, pydantic `OracleTribeBonusConfig`, расширение application use-case `RequestOracle` (две проводки `add_length`: `oracle_base` + `oracle_tribe_bonus`), интеграция в `IAnticheatChecker` через новый whitelist `tribe_bonus_sources` (источник НЕ идёт в organic 24h/7d). **Без** UI-изменений — UI делается отдельным PR-ом 3.6-B.

- [x] Дождаться мерджа `3.5-D` в `main` (PR #125, `ba0b769`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778391635-sprint-3-6-A-tribe-bonus-domain` от свежего `main = ba0b769`.
- [x] **A.0 — Обновить `current_tasks.md`** под старт Спринта 3.6-A: пересобрать «Снимок состояния» под актуальный `main = ba0b769`, расписать чек-лист 3.6-A, заархивировать чек-лист 3.5-D (этот коммит — Checkpoint 1).
- [ ] **A.1 — Доменный запрос `count_active_for_player`** (`domain/clan/ports.py` + SQL impl):
  - Метод `IClanRepository.count_active_for_player(player_id: int, *, min_tribe_size: int) -> int` — возвращает количество активных племён, в которых состоит игрок.
  - Активное племя: `status='active'` (не `frozen`/`archived`), `len(members) > min_tribe_size`, игрок есть в `members`.
  - SQL impl: `SELECT COUNT(*) FROM clans c JOIN clan_members cm ON cm.clan_id=c.id WHERE cm.player_id=:player_id AND c.status='active' GROUP BY c.id HAVING COUNT(cm.id) > :min_tribe_size` (или эквивалент через subquery).
  - **Критерий:** `mypy --strict` 0 issues; юнит-тесты на каждый gate (frozen → 0; size=3 при min=4 → 0; size=4 → +1; not_member → 0; bot-only-member → 0); 1 integration-тест `tests/integration/db/test_clan_repository.py`.
- [ ] **A.2 — pydantic `OracleTribeBonusConfig`** (`domain/balance/config.py`):
  - Поля: `enabled: bool` (default `true`), `cm_per_tribe: int >= 0` (default `1`), `cap_cm: int >= 0` (default `131`), `min_tribe_size: int >= 1` (default `4`). `extra="forbid"`.
  - Добавить `tribe_bonus: OracleTribeBonusConfig = Field(default_factory=OracleTribeBonusConfig)` в `OracleConfig`.
  - Sanity-check: `cap_cm + bonus_max <= 151` (мягкий warning в логе при загрузке).
  - Дефолты в `config/balance.yaml::oracle.tribe_bonus`.
  - **Критерий:** юнит-тесты pydantic-валидаторов; integration-тест парсинга дефолтного `balance.yaml`.
- [ ] **A.3 — Расширение use-case `RequestOracle`** (`application/oracle/request_oracle.py`):
  - После `length_grant = uniform(bonus_min, bonus_max)` — если `cfg.tribe_bonus.enabled`, считаем `n_active = clan_repo.count_active_for_player(player_id, min_tribe_size=cfg.tribe_bonus.min_tribe_size)`, далее `tribe_bonus = min(n_active * cfg.tribe_bonus.cm_per_tribe, cfg.tribe_bonus.cap_cm)`.
  - **Две** проводки `add_length` внутри одного idempotency-key `oracle:{player_id}:{moscow_date}` и одной транзакции:
    - `add_length(delta=+length_grant, reason="oracle_base", source=AuditSource.ORACLE, idempotency_key="add_length:{root}:base")`;
    - `add_length(delta=+tribe_bonus, reason="oracle_tribe_bonus", source=AuditSource.ORACLE_TRIBE_BONUS, idempotency_key="add_length:{root}:tribe_bonus")` (если `tribe_bonus > 0`).
  - DTO `OraclePredictionResult` — расширить полями `base_cm: int` + `tribe_bonus_cm: int` + `n_active_tribes: int` (для presenter-а 3.6-B).
  - **Критерий:** юнит-тесты — 0 племён → нет второй проводки; 5 племён → +5 см второй проводкой; 200 племён → +131 см (cap); idempotency повторного вызова за те же сутки → не дублирует ни одну проводку.
- [ ] **A.4 — Anti-cheat `tribe_bonus_sources`**:
  - Новый `AuditSource.ORACLE_TRIBE_BONUS = "oracle_tribe_bonus"` в `domain/shared/ports/audit.py`.
  - Миграция Alembic `0025_audit_source_oracle_tribe_bonus` — расширение CHECK constraint `audit_log_source_whitelist` на `'oracle_tribe_bonus'`. Зеркало в ORM `AuditLogORM.audit_log_source_whitelist` (`infrastructure/db/models/security.py`).
  - В `balance.yaml::anticheat` — новое поле `tribe_bonus_sources: [oracle_tribe_bonus]` (рядом с `organic_sources`). Pydantic-схема `AnticheatConfig` — добавить поле.
  - `IAnticheatChecker` (`application/anticheat/services/length_change_recorder.py` или эквивалент): при агрегации rolling-окна источники из `tribe_bonus_sources` игнорировать (не попадают в organic-сумму).
  - **Критерий:** integration-тест: `5 × /predict с +131 см бонуса` подряд = `+655 см «в обход» хардкапа` за час → trip-wire `ANTICHEAT_DAILY_CAP_EXCEEDED` **не** срабатывает; audit-проводки с правильным `source`.
- [ ] **A.5 — `make ci` локально:** ruff + mypy --strict + import-linter (4 contracts kept) + pytest зелёный + coverage gate (≥ 80%).
- [ ] **A.6 — Финальный док-коммит:** `history.md` + запись 3.6-A, `current_tasks.md` пересборка под старт **Спринта 3.6-B «Bot UI + локали + закрытие Спринта 3.6»**.
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 📦 Архив чек-листа (Спринт 3.5-D — Bot UI + локали + display + закрытие Спринта 3.5) ✅

> Этот PR закрыт, чек-лист сохранён для истории.

- [x] Дождаться мерджа `3.5-C` в `main` (PR #123, `7085e51`).
- [x] `git fetch && git checkout main && git pull` (после PR #124 fix-flaky → `main = 4baca4b`).
- [x] Создать ветку `devin/1778361483-sprint-3-5-D-roulette-bot-ui` от свежего `main = 4baca4b`.
- [x] **D.0 — Обновить `current_tasks.md`** под старт Спринта 3.5-D: пересобрать «Снимок состояния» под актуальный `main = 4baca4b`, расписать чек-лист 3.5-D, заархивировать чек-лист 3.5-C. Коммит `61bdbdd`.
- [x] **D.1 — Bot-handler `/roulette_free`** (`bot/handlers/roulette.py`, ~280 строк): команда `/roulette_free` (личка-only) + pre-spin gate (warning при `thickness_level < 2` / `length_cm < 100`) + spin-кнопка → callback `roulette_free:spin` → 3-кадровая анимация-крутилка (`asyncio.sleep(1.0)` × 3 + `bot.edit_message_text` с best-effort `contextlib.suppress(TelegramAPIError)`) → result-card. `idempotency_key = f"roulette_free:{tg_user_id}:{ts_ns()}"` (per-press). 24 unit-теста в `tests/unit/bot/handlers/test_roulette.py`. Коммиты `d8dca20` (handler) + `eb8b343` (24 unit-теста).
- [x] **D.2 — Локали `roulette-free-*`** (`locales/ru.ftl` + `locales/en.ftl`, ~50 ключей × RU+EN): intro, warnings (thickness/length), spin-prompt + spin-button, anim-frame × 3, result-cards (LENGTH × 4 buckets + ITEM/SCROLL_REGULAR/SCROLL_BLESSED/CRYPTO_LOT), toast-errors (5). Locale-parity-тест зелёный. Коммит `a7d650a` (вместе с D.3).
- [x] **D.3 — `RoulettePresenter`** (`bot/presenters/roulette.py`, ~115 строк): locale-driven рендер всех роулетка-карточек; маппинг `SpinResult` → result-card (switch по `outcome.kind` для не-LENGTH; для LENGTH — bucket по `length_cm`). 18 snapshot-тестов RU/EN parity. Коммит `a7d650a`.
- [x] **D.4 — DI-провязка** в `bot/main.py` + `bot/handlers/__init__.py` + `bot/presenters/__init__.py`: `Container.spin_free_roulette` создаётся через реальный `SpinFreeRoulette` в `build_container(...)`; `roulette_router` зарегистрирован в dispatcher; `RoulettePresenter` экспортирован. 5 composition-тестов в `tests/unit/bot/test_composition_root.py`. Коммит `c4a7289`.
- [x] **D.5 — `make ci` локально:** ruff + mypy --strict + import-linter (4 contracts kept) + pytest зелёный + coverage gate (≥ 80%) — **5132 passed / 2 skipped, coverage 95.63%** на `c4a7289`. Коммит `9914997`.
- [x] **D.6 — Финальный док-коммит:** `history.md` (запись 3.5-D) + `current_tasks.md` пересборка под старт **Спринта 3.6-A «Доменный запрос + конфиг + use-case + anti-cheat»** (этот коммит).
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md` — PR #125.
- [ ] Дождаться зелёного GitHub CI.

---

## 📦 Архив чек-листа (Спринт 3.5-C — Application use-case `SpinFreeRoulette` + audit + spend-100см) ✅

> Этот PR закрыт, чек-лист сохранён для истории.

- [x] Дождаться мерджа `3.5-B` в `main` (PR #122, `3505e83`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778350327-sprint-3-5-C-roulette-use-case` от свежего `main = 3505e83`.
- [x] PR #123 → merged → `7085e51`. После merge на main отдельным PR #124 поверх (`4baca4b`) — test-only NullPool-fix flaky load-теста (вне скоупа 3.5-C).
- [x] **C.0 — Обновить `current_tasks.md`** под старт Спринта 3.5-C: пересобрать «Снимок состояния» под актуальный `main`, расписать чек-лист 3.5-C. Коммит `902119e`.
- [x] **C.1 — Audit-action `ROULETTE_SPIN` + `AuditSource.ROULETTE_FREE_{COST,REWARD}` + миграция `0024_audit_source_roulette_free`**: добавлены в `domain/shared/ports/audit.py`; миграция расширяет CHECK whitelist `audit_log_source_whitelist`; обновлён parity-тест `test_audit_source.py`. Коммит `478d242`.
- [x] **C.2 — Application use-case `SpinFreeRoulette`** (`application/roulette/spin_free_roulette.py`, ~340 строк): DTO `SpinFreeRouletteCommand` + `SpinResult`; 8-шаговый flow (idempotency → load → thickness-gate → length-check → spend-100 → pick-outcome → record-spin → audit → mark-idempotency); domain-errors `RouletteThicknessGateError` / `InsufficientLengthForRouletteError`; для LENGTH-исхода — дополнительный `add_length(delta=+roll, source=ROULETTE_FREE_REWARD)`. 13 unit-тестов. Коммит `6330100` (checkpoint #1).
- [x] **C.3 — Integration-тесты use-case** (`tests/integration/db/test_spin_free_roulette_use_case.py`, ~440 строк, 7 тестов): real-DB round-trip для LENGTH-исхода (3 audit-записи: cost + ROULETTE_SPIN + reward); 3 параметризованных не-LENGTH (ITEM/SCROLL_REGULAR/SCROLL_BLESSED, 2 audit-записи); idempotent replay (тот же `idempotency_key` → no-op); gate-fail × 2 (thickness < 2, length < 100) без DB-записей. Bug fix: `AuditLogORM.audit_log_source_whitelist` (`infrastructure/db/models/security.py`) синхронизирован с миграцией 0024. Коммит `2c24ad7` (checkpoint #2).
- [x] **C.4 — `make ci` локально:** ruff (clean), `mypy --strict` (0 issues, 891 source files), import-linter (4 contracts KEPT), pytest unit **4529 passed / 2 skipped** (5017 baseline 3.5-B → +13 unit-тестов SpinFreeRoulette − дедупликация length_grant_guard whitelist), integration db/admin/balance/i18n/templates/application **515 passed**. Load-тесты `tests/integration/load/` flaky при параллельном прогоне (известный flake из 3.5-B), not related to 3.5-C.
- [x] **C.5 — Финальный док-коммит:** `history.md` (запись 3.5-C) + `current_tasks.md` пересборка под старт **Спринта 3.5-D «Bot UI + локали + display + закрытие Спринта 3.5»**.
- [x] Открыть PR в `main` по шаблону `.github/pull_request_template.md` — PR #123.
- [x] Дождаться зелёного GitHub CI — PR #123 смержен в `7085e51`.

---

## 📦 Архив чек-листа (Спринт 3.5-B — Persistence-слой рулетки) ✅

> Этот PR закрыт, чек-лист сохранён для истории.

- [x] Дождаться мерджа `3.5-A` в `main` (PR #121, `792a366`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778347640-sprint-3-5-B-roulette-persistence` от свежего `main = 792a366`.
- [x] **B.0 — Обновить `current_tasks.md`** под старт Спринта 3.5-B: пересобрать «Снимок состояния» под актуальный `main`, расписать чек-лист 3.5-B.
- [x] **B.1 — Доменный порт `IRouletteSpinRepository` + `RouletteSpin` entity** (`domain/roulette/ports.py` + `domain/roulette/entities.py`): Protocol с `record(*, spin)` + `last_free_spin_at(*, player_id)`; entity с TZ-aware `occurred_at`, `__post_init__`-валидация (`player_id > 0`, TZ-aware, non-empty key), convenience-properties `.kind`/`.length_cm`. 11 unit-тестов в `test_entities.py`. Закоммичено в `9d67af2` (checkpoint #1).
- [x] **B.2 — ORM `RouletteSpinORM` + миграция `0023_roulette_spins`**: ORM с `id BIGINT PK autoincrement`, `player_id` FK→users.id CASCADE, `occurred_at TIMESTAMPTZ`, `kind VARCHAR(32)`, `length_cm INT NULL`, `idempotency_key VARCHAR(128) UNIQUE`; CheckConstraint `(kind='length' AND length_cm IS NOT NULL) OR (kind != 'length' AND length_cm IS NULL)`; composite-индекс `(player_id, occurred_at)`. Миграция `down_revision="0022_scrolls"`. Зарегистрирована в `models/__init__.py` + `tests/integration/db/conftest.py`. Закоммичено в `e2b28ec` (checkpoint #2).
- [x] **B.3 — `SqlAlchemyRouletteSpinRepository`**: dialect-specific `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING` через `pg_insert` / `sqlite_insert`; `last_free_spin_at` через `SELECT MAX(occurred_at) WHERE player_id=:p`. Зарегистрировано в `repositories/__init__.py`. Закоммичено в `e2b28ec` (checkpoint #2).
- [x] **B.4 — Integration-тесты** (15 тестов в `test_roulette_spin_repository.py`): round-trip для всех 5 `RouletteOutcomeKind`, idempotency (повтор + DO NOTHING semantics), isolation (per-player), DB-CHECK invariants (отказ на нарушении `kind ↔ length_cm`). Также обновлён `test_migrations.py` (chain-test 0023, dir-list, table-structure). Закоммичено в `e2b28ec` (checkpoint #2) + `13a1b58` (test_migrations.py).
- [x] **B.5 — `make ci` локально:** ruff (clean), `mypy --strict` (0 issues), import-linter (4 contracts KEPT), pytest **5017 passed / 2 skipped** (4988 baseline 3.5-A → +29 новых тестов: 11 entity + 15 repo + 3 migration), **coverage 95.56%** (gate ≥ 80%). Load-тесты flaky при параллельном прогоне в `make ci`, проходят при изолированном запуске; not related to 3.5-B changes.
- [x] **B.6 — Финальный док-коммит:** `history.md` (запись 3.5-B) + `current_tasks.md` пересборка под старт **Спринта 3.5-C «Application use-case `SpinFreeRoulette` + audit + spend-100см»**.
- [x] Открыть PR в `main` по шаблону `.github/pull_request_template.md` — PR #122.
- [x] Дождаться зелёного GitHub CI — PR #122 смержен в `3505e83`.

---

## 📦 Архив чек-листа (Спринт 3.5-A — Каркас домена «Рулетка» + балансовый конфиг) ✅

> Этот PR закрыт, чек-лист сохранён для истории.

- [x] Дождаться мерджа `3.4-D` в `main` (PR #120, `9ebbf15`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778345019-sprint-3-5-A-roulette-domain` от `main = 9ebbf15`.
- [x] **A.0 — Обновить `current_tasks.md`** под старт Спринта 3.5-A.
- [x] **A.1 — Доменный пакет `domain/roulette/`**: `entities.py` (`RouletteOutcomeKind` ре-экспорт + `RouletteOutcome` frozen-VO с инвариантом `kind ↔ length_cm`); `services.py` (pure picker `pick_roulette_outcome(*, config, random, crypto_pool_empty)` с двухуровневым weighted_choice + crypto-pool-drain percolation rule); `errors.py` (`RouletteDomainError` + `InvalidRouletteConfigError`); `__init__.py` (экспорт публичных символов). Коммит `7757a6a`.
- [x] **A.2 — Балансовый конфиг `RouletteFreeConfig`** (`domain/balance/config.py`): `RouletteOutcomeKind` (StrEnum, единое место хранения); `RouletteOutcomeWeight` + `RouletteLengthBucket` + `RouletteFreeConfig` + `RouletteConfig` pydantic-модели с 5 валидаторами (outcome-веса в Σ=1.0±ε, уникальность kind, полнота 5-ти kind, bucket-веса в Σ=1.0±ε, уникальность имён бакетов) + `RouletteLengthBucket.min_cm <= max_cm`-валидатор + `extra="forbid"`. Поле `BalanceConfig.roulette: RouletteConfig`. Дефолты в `config/balance.yaml` (5 outcomes + 4 length_buckets из ГДД §12.4.2). Коммит `7757a6a`.
- [x] **A.3 — Юнит-тесты picker-а + integration-тест парсинга `balance.yaml`**: 47 новых тестов — 11 entity-инвариантов (`tests/unit/domain/roulette/test_entities.py`); 14 picker-сценариев (`tests/unit/domain/roulette/test_picker.py`) с Bernoulli-распределениями на 10 000 ролов с 3σ-границами + crypto-pool drain percolation; 18 config-валидатор-тестов + 4 `BalanceConfig` integration-тестов (`tests/unit/domain/balance/test_roulette_config.py`); обновлены `tests/unit/domain/balance/factories.py` для подхвата дефолтного `roulette`-блока. Коммит `0dc408a` (включая mypy-фиксы test_roulette_config.py + удаление неиспользуемого `# type: ignore[misc]` в test_entities.py).
- [x] **A.4 — `make ci` локально:** ruff (clean), `mypy --strict` (0 issues, 882 source files), import-linter (4 contracts KEPT), pytest **4988 passed / 2 skipped** (4941 baseline 3.4-D → +47 новых тестов), **coverage 95.56%** (gate ≥ 80%).
- [x] **A.5 — Финальный док-коммит:** `history.md` (запись 3.5-A) + `current_tasks.md` пересборка под старт **Спринта 3.5-B «Persistence-слой рулетки»** (этот коммит).
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 📦 Архив чек-листа (Спринт 3.4-D — Bot UI заточки + локали + display + закрытие Спринта 3.4) ✅

> Этот PR закрыт, чек-лист сохранён для истории.

- [x] Дождаться мерджа `3.4-C` в `main` (PR #119, `e490095`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778323886-sprint-3-4-D-enchant-bot-ui` от `main = e490095`.
- [x] **D.0 — Обновить `current_tasks.md`** под старт Спринта 3.4-D (Вариант A: добавлены D.½, D.1a-D.1d). Коммит `3c09d0e`.
- [x] **D.½ — Расширить порты инвентаря**: `IItemRepository.list_by_player` + `IScrollRepository.list_by_player` + `ScrollStack` DTO. Коммит `d78e100`.
- [x] **D.1a — Application use-case `GetInventory(player_id) → InventoryView`** + `ItemView`/`ScrollView` DTO. Коммит `5f0312d`.
- [x] **fix(3.4-D)** — реализация `list_by_player` в InMemory-fakes + удаление 4 неиспользуемых `# type: ignore[misc]`. Коммит `0f2ac00`.
- [x] **D.1b — Bot-handler `/inventory` + `InventoryPresenter`** + хелпер `enchant_suffix(level)` + snapshot-тесты RU/EN. Коммит `740e61e`.
- [x] **D.1c — Bot-handler `/enchant <item_id> <scroll_id>` + `EnchantPresenter`** + warning/result-карточки + handler-тесты + snapshot-тесты RU/EN. Коммиты `f3f7972` + `4cf503a`.
- [x] **D.1d — Inline-кнопка «Заточить»** в карточке `/inventory` + picker (0/1/2 скролла) + handler-тесты. Коммит `5b77f06`.
- [x] **D.2 — Локали `enchant-*` + `inventory-*`** (~40 ключей × RU/EN). Коммит `5f0312d`.
- [x] **D.3 — Display `+N`** — реализовано через хелпер `enchant_suffix(level)` в `/inventory` (D.1b) + `/enchant` warning/result (D.1c). `/profile` Equipment skeleton (отложено до Спринта 1.3+); forest/PvE/dungeon-`Item` не имеют `enchant_level` (всегда дроп `level=0`); audit-лог в TG не отображается. Все актуальные display-точки покрыты.
- [x] **D.4 — Composition root**: `EnchantItem` + `GetInventory` + `SqlAlchemyEnchantHistoryReader` зарегистрированы в `bot/main.py` + composition-тесты. Коммит `225987c`.
- [x] **D.5 — Handler-тесты** — покрыто в `test_enchant.py` (D.1c): параметризованный `test_use_case_domain_error_maps_to_toast` по 5 ошибкам (`ItemNotFoundError`/`WrongScrollCategoryError`/`ScrollNotFoundError`/`ScrollOutOfStockError` + `ValueError`).
- [x] **D.6 — Кнопка «Заточить»** — реализована в D.1d.
- [x] **D.7 — e2e snapshot-тесты** — покрыто в `test_inventory.py` + `test_enchant.py` презентер-тестах (D.1b + D.1c) RU/EN parity.
- [x] **D.8 — `make ci` локально зелёный**: 4941 passed / 2 skipped, coverage 95.59%, mypy --strict 0 issues, import-linter 4 contracts KEPT.
- [x] **D.9 — Финальный док-коммит:** `history.md` (запись 3.4-D) + `current_tasks.md` пересборка под старт Спринта 3.5 (этот коммит).
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 📦 Архив чек-листа (Спринт 3.4-C — Application use-case `EnchantItem` + audit + анти-чит trip-wire + `ScrollORM`) ✅

> Этот PR закрыт, чек-лист сохранён для истории.

- [x] Дождаться мерджа `3.4-B` в `main` (PR #118, `7259fad`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778313165-sprint-3-4-C-enchant-use-case` от `main`.
- [x] **C.0 — Обновить `current_tasks.md`** под старт Спринта 3.4-C.
- [x] **C.1 — Доменный VO `Scroll`** расширен проперти `scroll_id` + classmethod `from_scroll_id`; `IScrollRepository(Protocol)` с `get`/`consume(qty)`/`add`; `ScrollNotFoundError` + `ScrollOutOfStockError`; `IItemRepository.delete` (для DESTROY-исхода).
- [x] **C.2 — ORM `ScrollORM` + миграция `0022_scrolls`** (composite PK `(player_id, scroll_id)`, `qty INT NOT NULL CHECK qty >= 0`, `acquired_at TIMESTAMPTZ`).
- [x] **C.3 — `SqlAlchemyScrollRepository`** (get/consume/add) + 22 integration-теста (round-trip 6 вариантов, stacking, изоляция, error кейсы).
- [x] **C.4 — `AuditAction.ITEM_ENCHANT_ATTEMPT` + `AuditAction.ENCHANT_ANOMALY`** в `domain/shared/ports/audit.py` (без новых `AuditSource`).
- [x] **C.5 — Application use-case `EnchantItem`** (`application/inventory/enchant_item.py`) с 10-шаговым flow: idempotency check (namespace `enchant`) → load Item → parse `Scroll.from_scroll_id` → `matches_scroll`-check → consume scroll qty=1 → `pick_enchant_outcome` → apply outcome (update_enchant_level / delete) → audit `ITEM_ENCHANT_ATTEMPT` → mark idempotency → trip-wire. DTO `EnchantAttemptResult` (outcome, old_level, new_level, item_destroyed, item_dropped, idempotent, anomaly_detected). Доменный порт `IEnchantHistoryReader` + SQL-impl `SqlAlchemyEnchantHistoryReader` (читает `audit_log` с JSON-фильтрацией в Python для портабельности SQLite/PG).
- [x] **C.6 — Trip-wire `ENCHANT_ANOMALY`** интегрирован в `EnchantItem`: после успеха на тире `old_level ∈ [18, 25]` читаем последние 10 high-tier outcomes через `IEnchantHistoryReader`; все 10 — успехи → пишем `ENCHANT_ANOMALY`.
- [x] **C.7 — 25 unit-тестов `EnchantItem`** (`tests/unit/application/inventory/test_enchant_item.py`): 2 safe-zone успеха + 4 regular outcomes + 4 blessed non-trivial outcomes + 5 error кейсов + 2 idempotency + 1 audit-payload + 6 trip-wire сценариев + 1 ambient-UoW guard + 1 clamp. + 4 integration-теста через realDB (`tests/integration/db/test_enchant_item_use_case.py`): round-trip success, destroy-исход, idempotency через realDB, trip-wire после 10 засеянных audit-записей.
- [x] **C.8 — `make ci` локально:** ruff + mypy --strict (864 source files) + import-linter (4 contracts KEPT) + pytest **4762 passed / 2 skipped**, coverage **96%**.
- [x] **C.9 — Финальный док-коммит:** `history.md` + запись 3.4-C (этот коммит), `current_tasks.md` пересборка под старт Спринта 3.4-D.
- [x] Открыть PR в `main` по шаблону `.github/pull_request_template.md`.
- [x] Дождаться зелёного GitHub CI.

---

## 📦 Архив чек-листа (Спринт 3.4-B — Persistence-слой инвентаря) ✅

> Этот PR закрыт, чек-лист сохранён для истории.

- [x] Дождаться мерджа `3.4-A` в `main` (PR #117, `5c21d4e`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778309826-sprint-3-4-B-inventory-persistence` от `main`.
- [x] **B.0 — Обновить `current_tasks.md`** под старт Спринта 3.4-B: пересобрать «Снимок состояния» под `main = 5c21d4e`, переписать секцию «Декомпозиция» / чек-лист под скоуп Варианта 2 (создание таблицы вместо add-column).
- [x] **B.1 — Доменный порт `IItemRepository` + `ItemNotFoundError` + `ItemCategory.from_slot`**:
  - `domain/inventory/ports.py` (новый) — `IItemRepository(Protocol)` с `async get(*, player_id, item_id) -> Item`, `async add(*, player_id, item_id, now) -> Item`, `async update_enchant_level(*, player_id, item_id, new_level) -> Item`.
  - `domain/inventory/errors.py` — добавить `ItemNotFoundError(InventoryDomainError)` (kw-only `player_id: int, item_id: str`).
  - `domain/inventory/entities.py` — добавить `ItemCategory.from_slot(slot: Slot) -> ItemCategory` (мapping ГДД §2.6 / §2.8.1: `right_hand|left_hand → WEAPON`, `hat|body|legs|feet → ARMOR`, `ring|chain → JEWELRY`).
  - **Критерий:** `mypy --strict` 0 issues; юнит-тесты на `from_slot` (8 слотов × 1 категория) + `ItemNotFoundError.__init__` kw-only + наследование от `InventoryDomainError`.
- [x] **B.2 — ORM-модель `ItemORM` + миграция Alembic `0021_items`**:
  - `infrastructure/db/models/items.py` (новый) — `ItemORM(Base)`, `__tablename__ = "items"`. Колонки: `player_id BIGINT FK→users.id ondelete=CASCADE` (PK#1), `item_id VARCHAR(64)` (PK#2), `enchant_level INT NOT NULL server_default text("0")`, `acquired_at TIMESTAMP(timezone=True) NOT NULL`. CheckConstraint `enchant_level >= 0 AND enchant_level <= 30` (`ck_items_enchant_level_range`). Composite PK `pk_items` `(player_id, item_id)`.
  - `infrastructure/db/migrations/versions/20260509_0021_items.py` — `revision="0021_items"`, `down_revision="0020_boss_fights"`. `op.create_table("items", ...)` зеркалит ORM. `downgrade()` — `op.drop_table("items")`. `default=0` через `server_default=sa.text("0")` (Postgres backfill при `INSERT` без явного значения).
  - Зарегистрировать `ItemORM` в `infrastructure/db/models/__init__.py` (export + `__all__`) и в `tests/integration/db/conftest.py` (импорт для `Base.metadata.create_all`).
  - **Критерий:** `mypy --strict` 0 issues; `pytest tests/integration/db/test_migrations.py` зелёный (up→down→up).
- [x] **B.3 — `SqlAlchemyItemRepository`**:
  - `infrastructure/db/repositories/items.py` (новый). Зависимости: `uow: SqlAlchemyUnitOfWork`, `balance: IBalanceConfig` (для `Slot → ItemCategory`). Хелпер `_row_to_entity(row, *, balance) -> Item`: lookup `row.item_id` в `balance.get().items_catalog`, derive `category = ItemCategory.from_slot(entry.slot)`, return `Item(id=row.item_id, category=category, enchant_level=row.enchant_level)`.
  - `add(*, player_id, item_id, now)`: validate `item_id` в каталоге (иначе `DomainIntegrityError`), `INSERT items (player_id, item_id, enchant_level=0, acquired_at=now)`, return `Item`.
  - `get(*, player_id, item_id) -> Item`: `SELECT WHERE player_id=:player_id AND item_id=:item_id`, если 0 строк — `ItemNotFoundError(player_id, item_id)`.
  - `update_enchant_level(*, player_id, item_id, new_level) -> Item`: `UPDATE ... SET enchant_level = :new_level WHERE ...`, `result.rowcount == 0 → ItemNotFoundError`. Возвращает свежий `Item` (re-`get`).
  - Зарегистрировать в `infrastructure/db/repositories/__init__.py`.
  - **Критерий:** `mypy --strict` 0 issues; integration-тест на `add → get → update → get` round-trip зелёный.
- [x] **B.4 — Integration-тесты `tests/integration/db/test_item_repository.py`**:
  (a) `add → get` round-trip для всех 8 слотов × 3 категорий (`weapon`/`armor`/`jewelry`) с `enchant_level=0`;
  (b) `update_enchant_level(player, item, level=15)` → `get(...).enchant_level == 15`;
  (c) `update_enchant_level(player, item=missing, level=...)` → `ItemNotFoundError`;
  (d) `get(player, item=missing)` → `ItemNotFoundError`;
  (e) legacy-record: прямой SQL `INSERT INTO items (player_id, item_id, acquired_at) VALUES (...)` без `enchant_level` → `get` отдаёт `Item(enchant_level=0)` (доказывает `server_default`-backfill);
  (f) idempotency повторного `update_enchant_level(player, item, level=5)` × 2 → `enchant_level == 5` (без race-conflict).
  - **Критерий:** все тесты зелёные на in-memory SQLite (`engine` фикстура из `conftest.py`).
- [x] **B.5 — `make ci` локально:** ruff + mypy --strict + import-linter (4 contracts kept) + pytest зелёный + coverage gate (≥ 80%). Отчёт локального прогона: **4664 passed / 2 skipped, coverage 95.47%**, mypy 0 issues на 854 source files, 4 import-linter contracts kept.
- [x] **B.6 — Финальный док-коммит:** `history.md` +запись 3.4-B, `current_tasks.md` пересборка под старт **Спринта 3.4-C «Application use-case `EnchantItem` + audit + анти-чит trip-wire»** (включая `ScrollORM` + миграцию `0022_scrolls` — переезжает из 3.4-B в 3.4-C).
- [x] Открыт PR в `main` по шаблону `.github/pull_request_template.md`.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Текущий PR — 3.5-D «Bot UI + локали + display + закрытие Спринта 3.5»** — D.0/D.1/D.2/D.3/D.4/D.5/D.6 закрыты, осталось открыть PR в `main` и дождаться зелёного CI.
- **На `main`:** 3.5-C смержен (PR #123, `7085e51`); поверх — fix-flaky load-test (PR #124, `4baca4b`). 3.5-D открыт от свежего `main = 4baca4b`.
- **Что закрыли в 3.5-D:** см. архив чек-листа выше — 7 шагов (D.0–D.6) полностью покрыты. **Закрывает Спринт 3.5 «Free-to-play рулетка»**: после мерджа PR #125 → следующий спринт **3.6 «Бонус-за-племена в Предсказателе»** (3.6-A: domain + config + use-case + anti-cheat).
- **Открытые блокеры:** нет.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **`crypto_lot` — реальный розыгрыш отложен до Фазы 4 (Спринт 4.1).** На 3.5-D `crypto_pool_empty=True` (всегда) в use-case-е → вес `CRYPTO_LOT` перетекает на `LENGTH` в picker-е. До запуска Фазы 4 `crypto_lot` никогда не выпадет в продакшне, но result-карточка `roulette-free-result-crypto-lot` готова и snapshot-тестирована (для будущей платной рулетки + крипто-пула).
- **Не-LENGTH исходы (ITEM/SCROLL_REGULAR/SCROLL_BLESSED) — без INSERT в инвентарь на 3.5-D.** `RouletteSpinRepository.record(spin)` пишет `kind` + `length_cm=NULL`; audit-payload не содержит `target_id`. Реальный выбор предмета/скролла + INSERT в `items`/`scrolls` — задача отдельного спринта «инвентарь + рулетка интеграция» (после 3.6).
- **Баланс рулетки — стартовые веса (LENGTH 0.85 / ITEM 0.10 / SCROLL_REGULAR 0.04 / SCROLL_BLESSED 0.005 / CRYPTO_LOT 0.005)** — копия ГДД §12.4.2. После альфа-теста подбираются по метрикам; настройка через `balance.yaml` без релиза кода.
- **`AuditAction.SCROLL_DROP` всё ещё audit-only без write-through в инвентарь** — наследие предыдущих спринтов. Рейды и PvE дропают скроллы только в `audit_log`, без `INSERT` в `scrolls`-таблицу. Запланировано как отдельная задача после Спринта 3.6 (инвентарь готов с 3.4-B/C; нужен только wire-up в use-case-ах `FinishBossFight` / `FinishMountainRun` / `FinishDungeonRun`).

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`9914997` — `docs(3.5-D): D.5 — local make ci passing (5132 passed / coverage 95.63%)` (последний коммит перед docs-коммитом D.6).
