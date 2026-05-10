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

**На `main` после мерджа PR #128:** последний смерженный PR — **4.1-A** (PR #128) — Telegram Stars + платная рулетка skeleton: domain-payments (`Currency`/`StarsAmount`/`IdempotencyKey`/`Payment` + `PaymentStatus` + `IdempotencyConflict`); domain paid roulette (`RouletteVariant.PAID` + `pick_paid_outcome` по §12.5.2); application use-case `SpinPaidRoulette` + порт `IPaymentLedger.charge`/`get_by_idempotency_key` с idempotency-веткой и anti-fraud-сверкой; persistence (таблица `payments` + Alembic `0026_payments_and_audit_source` + `SqlAlchemyPaymentLedger`); audit-source `roulette_paid_reward`; конфиг `RoulettePaidConfig` + `balance.yaml::roulette.paid`; bot-handler skeleton (`/roulette_paid` → `pre_checkout_query` → `successful_payment` → `SpinPaidRoulette`) + `RoulettePaidPresenter` + 26 локалей × RU+EN. **Стартует Фазу 4 «Монетизация и масштаб» / Спринт 4.1.** Перед `4.1-A`: **3.6-B** (PR #127, `b684679`) — UI Tribe-bonus + закрытие Спринта 3.6; **3.6-A** (PR #126, `d0eb138`); **3.5-D** (PR #125, `ba0b769`) — закрытие Спринта 3.5; **3.5-A→C** (#121–#123); **fix(load-tests)** (PR #124); **3.4-A→D** (#117–#120) — закрытие Спринта 3.4; **3.6 design doc** (PR #116); **3.3-A→D** (#112–#115) — закрытие Спринта 3.3; **3.2-A→D** (#108–#111); **3.1-A→E** (#99–#107). **Закрыты Спринты 3.1 «PvE-Expeditions»**, **3.2 «Караваны»**, **3.3 «Рейд-боссы»**, **3.4 «Заточка предметов»**, **3.5 «Free-to-play рулетка»**, **3.6 «Бонус-за-племена в Предсказателе»**. **В работе Фаза 4 «Монетизация и масштаб»** ([`development_plan.md`](development_plan.md) §7) — **Спринт 4.1**, активный PR **4.1-B** «Призовой пул + persistence + audit».

**Текущая ветка** — будет создана от `main` после мерджа PR #128 — `devin/<timestamp>-sprint-4-1-B-prize-pool` под **Спринт 4.1-B «Призовой пул + persistence + audit»** (второй PR Спринта 4.1).

**Roadmap (Спринт 4.1, декомпозиция на фичевые PR-ы):**
- **4.1-A — Telegram Stars + платная рулетка (skeleton)** (задачи 4.1.1, 4.1.4) — **закрыт PR #128**: domain-payments + paid roulette + use-case `SpinPaidRoulette` + порт `IPaymentLedger` + persistence + audit + конфиг + bot-handler skeleton + 26 локалей × RU+EN.
- **4.1-B — Призовой пул + persistence + audit** (задачи 4.1.5, 4.1.6) — **активный**: domain-агрегат `PrizePool(stars, ton_nano, usdt_decimal)` + use-case `RecordDonation` (10% → пул, идемпотентно через тот же `idempotency_key`); domain-port `IPrizePoolRepository` (`get_current() -> PrizePool` + `apply_increment(currency, amount_native) -> PrizePool` атомарно); persistence (таблица `prize_pool_balance` или одна row + миграция Alembic `0027` + ORM + `SqlAlchemyPrizePoolRepository`); audit-source `prize_pool_increment` + `ADMIN_PRIZE_POOL_*`; интеграция `RecordDonation` в `SpinPaidRoulette`-flow (после `IPaymentLedger.charge → +pool`); юнит-тесты на all 3 валюты + integration «100 ⭐ донат → пул вырос на 10 ⭐».
- **4.1-C — Лот-генератор + крипто-приз в рулетке** (задачи 4.1.7, 4.1.8): `PrizePoolService.regenerate_lots`, `IFeeEstimator`, cron 1×/час, picker-крипто-приз в результат-пул.
- **4.1-D — TON Connect + USDT + ClaimPrize** (задачи 4.1.2, 4.1.3, 4.1.9): TON SDK, USDT через TON-процессор, `ClaimPrize`, handler «Привязать кошелёк», integration в sandbox; signature-верификация TG Stars payload-а (вывод 4.1-A handler-а в продакшн).
- **4.1-E — Админ-команды + лимиты выплат** (задачи 4.1.10, 4.1.11): `/prize_pool`/`/refund_lot`/`/freeze_payouts` (super_admin + TOTP), rolling-30d-лимит.
- **4.1-F — Redis + ИИ + многоязычность + метрики + закрытие Спринта 4.1** (задачи 4.1.12, 4.1.13, 4.1.14, 4.1.15): переход на Redis, опц. ИИ-предсказания, +6 локалей (PT, ES, TR, ID, FA, UK), Prometheus + Grafana, финальный док-коммит.

---

## 🎯 Активный спринт — Спринт 4.1 «Монетизация и масштаб» 🎯 (Фаза 4)

> Цель спринта (по [`development_plan.md`](development_plan.md) §7 «Фаза 4 — Монетизация и масштаб», ГДД §12.5/§12.6): запуск платных каналов (Telegram Stars / TON / USDT) + крипто-призовой пул из 10% донат-зачислений + лот-генератор + крипто-приз в рулетке + use-case `ClaimPrize` + админ-команды + переход на Redis + многоязычность + метрики. Декомпозиция на 6 фичевых PR-ов (4.1-A → 4.1-F, см. Roadmap выше).

**Скоуп — задачи плана 4.1.* (детали — в [`development_plan.md`](development_plan.md) §7):**

- **4.1.1 — Telegram Stars: платная рулетка** ✅ — реализовано в 4.1-A (PR #128). Skeleton: invoice + pre_checkout_query + successful_payment → `SpinPaidRoulette`. До 4.1-D — staging-only.
- **4.1.2 — TON Connect:** фикс длина за TON. Sandbox + продакшн-сеть; webhook/poll платежей. (4.1-D)
- **4.1.3 — USDT (через TON-сеть/процессор):** параметризованные суммы → длина. (4.1-D)
- **4.1.4 — Антифрод платежей,** проверка двойных зачислений ✅ — реализовано в 4.1-A (PR #128) — `IdempotencyKey` VO + DB `UNIQUE (player_id, idempotency_key)` + on-conflict + anti-fraud-сверка currency/amount.
- **4.1.5 — 10% от каждого донат-зачисления → крипто-призовой пул** (ГДД §12.6) — **в работе 4.1-B**. `RecordDonation` use-case при подтверждении платежа делает второй проводкой `IncreasePrizePool(currency, amount=donation*0.10)`. Идемпотентно. Юнит-тесты на all 3 валюты; integration: подтверждённый донат 100 ⭐ → пул вырос на 10 ⭐.
- **4.1.6 — Призовой пул** — domain-агрегат `PrizePool(stars, ton_nano, usdt_decimal)`. Persistence + миграция. Audit-лог любого изменения. Юнит-тесты на инкременты/декременты; round-trip persistence. **(4.1-B)**
- **4.1.7 — Лот-генератор** (`PrizePoolService.regenerate_lots`, ГДД §12.6.3). Cron 1×/час + триггер после крупного донат-зачисления. Учёт комиссии: `IFeeEstimator` с P95 за 7 дней. Минимум лота = 1 USD-эквивалент + комиссия; максимум = 10 USD-эквивалент. Юнит-тесты: пул 3 USDT → 3 лота × 1 USDT; пул 15 USDT → 1 лот × 10 USDT (5 USDT остаются); комиссия > buffer → лот возвращается. (4.1-C)
- **4.1.8 — Крипто-приз** в результат-пуле платной + free-рулеток (ГДД §12.4.2, §12.5.2). Если активных лотов в данной валюте нет — слот криптоприза занимает СМ-приз. Юнит-тесты picker-а: пул пуст → крипто-приз не появляется. (4.1-C)
- **4.1.9 — Выплата выигрыша:** handler «Привязать кошелёк» + use-case `ClaimPrize(player, lot_id, recipient_address)` + транзакция через TON SDK. Жёсткая защита: `actual_fee > fee_buffer` → лот возвращается в пул, выплата откладывается. Юнит-тесты на все ветки; integration в TON sandbox. (4.1-D)
- **4.1.10 — Админ-команды** `/prize_pool`, `/refund_lot <lot_id>`, `/freeze_payouts` (super_admin + TOTP, ГДД §12.6.6). RBAC-тесты; audit-записи `ADMIN_PRIZE_*`. (4.1-E)
- **4.1.11 — Лимиты выплат на игрока:** `max 50 USDT-экв за 30 дней` (TODO(balance): финальное число). Сверх лимита — выплата ставится в очередь. Юнит-тесты на rolling 30 day window. (4.1-E)
- **4.1.12 — Переход на Redis** (лобби, очереди, DAU, locks). Нагрузочный тест 10× от MVP. (4.1-F)
- **4.1.13 — Перевод предсказаний/логов на ИИ** (опционально). Кэш на сгенерированных ответах. (4.1-F)
- **4.1.14 — Доп. языки:** PT, ES, TR, ID, FA, UK. Файлы переводов, тест fallback. (4.1-F)
- **4.1.15 — Метрики и дашборд** (Prometheus + Grafana). Графики DAU/RPS/караваны/рейды + крипто-пул per currency. (4.1-F)

**Финальный коммит каждого PR-а Спринта 4.1** (внутри ветки, последним перед мерджем) — обновить `history.md` (запись «Спринт 4.1-X: ...») + пересобрать «Снимок состояния» в `current_tasks.md` под `main = <коммит_слияния>`, передвинуть чек-лист на следующий PR (или закрыть Спринт 4.1 на 4.1-F и расписать чек-лист **первого PR-а Спринта 4.2**, если он спланирован).

---

## 📝 Чек-лист текущего PR — 4.1-B «Призовой пул + persistence + audit»

> Скоуп: domain-агрегат `PrizePool(stars: int, ton_nano: int, usdt_decimal: int)` + invariant-ы (`>= 0`, atomic-операции `apply_increment(currency, amount)`); domain-port `IPrizePoolRepository` (`get_current() -> PrizePool`, `apply_increment(currency, amount_native) -> PrizePool` атомарно через row-lock или UPSERT); persistence (одна row в таблице `prize_pool_balance` или 3 row-а per currency + миграция Alembic `0027` + ORM + `SqlAlchemyPrizePoolRepository`); audit-source `prize_pool_increment` (per-донат) + `ADMIN_PRIZE_POOL_FREEZE/UNFREEZE/RESET` (для будущей 4.1-E); use-case `RecordDonation(player_id, currency, amount, idempotency_key) -> PrizePoolReceipt` (10% от подтверждённого платежа → пул, идемпотентно через тот же `idempotency_key`-prefix `prize_pool:{payment_id}`); интеграция в `SpinPaidRoulette`-flow (после `IPaymentLedger.charge → RecordDonation.execute`); юнит-тесты + integration «подтверждённый донат 100 ⭐ → пул вырос на 10 ⭐».

- [x] `git fetch && git checkout main && git pull` (свежий `main = 21c21c0` — merge PR #128).
- [x] Создать ветку `devin/1778420160-sprint-4-1-B-prize-pool` от свежего `main`.
- [x] **B.0 — Обновить `current_tasks.md`** под старт Спринта 4.1-B: пересобрать «Снимок состояния» под актуальный `main = 21c21c0`, расписать чек-лист 4.1-B (был расписан в A.8), создать `AGENT_HANDOFF.md` (Checkpoint 1, sha `48dbfc1`).
- [x] **B.1 — Domain prize pool** (`src/pipirik_wars/domain/monetization/`): расширил `entities.py` агрегатом `PrizePool(stars, ton_nano, usdt_decimal)` (frozen+slots) с фабрикой `PrizePool.empty()`, аксессором `balance_for(currency)` и иммутабельным `apply_increment(currency, amount_native) -> PrizePool` (invariant `>= 0`). Новые VO в `value_objects.py`: `StarsPoolBalance(int, >= 0)` (отдельно от платёжного `StarsAmount, >= 1`), `TonNanoAmount(int, >= 0)`, `UsdtDecimalAmount(int, >= 0)`. Ошибка `PrizePoolAmountInvariantError` в `errors.py`. Порт `IPrizePoolRepository` в `ports.py` (методы `get_current()` / `apply_increment(currency, amount_native)`). 50+ unit-тестов (test_prize_pool.py: 28 кейсов + 22 новых в test_value_objects.py). Checkpoint sha `05f78c2`.
- [~] **B.2 — Application use-case `RecordDonation`** (`src/pipirik_wars/application/monetization/record_donation.py`): принимает `(currency, payment_amount_native, idempotency_key) -> RecordDonationResult` (`donation_amount_native: int`, `pool_after: PrizePool`, `applied: bool`); вычисляет `donation = payment_amount_native // 10` (`floor`-округление, ГДД §12.6.1) и вызывает `repo.apply_increment(currency, donation)` при `donation > 0`, иначе возвращает текущий снапшот через `repo.get_current()` (`applied=False`). Идемпотентность наследуется от caller-а (`SpinPaidRoulette` в B.5 сам идемпотентен). audit-запись и `AuditSource.PRIZE_POOL_INCREMENT` добавятся в B.4 вместе с Alembic-миграцией whitelist-а. 14 unit-тестов: floor-округление (3), все 3 валюты (1 параметризованный, 3 кейса), result-shape (3), 0-фильтр (3), накопление (1), изоляция валют (1), command-shape (2). Checkpoint 2 — push после commit-а.
- [ ] **B.3 — Persistence** (`src/pipirik_wars/infrastructure/db/`): таблица `prize_pool_balance` (`id BIGSERIAL`, `currency VARCHAR(16) UNIQUE NOT NULL CHECK (...)`, `balance_native NUMERIC(38,0) NOT NULL CHECK >= 0`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`) + Alembic-миграция `0027_prize_pool_balance` с initial-seed-row на каждую `Currency`; ORM `PrizePoolBalanceORM` + `SqlAlchemyPrizePoolRepository` имплементация порта (`get_current` → SELECT all currencies → `PrizePool.from_rows(...)`; `apply_increment` → atomic UPDATE с `balance_native = balance_native + amount` + `RETURNING`). 8+ integration-тестов (round-trip, atomic increment под concurrent-writers, currency isolation, > 0 invariant). _Note:_ для 4.1-B можно остановиться на одной таблице — отдельный audit-trail (`prize_pool_audit`) добавится в B.4 / 4.1-C.
- [ ] **B.4 — Audit-source `prize_pool_increment`** (`src/pipirik_wars/domain/audit/sources.py` + Alembic CHECK): расширить `audit_log_source_whitelist` строкой `'prize_pool_increment'` (миграция `0027` или `0028`); audit payload включает `currency`, `amount_native`, `donation_idempotency_key`, `pool_after_native`; применяется в `RecordDonation`. 4+ unit-тестов записей.
- [ ] **B.5 — Интеграция с `SpinPaidRoulette`-flow:** после `IPaymentLedger.charge(...)` (existing 4.1-A logic) добавить вызов `RecordDonation.execute(...)` с тем же `idempotency_key` (suffix `:donation` для dedup-prefix-а). Cohesive — донат должен записаться один раз per-charge, при успешном `charge` + при retry того же `tg_payment_charge_id`. Integration-тест end-to-end: 9⭐ pack-10 → +0.9⭐ в пул (или 1⭐ если округлять вверх — TODO(balance) уточнить, в ГДД §12.6.1 «10% от каждого донат-зачисления»; стартую с floor-division `// 10`).
- [ ] **B.6 — Composition root** (`bot/main.py`): новый `prize_pool: IPrizePoolRepository` + `record_donation: RecordDonation` поля Container-а; инстанцирование `SqlAlchemyPrizePoolRepository(uow=uow)` и `RecordDonation(uow=uow, prize_pool=prize_pool, audit=audit, clock=clock)`; проброс `record_donation` в `SpinPaidRoulette` (расширение его конструктора; **breaking change** для unit-тестов — обновить `tests/unit/application/monetization/test_spin_paid_roulette.py` + `_container_with_fakes()`).
- [ ] **B.7 — `make ci` локально:** ruff + `mypy --strict` + import-linter (4 contracts kept) + pytest зелёный + coverage gate (≥ 80%).
- [ ] **B.8 — Финальный док-коммит:** `history.md` запись 4.1-B + `current_tasks.md` пересборка под старт **Спринта 4.1-C** «Лот-генератор + крипто-приз в рулетке».
- [ ] Открыть PR в `main` по шаблону `.github/pull_request_template.md` — PR #129.
- [ ] Дождаться зелёного GitHub CI.

---

## 🔗 Что ровно сейчас в работе

> Сюда пиши **дельту** к плану: что именно меняешь, какие use-cases / порты / handler-ы / тесты затронуты.

**Текущий PR — 4.1-B «Призовой пул + persistence + audit»** — второй PR Спринта 4.1 (Фаза 4 «Монетизация и масштаб»). Стартует от свежего `main` после мерджа PR #128 (закрытие 4.1-A).
- **На `main`:** Спринт 3.6 закрыт (PR #127, `b684679`), Спринт 4.1-A закрыт (PR #128).
- **Скоуп 4.1-B:** domain `PrizePool` агрегат + `TonNanoAmount`/`UsdtDecimalAmount` VO + `IPrizePoolRepository` порт + `RecordDonation` use-case (10% от донат-зачисления → пул, идемпотентно) + persistence (`prize_pool_balance` + Alembic `0027` + ORM + repository) + audit-source `prize_pool_increment` + интеграция в `SpinPaidRoulette`-flow + composition root. **Без** TON Connect / USDT-провайдера / лот-генератора / `ClaimPrize` — это следующие PR-ы (4.1-C…F).
- **Открытые блокеры:** нет.
- **После мерджа PR #129:** старт **Спринта 4.1-C** «Лот-генератор + крипто-приз в рулетке» (задачи 4.1.7, 4.1.8).

---

## 🛑 Известные блокеры / открытые вопросы PR-а

- **Phase-3 multi-membership ограничение** (наследие 3.6-A). В Phase 3 игрок может состоять максимум в **одном** клане (`UNIQUE` constraint на `clan_members.player_id` ещё с миграции `0006_clan_members`). Поэтому `count_active_for_player` фактически возвращает `0` или `1`, и `tribe_bonus_cm ∈ {0, cm_per_tribe}`. Интерфейс готов к Phase 4+ (multi-membership), но реальный `+131 см cap` будет достигаться только после снятия `UNIQUE`-constraint и реализации UI «вступить в племя × N» (вне скоупа Спринта 4.1).
- **Опциональный hint `oracle-no-tribes-hint`** (3 нулевых `/predict` подряд → «*вступай в новые племена и получай больше см*») — **не реализован** в 3.6-B. Помечен как feature-flag `oracle.show_no_tribes_hint` (default `false`). Реальная реализация требует трекинга последних 3 invocations — отдельный enhancement.
- **`crypto_lot` — реальный розыгрыш отложен до 4.1-C.** В рулетке `crypto_pool_empty=True` (всегда) в use-case-е → вес `CRYPTO_LOT` перетекает на `LENGTH` в picker-е (для free и paid-варианта). До запуска 4.1-C (лот-генератор + `PrizePool`-driven) `crypto_lot` никогда не выпадет в продакшне, но result-карточки `roulette-{free,paid}-result-*-crypto-lot` готовы и snapshot-тестированы.
- **Не-LENGTH исходы рулетки (ITEM/SCROLL_REGULAR/SCROLL_BLESSED) — без INSERT в инвентарь.** `RouletteSpinRepository.record(spin)` пишет `kind` + `length_cm=NULL`; audit-payload не содержит `target_id`. Реальный выбор предмета/скролла + INSERT в `items`/`scrolls` — задача отдельного спринта «инвентарь + рулетка интеграция» (после 4.1).
- **`AuditAction.SCROLL_DROP` всё ещё audit-only без write-through в инвентарь** — наследие предыдущих спринтов. Рейды и PvE дропают скроллы только в `audit_log`, без `INSERT` в `scrolls`-таблицу. Запланировано как отдельная задача после Спринта 4.1.
- **Реальный TG Stars-провайдер (skeleton 4.1-A bot-handler).** Skeleton handler принимает `successful_payment` от Telegram, но без подписания payload-а финансовый callback потенциально подделываем. В 4.1-D (TON Connect) добавим signature-верификацию payload-а и серверную сверку (provider-id ⇄ idempotency_key). До этого момента — **только staging/dev**, не запускать в prod.
- **Округление 10%-донат-комиссии:** ГДД §12.6.1 пишет «10% от каждого донат-зачисления → пул», но не уточняет округление при `amount % 10 != 0`. Стартую с `floor-division (// 10)` (= в пользу платформы; пользователь не теряет, потому что увидит точную сумму взимания только на стороне Telegram). Если на review будет фидбек — поменяю на `round half up`.

---

## 📌 Последний коммит на ветке

> Обновляется автоматически перед каждым `git push`. После `git log --oneline -1` — short sha + subject.

`21c21c0` — `Merge pull request #128 from Pipirkawar/devin/1778406997-sprint-4-1-A-paid-roulette-skeleton` (база ветки 4.1-B).
