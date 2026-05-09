# AGENT HANDOFF — Спринт 3.4-A (шаг ~3/10)

> Этот файл — временный safety-net. Удали его отдельным коммитом перед открытием PR
> (`git rm AGENT_HANDOFF.md && git commit -m "chore: remove AGENT_HANDOFF before PR"`).

## Что я сделал в этой сессии

Один коммит на ветке `devin/1778305054-sprint-3-4-A-enchant-domain-skeleton`:

- `e551cc8` — `feat(3.4-A): inventory package + EnchantmentConfig + balance defaults`
  - Создан пакет `src/pipirik_wars/domain/inventory/` (4 файла, ~660 строк):
    - `entities.py` — `ItemCategory(StrEnum)`, `RegularEnchantOutcome` (4),
      `BlessedEnchantOutcome` (5), `EnchantOutcome = Union`, immutable `Item`
      (`id: str`, `category: ItemCategory`, `enchant_level: int 0..30`)
      с `with_enchant_level()`, `is_destroyed()`, `matches_scroll()` +
      helper `_scroll_to_item_category()`. `MAX_ENCHANT_LEVEL = 30`.
    - `errors.py` — `InventoryDomainError` (база, наследник `DomainError`)
      и три domain-error-а: `WrongScrollCategoryError`, `MaxLevelReachedError`,
      `ItemDestroyedError`. Все с keyword-args, без `super().__init__`-ов
      message (стиль соседних domain-пакетов).
    - `services.py` — чистая функция `pick_enchant_outcome(*, level, blessed,
      config, random) -> EnchantOutcome`. Safe-zone forced-success;
      weighted_choice через `_T = TypeVar("_T")` (Python 3.11-совместимо!),
      `_WEIGHT_SCALE = 100_000`.
    - `__init__.py` — re-exports + большой docstring с таблицей соответствий
      `ItemCategory ↔ Slot ↔ ScrollCategory`.
  - В `src/pipirik_wars/domain/balance/config.py` (строки ~723–940) добавлены
    pydantic-классы `RegularLevelWeights`, `BlessedLevelWeights`,
    `EnchantmentTier`, `EnchantmentConfig` со всеми инвариантами:
    - sum(weights) == 1.0 ± 1e-6
    - safe-zone: drop/destroy = 0.0 на level < safe_zone_max_level
    - `blessed_outcomes_per_level[max_level - 1].success_2 == 0.0` (ГДД §2.8.4)
    - max_level == 30 (хардкод)
    - tiers покрывают [0, max_level] без дыр/пересечений
  - `config/balance.yaml` — добавлена секция `enchantment` со всеми 30 уровнями
    regular/blessed-весов из ГДД §2.8.6 + 6 тиров. **Проверено**:
    `EnchantmentConfig.model_validate(yaml.safe_load(open("config/balance.yaml"))["enchantment"])`
    проходит локально без ошибок.

`make ci` (lint + ruff format + mypy + import-linter) на этом коммите —
**ЗЕЛЁНЫЙ** (все pre-commit hooks Passed на коммите). Тесты A.5/A.6/A.7
ещё не написаны, поэтому coverage может временно просесть на новых файлах
(но цель ≥ 80% — это требование A.9, не A.1/A.2/A.3/A.4).

## На каком файле / задаче остановился

- **Сделано**: A.1, A.2, A.3, A.4 из чек-листа Спринта 3.4-A
  (см. `docs/current_tasks.md` секция «Чек-лист Спринта 3.4-A»).
- **НЕ сделано** (нужно следующему агенту):
  - **A.0** — обновить `docs/current_tasks.md`: пометить A.1..A.4 готовыми,
    обновить «Снимок состояния проекта» / «Текущая позиция» /
    «Последний коммит = e551cc8». Сейчас snapshot всё ещё на f7d671f
    (после мерджа PR #116).
  - **A.5** — `tests/unit/domain/inventory/test_enchant_picker.py`:
    юнит-тесты picker-а (safe-zone forced-success на level 0/1/2 для
    regular и blessed; все 4 regular- и 5 blessed-исходов появляются
    хотя бы по разу на тире `easy/hard/very_hard/extreme/almost_impossible`;
    3σ-Bernoulli частот; проверка `ValueError` при `level < 0` и `level >= 30`).
    Используй `FakeRandom` из `tests/fakes/` (см. как в
    `tests/unit/domain/forest/test_*.py` — там есть готовый паттерн).
  - **A.6** — `tests/unit/domain/inventory/test_item.py` +
    `tests/unit/domain/inventory/test_errors.py`:
    - Item: создание / `with_enchant_level` / границы 0..30 /
      `MaxLevelReachedError` при выходе / `matches_scroll` для всех
      3 категорий (positive + negative).
    - Scroll VO (из `domain/enchantment/entities.py`) — проверка
      equality, immutability (см. соседний `tests/unit/domain/enchantment/`
      на готовые паттерны).
    - Errors: keyword-args, типы атрибутов.
  - **A.7** — `tests/unit/domain/balance/test_enchantment_config.py`:
    - sum-to-1.0: при сумме != 1.0 `ValidationError`
    - safe-zone-zero: при `drop>0` на level<3 — `ValidationError`
    - blessed[29].success_2 != 0.0 — `ValidationError`
    - `outcomes_keys_full`: пропущенный или лишний level — `ValidationError`
    - `tiers_cover_range`: дыра / пересечение / неправильный from/to — `ValidationError`
    - `max_level != 30` — `ValidationError`
    - integration: `default balance.yaml parses without errors`
      (`pytest -m "..."` или просто `BalanceConfig` загрузка).
  - **A.8** — проверка `import-linter` контракта
    (`importlinter.contract.layered_architecture`):
    - `domain/inventory` НЕ импортирует из `application/` или `infrastructure/`
    - `domain/balance` НЕ импортирует из `domain/inventory`
      (одностороннее: inventory может зависеть от balance, не наоборот)
    - В `setup.cfg` или `pyproject.toml` (см. `[tool.importlinter]`)
      добавить новые ограничения, если их ещё нет.
  - **A.9** — `make ci` локально, **coverage ≥ 80%** (после A.5/A.6/A.7).
  - **A.10** — финальный док-коммит:
    - `docs/history.md` +запись за 2026-05-09 «Sprint 3.4-A — каркас доменов
      «Заточка» + балансовый конфиг» (по образцу записи 3.3-D).
    - `docs/current_tasks.md` — пометить ВСЕ A.0..A.10 готовыми, обновить
      «Снимок» под старт **3.4-B** «Persistence + миграции инвентаря».
    - Коммит: `chore(3.4-A): finalize docs`.
  - Удалить `AGENT_HANDOFF.md` отдельным коммитом перед PR.
  - Открыть PR в `main` через `git_create_pr` (НЕ `gh pr create`).
  - Дождаться зелёного GitHub CI (3/3) через `git_pr_checks`.

## Состояние ветки

- **Ветка**: `devin/1778305054-sprint-3-4-A-enchant-domain-skeleton`
- **База**: `main` (HEAD = `f7d671f`, после мерджа PR #116 «tribe-bonus»)
- **Последний коммит**: `e551cc8 feat(3.4-A): inventory package + EnchantmentConfig + balance defaults`
- **Незакоммиченные изменения**: нет (working tree clean после push-а).
- **CI прогонялся**: локальные pre-commit hooks (ruff/format/mypy/imports) —
  Passed. `make ci` (с pytest + coverage) **НЕ запускался полностью**
  для A.1..A.4 — но Спринт 0/1/2/3 тесты не должны были бы поломаться
  (изменения чисто аддитивные: новый пакет + новые pydantic-классы +
  новая секция в balance.yaml, ничто не модифицирует существующее).
  Открытый PR + GitHub CI **не запущен** — открой только когда A.5..A.10 готово.

## Команды для следующего агента

```bash
# 0. Pickup
cd /home/ubuntu/repos/PipirkaWar
git fetch origin --prune
git checkout devin/1778305054-sprint-3-4-A-enchant-domain-skeleton
git log --oneline -5    # должен быть e551cc8 наверху
git rev-parse --is-shallow-repository    # если true → git fetch --unshallow

# 1. Поднять окружение (если ещё не поднято в этой сессии)
python3.12 -m venv .venv 2>/dev/null || python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install

# 2. Sanity-check, что моя работа в порядке
.venv/bin/ruff check src/pipirik_wars/domain/inventory/ src/pipirik_wars/domain/balance/config.py
.venv/bin/mypy src/pipirik_wars/domain/inventory/ src/pipirik_wars/domain/balance/config.py
python -c "
from pipirik_wars.domain.balance.config import EnchantmentConfig
import yaml
data = yaml.safe_load(open('config/balance.yaml'))['enchantment']
cfg = EnchantmentConfig.model_validate(data)
print(f'OK: {cfg.max_level=}, {cfg.safe_zone_max_level=}, tiers={len(cfg.tiers)}')
"
# Должно вывести: OK: cfg.max_level=30, cfg.safe_zone_max_level=3, tiers=6

# 3. Запустить тесты (только домен инвентаря, когда напишешь A.5/A.6/A.7)
pytest tests/unit/domain/inventory/ -q -x

# 4. Полный CI (требование A.9)
make ci    # lint + mypy + imports + pytest + coverage ≥ 80%

# 5. После A.10 (финальный док-коммит):
git rm AGENT_HANDOFF.md && git commit -m "chore: remove AGENT_HANDOFF before PR"
git push
# Затем — git_create_pr (через инструмент Devin, НЕ через gh).
```

## Известные блокеры / открытые вопросы

1. **Edit-tool падает на `src/pipirik_wars/domain/balance/config.py`** —
   ругается «Missing required parameter: old_string» даже при валидном
   запросе. Я обошёл это через Python-скрипт `/tmp/insert_enchant_config.py`
   (вставка `EnchantmentConfig` блока перед `class PvpDuel1v1Config`).
   Если понадобится дальнейшее редактирование `config.py` — попробуй
   сначала `MultiEdit` (он работал на 5-edit chunk-ах в этой сессии),
   а если упадёт — пиши скрипт через `bash + python -c "..."` или
   `cat >> file << 'EOF' ... EOF`.

2. **MultiEdit на цепочке файлов**: если первый MultiEdit-call в parallel-блоке
   упадёт частично, последующие MultiEdit-call-ы на других файлах в том же
   блоке могут вернуть `"The previous action errored. This action was NOT taken."`
   и не примениться. Решение — повторный одиночный вызов, либо разбить
   на отдельные блоки. У меня сработало на 2-й попытке.

3. **Pre-commit hook auto-fixers могут модифицировать файлы при первой
   неудачной попытке коммита**: ruff format перезаписал `__init__.py` и
   `entities.py`. После такого надо `git add -A` ещё раз и пере-коммитить.

4. **3.6 «Бонус-за-племена»** запланирован как отдельный спринт (см. ГДД
   §11.1, ПД §6.3.6, `docs/current_tasks.md` секция Sprint 3.6 — добавлен
   в PR #116). Не путай с текущим 3.4 «Заточка предметов» — это разные
   спринты, и порядок: **3.4-A → 3.4-B → 3.4-C → 3.4-D → 3.5 → 3.6**.

5. **Локали (`ru.ftl` / `en.ftl`)** — для 3.4-A не нужны (домен-only).
   Они появятся в 3.4-B (handlers + UI). Не добавляй ftl-ключи сейчас.

6. **Тесты picker-а на 3σ-Bernoulli**: используй `n=10_000` трайлов на тир
   и эпсилон `3 * sqrt(p * (1-p) / n)` — паттерн уже применялся в
   `tests/integration/application/bosses/test_scroll_drop_frequencies.py`
   (Спринт 3.3-D, мой коммит `2bbb9fc` — посмотри для готового
   `_assert_within_3sigma()` хелпера или скопируй его рядом).

7. **Где брать ТЗ дальше**:
   - `docs/development_plan.md` §6.3 «Спринт 3.4 — Заточка предметов»
   - `docs/game_design.md` §2.8 «Заточка» (особенно §2.8.6 — балансовые числа)
   - `docs/current_tasks.md` секция «Чек-лист Спринта 3.4-A» (A.0..A.10)
