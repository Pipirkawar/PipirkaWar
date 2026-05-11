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
- **D.8.a (этот коммит):** Domain VO `StarsPayload(pack_value: str, idempotency_seed: str)` (frozen+slots, `idempotency_seed` regex `[A-Za-z0-9_-]{16,32}`) + port `ITgStarsPayloadVerifier.verify(*, raw_payload, provider_payment_id, amount_native, currency) -> StarsPayload` (sync, HMAC-проверка без I/O) + error `InvalidStarsPayloadError(reason, payload_len)` + ре-экспорт из `domain/monetization/__init__.py` + 43 unit-теста в `tests/unit/domain/monetization/test_stars_payload.py`. Ни одного application-/infra-writeа.

## На каком файле / задаче остановился
- Закончил D.8.a; D.7 + D.8.a готовы. Следующий — **D.8.b «Infrastructure `HmacTgStarsPayloadVerifier` + `TgStarsSettings`»** (HMAC-SHA256 поверх `provider_id|idempotency_key|amount|currency`, pydantic-settings `SecretStr secret`, 8+ unit-тестов на golden HMAC).
- D.8.a-контракт для D.8.b: VO `StarsPayload(pack_value: str, idempotency_seed: str)` выводится из `ITgStarsPayloadVerifier.verify(...)`. Реализация в D.8.b живёт в новом пакете `src/pipirik_wars/infrastructure/payments/tg_stars/` (рядом с `ton_rpc/` из D.5). Опирается на `Currency.STARS`, но в сигнатуре порта оставлен аргумент `currency: Currency`, чтобы в будущем переиспользовать такой же порт для TON/USDT-сценариев.
- *Note for D.10.c:* refund-ветка пока рендерит `actual_fee_native=0` (placeholder) — `ClaimPrizeResult.refund_*` контракт расширим в D.10.c.
- Где брать ТЗ: `docs/current_tasks.md` чек-лист D.8.a–D.8.c (бывший «долг 4.1-A»); `docs/development_plan.md` Спринт 4.1, задача 4.1.2 (TON Connect) + 4.1.4 (антифрод/idempotency).
- Composition root (`bot/main.py`) — пока не трогаем: подключение `HmacTgStarsPayloadVerifier` + `TgStarsSettings` + `TonRpcAdapter` / `TonRpcFeeEstimator` / `JettonUsdtProvider` + `link_wallet` + `claim_prize` + expire-cron отложено на **D.10.c** (composition-root-коммит).

## Состояние ветки
- Ветка: `devin/1778501374-sprint-4-1-D-ton-connect-usdt-claim-prize`
- База: `main` (= `db8e630 Merge pull request #131`)
- Предыдущий коммит: `607feb0 feat(4.1-D): D.7.d — регистрация claim_prize_router + smoke-тесты`.
- Последний коммит (этот): `feat(4.1-D): D.8.a — Domain VO StarsPayload + port ITgStarsPayloadVerifier + InvalidStarsPayloadError + 43 теста`.
- Незакоммиченные изменения: нет (после коммита).
- CI прогонялся локально: ДА, `make ci` зелёный на `607feb0` (приёмка 2026-05-11): **5915 passed, 2 skipped, coverage 95.62%**. На текущем коммите (D.8.a) — ruff/format/mypy/import-linter зелёные точечно + 267 монетизация-unit-тестов проходят в 0.5s; полный `make ci` отложен на D.11.
- GitHub CI: не открыт PR (по протоколу — PR откроется после D.13/D.14). Прежний прогон D.6 на GitHub не нужен — workflow `paths-ignore: ['docs/**', '**.md', 'AGENT_HANDOFF.md']` ignored docs-коммиты, а функциональные пуши до открытия PR-а в `on: pull_request`-trigger не попадают.

## Команды для следующего агента
- Поднять окружение: см. README.md «Локальная разработка» (`python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" && pre-commit install`).
- Прогнать CI: `make ci`.
- Запустить только D.5-тесты: `pytest tests/unit/infrastructure/payments/ton_rpc/ -q --no-cov`.
- Запустить только D.6-тесты: `pytest tests/unit/bot/handlers/test_link_wallet.py tests/unit/bot/presenters/test_link_wallet.py -q --no-cov`.
- Запустить только D.7-тесты: `pytest tests/unit/bot/handlers/test_claim_prize.py tests/unit/bot/presenters/test_claim_prize.py -q --no-cov`.
- Запустить только D.8.a-тесты: `pytest tests/unit/domain/monetization/test_stars_payload.py -q --no-cov`.
- Следующий шаг (D.8.b) — создать пакет `src/pipirik_wars/infrastructure/payments/tg_stars/` с `settings.py` (в стиле `infrastructure/payments/ton_rpc/settings.py` из D.5, pydantic-settings + SecretStr) + `verifier.py` (HmacTgStarsPayloadVerifier, HMAC-SHA256, constant-time `hmac.compare_digest`).

## Известные блокеры / открытые вопросы
- `lot_ttl_seconds` для RESERVED-таймаута (D.9.a) — пока не зафиксирован; стартую с гипотезы `48h = 172_800`, на ревью можем поменять.
- `tg_stars.secret` (D.8.b) — ожидается env-переменной (предложение: `TG_STARS_PAYLOAD_HMAC_SECRET`, alias по ENV_PREFIX `pipirik_tg_stars__`). В settings хранится как `SecretStr`; реальный secret пробросится в ops/runbook-е в D.12.
- ORM-CHECK whitelist-sync test guard — backlog из 4.1-C.
- **D.5 design notes для следующих шагов (D.10):**
  - `TonRpcAdapter._build_*_boc(...)` — на текущем этапе **текстовый стаб**, не реальный TEP-67/TEP-74 BOC. Реальная сериализация + Ed25519-подпись запланированы на D.10.b. Контракт `client.send_boc(signed_boc_base64)` не изменится — заменим только тело stub-методов.
  - `ITonRpcClient` — нет реальной HTTP-имплементации. До D.10.a в проде продолжает работать `InMemoryFeeEstimator` (4.1-C), а D.5-классы существуют «в коробке» только для unit-тестов.
  - `TonRpcAdapter._derive_query_id(...)` использует детерминированный hash без `hashlib` — на D.10.b заменим на `hashlib.blake2b(idempotency_key)` + связь с `IIdempotencyKey`-namespace-ом.
