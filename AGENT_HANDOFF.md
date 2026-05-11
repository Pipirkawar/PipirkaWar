# AGENT HANDOFF — Спринт 4.1-D (шаг D.6/D.15, после декомпозиции — шаг D.6 / D.15 + 14 микрошагов D.7.a–D.10.d)

> Этот файл — временный safety-net. Обновляется в том же коммите, что и основные изменения, и лежит в ветке пока есть незаконченная работа. Удали его отдельным коммитом перед открытием PR-а.

## Что сделано на ветке (хронологически)
- D.0: snapshot pivot `current_tasks.md` под старт 4.1-D + создан sticky `AGENT_HANDOFF.md`.
- D.1: Domain `Wallet(player_id, address, currency, linked_at)` aggregate (frozen+slots) + VO `TonAddress` / `UsdtJettonAddress` (raw + user-friendly formats) + порт `IWalletRepository(add_or_replace, get_by_player_and_currency)` + `ITonConnectVerifier(verify)` + `ITonPayoutAdapter(payout) -> PayoutResult` + ошибки `WalletNotLinkedError` / `WalletAlreadyLinkedError` + 37 unit-тестов.
- D.2: Application use-case `ClaimPrize(player_id, lot_id, recipient_address) -> ClaimPrizeResult` + `AuditAction.PRIZE_LOT_CLAIMED` / `AuditSource.PRIZE_LOT_CLAIMED` + `AuditAction.WALLET_LINKED` / `AuditSource.WALLET_LINKED` + 2 Alembic-миграции (0033, 0034: source whitelist) + ORM whitelist sync + 6 unit-тестов.
- D.3: Application use-case `LinkWallet` + `ITonConnectVerifier` proof verification + audit `WALLET_LINKED` + 4 unit-тестов.
- D.4: Persistence wallets — Alembic 0035 (таблица `wallets`, составной PK + CHECK) + `WalletORM` + `SqlAlchemyWalletRepository` (upsert через ON CONFLICT для Postgres+SQLite) + 6 integration-тестов.
- D.5: Infrastructure TON-RPC адаптеры. Новый пакет `src/pipirik_wars/infrastructure/payments/ton_rpc/` (`client.py`, `errors.py`, `settings.py`, `jetton.py`, `fee_estimator.py`, `adapter.py`) + тесты на `FakeTonRpcClient` (56 unit-тестов). Сборка signed-BOC — текстовый стаб до D.10.
- D.6: Bot-handler `/link_wallet` (личка-only) + callback `link_wallet:select:<ton|usdt>` + `/link_wallet_confirm <currency> <address> <proof>` + `LinkWalletPresenter` + 20 ключей `link-wallet-*` в RU/EN-локалях + 54 unit-теста.
- **Передача работы 2026-05-11 (docs-коммит `921c9c3`):** новый агент принял ветку у предыдущего; sticky-HANDOFF обновлён; чек-лист D.7–D.15 пере-декомпозирован на 14 микрошагов (D.7.a-d, D.8.a-c, D.9.a-d, D.10.a-d) для уменьшения размера коммитов под сокращённые лимиты агентских токенов.
- D.7.a (commit `632f6a1`): `ClaimPrizePresenter` (`src/pipirik_wars/bot/presenters/claim_prize.py`) + callback_data API (`claim_prize_callback_data` / `parse_claim_prize_callback_data` + `ClaimPrizeCallbackData(lot_id)`) + 20 ключей `claim-prize-*` в `locales/{ru,en}.ftl` (prompt + кнопка + 6 error-веток + success / refund + invalid-callback + toast) + 33 unit-теста (`tests/unit/bot/presenters/test_claim_prize.py`).
- D.7.b (commit `f91c18c`): `/claim_prize <lot_id>` handler — личка-only, pre-loads лот/кошелёк, вызывает ClaimPrize, рендерит success/refund + race-condition защита + 23 handler-теста.
- D.7.c (commit `541f89c`): callback `claim_prize:<lot_id>` handler + кнопка «Забрать приз» в roulette handlers + 29 handler-тестов.
- D.7.d (commit `607feb0`): регистрация `claim_prize_router` в `__init__.py` (после `roulette_paid_router`) + 3 smoke-теста в `test_register_routers.py`. **D.7 завершён.**
- **Передача работы 2026-05-11 (этот коммит):** новый агент принял ветку у предыдущего; выполнил все 7 шагов приёмки по CONTRIBUTING.md (HANDOFF → git fetch → доки → `make ci` зелёный 5915/2 sk, 95.62% cov на `607feb0` → sticky-обновление HANDOFF → current_tasks.md). Сразу в том же коммите — D.8.a.
- D.8.a (commit `0c0253b`): Domain VO `StarsPayload(pack_value: str, idempotency_seed: str)` (frozen+slots, `idempotency_seed` regex `[A-Za-z0-9_-]{16,32}`) + port `ITgStarsPayloadVerifier.verify(*, raw_payload, provider_payment_id, amount_native, currency) -> StarsPayload` (sync, HMAC-проверка без I/O) + error `InvalidStarsPayloadError(reason, payload_len)` + ре-экспорт из `domain/monetization/__init__.py` + 43 unit-теста.
- D.8.b (commit `ede95dd`): Infrastructure `HmacTgStarsPayloadVerifier` (`src/pipirik_wars/infrastructure/payments/tg_stars/verifier.py`) — реализация порта `ITgStarsPayloadVerifier` поверх HMAC-SHA256. Payload-формат v1: `<version>:<pack_value>:<seed>:<hmac_b64url>`, HMAC покрывает `version|pack_value|seed|amount|currency` (NUL-разделённый контекст). Метод-пара `serialize(...)` / `verify(...)`. `provider_payment_id` — non-empty-проверка (`bad_provider_id`), в HMAC не входит (не известен на момент выпуска инвойса). `TgStarsSettings` (`pydantic-settings` prefix `TG_STARS_`, обязательный `secret: SecretStr`). Сравнение — `hmac.compare_digest` (constant-time). 51 unit-тест (11 settings + 40 verifier: format, golden-HMAC, round-trip, 12 failure-modes, port-conformance). Ни одного application-writeа.
- **Передача работы 2026-05-11 (этот коммит):** новый агент принял ветку у предыдущего; выполнил все 7 шагов приёмки по CONTRIBUTING.md (HANDOFF → git fetch → доки → `make ci` зелёный 6002 passed, 95.64% cov на `ede95dd` → sticky-обновление HANDOFF → current_tasks.md). Сразу в том же коммите — D.8.c.
- **D.8.c (этот коммит):** Wire `ITgStarsPayloadVerifier` в `bot/handlers/roulette_paid.py`. Изменения:
  - **Port-расширение:** в `ITgStarsPayloadVerifier` добавлен метод `serialize(*, pack_value, idempotency_seed, amount_native, currency) -> str` (раньше был только в `HmacTgStarsPayloadVerifier`).
  - **Handler `handle_roulette_paid_buy`:** DI-параметр `tg_stars_verifier: ITgStarsPayloadVerifier`; вместо `invoice_payload_for(pack)` вызов `tg_stars_verifier.serialize(pack_value=pack.value, idempotency_seed=secrets.token_urlsafe(18), amount_native=cost_stars, currency=Currency.STARS)` (свежий seed per-invoice → блокирует replay).
  - **Handler `handle_successful_payment`:** DI-параметр `tg_stars_verifier`; вызов `verify(...)` **перед** `SpinPaidRoulette.execute(...)`; на `InvalidStarsPayloadError` — structured-log `WARNING` с `reason` / `payload_len` / `tg_payment_charge_id` + локализованная карточка `payment_invalid` + return (платёж списан Telegram-ом, refund — задача 4.1-E).
  - **Presenter `parse_invoice_payload`:** поддержка двух форматов — v0 legacy `paid_roulette:<pack>` (skeleton-handler 4.1-A) **и** v1 signed `<v>:<pack>:<seed>:<hmac>`. HMAC здесь НЕ проверяется (это роль verifier-а в successful_payment).
  - **Presenter `RoulettePaidPresenter.payment_invalid(*, locale)`:** новая карточка отказа.
  - **Локали:** новый ключ `roulette-paid-payment-invalid` в `locales/{ru,en}.ftl` с user-facing-generic-текстом (machine-readable reason — только в structured-log).
  - **Тесты:** 6 новых unit-тестов в `tests/unit/bot/handlers/test_roulette_paid.py` (idempotency_seed fresh-per-call + 4 ветки `InvalidStarsPayloadError` + legacy-v0-payload reject) + 2 новых в presenter-тестах (`payment_invalid` RU/EN) + 4 новых для v1-format в `parse_invoice_payload` + DI-aware existing tests. Добавлен `tests/fakes/tg_stars_verifier.FakeTgStarsPayloadVerifier` (детерминированный fake, error-injection).
  - **`make ci` зелёный:** 6014 passed + 2 skipped, coverage 95.63%, ruff/mypy/imports все зелёные.
- **Передача работы 2026-05-11 (этот коммит):** новый агент принял ветку у предыдущего; выполнил все 7 шагов приёмки по CONTRIBUTING.md (HANDOFF → git fetch → доки → `make ci` зелёный 6014 passed, 95.62% cov на `5ab5212` → sticky-обновление HANDOFF → current_tasks.md). Сразу в том же коммите — D.9.a.
- **D.9.a (этот коммит):** Domain-конфиг `PrizeLotConfig.reserved_ttl_seconds: int` (балансируемый refund-TTL для RESERVED-лота). Изменения:
  - **`domain/balance/config.py`:** новый `_Frozen`-подкласс `PrizeLotConfig` (поле `reserved_ttl_seconds: int = Field(ge=60, le=30 d)`); добавлен в `BalanceConfig` как обязательное поле `prize_lot: PrizeLotConfig` (после `roulette`, до `items_catalog`). Константа `_PRIZE_LOT_RESERVED_TTL_MAX_SECONDS = 30 * 24 * 3600` с пояснением «зачем 30 д. — sanity-cap, чтобы лот не зависал дольше P95-окна `IFeeEstimator` (7 d, §12.6.4)».
  - **`config/balance.yaml`:** добавлен корневой блок `prize_lot: { reserved_ttl_seconds: 172800 }` (48 h) с подробным комментарием-сценарием «выигрыш → reserve → claim/expire».
  - **`tests/unit/domain/balance/factories.py`:** в `valid_balance_payload()` добавлен `"prize_lot": {"reserved_ttl_seconds": 172_800}` — все 85 тестов через factory автоматически подхватили новое поле без изменений.
  - **Тесты:** 21 unit-тест в новом `tests/unit/domain/balance/test_prize_lot_config.py` (smoke-парсинг live-yaml + границы `[60, 30 d]` + 6 параметризованных valid-значений + типы int/float/str/bool/None + `extra="forbid"` + frozen). 1 hot-reload-тест в `tests/unit/infrastructure/test_balance_loader.py::TestReloadPrizeLot.test_reload_picks_up_new_reserved_ttl` (yaml `172_800 → 3600`, новый снимок подхватывает свежее значение, старый остаётся frozen).
  - **`make ci` зелёный:** 6036 passed + 2 skipped, coverage стабильна, ruff/mypy/import-linter все зелёные.

## На каком файле / задаче остановился
- Закончил D.9.a; D.7 + D.8 + D.9.a готовы. Следующий — **D.9.b «`IPrizeLotRepository.list_expired_reserved(now, ttl_seconds)`»**: добавить в порт + `SqlAlchemyPrizeLotRepository` метод поиска лотов в `RESERVED`, у которых `reserved_at <= now - ttl_seconds`. Нужен composite-индекс на `(status, reserved_at)` — отдельная Alembic-миграция в D.9.b или в D.9.c. 4+ integration-теста (sqlite + postgres). Затем D.9.c (use-case `ExpireReservedPrizeLots`), D.9.d (cron-entry).
- *Note for D.9.a:* pre-checkout-HMAC-валидация (handler `handle_pre_checkout_query`, `roulette_paid.py:~302`) перенесена в 4.1-E (см. plan); сейчас pre-checkout валидирует только `parse_invoice_payload` + amount, без HMAC.
- *Note for D.10.c:* refund-ветка пока рендерит `actual_fee_native=0` (placeholder) — `ClaimPrizeResult.refund_*` контракт расширим в D.10.c.
- *Note for D.10.c:* composition-root (`bot/main.py::Container`) пока не трогаем — `HmacTgStarsPayloadVerifier`-инстанс не собран; handler-параметр `tg_stars_verifier` пока бросит `MissingDependencyError` при реальном вызове, но это сборочный issue, не функциональный. Окончательная сборка в D.10.c.
- Где брать ТЗ: `docs/current_tasks.md` чек-лист D.9.a–D.10.d; `docs/development_plan.md` Спринт 4.1, задача 4.1.2 (TON Connect) + 4.1.4 (антифрод/idempotency).

## Состояние ветки
- Ветка: `devin/1778501374-sprint-4-1-D-ton-connect-usdt-claim-prize`
- База: `main` (= `db8e630 Merge pull request #131`)
- Предыдущий коммит: `5ab5212 feat(4.1-D): D.8.c — Wire ITgStarsPayloadVerifier into roulette_paid.py (serialize + verify) + 6 unit-тестов`.
- Последний коммит (этот): `feat(4.1-D): D.9.a — Balance prize_lot.reserved_ttl_seconds + Pydantic-схема + loader-hot-reload-тест`.
- Незакоммиченные изменения: нет (после коммита).
- CI прогонялся локально: ДА, `make ci` зелёный на текущем коммите (D.9.a): **6036 passed, 2 skipped**, ruff/mypy/import-linter все зелёные.
- GitHub CI: не открыт PR (по протоколу — PR откроется после D.13/D.14). Прежний прогон D.6 на GitHub не нужен — workflow `paths-ignore: ['docs/**', '**.md', 'AGENT_HANDOFF.md']` ignored docs-коммиты, а функциональные пуши до открытия PR-а в `on: pull_request`-trigger не попадают.

## Команды для следующего агента
- Поднять окружение: см. README.md «Локальная разработка» (`python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" && pre-commit install`).
- Прогнать CI: `make ci`.
- Запустить только D.5-тесты: `pytest tests/unit/infrastructure/payments/ton_rpc/ -q --no-cov`.
- Запустить только D.6-тесты: `pytest tests/unit/bot/handlers/test_link_wallet.py tests/unit/bot/presenters/test_link_wallet.py -q --no-cov`.
- Запустить только D.7-тесты: `pytest tests/unit/bot/handlers/test_claim_prize.py tests/unit/bot/presenters/test_claim_prize.py -q --no-cov`.
- Запустить только D.8.a-тесты: `pytest tests/unit/domain/monetization/test_stars_payload.py -q --no-cov`.
- Запустить только D.8.b-тесты: `pytest tests/unit/infrastructure/payments/tg_stars/ -q --no-cov`.
- Запустить только D.8.c-тесты: `pytest tests/unit/bot/handlers/test_roulette_paid.py tests/unit/bot/presenters/test_roulette_paid.py -q --no-cov`.
- Запустить только D.9.a-тесты: `pytest tests/unit/domain/balance/test_prize_lot_config.py tests/unit/infrastructure/test_balance_loader.py -q --no-cov`.
- Следующий шаг (**D.9.b — `IPrizeLotRepository.list_expired_reserved`**): добавить в порт `IPrizeLotRepository` метод `list_expired_reserved(*, currency, now, ttl_seconds, limit=100) -> list[PrizeLot]` (используем `reserved_at <= now - ttl_seconds AND status == RESERVED`). Реализация в `SqlAlchemyPrizeLotRepository` с composite-индексом на `(status, reserved_at)` (новая Alembic-миграция). 4+ integration-теста (создаём `RESERVED`-лот, прокручиваем clock, проверяем выборку). Затем D.9.c (use-case `ExpireReservedPrizeLots`), D.9.d (cron-entry через APS, DI в `bot/main.py::Container`). Полный гайд — в `docs/current_tasks.md`.

## Известные блокеры / открытые вопросы
- `reserved_ttl_seconds` для RESERVED-таймаута (D.9.a) — зафиксирован в `config/balance.yaml::prize_lot.reserved_ttl_seconds = 172800` (48 h). Pydantic-границы `[60, 30 d]`. На ревью геймдиза можем поменять — `hot-reload` без рестарта (см. `TestReloadPrizeLot.test_reload_picks_up_new_reserved_ttl`).
- `tg_stars.secret` (D.8.b) — ожидается env-переменной (предложение: `TG_STARS_PAYLOAD_HMAC_SECRET`, alias по ENV_PREFIX `pipirik_tg_stars__`). В settings хранится как `SecretStr`; реальный secret пробросится в ops/runbook-е в D.12.
- ORM-CHECK whitelist-sync test guard — backlog из 4.1-C.
- **D.5 design notes для следующих шагов (D.10):**
  - `TonRpcAdapter._build_*_boc(...)` — на текущем этапе **текстовый стаб**, не реальный TEP-67/TEP-74 BOC. Реальная сериализация + Ed25519-подпись запланированы на D.10.b. Контракт `client.send_boc(signed_boc_base64)` не изменится — заменим только тело stub-методов.
  - `ITonRpcClient` — нет реальной HTTP-имплементации. До D.10.a в проде продолжает работать `InMemoryFeeEstimator` (4.1-C), а D.5-классы существуют «в коробке» только для unit-тестов.
  - `TonRpcAdapter._derive_query_id(...)` использует детерминированный hash без `hashlib` — на D.10.b заменим на `hashlib.blake2b(idempotency_key)` + связь с `IIdempotencyKey`-namespace-ом.
