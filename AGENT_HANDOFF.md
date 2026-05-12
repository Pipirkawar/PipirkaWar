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
| **E.1** | **P0 bug-1**: `TonRpcAdapter._fetch_seqno` — поддержка hex/decimal от TON Center (`int(value, 0)` + edge cases) + unit-тесты | 🔄 in_progress (этот коммит) |
| **E.2** | **P0 bug-2**: `JettonUsdtProvider.resolve_wallet` — парсинг slice-base64-cell → TON-address через `BocCell`-decoder + unit/integration | ⏳ pending |
| **E.3** | Domain: `AdminAuditAction.{ADMIN_PRIZE_POOL_VIEWED, ADMIN_REFUND_LOT, ADMIN_FREEZE_PAYOUTS, ADMIN_UNFREEZE_PAYOUTS}` + Alembic CHECK whitelist | ⏳ pending |
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

- **Текущий коммит**: E.1 (этот коммит) — `_parse_tvm_int(...)` helper + замена `int(result.stack[0])` в `TonRpcAdapter._fetch_seqno`; +18 unit-тестов (10 параметризованных hex/decimal happy-path-ов через `payout(...)`, 7 негативных кейсов, 10 happy-path + 7 reject + 1 non-string для `_parse_tvm_int`-helper-а).
- **Baseline CI** (на свежем main + новой ветке без коммитов): **6290 passed + 2 skipped, 96% cov, 8m** — зелёный.
- **Local env**: `.venv` активирована; `httpx`, `pynacl`, `pyotp` уже в lock-файле (после 4.1-D).

## Что я сделал в этой сессии

- E.1: `TonRpcAdapter._fetch_seqno` — фикс P0 bug-а из 4.1-D backlog. TON Center API v2 в стек-ответе `run_get_method`-а возвращает TVM-int одной из двух форм: decimal (`"42"`) или hex (`"0x2a"`, `"0X2A"`). До E.1 адаптер парсил только decimal (`int(result.stack[0])`) — на хексе падал `ValueError`, что блокировало TON-payout в production. Введён module-level helper `_parse_tvm_int(raw, *, context) -> int` с двумя гарантиями: (а) поддержка decimal/hex/unary-minus/whitespace-обрамления через `int(trimmed, 0)`; (б) any non-numeric / non-string → `TonRpcCallError` с контекст-меткой (имя вызывающего метода). `_fetch_seqno` теперь возвращает `_parse_tvm_int(raw_seqno, context=...)`. +18 unit-тестов (`TestTonRpcAdapterFetchSeqnoIntParsing` через payout-flow + `TestParseTvmInt` напрямую).
- E.0: pivot doc-ов под 4.1-E + sticky `AGENT_HANDOFF.md` (предыдущий коммит на ветке).

## На каком файле / задаче остановился

E.1 завершён локально (`pytest tests/unit/infrastructure/payments/ton_rpc/test_adapter.py -q` → 53 passed, ruff/mypy зелёные на изменённых файлах). Следующий шаг — **E.2**: фикс `JettonUsdtProvider.resolve_wallet` (slice-base64-cell → TON-address через BoC-decoder). Файл — `src/pipirik_wars/infrastructure/payments/ton_rpc/jetton.py`.

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
