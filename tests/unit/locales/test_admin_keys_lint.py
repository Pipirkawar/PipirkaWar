"""Lint-тесты по FTL-локалям (Спринт 2.5-D.12).

Эти тесты — это статический аудит файлов `locales/{ru,en}.ftl` и Python-исходников
проекта. Они не запускают handler-ы и не вызывают `MessageBundle` — их задача
поймать классы багов, которые в production проявляются «беззвучно»:

1. **Дубликаты Message-ID в одном FTL-файле.** Mozilla Fluent при дубликатах
   молча оставляет первое определение, а второе игнорирует — без warning-а в
   рантайме. До D.12 в обоих файлах было по 5 таких дублей в `admin-confirm-*`,
   из-за чего админам отдавались устаревшие тексты от Спринта 2.5-A.3 вместо
   обновлённых из 2.5-B (`<code>{ $token }</code>` со substitution-ом).

2. **Расхождение RU↔EN.** Если ключ есть в одной локали и нет в другой,
   `FluentMessageBundle.format` сделает fallback на default (`en`). Для
   обратной локали (RU без EN) это явно ломает RU-юзеров — fallback идёт в
   обратную сторону и выдаёт английский текст. Эти тесты падают если хотя бы
   один admin-* (или любой другой) ключ присутствует только в одной из локалей.

3. **Используемый, но не определённый admin-ключ.** Если код зовёт ключ,
   которого нет в .ftl — `FluentMessageBundle.format` бросит `MessageKeyError`.
   В юнит-тестах handler-ов используется `_StubBundle`, который не валидирует
   наличие ключа в реальной локали, поэтому такие баги ловит только этот
   lint-тест или e2e.

4. **Orphan admin-ключ.** Если ключ есть в .ftl, но нигде в коде на него нет
   ссылки — это мёртвый код. До D.12 такими были `admin-confirm-prompt` и
   `admin-confirm-success` (наследие 2.5-A.3, вытеснённые per-команда
   `*-confirm-issued`/`admin-confirm-success-{cmd}`).

Тесты намеренно строгие: при добавлении нового ключа разработчик обязан
добавить его _и_ в `ru.ftl`, _и_ в `en.ftl`, _и_ зацепить из кода. Это
обратимо — ничего не падает на проде, упадёт CI.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Final

import pytest
from fluent.syntax import parse as fluent_parse
from fluent.syntax.ast import Message, Resource, Term

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_LOCALES_DIR: Final[Path] = _REPO_ROOT / "locales"
_SRC_DIR: Final[Path] = _REPO_ROOT / "src"

_SUPPORTED_LOCALES: Final[tuple[str, ...]] = ("ru", "en")
_ADMIN_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^admin-[a-z][a-z0-9-]+$")


def _parse_ftl(path: Path) -> Resource:
    return fluent_parse(path.read_text(encoding="utf-8"))


def _message_ids(resource: Resource) -> list[str]:
    """Все Message-ID файла в порядке появления (без Term-ов и Comment-ов)."""
    out: list[str] = []
    for entry in resource.body:
        if isinstance(entry, Message) and not isinstance(entry, Term):
            out.append(entry.id.name)
    return out


def _admin_keys_from_source() -> set[str]:
    """Собирает все строковые литералы вида `admin-*` из *.py в src/.

    Только `ast.Constant` — это исключает f-string-фрагменты и комментарии,
    оставляя именно те ключи, которые попадают в `MessageKey(...)` или
    в `bundle.format(...)`. Если ключ собран из частей через
    конкатенацию/.format() — он сюда не попадёт; именно поэтому в кодовой
    базе договор: ключи должны быть _литералами_ ради статической
    валидации (см. `bot/presenters/admin_*.py`).
    """
    keys: set[str] = set()
    for path in _SRC_DIR.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:  # pragma: no cover — мы парсим только валидные .py
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and _ADMIN_KEY_RE.match(node.value)
            ):
                keys.add(node.value)
    return keys


@pytest.fixture(scope="module")
def used_admin_keys() -> set[str]:
    return _admin_keys_from_source()


@pytest.fixture(scope="module")
def locale_resources() -> dict[str, Resource]:
    return {code: _parse_ftl(_LOCALES_DIR / f"{code}.ftl") for code in _SUPPORTED_LOCALES}


class TestNoDuplicateKeys:
    """Каждый Message-ID встречается в файле ровно один раз."""

    @pytest.mark.parametrize("code", _SUPPORTED_LOCALES)
    def test_no_duplicate_message_ids(
        self,
        code: str,
        locale_resources: dict[str, Resource],
    ) -> None:
        ids = _message_ids(locale_resources[code])
        counts = Counter(ids)
        duplicates = sorted(name for name, count in counts.items() if count > 1)
        assert duplicates == [], (
            f"locales/{code}.ftl: дубликаты Message-ID — Fluent молча "
            f"берёт первое определение и игнорирует остальные: {duplicates}"
        )


class TestLocaleParity:
    """RU↔EN: ключи должны совпадать множествами (no one-sided keys)."""

    def test_full_parity(self, locale_resources: dict[str, Resource]) -> None:
        ru_ids = set(_message_ids(locale_resources["ru"]))
        en_ids = set(_message_ids(locale_resources["en"]))
        only_ru = sorted(ru_ids - en_ids)
        only_en = sorted(en_ids - ru_ids)
        assert only_ru == [], f"ключи только в ru.ftl (нет EN-перевода): {only_ru}"
        assert only_en == [], f"ключи только в en.ftl (нет RU-перевода): {only_en}"

    def test_admin_keys_parity(self, locale_resources: dict[str, Resource]) -> None:
        """То же самое, но фокусированно на admin-* — admin-команды критичны."""
        ru_admin = {k for k in _message_ids(locale_resources["ru"]) if _ADMIN_KEY_RE.match(k)}
        en_admin = {k for k in _message_ids(locale_resources["en"]) if _ADMIN_KEY_RE.match(k)}
        only_ru = sorted(ru_admin - en_admin)
        only_en = sorted(en_admin - ru_admin)
        assert only_ru == [], f"admin-* только в ru.ftl: {only_ru}"
        assert only_en == [], f"admin-* только в en.ftl: {only_en}"


class TestAdminKeysCoverage:
    """Каждый admin-* ключ из кода присутствует в обеих локалях."""

    @pytest.mark.parametrize("code", _SUPPORTED_LOCALES)
    def test_no_missing_admin_keys(
        self,
        code: str,
        used_admin_keys: set[str],
        locale_resources: dict[str, Resource],
    ) -> None:
        defined = set(_message_ids(locale_resources[code]))
        missing = sorted(used_admin_keys - defined)
        assert missing == [], (
            f"locales/{code}.ftl: ключи зовутся из src/, но не определены в "
            f"локали — `FluentMessageBundle.format` бросит MessageKeyError: "
            f"{missing}"
        )


class TestNoOrphanAdminKeys:
    """Каждый admin-* ключ в .ftl должен быть зацеплен из кода."""

    @pytest.mark.parametrize("code", _SUPPORTED_LOCALES)
    def test_no_orphan_admin_keys(
        self,
        code: str,
        used_admin_keys: set[str],
        locale_resources: dict[str, Resource],
    ) -> None:
        admin_in_locale = {
            k for k in _message_ids(locale_resources[code]) if _ADMIN_KEY_RE.match(k)
        }
        orphans = sorted(admin_in_locale - used_admin_keys)
        assert orphans == [], (
            f"locales/{code}.ftl: admin-* ключи определены, но нигде в src/ не "
            f"используются — мёртвый код: {orphans}"
        )


class TestSanityCounts:
    """Защита от того, что наши регэкспы/AST-обходы вдруг перестали что-то находить.

    Без этих guard-ов lint-тесты выше могут «зелёно проходить» при пустых
    множествах. Цифры snapshot-ятся по факту состояния на момент D.12 (после
    дедупликации) и поднимаются по мере роста проекта.
    """

    def test_used_admin_keys_not_empty(self, used_admin_keys: set[str]) -> None:
        # На момент D.12 в коде 147 admin-* ключей. Регрессия ниже 100 —
        # значит, AST-обход сломан и реальная проверка не работает.
        assert len(used_admin_keys) >= 100, (
            f"AST-обход src/ нашёл всего {len(used_admin_keys)} admin-* ключей —"
            " подозрительно мало; вероятно, поломался _admin_keys_from_source()."
        )

    @pytest.mark.parametrize("code", _SUPPORTED_LOCALES)
    def test_locale_admin_keys_not_empty(
        self,
        code: str,
        locale_resources: dict[str, Resource],
    ) -> None:
        admin_count = sum(1 for k in _message_ids(locale_resources[code]) if _ADMIN_KEY_RE.match(k))
        assert admin_count >= 100, (
            f"locales/{code}.ftl: всего {admin_count} admin-* ключей — подозрительно мало."
        )
