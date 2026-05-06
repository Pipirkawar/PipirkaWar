"""Dotted-path lookup для `BalanceConfig` (Спринт 2.5-C.3 / C.4).

`/balance_get forest.cooldown_min_minutes` → нужно из иерархии
pydantic-моделей `BalanceConfig` достать значение по строковому пути.
То же — для `/balance_set` (set операции — задача C.4).

API:

- `lookup_path(config, key)` — вернуть значение по dotted-path.
  Возвращает «raw»-представление: для `BaseModel` — `dict` (`model_dump()`),
  для `tuple` — `list`, для скаляров — как есть. Это позволяет
  presenter-у безопасно сериализовать значение для Telegram.

- `lookup_raw_node(config, key)` — вернуть **узел** по path (промежуточный
  pydantic-объект ИЛИ скаляр), без преобразования. Используется
  `SetBalanceValue`, чтобы понять тип target-поля до подмены.

Ошибки:

- `BalanceKeyError(key, segment, reason="empty"|"not_found"|"index_invalid")`
  — пустой path / segment не существует / некорректный индекс по
  списку (`items_catalog.99`, в каталоге всего 5 записей). Handler
  ловит и сообщает «ключ не найден» с локализованным текстом.

Семантика индексации списков (для каталогов):

- `items_catalog.0.id` — индекс через целое число; если `int(part)`
  парсится — лезем по индексу. Иначе — `getattr` по имени.
- Граница: индекс должен быть `0 <= i < len(node)`; иначе
  `BalanceKeyError(reason="index_invalid")`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class BalanceKeyError(KeyError):
    """Dotted-path в `BalanceConfig` не разрешается."""

    __slots__ = ("key", "reason", "segment")

    def __init__(self, *, key: str, segment: str, reason: str) -> None:
        super().__init__(f"balance key {key!r} invalid at segment {segment!r}: {reason}")
        self.key = key
        self.segment = segment
        self.reason = reason


def _navigate_node(root: BaseModel, key: str) -> Any:
    """Внутренний обход. Возвращает «сырой» узел (pydantic-модель / скаляр / tuple)."""
    if not key or not key.strip():
        raise BalanceKeyError(key=key, segment="", reason="empty")

    parts = key.split(".")
    node: Any = root
    for part in parts:
        if not part:
            raise BalanceKeyError(key=key, segment=part, reason="empty_segment")

        if isinstance(node, BaseModel):
            field_name = _resolve_pydantic_field(node, part)
            if field_name is None:
                raise BalanceKeyError(key=key, segment=part, reason="not_found")
            node = getattr(node, field_name)
            continue

        if isinstance(node, dict):
            if part not in node:
                raise BalanceKeyError(key=key, segment=part, reason="not_found")
            node = node[part]
            continue

        if isinstance(node, tuple | list):
            if not _looks_like_int(part):
                raise BalanceKeyError(key=key, segment=part, reason="not_found")
            idx = int(part)
            if idx < 0 or idx >= len(node):
                raise BalanceKeyError(key=key, segment=part, reason="index_invalid")
            node = node[idx]
            continue

        # Скаляр в середине пути (например, `forest.cooldown_min_minutes.foo`).
        raise BalanceKeyError(key=key, segment=part, reason="not_found")

    return node


def lookup_path(root: BaseModel, key: str) -> Any:
    """Вернуть значение по dotted-path как «raw» (json-friendly).

    Pydantic-модели → `dict` через `model_dump()`. Tuple → list.
    Скаляры (int/float/str/bool/None) — как есть.
    """
    node = _navigate_node(root, key)
    return _to_raw(node)


def lookup_raw_node(root: BaseModel, key: str) -> Any:
    """Вернуть «узел» по dotted-path без преобразований.

    Используется `SetBalanceValue`, чтобы определить тип target-поля
    (нужно для приведения raw-строки к нужному скаляру).
    """
    return _navigate_node(root, key)


def _to_raw(node: Any) -> Any:
    if isinstance(node, BaseModel):
        # by_alias=True — чтобы JSON-ответ читался так же, как `balance.yaml`
        # (поле `from`, а не `from_cm`). Навигация поддерживает оба варианта,
        # но рендерим в YAML-стиле, чтобы экономист видел знакомую форму.
        return node.model_dump(mode="json", by_alias=True)
    if isinstance(node, tuple):
        return [_to_raw(item) for item in node]
    if isinstance(node, list):
        return [_to_raw(item) for item in node]
    if isinstance(node, dict):
        return {k: _to_raw(v) for k, v in node.items()}
    return node


def _resolve_pydantic_field(node: BaseModel, part: str) -> str | None:
    """Найти имя поля в pydantic-модели по имени или по alias-у.

    Возвращает реальное имя поля (`from_cm`), даже если caller передал alias
    (`from`). `None`, если поле не найдено.
    """
    fields = node.__class__.model_fields
    if part in fields:
        return part
    for field_name, field_info in fields.items():
        if field_info.alias == part:
            return field_name
    return None


def _looks_like_int(value: str) -> bool:
    if not value:
        return False
    body = value[1:] if value[0] in "+-" else value
    return body.isdigit()


__all__ = ["BalanceKeyError", "lookup_path", "lookup_raw_node"]
