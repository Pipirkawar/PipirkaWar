"""Infrastructure-слой: реализации портов из application/.

Содержит:
- db/ — SQLAlchemy 2.x async, Unit-of-Work, репозитории, Alembic миграции.
- cache/ — in-memory + Redis adapters.
- scheduler/ — APScheduler с PG-jobstore.
- telegram/ — обёртка над aiogram-клиентом.
- payments/ — адаптеры Stars/TON/USDT.
- i18n/ — fluent loader.
- templates/ — JSON-шаблоны (логи, предсказания, пацанские цитаты).

Может импортировать:
- domain/ и application/.

НЕ ИМЕЕТ права импортировать:
- bot/, admin/ (они импортируют infrastructure, не наоборот).
"""
