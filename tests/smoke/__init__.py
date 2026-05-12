"""Smoke-тесты: production-стек end-to-end на mocked-транспорте.

Отличие от unit/integration:
* Unit/integration берут конкретный класс изолированно (`FakeTonRpcClient` /
  in-memory UoW).  Smoke собирает **полную production-цепочку** —
  `TonRpcHttpClient` + `Ed25519MessageSigner` + `JettonUsdtProvider` +
  `TonRpcAdapter` — и гоняет её через `httpx.MockTransport` без живой
  сети.  Это «sanity-check»: каждый прод-класс инстанцируется так, как
  в `bot/main.py::build_container(...)`, и адаптер шлёт corrrectly
  сформированный HTTP-запрос для каждого payout-flow-а.
* Marker `smoke` (`@pytest.mark.smoke`) — позволяет выбрать только
  smoke-тесты через `pytest -m smoke tests/smoke/` или `make smoke`.
  По умолчанию они идут в общий `pytest`-прогон, потому что быстрые
  (<200ms на тест).
"""
