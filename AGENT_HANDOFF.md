# AGENT_HANDOFF — Спринт 2.2 (Масс-PvP и клановые механики)

> **Назначение:** этот файл — полная инструкция для следующего агента
> на случай, если текущий агент выйдет из контекста посреди работы.
> Удалить **только** после полного завершения спринта 2.2 (или
> отдельных PR-ов, если работа остановлена раньше).

## Контекст

Спринт **2.1 (PvP 1×1)** закрыт полностью — последний PR (2.1.H, шаблоны
раунд-логов + кнопка «Поделиться») смержен. См. `docs/current_tasks.md`
строки 53–68 и `docs/development_plan.md` §5 / Спринт 2.1.

Сейчас открываем **Спринт 2.2 — Масс-PvP и клановые механики**
(`docs/development_plan.md` §5 / строки 330–340). 5 задач:

| # | Задача | Критерий приёмки |
|---|---|---|
| 2.2.1 | `/clantop` | Топ кланов по сумме длин активных участников |
| 2.2.2 | Масс-PvP: вызов клан→клан, кулдаун 6 ч | Все участники с длиной ≥ 20 см автозаписываются |
| 2.2.3 | Игрок в обоих кланах — пропускает | Юнит-тест |
| 2.2.4 | Боевая механика N×M: 1 атака + 1 блок, случайные пары | Все удары разрешаются за один тик; ничья при 0 живых |
| 2.2.5 | Журнал клановых атак (история в карточке клана) | Тесты: события не теряются при сбое |

## Правила работы (из системного промпта)

- Python 3.12 + venv в `.venv`. Активация: `source .venv/bin/activate`.
- Команды: `make ci` (всё сразу), `make lint`, `make typecheck`, `make imports`, `make test`.
- pre-commit hooks **обязательны** (без `--no-verify`).
- Никаких прямых пушей в `main`. Только feature-бранчи `devin/<timestamp>-<slug>`.
- НЕ удалять этот файл, пока спринт не закрыт полностью.

## Архитектурные принципы (повторение для надёжности)

- Слои: `domain → application → infrastructure → bot/presentation`.
  Контролируется `import-linter` (см. `pyproject.toml::tool.importlinter`).
- Доменный слой — **только** чистые dataclass-ы, value-objects, ports
  (abc-классы); никаких I/O, ORM, HTTP, random.
- Use-case-ы (`application/`) — **обязательно** keyword-only
  параметры в `__init__` и `execute`, использование `IUnitOfWork` для
  транзакционности.
- Audit + idempotency — на каждой мутации длины/толщины через
  `add_length` / `with_length` (для PvP — `LENGTH_GRANT/REVOKE` audit-actions).
- Локализация: всё, что показывается пользователю — через
  `IMessageBundle.format(MessageKey, locale=…, **kwargs)`. Файлы:
  `locales/ru.ftl`, `locales/en.ftl`.
- Фейки для тестов — в `tests/fakes/`, in-memory, без mock-патчинга.

## Пошаговый план (PR 2.2.A)

**Текущий PR:** `/clantop` (задача 2.2.1).

> Эта задача задокументирована полностью; следующие задачи (2.2.2 —
> массовый PvP) будут описаны в новом handoff после мерджа 2.2.A.

### Шаг 1. Domain — `ClanTopEntry` VO

- `src/pipirik_wars/domain/clan/top.py`:
  - Frozen dataclass `ClanTopEntry`:
    - `clan_id: int`
    - `clan_title: ClanTitle`  (re-export)
    - `total_length_cm: int`  (сумма по всем `ACTIVE`-игрокам клана)
    - `member_count: int`     (количество `ACTIVE`-участников)
  - Валидация в `__post_init__`: `total_length_cm >= 0`, `member_count >= 0`.
- Обновить `domain/clan/__init__.py` — re-export `ClanTopEntry`.
- Тесты: `tests/unit/domain/clan/test_top_entry.py` —
  валидация + frozen.

**Почему в `domain/`, а не `application/`:** это инвариантный
«снимок», не зависящий от конкретного источника данных (БД vs кэш).
Точно так же, как `TopPlayerEntry` живёт в `application/top/entries.py`
(Спринт 1.4.C). Можно, по аналогии с 1.4.C, положить и в
`application/top/clan_entries.py` — выбрать один путь, согласовать
с существующим `TopPlayerEntry`. **Решение:** кладём в
`application/top/clan_entries.py` для симметрии.

### Шаг 2. Application — порт `IClanTopQuery` + use-case `GetTopClans`

Симметрично `ITopPlayersQuery` / `GetTopPlayers`:

- `src/pipirik_wars/application/top/clan_query.py` — `IClanTopQuery`:
  ```python
  async def get_top(self, *, limit: int) -> Sequence[ClanTopEntry]: ...
  ```
- `src/pipirik_wars/application/top/get_top_clans.py` — `GetTopClans`:
  - Тонкая обёртка над `IClanTopQuery.get_top`.
  - `default_limit: int = 50` (или сколько решит ГДД; в плане «топ кланов» — выбираем 50).
  - Валидация `limit > 0`.
- Расширить `application/top/__init__.py` re-export-ами.
- Тесты: `tests/unit/application/top/test_get_top_clans.py` —
  default-limit, override, invalid.

### Шаг 3. Domain — расширить `IClanRepository` методом `list_top_by_total_length`

- `src/pipirik_wars/domain/clan/repositories.py`:
  ```python
  @abc.abstractmethod
  async def list_top_by_total_length(self, *, limit: int) -> Sequence[ClanTopAggregate]:
      """Топ-N кланов по сумме длин ACTIVE-участников.
      ACTIVE — `Player.status == PlayerStatus.ACTIVE` и
      клан `ClanStatus.ACTIVE` (frozen-кланы пропускаются).
      Сортировка по `total_length_cm DESC`, тай-брейкер `clan_id ASC`.
      """
  ```
- `ClanTopAggregate` (новый VO в `domain/clan/value_objects.py` или рядом):
  - `clan_id: int`, `clan_title: ClanTitle`, `total_length_cm: int`, `member_count: int`.
  - Это «доменный read-model», аналог уже существующего паттерна в
    forest/oracle где есть подобные специфичные read-VO. Если
    избегать double-VO — можно использовать `ClanTopEntry` напрямую и
    отдавать его прямо из repo. **Решение:** отдаём `ClanTopEntry`
    из repo (порт-агрегат не нужен — `ClanTopEntry` без bizz-логики).
    Тогда `domain/clan/repositories.py` импортирует из
    `application/top/clan_entries.py` — это **нарушает** import-linter
    (domain не должен импортировать из application).
  - **Финальное решение:** держим VO в `domain/clan/top_entry.py`
    (`ClanTopEntry`), тогда `application/` импортирует его, а
    repo возвращает напрямую. Меняем шаг 1 — кладём VO в `domain/`.
    Re-export из `domain/clan/__init__.py`.

### Шаг 4. Infrastructure — `SqlAlchemyClanRepository.list_top_by_total_length`

- `src/pipirik_wars/infrastructure/db/repositories/clan.py`:
  - SQL-агрегация: JOIN `clans c` × `clan_members cm` × `players p`,
    GROUP BY `c.id`, SUM(p.length_cm), COUNT(p.id),
    WHERE `c.status='active' AND p.status='active'`,
    ORDER BY total DESC, `c.id` ASC, LIMIT `:limit`.
  - Кланы без активных участников **не** включаются (внутренний
    JOIN, не LEFT). Если требуется показывать «пустые» кланы — менять
    на LEFT и ставить total=0; пока что ГДД говорит «по сумме длин»,
    значит пустой клан суммой 0 не интересен.
  - Возврат: `tuple[ClanTopEntry, ...]`.
- Интеграционный тест: `tests/integration/db/clan/test_list_top.py`
  — вставить 3 клана + игроков, проверить порядок, проверить, что
  `frozen` кланы и `non-active` игроки исключены.

### Шаг 5. Infrastructure — кэш `ClanTopCache`

Симметрично `TopPlayersCache`:

- `src/pipirik_wars/infrastructure/cache/top_clans.py`:
  - `ClanTopCache(ITopClanQuery)` — TTL=60s, lock-protected refresh.
  - DI-параметры: `uow`, `clans` (репо), `clock`.
  - Аналогично `TopPlayersCache._refresh_locked` — читает срез из
    репо, кэширует.
- Тесты: `tests/unit/infrastructure/cache/test_top_clans.py` —
  fresh/expired/stampede через `FakeClock` + `FakeUnitOfWork`.

### Шаг 6. Bot/presenter + handler `/clantop`

- `src/pipirik_wars/bot/presenters/clantop.py` — `ClanTopPresenter`:
  - Локали: `clantop-header`, `clantop-empty`, `clantop-entry`
    (с плейсхолдерами `$rank`, `$title`, `$total_length_cm`, `$member_count`).
  - Формат строки: `<rank>. {clan_title} — {total_length_cm} см ({member_count} 👥)`.
- `src/pipirik_wars/bot/handlers/clantop.py` — `handle_clantop`:
  - `@router.message(Command("clantop"))` — публичная read-only команда,
    доступна и в ЛС, и в группе (как `/top`).
  - Использует `GetTopClans` + `ClanTopPresenter`.
  - Регистрация в `bot/handlers/__init__.py::register_routers`.
- Локали — `locales/ru.ftl` + `locales/en.ftl`:
  - `clantop-header`
  - `clantop-empty`
  - `clantop-entry = { $rank }. { $title } — { $total_length_cm } см ({ $member_count } 👥)`

### Шаг 7. DI — провязать в `bot/main.py`

- В `Container` добавить поле `top_clans_query: IClanTopQuery`,
  поле `get_top_clans: GetTopClans`.
- В `build_container()` создать `ClanTopCache(...)` + `GetTopClans(...)`.
- В `build_dispatcher()` добавить `dispatcher["get_top_clans"]`.
- Расширить `tests/unit/bot/test_composition_root.py` соответствующими
  fake-ами / новым полем Container.

### Шаг 8. Тесты handler-а + presenter-а

- `tests/unit/bot/handlers/test_clantop.py` — empty, non-empty,
  bundle-key-ы (по аналогии с `test_top.py`).
- `tests/unit/bot/presenters/test_clantop.py` — empty/non-empty rendering.

### Шаг 9. CI + PR

- `make ci` зелёный (≥80% coverage).
- Коммит-сообщения:
  - `feat(clan): ClanTopEntry VO + tests [Спринт 2.2.A шаг 1]`
  - `feat(clan): IClanTopQuery + GetTopClans use-case [Спринт 2.2.A шаг 2]`
  - `feat(clan): SqlAlchemyClanRepository.list_top_by_total_length [Спринт 2.2.A шаг 3-4]`
  - `feat(clan): ClanTopCache TTL=60s [Спринт 2.2.A шаг 5]`
  - `feat(clan): bot handler /clantop + presenter + locales [Спринт 2.2.A шаг 6-8]`
  - `feat(clan): DI wire GetTopClans in bot/main.py [Спринт 2.2.A шаг 7]`
- PR: `feat(clan): /clantop — top of clans by total length [Спринт 2.2.A]`.
- После мерджа — обновить `docs/current_tasks.md` (добавить строку
  2.2.A в таблицу спринта 2.2; статус ✅ смержено) **отдельным PR**.

## Текущий статус (обновляй на каждом коммите!)

- [x] Прочитал docs/current_tasks.md и docs/development_plan.md
- [x] Создал ветку `devin/<ts>-sprint-2-2-a-clantop` от свежего main
- [x] Создал AGENT_HANDOFF.md (этот файл)
- [ ] Шаг 1 (domain ClanTopEntry) — TODO
- [ ] Шаг 2 (application port + use-case) — TODO
- [ ] Шаг 3+4 (domain port + SQL repo) — TODO
- [ ] Шаг 5 (cache) — TODO
- [ ] Шаг 6 (bot handler + presenter + locales) — TODO
- [ ] Шаг 7 (DI) — TODO
- [ ] Шаг 8 (tests for handler/presenter) — TODO
- [ ] Шаг 9 (make ci + PR + CI green)

## Полезные ссылки в коде (для копирования паттернов)

- `TopPlayerEntry` — `src/pipirik_wars/application/top/entries.py`
- `ITopPlayersQuery` — `src/pipirik_wars/application/top/query.py`
- `GetTopPlayers` — `src/pipirik_wars/application/top/get_top.py`
- `TopPlayersCache` — `src/pipirik_wars/infrastructure/cache/top_players.py`
- `TopPresenter` — `src/pipirik_wars/bot/presenters/top.py`
- `handle_top` — `src/pipirik_wars/bot/handlers/top.py`
- DI/Container — `src/pipirik_wars/bot/main.py`
- ORM-таблицы — `src/pipirik_wars/infrastructure/db/orm/clan.py` и
  `…/player.py` (для агрегационного SQL).
- IClanRepository реализация — `src/pipirik_wars/infrastructure/db/repositories/clan.py`

## Что делать, если задача обрывается

1. Закоммить незавершённые изменения в текущую ветку с пометкой
   `[wip]` в commit-сообщении.
2. Обнови раздел «Текущий статус» в этом файле — отметь, какие шаги
   сделаны (`[x]`) и где остановился.
3. Запушь ветку.
4. Не удаляй HANDOFF.
5. Следующий агент: `git fetch && git checkout <ветка> && git pull` + читай
   текущий статус → продолжай со следующего невыполненного шага.

## После полного закрытия спринта 2.2

- Удалить AGENT_HANDOFF.md отдельным коммитом.
- Обновить `docs/current_tasks.md`: перенести спринт 2.2 в раздел
  «✅ Завершено» + добавить таблицу разбиения 2.2.A/B/...
- Дополнить `docs/history.md` (если такой файл — традиция этого репо).
