"""Доменные общие штуки.

`ports/` — интерфейсы для адаптеров (часы, RNG, UoW, idempotency, audit).
В domain нельзя импортировать ничего из infrastructure/bot/admin — это
проверяется import-linter (см. `.importlinter`).
"""
