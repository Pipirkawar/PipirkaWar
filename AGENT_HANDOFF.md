# AGENT HANDOFF — Спринт 2.1.H (раунд-логи + share-кнопка)

## Контекст
- Только что смержены: PR #56 (Спринт 2.1.G AFK-таймер) + PR #57 (docs G).
- **Текущая ветка**: `devin/1778015118-sprint-2-1-h-duel-log-templates`.
- Этот файл `AGENT_HANDOFF.md` нужно **удалить отдельным коммитом** перед финальным PR.

## Цель: Спринт 2.1.H
Из `docs/current_tasks.md` строка 68: «**2.1.H** — 50+ JSON-шаблонов забавных раунд-логов (RU/EN), `JsonDuelLogTemplateProvider` + рандомайзер. Карточка результата + кнопка «Поделиться»».

Аналогичный паттерн уже есть в **1.5.G** (PR #32) — `JsonForestLogTemplateProvider` для леса. Зеркалить его для PvP, не плодя сущностей.

## Полный план (commit-friendly: каждый шаг = отдельный коммит)

### Шаг 1: Domain `DuelLogTemplate` + чистая функция picker-а
- Создать `src/pipirik_wars/domain/pvp/log_template.py`:
  - `RoundOutcomeKind` enum: `BOTH_HIT` / `SINGLE_HIT` / `BOTH_BLOCKED` (что показывать как итог раунда).
  - `DuelLogTemplate` frozen+slots dataclass с полями `id: str`, `text: str`, `kind: RoundOutcomeKind` + `__post_init__` валидация (id/text непустые).
  - Чистая функция `pick_duel_log_template(*, random: IRandom, templates: Sequence[DuelLogTemplate], kind: RoundOutcomeKind) -> DuelLogTemplate` — фильтрует по `kind`, рандомит. Если для kind пусто — fallback на `BOTH_HIT` (или `DuelLogNoTemplatesError`).
  - Функция `classify_round_outcome(outcome: RoundOutcome) -> RoundOutcomeKind` — преобразует `(p1_attack_blocked, p2_attack_blocked)` → `RoundOutcomeKind`.
- Добавить `DuelLogNoTemplatesError` в `src/pipirik_wars/domain/pvp/errors.py`.
- Экспортировать в `src/pipirik_wars/domain/pvp/__init__.py`.
- Тесты: `tests/unit/domain/pvp/test_log_template.py` (валидация полей, picker rolls, classify-помощник).
- **Коммит**: `feat(pvp): domain DuelLogTemplate + classify_round_outcome [Спринт 2.1.H шаг 1]`.

### Шаг 2: Application port `IDuelLogTemplateProvider`
- Создать `src/pipirik_wars/application/pvp/log_templates.py` (порт абстракции, как `forest/log_templates.py`).
- Экспортировать в `application/pvp/__init__.py`.
- **Коммит**: `feat(pvp): port IDuelLogTemplateProvider [Спринт 2.1.H шаг 2]`.

### Шаг 3: JSON-каталоги шаблонов (≥50 на локаль; формат с категориями)
- `config/templates/duel_logs_ru.json` — ≥50 шаблонов (по 17+ на каждую из 3 категорий).
- `config/templates/duel_logs_en.json` — то же.
- Allowed placeholders: `{p1}`, `{p2}` (для `BOTH_HIT` / `BOTH_BLOCKED`); `{attacker}`, `{defender}` (для `SINGLE_HIT`). Это валидируется при парсинге.
- Формат:
  ```json
  {
    "version": 1,
    "templates": [
      {"id": "pvp.ru.both_hit.0001", "text": "🥊 {p1} и {p2} оба пробили блок!", "kind": "both_hit"},
      ...
    ]
  }
  ```
- **Коммит**: `feat(pvp): JSON catalogs duel_logs_{ru,en}.json [Спринт 2.1.H шаг 3]`.

### Шаг 4: Infrastructure `JsonDuelLogTemplateProvider`
- Создать `src/pipirik_wars/infrastructure/templates/duel_log.py` (зеркало `forest_log.py`):
  - Lazy-кэш per-локаль.
  - RU-fallback.
  - Валидация плейсхолдеров (только разрешённые для категории).
- Экспортировать в `infrastructure/templates/__init__.py`.
- Тесты: `tests/unit/infrastructure/templates/test_duel_log.py` (загрузка, fallback, ConfigError-кейсы).
- **Коммит**: `feat(pvp): JsonDuelLogTemplateProvider [Спринт 2.1.H шаг 4]`.

### Шаг 5: Presenter `DuelPresenter.round_flavor(...)` + `result_card(...)` с share-кнопкой
- Расширить `src/pipirik_wars/bot/presenters/duel.py`:
  - `round_flavor(*, template, p1_name, p2_name, attacker_name=None, defender_name=None) -> str` — рендерит шаблон с подстановкой плейсхолдеров.
  - `result_card(*, duel_outcome, p1_name, p2_name, locale) -> SerializedMessage` — карточка финала с inline-кнопкой «Поделиться» (callback-data `share_pvp_result:{duel_id}`).
- Локали: добавить `duel-result-card-*` ключи + `duel-share-button` в `locales/{ru,en}.ftl`.
- Тесты: расширить `tests/unit/bot/presenters/test_duel.py`.
- **Коммит**: `feat(pvp): DuelPresenter round_flavor + result_card with share button [Спринт 2.1.H шаг 5]`.

### Шаг 6: Bot-handler integration
- В handler `submit_move` / `resolve_afk_round` (там, где `_broadcast_result`-у нужны раунд-логи) — добавить best-effort flavour-бродкаст.
- Новый callback-handler `handle_share_pvp_result` для кнопки «Поделиться» — постит результат в `current_chat_id` (чат, откуда вызвали).
- DI-провязка `JsonDuelLogTemplateProvider` в `bot/main.py`.
- Тесты: расширить `tests/unit/bot/handlers/test_duel.py`.
- **Коммит**: `feat(pvp): bot integration round flavour + share handler [Спринт 2.1.H шаг 6]`.

### Шаг 7: Финиш
- Удалить `AGENT_HANDOFF.md` отдельным коммитом.
- `make ci` зелёный (≥80% coverage; mypy strict; ruff).
- `git push` + `git_pr fetch_template` + `git_pr create`.
- `git pr_checks wait_mode=all`.

## Важные паттерны (из 2.1.G и F.2)
- `Late-bound factory` — пока не понадобится в этом спринте; бот-handler-у достаточно прямого `IDuelLogTemplateProvider` через aiogram-DI.
- **Опциональные параметры в use-case-ах**: если приходится менять use-case-ы, делать новые поля `Optional` для back-compat существующих тестов.

## Что НЕ делать
- Не трогать use-case-ы `SubmitMove` / `ResolveAfkRound` — flavour-логи это **bot-side** best-effort, не часть domain-state. (См. 1.5.G: `TelegramForestFinishNotifier` тянет templates вне use-case-а).
- Не использовать `gh` CLI — встроенные git-инструменты Devin.
- Не делать `--no-verify` на pre-commit.

## Команды быстро-старта (в `/home/ubuntu/PipirkaWar/`)
```bash
git status -sb  # должно быть на devin/1778015118-sprint-2-1-h-duel-log-templates

# Прочитать существующий forest-паттерн
cat src/pipirik_wars/domain/forest/log_template.py
cat src/pipirik_wars/application/forest/log_templates.py
cat src/pipirik_wars/infrastructure/templates/forest_log.py

# Посмотреть RoundOutcome (для classify_round_outcome)
sed -n '78,103p' src/pipirik_wars/domain/pvp/entities.py

# Run CI
make ci
```

## После работы
Обновить `docs/current_tasks.md` (H → ✅смержено) + `docs/history.md` отдельным docs-PR-ом, как было сделано для G в PR #57.
