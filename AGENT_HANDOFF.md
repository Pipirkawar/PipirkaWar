# AGENT HANDOFF — Спринт 4.1-F (шаг F.8.b/F.12)

> Этот файл — временный safety-net. Обновляется в том же коммите, что и основные изменения, и лежит в ветке пока есть незаконченная работа. Удали его отдельным коммитом перед открытием PR-а.

## Что сделано в текущей ветке

**Ветка:** `devin/1778589416-sprint-4-1-F-real-ton-connect-verifier` от `main = 5ee1a84` (merge PR #133 4.1-E).

Закрытые шаги F.0–F.7 (из предыдущих сессий, последний коммит `ec9569a`):

- **F.0–F.5.c** — приёмка + F-plan + flaky-фикс + домейн-VO `TonProof` + порт `INonceStore` + `RequestLinkWalletProof`-use-case + `LinkWallet`-extend под anti-replay + `parse_ton_proof` + `build_canonical_message` + `TonConnectProductionVerifier`.
- **F.6.a** — Alembic `0038_ton_connect_nonces` + integration-тесты миграций.
- **F.6.b** — `SqlAlchemyNonceStore` + ORM `TonConnectNonceORM` + atomic-CAS-consume + 12 integration-тестов.
- **F.7** — composition root: `TonConnectSettings` (env `BOT_TON_CONNECT_*`) + `verifier_mode` switch + wired `RequestLinkWalletProof` use-case + 18 unit-тестов.

## Текущая сессия (2026-05-12, https://app.devin.ai/sessions/1d2123e96ad84f5baad3df4e85c25cfc)

Сессия подключилась после `ec9569a` (F.7). Выполнена 7-шаговая приёмка:

1. HANDOFF существует, прочитан целиком.
2. `git fetch` + ветка `devin/1778589416-sprint-4-1-F-real-ton-connect-verifier` — чистое состояние, нет незакоммиченных изменений.
3. Прочитан `CONTRIBUTING.md`, `README.md`, `docs/current_tasks.md`, `docs/development_plan.md` (релевантные секции 4.1-F).
4. `make ci` зелёный: 6846 passed + 2 skipped + 95.49% coverage; `ruff`/`mypy --strict`/`lint-imports` зелёные.
5. Артефактов нет — HANDOFF sticky, чек-лист отражает реальный git-лог.
6. `current_tasks.md` обновлён — добавлена «Передача работы 2026-05-12 (приёмка 4.1-F session 3)» секция.
7. Старт **F.8.a**.

## На каком файле/задаче остановился

**F.8.a закрыт в этой сессии.** Следующий шаг — **F.8.b** «bot-handler `/link_wallet_confirm <currency> <address> <proof-json>` phase-2»:
- Сейчас `bot/handlers/link_wallet.py::handle_link_wallet_confirm` принимает `proof: str` как sentinel-строку и передаёт в `LinkWalletCommand` с sentinel-ыми `scope=""` + `nonce=""`. Нужно вызвать `parse_ton_proof(raw_proof_arg) -> TonProof`, вынуть `nonce = proof.payload` + `domain.value` из proof-а, собрать `scope = f"link_wallet:{player_id}:{currency.value}"` (идентично F.4.a) и передать это в `LinkWalletCommand`.
- На `TonProofMalformedError` — рендер `link-wallet-confirm-invalid-proof` (уже существует).
- Существующие ветки (`WalletAlreadyLinkedError`, `TonProofInvalidError`, `TonProofReplayedError`) остаются.
- Обновить `tests/unit/bot/handlers/test_link_wallet.py::TestHandleLinkWalletConfirm` (happy-path с пропаршенным proof → scope+nonce передаются в use-case, malformed-proof → invalid-proof, sandbox-mode pass-through).

**После F.8.b:** F.8.c (RU/EN-локали с финальными текстами), F.9 (httpx.MockTransport smoke), F.10 (make ci), F.11 (history.md +1), F.12 (remove AGENT_HANDOFF + open PR).

## Состояние ветки

- **Last commit (планируемый после push):** `feat(4.1-F): F.8.a — bot-handler /link_wallet phase-1`. До этого: `ec9569a` (F.7).
- **Незакоммиченные изменения:** F.8.a-изменения (handler, presenter, `bot/main.py`, RU/EN locales, tests) + обновление этого файла + `docs/current_tasks.md`.
- **CI:** `make ci` зелёный после F.8.a: 6858 passed + 2 skipped + ~95% cov (было 6846 на F.7; +12 новых тестов).
- **Sticky:** этот файл живёт в ветке до F.12 (отдельный `chore: remove AGENT_HANDOFF` коммит перед открытием PR).
- **F.8.a выполнен в этой сессии**: bot-handler `/link_wallet` phase-1 + presenter + dispatcher-wiring + RU/EN локали-плейсхолдеры + 12 unit-тестов. `make ci` зелён: 6858 passed + 2 skipped (покрытие в норме).

## Что НЕ сделано

- F.8.b — `/link_wallet_confirm` TonProof-JSON parsing (извлечь `scope` + `nonce` из пропаршенного proof.payload + domain.value, передать в `LinkWalletCommand`).
- F.8.c — финальные RU/EN-локали `link-wallet-request-*`.
- F.9 — smoke-test через `httpx.MockTransport`.
- F.10 — `make ci` локально.
- F.11 — doc-sync (history.md +1 запись + переразложить current_tasks.md под 4.1-G).
- F.12 — снять AGENT_HANDOFF.md + открыть PR + дождаться CI.

## Команды для следующего агента

- Поднять окружение: см. README.md «Локальная разработка». На VM этой сессии venv уже создан в `.venv/`, deps установлены, pre-commit установлен.
- Прогнать CI: `source .venv/bin/activate && make ci`.
- Запустить только нужные тесты: `pytest tests/unit/bot/handlers/test_link_wallet.py -q`.

## Известные блокеры / открытые вопросы

- Flaky `test_invalid_payload_logs_machine_readable_reason` — закрыт в F.1; в полном `make ci`-прогоне стабильно зелёный.
- В остальном — нет.

## Ссылки

- TZ: `docs/current_tasks.md` (чек-лист F.0–F.12 + «Текущая позиция»).
- Спека TON Connect 2.0: https://docs.ton.org/develop/dapps/ton-connect/sign.
- Сессия: https://app.devin.ai/sessions/1d2123e96ad84f5baad3df4e85c25cfc.
- Предыдущая сессия: https://app.devin.ai/sessions/5d21d632cf2a44a2baa0cbf0d729c608.
