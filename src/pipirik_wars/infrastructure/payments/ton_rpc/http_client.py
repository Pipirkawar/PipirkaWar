"""Реальный HTTP-клиент TON-RPC (Спринт 4.1-D, шаг D.10.a).

`TonRpcHttpClient` — production-имплементация `ITonRpcClient`
(`infrastructure/payments/ton_rpc/client.py::ITonRpcClient`) поверх
**TON Center API v2** (`https://[testnet.]toncenter.com/api/v2`).

В D.5 `ITonRpcClient` оставался Protocol-ом и в проде не запускался —
все классы D.5-уровня (`TonRpcAdapter` / `TonRpcFeeEstimator` /
`JettonUsdtProvider`) тестировались на `FakeTonRpcClient`. В D.10.a мы
закрываем эту дыру: реальная HTTP-имплементация позволяет
composition-root-у (`bot/main.py::Container`, шаг D.10.c) запустить
TON-RPC-стек без mock-ов.

Принципы:

* **Тонкий клиент.** Один метод `_post_json` — единственное место, где
  происходит сетевой вызов; остальные `run_get_method` / `send_boc` /
  `recent_fees` лишь форматируют JSON-payload и парсят ответ. Это
  делает класс полностью покрытым unit-тестами через `httpx.MockTransport`
  — без `pytest-httpx` / `respx` / живой сети.
* **Fail-loud.** Любой не-`ok` ответ TON Center-а (`{"ok": false, ...}`),
  HTTP 4xx/5xx, или нестабильный JSON конвертируется в
  `TonRpcCallError`/`TonRpcTimeoutError` с сохранением `endpoint` /
  `method` для трассировки. Caller (`TonRpcAdapter`, `TonRpcFeeEstimator`)
  знает, как реагировать (см. их docstring-и).
* **Без retries / circuit-breaker-ов.** D.10.a — это слой транспорта.
  Логику повторов / backoff-а несёт application-слой (`ClaimPrize`,
  D.7 уже это делает через try/except + аудит refund-веток).
* **TON Center API key.** Если `settings.api_key` задан, добавляем
  заголовок `X-API-Key: <secret>` (toncenter-style). Значение —
  `SecretStr.get_secret_value()`; в логи не уходит.
* **Парсинг `recent_fees`.** TON Center не отдаёт сводной P95-статистики;
  отдаёт сырые транзакции через `/getTransactions?address=...&limit=N`.
  Мы делаем единственный GET, отфильтровываем by `now - days <= utime`
  и возвращаем `RecentFee(fee_native, occurred_at)` для каждой
  валидной транзакции. P95-расчёт остаётся в `TonRpcFeeEstimator`.

Что специально вынесено за скобки D.10.a:

* Polling статуса tx после `send_boc` — это задача
  `ClaimPrize`-handler-а (D.7). TON Center `/sendBoc` возвращает только
  `{"@type": "ok"}` без hash; реальная цепочка получает hash либо из
  `boc.cell.hash` (вычисляется до publish), либо через `/lookupBlock` +
  `/getTransactions(account=payout_wallet)`. На D.10.a мы возвращаем
  стабильный hash из тела BOC-а (`sha256` поверх base64-decoded BOC) —
  это даёт детерминированный, integration-friendly `tx_hash` без
  дополнительного polling-а.
* `actual_fee_native` в ответе на `send_boc` — TON Center также не
  возвращает; мы выставляем `0` (caller обновит реальную комиссию
  через post-факт polling или примет fallback-буфер из
  `TonRpcSettings`). Это поведение совпадает с FakeTonRpcClient-ом
  на дефолтном `queue_send_boc(actual_fee_native=0)`.

Тесты — в `tests/unit/infrastructure/payments/ton_rpc/test_http_client.py`
(D.10.a-юнит, без живой сети) через `httpx.MockTransport`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import httpx

from pipirik_wars.infrastructure.payments.ton_rpc.client import (
    BocSendResult,
    RecentFee,
    RunGetMethodResult,
)
from pipirik_wars.infrastructure.payments.ton_rpc.errors import (
    TonRpcCallError,
    TonRpcTimeoutError,
)
from pipirik_wars.infrastructure.payments.ton_rpc.settings import TonRpcSettings

__all__ = ["TonRpcHttpClient"]


# Имена TON Center эндпоинтов (`/api/v2/<endpoint>`). См. документацию
# toncenter.com/api/v2/ (Swagger-схема публична).
_ENDPOINT_RUN_GET_METHOD: Final[str] = "runGetMethod"
_ENDPOINT_SEND_BOC: Final[str] = "sendBoc"
_ENDPOINT_GET_TRANSACTIONS: Final[str] = "getTransactions"

# Лимит «сколько последних транзакций забираем» при запросе истории
# комиссий. TON Center жёстко режет `limit=256` на странице; берём 256,
# чего хватает для 7-дневного окна по hot-wallet-у при ожидаемой
# пропускной способности (≤ 36 выплат/час = ≤ 6048/неделю → нужно
# несколько страниц, но D.10.a сознательно держит один-page-запрос:
# нам важна свежая выборка для P95, а не полная история).
_RECENT_TRANSACTIONS_LIMIT: Final[int] = 256

_logger = logging.getLogger(__name__)


def _parse_toncenter_envelope(
    *,
    body: dict[str, Any],
    endpoint: str,
    method: str,
) -> dict[str, Any]:
    """Развернуть `{"ok": true, "result": ...}` или поднять `TonRpcCallError`.

    TON Center API заворачивает все успешные ответы в `ok=true`-конверт;
    ошибки приходят с `ok=false` + `error: "..."`. Эта функция —
    единственная точка обработки конверта; все остальные парсеры
    работают уже с `result`-телом.

    Если ответ не словарь, или нет `ok`/`result`, бросаем
    `TonRpcCallError` (контракт сломан — это infrastructure-bug,
    не application-кейс).
    """
    if not isinstance(body, dict):
        raise TonRpcCallError(
            f"toncenter envelope not a dict: type={type(body).__name__}",
            endpoint=endpoint,
            method=method,
        )
    if not body.get("ok", False):
        error_message = body.get("error") or body.get("result") or "unknown toncenter error"
        raise TonRpcCallError(
            f"toncenter returned ok=false: {error_message}",
            endpoint=endpoint,
            method=method,
        )
    result = body.get("result")
    if not isinstance(result, dict):
        # `sendBoc` иногда отдаёт result как строку `"OK"` / `"@type"`-объект;
        # это всё равно dict. Если пришёл не-dict — обрабатываем как ошибку
        # формата.
        raise TonRpcCallError(
            f"toncenter result not a dict: type={type(result).__name__}",
            endpoint=endpoint,
            method=method,
        )
    return result


def _stack_entry_to_str(entry: Any) -> str:
    """Сериализовать один элемент стека `runGetMethod` в строку.

    TON Center отдаёт стек как массив пар `[type, value]`, где `type`
    — это `"num"` / `"cell"` / `"slice"` / `"tuple"`, а `value` —
    либо строка (`"0x..."`, base64-encoded BOC), либо вложенный объект.
    Для нашего D.5-уровня (`JettonUsdtProvider.resolve_wallet`) хватает
    плоской строковой репрезентации: caller (`jetton.py`) парсит её
    локально.

    На вход — необработанный `entry` из JSON; на выход — `str`. На
    нестандартных формах (массив, dict) возвращаем JSON-string, чтобы
    caller получил хоть какую-то детерминированную форму.
    """
    if isinstance(entry, list) and len(entry) == 2:
        type_tag, value = entry
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            # TON Center заворачивает cell-объекты в `{"bytes": "<base64>"}` или
            # `{"object": {...}}`. Возвращаем `bytes` напрямую, иначе — JSON.
            bytes_value = value.get("bytes")
            if isinstance(bytes_value, str):
                return bytes_value
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        return json.dumps([type_tag, value], sort_keys=True, separators=(",", ":"))
    if isinstance(entry, str):
        return entry
    return json.dumps(entry, sort_keys=True, separators=(",", ":"))


def _derive_tx_hash_from_boc(signed_boc_base64: str) -> str:
    """Вывести детерминированный `tx_hash` из тела BOC-а.

    TON Center API v2 `/sendBoc` не возвращает hash транзакции в ответе.
    Реальный hash появляется в блокчейне после mine-инга и резолвится
    отдельным polling-вызовом (`/getTransactions`). На D.10.a мы делаем
    pragmatic-shortcut: возвращаем `sha256(boc-bytes).hexdigest()` —
    это **не** настоящий on-chain tx_hash, но он:
    * детерминирован (caller может коррелировать выплату с записью в БД),
    * уникален для каждого нового BOC-а,
    * не требует второго round-trip-а к TON Center-у.

    Если caller хочет настоящий on-chain hash, он подписывается на
    polling-loop в `ClaimPrize` (D.7) — это application-уровневая
    задача.

    На невалидный base64 возвращаем `sha256(<строка as utf-8>).hexdigest()`,
    чтобы не падать; caller увидит, что hash не совпадает с любым
    on-chain-значением, и поднимет alert.
    """
    try:
        raw = base64.b64decode(signed_boc_base64, validate=False)
    except (ValueError, TypeError):
        raw = signed_boc_base64.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class TonRpcHttpClient:
    """Production HTTP-имплементация `ITonRpcClient` поверх `httpx.AsyncClient`.

    Все три метода — асинхронные. Конструируется DI-фабрикой
    `bot/main.py::Container` (шаг D.10.c) одним инстансом на процесс
    бота: `httpx.AsyncClient` держит keep-alive-пул соединений и
    допускает concurrent-вызовы; thread-/async-safe.

    Конструктор-параметры:
    * `settings: TonRpcSettings` — берём `endpoint`, `api_key`,
      `request_timeout_seconds`. Остальное (jetton-master, hot-wallet,
      fallback-fee, fee-window-days) этому классу не нужно — он
      работает на сетевом уровне.
    * `http_client: httpx.AsyncClient | None` — опциональная inject-ия
      готового `AsyncClient`-а. В тестах это `AsyncClient(transport=httpx.MockTransport(...))`,
      в проде — конструктор создаёт свой `AsyncClient` с timeout-ом
      из настроек.

    Жизненный цикл: вызывайте `await client.aclose()` при shutdown-е
    бота (см. `bot/main.py::run()`).
    """

    __slots__ = ("_endpoint", "_http_client", "_owns_http_client", "_settings", "_timeout")

    def __init__(
        self,
        *,
        settings: TonRpcSettings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        # Нормализуем endpoint: убираем trailing slash (контракт `TonRpcSettings`).
        self._endpoint = settings.endpoint.rstrip("/")
        self._timeout = httpx.Timeout(settings.request_timeout_seconds)
        if http_client is None:
            headers = self._build_default_headers()
            self._http_client = httpx.AsyncClient(timeout=self._timeout, headers=headers)
            self._owns_http_client = True
        else:
            self._http_client = http_client
            self._owns_http_client = False

    async def aclose(self) -> None:
        """Закрыть HTTP-пул, если клиент создан этим классом.

        Если `http_client` был передан извне (тесты / shared singleton),
        мы его НЕ закрываем — caller отвечает за lifecycle.
        """
        if self._owns_http_client:
            await self._http_client.aclose()

    def _build_default_headers(self) -> dict[str, str]:
        """Сформировать headers по умолчанию для всех запросов.

        Если `api_key` задан, добавляем `X-API-Key: <secret>`. Имя
        заголовка совпадает с toncenter-style («X-API-Key» — single
        canonical form, без префикса `Bearer`).
        """
        headers = {"Content-Type": "application/json"}
        if self._settings.api_key is not None:
            headers["X-API-Key"] = self._settings.api_key.get_secret_value()
        return headers

    async def _post_json(
        self,
        *,
        path: str,
        payload: dict[str, Any],
        method: str,
    ) -> dict[str, Any]:
        """Отправить POST с JSON-телом и развернуть toncenter-конверт.

        Конвертирует все сетевые / HTTP-ошибки в `TonRpcCallError` /
        `TonRpcTimeoutError`. Логирует на DEBUG-уровне (под HTTP-timeout
        — на WARNING, чтобы операторы видели транзиентные сбои TON-ноды).
        """
        url = f"{self._endpoint}/{path}"
        try:
            response = await self._http_client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            _logger.warning(
                "ton_rpc_http_client: timeout on POST %s (timeout=%ss)",
                path,
                self._settings.request_timeout_seconds,
            )
            raise TonRpcTimeoutError(
                f"toncenter POST {path} timed out",
                timeout_seconds=self._settings.request_timeout_seconds,
                endpoint=url,
                method=method,
            ) from exc
        except httpx.HTTPError as exc:
            raise TonRpcCallError(
                f"toncenter POST {path} failed: {exc}",
                endpoint=url,
                method=method,
            ) from exc

        if response.status_code >= 400:
            raise TonRpcCallError(
                f"toncenter POST {path} returned HTTP {response.status_code}",
                endpoint=url,
                method=method,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise TonRpcCallError(
                f"toncenter POST {path} returned non-JSON body",
                endpoint=url,
                method=method,
            ) from exc

        return _parse_toncenter_envelope(body=body, endpoint=url, method=method)

    async def _get_json(
        self,
        *,
        path: str,
        params: dict[str, str | int],
        method: str,
    ) -> dict[str, Any] | list[Any]:
        """Отправить GET с query-параметрами и развернуть toncenter-конверт.

        Для `/getTransactions` toncenter возвращает `result: [<tx>, ...]`
        (список), не словарь. Поэтому возвращаем `dict | list` — caller
        проверяет тип сам.

        Замечание: `_parse_toncenter_envelope` требует `result` быть
        словарём; здесь мы делаем inline-обработку, чтобы поддержать
        list-result-ы.
        """
        url = f"{self._endpoint}/{path}"
        try:
            response = await self._http_client.get(url, params=params)
        except httpx.TimeoutException as exc:
            _logger.warning(
                "ton_rpc_http_client: timeout on GET %s (timeout=%ss)",
                path,
                self._settings.request_timeout_seconds,
            )
            raise TonRpcTimeoutError(
                f"toncenter GET {path} timed out",
                timeout_seconds=self._settings.request_timeout_seconds,
                endpoint=url,
                method=method,
            ) from exc
        except httpx.HTTPError as exc:
            raise TonRpcCallError(
                f"toncenter GET {path} failed: {exc}",
                endpoint=url,
                method=method,
            ) from exc

        if response.status_code >= 400:
            raise TonRpcCallError(
                f"toncenter GET {path} returned HTTP {response.status_code}",
                endpoint=url,
                method=method,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise TonRpcCallError(
                f"toncenter GET {path} returned non-JSON body",
                endpoint=url,
                method=method,
            ) from exc

        if not isinstance(body, dict):
            raise TonRpcCallError(
                f"toncenter envelope not a dict: type={type(body).__name__}",
                endpoint=url,
                method=method,
            )
        if not body.get("ok", False):
            error_message = body.get("error") or "unknown toncenter error"
            raise TonRpcCallError(
                f"toncenter GET {path} returned ok=false: {error_message}",
                endpoint=url,
                method=method,
            )
        result = body.get("result")
        if not isinstance(result, dict | list):
            raise TonRpcCallError(
                f"toncenter result not a dict/list: type={type(result).__name__}",
                endpoint=url,
                method=method,
            )
        return result

    # ---- ITonRpcClient implementation -----------------------------------

    async def run_get_method(
        self,
        *,
        address: str,
        method: str,
        stack: Sequence[str] = (),
    ) -> RunGetMethodResult:
        """См. `ITonRpcClient.run_get_method`."""
        payload: dict[str, Any] = {
            "address": address,
            "method": method,
            "stack": list(stack),
        }
        result = await self._post_json(
            path=_ENDPOINT_RUN_GET_METHOD,
            payload=payload,
            method=method,
        )
        exit_code_raw = result.get("exit_code", -1)
        try:
            exit_code = int(exit_code_raw)
        except (TypeError, ValueError) as exc:
            raise TonRpcCallError(
                f"toncenter runGetMethod returned non-int exit_code: {exit_code_raw!r}",
                endpoint=f"{self._endpoint}/{_ENDPOINT_RUN_GET_METHOD}",
                method=method,
            ) from exc

        stack_raw = result.get("stack", [])
        if not isinstance(stack_raw, list):
            raise TonRpcCallError(
                f"toncenter runGetMethod returned non-list stack: {type(stack_raw).__name__}",
                endpoint=f"{self._endpoint}/{_ENDPOINT_RUN_GET_METHOD}",
                method=method,
            )
        stack_parsed = tuple(_stack_entry_to_str(entry) for entry in stack_raw)
        return RunGetMethodResult(exit_code=exit_code, stack=stack_parsed)

    async def send_boc(
        self,
        *,
        signed_boc_base64: str,
    ) -> BocSendResult:
        """См. `ITonRpcClient.send_boc`.

        TON Center `/sendBoc` принимает `{"boc": "<base64>"}` и возвращает
        `{"ok": true, "result": {"@type": "ok"}}` без хеша. Мы выводим
        `tx_hash` из `sha256(boc-bytes)` (см. `_derive_tx_hash_from_boc`)
        и возвращаем `actual_fee_native=0` (toncenter не отдаёт fee на
        этом эндпоинте; полный fee резолвится после mine-инга через
        `/getTransactions` — D.10.b / D.7 могут поллить и обновлять).
        """
        await self._post_json(
            path=_ENDPOINT_SEND_BOC,
            payload={"boc": signed_boc_base64},
            method="sendBoc",
        )
        tx_hash = _derive_tx_hash_from_boc(signed_boc_base64)
        return BocSendResult(tx_hash=tx_hash, actual_fee_native=0)

    async def recent_fees(
        self,
        *,
        address: str,
        days: int,
    ) -> Sequence[RecentFee]:
        """См. `ITonRpcClient.recent_fees`.

        Запрашиваем `/getTransactions?address=<addr>&limit=256` и
        фильтруем по `utime >= now - days*86400`. Каждой транзакции
        соответствует один `RecentFee` с `fee_native=<fee>` и
        `occurred_at=<utc-from-utime>`. Возвращаем кортеж в
        хронологическом порядке (старые → новые).
        """
        if days < 1:
            raise ValueError(
                f"TonRpcHttpClient.recent_fees: days must be >= 1, got {days}",
            )
        result = await self._get_json(
            path=_ENDPOINT_GET_TRANSACTIONS,
            params={"address": address, "limit": _RECENT_TRANSACTIONS_LIMIT},
            method="getTransactions",
        )
        if not isinstance(result, list):
            raise TonRpcCallError(
                f"toncenter getTransactions returned non-list: {type(result).__name__}",
                endpoint=f"{self._endpoint}/{_ENDPOINT_GET_TRANSACTIONS}",
                method="getTransactions",
            )

        cutoff_utime = int(
            (datetime.now(tz=UTC) - timedelta(days=days)).timestamp(),
        )
        fees: list[RecentFee] = []
        for tx in result:
            if not isinstance(tx, dict):
                continue
            utime_raw = tx.get("utime")
            fee_raw = tx.get("fee")
            if utime_raw is None or fee_raw is None:
                continue
            try:
                utime = int(utime_raw)
                fee_native = int(fee_raw)
            except (TypeError, ValueError):
                continue
            if utime < cutoff_utime:
                continue
            if fee_native < 0:
                continue
            occurred_at = datetime.fromtimestamp(utime, tz=UTC)
            fees.append(RecentFee(fee_native=fee_native, occurred_at=occurred_at))
        fees.sort(key=lambda fee: fee.occurred_at)
        return tuple(fees)
