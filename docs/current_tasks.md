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

**На `main`:** последний смерженный PR — **3.6-A** (PR #126, `d0eb138`) — domain-side бонус-за-племена в `/predict`: новый `IClanRepository.count_active_for_player(*, player_id, min_tribe_size) -> int` (`status='active'`, `len(members) >= min_tribe_size`, игрок — член) + SQL-impl `SqlAlchemyClanRepository.count_active_for_player`; pydantic `OracleTribeBonusConfig` (`enabled=true`, `cm_per_tribe=1`, `cap_cm=131`, `min_tribe_size=4`) с soft-warning при `bonus_max + cap_cm > 151`; расширение `application/oracle/invoke.py::InvokeOracle` — DI `clans: IClanRepository`, **две** проводки `length_granter.grant(...)` под одним idempotency-root `oracle:{player_id}:{moscow_date}` (базовая `source=ORACLE`, бонус `source=ORACLE_TRIBE_BONUS` — только при `tribe_bonus_cm > 0`); DTO `OraclePredictionResult` расширен полями `base_cm`/`tribe_bonus_cm`/`n_active_tribes`/`total_cm`. Anti-cheat: новый `AuditSource.ORACLE_TRIBE_BONUS`, миграция Alembic `0025_audit_source_oracle_tribe_bonus` (CHECK constraint `audit_log_source_whitelist` расширен), `AnticheatConfig.tribe_bonus_sources: tuple[AuditSource, ...]` (валидаторы disjoint от `organic_sources`/`donate_sources` + запрет `UNKNOWN`), `config/balance.yaml::anticheat.tribe_bonus_sources: [oracle_tribe_bonus]`. `oracle_tribe_bonus` НЕ входит в `organic_sources` → автоматически выпадает из 24h/7d-агрегации `SqlAlchemyAnticheatRepository.sum_organic_in_window` (защита от съедания хардкапа крупным кланом). 9 unit-тестов на `FakeClanRepository.count_active_for_player` + 1 integration `test_count_active_for_player` + 11 unit-тестов `TestOracleTribeBonusConfig` + 6 unit-тестов `TestAnticheatConfig::tribe_bonus_sources` + 6 unit-тестов `TestInvokeOracleTribeBonus` + 1 integration `test_excludes_oracle_tribe_bonus_source`. **Без UI-изменений** — UI делается отдельным PR-ом 3.6-B. Перед ним: **3.5-D** (PR #125, `ba0b769`) — bot-UI free-to-play рулетки: команда `/roulette_free` (личка-only) + pre-spin gate + spin-callback с 3-кадровой анимацией → result-card по `RouletteOutcomeKind`; `RoulettePresenter` (`bot/presenters/roulette.py`); локали `roulette-free-*` (~50 ключей × RU+EN parity); 24 unit-теста handler-а + 18 snapshot-тестов presenter-а. **Закрывает Спринт 3.5 «Free-to-play рулетка»**. Перед ним: **fix(load-tests)** (PR #124, `4baca4b`) — `poolclass=NullPool` для flaky load-теста. **3.5-C** (PR #123, `7085e51`) — application use-case `SpinFreeRoulette` + audit `ROULETTE_SPIN`. **3.5-B** (PR #122, `3505e83`) — persistence-слой рулетки. **3.5-A** (PR #121, `792a366`) — каркас домена. **3.4-D** (PR #120, `9ebbf15`); **3.4-C** (PR #119, `e490095`); **3.4-B** (PR #118, `7259fad`); **3.4-A** (PR #117, `5c21d4e`). **Закрыты Спринты 3.1 «PvE-Expeditions»**, **3.2 «Караваны»**, **3.3 «Рейд-боссы»**, **3.4 «Заточка предметов»**, **3.5 «Free-to-play рулетка»**. **В работе Спринт 3.6 «Бонус-за-племена в Предсказателе»** ([`development_plan.md`](development_plan.md) §6.3.6, ГДД §11.1) — активный PR **3.6-B** «Bot UI + локали + закрытие Спринта 3.6» (UI-сторона + закрытие спринта).

**Текущая ветка** — `devin/1778401031-sprint-3-6-B-oracle-bot-ui` (создана от `main = d0eb138`, мердж PR #126) под **Спринт 3.6-B «Bot UI + локали + закрытие Спринта 3.6»**.

Перед `3.6-A` (PR #126, `d0eb138`): **3.5-D** (PR #125, `ba0b769`); **fix(load-tests)** (PR #124, `4baca4b`); **3.5-C** (PR #123, `7085e51`); **3.5-B** (PR #122, `3505e83`); **3.5-A** (PR #121, `792a366`); **3.4-D** (PR #120, `9ebbf15`); **3.4-C** (PR #119, `e490095`); **3.4-B** (PR #118, `7259fad`); **3.4-A** (PR #117, `5c21d4e`); **3.6 design doc** (PR #116, `f7d671f`); **3.3-D** (PR #115, `5d6c9a3`); **3.3-C** (PR #114, `d08985e`); **3.3-B** (PR #113, `9c859b7`), **3.3-A** (PR #112, `dbb9b1c`); **3.2-A→D** (#108–#111); **3.1-E** (PR #107, `5c1b26f`) и PR-ы Спринтов 3.1 (#99–#106) и 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а). **Закрыт Спринт 3.3 «Рейд-боссы»** (4 PR-а). **Закрыт Спринт 3.4 «Заточка предметов»** (4 PR-а: 3.4-A/B/C/D). **Закрыт Спринт 3.5 «Free-to-play рулетка»** (4 PR-а: 3.5-A/B/C/D). **В работе Спринт 3.6 «Бонус-за-племена в Предсказателе»** ([`development_plan.md`](development_plan.md) §6.3.6) — активный PR **3.6-B** (закрывающий).

**Roadmap (после Спринта 3.6 → далее):**
- **Спринт 3.6 «Бонус-за-племена в Предсказателе»** 🎯 ([`development_plan.md`](development_plan.md) §6.3.6, ГДД §11.1) — **активный**, 2 PR-а: 3.6-A ✅ (domain + config + use-case + anti-cheat — смержен) → 3.6-B (bot UI + локали + закрытие — **активный**).
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

- **3.6-A ✅ — Доменный запрос + конфиг + use-case + anti-cheat.** `IClanRepository.count_active_for_player`, pydantic `OracleTribeBonusConfig`, расширение `InvokeOracle` use-case-а (две проводки `length_granter.grant(...)`: `oracle_base` + `oracle_tribe_bonus`), `tribe_bonus_sources` в `balance.yaml::anticheat` + Alembic-миграция `0025` + ORM-зеркало. Юнит + integration-тесты. **Без** UI-изменений. **Смержен** (PR #126, `d0eb138`).
- **3.6-B — Bot UI + локали + закрытие Спринта 3.6 (активный).** Расширение `OraclePresenter` строками `+N см — за племена (K активных племён)` (Fluent-плюрал-формы `1 племя / 2-4 племени / 5+ племён`) + опциональный hint после 3 нулевых `/predict` подряд (feature-flag, off by default), локали RU+EN, snapshot-тесты, manual smoke + финальный док-коммит закрытия Спринта 3.6. Покрывает задачи 3.6.5, 3.6.6, 3.6.7, 3.6.8.

**Финальный коммит каждого PR-а Спринта 3.6** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 3.6-X: ...») + пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит_слияния>`, передвинуть чек-лист на следующий PR (или закрыть Спринт 3.6 на 3.6-B и расписать чек-лист **первого PR-а Фазы 4** «Монетизация и масштаб»).

---

## 📝 Чек-лист следующего PR (Спринт 3.6-B — Bot UI + локали + закрытие Спринта 3.6)

> Этот PR — закрывающий PR Спринта 3.6. UI-сторона `/predict`: bot-presenter `OraclePresenter` рендерит **две** строки прироста (`+N см — базовый` + `+M см — за племена (K активных племён)`) + итоговую `+(N+M) см — итого`; при `n_active_tribes == 0` строка-за-племена скрывается. Опциональный hint «*вступай в новые племена и получай больше см*» — после первых 3 нулевых `/predict` подряд (feature-flag, off by default). Локали `oracle-base-line` / `oracle-tribe-bonus-line` (Fluent-плюрал `1 племя / 2-4 племени / 5+ племён`) / `oracle-total-line` / `oracle-no-tribes-hint` в RU+EN. Финальный док-коммит закрытия Спринта 3.6 (history.md + game_design.md §11.1 «реализовано в Спринте 3.6 (PR #...)»).

- [x] Дождаться мерджа `3.6-A` в `main` (PR #126, `d0eb138`).
- [x] `git fetch && git checkout main && git pull`.
- [x] Создать ветку `devin/1778401031-sprint-3-6-B-oracle-bot-ui` от свежего `main = d0eb138`.
- [x] **B.0 — Обновить `current_tasks.md`** под старт Спринта 3.6-B: пересобрать «Снимок состояния» под актуальный `main = d0eb138`, расписать чек-лист 3.6-B, заархивировать чек-лист 3.6-A (этот коммит — Checkpoint 1).
- [ ] **B.1 — Расширение `OraclePresenter`** (`bot/presenters/oracle.py`):
  - Добавить `result(*, prediction: OraclePredictionResult, locale: str) -> str` (или расширить существующий) — рендер **до 3 строк**: `oracle-base-line` (`{ $base_cm } см — базовый`) + опционально `oracle-tribe-bonus-line` (`{ $tribe_bonus_cm } см — за племена ({ $n_active_tribes } { $n_active_tribes -> [one]племя [few]племени *[other]племён})`) + `oracle-total-line` (`{ $total_cm } см — итого`).
  - При `prediction.tribe_bonus_cm == 0` или `prediction.n_active_tribes == 0` — строка-за-племена **скрывается**, рендерится только базовая + итоговая (`base == total`).
  - Опциональный hint (feature-flag `oracle.show_no_tribes_hint`, default `false`): если игрок выполнил 3 `/predict` подряд с `n_active_tribes == 0` (трекинг через `oracle_invocations` по последним 3 записям) — показать `oracle-no-tribes-hint`.
  - **Критерий:** snapshot-тесты на 4 сценария (0 / 1 / N=5 / cap=131 племён) × 2 locales (RU + EN) → 8 снапшотов.
- [ ] **B.2 — Локализация** (`locales/ru.ftl` + `locales/en.ftl`):
  - `oracle-base-line` (с `{ $base_cm }`).
  - `oracle-tribe-bonus-line` (с `{ $tribe_bonus_cm }`, `{ $n_active_tribes }` + Fluent-`select`-pattern для плюрала: RU `[one]племя [few]племени *[other]племён`; EN `[one]tribe *[other]tribes`).
  - `oracle-total-line` (с `{ $total_cm }`).
  - `oracle-no-tribes-hint` (опц., feature-flag).
  - **Критерий:** locale-parity-тест (`tests/integration/i18n/test_locales_parity.py`) зелёный — все ключи `oracle-*` присутствуют и в RU, и в EN.
- [ ] **B.3 — Wire-up в bot-handler `/predict`** (`bot/handlers/oracle.py`):
  - Использовать новый презентер вместо текущего рендеринга. После `await invoke_oracle.execute(...)` — `presenter.result(prediction=result, locale=user_locale)` → `await message.answer(...)`.
  - Композитный composition root (`bot/main.py`) — добавить `OraclePresenter` в `Container.oracle_presenter` если ещё не подключён.
  - **Критерий:** `tests/unit/bot/handlers/test_oracle.py` зелёные (включая существующие тесты handler-а), composition-root-тест зелёный.
- [ ] **B.4 — Manual smoke в Telegram** (не блокирует PR; делается на стейдже):
  - `/predict` без активных племён → видим только `+N см — базовый` + `+N см — итого`, без строки-за-племена.
  - `/predict` с активным племенем (`size >= 4`) → видим `+N см — базовый` + `+M см — за племена (K активных племён)` + `+(N+M) см — итого`.
  - Чек-лист в PR-описании, выполняется ревьюером после мерджа.
- [ ] **B.5 — `make ci` локально:** ruff + `mypy --strict` + import-linter (4 contracts kept) + pytest зелёный + coverage gate (≥ 80%).
- [ ] **B.6 — Финальный док-коммит закрытия Спринта 3.6:** `history.md` (запись 3.6-B + закрытие Спринта 3.6) + `current_tasks.md` пересборка под старт **Фазы 4 «Монетизация и масштаб»** (Спринт 4.1) + `game_design.md` §11.1 — пометка «реализовано в Спринте 3.6 (PR #...)».
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md` — PR #127.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Текущий PR — 3.6-B «Bot UI + локали + закрытие Спринта 3.6»** — закрывающий PR Спринта 3.6. Стартован от свежего `main = d0eb138` (мердж PR #126).
- **На `main`:** 3.6-A смержен (PR #126, `d0eb138`). 3.6-B открыт от свежего `main = d0eb138`.
- **Скоуп 3.6-B:** UI-сторона `/predict` — рендер двух строк прироста (`+N см — базовый` + `+M см — за племена (K активных племён)`) + итоговая, опциональный hint после 3 нулевых `/predict` подряд (feature-flag, off by default). Локали `oracle-base-line` / `oracle-tribe-bonus-line` (Fluent-плюрал) / `oracle-total-line` / `oracle-no-tribes-hint` (опц.) в RU+EN. Snapshot-тесты на 4 сценария × 2 locales. Финальный док-коммит закрытия Спринта 3.6 (`history.md` + `game_design.md` §11.1 «реализовано в Спринте 3.6»). После закрытия Спринта 3.6 — переход к Фазе 4 «Монетизация и масштаб» (Спринт 4.1).
- **Открытые блокеры:** нет.

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Phase-3 multi-membership ограничение.** В Phase 3 игрок может состоять максимум в **одном** клане (`UNIQUE` constraint на `clan_members.player_id` ещё с миграции `0006_clan_members`). Поэтому `count_active_for_player` фактически возвращает `0` или `1` в Phase 3, и `tribe_bonus_cm ∈ {0, cm_per_tribe}` (по дефолту `0` или `1`). Интерфейс готов к Phase 4+ (multi-membership), но реальный `+131 см cap` будет достигаться только после снятия `UNIQUE`-constraint и реализации UI «вступить в племя × N» (вне скоупа Спринта 3.6).
- **`crypto_lot` — реальный розыгрыш отложен до Фазы 4 (Спринт 4.1).** В рулетке `crypto_pool_empty=True` (всегда) в use-case-е → вес `CRYPTO_LOT` перетекает на `LENGTH` в picker-е. До запуска Фазы 4 `crypto_lot` никогда не выпадет в продакшне, но result-карточка `roulette-free-result-crypto-lot` готова и snapshot-тестирована (для будущей платной рулетки + крипто-пула).
- **Не-LENGTH исходы рулетки (ITEM/SCROLL_REGULAR/SCROLL_BLESSED) — без INSERT в инвентарь.** `RouletteSpinRepository.record(spin)` пишет `kind` + `length_cm=NULL`; audit-payload не содержит `target_id`. Реальный выбор предмета/скролла + INSERT в `items`/`scrolls` — задача отдельного спринта «инвентарь + рулетка интеграция» (после 3.6).
- **`AuditAction.SCROLL_DROP` всё ещё audit-only без write-through в инвентарь** — наследие предыдущих спринтов. Рейды и PvE дропают скроллы только в `audit_log`, без `INSERT` в `scrolls`-таблицу. Запланировано как отдельная задача после Спринта 3.6 (инвентарь готов с 3.4-B/C; нужен только wire-up в use-case-ах `FinishBossFight` / `FinishMountainRun` / `FinishDungeonRun`).

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`<обновится после B.0 push>` — `docs(3.6-B): B.0 — pivot current_tasks.md под Спринт 3.6-B start (main = d0eb138)`.
