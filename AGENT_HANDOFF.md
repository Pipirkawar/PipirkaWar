# AGENT HANDOFF — Спринт 4.1-F (шаг F.0/F.12)

> Этот файл — временный safety-net. Обновляется в том же коммите, что и основные изменения, и лежит в ветке пока есть незаконченная работа. Удали его отдельным коммитом перед открытием PR-а.

## Что я сделал в этой сессии

- **Приёмка по 7-шаговому протоколу из CONTRIBUTING.md** (HANDOFF отсутствовал → git fetch → доки → `make ci` baseline → артефактов нет → current_tasks.md перерасписан под 4.1-F → старт F.0).
- **F.0** (этот коммит) — Snapshot pivot + sticky `AGENT_HANDOFF.md` под старт Спринта 4.1-F. `current_tasks.md` перерасписан: чек-лист F.0–F.12, «Текущая позиция» обновлена, открытые блокеры из 4.1-E переразложены под 4.1-F (главный таргет — замена `SandboxTonConnectVerifier`-stub на production).

## На каком файле/задаче остановился

- Файл: следующий шаг — `tests/unit/bot/handlers/test_roulette_paid.py` (F.1: fix flaky `test_invalid_payload_logs_machine_readable_reason`).
- Что планировал дальше: F.1 → F.2 (Domain VO `TonProof` + ошибки) → F.3 (port `INonceStore`) → F.4 (`RequestLinkWalletProof`-use-case) → F.5 (`TonConnectProductionVerifier` в infrastructure) → F.6 (persistence nonce-store + Alembic) → F.7 (composition root + config-flag) → F.8 (bot-handlers `/link_wallet` rebuild) → F.9 (smoke-test через `httpx.MockTransport`) → F.10 (`make ci` зелёный) → F.11 (doc-sync + history.md +1) → F.12 (remove HANDOFF + open PR).
- Где брать ТЗ: `docs/development_plan.md` §7 (Спринт 4.1, задача 4.1.2 «TON Connect: фикс длина за TON»); `docs/current_tasks.md` (этот PR-чек-лист F.0–F.12); `docs/game_design.md` §12.5/§12.6 (Telegram Stars + крипто-призовой пул); официальная спецификация TON Connect 2.0 sign-message: https://docs.ton.org/develop/dapps/ton-connect/sign.

## Состояние ветки

- Ветка: `devin/1778589416-sprint-4-1-F-real-ton-connect-verifier`
- База: `main = 5ee1a84` (merge PR #133 «Спринт 4.1-E»)
- Последний коммит: `(F.0 — этот, sha будет известен после commit-а)` — `docs(4.1-F): F.0 — snapshot pivot + sticky AGENT_HANDOFF под старт 4.1-F`.
- Незакоммиченные изменения: да — `docs/current_tasks.md` (перерасписан под 4.1-F) + `AGENT_HANDOFF.md` (создан).
- CI прогонялся? Да, локальный `make ci` зелёный 6590 passed + 2 skipped с одним известным flaky-тестом `test_invalid_payload_logs_machine_readable_reason` (см. F.1).

## Команды для следующего агента

- Поднять окружение: см. `README.md` «Локальная разработка» (`python3.12 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" && pre-commit install`).
- Прогнать CI: `make ci` (lint + typecheck + imports + tests).
- Запустить только нужные тесты: `pytest tests/unit/bot/handlers/test_roulette_paid.py -q --no-cov`.
- Запустить F.1-flake в полном прогоне: `make test` (~9 минут).
- Проверить flake в изоляции: `pytest tests/unit/bot/handlers/test_roulette_paid.py::TestHandleSuccessfulPayment::test_invalid_payload_logs_machine_readable_reason -v --no-cov` (всегда зелёный).

## Известные блокеры / открытые вопросы

- **TTL nonce + max-age timestamp-window** — текущие гипотезы 600 секунд (10 минут) для обоих. Будут зафиксированы в `config/balance.yaml::monetization.ton_connect` в F.7.
- **Whitelist доменов** — будут зафиксированы в `config/balance.yaml::monetization.ton_connect.allowed_domains` в F.7.
- **JSON-формат `proof: str`** — TON Connect 2.0 spec возвращает `ton_proof` как объект `{ timestamp, domain: { lengthBytes, value }, payload, signature, state_init }`. В нашем интерфейсе `proof: str` будет JSON-string этого объекта + добавочно `public_key_hex` (из wallet-info), либо весь wallet-response. Решение зафиксируется в F.2 (VO `TonProof`).
- **Flaky `test_invalid_payload_logs_machine_readable_reason`** — закрывается в F.1, подробности в `current_tasks.md::Известные блокеры`.
