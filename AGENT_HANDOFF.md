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
| **E.0** | Pivot `docs/current_tasks.md` под 4.1-E + создать sticky `AGENT_HANDOFF.md` | 🔄 in_progress (этот коммит) |
| **E.1** | **P0 bug-1**: `TonRpcAdapter._fetch_seqno` — поддержка hex/decimal от TON Center (`int(value, 0)` + edge cases) + unit-тесты | ⏳ pending |
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

- **Текущий коммит**: TBD (будет обновлён в E.0)
- **Baseline CI** (на свежем main + новой ветке без коммитов): **6290 passed + 2 skipped, 96% cov, 8m** — зелёный.
- **Local env**: `.venv` активирована; `httpx`, `pynacl`, `pyotp` уже в lock-файле (после 4.1-D).

## На каком файле / задаче остановился

E.0 — pivot doc-ов под старт 4.1-E. Следующий шаг — **E.1** (фикс `_fetch_seqno` в `src/pipirik_wars/infrastructure/payments/ton_rpc/adapter.py` на строке `int(stack[0])`).

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
