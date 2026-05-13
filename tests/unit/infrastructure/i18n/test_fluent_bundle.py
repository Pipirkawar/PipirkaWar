"""Юнит-тесты `infrastructure.i18n.FluentMessageBundle` (Спринт 1.5.A).

Проверяем основные кейсы изолированно:
- Загрузка существующих RU/EN ключей.
- Подстановка параметров.
- Fallback с RU на EN при отсутствии ключа.
- `MessageKeyError` для ключа, отсутствующего в обеих локалях.
- `FileNotFoundError` для неподдерживаемого / отсутствующего файла локали.
- Кэширование bundle-а между вызовами.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipirik_wars.application.i18n import Locale, MessageKey, MessageKeyError
from pipirik_wars.infrastructure.i18n import FluentMessageBundle


@pytest.fixture
def locales_dir(tmp_path: Path) -> Path:
    """Каталог с минимальным набором .ftl для каждой локали.

    `ru.ftl` — содержит `greeting`, `start-registered`.
    `en.ftl` — содержит `greeting`, `start-registered`, `english-only`.
    """
    (tmp_path / "ru.ftl").write_text(
        "greeting = Привет, { $name }!\nstart-registered = 🍆 Готово!\n",
        encoding="utf-8",
    )
    (tmp_path / "en.ftl").write_text(
        "greeting = Hi, { $name }!\nstart-registered = 🍆 Done!\nenglish-only = Only in EN\n",
        encoding="utf-8",
    )
    return tmp_path


class TestFormatBasic:
    def test_renders_russian_with_param(self, locales_dir: Path) -> None:
        bundle = FluentMessageBundle(locales_dir=locales_dir)
        text = bundle.format(MessageKey("greeting"), locale=Locale("ru"), name="Игрок")
        assert "Игрок" in text
        assert text.startswith("Привет")

    def test_renders_english_with_param(self, locales_dir: Path) -> None:
        bundle = FluentMessageBundle(locales_dir=locales_dir)
        text = bundle.format(MessageKey("greeting"), locale=Locale("en"), name="Player")
        assert "Player" in text
        assert text.startswith("Hi")

    def test_no_params_works(self, locales_dir: Path) -> None:
        bundle = FluentMessageBundle(locales_dir=locales_dir)
        assert bundle.format(MessageKey("start-registered"), locale=Locale("ru")) == "🍆 Готово!"


class TestFallback:
    def test_missing_in_requested_locale_falls_back_to_english(
        self,
        locales_dir: Path,
    ) -> None:
        bundle = FluentMessageBundle(locales_dir=locales_dir)
        text = bundle.format(MessageKey("english-only"), locale=Locale("ru"))
        assert text == "Only in EN"

    def test_missing_everywhere_raises_message_key_error(
        self,
        locales_dir: Path,
    ) -> None:
        bundle = FluentMessageBundle(locales_dir=locales_dir)
        with pytest.raises(MessageKeyError) as exc:
            bundle.format(MessageKey("does-not-exist"), locale=Locale("ru"))
        assert "does-not-exist" in str(exc.value)


# Спринт 4.1-K (пункт 4.1.14): расширяем каталог локалей до 8 языков.
# Для каждой из 6 новых локалей (`pt`/`es`/`tr`/`id`/`fa`/`uk`) проверяем два
# базовых сценария фолбэка:
#   1. Ключ **есть в своём языке** → выбирается из своего языка (PT-значение).
#   2. Ключ **есть только в EN** → фолбэк на EN (подтверждает, что ~1550
#      оставшихся ключей работают в новых локалях из коробки).
# Для изоляции от реальных `locales/*.ftl` — пишем временные файлы в `tmp_path`.

_EXTRA_LOCALES: tuple[str, ...] = ("pt", "es", "tr", "id", "fa", "uk")


class TestExtraLocalesFallback:
    """Sprint 4.1-K: fallback на EN работает для каждой из 6 новых локалей."""

    @pytest.mark.parametrize("code", _EXTRA_LOCALES)
    def test_key_present_in_extra_locale_takes_precedence(
        self,
        tmp_path: Path,
        code: str,
    ) -> None:
        """K.5 сценарий 1: ключ есть и в EN, и в экстра-локали — рендерится экстра."""
        (tmp_path / "en.ftl").write_text(
            "greeting = Hi, { $name }!\n",
            encoding="utf-8",
        )
        (tmp_path / f"{code}.ftl").write_text(
            f"greeting = Hola-{code}, {{ $name }}!\n",
            encoding="utf-8",
        )
        bundle = FluentMessageBundle(locales_dir=tmp_path)

        text = bundle.format(MessageKey("greeting"), locale=Locale(code), name="P")

        assert text == f"Hola-{code}, P!"

    @pytest.mark.parametrize("code", _EXTRA_LOCALES)
    def test_key_missing_in_extra_locale_falls_back_to_english(
        self,
        tmp_path: Path,
        code: str,
    ) -> None:
        """K.5 сценарий 2: ключ есть только в `en.ftl` — fallback возвращает EN."""
        (tmp_path / "en.ftl").write_text(
            "english-only = Only in EN\n",
            encoding="utf-8",
        )
        # Экстра-локаль файл есть, но без этого ключа. Другой ключ проверяет,
        # что файл вообще загружается в `FluentBundle`-кеш.
        (tmp_path / f"{code}.ftl").write_text(
            f"native-key = Native {code}\n",
            encoding="utf-8",
        )
        bundle = FluentMessageBundle(locales_dir=tmp_path)

        assert bundle.format(MessageKey("english-only"), locale=Locale(code)) == "Only in EN"
        # Проверяем, что файл экстра-локали действительно подхватился (sanity check):
        assert bundle.format(MessageKey("native-key"), locale=Locale(code)) == f"Native {code}"


class TestCaching:
    def test_bundle_is_loaded_once_per_locale(self, locales_dir: Path) -> None:
        """Удаляем .ftl ПОСЛЕ первого вызова — второй вызов всё ещё работает,
        значит результат закэширован."""
        bundle = FluentMessageBundle(locales_dir=locales_dir)
        first = bundle.format(MessageKey("start-registered"), locale=Locale("ru"))
        (locales_dir / "ru.ftl").unlink()
        second = bundle.format(MessageKey("start-registered"), locale=Locale("ru"))
        assert first == second


class TestErrors:
    def test_missing_locale_file_raises_file_not_found(self, tmp_path: Path) -> None:
        # `tmp_path` пустой — нет ни ru.ftl, ни en.ftl.
        bundle = FluentMessageBundle(locales_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            bundle.format(MessageKey("anything"), locale=Locale("en"))

    def test_partial_files_still_supports_present_locale(
        self,
        tmp_path: Path,
    ) -> None:
        # Только en.ftl — если запрошена en, всё работает.
        (tmp_path / "en.ftl").write_text("only-en = hi\n", encoding="utf-8")
        bundle = FluentMessageBundle(locales_dir=tmp_path)
        assert bundle.format(MessageKey("only-en"), locale=Locale("en")) == "hi"
