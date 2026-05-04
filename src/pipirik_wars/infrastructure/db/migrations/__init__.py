"""Alembic migrations.

`env.py` — стандартный entry point Alembic; `versions/` — версионные
файлы. URL берётся из env (`DATABASE_URL`) через `pydantic-settings`,
не из `alembic.ini`.
"""
