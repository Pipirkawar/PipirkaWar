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

**На `main`:** последний смерженный PR — **3.6-B** (PR #127, `b684679`) — UI-сторона Tribe-bonus в `/predict`: `OraclePresenter.success()` расширен на 3-line breakdown (`oracle-base-line` + `oracle-tribe-bonus-line` + `oracle-total-line` + `oracle-new-length-line` под conditional рендер `n_active_tribes > 0`); локали `oracle-*` × RU+EN с Fluent-плюрал-формами (RU `[one]племя [few]племени *[other]племён`; EN `[one]tribe *[other]tribes`); wire-up в `predict_handler` (`base_cm`/`tribe_bonus_cm`/`n_active_tribes` → presenter); 22 snapshot-теста на 4 сценария (`n_active_tribes ∈ {0, 1, 5, 131}`) × 2 locales + handler-тесты. **Закрывает Спринт 3.6 «Бонус-за-племена в Предсказателе»**. Перед `3.6-B`: **3.6-A** (PR #126, `d0eb138`) — domain-side бонус-за-племена. Перед `3.6-A`: **3.5-D** (PR #125, `ba0b769`) — bot-UI free-to-play рулетки, закрытие Спринта 3.5; **fix(load-tests)** (PR #124, `4baca4b`); **3.5-C** (PR #123, `7085e51`); **3.5-B** (PR #122, `3505e83`); **3.5-A** (PR #121, `792a366`). **Закрыты Спринты 3.1 «PvE-Expeditions»**, **3.2 «Караваны»**, **3.3 «Рейд-боссы»**, **3.4 «Заточка предметов»**, **3.5 «Free-to-play рулетка»**, **3.6 «Бонус-за-племена в Предсказателе»**. **В работе Фаза 4 «Монетизация и масштаб»** ([`development_plan.md`](development_plan.md) §7) — **Спринт 4.1**, активный PR **4.1-A** «Telegram Stars + платная рулетка skeleton».

**Текущая ветка** — `devin/1778406997-sprint-4-1-A-paid-roulette-skeleton` (создана от `main = b684679`, мердж PR #127) под **Спринт 4.1-A «Telegram Stars + платная рулетка skeleton»** (первый PR Спринта 4.1).

Перед `3.6-B` (PR #127, `b684679`): **3.6-A** (PR #126, `d0eb138`); **3.5-D** (PR #125, `ba0b769`); **fix(load-tests)** (PR #124, `4baca4b`); **3.5-C** (PR #123, `7085e51`); **3.5-B** (PR #122, `3505e83`); **3.5-A** (PR #121, `792a366`); **3.4-D** (PR #120, `9ebbf15`); **3.4-C** (PR #119, `e490095`); **3.4-B** (PR #118, `7259fad`); **3.4-A** (PR #117, `5c21d4e`); **3.6 design doc** (PR #116, `f7d671f`); **3.3-D** (PR #115, `5d6c9a3`); **3.3-C** (PR #114, `d08985e`); **3.3-B** (PR #113, `9c859b7`), **3.3-A** (PR #112, `dbb9b1c`); **3.2-A→D** (#108–#111); **3.1-E** (PR #107, `5c1b26f`) и PR-ы Спринтов 3.1 (#99–#106) и 2.5 (#79–#97).

**Закрыт Спринт 3.1 «PvE-Expeditions»** (5 PR-ов). **Закрыт Спринт 3.2 «Караваны (полная механика)»** (4 PR-а). **Закрыт Спринт 3.3 «Рейд-боссы»** (4 PR-а). **Закрыт Спринт 3.4 «Заточка предметов»** (4 PR-а: 3.4-A/B/C/D). **Закрыт Спринт 3.5 «Free-to-play рулетка»** (4 PR-а: 3.5-A/B/C/D). **Закрыт Спринт 3.6 «Бонус-за-племена в Предсказателе»** (2 PR-а: 3.6-A/B). **В работе Спринт 4.1 (Фаза 4 «Монетизация и масштаб»)** ([`development_plan.md`](development_plan.md) §7).

**Roadmap (Спринт 4.1, декомпозиция на фичевые PR-ы):**
- **4.1-A — Telegram Stars + платная рулетка (skeleton)** (задачи 4.1.1, 4.1.4) — **активный**: domain-payments (`Currency`/`StarsAmount`/`IdempotencyKey`/`Payment`), domain paid roulette (`RouletteVariant.PAID` + paid-picker по §12.5.2), application use-case `SpinPaidRoulette` + порт `IPaymentLedger.charge` с idempotency, persistence (таблица `payments` + Alembic `0026` + `SqlAlchemyPaymentLedger`), audit-source `PAYMENT_STARS`, конфиг `RoulettePaidConfig` + `balance.yaml::roulette.paid`, bot-handler skeleton (TG Stars `pre_checkout_query` + payment-callback). **Без TON/USDT/прайз-пула — это последующие PR-ы.**
- **4.1-B — Призовой пул + persistence + audit** (задачи 4.1.5, 4.1.6): `RecordDonation` (10% → пул), domain-агрегат `PrizePool(stars, ton_nano, usdt_decimal)`, миграция Alembic, ORM, audit `ADMIN_PRIZE_POOL_*`.
- **4.1-C — Лот-генератор + крипто-приз в рулетке** (задачи 4.1.7, 4.1.8): `PrizePoolService.regenerate_lots`, `IFeeEstimator`, cron 1×/час, picker-крипто-приз в результат-пул.
- **4.1-D — TON Connect + USDT + ClaimPrize** (задачи 4.1.2, 4.1.3, 4.1.9): TON SDK, USDT через TON-процессор, `ClaimPrize`, handler «Привязать кошелёк», integration в sandbox.
- **4.1-E — Админ-команды + лимиты выплат** (задачи 4.1.10, 4.1.11): `/prize_pool`/`/refund_lot`/`/freeze_payouts` (super_admin + TOTP), rolling-30d-лимит.
- **4.1-F — Redis + ИИ + многоязычность + метрики + закрытие Спринта 4.1** (задачи 4.1.12, 4.1.13, 4.1.14, 4.1.15): переход на Redis, опц. ИИ-предсказания, +6 локалей (PT, ES, TR, ID, FA, UK), Prometheus + Grafana, финальный док-коммит.

---

## 🎯 Активный спринт — Спринт 4.1 «Монетизация и масштаб» 🎯 (Фаза 4)

> Цель спринта (по [`development_plan.md`](development_plan.md) §7 «Фаза 4 — Монетизация и масштаб», ГДД §12.5/§12.6): запуск платных каналов (Telegram Stars / TON / USDT) + крипто-призовой пул из 10% донат-зачислений + лот-генератор + крипто-приз в рулетке + use-case `ClaimPrize` + админ-команды + переход на Redis + многоязычность + метрики. Декомпозиция на 6 фичевых PR-ов (4.1-A → 4.1-F, см. Roadmap выше).

**Скоуп — задачи плана 4.1.* (детали — в [`development_plan.md`](development_plan.md) §7):**

- **4.1.1 — Telegram Stars: платная рулетка** за 1 ⭐ (1 спин) и 9 ⭐ (10 спинов, 10-pack). ГДД §12.5; стартовые веса призов и бакеты СМ — §12.5.2. Расчёт случайного выигрыша; чек-лог транзакций; 10-pack одной транзакцией; integration 10000 спинов: `E[CM | spin] ≈ 27 см`.
- **4.1.2 — TON Connect:** фикс длина за TON. Sandbox + продакшн-сеть; webhook/poll платежей.
- **4.1.3 — USDT (через TON-сеть/процессор):** параметризованные суммы → длина.
- **4.1.4 — Антифрод платежей,** проверка двойных зачислений. Idempotency-key на платёж.
- **4.1.5 — 10% от каждого донат-зачисления → крипто-призовой пул** (ГДД §12.6). `RecordDonation` use-case при подтверждении платежа делает второй проводкой `IncreasePrizePool(currency, amount=donation*0.10)`. Идемпотентно. Юнит-тесты на all 3 валюты; integration: подтверждённый донат 100 ⭐ → пул вырос на 10 ⭐.
- **4.1.6 — Призовой пул** — domain-агрегат `PrizePool(stars, ton_nano, usdt_decimal)`. Persistence + миграция. Audit-лог любого изменения. Юнит-тесты на инкременты/декременты; round-trip persistence.
- **4.1.7 — Лот-генератор** (`PrizePoolService.regenerate_lots`, ГДД §12.6.3). Cron 1×/час + триггер после крупного донат-зачисления. Учёт комиссии: `IFeeEstimator` с P95 за 7 дней. Минимум лота = 1 USD-эквивалент + комиссия; максимум = 10 USD-эквивалент. Юнит-тесты: пул 3 USDT → 3 лота × 1 USDT; пул 15 USDT → 1 лот × 10 USDT (5 USDT остаются); комиссия > buffer → лот возвращается.
- **4.1.8 — Крипто-приз** в результат-пуле платной + free-рулеток (ГДД §12.4.2, §12.5.2). Если активных лотов в данной валюте нет — слот криптоприза занимает СМ-приз. Юнит-тесты picker-а: пул пуст → крипто-приз не появляется.
- **4.1.9 — Выплата выигрыша:** handler «Привязать кошелёк» + use-case `ClaimPrize(player, lot_id, recipient_address)` + транзакция через TON SDK. Жёсткая защита: `actual_fee > fee_buffer` → лот возвращается в пул, выплата откладывается. Юнит-тесты на все ветки; integration в TON sandbox.
- **4.1.10 — Админ-команды** `/prize_pool`, `/refund_lot <lot_id>`, `/freeze_payouts` (super_admin + TOTP, ГДД §12.6.6). RBAC-тесты; audit-записи `ADMIN_PRIZE_*`.
- **4.1.11 — Лимиты выплат на игрока:** `max 50 USDT-экв за 30 дней` (TODO(balance): финальное число). Сверх лимита — выплата ставится в очередь. Юнит-тесты на rolling 30 day window.
- **4.1.12 — Переход на Redis** (лобби, очереди, DAU, locks). Нагрузочный тест 10× от MVP.
- **4.1.13 — Перевод предсказаний/логов на ИИ** (опционально). Кэш на сгенерированных ответах.
- **4.1.14 — Доп. языки:** PT, ES, TR, ID, FA, UK. Файлы переводов, тест fallback.
- **4.1.15 — Метрики и дашборд** (Prometheus + Grafana). Графики DAU/RPS/караваны/рейды + крипто-пул per currency.

**Финальный коммит каждого PR-а Спринта 4.1** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 4.1-X: ...») + пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит_слияния>`, передвинуть чек-лист на следующий PR (или закрыть Спринт 4.1 на 4.1-F и расписать чек-лист **первого PR-а Спринта 4.2**, если он спланирован).

---

## 📝 Чек-лист текущего PR — 4.1-A «Telegram Stars + платная рулетка skeleton»

> Скоуп: domain-payments (`Currency`/`StarsAmount`/`IdempotencyKey`/`Payment` + `PaymentStatus`); domain paid roulette (`RouletteVariant` enum + `pick_paid_outcome` функция, веса §12.5.2); pydantic `RoulettePaidConfig`; application use-case `SpinPaidRoulette(player, pack: SINGLE|PACK_10, idempotency_key)` + порт `IPaymentLedger.charge` с idempotency-веткой; persistence (таблица `payments` + Alembic `0026_payments` + ORM + `SqlAlchemyPaymentLedger`); audit-source `PAYMENT_STARS`; конфиг `balance.yaml::roulette.paid`; bot-handler skeleton (TG Stars `pre_checkout_query` + `successful_payment` callback → `SpinPaidRoulette`).

- [x] `git fetch && git checkout main && git pull` (свежий `main = b684679`).
- [x] Создать ветку `devin/1778406997-sprint-4-1-A-paid-roulette-skeleton` от свежего `main = b684679`.
- [x] **A.0 — Обновить `current_tasks.md`** под старт Спринта 4.1-A: пересобрать «Снимок состояния» под актуальный `main = b684679`, расписать чек-лист 4.1-A, заархивировать чек-лист 3.6-B (Checkpoint 1).
- [x] **A.1 — Domain payments** (`src/pipirik_wars/domain/monetization/`): `value_objects.py` — `Currency` enum (`STARS`/`TON_NANO`/`USDT_DECIMAL`), `StarsAmount(int, > 0)` VO, `IdempotencyKey` VO (≤ 64 chars, `[a-zA-Z0-9_-]+`); `entities.py` — `Payment(id, player_id, currency, amount_native, idempotency_key, status: PENDING/CONFIRMED/REFUNDED, provider_payment_id, payload, created_at, confirmed_at)`; `errors.py` — `IdempotencyConflict(stored_key)`. 12+ unit-тестов VO (StarsAmount > 0, IdempotencyKey валидация, Currency enum членство).
- [x] **A.2 — Domain paid roulette** (`src/pipirik_wars/domain/roulette/`): расширить `entities.py` enum-ом `RouletteVariant` (`FREE`/`PAID`); `services.py::pick_paid_outcome(rng, paid_config) -> SpinResult` (выбор kind по 5 весам §12.5.2 + `length_buckets`-выбор для `LengthGain`); `errors.py` — `PaidRouletteCryptoPoolEmpty` если `crypto_lot` выпал, но пул пуст → `LengthGain` fallback (как у free). 10+ unit-тестов picker-а на детерминированный seed.
- [x] **A.3 — Application** (`src/pipirik_wars/application/monetization/` + `application/roulette/`): новый порт `IPaymentLedger.charge(player_id, currency, amount, idempotency_key) -> PaymentReceipt` (если ключ уже есть → возвращаем существующий receipt, не списываем повторно; если ключ есть с другой суммой/игроком → `IdempotencyConflict`); use-case `SpinPaidRoulette(player, pack: PaidRoulettePack.SINGLE|PACK_10, idempotency_key)` — расширение `SpinFreeRoulette`-логики. 1 spin = `single` charge, 10-pack = одна транзакция → 10 спинов в цикле под одним `idempotency_key`. Audit `ROULETTE_SPIN` per spin (как у free) + `PAYMENT_STARS_RECORDED` per charge. 15+ unit-тестов: успешный спин, повторный idempotency_key (noop), коллизия суммы/игрока (`IdempotencyConflict`), 10-pack → 10 спинов, кап-проверка длины.
- [ ] **A.4 — Config + balance.yaml** (`config/balance.yaml`, `src/pipirik_wars/domain/balance/_models/roulette.py`): добавить блок `roulette.paid` с весами и бакетами §12.5.2 (`cost_stars_single: 1`, `cost_stars_pack10: 9`, `pack10_spins: 10`, `min_thickness: 1`, `outcomes: [length 0.550, item 0.200, scroll_regular 0.180, scroll_blessed 0.050, crypto_lot 0.020]`, `length_buckets: [small 10..50 0.800, medium 50..150 0.170, good 150..300 0.025, big 300..500 0.005]`); `RoulettePaidConfig` pydantic с валидацией суммы весов = 1.0 ± epsilon. 8+ unit-тестов конфига.
- [ ] **A.5 — Persistence** (`src/pipirik_wars/infrastructure/db/`): таблица `payments` (`id BIGSERIAL`, `player_id BIGINT FK NOT NULL`, `currency TEXT CHECK (...)`, `amount_native NUMERIC(38,0) NOT NULL CHECK > 0`, `idempotency_key TEXT NOT NULL`, `status TEXT CHECK (...)`, `provider_payment_id TEXT NULL`, `payload JSONB NOT NULL DEFAULT '{}'`, `created_at TIMESTAMPTZ NOT NULL`, `confirmed_at TIMESTAMPTZ NULL`, `UNIQUE (player_id, idempotency_key)`); Alembic-миграция `0026_payments_and_audit_source` (включает `audit_log_source_whitelist` CHECK расширение для `payment_stars`); ORM `PaymentRow` + `SqlAlchemyPaymentLedger` имплементация порта (insert + on-conflict-by-idempotency_key + select-by-key + status update). `AuditSource.PAYMENT_STARS` в whitelist + `AnticheatConfig.donate_sources: [..., payment_stars]`. 6+ unit-тестов миграции (up/down) + 8+ integration round-trip.
- [ ] **A.6 — Bot handler skeleton** (`src/pipirik_wars/bot/handlers/roulette_paid.py` + расширение `roulette.py`): `/roulette_paid` → invoice TG Stars (1⭐ or 9⭐); `pre_checkout_query` → ack (валидация payload); `successful_payment` → `IPaymentLedger.charge` + `SpinPaidRoulette.execute` → render result через `RoulettePresenter` (используем существующий из 3.5-D). Локали `roulette-paid-*` (~10 ключей × RU+EN, parity-тест зелёный). 8+ unit-тестов handler-а с `FakePaymentLedger`.
- [ ] **A.7 — `make ci` локально:** ruff + `mypy --strict` + import-linter (4 contracts kept) + pytest зелёный + coverage gate (≥ 80%).
- [ ] **A.8 — Финальный док-коммит:** `history.md` запись 4.1-A + `current_tasks.md` пересборка под старт **Спринта 4.1-B** «Призовой пул + persistence + audit».
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md` — PR #128.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Текущий PR — 4.1-A «Telegram Stars + платная рулетка skeleton»** — первый PR Спринта 4.1 (Фаза 4 «Монетизация и масштаб»). Стартован от свежего `main = b684679` (мердж PR #127, закрытие Спринта 3.6).
- **На `main`:** Спринт 3.6 закрыт (PR #127, `b684679`). Спринт 4.1 в работе.
- **Скоуп 4.1-A:** domain-payments (`Currency`/`StarsAmount`/`IdempotencyKey`/`Payment`+`PaymentStatus`) + domain paid roulette (`RouletteVariant` enum + paid-picker по §12.5.2) + application use-case `SpinPaidRoulette` + порт `IPaymentLedger.charge` с idempotency-веткой + persistence (таблица `payments` + Alembic `0026` + `SqlAlchemyPaymentLedger`) + audit-source `PAYMENT_STARS` + bot-handler skeleton (TG Stars invoice + payment-callback). **Без** TON Connect / USDT / крипто-пула / лот-генератора / `ClaimPrize` — это следующие PR-ы (4.1-B…F).
- **Открытые блокеры:** нет.
- **После мерджа PR #128:** старт **Спринта 4.1-B** «Призовой пул + persistence + audit» (задачи 4.1.5, 4.1.6).

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Phase-3 multi-membership ограничение** (наследие 3.6-A). В Phase 3 игрок может состоять максимум в **одном** клане (`UNIQUE` constraint на `clan_members.player_id` ещё с миграции `0006_clan_members`). Поэтому `count_active_for_player` фактически возвращает `0` или `1`, и `tribe_bonus_cm ∈ {0, cm_per_tribe}`. Интерфейс готов к Phase 4+ (multi-membership), но реальный `+131 см cap` будет достигаться только после снятия `UNIQUE`-constraint и реализации UI «вступить в племя × N» (вне скоупа Спринта 4.1).
- **Опциональный hint `oracle-no-tribes-hint`** (3 нулевых `/predict` подряд → «*вступай в новые племена и получай больше см*») — **не реализован** в 3.6-B. Помечен как feature-flag `oracle.show_no_tribes_hint` (default `false`). Реальная реализация требует трекинга последних 3 invocations — отдельный enhancement.
- **`crypto_lot` — реальный розыгрыш отложен до 4.1-C.** В рулетке `crypto_pool_empty=True` (всегда) в use-case-е → вес `CRYPTO_LOT` перетекает на `LENGTH` в picker-е (для free и paid-варианта). До запуска 4.1-C (лот-генератор + `PrizePool`) `crypto_lot` никогда не выпадет в продакшне, но result-карточка `roulette-free-result-crypto-lot` готова и snapshot-тестирована (для будущей платной рулетки + крипто-пула).
- **Не-LENGTH исходы рулетки (ITEM/SCROLL_REGULAR/SCROLL_BLESSED) — без INSERT в инвентарь.** `RouletteSpinRepository.record(spin)` пишет `kind` + `length_cm=NULL`; audit-payload не содержит `target_id`. Реальный выбор предмета/скролла + INSERT в `items`/`scrolls` — задача отдельного спринта «инвентарь + рулетка интеграция» (после 4.1).
- **`AuditAction.SCROLL_DROP` всё ещё audit-only без write-through в инвентарь** — наследие предыдущих спринтов. Рейды и PvE дропают скроллы только в `audit_log`, без `INSERT` в `scrolls`-таблицу. Запланировано как отдельная задача после Спринта 4.1.
- **Реальный TG Stars-провайдер (skeleton 4.1-A bot-handler).** Skeleton handler принимает `successful_payment` от Telegram, но без подписания payload-а финансовый callback потенциально подделываем. В 4.1-D (TON Connect) добавим signature-верификацию payload-а и серверную сверку (provider-id ⇄ idempotency_key). До этого момента — **только staging/dev**, не запускать в prod.

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`<обновится после A.3 push>` — `feat(4.1-A): A.3 — SpinPaidRoulette use-case + IPaymentLedger port + unit-тесты`.
