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
- **D.8.b (этот коммит):** Infrastructure `HmacTgStarsPayloadVerifier` (`src/pipirik_wars/infrastructure/payments/tg_stars/verifier.py`) — реализация порта `ITgStarsPayloadVerifier` поверх HMAC-SHA256. Payload-формат v1: `<version>:<pack_value>:<seed>:<hmac_b64url>`, HMAC покрывает `version|pack_value|seed|amount|currency` (NUL-разделённый контекст). Метод-пара `serialize(...)` / `verify(...)`. `provider_payment_id` — non-empty-проверка (`bad_provider_id`), в HMAC не входит (не известен на момент выпуска инвойса). `TgStarsSettings` (`pydantic-settings` prefix `TG_STARS_`, обязательный `secret: SecretStr`). Сравнение — `hmac.compare_digest` (constant-time). 51 unit-тест (11 settings + 40 verifier: format, golden-HMAC, round-trip, 12 failure-modes, port-conformance). Ни одного application-writeа.

## На каком файле / задаче остановился
- Закончил D.8.b; D.7 + D.8.a + D.8.b готовы. Следующий — **D.8.c «Wire в `successful_payment`-handler 4.1-A»**: в `bot/handlers/roulette_paid.py` вызывать `tg_stars_verifier.verify(raw_payload=payment.invoice_payload, provider_payment_id=payment.telegram_payment_charge_id, amount_native=payment.total_amount, currency=Currency.STARS)` **перед** `SpinPaidRoulette.execute(...)`; на `InvalidStarsPayloadError` — отказ платежа + structured-log + локализованный ответ + 4-6 unit-тестов.
- D.8.b-контракт для D.8.c: `HmacTgStarsPayloadVerifier` живёт в `infrastructure/payments/tg_stars/`, из handler-а он обращается по порту `ITgStarsPayloadVerifier`. DI-вход в handler — по той же схеме, что `spin_paid_roulette` (см. линию 348 в `bot/handlers/roulette_paid.py`).
- Отдельно в D.8.c: handler `handle_pre_checkout_query` (тоже в `roulette_paid.py`, линия ~302) **тоже хорошо бы** проверять HMAC; но это вынесем в следующий спринт, в D.8.c фокус только на `successful_payment`.
- D.8.c подводный камень: сейчас invoice выдаётся через `invoice_payload_for(pack)` (`presenters/roulette_paid.py:144`), который возвращает просто `paid_roulette:<pack>`. Нужно заменить на подписанный формат. Вариант (выбран): оставить старый `invoice_payload_for(pack)` как deprecated-fallback (верификатор отказывает в verify(...) на v0-payload-е), в handler invoice-выдачи (`_send_invoice`, линия 233) вызывать `tg_stars_verifier.serialize(pack_value=pack.value, idempotency_seed=secrets.token_urlsafe(18)[:24], amount_native=cost_stars, currency=Currency.STARS)`.
- *Note for D.10.c:* refund-ветка пока рендерит `actual_fee_native=0` (placeholder) — `ClaimPrizeResult.refund_*` контракт расширим в D.10.c.
- Где брать ТЗ: `docs/current_tasks.md` чек-лист D.8.a–D.8.c (бывший «долг 4.1-A»); `docs/development_plan.md` Спринт 4.1, задача 4.1.2 (TON Connect) + 4.1.4 (антифрод/idempotency).
- Composition root (`bot/main.py`) — пока не трогаем: подключение `HmacTgStarsPayloadVerifier` + `TgStarsSettings` + `TonRpcAdapter` / `TonRpcFeeEstimator` / `JettonUsdtProvider` + `link_wallet` + `claim_prize` + expire-cron отложено на **D.10.c** (composition-root-коммит). Но в D.8.c всё равно придётся пробросить `tg_stars_verifier: ITgStarsPayloadVerifier` в `roulette_paid.py`-handler-ы (иначе wire не имеет смысла). Окончательная сборка в `bot/main.py::Container` — в D.10.c.

## Состояние ветки
- Ветка: `devin/1778501374-sprint-4-1-D-ton-connect-usdt-claim-prize`
- База: `main` (= `db8e630 Merge pull request #131`)
- Предыдущий коммит: `0c0253b feat(4.1-D): D.8.a — Domain VO StarsPayload + port ITgStarsPayloadVerifier + InvalidStarsPayloadError + 43 теста`.
- Последний коммит (этот): `feat(4.1-D): D.8.b — Infrastructure HmacTgStarsPayloadVerifier + TgStarsSettings + 51 тест`.
- Незакоммиченные изменения: нет (после коммита).
- CI прогонялся локально: ДА, `make ci` зелёный на `607feb0` (приёмка 2026-05-11): **5915 passed, 2 skipped, coverage 95.62%**. На текущем коммите (D.8.b) — ruff/format/mypy/import-linter зелёные точечно + 308 монетизация-unit-тестов проходят в 0.7s; полный `make ci` отложен на D.11.
- GitHub CI: не открыт PR (по протоколу — PR откроется после D.13/D.14). Прежний прогон D.6 на GitHub не нужен — workflow `paths-ignore: ['docs/**', '**.md', 'AGENT_HANDOFF.md']` ignored docs-коммиты, а функциональные пуши до открытия PR-а в `on: pull_request`-trigger не попадают.

## Команды для следующего агента
- Поднять окружение: см. README.md «Локальная разработка» (`python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" && pre-commit install`).
- Прогнать CI: `make ci`.
- Запустить только D.5-тесты: `pytest tests/unit/infrastructure/payments/ton_rpc/ -q --no-cov`.
- Запустить только D.6-тесты: `pytest tests/unit/bot/handlers/test_link_wallet.py tests/unit/bot/presenters/test_link_wallet.py -q --no-cov`.
- Запустить только D.7-тесты: `pytest tests/unit/bot/handlers/test_claim_prize.py tests/unit/bot/presenters/test_claim_prize.py -q --no-cov`.
- Запустить только D.8.a-тесты: `pytest tests/unit/domain/monetization/test_stars_payload.py -q --no-cov`.
- Запустить только D.8.b-тесты: `pytest tests/unit/infrastructure/payments/tg_stars/ -q --no-cov`.
- Следующий шаг (D.8.c) — подключить `ITgStarsPayloadVerifier` в `bot/handlers/roulette_paid.py`: (a) `_send_invoice` подписывает invoice_payload через `verifier.serialize(...)` + свежий seed через `secrets.token_urlsafe(...)`; (b) `handle_successful_payment` вызывает `verifier.verify(...)` перед `SpinPaidRoulette.execute(...)`, на `InvalidStarsPayloadError` — отказ + structured-log + локализованный ответ; (c) пробросить verifier как DI-аргумент в сигнатуру handler-ов. 4-6 unit-тестов на ветки.

## Известные блокеры / открытые вопросы
- `lot_ttl_seconds` для RESERVED-таймаута (D.9.a) — пока не зафиксирован; стартую с гипотезы `48h = 172_800`, на ревью можем поменять.
- `tg_stars.secret` (D.8.b) — ожидается env-переменной (предложение: `TG_STARS_PAYLOAD_HMAC_SECRET`, alias по ENV_PREFIX `pipirik_tg_stars__`). В settings хранится как `SecretStr`; реальный secret пробросится в ops/runbook-е в D.12.
- ORM-CHECK whitelist-sync test guard — backlog из 4.1-C.
- **D.5 design notes для следующих шагов (D.10):**
  - `TonRpcAdapter._build_*_boc(...)` — на текущем этапе **текстовый стаб**, не реальный TEP-67/TEP-74 BOC. Реальная сериализация + Ed25519-подпись запланированы на D.10.b. Контракт `client.send_boc(signed_boc_base64)` не изменится — заменим только тело stub-методов.
  - `ITonRpcClient` — нет реальной HTTP-имплементации. До D.10.a в проде продолжает работать `InMemoryFeeEstimator` (4.1-C), а D.5-классы существуют «в коробке» только для unit-тестов.
  - `TonRpcAdapter._derive_query_id(...)` использует детерминированный hash без `hashlib` — на D.10.b заменим на `hashlib.blake2b(idempotency_key)` + связь с `IIdempotencyKey`-namespace-ом.
