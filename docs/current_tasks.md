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
- [x] **A.1 — Доменный запрос `count_active_for_player`** (`domain/clan/repositories.py` + SQL impl):
  - Метод `IClanRepository.count_active_for_player(*, player_id: int, min_tribe_size: int) -> int` — возвращает количество активных племён, в которых состоит игрок (Phase 3 → 0/1; интерфейс готов к multi-membership Фазы 4+).
  - Активное племя: `status='active'` (не `frozen`/`archived`), `len(members) >= min_tribe_size` (с учётом самого игрока), игрок есть в `members`. Семантика `>=` совпадает с GDD §11.1 «> 3» при дефолте `min_tribe_size=4`.
  - SQL impl `SqlAlchemyClanRepository.count_active_for_player`: `SELECT clan_id FROM clan_members JOIN clans WHERE clan_id IN (SELECT clan_id FROM clan_members WHERE player_id=:p) AND clans.status='active' GROUP BY clan_id HAVING COUNT(*) >= :min_tribe_size` → `len(rows)`.
  - **Критерий:** юнит-тесты `FakeClanRepository.count_active_for_player` (9 тестов: пустой репо; не-член; size<min; size=min; size>min; frozen; min=1; min=0 → ValueError; multi-clan смешанный сценарий) + 1 integration-тест `tests/integration/db/test_clan_repository.py::test_count_active_for_player` (4 gates на одном sql-репо: ACTIVE+size>=min+член → 1; ACTIVE+size<min → 0; FROZEN+size>=min+член → 0; ACTIVE+size>=min+не-член → 0).
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
