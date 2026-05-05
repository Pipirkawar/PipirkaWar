# HANDOFF — Спринт 1.5.G (forest-log-templates)

Ветка: **`devin/1777976148-sprint-1-5g-forest-templates`** (от `origin/main`,
смерженный PR #31 «docs: хардкап/античит»).

PR ещё **не создан**. Перед PR — стадии 3 и 4 (см. ниже) + `make ci` зелёный.

## Что уже сделано (закоммичено и запушено)

### Стадия 1 — фундамент (`c2b8569`)
Скелет каталога forest-логов по образцу oracle:

- **domain** `src/pipirik_wars/domain/forest/log_template.py`
  - `ForestLogTemplate(id: str, text: str)` — frozen dataclass с валидацией:
    - `id` ≠ "", без префиксных/суффиксных пробелов
    - `text` ≠ "", без префиксных/суффиксных пробелов
  - `pick_forest_log_template(*, random, templates) -> ForestLogTemplate`
    — чистая функция (без I/O), бросает `ForestLogNoTemplatesError`, если каталог пуст.
- **domain errors** `src/pipirik_wars/domain/forest/errors.py`
  - `ForestLogNoTemplatesError(ForestError)` — каталог пуст.
- **application port** `src/pipirik_wars/application/forest/log_templates.py`
  - `IForestLogTemplateProvider.get_templates(*, locale: str) -> Sequence[ForestLogTemplate]`
  - Контракт фолбэка: requested locale → `"ru"` → `ForestLogNoTemplatesError`
  - Lazy кэш per locale.
- **infrastructure adapter** `src/pipirik_wars/infrastructure/templates/forest_log.py`
  - `JsonForestLogTemplateProvider(*, templates_dir: Path)`
  - Зеркалит `JsonOracleTemplateProvider`.
  - Lazy load из `templates_dir / f"forest_logs_{locale}.json"`.
  - Валидирует: `version` field, `templates` массив, уникальные id, валидные строки.
- **fake** `tests/fakes/forest_log_templates.py`
  - `FakeForestLogTemplateProvider` — in-memory с фолбэком на `"ru"`.
- **unit-тесты**:
  - `tests/unit/domain/forest/test_log_template.py` (11 тестов: validation, picking, errors)
  - `tests/unit/domain/forest/test_errors.py` — добавлен `TestForestLogNoTemplatesError`

### Стадия 2 — интеграция в нотифай-флоу (`cdf62a2`)
Picker зовётся в `TelegramForestFinishNotifier` (после коммита `FinishForestRun`,
**вне транзакции**, best-effort — каталог пуст / провайдер упал → flavour не показываем,
основное сообщение «вернулся из леса» уходит как было):

- **`bot/notifications/forest.py`** — добавлены deps `log_templates: IForestLogTemplateProvider`
  и `random: IRandom`; новый метод `_pick_flavor_template(*, locale)`:
  - `IForestLogTemplateProvider.get_templates(locale=locale.code)` — port ждёт `str`,
    `Locale` value-object имеет `.code`.
  - `ForestLogNoTemplatesError` → log warning + None.
  - Любое другое исключение → log exception + None.
- **`bot/presenters/forest.py`** — `finished(*, flavor_template: ForestLogTemplate | None = None)`
  - Если `flavor_template is not None` — добавляет строку через `_render_flavor(...)`
  - `_render_flavor` подставляет `{user}` (полный ник «Локализованный титул + display_name + name»)
    и `{delta}` (берётся из bundle-ключа `forest-flavour-delta`).
  - Defensive: `try/except (KeyError, IndexError, ValueError)` — кривой плейсхолдер
    в JSON-каталоге не сломает сообщение игрока, отдаём сырой текст.
  - Новый константный ключ `_KEY_FLAVOUR_DELTA = MessageKey("forest-flavour-delta")`.
- **`locales/ru.ftl`** + **`locales/en.ftl`** — новый ключ `forest-flavour-delta`
  («+N см» / «+N cm»), параметр `$length_delta_cm`. Объяснение, зачем отдельный
  ключ (а не reuse `forest-finished-length`), — в комментарии перед ключом.
- **`bot/main.py`** — composition root:
  - `JsonForestLogTemplateProvider(templates_dir=...)` (тот же `_DEFAULT_TEMPLATES_DIR`,
    что и oracle).
  - Прокинут в `TelegramForestFinishNotifier(log_templates=..., random=RealRandom())`.
- **тесты**:
  - `tests/unit/bot/presenters/test_forest.py` — 3 новых теста (без template, с template,
    с битым placeholder).
  - `tests/unit/bot/notifications/test_forest.py` — `_make_notifier` принимает дефолты
    `log_templates=_default_log_templates()` (RU+EN по 1 шаблону) и `random=FakeRandom(seed=42)`.

### Локально `make ci` зелёный
- 1072 пройденных + 1 skipped, coverage **96.59 %**, ruff/mypy/import-linter — все KEPT.
- См. `/tmp/devin-remote-overflows-1000/bd32deeb/content.txt` для последнего лога,
  если ещё не вытерт.

## Что должен сделать следующий агент

### Стадия 3 — каталоги `config/templates/forest_logs_{ru,en}.json` (≥ 300 entries каждый)

Формат (зеркало oracle, см. `config/templates/oracle_ru.json` для образца):
```json
{
  "version": 1,
  "templates": [
    {"id": "forest.ru.0001", "text": "{user} зацепился за корягу и нашёл {delta} в кустах!"},
    {"id": "forest.ru.0002", "text": "..."}
  ]
}
```

Жёсткие требования (валидируются на загрузке `JsonForestLogTemplateProvider`):
- Уникальные `id` внутри одного файла.
- `id` рекомендуется в формате `forest.<locale>.<NNNN>` (4-значный padding).
- `text` ≠ "", без префиксных/суффиксных пробелов.
- Допустимые плейсхолдеры в `text`: **только** `{user}` и `{delta}`.
  Любой другой `{...}` ломает `str.format` → defensive в презентере отдаст сырой текст —
  это invariant-нарушение, integration-тест должен на этом падать.
- Желательно использовать `{user}` и/или `{delta}` (хотя бы один из них) — иначе
  flavour-строка тривиальна; не строгий invariant, но рекомендация.

Стиль (ГДД §15): забавные «логи леса» в духе «🌲 «Ядрёный Бананчик Коляндр зацепился
за корягу и нашёл +3 см в кустах!»». RU и EN — независимые каталоги (не машинный
перевод 1:1, локализация культуры): можно делать ≥ 300 в каждом без жёсткого
соответствия id.

Подсказка: лучше сгенерировать инструментально через грамматику
(prefix × verb × object × outcome) и вручную дочистить «топ-50» — итого должно
получиться ≥ 300 уникальных. Скрипт-генератор **не коммитить**, только результат.

### Стадия 4 — integration-тесты загрузчика
Файл: `tests/integration/templates/test_forest_log_loader.py` — зеркало
существующего `tests/integration/templates/test_oracle_loader.py`.

Покрыть:
1. **Реальные файлы** `config/templates/forest_logs_{ru,en}.json` грузятся без ошибок.
2. В каждом файле **≥ 300** шаблонов.
3. Все `id` уникальны внутри файла.
4. Все `text` непустые, без leading/trailing whitespace.
5. Все плейсхолдеры в `text` — **только** `{user}` или `{delta}` (regex по `\{[^}]+\}` →
   set должен быть подмножеством `{"{user}", "{delta}"}`).
6. Lazy-кэш: повторный `get_templates(locale="ru")` возвращает ту же tuple-instance
   (как у oracle).
7. Fallback: `get_templates(locale="zz")` — фолбэк на `"ru"` (`SUPPORTED_LOCALES` —
   только `ru/en`, но порт принимает любой `str`).
8. Полностью пустой каталог → `ForestLogNoTemplatesError` (на тестовом dir).
9. Невалидный JSON / отсутствие поля `version` / дубликат id → `ValueError` или
   `ForestTemplateValidationError` (как у oracle — взять тот же тип ошибки!).

### Финиш
1. `make ci` локально — должен остаться зелёным (coverage может слегка просесть из-за
   `infrastructure/templates/forest_log.py:59-70` — это error-paths, integration-тесты
   их и должны накрыть).
2. **Удалить** `HANDOFF.md` отдельным коммитом перед PR.
3. `git_pr(action="fetch_template")` → `git_pr(action="create")` с базой `main`.
4. `git(action="pr_checks", wait_mode="all")` до зелёного CI.
5. Notifier ловит `Exception` из провайдера и не падает — но если CI упал на
   integration-тестах, это invariant-нарушение каталога, фиксить **JSON**, не
   презентер.

## Архитектурные нюансы (не проспать)

- **Презентер не зависит от `IRandom`/`IForestLogTemplateProvider`** — picking
  делает notifier (внешний для презентера слой). Это сделано чтобы презентер
  оставался pure / детерминистичным и сохранял существующий контракт.
- **`Locale` value-object vs `str`** — порт `IForestLogTemplateProvider.get_templates`
  принимает `str`, не `Locale` (как у oracle). В notifier-е делаем `locale.code`.
- **Audit `LENGTH_GRANT.source`** — в development_plan.md изначально стояло требование
  расширить audit полем `source: "forest" | "donate" | "admin" | ...` (в задаче 1.6.1,
  hardcap-античит, не 1.5.G). На 1.5.G **не** трогаем `AuditEntry`/audit-лог;
  идемпотентность уже обеспечена через `idempotency_key=f"forest_run_finished:length:{run_id}"`.
- **Кодинг-стиль** — `from __future__ import annotations` обязателен; импорты в начале
  файла; никаких `Any`/`getattr`. Pre-commit hooks (`ruff`, `mypy --strict`,
  `import-linter`) запускаются автоматически на `git commit`.
- **`make ci` не запускает pip-audit** локально (только в GitHub CI workflow,
  есть отдельная job).

## Команды
```bash
# Запуск CI локально
make ci

# Запуск тестов конкретно по новым файлам
pytest tests/unit/domain/forest/test_log_template.py \
       tests/unit/bot/presenters/test_forest.py \
       tests/unit/bot/notifications/test_forest.py \
       tests/integration/templates/test_forest_log_loader.py \
       --no-cov -q

# Создать PR (после удаления HANDOFF.md и зелёного make ci)
# git_pr(action="fetch_template", repo="Pipirkawar/PipirkaWar", exec_dir="/home/ubuntu/repos/PipirkaWar")
# git_pr(action="create", repo="...", title="Спринт 1.5.G: каталог forest-логов (300+ шаблонов RU+EN)",
#        body=<по template>, head_branch="devin/1777976148-sprint-1-5g-forest-templates", base_branch="main")
```
