"""YAML-writer балансовой конфигурации (Спринт 2.5-C.4).

Реализация `IBalanceWriter`. Применяет одно изменение по dotted-path
к `config/balance.yaml`, валидирует через pydantic-схему `BalanceConfig`,
атомарно сохраняет файл (`tmp + os.replace`) и обновляет кэш связанного
`YamlBalanceLoader.reload()`.

**Не сохраняет YAML-комментарии** — `yaml.safe_load` теряет их. Это
осознанное допущение для Спринта 2.5-C: правка балансовых констант
через `/balance_set` — точечная hot-fix-операция; основной workflow
правки — Pull Request к `config/balance.yaml` с code review. Если в
будущем понадобится сохранять комментарии (например, для
self-документирующихся YAML-файлов), мигрируем на `ruamel.yaml.YAML`.

File-lock semantics: используем `fcntl.flock` (advisory) на target-файле
до `os.replace`. Это сериализует одновременные `/balance_set` от разных
admin-инстансов (last-write-wins) и не позволяет читателю получить
полу-обновлённый файл в момент `replace` (POSIX `rename` атомарен на
одной FS). На non-Linux (Windows) `fcntl` отсутствует — пропускаем
lock; у нас 1 инстанс бота, так что race window пренебрежимо мал.
"""

from __future__ import annotations

import contextlib
import copy
import logging
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, ValidationError

from pipirik_wars.domain.balance.config import BalanceConfig
from pipirik_wars.domain.balance.errors import BalanceKeyError
from pipirik_wars.domain.balance.ports import IBalanceWriter
from pipirik_wars.shared.errors import ConfigError

if TYPE_CHECKING:
    from pipirik_wars.infrastructure.balance.loader import YamlBalanceLoader

try:
    import fcntl

    _HAS_FCNTL = True
except ImportError:  # pragma: no cover — Windows-fallback
    _HAS_FCNTL = False


_log = logging.getLogger(__name__)


class YamlBalanceWriter(IBalanceWriter):
    """Атомарная запись + reload связанного `YamlBalanceLoader`.

    `loader` — тот же экземпляр `YamlBalanceLoader`, что используется
    как `IBalanceConfig` в DI; после успешной записи мы зовём
    `loader.reload()`, чтобы in-memory кэш отразил новый файл.
    """

    __slots__ = ("_loader", "_path")

    def __init__(self, *, path: Path, loader: YamlBalanceLoader) -> None:
        self._path = path
        self._loader = loader

    def write_value(self, *, key: str, raw_value: Any) -> BalanceConfig:
        # 1. Прочитать YAML «как есть» (dict).
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as e:
            raise ConfigError(f"failed to read {self._path}: {e}") from e
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise ConfigError(f"invalid YAML in {self._path}: {e}") from e
        if not isinstance(raw, dict):
            raise ConfigError(
                f"{self._path}: root must be a YAML mapping, got {type(raw).__name__}"
            )

        # 2. Применить изменение по dotted-path. Используем «raw»-ключи
        # (то, что физически в YAML, в т.ч. alias-ы pydantic-полей —
        # `from`/`to`, а не `from_cm`/`to_cm`).
        new_raw = _apply_dotted_path(raw, key=key, value=raw_value)

        # 3. Валидировать новый dict через pydantic. **До** записи на диск.
        try:
            new_config = BalanceConfig.model_validate(new_raw)
        except ValidationError as e:
            raise ConfigError(
                f"setting {key!r}={raw_value!r} would break BalanceConfig: {e}"
            ) from e

        # 4. Атомарная запись (tmp в той же директории + os.replace).
        new_text = yaml.safe_dump(
            new_raw,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

        with _FileLock(self._path):
            tmp_fd, tmp_path = tempfile.mkstemp(
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                dir=str(self._path.parent),
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                    fh.write(new_text)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_path, self._path)
            except OSError as e:
                # tmp-файл подчищаем (best-effort) — DBA может его удалить.
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
                raise ConfigError(f"failed to write {self._path}: {e}") from e

        # 5. Hot-reload — кэш `YamlBalanceLoader` теперь видит новый файл.
        try:
            return self._loader.reload()
        except ConfigError:
            # Невозможно: только что валидировали.
            _log.exception("balance.yaml validated by writer but failed at loader.reload()")
            return new_config


def _apply_dotted_path(root: dict[str, Any], *, key: str, value: Any) -> dict[str, Any]:
    """Вернуть новый dict с применённым изменением по dotted-path.

    Не модифицирует исходный `root` (deep-copy под капотом). Бросает
    `BalanceKeyError` при невалидном path.
    """
    # Импортим здесь — `_balance_path` лежит в application-слое, а порт
    # должен жить выше; писатель — infrastructure, ниже application,
    # но мы переиспользуем helper для семантики.
    # Нет круга: `infrastructure` уже импортирует из `application` — это
    # запрещено import-linter-ом. Реализуем minimal navigator inline.
    if not key or not key.strip():
        raise BalanceKeyError(key=key, segment="", reason="empty")

    new_root = copy.deepcopy(root)
    parts = key.split(".")
    parent = _navigate_to_parent(new_root, key=key, parts=parts)
    last = parts[-1]
    _set_in_node(parent, segment=last, value=value, key=key)
    return new_root


def _navigate_to_parent(
    root: Any,
    *,
    key: str,
    parts: list[str],
) -> Any:
    """Дойти до **родителя** последнего сегмента и вернуть его.

    Возвращает контейнер (dict / list), в котором лежит target-поле.
    """
    node: Any = root
    for part in parts[:-1]:
        if not part:
            raise BalanceKeyError(key=key, segment=part, reason="empty_segment")
        node = _step_into(node, segment=part, key=key)
    return node


def _step_into(node: Any, *, segment: str, key: str) -> Any:
    if isinstance(node, dict):
        if segment not in node:
            raise BalanceKeyError(key=key, segment=segment, reason="not_found")
        return node[segment]
    if isinstance(node, list):
        if not _looks_like_int(segment):
            raise BalanceKeyError(key=key, segment=segment, reason="not_found")
        idx = int(segment)
        if idx < 0 or idx >= len(node):
            raise BalanceKeyError(key=key, segment=segment, reason="index_invalid")
        return node[idx]
    if isinstance(node, BaseModel):  # pragma: no cover — мы не поднимаемся в pydantic
        raise BalanceKeyError(key=key, segment=segment, reason="not_found")
    raise BalanceKeyError(key=key, segment=segment, reason="not_found")


def _set_in_node(parent: Any, *, segment: str, value: Any, key: str) -> None:
    if isinstance(parent, dict):
        if segment not in parent:
            raise BalanceKeyError(key=key, segment=segment, reason="not_found")
        parent[segment] = value
        return
    if isinstance(parent, list):
        if not _looks_like_int(segment):
            raise BalanceKeyError(key=key, segment=segment, reason="not_found")
        idx = int(segment)
        if idx < 0 or idx >= len(parent):
            raise BalanceKeyError(key=key, segment=segment, reason="index_invalid")
        parent[idx] = value
        return
    raise BalanceKeyError(key=key, segment=segment, reason="not_found")


def _looks_like_int(value: str) -> bool:
    if not value:
        return False
    body = value[1:] if value[0] in "+-" else value
    return body.isdigit()


class _FileLock:
    """Контекст-менеджер advisory-lock для writer-а.

    На POSIX блокирует **directory**-файл (`config/`), а не `balance.yaml` —
    последний мы заменим через `os.replace`, и lock на нём потеряется
    в момент replace. На non-POSIX — no-op.
    """

    __slots__ = ("_fd", "_lock_path")

    def __init__(self, target_path: Path) -> None:
        # Lock-файл `<dir>/.<name>.lock`; не путаем с tmp-файлом writer-а.
        self._lock_path = target_path.parent / f".{target_path.name}.lock"
        self._fd: int | None = None

    def __enter__(self) -> _FileLock:
        if not _HAS_FCNTL:  # pragma: no cover — non-Linux
            return self
        self._fd = os.open(
            str(self._lock_path),
            os.O_CREAT | os.O_RDWR,
            0o644,
        )
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *_args: object) -> None:
        if self._fd is None:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None


__all__ = ["YamlBalanceWriter"]
