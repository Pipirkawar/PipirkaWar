# AGENT HANDOFF — Спринт 4.1-F (шаг F.0/F.12)

> Этот файл — временный safety-net. Обновляется в том же коммите, что и основные изменения, и лежит в ветке пока есть незаконченная работа. Удали его отдельным коммитом перед открытием PR-а.

## Что я сделал в этой сессии

- **Приёмка по 7-шаговому протоколу из CONTRIBUTING.md** (HANDOFF отсутствовал → git fetch → доки → `make ci` baseline → артефактов нет → current_tasks.md перерасписан под 4.1-F → старт F.0).
- **F.0** (`e219a0c`) — Snapshot pivot + sticky `AGENT_HANDOFF.md` под старт Спринта 4.1-F. `current_tasks.md` перерасписан: чек-лист F.0–F.12, «Текущая позиция» обновлена, открытые блокеры из 4.1-E переразложены под 4.1-F (главный таргет — замена `SandboxTonConnectVerifier`-stub на production).
- **F-plan refined** (`e3151be`) — по запросу пользователя F.1–F.12 разбиты на 17 коммитов с под-шагами F.4.a/b, F.5.a/b/c, F.6.a/b, F.8.a/b/c. Каждый под-шаг — самостоятельный, атомарный для rollback-а, ревью-friendly. Аргументация в `docs/current_tasks.md::Чек-лист текущего PR`. Явно отсечён address-from-pubkey-recovery в backlog 4.1-G (optional по TON Connect 2.0-spec).
- **F.1** (`fce8468`) — Fix flaky `test_invalid_payload_logs_machine_readable_reason` в `tests/unit/bot/handlers/test_roulette_paid.py`: заменён `caplog.at_level(...)` на прямой `unittest.mock.patch("...._LOGGER.warning")` (как в `test_config.py::test_total_above_contract_limit_warns`). Не меняет prod-код. После фикса `make test` стабильно зелёный 6591 passed + 2 skipped (один прогон полного suite — 504 секунды).
- **F.2** (`d35be55`) — Domain VO `TonProof` + `TonConnectVerificationError`-таксономия. В `domain/monetization/value_objects.py` добавлен `TonProof(timestamp, domain_value, payload, signature_b64, public_key_hex, address, state_init_b64=None)` — фрозен-dataclass со строгими invariants: timestamp `int > 0`; domain RFC1123-host-like `[A-Za-z0-9._:\-]{1,253}`; payload ASCII-printable `[1,512]`; signature ровно 64 байта после base64-decode (Ed25519); pubkey 64 hex-сим (32 байта); address raw `workchain:hex64`; state_init optional valid base64. В `domain/monetization/errors.py` добавлен `TonConnectVerificationError(MonetizationDomainError)`-base + 6 sub-class-ов: `TonProofMalformedError(reason, raw_len)`, `TonProofExpiredError(proof_timestamp, now_timestamp, max_age_seconds)`, `TonProofDomainMismatchError(actual_domain, allowed_domains)`, `TonProofSignatureInvalidError(public_key_hex)`, `TonProofAddressMismatchError(actual_address, expected_address)`, `TonProofReplayedError(scope)`. Всё переэкспортировано через `domain/monetization/__init__.py`. Unit-тесты — `tests/unit/domain/monetization/test_ton_proof.py` (112 passed).
- **F.3** (этот коммит) — Domain port `INonceStore` + `FakeNonceStore` для тестов. В `domain/monetization/ports.py` добавлен Protocol `INonceStore` с двумя async-методами: `issue_nonce(*, scope, nonce, expires_at)` — записать выданный nonce; `consume_nonce(*, scope, nonce, now) -> bool` — атомарный CAS-consume (контракт: два параллельных вызова с одинаковым `(scope, nonce)` гарантируют ровно один `True` и один `False`). Документирован паттерн `UPDATE … WHERE consumed_at IS NULL AND expires_at > now() RETURNING …` как обязательный для F.6.b SQL-реализации. В `tests/fakes/nonce_store.py` создан in-memory `FakeNonceStore` с counter-ами `issue_calls` / `consume_calls` и helper-ами `is_known` / `is_consumed`. Переэкспорт через `tests/fakes/__init__.py`. Unit-тесты `tests/unit/fakes/test_nonce_store.py` (10 passed): покрывают happy-path, double-issue → ValueError, same-nonce-different-scope ok, consume-unknown/consumed/expired/wrong-scope → False, второй consume того же (scope, nonce) → False (CAS-семантика), граница `expires_at == now` → False.

## На каком файле/задаче остановился

- Файл: следующий шаг — `src/pipirik_wars/application/monetization/link_wallet_proof.py` (F.4.a: новый use-case `RequestLinkWalletProof`, который генерирует nonce и возвращает payload-инструкцию).
- Что планировал дальше: F.4.a (`RequestLinkWalletProof`-use-case) → F.4.b (extend `LinkWallet`) → F.5.a (TonProof-JSON-deserializer) → F.5.b (canonical-message-builder) → F.5.c (`TonConnectProductionVerifier`) → F.6.a (Alembic 0038) → F.6.b (`SqlAlchemyNonceStore`) → F.7 (composition root + config-flag) → F.8.a (`/link_wallet`-phase-1) → F.8.b (`/link_wallet_confirm`-phase-2) → F.8.c (локали RU/EN) → F.9 (smoke-test) → F.10 (`make ci` sanity, не отдельный коммит) → F.11 (doc-sync) → F.12 (remove HANDOFF + PR).
- Где брать ТЗ: `docs/development_plan.md` §7 (Спринт 4.1, задача 4.1.2 «TON Connect: фикс длина за TON»); `docs/current_tasks.md` (этот PR-чек-лист F.0–F.12 с под-шагами); `docs/game_design.md` §12.5/§12.6 (Telegram Stars + крипто-призовой пул); официальная спецификация TON Connect 2.0 sign-message: https://docs.ton.org/develop/dapps/ton-connect/sign.

## Состояние ветки

- Ветка: `devin/1778589416-sprint-4-1-F-real-ton-connect-verifier`
- База: `main = 5ee1a84` (merge PR #133 «Спринт 4.1-E»)
- Последний коммит: `(F.3 — этот, sha будет известен после commit-а)` — `feat(4.1-F): F.3 — domain port INonceStore + FakeNonceStore`.
- Незакоммиченные изменения: да — `src/pipirik_wars/domain/monetization/{ports.py,__init__.py}` + `tests/fakes/{nonce_store.py,__init__.py}` + `tests/unit/fakes/test_nonce_store.py` (новый) + `AGENT_HANDOFF.md` (этот файл).
- CI прогонялся? Локально: `pytest tests/unit/fakes/test_nonce_store.py -q --no-cov` → 10 passed; `ruff check` + `ruff format --check` + `mypy --strict` + `lint-imports` зелёные.

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
