# HANDOFF: Sprint 1.6.F — Migration of length-granting use-cases to `ILengthGranter`

**Состояние на момент передачи:** **заблокировано архитектурным конфликтом**. Прямая миграция, как описано в `current_tasks.md::1.6.F`, упирается в инвариант `IUnitOfWork: Nested UnitOfWork is not allowed`. Нужен решительный архитектурный шаг (см. ниже три варианта). Не рекомендую начинать миграцию use-case-ов до выбора варианта.

## Что было сделано в этой ветке

Только этот HANDOFF-документ. Никакого кода не закоммичено — попытка миграции `InvokeOracle` была отменена через `git checkout --` после того, как тест упал на `RuntimeError: FakeUnitOfWork: nested context not allowed`.

## Сама задача (формулировка из `current_tasks.md`)

> **1.6.F** — Миграция всех существующих use-cases (`FinishForestRun`, `InvokeOracle`, `RegisterPlayer`-реферальный бонус) на `progression.add_length(...)` через DI-порт `ILengthGranter` + `import-linter`-контракт «прибавка длины только через ILengthGranter».

Цель: превратить `ILengthGranter`/`AddLength` (1.6.D, уже смержен) из «изолированного use-case» в **единственную точку прибавки длины** в проекте, с контрактом, проверяемым в CI.

## Что мешает прямой миграции

Архитектурный инвариант: **`IUnitOfWork` не поддерживает nested context** — ни `FakeUnitOfWork` (`tests/fakes/uow.py:27-28`), ни `SqlAlchemyUnitOfWork` (`src/pipirik_wars/infrastructure/db/uow.py:41-42`). Оба бросают `RuntimeError("Nested UnitOfWork is not allowed")` при повторном `__aenter__`.

`AddLength.grant()` (`src/pipirik_wars/application/progression/add_length.py:158`) открывает **свой** `async with self._uow:` блок. Все use-case-ы, которые **сейчас** дают длину (`InvokeOracle`, `FinishForestRun`, `UpgradeThickness`-debit), тоже открывают `async with self._uow:`. Прямой вызов `length_granter.grant(...)` изнутри другого use-case-а → `RuntimeError`.

### Воспроизведение блокера (на ветке)

```python
# Минимальная попытка миграции InvokeOracle (отменена):
class InvokeOracle:
    async def execute(self, input_dto):
        async with self._uow:
            player = await self._players.get_by_tg_id(...)
            ...
            await self._history.add(OracleInvocation(...))  # preflight + UNIQUE
            await self._length_granter.grant(  # ← falls into AddLength.grant
                player_id=player.id, delta_cm=result.bonus_cm,
                source=AuditSource.ORACLE, reason="oracle_invocation",
                idempotency_key=f"add_length:oracle:{player.id}:{moscow_date}",
            )
            # AddLength.grant: `async with self._uow:` → RuntimeError
```

## Три варианта развязки

### Вариант A: Re-entrant UoW (counter-based)

Изменить `IUnitOfWork.__aenter__` так, чтобы повторный enter не открывал новую сессию, а инкрементил счётчик. `__aexit__` декрементит; commit/rollback делает только outermost.

**Плюсы:** минимум изменений в use-case-ах. Один use-case владеет транзакцией, вложенные просто пользуются ambient-сессией.

**Минусы:**
- Нужно осторожно обработать `exc` в inner: если inner бросил, outer должен откатиться, а не закоммитить.
- В тестах `uow.commits == 1` останется верным только для outer.
- Меняется контракт `IUnitOfWork` — это глобальный архитектурный sweep.
- Реальные SQLAlchemy-savepoints были бы корректнее, но это уже большой рефактор.

**Эстимейт:** 1 PR на `IUnitOfWork` + `FakeUnitOfWork` + `SqlAlchemyUnitOfWork` + integration-тесты на nested-семантику. ~150 строк диффа без миграций use-cases.

### Вариант B: `AddLength` использует ambient UoW

Убрать `async with self._uow:` из `AddLength.grant`. Caller-use-case обязан открыть UoW сам.

**Плюсы:** концептуально честнее — `AddLength.grant` это **этап** транзакции, не самостоятельная транзакция. Вписывается в DDD-аксиому «UoW = transaction boundary, owned by application service».

**Минусы:**
- Текущие тесты `AddLength` (`tests/unit/application/progression/test_add_length.py`) предполагают, что `AddLength` сам открывает UoW. Все 21 тест надо обернуть в `async with uow:` снаружи.
- Все callers в DI (только `InvokeOracle` пока) обязаны открыть UoW. Если когда-нибудь будет top-level handler `/admin_grant_length` — он тоже должен открыть UoW.
- Нужен аудит, что `AddLength.grant` не зовётся вне UoW (можно — runtime assert: `if uow.session is None: raise`).

**Эстимейт:** 1 PR — `AddLength.grant` + переоформление 21 теста + 1-2 миграции use-case-ов. ~300 строк.

### Вариант C: Композиция через цепочку отдельных UoW

Не трогать UoW. В `InvokeOracle.execute` сделать **две последовательные** транзакции:
1. UoW-1: preflight + insert в `oracle_invocations`. Коммит.
2. UoW-2: вызов `length_granter.grant(...)`. Коммит.

**Плюсы:** никаких архитектурных изменений. Каждый use-case остаётся top-level.

**Минусы:** **потеря атомарности** между «зафиксировали ритуал» и «дали длину». Если упало между ними (краш ВМ, сетевой обрыв в `grant`) — `oracle_invocations` есть, длина не выдана. UX: игрок не получит длину сегодня и завтра не сможет повторить (preflight отбьёт). Это **регрессия** по сравнению с текущей атомарной семантикой.

**Эстимейт:** 1 PR на use-case (3 use-case-а), очень быстрый, но с UX-регрессией. ~200 строк.

## Рекомендация

**Вариант B** — концептуально чище и хорошо ложится на существующую архитектуру (UoW владеет транзакцией, application-сервис — этапом). Цена — переоформление тестов `AddLength`, что относительно механическое.

**Вариант A** — если не хочется трогать тесты `AddLength`. Но re-entrant counter-based UoW — это нетривиальный invariant с edge-case-ами на исключениях.

**Вариант C** — категорически не рекомендую: вводит фактический баг в продакшен.

## План на следующего агента

### Шаг 1 (≈1 PR): выбрать вариант + опубликовать ADR

Вариант B по моей рекомендации. ADR в `docs/adr/0001-uow-and-length-granter.md` (или в `docs/history.md` секция «Решения по архитектуре»).

### Шаг 2 (≈1 PR): рефактор `AddLength.grant` (если выбран B)

- Убрать `async with self._uow:` из `AddLength.grant`. Вместо этого добавить runtime-assert: `if not self._uow.is_active: raise RuntimeError("AddLength.grant requires active UoW")` (для этого надо в `IUnitOfWork` ввести property `is_active`).
- В `tests/unit/application/progression/test_add_length.py`: обернуть все вызовы в `async with uow: result = await use_case.grant(...)`. ~21 тест.
- Integration-тесты: то же самое, но с реальной БД.

### Шаг 3 (≈1 PR per use-case): миграция callers

**3a. `InvokeOracle`:** заменить блок `with_length` + `audit.record(LENGTH_GRANT)` на `length_granter.grant(...)`. Разместить ПОСЛЕ `history.add(...)` (важно: insert первым, чтобы UNIQUE отбил race). Убрать зависимость от `audit` (если она нигде больше не используется — пока используется, оставить).
- Audit-запись теперь пишет `AddLength`, а не `InvokeOracle`. Формат `idempotency_key` меняется с `"oracle:..."` на `"add_length:oracle:..."`. Тесты в `tests/unit/application/oracle/test_invoke.py:124-125` надо переписать.

**3b. `FinishForestRun`:** аналогично — заменить блок `Length(player.length.cm + run.length_delta_cm)` + `audit LENGTH_GRANT` на `length_granter.grant(player_id=run.player_id, delta_cm=run.length_delta_cm, source=AuditSource.FOREST, reason="forest_run_finished", idempotency_key=f"add_length:forest_run:{run.id}")`.
- Внимание: `FinishForestRun` ВНУТРИ той же транзакции пишет ещё title-grant и name-grant. Они должны остаться как есть (это не length).
- Тесты в `tests/unit/application/forest/test_finish_run.py` — про length-audit-запись надо переписать.

**3c. `RegisterPlayer`-реферальный бонус:** не существует в коде. Это анонс в docstring `add_length.py`. Ничего делать не надо, но добавить TODO в HANDOFF, что когда реферальный бонус будет реализован — сразу через `length_granter.grant(source=AuditSource.REFERRAL, ...)`.

### Шаг 4 (≈1 PR): import-linter контракт

В `pyproject.toml` (или `.importlinter`):

```ini
[importlinter:contract:length-grant-only-via-granter]
name = Прибавка длины — только через ILengthGranter
type = forbidden
source_modules =
    pipirik_wars.application
    pipirik_wars.bot
forbidden_modules =
    # Никто не имеет права звать Player.with_length(+positive) напрямую,
    # кроме AddLength.
    # Это реализовано не как forbidden_modules (он про import), а как
    # custom-контракт через `lint-imports --custom`. Альтернатива —
    # AST-grep / ruff-rule.
```

import-linter не умеет напрямую запретить вызов метода — он работает на уровне импортов модулей. Поэтому контракт должен быть либо:
- **Импортный:** `application/oracle/invoke.py` не импортирует `Player.with_length` напрямую (но это не работает — импортируется класс, а не метод).
- **AST-grep / ruff:** custom rule, которое ругается на `*.with_length(*, *)` если файл не `add_length.py` или `upgrade_thickness.py` (последний — debit, всегда отрицательная дельта). Это, вероятно, самый честный путь — но требует написать Ruff plugin или AST-grep правило.

**Альтернатива:** проще — добавить runtime-проверку в `Player.with_length`: «требует either `AnticheatGuard` контекст или `AddLength` вызов» через ContextVar. Но это запах архитектуры.

**Самое честное:** unit-тест-сторож:

```python
# tests/architecture/test_no_direct_length_grant.py
def test_only_add_length_calls_player_with_length_for_grants():
    """Сторож: никто, кроме AddLength.grant и UpgradeThickness (debit), не зовёт
    `Player.with_length(...)`. Грантования длины — только через ILengthGranter."""
    import ast, pathlib
    src = pathlib.Path("src/pipirik_wars")
    allowed_files = {
        "application/progression/add_length.py",
        "application/progression/upgrade_thickness.py",  # debit
    }
    for py in src.rglob("*.py"):
        rel = py.relative_to(src)
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "with_length":
                    assert str(rel) in allowed_files, (
                        f"{rel}: прямой вызов Player.with_length() запрещён, "
                        f"используй ILengthGranter.grant(...)"
                    )
```

Этот тест дешевле import-linter и точнее.

### Шаг 5 (≈1 PR): `current_tasks.md` → `history.md`

Перенести 1.6.F в `history.md` после мержа всех под-PR-ов.

## Ссылки на код

- Use-cases-кандидаты на миграцию:
  - `src/pipirik_wars/application/oracle/invoke.py:151-187` (Oracle)
  - `src/pipirik_wars/application/forest/finish_run.py:151-187` (Forest)
- ILengthGranter порт: `src/pipirik_wars/domain/progression/length_granter.py`
- AddLength реализация: `src/pipirik_wars/application/progression/add_length.py:145-230` (там, где `async with self._uow:` — это и есть точка конфликта).
- UoW-фейк: `tests/fakes/uow.py:27-28` (источник `RuntimeError`).
- Реальный UoW: `src/pipirik_wars/infrastructure/db/uow.py:40-44` (тоже `RuntimeError`).

## Ничего не блокирует следующего агента

Текущий main стабилен. Все 1.6.A–E смержены. CI зелёный. Ветка `devin/1777987739-sprint-1-6f-add-length-migration` содержит только этот документ — её можно либо удалить, либо использовать как стартовую под Шаг 1 (ADR).
