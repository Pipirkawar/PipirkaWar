"""In-memory `IMessageBundle` для тестов (Спринт 1.5.B).

`FakeMessageBundle.format(...)` возвращает маркерную строку
``<locale>:<key>[k=v,...]`` — это даёт тестам два преимущества:

1. **Однозначная идентификация ключа.** Тест проверяет, что handler
   просит именно `start-registered`, а не другой ключ — без
   привязки к реальному переводу.
2. **Сериализованные параметры.** `assert_awaited_once_with(...)`
   видит и сам ключ, и переданные плейсхолдеры (например, `position`).

Класс не зависит от `fluent.runtime` и не читает файлы — это
удерживает `tests/unit/...` от случайной зависимости от
инфраструктурного слоя.
"""

from __future__ import annotations

from pipirik_wars.application.i18n import Locale, MessageKey


class FakeMessageBundle:
    """Маркерная реализация `IMessageBundle`."""

    def format(
        self,
        key: MessageKey,
        *,
        locale: Locale,
        **params: object,
    ) -> str:
        suffix = ""
        if params:
            kv = ",".join(f"{k}={v}" for k, v in sorted(params.items()))
            suffix = f"[{kv}]"
        return f"{locale.code}:{key}{suffix}"


__all__ = ["FakeMessageBundle"]
