"""SQLAlchemy 2.x async — БД-адаптеры.

`base` — declarative `Base`, общий для всех моделей.
`engine` — фабрика async engine + sessionmaker.
`uow` — реализация `IUnitOfWork`.
`models/` — ORM-модели (idempotency_keys, audit_log, activity_locks, admins).
`repositories/` — реализации доменных портов.
`services/` — реализации сервисных портов (`IIdempotencyKey`, `IAuditLogger`).
"""
