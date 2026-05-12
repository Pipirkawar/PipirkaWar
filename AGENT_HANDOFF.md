# AGENT_HANDOFF — Спринт 4.1-E «Админ-команды + лимиты выплат + 4.1-D backlog»

> **Sticky-mode**: этот файл обновляется в **каждом** коммите фичевой ветки `devin/1778559360-sprint-4-1-E-admin-payout-limits` параллельно с функциональными изменениями. Удаляется отдельным коммитом перед открытием PR. См. `CONTRIBUTING.md` §«Sticky AGENT_HANDOFF mode».

---

## Контекст

- **Активный PR**: 4.1-E «Админ-команды + лимиты выплат» (пятый PR Спринта 4.1).
- **Ветка**: `devin/1778559360-sprint-4-1-E-admin-payout-limits` (от свежего main `1601410` — после мерджа PR #132 «4.1-D TON Connect + USDT + ClaimPrize»).
- **База**: `main = 1601410`.
- **Сессия**: https://app.devin.ai/sessions/1b8e65d68a484110a22eef2af362aee7 (приёмка после E.12, работа E.13.a+; предыдущие — https://app.devin.ai/sessions/f1baa58dac484f88a557431fc74959bb E.10–E.12, https://app.devin.ai/sessions/ba3b3f787335465f995742b5aba6799c E.6–E.9). По указанию пользователя E.13 разбит на 5 под-шагов (E.13.a–E.13.e), каждый — отдельный коммит с push-ем, чтобы при обрыве сессии следующий агент видел freshest origin.

## Чек-лист 4.1-E (E.0 → E.20)

| Шаг | Описание | Статус |
|-----|----------|--------|
| **E.0** | Pivot `docs/current_tasks.md` под 4.1-E + создать sticky `AGENT_HANDOFF.md` | ✅ done |
| **E.1** | **P0 bug-1**: `TonRpcAdapter._fetch_seqno` — поддержка hex/decimal от TON Center (`int(value, 0)` + edge cases) + unit-тесты | ✅ done |
| **E.2** | **P0 bug-2**: `JettonUsdtProvider.resolve_wallet` — парсинг slice-base64-cell → TON-address через `BocCell`-decoder + unit/integration | ✅ done |
| **E.3** | Domain: `AdminAuditAction.{ADMIN_PRIZE_POOL_VIEWED, ADMIN_REFUND_LOT, ADMIN_FREEZE_PAYOUTS, ADMIN_UNFREEZE_PAYOUTS}` (без Alembic-CHECK — `admin_audit_log.action` не имеет CHECK-constraint-а) + unit-тесты | ✅ done |
| **E.4** | Domain: `PayoutFreeze` aggregate + `IPayoutFreezeRepository` port | ✅ done |
| **E.5** | Domain: `PayoutLimitConfig` VO + `IPayoutLimitChecker` port + `config/balance.yaml::monetization.payout_limit` | ✅ done |
| **E.6** | Application: `EvaluatePayoutLimit(player, currency, amount, now) -> Within \| OverLimit(retry_after)` (rolling-window через `IPrizeLotRepository.sum_claimed_in_window` + `oldest_claimed_at_in_window`) | ✅ done (`750de27`) |
| **E.7** | Application: `FreezePayouts(admin_id, reason)` / `UnfreezePayouts(admin_id)` use-cases (RBAC через `AdminCommandKind.FREEZE_PAYOUTS`/`UNFREEZE_PAYOUTS` + audit `ADMIN_FREEZE_PAYOUTS`/`ADMIN_UNFREEZE_PAYOUTS`) | ✅ done (`0ee165f`) |
| **E.8** | Application: `RefundLot(admin_id, lot_id, reason)` (RBAC через `AdminCommandKind.REFUND_LOT` + pool increment + double-audit) | ✅ done (`ded52b4`) |
| **E.9** | Application: `GetPrizePoolStatus(admin_id) -> StatusReport` (read-only + audit `ADMIN_PRIZE_POOL_VIEWED`) | ✅ done (`2b6b2cf`) |
| **E.11a** | Persistence: Alembic `0037` — `payout_freeze` singleton + `prize_lots.winner_id` + покрывающий индекс + `PayoutFreezeORM` + `SqlAlchemyPayoutFreezeRepository` + SQL `sum_claimed_in_window` / `oldest_claimed_at_in_window` + `ClaimPrize` передаёт `winner_id` + integration/unit-тесты | ✅ done (`b0b147c`) |
| **E.10** | Hook `EvaluatePayoutLimit` + freeze-check в `ClaimPrize.execute(...)` + new errors `ClaimPrizePayoutsFrozenError` / `ClaimPrizeOverLimitError` + composition root wires `SqlAlchemyPayoutFreezeRepository` + `EvaluatePayoutLimit` | ✅ done (`29de93b`) |
| **E.11b** | Persistence: queue (расширение `prize_lots.status=QUEUED` или отдельная таблица) + Alembic | ⏸️ skip (опционально; over-limit-ошибка отдаётся юзеру в E.12 c `retry_after`-инструкцией) |
| **E.12** | Bot-handler `/prize_pool` + presenter + локали RU/EN | ✅ done (`c42eee4`) |
| **E.13.a** | Presenter `RefundLotPresenter` + 10 локалей `admin-refund-lot-*` RU/EN | 🔄 in_progress (этот коммит) |
| **E.13.b** | Phase-1 handler `/refund_lot <lot_id> <reason>` + `RequestAdminConfirm`-wiring + unit-тесты | ⏳ pending |
| **E.13.c** | Phase-2 `dispatch_refund_lot` + `ConfirmDispatchDeps.refund_lot` + `CONFIRM_DISPATCHERS`-register + unit-тесты | ⏳ pending |
| **E.13.d** | Composition root `Container.refund_lot` + dispatcher workflow + router-register + handler-тесты | ⏳ pending |
| **E.13.e** | `make ci` + `pre-commit run --all-files` зелёные | ⏳ pending |
| **E.14** | Bot-handler `/freeze_payouts <reason>` + `/unfreeze_payouts` + TOTP-confirm + presenter + локали | ⏳ pending |
| **E.15** | Composition root: `bot/main.py::Container` + `build_dispatcher` пробрасывает в workflow-data | ⏳ pending |
| **E.16** | Smoke-тесты новых admin-flow-ов | ⏳ pending |
| **E.17** | Локальный `make ci` + `pre-commit run --all-files` зелёный | ⏳ pending |
| **E.18** | Doc-sync: `history.md` + `current_tasks.md` (последний коммит до PR) | ⏳ pending |
| **E.19** | Удалить `AGENT_HANDOFF.md` отдельным коммитом | ⏳ pending |
| **E.20** | PR + GitHub CI зелёным | ⏳ pending |

## Состояние ветки

- **Текущий коммит**: E.13.a (этот коммит) — `RefundLotPresenter` в `src/pipirik_wars/bot/presenters/admin_refund_lot.py` (10 методов: `usage`, `not_authorized`, `totp_not_configured`, `bad_lot_id`, `no_reason`, `confirm_issued`, `success`, `already_refunded`, `not_found`, `bad_transition`) + 10 локалей `admin-refund-lot-*` × RU/EN в конце `locales/ru.ftl` + `locales/en.ftl`. `fluent.syntax.parse(...)` на обоих файлах — 0 junk. Handler-а и dispatcher-а пока нет — они придут в E.13.b и E.13.c. Тесты на presenter не пишутся отдельно — presenter покрывается тестами handler-а (как в E.12 / `test_admin_prize_pool.py`). `make lint typecheck imports` зелёные.
- **Предыдущий коммит** (`c42eee4`): E.12 — bot-handler `/prize_pool` + presenter + локали RU/EN. Read-only admin-команда (без TOTP), доступ super_admin через RBAC use-case-а; рендерит per-currency-снимок (balance / active / reserved / claimed / refunded) + freeze-блок (frozen / unfrozen / by / at / reason). Composition root (`bot/main.py`) подключает `GetPrizePoolStatus(uow, admins, prize_pool_repo, prize_lot_repo, payout_freeze_repo, admin_audit, clock, authz)` + Container-поле `get_prize_pool_status` + dispatcher workflow-data. Новый router зарегистрирован в `bot/handlers/__init__.py` после `admin_setup_totp_router`. +6 unit-тестов (TestHandlePrizePool: non-private chat, missing identity, authz-error, render unfrozen, render frozen, default locale). Full pytest → 6540 passed, 2 skipped (+8 от E.10). `make lint typecheck imports` зелёные. E.11b решено пропустить — over-limit-ошибка просто рендерится юзеру с `retry_after`-инструкцией (queue добавим, если по UX-метрикам станет нужно).
- **Предыдущий коммит**: E.10 (`29de93b`) — hook freeze-check + EvaluatePayoutLimit в `ClaimPrize.execute(...)`. Новые domain-ошибки: `ClaimPrizePayoutsFrozenError` (frozen → reject, payout не вызывается), `ClaimPrizeOverLimitError` (over-limit → reject, retry_after). Use-case получил 2 новые зависимости `payout_freeze_repository` и `payout_limit_checker`. Порядок: lot check → freeze → limit → wallet → payout. Composition root (`bot/main.py`) теперь вызывает `SqlAlchemyPayoutFreezeRepository(uow)` + `EvaluatePayoutLimit(lot_repo, balance)` и пробрасывает в dispatcher (`payout_freeze_repository`, `payout_limit_checker`). +7 unit-тестов (TestClaimPrizeFreezeCheck, TestClaimPrizeOverLimitCheck, TestClaimPrizeCheckOrder). Full pytest → 6532 passed, 2 skipped (+6 от E.11a).
- **Предыдущий коммит (`b0b147c`)**: E.11a — Alembic-миграция `0037_payout_freeze_and_prize_lot_winner_id`: (1) singleton-таблица `payout_freeze` (id=1, is_frozen, frozen_by_admin_id, frozen_at, reason; CHECK-инварианты: singleton `id=1`, attrs-consistency, positive admin_id, non-empty reason; seed-row `is_frozen=FALSE`); (2) `prize_lots.winner_id BIGINT NULL` + CHECK `(status='claimed') OR (winner_id IS NULL)` + CHECK `winner_id > 0` + покрывающий индекс `(winner_id, currency, status, claimed_at)`. `PayoutFreezeORM` + `SqlAlchemyPayoutFreezeRepository(get_state, set_frozen, set_unfrozen)`. Расширен `IPrizeLotRepository.update_status(winner_id=...)` в порте + SQL-реализации + Fake. `ClaimPrize.execute(...)` теперь передаёт `winner_id=command.player_id`. SQL `sum_claimed_in_window` и `oldest_claimed_at_in_window` реализованы (вместо `NotImplementedError`). +7 integration-тестов payout_freeze + +7 integration-тестов sum/oldest window. `make lint typecheck imports` зелёные; full `pytest -q --no-cov` → 6526 passed, 2 skipped (+14 от E.9).
- **Предыдущий коммит (`2b6b2cf`)**: E.9 — application use-case `GetPrizePoolStatus` в `src/pipirik_wars/application/monetization/get_prize_pool_status.py`. Read-only по экономике + admin-audit `ADMIN_PRIZE_POOL_VIEWED` на каждый просмотр (non-idempotent — каждый view фиксируется в trail-е). RBAC через `ensure_admin_authorized(..., AdminCommandKind.GET_PRIZE_POOL)`. Эффекты в одной UoW: (1) `IPrizePoolRepository.get_current()` — pool snapshot; (2) `IPayoutFreezeRepository.get_state()` — freeze state; (3) `IPrizeLotRepository.count_by_status(currency, status)` × 3 валюты × 4 статуса = 12 быстрых COUNT-запросов (новый порт-метод). Output: tuple `CurrencyPoolStatus` в порядке Stars → TON → USDT + `PayoutFreeze`. Расширены порт `IPrizeLotRepository.count_by_status(currency, status) -> int` (новая семантика, не зависит от winner_id-схемы E.11 — SQL `COUNT(*) WHERE currency=? AND status=?`) + SQL-реализация в `SqlAlchemyPrizeLotRepository` + Fake. +7 unit-тестов use-case-а + +4 integration-теста SQL `count_by_status` + +2 fake-теста. `make lint typecheck imports` зелёные; full `pytest -q --no-cov` → 6512 passed, 2 skipped (+13 от E.8).
- **Предыдущий коммит (`ded52b4`)**: E.8 — application use-case `RefundLot` в `src/pipirik_wars/application/monetization/refund_lot.py`. Эффекты в одной UoW: (1) `IPrizeLotRepository.update_status(lot_id, REFUNDED)` (домен-state-machine: `ACTIVE|RESERVED → REFUNDED`; `CLAIMED` отвергается); (2) `IPrizePoolRepository.apply_increment(currency, +amount_native)` — gross-сумма (включая `fee_buffer_native`); (3) `IAuditLogger.record(PRIZE_LOT_REFUNDED)` с `source=ADMIN_REFUND`, `target_id="<lot_id>:refund"`, `actor_id=admin_id`, `idempotency_key=admin_refund_lot:<lot_id>`, payload включает `reason="admin"`, `reason_detail=<input.reason>`, `admin_id`, `prev_status`, `pool_after_native`; (4) `IAdminAuditLogger.record(ADMIN_REFUND_LOT)` с `before={status, currency, amount_native, fee_buffer_native}` / `after={status: "refunded", currency, amount_native, pool_after_native}`. Идемпотентность: `lot.status=REFUNDED` → pure no-op (`was_already_refunded=True`, без mutation/audit, `pool_after_native` = текущий баланс). TOTP-confirm — в bot-handler-е (E.14). +11 unit-тестов (auth-flow / RBAC-deny + admin-audit / валидация `lot_id<=0` + пустого reason / `PrizeLotNotFoundError` / happy ACTIVE→REFUNDED + полная проверка обеих audit-записей / happy RESERVED→REFUNDED / reason trimming / idempotent REFUNDED / terminal-block CLAIMED). `make lint typecheck imports` зелёные; полный suite — 6499 passed, 2 skipped, 1 flaky pre-existing (test_invalid_payload_logs_machine_readable_reason — caplog/xdist race, проходит в изоляции).
- **Предыдущий коммит (`0ee165f`)**: E.7 — `FreezePayouts`/`UnfreezePayouts` use-cases + `AdminCommandKind` расширен `GET_PRIZE_POOL`/`REFUND_LOT`/`FREEZE_PAYOUTS`/`UNFREEZE_PAYOUTS` (все super-admin-only) + `RoleBasedAdminAuthorizationPolicy._matrix` синхронизирован + +20 unit-тестов use-case-ов + +16 кейсов exhaustive-матрицы.
- **Предыдущий коммит (`750de27`)**: E.6 — application use-case `EvaluatePayoutLimit` (реализует доменный `IPayoutLimitChecker`) в `src/pipirik_wars/application/monetization/evaluate_payout_limit.py`. Алгоритм: (1) `cfg = balance.get().monetization.payout_limit.get(currency)`; если `None` → `Within(sys.maxsize)`; (2) `since = now - timedelta(days=cfg.window_days)`, `already = repo.sum_claimed_in_window(player_id, currency, since)`; (3) если `already+amount <= cfg.max_amount_native` → `Within(remaining = max - would_be)`; (4) иначе вытащить `oldest = repo.oldest_claimed_at_in_window(...)` → `OverLimit(retry_after = oldest + window_days, exceeded_by_native = would_be - max)`. Два новых порт-метода в `IPrizeLotRepository`: `sum_claimed_in_window(*, player_id, currency, since) -> int` и `oldest_claimed_at_in_window(*, player_id, currency, since) -> datetime | None`. SQL-реализация в `SqlAlchemyPrizeLotRepository` пока поднимает `NotImplementedError` — до шага E.11 в `prize_lots` нет `winner_id`-колонки; это осознанный выбор «fail-fast вместо silent-zero». `FakePrizeLotRepository` расширен sidemap-ом `winners: dict[lot_id, player_id]` (заполняется публичным методом `record_winner(lot_id, player_id)`) + реальными реализациями `sum_claimed_in_window` и `oldest_claimed_at_in_window`. +25 unit-тестов (11 на `EvaluatePayoutLimit`-use-case в `test_evaluate_payout_limit.py` + 14 на Fake-методы в `test_prize_lot_repo_payout_window.py`).
- **Предыдущий коммит (`cd31737`)**: E.5 — доменные VO результата `IPayoutLimitChecker.check(...)` (`PayoutLimitWithin(remaining_native)` / `PayoutLimitOverLimit(retry_after, exceeded_by_native)` — фрозен-VOи без identity, жёсткие `__post_init__`-invariant-ы: `remaining_native >= 0`, `exceeded_by_native >= 1`, `retry_after` TZ-aware, `bool` в `int`-поле отвергается) + sum-type `PayoutLimitCheckResult = Within | OverLimit` + порт `IPayoutLimitChecker.check(*, player_id, currency, amount_native, now) -> PayoutLimitCheckResult` (Protocol, async, omitted-from-config = unlimited → `Within(sys.maxsize)`) + pydantic-схема `domain/balance/config.py::PayoutLimitConfig`/`PayoutLimitsConfig`/`MonetizationConfig` (`currency ∈ {ton_nano, usdt_decimal}` — STARS отвергается; `window_days ∈ [1, 365]`; `max_amount_native >= 0`; уникальные валюты в `per_currency`; `BalanceConfig.monetization` обязательное поле). Обновлён `config/balance.yaml` (стартовые гипотезы: 50 USDT / 30 d + 10 TON / 30 d) и `tests/unit/domain/balance/factories.py::_build_valid_balance_dict()`. +`FakePayoutLimitChecker` (`tests/fakes/payout_limit_checker.py`, default=unlimited, per_key-override-ы, factory-callback, лог вызовов). +56 unit-тестов (`test_payout_limit_check.py` — 26, `test_payout_limit_config.py` — 25, `tests/unit/fakes/test_payout_limit_checker.py` — 5). Попутно убраны unused `# type: ignore[misc]` на фрозен-dataclass assignments в `test_payout_freeze.py` (mypy 1.20 больше не флагирует это как `misc`-ошибку).
- **Предыдущий коммит (`7c7acaf`)**: E.4 — доменный агрегат `PayoutFreeze` (frozen+slots, `is_frozen + frozen_by_admin_id + frozen_at + reason`, фабрики `.unfrozen()` / `.frozen(admin_id, at, reason)`, жёсткие invariant-ы: `is_frozen=True` → все три nullable заполнены; `is_frozen=False` → все три nullable `None`; `frozen_at` TZ-aware; `admin_id > 0`; `reason` непустой) + порт `IPayoutFreezeRepository(get_state, set_frozen(admin_id, at, reason), set_unfrozen())` (singleton, idempotent, async). Экспорты в `domain/monetization/__init__.py` обновлены. +`FakePayoutFreezeRepository` в `tests/fakes/payout_freeze_repo.py` (in-memory, log вызовов). +17 unit-тестов в `test_payout_freeze.py` (фабрики + invariant-ы + immutability + Fake-контракт).
- **Предыдущий коммит (`5fffc6f`)**: E.3 — расширение `AdminAuditAction`-enum 4 новыми значениями + 4 unit-теста.
- **Предыдущий коммит (`f5a7048`)**: E.2 — BoC-deserializer + `MsgAddressInt addr_std$10`-парсер в `boc.py` (`deserialize_boc(...)`, `parse_msgaddress_int_from_cell(...)`, `format_raw_address(...)` + выведены helper-ы `_parse_boc_header` / `_parse_cell_specs` / `_parse_one_cell_spec` / `_validate_ref_indices` / `_decode_d2` / `_recover_bits_count_and_strip_padding` / `_read_bits` / `_read_bit_slice` для читаемости); `JettonUsdtProvider.resolve_wallet` теперь parse-address-first с fallback на base64-BoC декодинг (+ permissive base64/base64url-decode). +29 новых unit-тестов: 7 на jetton-resolver (`TestJettonUsdtProviderResolveWalletDecodesBoc`), 11 на `deserialize_boc` (round-trip, errors), 6 на `parse_msgaddress_int_from_cell`, 5 на `format_raw_address`. Все 305 тестов пакета `ton_rpc/` зелёные; ruff/mypy/lint-imports зелёные на изменённых файлах.
- **Baseline CI** (на свежем main + новой ветке без коммитов): **6290 passed + 2 skipped, 96% cov, 8m** — зелёный.
- **Local env**: `.venv` активирована; `httpx`, `pynacl`, `pyotp` уже в lock-файле (после 4.1-D).

## Что я сделал в этой сессии

- E.4: доменный агрегат `PayoutFreeze` + порт `IPayoutFreezeRepository`. Пакет выбран `domain/monetization/` (по аналогии с `Wallet` + `IWalletRepository` в 4.1-D), т.к. freeze-флаг блокирует именно крипто-выплаты (`Currency.TON_NANO` / `USDT_DECIMAL`), а не все админские мутации. Агрегат frozen+slots без identity (два идентичных снапшота неотличимы по аналогии с `PrizePool`). Строгие invariant-ы: `is_frozen=True` → все три nullable-атрибута (`frozen_by_admin_id`, `frozen_at`, `reason`) заполнены; `is_frozen=False` → все три `None` (нельзя оставлять сиротские `frozen_by_admin_id` после unfreeze — это равносильно битым данным). Порт идемпотентный (`set_frozen` одного и того же админа не создаёт второй ряд, а обновляет `reason`/`at`; `set_unfrozen` на уже-unfrozen-состоянии — no-op). +17 unit-тестов. mypy/ruff/import-linter зелёные.
- E.3: расширение `AdminAuditAction`-enum четырьмя новыми значениями под admin-команды призового пула (`ADMIN_PRIZE_POOL_VIEWED` — read-side для `/prize_pool`; `ADMIN_REFUND_LOT` — write-side для `/refund_lot`; `ADMIN_FREEZE_PAYOUTS` / `ADMIN_UNFREEZE_PAYOUTS` — для `/freeze_payouts` / `/unfreeze_payouts`). +4 unit-теста (1 happy-path + 2 инвариантных + расширение existing-теста). Alembic-CHECK не нужен: `admin_audit_log.action` в схеме — `String(64)` без CHECK-constraint-а, whitelist энфорсит только domain-enum (см. `migrations/.../0016_admin_audit_log.py:48-99`).
- E.2: фикс P0 bug-2 из 4.1-D backlog (в предыдущем коммите `f5a7048`). TON Center API v2 в ответе `runGetMethod("get_wallet_address", ...)` возвращает stack-entry вида `["slice"|"cell", {"bytes": "<base64-BoC>"}]`, который `http_client._stack_entry_to_str` flatten-ит в base64-стрингу. До E.2 `JettonUsdtProvider.resolve_wallet` возвращал `stack[0]` как-есть — в production это была base64-BoC-стринга вместо TON-адреса, блокируя все USDT jetton-transfer-ы. Реализованы: (1) `deserialize_boc(raw: bytes) -> Cell` (симметрично к `serialize_boc`, поддерживает single-root + size_bytes=1 + off_bytes ∈ {1, 2} + non-aligned padding-stripping); (2) `parse_msgaddress_int_from_cell(cell) -> (workchain: int, account_hash: bytes)` (парсит TL-B `addr_std$10` из первых 267 бит ячейки); (3) `format_raw_address(workchain, account_hash) -> str` (inverse к `parse_address` для raw-формы "wc:hex"). `resolve_wallet` теперь сначала пробует `parse_address(stack[0])` (backward-compat с `FakeTonRpcClient` и raw-адресами), иначе делает `_b64_decode_permissive` → `deserialize_boc` → `parse_msgaddress_int_from_cell` → `format_raw_address`. На любую ошибку → `JettonResolutionError` с диагностикой (`raw`, `error`). +29 unit-тестов.
- E.1: `TonRpcAdapter._fetch_seqno` hex/decimal парсер (предыдущий коммит `9c3878b`).
- E.0: pivot doc-ов под 4.1-E + sticky `AGENT_HANDOFF.md` (`862260b`).

## На каком файле / задаче остановился

E.11a + E.10 завершены. Следующий шаг — **E.11b** (queue, если нужна — по ревью можно пропустить и сразу в E.12 over-limit-эррор превращать в user-facing сообщение без queue). Дальше: E.12–E.14 (bot-handlers + presenters + locales), E.15 (DI уже частично в E.10), E.16 (smoke), E.17–E.20 (CI / doc-sync / handoff cleanup / PR).

Особое внимание в E.6: семантика "`amount > max` без истории → `Within(max)`" — это осознанный fallback (в docstring use-case): `IPayoutLimitChecker` реализует «сумму CLAIMED за окно», а не «не более max за одну выплату». Сами single-amount лимиты (если понадобятся) будут в ClaimPrize-flow в шаге E.10 (отдельное правило `lot.amount_native <= cfg.max_amount_native`).

Проблема winner_id — **решена в E.11a**: `prize_lots.winner_id BIGINT NULL` + покрывающий индекс + CHECK-инварианты. `ClaimPrize.execute(...)` передаёт `winner_id=command.player_id` в `update_status(CLAIMED)`. SQL `sum_claimed_in_window`/`oldest_claimed_at_in_window` реализованы вместо `NotImplementedError`. Fake `update_status(CLAIMED, winner_id=...)` автоматически записывает winner в sidemap (вместо ручного `record_winner`). E.11 разбит на E.11a (схема + репозиторий) и E.11b (очередь).

## Команды для разогрева

```bash
# Активация окружения
source /home/ubuntu/repos/PipirkaWar/.venv/bin/activate
cd /home/ubuntu/repos/PipirkaWar

# Запуск конкретного теста
pytest tests/unit/infrastructure/payments/ton_rpc/test_adapter.py -xvs

# Полный CI
make ci

# Только smoke
make smoke

# Pre-commit на изменённые файлы
pre-commit run --files <file>
```

## Ссылки на спецификации

- **ГДД §12.6.6** «Экспозиция в админке» — `/prize_pool`, `/refund_lot`, `/freeze_payouts` (super_admin + TOTP, audit `ADMIN_PRIZE_*`).
- **ГДД §12.6.5** «KYC / антифрод / лимиты» — `max 50 USDT-eq за 30 дней` (rolling), over-limit → очередь.
- **development_plan.md §7** задачи 4.1.10, 4.1.11.
- **CONTRIBUTING.md** §«Sticky AGENT_HANDOFF» — режим обновления HANDOFF.

## Известные production bugs из 4.1-D (P0, делаю в E.1–E.2)

1. **`TonRpcAdapter._fetch_seqno`** (`src/.../ton_rpc/adapter.py`): `int(result.stack[0])` без `base=0` — TON Center иногда возвращает `"0x..."` (hex). Fix: `int(value, 0)`.
2. **`JettonUsdtProvider.resolve_wallet`** (`src/.../ton_rpc/jetton.py`): сохраняет `result.stack[0]` (slice-base64-cell от `get_wallet_address`) как plain string. Реальный ответ — slice, требует BoC-decode + parse-address. Fix: `BocCell.deserialize(...).parse_address()`.
