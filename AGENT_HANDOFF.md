# AGENT_HANDOFF — Спринт 4.1-E «Админ-команды + лимиты выплат + 4.1-D backlog»

> **Sticky-mode**: этот файл обновляется в **каждом** коммите фичевой ветки `devin/1778559360-sprint-4-1-E-admin-payout-limits` параллельно с функциональными изменениями. Удаляется отдельным коммитом перед открытием PR. См. `CONTRIBUTING.md` §«Sticky AGENT_HANDOFF mode».

---

## Контекст

- **Активный PR**: 4.1-E «Админ-команды + лимиты выплат» (пятый PR Спринта 4.1).
- **Ветка**: `devin/1778559360-sprint-4-1-E-admin-payout-limits` (от свежего main `1601410` — после мерджа PR #132 «4.1-D TON Connect + USDT + ClaimPrize»).
- **База**: `main = 1601410`.
- **Сессия**: https://app.devin.ai/sessions/6b5380ef4ab741bb959987c6edf6953c

## Чек-лист 4.1-E (E.0 → E.20)

| Шаг | Описание | Статус |
|-----|----------|--------|
| **E.0** | Pivot `docs/current_tasks.md` под 4.1-E + создать sticky `AGENT_HANDOFF.md` | ✅ done |
| **E.1** | **P0 bug-1**: `TonRpcAdapter._fetch_seqno` — поддержка hex/decimal от TON Center (`int(value, 0)` + edge cases) + unit-тесты | ✅ done |
| **E.2** | **P0 bug-2**: `JettonUsdtProvider.resolve_wallet` — парсинг slice-base64-cell → TON-address через `BocCell`-decoder + unit/integration | ✅ done |
| **E.3** | Domain: `AdminAuditAction.{ADMIN_PRIZE_POOL_VIEWED, ADMIN_REFUND_LOT, ADMIN_FREEZE_PAYOUTS, ADMIN_UNFREEZE_PAYOUTS}` (без Alembic-CHECK — `admin_audit_log.action` не имеет CHECK-constraint-а) + unit-тесты | 🔄 in_progress (этот коммит) |
| **E.4** | Domain: `PayoutFreeze` aggregate + `IPayoutFreezeRepository` port | ⏳ pending |
| **E.5** | Domain: `PayoutLimitConfig` VO + `IPayoutLimitChecker` port | ⏳ pending |
| **E.6** | Application: `EvaluatePayoutLimit(player, currency, amount, now) -> Within \| OverLimit(retry_after)` (rolling-window через `IPrizeLotRepository`) + balance.yaml-конфиг | ⏳ pending |
| **E.7** | Application: `FreezePayouts(admin_id, reason)` / `UnfreezePayouts(admin_id)` (TOTP-confirmed + audit) | ⏳ pending |
| **E.8** | Application: `RefundLot(admin_id, lot_id, reason)` (TOTP-confirmed + pool increment + audit) | ⏳ pending |
| **E.9** | Application: `GetPrizePoolStatus(admin_id) -> StatusReport` (read-only + audit `ADMIN_PRIZE_POOL_VIEWED`) | ⏳ pending |
| **E.10** | Hook `EvaluatePayoutLimit` + freeze-check в `ClaimPrize.execute(...)` (over-limit → queue; frozen → reject) | ⏳ pending |
| **E.11** | Persistence: `payout_freeze` (singleton) + queue (расширение `prize_lots.status=QUEUED` или отдельная таблица) + Alembic + repository | ⏳ pending |
| **E.12** | Bot-handler `/prize_pool` + presenter + локали RU/EN | ⏳ pending |
| **E.13** | Bot-handler `/refund_lot <lot_id>` + FSM TOTP-confirm + presenter + локали | ⏳ pending |
| **E.14** | Bot-handler `/freeze_payouts <reason>` + `/unfreeze_payouts` + FSM TOTP-confirm + presenter + локали | ⏳ pending |
| **E.15** | Composition root: `bot/main.py::Container` + `build_dispatcher` пробрасывает в workflow-data | ⏳ pending |
| **E.16** | Smoke-тесты новых admin-flow-ов | ⏳ pending |
| **E.17** | Локальный `make ci` + `pre-commit run --all-files` зелёный | ⏳ pending |
| **E.18** | Doc-sync: `history.md` + `current_tasks.md` (последний коммит до PR) | ⏳ pending |
| **E.19** | Удалить `AGENT_HANDOFF.md` отдельным коммитом | ⏳ pending |
| **E.20** | PR + GitHub CI зелёным | ⏳ pending |

## Состояние ветки

- **Текущий коммит**: E.3 (этот коммит) — расширение `AdminAuditAction`-enum четырьмя новыми значениями (`ADMIN_PRIZE_POOL_VIEWED`, `ADMIN_REFUND_LOT`, `ADMIN_FREEZE_PAYOUTS`, `ADMIN_UNFREEZE_PAYOUTS`) + расширение `TestAdminAuditAction` тремя новыми проверками (`test_prize_pool_actions_present` + 2 инвариантных теста: uniqueness + snake_case-префикс на все валюесы enum-а). Alembic-миграция НЕ нужна: `admin_audit_log.action` не имеет CHECK-constraint-а в схеме (`String(64)` без whitelist-а — энфорсит только domain-enum). +4 теста.
- **Предыдущий коммит (`f5a7048`)**: E.2 — BoC-deserializer + `MsgAddressInt addr_std$10`-парсер в `boc.py` (`deserialize_boc(...)`, `parse_msgaddress_int_from_cell(...)`, `format_raw_address(...)` + выведены helper-ы `_parse_boc_header` / `_parse_cell_specs` / `_parse_one_cell_spec` / `_validate_ref_indices` / `_decode_d2` / `_recover_bits_count_and_strip_padding` / `_read_bits` / `_read_bit_slice` для читаемости); `JettonUsdtProvider.resolve_wallet` теперь parse-address-first с fallback на base64-BoC декодинг (+ permissive base64/base64url-decode). +29 новых unit-тестов: 7 на jetton-resolver (`TestJettonUsdtProviderResolveWalletDecodesBoc`), 11 на `deserialize_boc` (round-trip, errors), 6 на `parse_msgaddress_int_from_cell`, 5 на `format_raw_address`. Все 305 тестов пакета `ton_rpc/` зелёные; ruff/mypy/lint-imports зелёные на изменённых файлах.
- **Baseline CI** (на свежем main + новой ветке без коммитов): **6290 passed + 2 skipped, 96% cov, 8m** — зелёный.
- **Local env**: `.venv` активирована; `httpx`, `pynacl`, `pyotp` уже в lock-файле (после 4.1-D).

## Что я сделал в этой сессии

- E.3: расширение `AdminAuditAction`-enum четырьмя новыми значениями под admin-команды призового пула (`ADMIN_PRIZE_POOL_VIEWED` — read-side для `/prize_pool`; `ADMIN_REFUND_LOT` — write-side для `/refund_lot`; `ADMIN_FREEZE_PAYOUTS` / `ADMIN_UNFREEZE_PAYOUTS` — для `/freeze_payouts` / `/unfreeze_payouts`). +4 unit-теста (1 happy-path + 2 инвариантных + расширение existing-теста). Alembic-CHECK не нужен: `admin_audit_log.action` в схеме — `String(64)` без CHECK-constraint-а, whitelist энфорсит только domain-enum (см. `migrations/.../0016_admin_audit_log.py:48-99`).
- E.2: фикс P0 bug-2 из 4.1-D backlog (в предыдущем коммите `f5a7048`). TON Center API v2 в ответе `runGetMethod("get_wallet_address", ...)` возвращает stack-entry вида `["slice"|"cell", {"bytes": "<base64-BoC>"}]`, который `http_client._stack_entry_to_str` flatten-ит в base64-стрингу. До E.2 `JettonUsdtProvider.resolve_wallet` возвращал `stack[0]` как-есть — в production это была base64-BoC-стринга вместо TON-адреса, блокируя все USDT jetton-transfer-ы. Реализованы: (1) `deserialize_boc(raw: bytes) -> Cell` (симметрично к `serialize_boc`, поддерживает single-root + size_bytes=1 + off_bytes ∈ {1, 2} + non-aligned padding-stripping); (2) `parse_msgaddress_int_from_cell(cell) -> (workchain: int, account_hash: bytes)` (парсит TL-B `addr_std$10` из первых 267 бит ячейки); (3) `format_raw_address(workchain, account_hash) -> str` (inverse к `parse_address` для raw-формы "wc:hex"). `resolve_wallet` теперь сначала пробует `parse_address(stack[0])` (backward-compat с `FakeTonRpcClient` и raw-адресами), иначе делает `_b64_decode_permissive` → `deserialize_boc` → `parse_msgaddress_int_from_cell` → `format_raw_address`. На любую ошибку → `JettonResolutionError` с диагностикой (`raw`, `error`). +29 unit-тестов.
- E.1: `TonRpcAdapter._fetch_seqno` hex/decimal парсер (предыдущий коммит `9c3878b`).
- E.0: pivot doc-ов под 4.1-E + sticky `AGENT_HANDOFF.md` (`862260b`).

## На каком файле / задаче остановился

E.3 завершён локально (`pytest tests/unit/domain/admin/test_admin_audit.py -q` → 10 passed, pre-commit run зелёный на изменённых файлах). Следующий шаг — **E.4**: доменный агрегат `PayoutFreeze` (`is_frozen, frozen_by, frozen_at, reason`) + порт `IPayoutFreezeRepository(get_state, set_frozen, set_unfrozen)` (singleton-таблица). Файлы — `src/pipirik_wars/domain/payment/` (создать или найти существующий sub-package).

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
