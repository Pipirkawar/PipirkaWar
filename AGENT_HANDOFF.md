# AGENT HANDOFF — Спринт 4.1-F (шаг F.7/F.12)

> Этот файл — временный safety-net. Обновляется в том же коммите, что и основные изменения, и лежит в ветке пока есть незаконченная работа. Удали его отдельным коммитом перед открытием PR-а.

## Что сделано в текущей ветке

**Ветка:** `devin/1778589416-sprint-4-1-F-real-ton-connect-verifier` от `main = 5ee1a84` (merge PR #133 4.1-E).

Закрытые шаги F.0–F.7:

- **F.0–F.5.c** (`e219a0c`…`f49a4a8`) — приёмка + F-plan + flaky-фикс + домейн-VO `TonProof` + порт `INonceStore` + `RequestLinkWalletProof`-use-case + `LinkWallet`-extend под anti-replay + `parse_ton_proof` + `build_canonical_message` + `TonConnectProductionVerifier`. Подробности — см. предыдущие версии этого файла + `docs/current_tasks.md`.
- **F.6.a** (`17e6424`) — Alembic `0038_ton_connect_nonces` (PK nonce VARCHAR(64), scope VARCHAR(128), 3 timestamp-колонки, 3 CHECK-инварианта, 2 индекса) + integration-тесты миграций.
- **F.6.b** (`ed117cc`) — `SqlAlchemyNonceStore` + ORM `TonConnectNonceORM` поверх `infrastructure/db/repositories|models/ton_connect_nonce.py`. `issue_nonce(scope, nonce, expires_at)` — `session.add()` + `flush()` + `IntegrityError → ValueError`. `consume_nonce(scope, nonce, now)` — атомарный CAS через `update().where(...).values(consumed_at=:now)` + `result.rowcount > 0`. DI: `uow: SqlAlchemyUnitOfWork`, `clock: IClock`. 12 integration-тестов покрывают happy-paths, error-paths, CAS-семантику, boundary-условия, DB-constraints. 517 integration-DB-тестов зелёные.
- **F.7** (этот коммит) — composition root + config-flag.

## F.7 — что именно вошло в этот коммит

**Новый `TonConnectSettings` (`infrastructure/payments/ton_connect/settings.py`):**
- env-prefix `BOT_TON_CONNECT_`, поля:
  - `verifier_mode: Literal["sandbox", "production"] = "sandbox"`
  - `allowed_domains: tuple[str, ...] = ("pipirik.example.com",)` — CSV-parser в `@field_validator("allowed_domains", mode="before")`.
  - `canonical_domain: str = "pipirik.example.com"` — попадает в `ton_proof.domain.value` через `RequestLinkWalletProof`.
  - `max_age_seconds: int = 600` (gt=0).
  - `clock_skew_seconds: int = 60` (ge=0).
  - `nonce_ttl_seconds: int = 600` (gt=0).
- Cross-field-validation в `model_post_init`: при `verifier_mode == "production"` whitelist должен быть non-empty И содержать `canonical_domain` — иначе ValueError. Это fail-loud при `Settings()` старте: production-verifier гарантированно отверг бы свой собственный proof, если бы домен advertised игроку не совпадал с whitelist-ом.

**`Settings.ton_connect`:** `Field(default_factory=TonConnectSettings)`. Не Optional — backward-compat default «sandbox + InMemoryNonceStore» собирается всегда.

**`bot/main.py::build_container`:**
- Импорты: добавлены `TonConnectProductionConfig`, `TonConnectProductionVerifier`, `SqlAlchemyNonceStore`, `RequestLinkWalletProof`, `RequestLinkWalletProofConfig`.
- Старый блок `ton_connect_verifier = SandboxTonConnectVerifier(...)` + `nonce_store = InMemoryNonceStore()` заменён на ветку:
  ```python
  if ton_connect_settings.verifier_mode == "production":
      ton_connect_verifier = TonConnectProductionVerifier(
          config=TonConnectProductionConfig(
              allowed_domains=...,
              max_age_seconds=...,
              clock_skew_seconds=...,
          ),
          clock=clock,
      )
      nonce_store = SqlAlchemyNonceStore(uow=uow, clock=clock)
  else:
      ton_connect_verifier = SandboxTonConnectVerifier(is_sandbox=ton_rpc_settings.is_sandbox)
      nonce_store = InMemoryNonceStore()
  ```
- Добавлен use-case `request_link_wallet_proof = RequestLinkWalletProof(nonce_store=nonce_store, clock=clock, config=RequestLinkWalletProofConfig(canonical_domain=..., nonce_ttl_seconds=...))`.
- `Container` расширен полем `request_link_wallet_proof: RequestLinkWalletProof`.

**Тесты:**
- `tests/unit/infrastructure/payments/ton_connect/test_settings.py` — 14 unit-тестов: defaults, production-mode-ok, production-mode-mismatch-domain-raises, production-empty-whitelist-raises, sandbox-ignores-whitelist-mismatch, CSV-parser (3 теста), field-invariants (5 тестов).
- `tests/unit/bot/test_container_ton_rpc.py::TestBuildContainerTonConnectModeSwitch` — 4 теста: sandbox-mode wiring + production-mode wiring + request_link_wallet_proof в обоих режимах.
- `tests/unit/bot/test_composition_root.py` — добавлен `request_link_wallet_proof_uc` в `_build_container_with_fakes`-фикстуру; `Container(...)` обновлён.

**Verification:**
- `ruff check` зелён.
- `mypy --strict` зелён (1050 source files, 0 issues).
- `lint-imports` зелён (4 contracts kept).
- `pytest tests/unit/bot/ tests/unit/infrastructure/payments/ton_connect/ tests/integration/db/test_ton_connect_nonce_store.py` — 1816 passed.
- `make ci` локально не запускал (он 8+ минут) — `make ci` finalize в F.10.

## На каком файле/задаче остановился

**Следующий шаг — F.8.a** «bot-handler `/link_wallet` phase-1»:
- Открыть `src/pipirik_wars/bot/handlers/link_wallet.py` (handler уже существует, расширяет phase-2 `/link_wallet_confirm`).
- Добавить новый `@router.message(Command("link_wallet"))`-handler (или подкоманду `/link_wallet <address>`, ровно по контракту).
- Внутри handler-а:
  1. Резолвить player_id из update.from_user.id (через `IPlayerRepository.find_by_tg_id` — паттерн ровно как в существующем `/link_wallet_confirm`).
  2. Парсить `address` из args; нормализовать в raw `workchain:hex64` (хелпер `parse_ton_address(...)` уже есть в `bot/handlers/_ton_addr.py` или нужно добавить).
  3. Парсить `currency` (TON / USDT, default TON).
  4. Вызвать `request_link_wallet_proof.execute(RequestLinkWalletProofCommand(...))`.
  5. Отрендерить локаль `link-wallet-prompt` с `{nonce}` + `{domain}` + `{expires_at_minutes}` (формат «у вас N минут»).
  6. На ValueError (валидация) — `link-wallet-invalid-address` или `link-wallet-invalid-currency`.
- `workflow_data[request_link_wallet_proof]` уже проброшен в dispatcher через `build_dispatcher(container)` — проверить в `bot/main.py::build_dispatcher`.

**После F.8.a:** F.8.b (расширить `/link_wallet_confirm` парсингом TonProof-JSON из proof-арга, передавать `scope` + `nonce` корректно из подписанного proof-а), F.8.c (RU/EN-локали), F.9 (httpx.MockTransport smoke), F.10 (make ci), F.11 (history.md +1), F.12 (remove AGENT_HANDOFF + open PR).

## Состояние ветки

- **Last commit (будет после `git commit`):** F.7 — `feat(4.1-F): F.7 — composition root + BOT_TON_CONNECT_VERIFIER_MODE`.
- **Files in this commit:**
  * Новый: `src/pipirik_wars/infrastructure/payments/ton_connect/settings.py`.
  * Новый: `tests/unit/infrastructure/payments/ton_connect/test_settings.py`.
  * Модифицированы: `src/pipirik_wars/infrastructure/settings/settings.py` (+`TonConnectSettings` import + `Settings.ton_connect` поле), `src/pipirik_wars/bot/main.py` (импорты + Container-поле + build_container-ветка), `tests/unit/bot/test_container_ton_rpc.py` (+`TestBuildContainerTonConnectModeSwitch`), `tests/unit/bot/test_composition_root.py` (+`request_link_wallet_proof_uc` в фикстуре), `docs/current_tasks.md`, `AGENT_HANDOFF.md`.
- **Pre-commit hooks:** должны быть зелёные (ruff + ruff-format + mypy + import-linter все запущены вручную и зелёные).
- **CI:** не запущен ещё (запустится после push-а).
- **Sticky:** этот файл живёт в ветке до F.12 (отдельный `chore: remove AGENT_HANDOFF` коммит перед открытием PR).

## Что НЕ сделано

- F.8.a/b/c — handlers + locales.
- F.9 — smoke-test через `httpx.MockTransport`.
- F.10 — `make ci` локально.
- F.11 — doc-sync (history.md +1 запись + переразложить current_tasks.md под 4.1-G).
- F.12 — снять AGENT_HANDOFF.md + открыть PR + дождаться CI.

## Ссылки

- TZ: `docs/current_tasks.md` (чек-лист F.0–F.12 + «Текущая позиция»).
- Спека TON Connect 2.0: https://docs.ton.org/develop/dapps/ton-connect/sign.
- Сессия: https://app.devin.ai/sessions/5d21d632cf2a44a2baa0cbf0d729c608.
- Предыдущая сессия: https://app.devin.ai/sessions/f9838cfa4a284470b3dde218866bbe61.
