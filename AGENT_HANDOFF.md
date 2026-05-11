# AGENT HANDOFF — Спринт 4.1-D (шаг D.6/D.15)

> Этот файл — временный safety-net. Обновляется в том же коммите, что и основные изменения, и лежит в ветке пока есть незаконченная работа. Удали его отдельным коммитом перед открытием PR-а.

## Что сделано на ветке (хронологически)
- D.0: snapshot pivot `current_tasks.md` под старт 4.1-D + создан sticky `AGENT_HANDOFF.md`.
- D.1: Domain `Wallet(player_id, address, currency, linked_at)` aggregate (frozen+slots) + VO `TonAddress` / `UsdtJettonAddress` (raw + user-friendly formats) + порт `IWalletRepository(add_or_replace, get_by_player_and_currency)` + `ITonConnectVerifier(verify)` + `ITonPayoutAdapter(payout) -> PayoutResult` + ошибки `WalletNotLinkedError` / `WalletAlreadyLinkedError` + 37 unit-тестов.
- D.2: Application use-case `ClaimPrize(player_id, lot_id, recipient_address) -> ClaimPrizeResult` + `AuditAction.PRIZE_LOT_CLAIMED` / `AuditSource.PRIZE_LOT_CLAIMED` + `AuditAction.WALLET_LINKED` / `AuditSource.WALLET_LINKED` + 2 Alembic-миграции (0033, 0034: source whitelist) + ORM whitelist sync + 6 unit-тестов.
- D.3: Application use-case `LinkWallet` + `ITonConnectVerifier` proof verification + audit `WALLET_LINKED` + 4 unit-тестов.
- D.4: Persistence wallets — Alembic 0035 (таблица `wallets`, составной PK + CHECK) + `WalletORM` + `SqlAlchemyWalletRepository` (upsert через ON CONFLICT для Postgres+SQLite) + 6 integration-тестов.
- **D.5: Infrastructure TON-RPC адаптеры.**
  Новый пакет `src/pipirik_wars/infrastructure/payments/ton_rpc/` с подмодулями:
  - `client.py` — `ITonRpcClient` (Protocol: `run_get_method` / `send_boc` / `recent_fees`) + DTO (`RunGetMethodResult`, `BocSendResult`, `RecentFee`).
  - `errors.py` — `TonRpcCallError` (база) → `TonRpcTimeoutError`, `JettonResolutionError`; отдельный `UnsupportedPayoutCurrencyError(ValueError)`.
  - `settings.py` — `TonRpcSettings` (`pydantic-settings`, prefix `TON_RPC_`): `endpoint`, `api_key: SecretStr`, `is_sandbox`, `usdt_jetton_master`, `payout_wallet_address`, `request_timeout_seconds`, `fee_window_days`, fallback-buffers. Дефолты — testnet-friendly.
  - `jetton.py` — `JettonUsdtProvider(client, jetton_master_address)`: `resolve_wallet(owner) -> jetton_wallet_addr` через `runGetMethod('get_wallet_address')`, `build_transfer_payload(...) -> JettonTransferPayload` (TEP-74 op-code `0x0f8a7ea5` + валидации входов).
  - `fee_estimator.py` — `TonRpcFeeEstimator(client, settings)` implements `IFeeEstimator`: nearest-rank P95 от `client.recent_fees(...)` (STARS=0; пустая выборка / пустой адрес → fallback из settings).
  - `adapter.py` — `TonRpcAdapter(client, settings, jetton_provider)` implements `ITonPayoutAdapter`: маршрутизация по валюте (TON / USDT-jetton / STARS-fail), сборка signed-BOC-стаба (детерминированный текстовый формат до D.10), вызов `client.send_boc(...)`, возврат `PayoutResult(tx_hash, actual_fee_native)`.
  - Тесты: `tests/unit/infrastructure/payments/ton_rpc/` — `_fakes.py` (`FakeTonRpcClient` с очередями ответов и raise-hooks), `test_settings.py` (15 кейсов), `test_jetton.py` (14), `test_fee_estimator.py` (13), `test_adapter.py` (11). Всего **+56 unit-тестов**, все зелёные.
  - `make ci` зелёный: ruff clean, mypy 0 issues (971 файл), 4/4 import-contracts KEPT, **5792 passed / 2 skipped**, coverage **95.63%**.
- **D.6 (этот коммит): Bot-handler `/link_wallet` + `/link_wallet_confirm`.**
  - `src/pipirik_wars/bot/handlers/link_wallet.py` — три handler-а:
    - `/link_wallet` (личка-only) → prompt-карточка с inline-клавиатурой выбора валюты TON / USDT.
    - Callback `link_wallet:select:<ton|usdt>` → снять клавиатуру + показать локализованные инструкции (TON Connect deeplink-flow).
    - `/link_wallet_confirm <currency> <address> <proof>` → backend-вход в `LinkWallet.execute(...)`. На D.6 это «ручная» точка входа для теста; на D.10 её будет дёргать TON-Connect-bridge.
  - `src/pipirik_wars/bot/presenters/link_wallet.py` — `LinkWalletPresenter` + `link_wallet_callback_data` / `parse_link_wallet_callback_data` (formate `link_wallet:select:<ton|usdt>`, ≤ 64 байта).
  - `src/pipirik_wars/bot/handlers/__init__.py` — регистрация `link_wallet_router` после `lang_router`.
  - `locales/ru.ftl` + `locales/en.ftl` — 20 новых ключей `link-wallet-*` (prompt, инструкции, ошибки, success-варианты с параметрами `address` / `currency`).
  - Тесты: `tests/unit/bot/handlers/test_link_wallet.py` (29 кейсов) + `tests/unit/bot/presenters/test_link_wallet.py` (25). Всего **+54 unit-тестов**, все зелёные.
  - Обработка ошибок: `WalletAlreadyLinkedError` → ветка `already-linked`, `ValueError` (битый TON-Connect-proof) → ветка `invalid-proof`. Остальное ловит `ErrorHandlerMiddleware`.
  - `make ci` зелёный: ruff clean, mypy 0 issues (975 файлов), 4/4 import-contracts KEPT, **5848 passed / 2 skipped**, coverage **96%**.

## На каком файле / задаче остановился
- Файл: закончил D.6; следующий — **D.7 «Bot-handler /claim_prize <lot_id>»** (`src/pipirik_wars/bot/...`): команда + presenter «лот зарезервирован» + RU/EN + unit-тесты. На D.7 use-case `ClaimPrize.execute(...)` вызывается напрямую с `recipient_address` из `wallet_repo.get_by_player_and_currency(...)`.
- Где брать ТЗ: `docs/current_tasks.md` чек-лист D.7; ГДД §12.6.5 «Забрать приз».
- Composition root (`bot/main.py`) — пока не трогаем: подключение `TonRpcAdapter` / `TonRpcFeeEstimator` / `JettonUsdtProvider` + `link_wallet` + `claim_prize` отложено на **D.10** (single composition-root-коммит).

## Состояние ветки
- Ветка: `devin/1778501374-sprint-4-1-D-ton-connect-usdt-claim-prize`
- База: `main` (= `db8e630 Merge pull request #131`)
- Последний коммит: `feat(4.1-D): D.6 — Bot-handler /link_wallet + TON Connect deeplink + callback + 54 unit-тестов`
- Незакоммиченные изменения: нет (после коммита)
- CI прогонялся локально: ДА, **make ci зелёный** (5848 passed, 96% coverage).
- GitHub CI: только что запушено, ждём прогон.

## Команды для следующего агента
- Поднять окружение: см. README.md «Локальная разработка» (`pip install -e ".[dev]" && pre-commit install`).
- Прогнать CI: `make ci`.
- Запустить только D.5-тесты: `pytest tests/unit/infrastructure/payments/ton_rpc/ -q --no-cov`.
- Запустить только D.6-тесты: `pytest tests/unit/bot/handlers/test_link_wallet.py tests/unit/bot/presenters/test_link_wallet.py -q --no-cov`.

## Известные блокеры / открытые вопросы
- `lot_ttl_seconds` для RESERVED-таймаута (D.9) — пока не зафиксирован, нужно решить.
- ORM-CHECK whitelist-sync test guard — backlog из 4.1-C.
- **D.5 design notes для следующих шагов:**
  - `TonRpcAdapter._build_*_boc(...)` — на текущем этапе **текстовый стаб**, не реальный TEP-67/TEP-74 BOC. Реальная сериализация + Ed25519-подпись должна появиться вместе с реальным `ITonRpcClient`-имплементом в D.10. Контракт `client.send_boc(signed_boc_base64)` не изменится — заменим только тело stub-методов.
  - `ITonRpcClient` — нет реальной HTTP-имплементации. До D.10 в проде продолжает работать `InMemoryFeeEstimator` (4.1-C), а D.5-классы существуют «в коробке» только для unit-тестов.
  - `TonRpcAdapter._derive_query_id(...)` использует детерминированный hash без `hashlib` — на проде стоит заменить на криптографически-стойкий + связанный с `IIdempotencyKey`-namespace-ом.
